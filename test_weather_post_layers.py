"""Post-event layer types end to end without network: weather_layers.csv rows -> fetch (recorded responses) -> snapshot ->
events, fills, rasters and the numbers report. Every number shown is in the report with its URL; errors name their row."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from weather.events import build
from weather.layers import FetchContext
from weather.post import besttrack, mrms
from weather.resolve import Snapshot, prepare
from weather.sidecar import SidecarError, parse_sidecar
from weather.timing import Window

DATA = Path(__file__).resolve().parent / "weather" / "testdata" / "post"
NOW = datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc)
HEAD = "beat,vo_anchor,t,id,type,place,data_source,hold,until,extra\n"


class Net:
    """URL -> recorded file (weather/testdata/post/urls.json, plus the MRMS crops, GIBS and HURDAT2 files)."""

    def __init__(self):
        self.routes = {u: DATA / n for n, u in json.loads((DATA / "urls.json").read_text()).items()}
        for d in ("0826", "0827", "0828", "0829", "0830", "0831", "0901"):
            u = f"{mrms.ARCHIVE}/2017/{d[:2]}/{d[2:]}/GIS/mrms/p24h_2017{d}1200.png"
            self.routes[u] = DATA / f"mrms_crop_2017{d}.png"
            self.routes[mrms.world_url(u)] = DATA / "mrms_crop.wld"
        self.routes[besttrack.INDEX] = DATA / "hurdat_index.txt"
        self.routes[besttrack.INDEX + "hurdat2-1851-2025-092326.txt"] = DATA / "hurdat2_al092017.txt"
        self.calls = []

    def bytes(self, url):
        self.calls.append(url)
        if url not in self.routes:
            raise RuntimeError(f"HTTP 404 {url}")
        return self.routes[url].read_bytes()

    def text(self, url):
        return self.bytes(url).decode("utf-8")


def rows(csv_body):
    return parse_sidecar(HEAD + csv_body)


def run(csv_body, windows=None):
    net = Net()
    rs = rows(csv_body)
    snap = prepare(rs, None, now=NOW, get_text=net.text, get_bytes=net.bytes)
    snap = Snapshot.from_json(snap.to_json())   # what the render reads back
    wins = {r.id: (windows or {}).get(r.id, Window(1.0, 11.0)) for r in rs}
    return build(rs, snap, wins), snap, net


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("VIDEOGEN_WEATHER_CACHE")
        os.environ["VIDEOGEN_WEATHER_CACHE"] = self.tmp.name

    def tearDown(self):
        if self.old is None:
            os.environ.pop("VIDEOGEN_WEATHER_CACHE", None)
        else:
            os.environ["VIDEOGEN_WEATHER_CACHE"] = self.old
        self.tmp.cleanup()

    def assertReported(self, out, shown):
        lines = [ln for ln in out.report.lines if ln["shown"] == shown]
        self.assertTrue(lines, f"{shown!r} is not in the numbers report: {[ln['shown'] for ln in out.report.lines]}")
        for ln in lines:
            self.assertTrue(ln["url"].startswith("https://"), ln)
            self.assertTrue(ln["issued"], ln)


class TotalsTest(Base):
    def test_one_place_is_a_chip_on_the_map(self):
        out, snap, _ = run('b1,,1,iah,rain_total,,"acis:pcpn_total@Houston,TX#2017-08-25..2017-09-01",,,\n')
        (e,) = out.events
        self.assertEqual(e["type"], "post_chip")
        self.assertEqual((e["label"], e["value"], e["sub"]), ("HOUSTON (IAH)", "31.26 IN", "AUG 25–SEP 1 · OBSERVED"))
        self.assertEqual((e["lon"], e["lat"]), (-95.36072, 29.98438))
        self.assertEqual(e["tag"], "")   # 2017 data is past NOAA's quality control: not preliminary
        self.assertReported(out, "31.26 IN")
        self.assertIn("RCC-ACIS", out.shown["iah"][0]["text"])
        self.assertIn("Observed station data: NOAA Regional Climate Centers (RCC-ACIS).", out.credits)

    def test_several_places_are_a_sorted_bar_chart(self):
        out, _, _ = run('b1,,1,bars,rain_total,,"acis:pcpn_total@BPT|HOU|IAH|GLS|SGR|CXO#2017-08-25..2017-09-01",,,"{""decimals"": 1}"\n')
        (e,) = out.events
        self.assertEqual(e["type"], "post_bars")
        self.assertEqual([b["label"] for b in e["bars"]], ["PORT ARTHUR", "HOUSTON HOBBY", "HOUSTON (IAH)", "GALVESTON", "SUGAR LAND", "CONROE"])
        self.assertEqual([b["text"] for b in e["bars"]], ["47.5", "37.0", "31.3", "22.8", "22.7", "21.4"])
        self.assertEqual(e["sub"], "AUG 25–SEP 1, 2017 · OBSERVED")
        for b in e["bars"]:
            self.assertReported(out, f"{b['text']} IN")

    def test_a_missing_day_is_said_on_screen(self):
        out, _, _ = run('b1,,1,bars,rain_total,,"acis:pcpn_total@LBX|IAH#2017-08-25..2017-09-01",,,\n')
        lbx = [b for b in out.events[0]["bars"] if b["label"] == "ANGLETON"][0]
        self.assertEqual((lbx["text"], lbx["note"]), ("18.48", "1 DAY MISSING"))
        self.assertTrue(any("at least" in ln["label"] for ln in out.report.lines))

    def test_recent_data_is_preliminary(self):
        rs = rows('b1,,1,iah,rain_total,,"acis:pcpn_total@Houston,TX#2017-08-25..2017-09-01",,,\n')
        net = Net()
        snap = prepare(rs, None, now=datetime(2017, 9, 5, tzinfo=timezone.utc), get_text=net.text, get_bytes=net.bytes)
        out = build(rs, snap, {"iah": Window(1, 5)})
        self.assertEqual(out.events[0]["tag"], "PRELIMINARY")
        self.assertIn("preliminary", out.shown["iah"][0]["text"])

    def test_record_badge(self):
        out, _, _ = run('b1,,1,rec,record,,"acis:record@Houston,TX#pcpn#2017-08-27",,,\n')
        (e,) = out.events
        self.assertEqual(e["type"], "post_record")
        self.assertEqual((e["headline"], e["place"], e["value"], e["date"]), ("WETTEST DAY ON RECORD", "HOUSTON AREA", "16.07 IN", "AUG 27, 2017"))
        self.assertEqual((e["prev_label"], e["prev_value"], e["prev_date"], e["since"]), ("PREVIOUS RECORD", "10.34 IN", "JUN 26, 1989", "RECORDS SINCE 1888"))
        for shown in ("16.07 IN", "WETTEST DAY ON RECORD", "10.34 IN", "RECORDS SINCE 1888"):
            self.assertReported(out, shown)

    def test_heat_record_tied(self):
        out, _, _ = run('b1,,1,phx,temp_extreme,,"acis:record@Phoenix,AZ#maxt#2023-07-19",,,\n')
        e = out.events[0]
        self.assertEqual((e["headline"], e["value"], e["prev_label"], e["prev_value"], e["kind"]),
                         ("TIED: 4TH HOTTEST DAY ON RECORD", "119°F", "RECORD", "122°F", "heat"))

    def test_rows_are_checked(self):
        bad = [
            ('b1,,1,x,rain_total,,"acis:pcpn_total@Nowhere,TX#2017-08-25..2017-09-01",,,', "no ACIS station"),
            ('b1,,1,x,rain_total,,"acis:pcpn_total@IAH#2017-08-25",,,', "date range"),
            ('b1,,1,x,rain_total,,"acis:pcpn_total@IAH|HOU#2017-08-25..2017-08-26",,,"{""labels"": [""A 1"", ""B""]}"', "words only"),
            ('b1,,1,x,record,,"acis:record@Houston,TX#rain#2017-08-27",,,', "element must be one of"),
            ('b1,,1,x,temp_extreme,,"acis:record@Houston,TX#pcpn#2017-08-27",,,', "element must be one of maxt, mint"),
            ('b1,,1,x,record,,"acis:pcpn_total@Houston,TX#2017-08-25..2017-08-26",,,', "record takes acis:record"),
        ]
        for line, msg in bad:
            with self.assertRaises(SidecarError) as cm:
                rows(line + "\n")
            self.assertIn("row 2", str(cm.exception))
            self.assertIn(msg, str(cm.exception), line)


class RiversTest(Base):
    def test_crest_marker_and_hydrograph(self):
        out, snap, _ = run('b1,,1,bb,river_crest,,usgs:crest@08074000#2017-08-25..2017-09-05,,,"{""chart"": true}"\n')
        chip, chart = out.events
        self.assertEqual((chip["label"], chip["value"], chip["sub"], chip["tag"]), ("BUFFALO BAYOU", "41.9 FT", "CREST AUG 28 · MAJOR FLOOD", "RECORD CREST"))
        self.assertReported(out, "41.9 FT")
        self.assertReported(out, "MAJOR FLOOD")
        self.assertReported(out, "RECORD CREST")
        crest_line = [ln for ln in out.report.lines if ln["shown"] == "41.9 FT"][0]
        self.assertIn("time is uncertain", crest_line["label"])
        self.assertEqual(chart["type"], "post_hydrograph")
        self.assertEqual(len(chart["values"]), 12 * 24)
        self.assertEqual(chart["values"][chart["crest"]["index"]], 41.9)
        self.assertEqual([ln["label"] for ln in chart["lines"]], ["MAJOR FLOOD 32.0 FT", "MODERATE FLOOD 29.5 FT", "MINOR FLOOD 28.0 FT"])
        for ln in chart["lines"]:
            self.assertReported(out, ln["label"])

    def test_without_nws_categories_the_crest_stands_alone(self):
        net = Net()
        del net.routes["https://api.water.noaa.gov/nwps/v1/gauges/08074000"]
        rs = rows('b1,,1,bb,river_crest,,usgs:crest@08074000#2017-08-25..2017-09-05,,,\n')
        snap = prepare(rs, None, now=NOW, get_text=net.text, get_bytes=net.bytes)
        out = build(rs, snap, {"bb": Window(1, 5)})
        self.assertEqual((out.events[0]["sub"], out.events[0]["tag"]), ("CREST AUG 28", ""))
        self.assertTrue(any("no NWS flood categories" in n for n in snap.notes))

    def test_provisional_crest_is_labelled(self):
        net = Net()
        url = "https://nwis.waterservices.usgs.gov/nwis/iv/?format=json&sites=08057000&parameterCd=00065&startDT=2026-10-11&endDT=2026-10-12&siteStatus=all"
        net.routes[url] = DATA / "usgs_iv_08057000_recent.json"
        rs = rows('b1,,1,tr,river_crest,,usgs:crest@08057000#2026-10-11..2026-10-12,,,\n')
        snap = prepare(rs, None, now=NOW, get_text=net.text, get_bytes=net.bytes)
        out = build(rs, snap, {"tr": Window(1, 5)})
        self.assertEqual(out.events[0]["tag"], "PROVISIONAL")
        self.assertIn("provisional", out.shown["tr"][0]["text"])
        self.assertIn("provisional", out.report.lines[0]["product"])

    def test_bad_site(self):
        with self.assertRaisesRegex(SidecarError, "row 2.*USGS site number"):
            rows("b1,,1,x,river_crest,,usgs:crest@BBST2#2017-08-25..2017-09-05,,,\n")


class RainMapTest(Base):
    ROW = 'b1,,1,rm,rain_map,,mrms:total@2017-08-25..2017-09-01,,,"{""bbox"": [-95.6, 29.6, -95.0, 30.1], ""peak"": true}"\n'

    def test_rain_map_is_a_value_overlay_with_a_legend(self):
        out, snap, net = run(self.ROW)
        (fill,) = out.fills
        self.assertEqual(fill["type"], "value_overlay")
        self.assertTrue(fill["data"].startswith("file:"))
        path = Path(fill["data"][5:])
        self.assertTrue(path.is_file())
        self.assertTrue(str(path).startswith(self.tmp.name))
        self.assertEqual(fill["ramp"][0], [1, "#A7D8F0"])
        (legend,) = out.events
        self.assertEqual(legend["type"], "post_rainlegend")
        self.assertEqual(legend["sub"], "AUG 25 7 AM CDT – SEP 1 7 AM CDT")
        self.assertTrue(legend["peak"].startswith("PEAK ESTIMATE"))
        self.assertReported(out, legend["peak"])
        self.assertReported(out, "1 2 4 6 8 10 15 20 25 30 40")
        self.assertEqual(sum(1 for u in net.calls if u.endswith(".png")), 7)
        self.assertIn("MRMS", out.shown["rm"][0]["text"])

    def test_a_box_mostly_without_rain_is_refused(self):
        with self.assertRaisesRegex(ValueError, r"row 2 \(rm\).*smaller bbox"):
            run(self.ROW.replace('""peak"": true', '""min_in"": 80'))

    def test_bbox_checks(self):
        for extra, msg in (('"{}"', "needs extra bbox"), ('"{""bbox"": [-60, 29, -95, 30]}"', "must lie inside"),
                           ('"{""bbox"": [-110, 25, -90, 40]}"', "larger than 12 x 10")):
            with self.assertRaisesRegex(SidecarError, msg):
                rows(f"b1,,1,rm,rain_map,,mrms:total@2017-08-25..2017-09-01,,,{extra}\n")
        with self.assertRaisesRegex(SidecarError, "starts in 2015"):
            rows('b1,,1,rm,rain_map,,mrms:total@2014-08-25..2014-09-01,,,"{""bbox"": [-95.6, 29.6, -95.0, 30.1]}"\n')


class BeforeAfterTest(Base):
    def test_two_frames_crossfade_with_labels(self):
        out, snap, _ = run("b1,,1,ba,before_after,,gibs:falsecolor@2017-08-22|2017-08-31,,,\n", {"ba": Window(10.0, 20.0)})
        (r,) = out.rasters
        self.assertEqual([f["provider"]["id"] for f in r["frames"]], ["wx_gibs_falsecolor_20170822", "wx_gibs_falsecolor_20170831"])
        self.assertEqual([f["at"] for f in r["frames"]], [0.0, 5.0])
        self.assertEqual((r["crossfade_s"], r["above_fills"], r["clock"]), (1.5, False, False))
        (lab,) = out.events
        self.assertEqual([(f["label"], f["date"]) for f in lab["frames"]], [("BEFORE", "AUG 22, 2017"), ("AFTER", "AUG 31, 2017")])
        self.assertReported(out, "AUG 22, 2017")
        self.assertReported(out, "AUG 31, 2017")

    def test_a_wipe_is_asked_of_the_page_and_a_crossfade_is_not(self):
        out, _snap, _ = run('b1,,1,ba,before_after,,gibs:falsecolor@2017-08-22|2017-08-31,,,"{""transition"": ""wipe""}"\n', {"ba": Window(10.0, 22.0)})
        (r,) = out.rasters
        self.assertEqual((r.get("wipe"), r["crossfade_s"]), (True, 3.0))
        out, _snap, _ = run("b1,,1,ba,before_after,,gibs:falsecolor@2017-08-22|2017-08-31,,,\n", {"ba": Window(10.0, 22.0)})
        self.assertNotIn("wipe", out.rasters[0])

    def test_a_day_gibs_does_not_have(self):
        net = Net()
        net.routes = {u: (DATA / "gibs_domain_falsecolor_20170831.xml" if "2017-08-31" in u else p) for u, p in net.routes.items()}
        empty = Path(self.tmp.name) / "empty.xml"
        empty.write_text("<Domains><Size>0</Size></Domains>")
        net.routes[[u for u, p in net.routes.items() if "2017-08-22--" in u][0]] = empty
        rs = rows("b1,,1,ba,before_after,,gibs:falsecolor@2017-08-22|2017-08-31,,,\n")
        with self.assertRaisesRegex(ValueError, "row 2 \\(ba\\).*no MODIS Terra bands 7-2-1 picture for 2017-08-22"):
            prepare(rs, None, now=NOW, get_text=net.text, get_bytes=net.bytes)

    def test_checks(self):
        for ds, msg in (("gibs:falsecolor@2017-08-31|2017-08-22", "must be later"), ("gibs:falsecolor@2017-08-22", "two dates"),
                        ("gibs:geocolor@2017-08-22|2017-08-31", "before_after takes")):
            with self.assertRaisesRegex(SidecarError, msg):
                rows(f"b1,,1,ba,before_after,,{ds},,,\n")


class TimelineTest(Base):
    MARKS = ('"{""marks"": [{""from"": ""usgs:crest@08074000#2017-08-25..2017-09-05""}, {""from"": ""nhc:landfall@AL092017#1""}, '
             '{""from"": ""acis:peak_day@Houston,TX#2017-08-25..2017-09-01""}, {""from"": ""acis:record@Houston,TX#pcpn#2017-08-27"", ""title"": ""HOUSTON RECORD""}]}"')

    def test_marks_come_from_the_data_in_order(self):
        out, _, _ = run(f"b1,,1,tl,event_timeline,,post:timeline@2017-08-24..2017-09-02,,,{self.MARKS}\n")
        (e,) = out.events
        self.assertEqual(e["type"], "post_timeline")
        self.assertEqual(len(e["ticks"]), 10)
        self.assertEqual(e["ticks"][0]["label"], "AUG 24")
        got = [(m["when"], m["title"], m["detail"]) for m in e["marks"]]
        self.assertEqual(got[0], ("AUG 25 · 10 PM", "LANDFALL", "CATEGORY 4 HURRICANE · 130 MPH"))   # 03 UTC Aug 26 = 10 PM CDT Aug 25
        self.assertEqual(got[1][:2], ("AUG 27", "WETTEST DAY"))
        self.assertEqual(got[1][2], "16.07 IN · HOUSTON (IAH)")
        self.assertEqual(got[2][:2], ("AUG 27", "HOUSTON RECORD"))
        self.assertEqual(got[3], ("AUG 28", "RIVER CREST", "BUFFALO BAYOU 41.9 FT"))   # crest beside a gap: the day only
        fs = [m["f"] for m in e["marks"]]
        self.assertEqual(fs, sorted(fs))
        self.assertAlmostEqual(fs[0], (1 + 22 / 24) / 10)
        for m in e["marks"]:
            self.assertReported(out, m["detail"] if m["title"] != "HOUSTON RECORD" else f"WETTEST DAY ON RECORD · {m['detail']}")
        self.assertEqual(out.shown["tl"][0]["text"], "Timeline: NHC best track, NOAA RCC-ACIS, USGS")

    def test_landfall_number_counts_inside_the_timeline(self):
        marks = '"{""marks"": [{""from"": ""nhc:landfall@AL092017#3""}]}"'
        out, _, _ = run(f"b1,,1,tl,event_timeline,,post:timeline@2017-08-24..2017-09-02,,,{marks}\n")
        self.assertEqual(out.events[0]["marks"][0]["when"], "AUG 30 · 3 AM")   # Louisiana, 08 UTC Aug 30
        with self.assertRaisesRegex(ValueError, r"row 2 \(tl\).*3 landfall\(s\).*not 4"):
            run(f"b1,,1,tl,event_timeline,,post:timeline@2017-08-24..2017-09-02,,,{marks.replace('#3', '#4')}\n")

    def test_marks_are_checked(self):
        for extra, msg in (('"{}"', "needs extra marks"), ('"{""marks"": [{""from"": ""nws:alerts@TX""}]}"', "a timeline mark comes from"),
                           ('"{""marks"": [{""from"": ""nhc:landfall@AL092017"", ""title"": ""LANDFALL AT 130 MPH""}]}"', "words only"),
                           ('"{""marks"": [{""from"": ""nhc:landfall@AL092017"", ""when"": ""x""}]}"', "takes from and title")):
            with self.assertRaisesRegex(SidecarError, msg):
                rows(f"b1,,1,tl,event_timeline,,post:timeline@2017-08-24..2017-09-02,,,{extra}\n")

    def test_a_mark_outside_the_axis(self):
        marks = '"{""marks"": [{""from"": ""usgs:crest@08074000#2017-08-25..2017-09-05""}]}"'
        with self.assertRaisesRegex(ValueError, "outside the timeline"):
            run(f"b1,,1,tl,event_timeline,,post:timeline@2017-08-24..2017-08-26,,,{marks}\n")


class SnapshotTest(Base):
    def test_each_product_is_fetched_once_and_needs_no_nws_contact(self):
        body = ('b1,,1,a,rain_total,,"acis:pcpn_total@Houston,TX#2017-08-25..2017-09-01",,,\n'
                'b1,,1,b,event_timeline,,post:timeline@2017-08-24..2017-09-02,,,"{""marks"": [{""from"": ""acis:peak_day@Houston,TX#2017-08-25..2017-09-01""}]}"\n'
                'b1,,1,c,river_crest,,usgs:crest@08074000#2017-08-25..2017-09-05,,,\n'
                'b1,,1,d,event_timeline,,post:timeline@2017-08-24..2017-09-02,,,"{""marks"": [{""from"": ""usgs:crest@08074000#2017-08-25..2017-09-05""}]}"\n')
        out, snap, net = run(body)
        self.assertEqual(len(net.calls), len(set(net.calls)))
        self.assertTrue(all(k.startswith("post:") for k in snap.extra))
        self.assertEqual(snap.forecasts, {})


if __name__ == "__main__":
    unittest.main()
