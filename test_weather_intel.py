"""Weather Intelligence (weather/intel): the engine reads the story, resolves the event from official indexes, finds the graphics the
narration calls for, fetches their data and places them — with no weather_layers.csv. No network: official answers recorded on
2026-10-14 are replayed from weather/testdata/intel (see its README)."""

from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
import urllib.error
from datetime import date, datetime, timezone
from pathlib import Path

from weather.generate import WeatherProject, plan_layers
from weather.intel import engine, identity as idn
from weather.intel.numwords import number_at, ordinal_at, tokens, year_at
from weather.intel.understand import Segment, understand

FIX = Path(__file__).resolve().parent / "weather" / "testdata" / "intel"
POST = Path(__file__).resolve().parent / "weather" / "testdata" / "post"
NOW = datetime(2026, 10, 14, 8, 0, tzinfo=timezone.utc)
HEAD = "beat,row,vo_anchor,mode,type,id,place,frame,label,sub,text,role,kind,value_from,value_to,format,anchor,until,hold,asset,dur,why\n"


class Replay:
    """GETs answered from the recorded files; anything else is a 404 (not archived). `broken` URLs (substring) fail like the network."""

    def __init__(self, extra=None, broken=(), malformed=(), missing=()):
        self.index = json.loads((FIX / "index.json").read_text(encoding="utf-8"))
        self.extra = extra or {}
        self.broken, self.malformed, self.missing = broken, malformed, missing
        self.asked = []

    def _body(self, url: str) -> bytes:
        self.asked.append(url)
        if any(b in url for b in self.broken):
            raise RuntimeError(f"{url} could not be fetched (<urlopen error timed out>)")
        if any(m in url for m in self.missing):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        if any(m in url for m in self.malformed):
            return b"<html>Service temporarily replaced by a maintenance page</html>"
        for key, body in self.extra.items():
            if key in url:
                return body if isinstance(body, bytes) else body.encode("utf-8")
        if url in self.index:
            return (FIX / self.index[url]).read_bytes()
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    def text(self, url, **kw):
        return self._body(url).decode("utf-8", "replace")

    def bytes(self, url, **kw):
        return self._body(url)


def words_for(beats_text: str, wps: float = 2.6):
    """Narration words timed evenly from the beats' text (what Whisper would give for a steady reader)."""
    words, t = [], 0.0
    for r in csv.DictReader(io.StringIO(beats_text)):
        if r["row"] != "beat":
            continue
        for w in r["text"].split():
            words.append((w, round(t, 3), round(t + 0.9 / wps * 2, 3)))
            t += 1 / wps
        t += 0.6
    return words, t + 1.0


TORNADO = HEAD + "".join([
    'b1,beat,A tornado carrying estimated,map,push_in,,South Carolina,region,,,"A tornado carrying estimated winds of 115 miles per hour struck Newberry County, South Carolina, early Sunday morning, leaving a trail of damaged trees near the Broad River.",,,,,,,,,,,open\n',
    'b2,beat,The National Weather Service,map,hold,,South Carolina,region,,,"The National Weather Service confirmed the tornado’s EF2 rating following the weekend storms. The confirmation turned an early report of storm damage into a clearer account of what happened in northeastern Newberry County on October 11, 2026.",,,,,,,,,,,confirm\n',
    'b3,beat,Local reporting associated the,footage,,,,,,,"Local reporting associated the weekend severe weather with the remnants of Hurricane Isaias. Trees fell, a radar showed rotation and warnings went out.",,,,,,,,,,,feel\n',
    "b3,clip,,,,,,,,,,,,,,,,,,stock_video:dark storm clouds rolling over a wooded landscape,,clouds\n",
    'b4,beat,The tornado touched down,map,push_in,,"34.40,-81.42",local,,,"The tornado touched down at approximately 6:05 a.m. Eastern Daylight Time near the intersection of Henderson Ferry Road and Old Blair Road. The location is close to the Broad River and the boundary between Newberry and Fairfield counties.",,,,,,,,,,,touchdown\n',
    'b5,beat,The report says the,map,hold,,"34.40,-81.42",local,,,"The report says the National Weather Service issued a tornado warning for northeastern Newberry County early Sunday as the storm moved through. By approximately 6:15 a.m., the warning for Newberry County had been canceled as the storm moved on.",,,,,,,,,,,warning\n',
    'b6,beat,The Newberry confirmation also,map,hold,,South Carolina,region,,,"The Newberry confirmation also formed part of a wider assessment of tornadoes from the weekend storms. The article published Monday reported other confirmed tornadoes in Allendale and Barnwell counties.",,,,,,,,,,,wider\n',
    'b7,beat,In Allendale County the,map,hold,,South Carolina,region,,,"In Allendale County the reported damage included homes that lost roofing material, along with damaged or destroyed porches, carports, and outbuildings. No injuries or deaths were reported in that account.",,,,,,,,,,,allendale\n',
])

