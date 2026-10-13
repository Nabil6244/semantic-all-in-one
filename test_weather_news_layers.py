"""Weather News layer types end to end without network: weather_layers.csv rows -> resolve.prepare (recorded answers) ->
events.build. Radar frames and clock labels, satellite loops, NHC cone and tracks, SPC/WPC areas, storm reports, archived
warnings in step with the radar, counters, freshness, and every number in the numbers report."""

import json
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from weather.events import build
from weather.resolve import Snapshot, StaleDataError, check_fresh, prepare
from weather.sidecar import SidecarError, parse_sidecar
from weather.timing import Window

DATA = Path(__file__).resolve().parent / "weather" / "testdata" / "news"
UTC = timezone.utc
NOW = datetime(2026, 10, 13, 5, 40, tzinfo=UTC)
HEAD = "beat,vo_anchor,t,id,type,place,data_source,hold,until,extra\n"
ROUTES = {
    "json/radar?operation=list&product=N0Q&radar=USCOMP&start=2022-09-28T14:00Z": "iem_radar_list_ian.json",
    "n0q_0.json": "iem_n0q_latest.json",
    "json/radar?operation=list": "iem_radar_list_latest.json",
    "al092022_5day_030.zip": "al092022_5day_030.zip",
    "al092022_best_track.zip": "al092022_best_track_pts_lin.zip",
    "day1otlk_20240506_1300_cat": None,
    "day1otlk_20240506_1200_cat": None,
    "day1otlk_20240506_1630_cat": "spc_day1otlk_20240506_1630_cat.geojson",
    "outlook/day1otlk_cat.nolyr.geojson": "spc_day1otlk_latest.geojson",
    "240506_rpts_filtered.csv": "spc_240506_rpts_filtered.csv",
    "shp_94e_2022092809.zip": "ero_94e_2022092809.zip",
    "Day1_Latest.geojson": "wpc_ero_day1_latest.geojson",
    "sbw.geojson": "sbw_ian_fl.geojson",
}


class Net:
    def __init__(self):
        self.calls = []

    def bytes(self, url):
        self.calls.append(url)
        for k, name in ROUTES.items():
            if k in url:
                if name is None:
                    raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
                return (DATA / name).read_bytes()
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    def text(self, url):
        return self.bytes(url).decode("utf-8")


def run(rows_csv, windows=None, now=NOW):
    rows = parse_sidecar(HEAD + rows_csv)
    net = Net()
    snap = prepare(rows, None, now=now, get_text=net.text, get_bytes=net.bytes)
    snap = Snapshot.from_json(snap.to_json())   # what the render reads back
    win = windows or {r.id: Window(10.0, 30.0) for r in rows}
    return rows, snap, build(rows, snap, win), net


