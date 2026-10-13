"""Post-event data (no network): RCC-ACIS values (M, T, S, accumulations), totals and record ranking; USGS gage height with
provisional flags, crests and gaps; NWS flood categories and historic crests; the MRMS PNG decoder and day sums; GIBS
providers; the NHC best-track landfalls; date and number formatting. All from recorded real responses in weather/testdata/post/."""

import json
import struct
import unittest
import zlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from weather.post import acis, besttrack, fmt, gibs, mrms, usgs

DATA = Path(__file__).resolve().parent / "weather" / "testdata" / "post"


def text(name):
    return (DATA / name).read_text(encoding="utf-8")


def png8(rows, filters=None):
    """A one-channel 8-bit PNG with the given row filters (0 none, 1 sub, 2 up, 3 average, 4 paeth) applied for real."""
    h, w = rows.shape
    out, prev = b"", np.zeros(w, dtype=np.int32)
    for r in range(h):
        f = (filters or [0])[r % len(filters or [0])]
        cur = rows[r].astype(np.int32)
        left = np.concatenate([[0], cur[:-1]])
        upleft = np.concatenate([[0], prev[:-1]])
        if f == 0:
            enc = cur
        elif f == 1:
            enc = cur - left
        elif f == 2:
            enc = cur - prev
        elif f == 3:
            enc = cur - (left + prev) // 2
        else:
            p = left + prev - upleft
            pa, pb, pc = np.abs(p - left), np.abs(p - prev), np.abs(p - upleft)
            pred = np.where((pa <= pb) & (pa <= pc), left, np.where(pb <= pc, prev, upleft))
            enc = cur - pred
        out += bytes([f]) + (enc & 255).astype(np.uint8).tobytes()
        prev = cur

    def chunk(k, b):
        return struct.pack(">I", len(b)) + k + b + struct.pack(">I", zlib.crc32(k + b) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 3, 0, 0, 0)) + chunk(b"PLTE", bytes(768))
            + chunk(b"IDAT", zlib.compress(out)) + chunk(b"IEND", b""))


class FormatTest(unittest.TestCase):
    def test_spans_and_dates(self):
        self.assertEqual(fmt.span(date(2017, 8, 25), date(2017, 8, 30)), "AUG 25–30")
        self.assertEqual(fmt.span(date(2017, 8, 25), date(2017, 9, 1), year=True), "AUG 25–SEP 1, 2017")
        self.assertEqual(fmt.short(date(2017, 8, 27), year=True), "AUG 27, 2017")
        self.assertEqual([fmt.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22)], ["1ST", "2ND", "3RD", "4TH", "11TH", "12TH", "13TH", "21ST", "22ND"])
        self.assertEqual(fmt.amount(41.9), "41.9")
        self.assertEqual(fmt.amount(12.07), "12.07")

    def test_bad_ranges_and_author_numbers_are_refused(self):
        with self.assertRaisesRegex(ValueError, "backwards"):
            fmt.date_range("2017-08-30..2017-08-25")
        with self.assertRaisesRegex(ValueError, "60 days"):
            fmt.date_range("2017-01-01..2017-06-01")
        with self.assertRaisesRegex(ValueError, "date range"):
            fmt.date_range("2017-08-25")
        with self.assertRaisesRegex(ValueError, "numbers on screen come from the data"):
            fmt.no_digits("50 INCHES", "the label")