IAN = HEAD + "".join([
    'b1,beat,This is a look,map,,,Caribbean,region,,,"This is a look back at Hurricane Ian, from September of twenty twenty two. Here is the storm from space, one picture a day from a NASA and NOAA weather satellite, as it crossed the Caribbean and turned north toward the Gulf coast of Florida.",,,,,,,,,,,open\n',
    'b2,beat,This is the storm\'s,map,hold,,Caribbean,region,,,"This is the storm\'s path, as the National Hurricane Center analyzed it after the season, colored by strength. At eight in the morning on Wednesday, September twenty eighth, that analysis puts the hurricane at category five, with winds near one hundred sixty miles per hour.",,,,,,,,,,,path\n',
    'b3,beat,"That morning, the hurricane",map,,,Florida,region,,,"That morning, the hurricane center\'s eleven o\'clock advisory placed the cone of uncertainty over southwest and central Florida, with hurricane warnings along the coast.",,,,,,,,,,,cone\n',
    'b4,beat,"Now the radar, from",map,push_in,,Florida,region,,,"Now the radar, from ten in the morning to six in the evening, Eastern time. The warnings appear as they were issued: tornado warnings in red, and extreme wind warnings in orange, as the eyewall moved onshore.",,,,,,,,,,,radar\n',
    'b5,beat,"In all, the National",map,,,Florida,region,,,"In all, the National Weather Service issued five extreme wind warnings in Florida between eight in the morning and eight at night that Wednesday. The Weather Prediction Center\'s rain outlook for that day had a high risk of excessive rainfall over central and southwest Florida.",,,,,,,,,,,count\n',
])


def project(beats: str, layers: str = "") -> WeatherProject:
    tmp = tempfile.mkdtemp()
    p = WeatherProject(Path(tmp) / "wx")
    p.root.mkdir()
    p.beats_csv.write_text(beats, encoding="utf-8")
    if layers:
        p.layers_csv.write_text(layers, encoding="utf-8")
    return p


def run(p: WeatherProject, replay: Replay, *, fmt="news", dry_run=False, fetch=True):
    words, dur = words_for(p.beats_csv.read_text(encoding="utf-8"))
    plan, text = engine.project_plan(p, words, dur, [])
    return engine.run(p, plan, words, beats_text=text, fmt=fmt, dry_run=dry_run, now=NOW, get_text=replay.text, get_bytes=replay.bytes,
                      fetch_data=fetch), words, dur


# ---- reading the story ---------------------------------------------------------------------------------------------------------

class SpokenNumbers(unittest.TestCase):
    def test_numbers_years_and_days_in_words(self):
        self.assertEqual(number_at(tokens("one hundred sixty miles"), 0), (160.0, 3))
        self.assertEqual(number_at(tokens("forty-one point nine feet"), 0)[0], 41.9)
        self.assertEqual(number_at(tokens("sixteen point zero seven"), 0)[0], 16.07)
        self.assertEqual(year_at(tokens("twenty twenty two"), 0), (2022, 3))
        self.assertEqual(year_at(tokens("two thousand seventeen"), 0)[0], 2017)
        self.assertEqual(year_at(tokens("nineteen eighty nine"), 0)[0], 1989)
        self.assertEqual(ordinal_at(tokens("twenty-eighth"), 0), (28, 2))
        self.assertEqual(ordinal_at(tokens("thirty first"), 0), (31, 2))
        self.assertIsNone(year_at(tokens("twenty five"), 0))


class Understanding(unittest.TestCase):
    def seg(self, text, sid="b1", mode="map"):
        return Segment(sid, mode, text)

    def test_dates_in_words_take_the_story_year_not_a_record_year(self):
        u = understand([self.seg("This is a report on Hurricane Harvey of August twenty seventeen."),
                        self.seg("Houston measured sixteen inches on August twenty seventh. The previous record was on June twenty sixth, "
                                 "nineteen eighty nine.", "b2"),
                        self.seg("Buffalo Bayou crested on August twenty eighth.", "b3")])
        days = [(d.seg, d.day) for d in u.dates]
        self.assertIn(("b2", "2017-08-27"), days)
        self.assertIn(("b2", "1989-06-26"), days)
        self.assertIn(("b3", "2017-08-28"), days)
        self.assertNotIn("2017-08-20", [d for _s, d in days])   # "August twenty seventeen" is a month and a year

    def test_weekday_is_read_against_the_full_date_the_story_says(self):
        u = understand([self.seg("A tornado struck early Sunday morning."), self.seg("It happened on October 11, 2026.", "b2")])
        sunday = next(d for d in u.dates if d.text == "sunday")
        self.assertEqual(sunday.day, "2026-10-11")
        self.assertTrue(any("Sunday" in a for a in u.assumptions))

    def test_relative_day_without_any_date_is_an_open_question(self):
        u = understand([self.seg("A tornado struck yesterday evening near the river.")])
        self.assertTrue(u.ambiguities)

    def test_relative_day_with_a_recording_date(self):
        u = understand([self.seg("A tornado struck yesterday evening.")], datetime(2026, 10, 12, 15, tzinfo=timezone.utc))
        self.assertEqual(next(d for d in u.dates if d.text.startswith("yesterday")).day, "2026-10-11")

    def test_a_weekday_that_disagrees_with_the_date_is_flagged(self):
        u = understand([self.seg("On Monday, October 11, 2026, a tornado struck.")])
        self.assertTrue(any("Monday" in a and "Sunday" in a for a in u.ambiguities))

    def test_category_places_and_claims(self):
        u = understand([self.seg("A tornado carrying estimated winds of 115 miles per hour struck Newberry County, South Carolina. "
                                 "Each frame comes from the Iowa Environmental Mesonet. It received an EF2 rating.")])
        self.assertEqual(u.category, "tornado")
        self.assertEqual(u.states, ["SC"])   # Iowa is part of an organisation's name, not a place in the story
        county = u.places_of("county")[0]
        self.assertEqual((county.name, county.state), ("Newberry County", "SC"))
        self.assertAlmostEqual(county.lat, 34.25, delta=0.2)
        self.assertIn(("mph", 115.0), [(m.unit, m.value) for m in u.measurements])
        self.assertIn(("EF", 2.0), [(m.unit, m.value) for m in u.measurements])

    def test_a_storm_named_in_passing_is_not_the_story(self):
        u = understand([self.seg("A tornado touched down. Tornadoes damaged trees. Local reporting tied it to the remnants of Hurricane Isaias.")])
        self.assertEqual(u.category, "tornado")
        self.assertEqual([s.name for s in u.storms], ["ISAIAS"])