class Radar(unittest.TestCase):
    def test_archive_loop(self):
        rows, snap, out, net = run('b1,,10,rad,radar,"Fort Myers, FL",iem:radar@2022-09-28T14:00Z..2022-09-28T22:00Z#n0q,,,"{""frames"": 17}"\n'
                                   "b1,,10,src,source_line,,,,,\n")
        r = out.rasters[0]
        self.assertEqual((r["id"], r["t_in"], r["t_out"], r["above_fills"], r["clock"]), ("wx_rad", 10.0, 30.0, True, True))
        self.assertEqual(len(r["frames"]), 17)
        self.assertEqual(r["frames"][0]["label"], "RADAR · 10:00 AM EDT")
        self.assertEqual(r["frames"][-1]["label"], "RADAR · 6:00 PM EDT")
        self.assertEqual(r["frames"][0]["at"], 0.0)
        self.assertAlmostEqual(r["frames"][-1]["at"], 17.0)        # 85 % of the 20 s layer; the end holds
        ats = [f["at"] for f in r["frames"]]
        self.assertEqual(ats, sorted(ats))
        self.assertIn("ridge::USCOMP-N0Q-202209281400/{z}/{x}/{y}.png", r["frames"][0]["provider"]["urlTemplate"])
        self.assertEqual(len({f["provider"]["id"] for f in r["frames"]}), 17)
        legend = [e for e in out.events if e["type"] == "radar_legend"][0]
        self.assertEqual([lb["text"] for lb in legend["labels"]], ["LIGHT", "HEAVY", "HAIL"])
        src = [e for e in out.events if e["type"] == "source_line"][0]["text"]
        self.assertIn("Radar: NOAA/NWS NEXRAD via Iowa Environmental Mesonet, Sep 28, 10:00 AM–6:00 PM EDT", src)
        self.assertTrue(any("Iowa Environmental Mesonet" in c for c in out.credits))
        self.assertEqual(out.report.lines[0]["layer"], "rad")
        self.assertIn("json/radar", out.report.lines[0]["url"])

    def test_tz_extra_and_no_legend(self):
        _r, _s, out, _n = run('b1,,10,rad,radar,,iem:radar@2022-09-28T14:00Z..2022-09-28T22:00Z#n0q,,,"{""tz"": ""America/Chicago"", ""legend"": false}"\n')
        self.assertEqual(out.rasters[0]["frames"][0]["label"], "RADAR · 9:00 AM CDT")
        self.assertFalse([e for e in out.events if e["type"] == "radar_legend"])

    def test_latest_is_fresh_then_stale(self):
        rows, snap, out, _n = run("b1,,10,rad,radar,TX,iem:radar@latest#n0q,,,\n", now=NOW)
        self.assertEqual(len(out.rasters[0]["frames"]), 18)
        check_fresh(snap, NOW)
        with self.assertRaisesRegex(StaleDataError, r"latest radar .* ago \(more than 1 h\)"):
            check_fresh(snap, datetime(2026, 10, 13, 8, 0, tzinfo=UTC))

    def test_archive_never_stale(self):
        _r, snap, _o, _n = run("b1,,10,rad,radar,FL,iem:radar@2022-09-28T14:00Z..2022-09-28T22:00Z#n0q,,,\n")
        check_fresh(snap, datetime(2030, 1, 1, tzinfo=UTC))

    def test_provider_none_and_bad_rows(self):
        _r, _s, out, net = run('b1,,10,rad,radar,FL,iem:radar@2022-09-28T14:00Z..2022-09-28T22:00Z#n0q,,,"{""provider"": ""none""}"\nb1,,10,src,source_line,,,,,\n')
        self.assertEqual(out.rasters, [])
        self.assertEqual(net.calls, [])
        self.assertIn("Radar not shown", [e for e in out.events if e["type"] == "source_line"][0]["text"])
        for bad, msg in [("iem:radar@2022-09-28T14:00Z..2022-09-28T22:00Z#n0r", "takes #n0q"),
                         ("iem:radar@2022-09-28..2022-09-29#n0q", "UTC time like"),
                         ("iem:radar@2022-09-28T14:00Z..2022-10-08T22:00Z#n0q", "longer than 48 hours")]:
            with self.assertRaisesRegex(SidecarError, f"row 2.*{msg}"):
                parse_sidecar(HEAD + f"b1,,10,rad,radar,FL,{bad},,,\n")
        with self.assertRaisesRegex(SidecarError, "row 2.*unknown radar provider"):
            parse_sidecar(HEAD + 'b1,,10,rad,radar,FL,iem:radar@latest#n0q,,,"{""provider"": ""acme""}"\n')

    def test_fetch_error_names_the_row(self):
        rows = parse_sidecar(HEAD + "b1,,10,rad,radar,FL,iem:radar@2022-09-28T14:00Z..2022-09-28T22:00Z#n0q,,,\n")
        with self.assertRaisesRegex(ValueError, r"weather_layers.csv row 2 \(rad\): .*lists no radar picture"):
            prepare(rows, None, now=NOW, get_text=lambda u: '{"scans": []}', get_bytes=lambda u: b"")