class AcisTest(unittest.TestCase):
    def test_values_missing_trace_accumulated(self):
        self.assertIsNone(acis.parse_value("M").amount)
        t = acis.parse_value("T")
        self.assertEqual((t.amount, t.trace), (0.0, True))
        a = acis.parse_value("1.20A")
        self.assertEqual((a.amount, a.accumulated), (1.2, True))
        self.assertTrue(acis.parse_value("S").accumulated)
        with self.assertRaises(ValueError):
            acis.parse_value("x1")

    def test_total_counts_trace_as_zero_and_lists_missing_days(self):
        tot = acis.total([("2017-08-25", "0.39"), ("2017-08-26", "8.37"), ("2017-08-27", "T"), ("2017-08-28", "M")])
        self.assertEqual(tot.amount, 8.76)
        self.assertEqual(tot.missing, ["2017-08-28"])
        self.assertEqual(tot.trace_days, 1)
        self.assertFalse(tot.complete)

    def test_harvey_station_totals_from_multistndata(self):
        sids = ["BPT", "HOU", "IAH", "GLS", "SGR", "CXO"]
        st = acis.parse_multi(text("acis_multi_harvey.json"), sids, date(2017, 8, 25), date(2017, 9, 1))
        self.assertEqual([s["sid"] for s in st], sids)
        totals = {s["sid"]: acis.total([tuple(v) for v in s["values"]]).amount for s in st}
        self.assertEqual(totals["IAH"], 31.26)   # 0.39 + 8.37 + 16.07 + 4.00 + 2.43 + T + 0 + 0
        self.assertEqual(totals["HOU"], 37.01)
        self.assertEqual(totals["BPT"], 47.48)
        iah = st[2]
        self.assertEqual(iah["values"][2], ["2017-08-27", "16.07"])
        self.assertEqual(acis.peak_day([tuple(v) for v in iah["values"]]), ("2017-08-27", 16.07))
        self.assertEqual(iah["ll"], [-95.36072, 29.98438])

    def test_a_missing_day_in_a_real_answer(self):
        st = acis.parse_multi(text("acis_multi_lbx.json"), ["LBX", "IAH"], date(2017, 8, 25), date(2017, 9, 1))
        tot = acis.total([tuple(v) for v in st[0]["values"]])
        self.assertEqual(tot.missing, ["2017-09-01"])
        self.assertEqual(tot.amount, 18.48)

    def test_unknown_station_or_wrong_length_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "no data for XYZ"):
            acis.parse_multi(text("acis_multi_iah.json"), ["IAH", "XYZ"], date(2017, 8, 25), date(2017, 9, 1))
        with self.assertRaisesRegex(ValueError, "expected"):
            acis.parse_multi(text("acis_multi_iah.json"), ["IAH"], date(2017, 8, 25), date(2017, 9, 3))

    def test_places_and_labels(self):
        self.assertEqual(acis.station_for("Houston, TX"), "IAH")
        self.assertEqual(acis.station_for("houston,tx", record=True), "IAHthr 9")
        self.assertEqual(acis.station_for("HOU"), "HOU")
        with self.assertRaisesRegex(ValueError, "no ACIS station is known"):
            acis.station_for("Nowhere, TX")
        with self.assertRaisesRegex(ValueError, "neither"):
            acis.station_for("H#U")
        self.assertEqual(acis.base_sid("IAHthr 9"), "IAH")
        self.assertEqual(acis.label_for("IAH", "HOUSTON INTERCONTINENTAL AP"), "HOUSTON (IAH)")
        self.assertEqual(acis.label_for("IAHthr 9", "Houston Area"), "HOUSTON AREA")
        self.assertEqual(acis.label_for("XYZ", "SOMEWHERE MUNICIPAL AP"), "SOMEWHERE")

    def test_wettest_day_on_record(self):
        top, meta = acis.parse_rank(text("acis_rank_iahthr_pcpn_20170827.json"))
        v = acis.parse_day(text("acis_day_iahthr_pcpn_20170827.json"))
        r = acis.rank_day("pcpn", "2017-08-27", v.amount, top, station=meta["name"], por_start=meta["por_start"])
        self.assertEqual((r.rank, r.tied), (1, False))
        self.assertEqual(r.record, (10.34, "1989-06-26"))   # the old record it beat
        self.assertEqual(meta["por_start"], "1888-07-01")
        self.assertEqual(acis.headline(r), "WETTEST DAY ON RECORD")

    def test_a_day_that_is_not_number_one(self):
        top, meta = acis.parse_rank(text("acis_rank_iahthr_pcpn_20170826.json"))
        v = acis.parse_day(text("acis_day_iahthr_pcpn_20170826.json"))
        r = acis.rank_day("pcpn", "2017-08-26", v.amount, top, station=meta["name"], por_start=meta["por_start"])
        self.assertEqual(v.amount, 8.37)
        self.assertGreater(r.rank, 1)
        self.assertTrue(acis.headline(r).startswith(f"{fmt.ordinal(r.rank)} WETTEST DAY"))
        self.assertEqual(r.record[0], 10.34)

    def test_calendar_date_record_and_tied_heat(self):
        top, meta = acis.parse_rank(text("acis_rank_iahthr_pcpndate_20170827.json"))
        r = acis.rank_day("pcpn", "2017-08-27", 16.07, top, station=meta["name"], por_start=meta["por_start"])
        self.assertEqual(acis.headline(r, "date"), "WETTEST AUG 27 ON RECORD")
        self.assertEqual(r.record, (8.32, "1945-08-27"))
        top, meta = acis.parse_rank(text("acis_rank_phxthr_maxt_20230719.json"))
        v = acis.parse_day(text("acis_day_phxthr_maxt_20230719.json"))
        r = acis.rank_day("maxt", "2023-07-19", v.amount, top, station=meta["name"], por_start=meta["por_start"])
        self.assertEqual((v.amount, r.rank, r.tied), (119.0, 4, True))
        self.assertEqual(acis.headline(r), "TIED: 4TH HOTTEST DAY ON RECORD")
        self.assertEqual(acis.amount_text("maxt", 119.0), "119°F")

    def test_a_day_below_the_top_list_is_not_a_record(self):
        top = [(10.0 - k, f"2000-01-{k + 1:02d}") for k in range(10)]
        r = acis.rank_day("pcpn", "2017-08-01", 0.5, top, station="X", por_start="1900-01-01")
        self.assertIsNone(r.rank)
        with self.assertRaisesRegex(ValueError, "leave this record out"):
            acis.headline(r)

    def test_coldest_ranks_lowest_first(self):
        r = acis.rank_day("mint", "2021-02-16", -2.0, [(-2.0, "2021-02-16"), (5.0, "1930-01-01"), (7.0, "1949-01-31")], station="X", por_start="1900")
        self.assertEqual(r.rank, 1)
        self.assertEqual(acis.headline(r), "COLDEST MORNING ON RECORD")