# ---- identity --------------------------------------------------------------------------------------------------------------------

class Identity(unittest.TestCase):
    records = idn.parse_storm_list((FIX / "storm_list_subset.txt").read_text(encoding="utf-8"))

    def test_a_shared_name_without_a_year_is_never_guessed(self):
        rec, why = idn.resolve_storm("Harvey", self.records)
        self.assertIsNone(rec)
        self.assertIn("ambiguous", why)
        self.assertIn("AL092017", why)

    def test_the_year_said_picks_the_storm(self):
        rec, _ = idn.resolve_storm("Harvey", self.records, years=[2017])
        self.assertEqual(rec.id, "AL092017")
        rec, _ = idn.resolve_storm("Ian", self.records, years=[2022])
        self.assertEqual(rec.id, "AL092022")

    def test_current_season_storm_by_the_dates_of_the_story(self):
        rec, why = idn.resolve_storm("Isaias", self.records, days=["2026-10-11"], recorded=date(2026, 10, 13))
        self.assertEqual(rec.id, "AL092026")
        self.assertIsNone(rec.end)   # still listed as active
        rec, _ = idn.resolve_storm("Isaias", self.records, years=[2020])
        self.assertEqual(rec.id, "AL092020")

    def test_invests_and_genesis_entries_are_not_storms(self):
        rec, why = idn.resolve_storm("Invest", self.records, years=[2026])
        self.assertIsNone(rec)

    def test_morning_events_belong_to_the_previous_convective_day(self):
        self.assertEqual(idn.convective_day(datetime(2026, 10, 11, 10, 5, tzinfo=timezone.utc)), "2026-10-10")
        self.assertEqual(idn.convective_day(datetime(2026, 10, 11, 18, 0, tzinfo=timezone.utc)), "2026-10-11")

    def test_advisory_search_is_bounded_and_picks_the_last_one_issued_before(self):
        advs = idn.advisories((FIX / "ian_advisory_index_al09_2022.html").read_text(encoding="utf-8"), "AL092022")
        self.assertIn("024", advs)
        self.assertIn("023A", advs)
        opened = []

        def issued(adv):
            opened.append(adv)
            from weather.news import nhc
            from weather.tz import parse_iso

            return parse_iso(nhc.advisory((FIX / f"al092022_5day_{adv}.zip").read_bytes())["issued"])

        adv, t, _notes = idn.pick_advisory("AL092022", datetime(2022, 9, 28, 15, 0, tzinfo=timezone.utc), advs, issued)
        self.assertEqual(adv, "024")
        self.assertEqual(t, datetime(2022, 9, 28, 15, 0, tzinfo=timezone.utc))
        self.assertLessEqual(len(opened), 9)

    def test_gauge_on_a_named_river_near_the_named_place(self):
        rdb = ("agency_cd\tsite_no\tstation_nm\tsite_tp_cd\tdec_lat_va\tdec_long_va\n5s\t15s\t50s\t7s\t16s\t16s\n"
               "USGS\t08072300\tBuffalo Bayou nr Katy, TX\tST\t29.74\t-95.80\n"
               "USGS\t08074000\tBuffalo Bayou at Houston, TX\tST-TS\t29.76\t-95.41\n"
               "USGS\t08067650\tW Fk San Jacinto Rv bl Lk Conroe nr Conroe, TX\tST\t30.34\t-95.54\n"
               "USGS\t08072050\tSan Jacinto Rv nr Sheldon, TX\tST-TS\t29.88\t-95.09\n")
        sites = idn.parse_sites(rdb)
        g, _ = idn.pick_gauge("Buffalo Bayou", sites, "Buffalo Bayou, which runs through downtown Houston, crested", (29.76, -95.37))
        self.assertEqual(g.site, "08074000")
        g, _ = idn.pick_gauge("San Jacinto River", sites, "East of the city, the San Jacinto River near Sheldon crested", None)
        self.assertEqual(g.site, "08072050")   # the main stem, not the West Fork
        g, why = idn.pick_gauge("Brazos River", sites, "the Brazos River rose", None)
        self.assertIsNone(g)