class SatelliteLoop(unittest.TestCase):
    def test_daily_truecolor(self):
        _r, _s, out, net = run("b1,,10,sat,satellite_loop,FL,gibs:truecolor_loop@2022-09-25..2022-09-29,,,\n")
        r = out.rasters[0]
        self.assertEqual(len(r["frames"]), 5)
        self.assertFalse(r["above_fills"])
        self.assertEqual(r["opacity"], 1.0)
        self.assertEqual([f["label"] for f in r["frames"]][:2], ["SATELLITE · SEP 25", "SATELLITE · SEP 26"])
        self.assertIn("VIIRS_SNPP_CorrectedReflectance_TrueColor/default/2022-09-28/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg",
                      r["frames"][3]["provider"]["urlTemplate"])
        self.assertEqual(net.calls, [])

    def test_geocolor_too_old(self):
        rows = parse_sidecar(HEAD + "b1,,10,sat,satellite_loop,FL,gibs:geocolor_loop@2022-09-28T15:00Z..2022-09-28T19:00Z,,,\n")
        domain = '<Domain>2022-09-28T12:00:00Z/2022-09-28T20:00:00Z/PT10M</Domain>'   # GIBS still lists 2022 times it no longer keeps

        def no_tiles(url):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        with self.assertRaisesRegex(ValueError, "row 2 .*no longer keeps GOES-East GeoColor.*truecolor_loop"):
            prepare(rows, None, now=NOW, get_text=lambda u: domain, get_bytes=no_tiles)

    def test_geocolor_recent(self):
        rows = parse_sidecar(HEAD + 'b1,,10,sat,satellite_loop,TX,gibs:geocolor_loop@2026-10-12T15:00Z..2026-10-12T19:00Z,,,"{""frames"": 5}"\n')
        domain = '<Domain>2026-10-12T15:00:00Z/2026-10-12T19:00:00Z/PT10M</Domain>'
        snap = prepare(rows, None, now=NOW, get_text=lambda u: domain, get_bytes=lambda u: b"png")
        out = build(rows, snap, {"sat": Window(0, 10)})
        self.assertEqual([f["label"] for f in out.rasters[0]["frames"]],
                         ["SATELLITE · 10:00 AM CDT", "SATELLITE · 11:00 AM CDT", "SATELLITE · 12:00 PM CDT", "SATELLITE · 1:00 PM CDT", "SATELLITE · 2:00 PM CDT"])


class Storms(unittest.TestCase):
    def test_cone_and_coast(self):
        _r, _s, out, _n = run("b1,,10,cone,storm_cone,FL,nhc:cone@AL092022#030,,,\nb1,,10,src,source_line,,,,,\n")
        cone = [f for f in out.fills if f["id"] == "wx_cone_cone"][0]
        self.assertEqual((cone["type"], cone["color"], cone["opacity"]), ("fill", "#FFFFFF", 0.35))
        coast = [f for f in out.fills if f["type"] == "line"]
        self.assertEqual({c["color"] for c in coast}, {"#FF0000", "#FF99FF", "#3366FF"})
        self.assertTrue(all(c["kind"] == "border_trace" and len(c["coords"]) >= 2 for c in coast))
        legend = [e for e in out.events if e["type"] == "alert_legend"][0]
        self.assertEqual(legend["items"][0]["label"], "CONE OF UNCERTAINTY")
        self.assertIn("HURRICANE WARNING", [i["label"] for i in legend["items"]])
        self.assertIn("NHC Advisory 30, Sep 29, 11:00 PM EDT", [e for e in out.events if e["type"] == "source_line"][0]["text"])

    def test_forecast_track_labels_are_reported(self):
        _r, _s, out, _n = run('b1,,10,trk,storm_track,FL,nhc:track@AL092022#030,,,"{""labels"": 2}"\n')
        pts = [e for e in out.events if e["type"] == "storm_points"][0]["points"]
        self.assertEqual([p["label"] for p in pts[:3]], ["CAT 1 · 80 MPH · THU 8 PM", "CAT 1 · 85 MPH · FRI 8 AM", ""])
        self.assertTrue(pts[0]["ring"])
        self.assertEqual([p["at"] for p in pts], sorted(p["at"] for p in pts))
        line = [f for f in out.fills if f["id"] == "wx_trk_track"][0]
        self.assertEqual((line["type"], line["kind"]), ("line", "connector"))
        shown = [ln["shown"] for ln in out.report.lines]
        self.assertEqual(shown, ["CAT 1 · 80 MPH · THU 8 PM", "CAT 1 · 85 MPH · FRI 8 AM"])
        self.assertEqual(out.report.lines[0]["value"], "70 kt")
        self.assertIn("al092022_5day_030.zip", out.report.lines[0]["url"])

    def test_best_track(self):
        _r, _s, out, _n = run('b1,,10,best,storm_track,FL,nhc:track@AL092022#best,,,"{""label_times"": [""2022-09-28T18:00Z""]}"\n')
        segs = [f for f in out.fills if f["type"] == "line"]
        self.assertEqual(len(segs), 14)
        self.assertEqual(sorted(s["t_draw"] for s in segs), [s["t_draw"] for s in sorted(segs, key=lambda s: s["t_draw"])])
        pts = [e for e in out.events if e["type"] == "storm_points"][0]["points"]
        labelled = [p for p in pts if p["label"]]
        self.assertEqual([p["label"] for p in labelled], ["CAT 4 · 155 MPH · SEP 28 2 PM"])
        self.assertEqual(out.report.lines[0]["value"], "135 kt")

    def test_bad_storm_rows(self):
        for ds, msg in [("nhc:cone@AL092022#best", "advisory number as #024"), ("nhc:track@IAN#030", "NHC storm id"),
                        ("nhc:cone@AL092022#30", "advisory number")]:
            typ = ds.split(":")[1].split("@")[0]
            with self.assertRaisesRegex(SidecarError, f"row 2.*{msg}"):
                parse_sidecar(HEAD + f"b1,,10,x,storm_{typ},FL,{ds},,,\n")

    def test_missing_advisory_is_named(self):
        rows = parse_sidecar(HEAD + "b1,,10,cone,storm_cone,FL,nhc:cone@AL092022#099,,,\n")
        with self.assertRaisesRegex(ValueError, r"row 2 \(cone\): NHC advisory 099 of AL092022 could not be fetched.*HTTP 404"):
            prepare(rows, None, now=NOW, get_text=Net().text, get_bytes=Net().bytes)


