"""Weather News parsers on recorded real answers (weather/testdata/news/): the stdlib shapefile/dbf reader, NHC advisory and best
track (Hurricane Ian 2022), SPC outlook and storm reports (2024-05-06), WPC excessive rainfall outlook, IEM warnings archive,
radar scan lists. No network."""

import io
import struct
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from weather.news import iem_warnings, nhc, radar_providers as rp, spc, wpc
from weather.news.shapefile import ShapefileError, read_dbf, read_shp, read_zip, rings_to_multipolygon
from weather.news.timeline import parse_window, place_tz, span, to_layer

DATA = Path(__file__).resolve().parent / "weather" / "testdata" / "news"
UTC = timezone.utc


def fx(name, mode="rb"):
    return (DATA / name).read_bytes() if mode == "rb" else (DATA / name).read_text(encoding="utf-8")


def _shp(shape_type, records):
    """A tiny .shp built by hand: records are bodies (bytes after the record header)."""
    body = b"".join(struct.pack(">ii", i + 1, len(r) // 2) + r for i, r in enumerate(records))
    head = struct.pack(">i", 9994) + b"\0" * 20 + struct.pack(">i", (100 + len(body)) // 2) + struct.pack("<ii", 1000, shape_type) + b"\0" * 64
    return head + body


class Shapefile(unittest.TestCase):
    def test_point_and_polygon_records(self):
        pt = struct.pack("<i2d", 1, -82.2, 26.7)
        ring_cw = [[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]       # clockwise: outer
        hole = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8], [0.2, 0.2]]  # counter-clockwise: hole
        pts = ring_cw + hole
        poly = struct.pack("<i4d2i", 5, 0, 0, 1, 1, 2, len(pts)) + struct.pack("<2i", 0, len(ring_cw)) + b"".join(struct.pack("<2d", *p) for p in pts)
        self.assertEqual(read_shp(_shp(1, [pt])), [("point", [-82.2, 26.7])])
        kind, mp = read_shp(_shp(5, [poly]))[0]
        self.assertEqual(kind, "polygon")
        self.assertEqual(len(mp), 1)          # one polygon ...
        self.assertEqual(len(mp[0]), 2)       # ... with its hole

    def test_two_outer_rings_are_two_polygons(self):
        a = [[0, 0], [0, 1], [1, 1], [0, 0]]
        b = [[5, 5], [5, 6], [6, 6], [5, 5]]
        self.assertEqual(len(rings_to_multipolygon([a, b])), 2)

    def test_not_a_shapefile(self):
        with self.assertRaises(ShapefileError):
            read_shp(b"\0" * 120)
        with self.assertRaises(ShapefileError):
            read_zip(b"not a zip")

    def test_dbf_types(self):
        names, rows = read_dbf(zipfile.ZipFile(io.BytesIO(fx("al092022_5day_030.zip"))).read("al092022-030_5day_pts.dbf"))
        self.assertIn("MAXWIND", names)
        self.assertEqual(rows[0]["MAXWIND"], 70.0)
        self.assertEqual(rows[0]["VALIDTIME"], "30/0000")
        self.assertEqual(rows[0]["TAU"], 0)

    def test_missing_layer_is_named(self):
        with self.assertRaisesRegex(ShapefileError, "no _nothing layer.*5day_pgn"):
            read_zip(fx("al092022_5day_030.zip")).find("_nothing")


class Nhc(unittest.TestCase):
    def test_ian_advisory_30(self):
        d = nhc.advisory(fx("al092022_5day_030.zip"))
        self.assertEqual(d["name"], "Hurricane Ian")
        self.assertEqual(d["adv"], "30")
        self.assertEqual(d["issued"], "2022-09-30T03:00:00+00:00")   # 11 PM EDT Thu Sep 29
        self.assertEqual(len(d["cone"]), 1)
        self.assertGreater(len(d["cone"][0][0]), 100)
        self.assertEqual(len(d["track"]), 5)
        p0 = d["points"][0]
        self.assertEqual((p0["lon"], p0["lat"], p0["wind_kt"], p0["wind_mph"], p0["cat"]), (-79.3, 30.2, 70.0, 80, 1))
        self.assertEqual(p0["time"], "2022-09-30T00:00:00+00:00")
        self.assertEqual(p0["when_label"], "THU 8 PM")
        self.assertEqual(d["points"][2]["kind"], "TS")
        self.assertEqual({c["code"] for c in d["coast"]}, {"HWR", "HWA", "TWR"})

    def test_best_track(self):
        b = nhc.best_track(fx("al092022_best_track_pts_lin.zip"))
        self.assertEqual(len(b["points"]), 36)
        peak = max(b["points"], key=lambda p: p["wind_kt"])
        self.assertEqual((peak["time"], peak["wind_kt"], peak["wind_mph"], peak["cat"]), ("2022-09-28T12:00:00+00:00", 140.0, 160, 5))
        landfall_area = [p for p in b["points"] if p["time"] == "2022-09-28T18:00:00+00:00"][0]
        self.assertEqual((landfall_area["wind_kt"], landfall_area["wind_mph"], landfall_area["cat"]), (135.0, 155, 4))
        self.assertEqual(len(b["segments"]), 14)

    def test_units_and_categories(self):
        self.assertEqual(nhc.mph(135), 155)
        self.assertEqual(nhc.mph(64), 75)
        self.assertIsNone(nhc.mph(9999))
        self.assertEqual([nhc.category(k) for k in (30, 34, 64, 96, 113, 137)], [-1, 0, 1, 3, 4, 5])
        self.assertEqual(nhc.parse_adv_date("1100 AM EDT Wed Sep 28 2022"), datetime(2022, 9, 28, 15, 0, tzinfo=UTC))
        self.assertEqual(nhc.parse_adv_date("500 PM AST Mon Sep 26 2022"), datetime(2022, 9, 26, 21, 0, tzinfo=UTC))
        with self.assertRaisesRegex(ValueError, "NHC's form"):
            nhc.parse_adv_date("yesterday")
        with self.assertRaisesRegex(ValueError, "NHC storm id"):
            nhc.check_storm("IAN2022")

    def test_point_time_crosses_a_month(self):
        self.assertEqual(nhc.point_time("01/1200", datetime(2022, 9, 30, 3, tzinfo=UTC)), datetime(2022, 10, 1, 12, tzinfo=UTC))


class Spc(unittest.TestCase):
    def test_outlook_archive(self):
        o = spc.outlook(fx("spc_day1otlk_20240506_1630_cat.geojson", "t"))
        self.assertEqual([a["label"] for a in o["areas"]], ["TSTM", "MRGL", "SLGT", "ENH", "MDT", "HIGH"])
        self.assertEqual(o["areas"][-1]["fill"], "#EE99EE")
        self.assertEqual((o["issued"], o["expires"]), ("2024-05-06T16:02:00+00:00", "2024-05-07T12:00:00+00:00"))

    def test_outlook_urls(self):
        self.assertEqual(spc.outlook_urls("2024-05-06", "day1_1630"),
                         ["https://www.spc.noaa.gov/products/outlook/archive/2024/day1otlk_20240506_1630_cat.nolyr.geojson"])
        self.assertEqual(len(spc.outlook_urls("2024-05-06", "day1")), 3)
        self.assertEqual(spc.outlook_urls("latest", "day2"), ["https://www.spc.noaa.gov/products/outlook/day2otlk_cat.nolyr.geojson"])
        with self.assertRaisesRegex(ValueError, "day1, day2 or day3"):
            spc.outlook_selector("day4")

    def test_reports_2024_05_06(self):
        r = spc.reports(fx("spc_240506_rpts_filtered.csv", "t"), "2024-05-06")
        self.assertEqual((spc.count(r, "tornado"), spc.count(r, "wind"), spc.count(r, "hail")), (46, 257, 79))
        self.assertEqual(r[0]["time"], "2024-05-06T15:33:00+00:00")
        self.assertEqual(r[-1]["time"], "2024-05-07T11:54:00+00:00")    # after midnight UTC = the next calendar day
        self.assertEqual([x["time"] for x in r], sorted(x["time"] for x in r))
        t0 = [x for x in r if x["kind"] == "tornado"][0]
        self.assertEqual((t0["state"], t0["lat"], t0["lon"]), ("NE", 40.87, -100.71))


class Wpc(unittest.TestCase):
    def test_archive_zip(self):
        e = wpc.from_zip(fx("ero_94e_2022092809.zip"))
        self.assertEqual([a["label"] for a in e["areas"]], ["MARGINAL RISK", "MARGINAL RISK", "SLIGHT RISK", "MODERATE RISK", "HIGH RISK"])
        self.assertEqual(e["areas"][-1]["color"], "#FF00FF")
        self.assertEqual((e["issued"], e["valid"], e["expires"]), ("2022-09-28T11:00:00+00:00", "2022-09-28T12:00:00+00:00", "2022-09-29T12:00:00+00:00"))

    def test_latest_geojson_and_urls(self):
        e = wpc.from_geojson(fx("wpc_ero_day1_latest.geojson", "t"))
        self.assertTrue(e["areas"])
        self.assertEqual(wpc.urls("2022-09-28", "day1_16"), ["https://www.wpc.ncep.noaa.gov/archives/ero/20220928/shp_94e_2022092816.zip"])
        with self.assertRaisesRegex(ValueError, "day1, day2 or day3"):
            wpc.selector("week1")


class IemWarnings(unittest.TestCase):
    def test_ian_florida(self):
        ws = iem_warnings.warnings(fx("sbw_ian_fl.geojson", "t"), ["TO", "EW"])
        ew = [w for w in ws if w["phenomena"] == "EW"]
        self.assertEqual(len(ew), 5)
        self.assertEqual(ew[0]["issued"], "2022-09-28T14:46:00Z")
        self.assertEqual(ew[0]["color"], "#FF8C00")
        self.assertEqual(len([w for w in ws if w["phenomena"] == "TO"]), 7)
        self.assertEqual([w["issued"] for w in ws], sorted(w["issued"] for w in ws))
        tor = [w for w in ws if w["phenomena"] == "TO"][0]
        self.assertEqual(tor["color"], "#FF0000")   # weather/alerts.py ALERT_COLORS

    def test_one_record_per_warning(self):
        ws = iem_warnings.warnings(fx("sbw_ian_fl.geojson", "t"), [])
        self.assertEqual(len({w["key"] for w in ws}), len(ws))

    def test_url(self):
        u = iem_warnings.url(datetime(2022, 9, 28, 12, tzinfo=UTC), datetime(2022, 9, 29, tzinfo=UTC), ["fl"])
        self.assertIn("sts=2022-09-28T12%3A00%3A00Z", u)
        self.assertIn("states=FL", u)


class RadarFrames(unittest.TestCase):
    def test_scan_list_and_pick(self):
        scans = rp.parse_scan_list(fx("iem_radar_list_ian.json", "t"))
        self.assertEqual(scans[0], datetime(2022, 9, 28, 14, tzinfo=UTC))
        self.assertEqual(scans[-1], datetime(2022, 9, 28, 22, tzinfo=UTC))
        fr = rp.pick_frames(scans, 17)
        self.assertEqual(len(fr), 17)
        self.assertEqual((fr[0], fr[-1]), (scans[0], scans[-1]))
        self.assertEqual(fr[1] - fr[0], fr[2] - fr[1])          # evenly spread (30 min)
        self.assertEqual(rp.pick_frames(scans[:5], 18), scans[:5])
        with self.assertRaises(ValueError):
            rp.pick_frames(scans, 1)

    def test_frame_provider_is_xyz_with_time_in_id(self):
        p = rp.frame_provider(rp.get_provider("iem_n0q"), datetime(2022, 9, 28, 19, 5, tzinfo=UTC))
        self.assertEqual(p["urlTemplate"], "https://mesonet.agron.iastate.edu/c/tile.py/1.0.0/ridge::USCOMP-N0Q-202209281905/{z}/{x}/{y}.png")
        self.assertEqual(p["id"], "wx_radar_iem_n0q_202209281905")

    def test_latest(self):
        t = rp.parse_latest(fx("iem_n0q_latest.json", "t"))
        got = rp.fetch_scans(rp.get_provider("iem_n0q"), None, None,
                             lambda u: fx("iem_n0q_latest.json", "t") if "n0q_0" in u else fx("iem_radar_list_latest.json", "t"), t)
        self.assertEqual(got["scans"][-1], t.isoformat())
        self.assertGreaterEqual(len(got["scans"]), 20)

    def test_provider_config(self):
        self.assertEqual(rp.get_provider(None).id, "iem_n0q")
        with self.assertRaisesRegex(ValueError, "unknown radar provider 'acme'.*iem_n0q"):
            rp.get_provider("acme")
        with self.assertRaisesRegex(ValueError, "not map tiles"):
            rp.fetch_scans(rp.get_provider("noaa_mapservices"), None, None, lambda u: "", datetime.now(UTC))
        self.assertEqual(rp.fetch_scans(rp.get_provider("none"), None, None, lambda u: "", datetime.now(UTC))["scans"], [])
        with self.assertRaisesRegex(ValueError, "archived from 2010-11-13"):
            rp.fetch_scans(rp.get_provider("iem_n0q"), datetime(2005, 8, 29, tzinfo=UTC), datetime(2005, 8, 29, 6, tzinfo=UTC), lambda u: "", datetime.now(UTC))


class Timeline(unittest.TestCase):
    def test_window_and_mapping(self):
        a, b = parse_window("2024-05-06T21:00Z..2024-05-07T03:00Z")
        self.assertEqual(b - a, b - a)
        self.assertEqual(to_layer(a, a, b, 10, 30), 10)
        self.assertAlmostEqual(to_layer(b, a, b, 10, 30), 27.0)   # the last 15 % holds the end
        with self.assertRaisesRegex(ValueError, "must end after"):
            parse_window("2024-05-07T03:00Z..2024-05-06T21:00Z")
        with self.assertRaisesRegex(ValueError, "UTC time like"):
            parse_window("2024-05-06..2024-05-07")

    def test_span(self):
        a, b = parse_window("2022-09-28T14:00Z..2022-09-28T22:00Z")
        self.assertEqual(span(a, b, "America/New_York"), "10:00 AM–6:00 PM EDT")
        self.assertEqual(span(a, b, "America/New_York", date=True), "Sep 28, 10:00 AM–6:00 PM EDT")
        a, b = parse_window("2024-05-06T21:00Z..2024-05-07T06:00Z")
        self.assertEqual(span(a, b, "America/Chicago", date=True), "May 6, 4:00 PM–May 7, 1:00 AM CDT")
        a, b = parse_window("2024-11-03T04:00Z..2024-11-03T09:00Z")   # the night daylight time ends
        self.assertEqual(span(a, b, "America/Chicago"), "11:00 PM CDT–3:00 AM CST")

    def test_place_tz(self):
        self.assertEqual(place_tz("FL"), "America/New_York")
        self.assertEqual(place_tz("Oklahoma"), "America/Chicago")
        self.assertEqual(place_tz("Dallas, TX"), "America/Chicago")
        self.assertEqual(place_tz(""), "America/New_York")


if __name__ == "__main__":
    unittest.main()