# ---- the engine, end to end (offline) -------------------------------------------------------------------------------------------

class TornadoWithNoWeatherFile(unittest.TestCase):
    """Mode A: a beat plan and a narration, no weather_layers.csv."""

    def setUp(self):
        self.p = project(TORNADO)
        self.replay = Replay()
        self.res, self.words, self.dur = run(self.p, self.replay)

    def test_the_event_is_resolved(self):
        e = self.res.event
        self.assertEqual(e["category"], "tornado")
        self.assertEqual(e["main_day"], "2026-10-11")
        self.assertEqual(e["moment"], "2026-10-11T10:05:00Z")       # 6:05 a.m. EDT
        self.assertEqual(e["convective_day"], "2026-10-10")         # before 12 UTC: the previous SPC day
        self.assertEqual(e["states"], ["SC"])
        self.assertIsNone(e["storm"])                               # Isaias is context, not the story
        self.assertTrue(any("AL092026" in note for _n, note in e["context_storms"]))

    def test_the_graphics_were_found_and_placed_on_the_narration(self):
        by = {d.id: d for d in self.res.added}
        # first the moment +-2 h, then fitted to the tornado warning it shows (issued 10:05Z, ended 10:15Z)
        self.assertEqual(by["auto_radar"].data_source, "iem:radar@2026-10-11T09:55Z..2026-10-11T10:25Z#n0q")
        self.assertEqual(by["auto_warnings"].data_source.split("#")[0], "iem:warnings@2026-10-11T09:55Z..2026-10-11T10:25Z")
        self.assertEqual(by["auto_warnings"].beat, by["auto_radar"].beat)
        self.assertEqual(by["auto_radar"].beat, "b5")              # the beat about the warning
        self.assertEqual(by["auto_reports"].data_source, "spc:reports@2026-10-10#tornado")
        self.assertEqual(by["auto_reports"].extra["states"], ["SC"])
        self.assertIn(by["auto_reports"].beat, ("b2", "b6", "b7"))   # beats about confirmed tornadoes
        self.assertIn("auto_headline", by)
        self.assertIn("auto_label_newberry_county", by)
        for d in self.res.added:
            self.assertNotEqual(d.beat, "b3", "nothing goes on a full-screen footage beat")

    def test_the_fitted_loop_falls_back_when_its_data_is_missing(self):
        p = project(TORNADO)
        res, _w, _d = run(p, Replay(missing=("2026-10-11T09:55Z", "2026-10-11T09%3A55")))
        by = {d.id: d for d in res.added}
        self.assertEqual(by["auto_radar"].data_source, "iem:radar@2026-10-11T08:00Z..2026-10-11T13:00Z#n0q")
        self.assertTrue(any("kept its first window" in n for n in res.notes))

    def test_files_written_and_the_users_files_untouched(self):
        self.assertFalse(self.p.layers_csv.exists())
        for name in ("auto_plan.json", "evidence.json", "report.md"):
            self.assertTrue((self.p.root / "intel" / name).is_file())
        self.assertTrue(self.p.resolved_json.is_file())
        report = (self.p.root / "intel" / "report.md").read_text(encoding="utf-8")
        self.assertIn("## Added for you", report)
        self.assertIn("2026-10-10", report)

    def test_evidence_keeps_categories_apart(self):
        ev = json.loads((self.p.root / "intel" / "evidence.json").read_text(encoding="utf-8"))
        kinds = {f["kind"] for f in ev["facts"]}
        self.assertIn("preliminary_report", kinds)
        self.assertIn("warning", kinds)
        count = next(f for f in ev["facts"] if f["subject"] == "tornado reports" and f["what"] == "count")
        self.assertEqual(count["where"], "SC")
        self.assertEqual(count["quality"], "preliminary")
        self.assertGreaterEqual(count["value"], 1)
        self.assertTrue(all(a["status"] == "ok" for a in ev["attempts"]))

    def test_a_second_run_adds_nothing_twice(self):
        first = json.loads((self.p.root / "intel" / "auto_plan.json").read_text(encoding="utf-8"))["rows"]
        res2, _w, _d = run(self.p, Replay())
        second = json.loads((self.p.root / "intel" / "auto_plan.json").read_text(encoding="utf-8"))["rows"]
        self.assertEqual([r["id"] for r in first], [r["id"] for r in second])
        self.assertEqual(len({r["id"] for r in second}), len(second))

    def test_the_render_plan_takes_the_engines_graphics(self):
        plan, rows, snap, payload = plan_layers(self.p, self.words, self.dur, now=NOW)
        types = {e["type"] for e in payload.events}
        self.assertIn("storm_reports", types)
        self.assertTrue(payload.rasters, "the radar loop is a timed tile layer")
        self.assertTrue(any(f["type"] == "fill" for f in payload.fills), "the archived warning polygon is drawn")
        reports = next(e for e in payload.events if e["type"] == "storm_reports")
        self.assertIn("SC", reports["sub"])
        self.assertTrue(any("spc.noaa.gov" in ln["url"] for ln in payload.report.lines))
        # every engine graphic was timed on its own words (no fallback to the beat start)
        auto = [r for r in rows if r.id.startswith("auto_")]
        self.assertTrue(auto)

    def test_limits_per_beat(self):
        from weather.intel.planner import LOOP_TYPES, NOT_DATA

        for beat in {d.beat for d in self.res.added}:
            ds = [d for d in self.res.added if d.beat == beat and d.type not in NOT_DATA]
            self.assertLessEqual(len(ds), 3)
            self.assertLessEqual(sum(1 for d in ds if d.type in LOOP_TYPES), 1)
            self.assertLessEqual(sum(1 for d in ds if d.type == "counter"), 1)