class UsgsTest(unittest.TestCase):
    def test_buffalo_bayou_crest_with_a_gap(self):
        s = usgs.parse_iv(text("usgs_iv_08074000_harvey.json"), "08074000")
        self.assertEqual(s.name, "Buffalo Bayou at Houston, TX")
        self.assertAlmostEqual(s.lon, -95.4085505)
        c = usgs.crest(s)
        self.assertEqual(c.value, 41.90)
        self.assertEqual(c.when, datetime(2017, 8, 28, 1, 0, tzinfo=timezone(timedelta(hours=-5))))
        self.assertFalse(c.provisional)
        self.assertIn("A", c.qualifiers)
        self.assertTrue(c.gap_near)   # the gauge record has hours missing around the crest
        self.assertEqual(usgs.short_name(s.name), "BUFFALO BAYOU")

    def test_provisional_values_are_flagged(self):
        s = usgs.parse_iv(text("usgs_iv_08057000_recent.json"), "08057000")
        self.assertTrue(usgs.any_provisional(s))
        self.assertTrue(usgs.crest(s).provisional)

    def test_nodata_and_missing_parameter(self):
        doc = {"value": {"timeSeries": [{"sourceInfo": {"siteName": "X", "geoLocation": {"geogLocation": {"longitude": -95, "latitude": 30}}},
                                          "variable": {"variableCode": [{"value": "00065"}], "unit": {"unitCode": "ft"}, "noDataValue": -999999.0},
                                          "values": [{"value": [{"value": "-999999", "qualifiers": ["P", "Eqp"], "dateTime": "2024-01-01T00:00:00.000-06:00"},
                                                                {"value": "3.10", "qualifiers": ["P"], "dateTime": "2024-01-01T00:15:00.000-06:00"}]}]}]}}
        s = usgs.parse_iv(json.dumps(doc), "01234567")
        self.assertEqual([p[1] for p in s.points], [3.10])
        with self.assertRaisesRegex(ValueError, "no gage height"):
            usgs.parse_iv(json.dumps({"value": {"timeSeries": []}}), "01234567")
        with self.assertRaisesRegex(ValueError, "USGS site number"):
            usgs.site_ok("BBST2")

    def test_flood_categories_and_record_crest(self):
        nw = usgs.parse_nwps(text("nwps_08074000.json"))
        self.assertEqual(nw["lid"], "BBST2")
        self.assertEqual(nw["categories"], {"major": 32.0, "moderate": 29.5, "minor": 28.0, "action": 17.0})
        self.assertEqual(usgs.category(41.9, nw["categories"]), "major")
        self.assertEqual(usgs.category(18.0, nw["categories"]), "action")
        self.assertIsNone(usgs.category(5.0, nw["categories"]))
        when = datetime(2017, 8, 28, 6, 0, tzinfo=timezone.utc)
        st = usgs.record_standing(41.9, when, nw["crests"])
        self.assertTrue(st["record"])
        self.assertEqual(st["previous"]["stage"], 36.58)   # the 2017 crest itself is left out
        self.assertFalse(usgs.record_standing(30.0, when, nw["crests"])["record"])

    def test_hourly_series_keeps_gaps(self):
        s = usgs.parse_iv(text("usgs_iv_08074000_harvey.json"), "08074000")
        tz = timezone(timedelta(hours=-5))
        h = usgs.hourly(s, datetime(2017, 8, 25, tzinfo=tz), datetime(2017, 9, 5, 23, 59, tzinfo=tz))
        self.assertEqual(len(h), 12 * 24)
        self.assertEqual(max(v for v in h if v is not None), 41.9)
        self.assertIn(None, h[60:80])   # Aug 27-28: the gauge record is broken


