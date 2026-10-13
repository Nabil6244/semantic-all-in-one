"""Phase 5 "Suggested reports" feed (weather/post/feed.py) on stub answers: NWS past alerts over pages, SPC report days (a missing day
is skipped and named), and the prompt's event line."""

import unittest
from datetime import datetime, timezone

from weather.post.feed import alert_history, event_text, report_history, suggestions

NOW = datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc)


def alert(event, ugc, onset, ends):
    return {"properties": {"event": event, "geocode": {"UGC": ugc}, "onset": onset, "ends": ends}}


class Client:
    def __init__(self):
        self.urls = []

    def get_json(self, url):
        self.urls.append(url)
        if "page2" in url:
            return {"features": [alert("Flash Flood Warning", ["TXC201"], "2026-10-08T01:00:00Z", "2026-10-08T07:00:00Z")]}, None
        return {"features": [alert("Flash Flood Warning", ["TXC201", "TXZ213"], "2026-10-07T20:00:00Z", "2026-10-08T02:00:00Z"),
                             alert("Flood Warning", ["TXC157"], "2026-10-08T03:00:00Z", "2026-10-09T03:00:00Z"),
                             alert("Special Weather Statement", ["TXZ213"], "2026-10-08T03:00:00Z", "2026-10-08T05:00:00Z"),
                             alert("Flash Flood Warning", ["XXZ001"], "2026-10-08T03:00:00Z", "2026-10-08T05:00:00Z")],
                "pagination": {"next": "https://api.weather.gov/alerts?page2"}}, None


SPC = ("Time,F_Scale,Location,County,State,Lat,Lon,Comments\n"
       "Time,Speed,Location,County,State,Lat,Lon,Comments\n2130,UNK,3 N Katy,Harris,TX,29.83,-95.82,trees down\n"
       "Time,Size,Location,County,State,Lat,Lon,Comments\n")


def get_text(url):
    if "261012" in url:
        return SPC
    raise OSError("404")


class Feed(unittest.TestCase):
    def test_every_page_and_only_significant_warnings_over_us_states(self):
        c = Client()
        a = alert_history(c, NOW)
        self.assertEqual(len(c.urls), 2)
        self.assertIn("event=", c.urls[0])
        self.assertEqual([(x["event"], x["states"]) for x in a],
                         [("Flash Flood Warning", ["TX"]), ("Flood Warning", ["TX"]), ("Flash Flood Warning", ["TX"])])

    def test_report_days_and_a_missing_day(self):
        reports, missing = report_history(get_text, NOW, days=3)
        self.assertEqual([(r["kind"], r["state"]) for r in reports], [("wind", "TX")])
        self.assertEqual(missing, ["2026-10-11", "2026-10-10"])

    def test_a_texas_flood_is_suggested_with_its_event_line(self):
        found, problems = suggestions(Client(), get_text, NOW)
        self.assertEqual([s.state for s in found], ["TX"])
        line = event_text(found[0])
        self.assertTrue(line.startswith("THE EVENT: "))
        self.assertIn("State: TX. Dates (UTC): 2026-10-07 to 2026-10-09", line)
        self.assertTrue(problems and "SPC storm reports missing" in problems[0])
        self.assertEqual(suggestions(Client(), get_text, NOW, already=[found[0].id])[0], [])


if __name__ == "__main__":
    unittest.main()