class DryRun(unittest.TestCase):
    def test_nothing_is_written(self):
        p = project(TORNADO)
        res, _w, _d = run(p, Replay(), dry_run=True)
        self.assertTrue(res.added)
        self.assertFalse((p.root / "intel").exists())
        self.assertFalse(p.resolved_json.exists())
        self.assertIn("dry run", res.report)


class FailingSources(unittest.TestCase):
    def test_a_missing_archive_drops_only_that_graphic(self):
        p = project(TORNADO)
        res, _w, _d = run(p, Replay(missing=("spc.noaa.gov/climo/reports",)))
        ids = {d.id for d in res.added}
        self.assertNotIn("auto_reports", ids)
        self.assertIn("auto_radar", ids)
        why = dict((d.id, w) for d, w in res.dropped)["auto_reports"]
        self.assertIn("unavailable", why)
        self.assertTrue(any(a.status == "unavailable" for a in res.evidence.attempts))

    def test_a_network_failure_is_temporary_and_reported_as_degraded(self):
        p = project(TORNADO)
        res, _w, _d = run(p, Replay(broken=("json/radar",)))
        ids = {d.id for d in res.added}
        self.assertNotIn("auto_radar", ids)
        self.assertNotIn("auto_warnings", ids)     # it goes with the radar loop
        self.assertIn("auto_reports", ids)
        self.assertIn("temporary", dict((d.id, w) for d, w in res.dropped)["auto_radar"])
        self.assertIn("Degraded", res.report)

    def test_a_malformed_answer_is_never_shown_as_data(self):
        p = project(TORNADO)
        res, _w, _d = run(p, Replay(malformed=("spc.noaa.gov/climo/reports",)))
        self.assertNotIn("auto_reports", {d.id for d in res.added})

    def test_no_storm_list_still_plans_the_rest(self):
        p = project(TORNADO)
        res, _w, _d = run(p, Replay(missing=("storm_list",)))
        self.assertIn("auto_reports", {d.id for d in res.added})


LAYERS = ("beat,vo_anchor,t,id,type,place,data_source,hold,until,extra\n"
          "b1,A tornado carrying estimated,,sat1,satellite,,gibs:geocolor@latest,,end,\n"
          'b1,A tornado carrying estimated,,head1,headline,,,7,,"{""kicker"": ""STORM SURVEY"", ""title"": ""Tornado confirmed"", ""sub"": ""OCTOBER 11"", ""tone"": ""news""}"\n'
          'b1,"struck Newberry County,",,lbl_newb,place_label,"34.40,-81.42",,,end,"{""text"": ""Newberry County""}"\n'
          "b6,The Newberry confirmation also,,rep1,storm_reports,,spc:reports@2026-10-11#tornado,,,\n")