class MrmsTest(unittest.TestCase):
    def test_png_filters_decode_exactly(self):
        rng = np.random.default_rng(3)
        rows = rng.integers(0, 256, size=(9, 23), dtype=np.uint8)
        for filters in ([0], [1], [2], [3], [4], [0, 1, 2, 3, 4]):
            out, w, h = mrms.decode_png_rows(png8(rows, filters), 2, 7)
            self.assertEqual((w, h), (23, 9))
            np.testing.assert_array_equal(out, rows[2:7], err_msg=f"filters {filters}")

    def test_index_encoding_from_iem(self):
        mm = mrms.index_to_mm(np.array([0, 1, 99, 100, 179, 180, 253, 254, 255], dtype=np.uint8))
        np.testing.assert_allclose(mm[:8], [0, 0.375, 24.875, 25.625, 124.375, 127.5, 492.5, 495.0])
        self.assertTrue(np.isnan(mm[8]))

    def test_urls_and_days(self):
        self.assertEqual(mrms.png_url(date(2017, 9, 1)), "https://mesonet.agron.iastate.edu/archive/data/2017/09/01/GIS/mrms/p24h_201709011200.png")
        self.assertEqual(mrms.day_endings(date(2017, 8, 25), date(2017, 8, 28)), [date(2017, 8, 26), date(2017, 8, 27), date(2017, 8, 28)])
        with self.assertRaisesRegex(ValueError, "LATER day"):
            mrms.day_endings(date(2017, 8, 25), date(2017, 8, 25))
        self.assertEqual(mrms.parse_world(text("mrms_p24h_201709011200.wld")), (0.01, -0.01, -130.0, 55.0))

    def test_houston_week_from_recorded_grids(self):
        world = mrms.parse_world(text("mrms_crop.wld"))
        pngs = [(DATA / f"mrms_crop_2017{d}.png").read_bytes() for d in ("0826", "0827", "0828", "0829", "0830", "0831", "0901")]
        g = mrms.sum_days(pngs, world, [-95.6, 29.6, -95.0, 30.1])
        self.assertAlmostEqual(g.west, -95.605, places=6)
        self.assertAlmostEqual(g.cell, 0.01)
        # IAH (29.98N 95.36W): MRMS's 7-day estimate is near the gauge's 31.26 in (radar estimate, 12 UTC days)
        self.assertTrue(25 < g.at(-95.36, 29.984) < 45, g.at(-95.36, 29.984))
        v, lon, lat, at_least = g.peak()
        self.assertGreater(v, 40)
        back = mrms.RainGrid.from_dict(g.to_dict())
        np.testing.assert_allclose(back.inches, np.round(g.inches, 2), atol=0.006)
        self.assertEqual(back.capped, g.capped)
        self.assertEqual(back.peak()[3], at_least)

    def test_missing_day_leaves_the_cell_empty_and_cap_is_counted(self):
        a = png8(np.array([[4, 255], [254, 0]], dtype=np.uint8))
        b = png8(np.array([[4, 8], [254, 0]], dtype=np.uint8))
        g = mrms.sum_days([a, b], (0.01, -0.01, -100.0, 40.0), [-100.005, 39.985, -99.985, 40.005])
        self.assertTrue(np.isnan(g.inches[0, 1]))
        self.assertAlmostEqual(g.inches[1, 0], 990 / 25.4)
        self.assertEqual(g.capped, 1)

    def test_asc_file_for_pakmap(self):
        import tempfile

        g = mrms.RainGrid(-100.0, 39.98, -99.98, 40.0, 0.01, np.array([[0.4, 2.5], [np.nan, 10.0]]), 0)
        with tempfile.TemporaryDirectory() as d:
            p = mrms.write_asc(g, 1.0, Path(d))
            lines = p.read_text().splitlines()
            self.assertEqual(lines[:6], ["ncols 2", "nrows 2", "xllcorner -100.000000", "yllcorner 39.980000", "cellsize 0.010000", "nodata_value -9999"])
            self.assertEqual(lines[6:], ["-9999 2.50", "-9999 10.00"])
            self.assertEqual(mrms.write_asc(g, 1.0, Path(d)), p)   # same grid, same file