class Severe(unittest.TestCase):
    def test_spc_outlook_falls_back_through_issuances(self):
        _r, snap, out, net = run("b1,,10,otl,spc_outlook,OK,spc:outlook@2024-05-06#day1,,,\n")
        self.assertEqual(len(out.fills), 6)
        self.assertEqual(out.fills[-1]["color"], "#EE99EE")
        self.assertEqual([e for e in out.events if e["type"] == "alert_legend"][0]["items"][0]["label"], "HIGH RISK")
        self.assertEqual(len([u for u in net.calls if "day1otlk_20240506" in u]), 3)

    def test_latest_outlook_expires(self):
        _r, snap, _o, _n = run("b1,,10,otl,spc_outlook,US,spc:outlook@latest#day1,,,\n")
        exp = [v for k, v in snap.extra.items() if k.startswith("spc_outlook")][0]["expires"]
        with self.assertRaisesRegex(StaleDataError, "SPC outlook .* expired"):
            check_fresh(snap, datetime.fromisoformat(exp))

    def test_reports_in_time_order_and_preliminary(self):
        _r, _s, out, _n = run("b1,,10,rep,storm_reports,OK,spc:reports@2024-05-06,,,\nb1,,10,src,source_line,,,,,\n")
        e = [e for e in out.events if e["type"] == "storm_reports"][0]
        self.assertEqual(len(e["points"]), 382)
        self.assertEqual(e["sub"], "PRELIMINARY")
        self.assertEqual([p["at"] for p in e["points"]], sorted(p["at"] for p in e["points"]))
        self.assertEqual({l["kind"]: l["total"] for l in e["legend"]}, {"tornado": 46, "wind": 257, "hail": 79})
        self.assertEqual([(ln["shown"], "preliminary" in ln["label"]) for ln in out.report.lines], [("46", True), ("257", True), ("79", True)])
        self.assertIn("preliminary", [x for x in out.events if x["type"] == "source_line"][0]["text"])

    def test_reports_one_kind(self):
        _r, _s, out, _n = run("b1,,10,rep,storm_reports,OK,spc:reports@2024-05-06#tornado,,,\n")
        self.assertEqual(len([e for e in out.events if e["type"] == "storm_reports"][0]["points"]), 46)
        with self.assertRaisesRegex(SidecarError, "tornado, wind and hail"):
            parse_sidecar(HEAD + "b1,,10,rep,storm_reports,OK,spc:reports@2024-05-06#snow,,,\n")

    def test_wpc_ero_archive(self):
        _r, _s, out, _n = run("b1,,10,ero,wpc_ero,FL,wpc:ero@2022-09-28#day1,,,\n")
        self.assertEqual(out.fills[-1]["color"], "#FF00FF")
        self.assertEqual([e for e in out.events if e["type"] == "alert_legend"][0]["items"][0]["label"], "HIGH RISK")

    def test_warnings_in_step_with_radar(self):
        win = "2022-09-28T14:00Z..2022-09-28T22:00Z"
        _r, _s, out, _n = run(f'b1,,10,rad,radar,FL,iem:radar@{win}#n0q,,,"{{""frames"": 17}}"\n'

                              f'b1,,10,warn,warnings_archive,FL,"iem:warnings@{win}#TO,EW",,,"{{""states"": [""FL""]}}"\n')
        ws = [f for f in out.fills if f["id"].startswith("wx_warn_") and f["type"] == "fill"]
        edges = [f for f in out.fills if f["id"].startswith("wx_warn_") and f["type"] == "line"]
        self.assertEqual(len(edges), len(ws))   # each warning also outlined on the overlay, above the radar
        self.assertEqual([(e["t_in"], e["color"]) for e in edges], [(w["t_in"], w["color"]) for w in ws])
        self.assertEqual(len(ws), 9)   # 5 tornado + 4 extreme wind warnings live between 14 and 22 UTC (sbw_ian_fl.geojson)
        frames = out.rasters[0]["frames"]
        # the extreme wind warning issued 19:03Z appears just after the 19:00Z radar frame
        ew = [f for f in ws if f["color"] == "#FF8C00"]
        f19 = [f for f in frames if f["label"] == "RADAR · 3:00 PM EDT"][0]
        self.assertTrue(any(abs(w["t_in"] - (10 + f19["at"])) < 0.2 for w in ew))
        self.assertTrue(all(10 <= w["t_in"] < w["t_out"] <= 30 for w in ws))
        legend = [e for e in out.events if e["type"] == "alert_legend"][0]
        self.assertEqual({i["label"] for i in legend["items"]}, {"TORNADO WARNING", "EXTREME WIND WARNING"})
        with self.assertRaisesRegex(SidecarError, "states is a list"):
            parse_sidecar(HEAD + f'b1,,10,warn,warnings_archive,FL,iem:warnings@{win}#TO,,,"{{""states"": ""FL""}}"\n')