class WithTheUsersWeatherFile(unittest.TestCase):
    """Mode B: the user's rows are kept as written; gaps are filled; conflicts are reported, not applied."""

    def setUp(self):
        self.p = project(TORNADO, LAYERS)
        self.res, self.words, self.dur = run(self.p, Replay())

    def test_user_rows_kept_and_file_unchanged(self):
        self.assertEqual(self.p.layers_csv.read_text(encoding="utf-8"), LAYERS)
        self.assertEqual(self.res.mode, "B")
        ids = {d.id for d in self.res.added}
        self.assertNotIn("auto_headline", ids)                 # the user has a headline
        self.assertNotIn("auto_label_newberry_county", ids)    # and a Newberry label
        self.assertNotIn("auto_reports", ids)                  # and storm reports
        self.assertIn("auto_radar", ids)                       # the gap is filled

    def test_conflicts_are_reported_with_a_proposal(self):
        c = {x.row: x for x in self.res.conflicts}
        self.assertEqual(c["sat1"].kind, "stale")
        self.assertIn("geocolor@2026-10-11T10:00Z", c["sat1"].replacement)
        self.assertEqual(c["rep1"].kind, "conflict")            # the morning tornado is in the 2026-10-10 file
        self.assertIn("2026-10-10", c["rep1"].replacement)
        self.assertFalse(any(x.applied for x in self.res.conflicts))
        self.assertIn("NOT changed", self.res.report)

    def test_accepted_proposals_apply_in_memory_only(self):
        (self.p.root / "intel" / "overrides.json").write_text(json.dumps({"accept": ["conflict:rep1"]}), encoding="utf-8")
        res, _w, _d = run(self.p, Replay())
        self.assertTrue(next(x for x in res.conflicts if x.row == "rep1").applied)
        self.assertEqual(self.p.layers_csv.read_text(encoding="utf-8"), LAYERS)
        plan, rows, snap, payload = plan_layers(self.p, self.words, self.dur, now=NOW)
        self.assertEqual(next(r for r in rows if r.id == "rep1").data_source.target, "2026-10-10")

    def test_both_files_render_together(self):
        plan, rows, snap, payload = plan_layers(self.p, self.words, self.dur, now=NOW)
        ids = [r.id for r in rows]
        self.assertIn("head1", ids)
        self.assertIn("auto_radar", ids)
        self.assertEqual(len(ids), len(set(ids)))


class Overrides(unittest.TestCase):
    def test_excluded_graphics_are_not_added(self):
        p = project(TORNADO)
        (p.root / "intel").mkdir()
        (p.root / "intel" / "overrides.json").write_text(json.dumps({"exclude": ["radar.loop", "broadcast.place_label"]}), encoding="utf-8")
        res, _w, _d = run(p, Replay())
        ids = {d.id for d in res.added}
        self.assertNotIn("auto_radar", ids)
        self.assertFalse(any(i.startswith("auto_label_") for i in ids))
        self.assertIn("auto_reports", ids)
        self.assertTrue(any("excluded" in s.reason for s in res.skipped))

    def test_the_event_can_be_set(self):
        p = project(TORNADO.replace("on October 11, 2026", "on the eleventh"))
        (p.root / "intel").mkdir()
        (p.root / "intel" / "overrides.json").write_text(json.dumps({"event": {"day": "2026-10-11", "year": 2026}}), encoding="utf-8")
        res, _w, _d = run(p, Replay())
        self.assertEqual(res.event["convective_day"], "2026-10-10")


class HurricaneIan(unittest.TestCase):
    def test_identity_advisory_and_windows_from_the_records(self):
        extra = {"hurdat2-": (FIX / "hurdat2_al092022_only.txt").read_bytes(), "/data/hurdat/": (FIX / "hurdat_index.html").read_bytes()}
        p = project(IAN)
        res, _w, _d = run(p, Replay(extra=extra), fetch=False)
        e = res.event
        self.assertEqual(e["storm"]["id"], "AL092022")
        self.assertEqual(e["moment"], "2022-09-28T19:05:00Z")      # the strongest Florida landfall (HURDAT2)
        by = {d.id: d for d in res.added}
        self.assertEqual(by["auto_cone"].data_source, "nhc:cone@AL092022#024")   # "eleven o'clock" Wednesday = 15 UTC
        self.assertEqual(by["auto_cone"].beat, "b3")
        self.assertEqual(by["auto_cone_track"].beat, "b3")
        self.assertEqual(by["auto_best_track"].beat, "b2")
        self.assertEqual(by["auto_radar"].data_source, "iem:radar@2022-09-28T14:00Z..2022-09-28T22:00Z#n0q")
        self.assertEqual(by["auto_radar"].entity, "said")   # the narration's own window is never refitted
        self.assertEqual(by["auto_warn_count"].data_source, "iem:warnings@2022-09-28T12:00Z..2022-09-29T00:00Z#EW")
        self.assertEqual(by["auto_sat_loop"].beat, "b1")
        self.assertEqual(by["auto_ero"].data_source, "wpc:ero@2022-09-28#day1")
        # phase 2: the record card, the landfall marker and best-track labels at the times the narration says
        self.assertEqual(by["auto_storm_stats"].data_source, "nhc:stats@AL092022")
        self.assertEqual(by["auto_storm_stats"].extra["landfall"], 3)            # the third L record: Cayo Costa, 19:05Z
        self.assertEqual(by["auto_best_track"].extra["label_times"], ["2022-09-28T12:00Z"])   # "eight in the morning" (EDT)
        self.assertEqual(by["auto_landfall"].place, "26.70,-82.20")
        self.assertIn(by["auto_landfall"].beat, ("b4", "b1", "b2", "b3"))
        self.assertNotIn(by["auto_landfall"].beat, ("b5",))