class GibsAndTrackTest(unittest.TestCase):
    def test_gibs_provider_and_domain(self):
        p = gibs.provider("falsecolor", date(2017, 8, 31))
        self.assertEqual(p["id"], "wx_gibs_falsecolor_20170831")
        self.assertIn("/MODIS_Terra_CorrectedReflectance_Bands721/default/2017-08-31/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg", p["urlTemplate"])
        self.assertEqual(p["format"], "jpg")
        self.assertTrue(gibs.has_day(text("gibs_domain_falsecolor_20170831.xml")))
        self.assertFalse(gibs.has_day("<Domains><Size>0</Size></Domains>"))
        with self.assertRaisesRegex(ValueError, "unknown GIBS picture"):
            gibs.layer("geocolor")

    def test_harvey_landfalls(self):
        name, fixes = besttrack.parse_block(besttrack.storm_block(text("hurdat2_al092017.txt"), "AL092017"))
        self.assertEqual(name, "HARVEY")
        lands = besttrack.landfalls(fixes)
        texas = [f for f in lands if f.time.date() >= date(2017, 8, 25)]
        self.assertEqual(texas[0].time, datetime(2017, 8, 26, 3, 0, tzinfo=timezone.utc))
        self.assertEqual((texas[0].lat, texas[0].lon, texas[0].wind_kt), (28.0, -96.9, 115))
        self.assertEqual(besttrack.category(115, "HU"), "CATEGORY 4 HURRICANE")
        self.assertEqual(besttrack.mph(115), 130)
        self.assertEqual(besttrack.category(40, "TS"), "TROPICAL STORM")
        with self.assertRaisesRegex(ValueError, "not in the NHC best track"):
            besttrack.storm_block(text("hurdat2_al092017.txt"), "AL112017")
        with self.assertRaisesRegex(ValueError, "storm id"):
            besttrack.check_id("Harvey")

    def test_latest_hurdat_file(self):
        names = text("hurdat_index.txt")
        self.assertEqual(besttrack.latest_file(names), besttrack.INDEX + "hurdat2-1851-2025-092326.txt")
        self.assertTrue(besttrack.latest_file(names, "EP").startswith(besttrack.INDEX + "hurdat2-nepac-1949-2025-"))


if __name__ == "__main__":
    unittest.main()