class Counter(unittest.TestCase):
    def test_report_counter(self):
        _r, _s, out, _n = run("b1,,10,cnt,counter,OK,spc:reports@2024-05-06#tornado,,,\n")
        e = out.events[0]
        self.assertEqual((e["type"], e["value"], e["label"], e["sub"]), ("counter", 46, "TORNADO REPORTS", "PRELIMINARY · SPC"))
        self.assertEqual(out.report.lines[0]["shown"], "46")

    def test_sub_always_says_preliminary(self):
        _r, _s, out, _n = run('b1,,10,cnt,counter,OK,spc:reports@2024-05-06#hail,,,"{""sub"": ""Storm Prediction Center""}"\n')
        self.assertEqual(out.events[0]["sub"], "STORM PREDICTION CENTER · PRELIMINARY")

    def test_warning_counter_counts_issued_in_window(self):
        _r, _s, out, _n = run('b1,,10,cnt,counter,FL,iem:warnings@2022-09-28T12:00Z..2022-09-29T00:00Z#EW,,,"{""states"": [""FL""]}"\n')
        self.assertEqual((out.events[0]["value"], out.events[0]["label"]), (5, "EXTREME WIND WARNINGS ISSUED"))
        self.assertIn("sbw.geojson", out.report.lines[0]["url"])

    def test_bad_counter_rows(self):
        for ds, msg in [("spc:reports@2024-05-06", "one kind"), ('"iem:warnings@2022-09-28T12:00Z..2022-09-29T00:00Z#TO,EW"', "one type")]:
            with self.assertRaisesRegex(SidecarError, f"row 2.*{msg}"):
                parse_sidecar(HEAD + f"b1,,10,cnt,counter,OK,{ds},,,\n")
        with self.assertRaisesRegex(SidecarError, "anchor"):
            parse_sidecar(HEAD + 'b1,,10,cnt,counter,OK,spc:reports@2024-05-06#hail,,,"{""anchor"": ""middle""}"\n')


class FootageCredit(unittest.TestCase):
    def test_credit_row(self):
        rows = parse_sidecar(HEAD + 'b6,,10,cr,footage_credit,,,,,"{""text"": ""Video: NASA · Sep 28, 2022""}"\n')
        out = build(rows, Snapshot(prepared="x"), {"cr": Window(10, 20)})
        self.assertEqual(out.events[0], {"id": "wx_cr", "type": "footage_credit", "t_in": 10, "t_out": 20, "text": "VIDEO: NASA · SEP 28, 2022"})
        with self.assertRaisesRegex(SidecarError, "footage_credit needs extra"):
            parse_sidecar(HEAD + "b6,,10,cr,footage_credit,,,,,\n")


class EveryProductOnce(unittest.TestCase):
    def test_shared_fetches(self):
        _r, _s, _o, net = run("b1,,10,a,storm_reports,OK,spc:reports@2024-05-06,,,\n"
                              "b1,,10,b,counter,OK,spc:reports@2024-05-06#tornado,,,\n"
                              "b1,,10,c,counter,OK,spc:reports@2024-05-06#wind,,,\n")
        self.assertEqual(len([u for u in net.calls if "rpts" in u]), 1)


if __name__ == "__main__":
    unittest.main()