class Composition(unittest.TestCase):
    def test_the_side_card_goes_where_the_track_is_not(self):
        from types import SimpleNamespace

        from weather.intel.catalog import card_side

        seg = Segment("b2", "map", "x", cam="Caribbean")                      # centre about 19N 71W
        west = SimpleNamespace(ctx=SimpleNamespace(track=[(15.0, -78.0), (20.0, -82.0), (25.0, -83.0), (18.0, -70.0)]))
        east = SimpleNamespace(ctx=SimpleNamespace(track=[(15.0, -62.0), (18.0, -65.0), (20.0, -60.0)]))
        self.assertEqual(card_side(west, seg), "r")
        self.assertEqual(card_side(east, seg), "l")
        self.assertEqual(card_side(west, Segment("b3", "footage", "x")), "l")

    def test_no_second_title_over_the_plans_own(self):
        beats = IAN.replace("b1,beat,This is a look,map,,,Caribbean,region,,,", "b1,beat,This is a look,map,,,Caribbean,region,,,", 1)
        beats = beats.replace("b2,beat,", "b1,layer,This is a look,,hud_title,t1,,,HURRICANE IAN,SEPTEMBER,,,,,,,,,,,,\nb2,beat,", 1)
        p = project(beats)
        extra = {"hurdat2-": (FIX / "hurdat2_al092022_only.txt").read_bytes(), "/data/hurdat/": (FIX / "hurdat_index.html").read_bytes()}
        res, _w, _d = run(p, Replay(extra=extra), fetch=False)
        self.assertNotIn("auto_headline", {d.id for d in res.added})
        self.assertTrue(any(s.spec == "broadcast.headline" and "title card" in s.reason for s in res.skipped))
        self.assertEqual(next(d for d in res.added if d.id == "auto_storm_stats").extra["anchor"], "r")


class StormStatsLayer(unittest.TestCase):
    """storm_stats (weather/layers/stormstats.py): every value from the HURDAT2 block, in the numbers report."""

    def test_ian_record_card(self):
        from weather.events import WeatherPayload
        from weather.layers import get
        from weather.resolve import Snapshot
        from weather.sidecar import WxRow, parse_data_source
        from weather.timing import Window

        lines = (FIX / "hurdat2_al092022_only.txt").read_text(encoding="utf-8").splitlines()
        snap = Snapshot("2026-10-14T08:00:00+00:00", extra={"post:nhc:best:AL092022": {"storm": "AL092022", "url": "https://x/hurdat2.txt",
                                                                                          "fetched": "2026-10-14T08:00:00Z", "lines": lines}})
        row = WxRow(line=2, beat="b2", id="st", type="storm_stats", place="Florida", data_source=parse_data_source("nhc:stats@AL092022"),
                    extra={"landfall": 3})
        lt = get("storm_stats")
        lt.check(row)
        out = WeatherPayload()
        lt.build(row, snap, Window(10.0, 20.0), out)
        e = out.events[0]
        self.assertEqual(e["title"], "HURRICANE IAN")
        self.assertEqual([r["value"] for r in e["rows"]], ["CAT 5 · 160 MPH", "937 MB", "CAT 4 · 150 MPH"])
        self.assertEqual(e["rows"][2]["sub"], "SEP 28, 3:05 PM EDT")
        self.assertEqual(len([ln for ln in out.report.lines if ln["layer"] == "st"]), 3)

    def test_a_current_season_storm_is_left_out_with_the_reason(self):
        p = project(IAN.replace("Hurricane Ian", "Hurricane Isaias").replace("twenty twenty two", "twenty twenty six"))
        res, _w, _d = run(p, Replay(), fetch=False)
        self.assertEqual(res.event["storm"]["id"], "AL092026")
        by = {d.id: d for d in res.added}
        self.assertEqual(by["auto_storm_stats"].data_source, "nhc:stats@AL092026#working")   # preliminary, from the working track
        self.assertIn("WORKING", by["auto_storm_stats"].why)

    def test_working_best_track_card_is_labelled_preliminary(self):
        from weather.events import WeatherPayload
        from weather.layers import FetchContext, get
        from weather.resolve import Snapshot
        from weather.sidecar import WxRow, parse_data_source
        from weather.timing import Window

        snap = Snapshot("2026-10-14T08:00:00+00:00")
        row = WxRow(line=2, beat="b1", id="st", type="storm_stats", place="Florida", data_source=parse_data_source("nhc:stats@AL092026#working"))
        lt = get("storm_stats")
        lt.check(row)
        lt.fetch(row, FetchContext(snap=snap, now=NOW, get_bytes=Replay().bytes, get_text=Replay().text))
        out = WeatherPayload()
        lt.build(row, snap, Window(0.0, 8.0), out)
        e = out.events[0]
        self.assertEqual(e["title"], "HURRICANE ISAIAS")
        self.assertEqual(e["rows"][0]["value"], "CAT 3 · 120 MPH")
        self.assertIn("PRELIMINARY", e["foot"])
        self.assertTrue(all("preliminary" in ln["label"] for ln in out.report.lines))

    def test_a_storm_named_in_passing_is_checked_against_its_best_track_not_the_list(self):
        p = project(TORNADO)
        res, _w, _d = run(p, Replay())
        self.assertFalse(any("worth checking" in n for n in res.notes))   # Isaias peaked at 105 kt: the script's "hurricane" is right
        self.assertTrue(any(f.subject.startswith("Isaias") and f.what == "peak sustained wind" and f.value == 120
                            for f in res.evidence.facts))


