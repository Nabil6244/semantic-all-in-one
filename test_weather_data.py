"""Weather data layer (no network): time zones, the NWS client and its cache, products from recorded responses, alerts,
the satellite time, the snapshot and the freshness rules."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from weather import tz
from weather.alerts import alert_areas, alert_color
from weather.cache import HttpCache, Response, expires_at
from weather.cities import find_city
from weather.nws import NwsClient, NwsError, check_contact
from weather.resolve import (Snapshot, StaleDataError, check_fresh, f_from_c, fetch_forecast, fetch_observation, geocolor_times, icon_for,
                             pick_geocolor_time, prepare)
from weather.sidecar import parse_sidecar

DATA = Path(__file__).resolve().parent / "weather" / "testdata"
UTC = timezone.utc


def fixture(name):
    return (DATA / name).read_bytes()


class FakeNet:
    """URL -> (status, body); records every call and every User-Agent."""

    def __init__(self, routes, now=datetime(2026, 10, 12, 21, 0, tzinfo=UTC)):
        self.routes, self.calls, self.now = dict(routes), [], now

    def __call__(self, url, headers):
        self.calls.append((url, headers))
        r = self.routes.get(url)
        if r is None:
            return Response(404, b'{"detail": "not found"}', {}, self.now)
        if callable(r):
            return r()
        status, body = r
        return Response(status, body, {"cache-control": "public, max-age=600"}, self.now)


API = "https://api.weather.gov"
DALLAS_ROUTES = {
    f"{API}/points/32.7767,-96.7970": (200, fixture("points_dallas.json")),
    f"{API}/gridpoints/FWD/89,104/forecast": (200, fixture("forecast_dallas.json")),
    f"{API}/stations/KDFW/observations/latest": (200, fixture("obs_kdfw.json")),
    f"{API}/alerts/active?status=actual&area=TX": (200, fixture("alerts_tx.json")),
}


class TimeZones(unittest.TestCase):
    def test_us_daylight_saving_switches_at_2am_local_on_the_right_sundays(self):
        z = "America/Chicago"
        # 2026: DST from Sunday 8 March 08:00 UTC (2:00 CST) to Sunday 1 November 07:00 UTC (2:00 CDT)
        self.assertEqual(tz.to_local(datetime(2026, 3, 8, 7, 59, tzinfo=UTC), z)[1], "CST")
        self.assertEqual(tz.to_local(datetime(2026, 3, 8, 8, 0, tzinfo=UTC), z)[1], "CDT")
        self.assertEqual(tz.to_local(datetime(2026, 11, 1, 6, 59, tzinfo=UTC), z)[1], "CDT")
        self.assertEqual(tz.to_local(datetime(2026, 11, 1, 7, 0, tzinfo=UTC), z)[1], "CST")

    def test_clock_text_and_zones_without_daylight_saving(self):
        t = datetime(2026, 10, 12, 21, 11, 46, tzinfo=UTC)
        self.assertEqual(tz.clock(t, "America/Chicago"), "4:11 PM CDT")
        self.assertEqual(tz.clock(t, "America/New_York", date=True), "Oct 12, 5:11 PM EDT")
        self.assertEqual(tz.clock(t, "America/Phoenix"), "2:11 PM MST")
        self.assertEqual(tz.clock(t, "Pacific/Honolulu"), "11:11 AM HST")
        self.assertEqual(tz.clock(datetime(2026, 10, 12, 5, 0, tzinfo=UTC), "America/Chicago"), "12:00 AM CDT")
        self.assertEqual(tz.weekday(t, "America/Los_Angeles"), "MON")

    def test_an_unknown_zone_or_a_naive_time_is_refused(self):
        with self.assertRaises(ValueError):
            tz.zone("Europe/Paris")
        with self.assertRaises(ValueError):
            tz.to_local(datetime(2026, 1, 1), "America/Chicago")


class Conversions(unittest.TestCase):
    def test_celsius_to_whole_fahrenheit_rounds_halves_up(self):
        self.assertEqual(f_from_c(31), 88)       # 87.8
        self.assertEqual(f_from_c(30.5), 87)     # 86.9
        self.assertEqual(f_from_c(25), 77)
        self.assertEqual(f_from_c(-40), -40)
        self.assertEqual(f_from_c(0.25), 32)     # 32.45
        self.assertEqual(f_from_c(0.2778), 33)   # 32.50004

    def test_icons_follow_the_nws_wording(self):
        cases = {"Chance Showers And Thunderstorms": "storm", "Mostly Sunny": "partly", "Sunny": "sun", "Partly Cloudy": "partly",
                 "Mostly Cloudy": "cloud", "Light Rain": "rain", "Snow Showers": "snow", "Patchy Fog": "fog", "Freezing Rain": "sleet",
                 "Breezy": "wind", "Something Else": "cloud"}
        for text, icon in cases.items():
            self.assertEqual(icon_for(text), icon, text)
        self.assertEqual(icon_for("Clear", is_day=False), "moon")
        self.assertEqual(icon_for("Partly Cloudy", is_day=False), "partly_night")


class Client(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = HttpCache(Path(self.tmp.name), now=lambda: datetime(2026, 10, 12, 21, 0, tzinfo=UTC))

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_contact_no_fetch_and_the_contact_must_be_an_email_or_a_website(self):
        for bad in ("", "   ", "my name", "ftp://x"):
            with self.assertRaises(NwsError):
                check_contact(bad)
        self.assertEqual(check_contact(" me@example.com "), "me@example.com")
        self.assertEqual(check_contact("https://example.com/contact"), "https://example.com/contact")
        with self.assertRaises(NwsError):
            NwsClient("", cache=self.cache)

    def test_the_contact_goes_in_the_user_agent(self):
        net = FakeNet(DALLAS_ROUTES)
        NwsClient("me@example.com", cache=self.cache, fetch=net).point(32.7767, -96.797)
        self.assertIn("(me@example.com)", net.calls[0][1]["User-Agent"])
        self.assertEqual(net.calls[0][1]["Accept"], "application/geo+json")

    def test_server_trouble_is_retried_with_a_growing_pause_then_succeeds(self):
        url = f"{API}/points/32.7767,-96.7970"
        answers = iter([Response(503, b"", {}, datetime.now(UTC)), Response(429, b"", {"retry-after": "3"}, datetime.now(UTC)),
                        Response(200, fixture("points_dallas.json"), {}, datetime.now(UTC))])
        slept = []
        c = NwsClient("me@example.com", cache=self.cache, fetch=FakeNet({url: lambda: next(answers)}), sleep=slept.append)
        props, _ = c.point(32.7767, -96.797)
        self.assertEqual(props["gridId"], "FWD")
        self.assertEqual(slept, [1.0, 3.0])

    def test_a_4xx_is_reported_at_once_with_the_url_and_endless_trouble_gives_up(self):
        c = NwsClient("me@example.com", cache=self.cache, fetch=FakeNet({}), sleep=lambda s: None)
        with self.assertRaisesRegex(NwsError, r"points/1.0000,2.0000 answered HTTP 404"):
            c.point(1, 2)
        url = f"{API}/points/1.0000,2.0000"
        c2 = NwsClient("me@example.com", cache=self.cache, fetch=FakeNet({url: (500, b"")}), sleep=lambda s: None, retries=2)
        with self.assertRaisesRegex(NwsError, "after 3 tries"):
            c2.point(1, 2)

    def test_the_cache_answers_inside_the_window_and_fetches_again_after_it(self):
        clock = [datetime(2026, 10, 12, 21, 0, tzinfo=UTC)]
        cache = HttpCache(Path(self.tmp.name) / "c2", now=lambda: clock[0])
        net = FakeNet(DALLAS_ROUTES)
        c = NwsClient("me@example.com", cache=cache, fetch=net)
        c.point(32.7767, -96.797)
        c.point(32.7767, -96.797)
        self.assertEqual(len(net.calls), 1)               # max-age=600: the second answer is the cached one
        clock[0] += timedelta(minutes=11)
        c.point(32.7767, -96.797)
        self.assertEqual(len(net.calls), 2)

    def test_expires_reads_max_age_then_expires_then_the_default(self):
        t = datetime(2026, 10, 12, 21, 0, tzinfo=UTC)
        self.assertEqual(expires_at({"cache-control": "s-maxage=1, max-age=90"}, t, 3600), t + timedelta(seconds=90))
        self.assertEqual(expires_at({"expires": "Mon, 12 Oct 2026 21:30:00 GMT"}, t, 3600), t + timedelta(minutes=30))
        self.assertEqual(expires_at({}, t, 3600), t + timedelta(hours=1))


class Products(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = datetime(2026, 10, 12, 21, 0, tzinfo=UTC)
        self.client = NwsClient("me@example.com", cache=HttpCache(Path(self.tmp.name), now=lambda: self.now), fetch=FakeNet(DALLAS_ROUTES))

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_forecast_pairs_each_day_with_its_night_and_keeps_its_source(self):
        notes = []
        f = fetch_forecast(self.client, find_city("Dallas, TX"), notes)
        raw = json.loads(fixture("forecast_dallas.json"))["properties"]
        self.assertEqual(f["issued"], raw["updateTime"])
        self.assertEqual(f["grid"], "FWD 89,104")
        self.assertEqual(notes, [])
        periods = raw["periods"]
        d0 = f["days"][0]
        self.assertEqual(d0["high"]["value"], periods[0]["temperature"])   # Columbus Day (daytime)
        self.assertEqual(d0["low"]["value"], periods[1]["temperature"])    # Tonight
        self.assertEqual(d0["dow"], "MON")
        self.assertEqual(d0["high"]["url"], f"{API}/gridpoints/FWD/89,104/forecast")
        self.assertEqual(d0["high"]["where"], "FWD 89,104")
        self.assertEqual(d0["high"]["issued"], raw["updateTime"])
        self.assertEqual([d["dow"] for d in f["days"]], ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"])
        for d, (day, night) in zip(f["days"], zip(periods[0::2], periods[1::2])):
            self.assertEqual((d["high"]["value"], d["low"]["value"]), (day["temperature"], night["temperature"]))

    def test_a_forecast_starting_at_night_begins_with_the_next_day(self):
        raw = json.loads(fixture("forecast_dallas.json"))
        raw["properties"]["periods"] = raw["properties"]["periods"][1:]   # first period is "Tonight"
        routes = dict(DALLAS_ROUTES)
        routes[f"{API}/gridpoints/FWD/89,104/forecast"] = (200, json.dumps(raw).encode())
        c = NwsClient("me@example.com", cache=HttpCache(Path(self.tmp.name) / "n", now=lambda: self.now), fetch=FakeNet(routes))
        f = fetch_forecast(c, find_city("Dallas, TX"), [])
        self.assertEqual(f["days"][0]["dow"], "TUE")
        self.assertEqual(f["days"][0]["high"]["value"], raw["properties"]["periods"][1]["temperature"])

    def test_the_observation_is_converted_and_a_silent_station_is_skipped(self):
        routes = dict(DALLAS_ROUTES)
        empty = json.loads(fixture("obs_kdfw.json"))
        empty["properties"]["temperature"]["value"] = None
        routes[f"{API}/stations/KDFW/observations/latest"] = (200, json.dumps(empty).encode())
        routes[f"{API}/stations/KDAL/observations/latest"] = (200, fixture("obs_kdfw.json"))
        c = NwsClient("me@example.com", cache=HttpCache(Path(self.tmp.name) / "o", now=lambda: self.now), fetch=FakeNet(routes))
        notes = []
        o = fetch_observation(c, find_city("Dallas, TX"), self.now, notes)
        self.assertEqual(o["station"], "KDAL")
        self.assertEqual(o["temp"]["value"], 88)      # 31 C
        self.assertEqual(o["temp"]["product"], "NWS observation")
        self.assertIn("skipped KDFW (no temperature reported)", notes[0])

    def test_an_observation_older_than_six_hours_is_not_used(self):
        with self.assertRaisesRegex(NwsError, "h old"):
            fetch_observation(self.client, find_city("Dallas, TX"), self.now + timedelta(hours=7), [])

    def test_alerts_use_their_own_polygon_else_the_bundled_county_shapes(self):
        s = alert_areas(json.loads(fixture("alerts_tx.json")))
        by = {a.event: a for a in s.areas}
        self.assertEqual(by["Flood Warning"].how, "polygon")
        self.assertEqual(by["Rip Current Statement"].how, "counties")
        self.assertIn("48321", by["Rip Current Statement"].counties)
        self.assertTrue(all(isinstance(p, list) and p for p in by["Coastal Flood Advisory"].polys))
        self.assertEqual(s.skipped, [])
        self.assertEqual(by["Flood Warning"].color, "#00FF00")

    def test_a_marine_alert_is_left_out_and_said_so(self):
        fc = {"features": [{"geometry": None, "properties": {"event": "Gale Warning", "areaDesc": "Coastal waters", "geocode": {"SAME": ["077250"]}}}]}
        s = alert_areas(fc)
        self.assertEqual(s.areas, [])
        self.assertIn("Gale Warning", s.skipped[0])
        self.assertEqual(alert_color("Unheard Of", "Severe"), "#F28C28")


class Satellite(unittest.TestCase):
    def test_latest_is_the_newest_listed_picture_and_a_named_time_must_be_listed(self):
        iv = geocolor_times(fixture("gibs_geocolor_domain.xml").decode())
        self.assertEqual(len(iv), 2)
        now = datetime(2026, 10, 12, 22, 0, tzinfo=UTC)
        self.assertEqual(pick_geocolor_time("latest", now, iv), datetime(2026, 10, 12, 21, 10, tzinfo=UTC))
        self.assertEqual(pick_geocolor_time("2026-10-12T16:10Z", now, iv), datetime(2026, 10, 12, 16, 10, tzinfo=UTC))
        with self.assertRaisesRegex(NwsError, "no picture"):
            pick_geocolor_time("2026-10-12T16:00Z", now, iv)     # the gap in the listing
        with self.assertRaises(NwsError):
            pick_geocolor_time("latest", datetime(2026, 10, 1, tzinfo=UTC), iv)


SIDE = """beat,vo_anchor,t,id,type,place,data_source,hold,until,extra
b1,,1,sat,satellite,,gibs:geocolor@latest,,end,
b1,,1,dal,temp_marker,"Dallas, TX","nws:forecast@Dallas,TX#day1",,,
b1,,1,strip,forecast_strip,"Dallas, TX","nws:forecast@Dallas,TX#day1-5",,,
b1,,1,now,now_card,"Dallas, TX","nws:obs@Dallas,TX",,,
b1,,1,al,alert_area,TX,nws:alerts@TX,,,
b1,,1,src,source_line,,,,,
"""


class SnapshotAndFreshness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = datetime(2026, 10, 12, 21, 0, tzinfo=UTC)
        self.client = NwsClient("me@example.com", cache=HttpCache(Path(self.tmp.name), now=lambda: self.now), fetch=FakeNet(DALLAS_ROUTES))
        self.gibs = lambda url: fixture("gibs_geocolor_domain.xml").decode()

    def tearDown(self):
        self.tmp.cleanup()

    def test_prep_fetches_each_product_once_and_the_snapshot_round_trips(self):
        snap = prepare(parse_sidecar(SIDE), self.client, now=self.now, gibs_get=self.gibs)
        self.assertEqual(list(snap.forecasts), ["Dallas, TX"])
        self.assertEqual(snap.observations["Dallas, TX"]["temp"]["value"], 88)
        self.assertEqual(snap.satellite["geocolor@latest"]["time"], "2026-10-12T21:00:00Z")
        urls = [u for u, _ in self.client.fetch.calls]
        self.assertEqual(len(urls), len(set(urls)))                  # nothing fetched twice
        again = Snapshot.from_json(snap.to_json())
        self.assertEqual(again.to_json(), snap.to_json())

    def test_a_forecast_older_than_six_hours_is_refused_at_prep_and_at_render(self):
        late = datetime(2026, 10, 13, 0, 30, tzinfo=UTC)     # forecast updateTime 18:26 UTC: 6.1 h later
        with self.assertRaisesRegex(StaleDataError, r"Dallas, TX forecast was issued 6\.1 h ago"):
            prepare(parse_sidecar(SIDE.replace("b1,,1,now,now_card,\"Dallas, TX\",\"nws:obs@Dallas,TX\",,,\n", "")
                                  .replace("b1,,1,al,alert_area,TX,nws:alerts@TX,,,\n", "")), self.client, now=late, gibs_get=self.gibs)
        snap = prepare(parse_sidecar(SIDE), self.client, now=self.now, gibs_get=self.gibs)
        check_fresh(snap, self.now + timedelta(hours=1))
        with self.assertRaisesRegex(StaleDataError, "not fresh enough to render"):
            check_fresh(snap, self.now + timedelta(hours=6))

    def test_an_alert_that_has_ended_by_render_time_is_refused(self):
        snap = prepare(parse_sidecar(SIDE), self.client, now=self.now, gibs_get=self.gibs)
        # Rip Current Statement ends 19:00 CDT = 00:00 UTC on the 13th
        with self.assertRaisesRegex(StaleDataError, r"alert\(s\) for TX have ended \(.*Rip Current Statement"):
            check_fresh(snap, datetime(2026, 10, 13, 0, 5, tzinfo=UTC))

    def test_an_old_snapshot_version_must_be_fetched_again(self):
        with self.assertRaisesRegex(ValueError, "fetch again"):
            Snapshot.from_json(json.dumps({"version": 0, "prepared": "x"}))


if __name__ == "__main__":
    unittest.main()