class NoBeatPlanAtAll(unittest.TestCase):
    """Mode A with only the narration: the beats are made from its sentences (weather.intel.beats), no CSV anywhere."""

    def test_script_and_voiceover_only(self):
        rows = [r for r in csv.DictReader(io.StringIO(TORNADO)) if r["row"] == "beat" and r["mode"] == "map"]
        script = "\n\n".join(r["text"] for r in rows)
        words, t = [], 0.0
        for w in script.split():
            words.append((w, round(t, 3), round(t + 0.35, 3)))
            t += 0.38 + (0.5 if w.endswith(".") else 0.0)
        tmp = tempfile.mkdtemp()
        p = WeatherProject(Path(tmp) / "wx")
        p.root.mkdir()
        (p.root / "script.txt").write_text(script, encoding="utf-8")
        plan, text = engine.project_plan(p, words, t + 1.0, notes := [])
        self.assertEqual(text, "")
        self.assertTrue(all(b.mode == "map" for b in plan.beats))
        self.assertTrue(any("no beat plan" in n for n in notes))
        res = engine.run(p, plan, words, now=NOW, get_text=Replay().text, get_bytes=Replay().bytes)
        ids = {d.id for d in res.added}
        self.assertIn("auto_radar", ids)
        self.assertIn("auto_reports", ids)
        self.assertFalse(p.beats_csv.exists() or p.layers_csv.exists())
        plan2, rows2, snap, payload = plan_layers(p, words, t + 1.0, now=NOW)
        self.assertEqual([b.id for b in plan2.beats], [b.id for b in plan.beats])
        self.assertTrue(payload.rasters)


class TheAppCard(unittest.TestCase):
    """The Weather card's entry points: a plan with no weather rows is a plan when the engine is on, and the engine runs before
    Check plan / Generate (never raising)."""

    def app(self, root: Path):
        from types import SimpleNamespace

        return SimpleNamespace(_workspace=SimpleNamespace(root=str(root)))

    def test_a_beat_plan_alone_is_a_plan_when_intelligence_is_on(self):
        from weather import app_section

        tmp = Path(tempfile.mkdtemp())
        (tmp / "weather").mkdir()
        (tmp / "weather" / "beats.csv").write_text(TORNADO, encoding="utf-8")
        self.assertTrue(app_section.has_plan(self.app(tmp)))
        (tmp / "weather" / "weather.json").write_text(json.dumps({"intelligence": False}), encoding="utf-8")
        self.assertFalse(app_section.has_plan(self.app(tmp)))

    def test_one_file_plan_without_weather_rows_splits_into_beats_only(self):
        from weather.app_section import split_one_file

        one = TORNADO.replace("why\n", "why,data_source,extra\n", 1)
        beats, layers = split_one_file(one)
        self.assertTrue(beats)
        self.assertIsNone(layers)

    def test_the_engine_never_stops_a_render(self):
        p = project(TORNADO)
        logs = []
        words, dur = words_for(TORNADO)
        res = engine.prepare_project(p, words, dur, log=logs.append, now=NOW, get_text=Replay(broken=("",)).text,
                                     get_bytes=Replay(broken=("",)).bytes)
        self.assertIsNotNone(res)    # every source failed: the run still finishes, and says so
        self.assertFalse([d for d in res.added if d.type not in ("headline", "place_label", "source_line")])
        self.assertTrue(any("Degraded" in res.report for _ in [0]))


class NarrationNumbers(unittest.TestCase):
    def test_said_numbers_are_matched_to_shown_numbers_never_called_wrong(self):
        u = understand([Segment("b4", "map", "Port Arthur measured forty seven point four eight inches. It reached category four."),
                        Segment("b5", "map", "The path was 450 yards wide.")])
        shown = [{"layer": "t", "label": "PORT ARTHUR total", "shown": "47.48 IN", "product": "RCC-ACIS"},
                 {"layer": "k", "label": "track point", "shown": "CAT 4 · 130 MPH", "product": "NHC best track"},
                 {"layer": "x", "label": "a clock", "shown": "4:50 PM", "product": "IEM"}]
        u.measurements.append(type(u.measurements[0])("b4", "five extreme wind warnings", 5.0, "count", "count_warnings"))
        got = {c["said"]: c for c in engine.check_claims(u, shown)}
        self.assertFalse(got["five extreme wind warnings"]["verified"])   # "CAT 4 · 130" is not a count of warnings
        got = {c["said"]: c for c in engine.check_claims(u, shown + [{"layer": "c", "label": "extreme wind warnings issued", "shown": "5",
                                                                        "product": "IEM"}])}
        self.assertTrue(got["five extreme wind warnings"]["verified"])
        self.assertTrue(got["forty seven point four eight inches"]["verified"])
        self.assertTrue(got["category 4"]["verified"])
        self.assertFalse(got["450 yards"]["verified"])   # unverified, not "wrong"


if __name__ == "__main__":
    unittest.main()
