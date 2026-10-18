"""Automatic place boundary highlighting (place_focus + boundary_source): real polygons only, a place is outlined when the narration discusses it, an
unsure place is skipped with a reason. No test touches the network: Nominatim is a fake. Run: python -m unittest test_place_focus"""
import json
import os
import tempfile
import unittest
from pathlib import Path

import boundary_source as BS
import place_focus as PF
from pakmap.compile import compile_csv
from pakmap.words import estimate_words

os.environ["VIDEOGEN_BOUNDARY_NETWORK"] = "0"          # nothing here may reach OpenStreetMap, whatever else is imported
INTRO = "This is a long introduction sentence that fills the first few seconds of the video narration. "
OUTRO = " And then the story moves on to something else entirely for a while."


def square(lon, lat, d=0.2):
    return [[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d]]


def item(name="Houston", lon=-95.37, lat=29.76, country="United States", osm=2688911, geom=None, category="boundary", typ="administrative", osm_type="relation"):
    return {"osm_type": osm_type, "osm_id": osm, "category": category, "type": typ, "name": name, "display_name": f"{name}, Harris County, Texas, {country}",
            "address": {"country": country}, "geojson": geom or {"type": "Polygon", "coordinates": [square(lon, lat)]}}


class FakeNominatim:
    def __init__(self, answers=None, error=None):
        self.answers, self.error, self.calls = answers or {}, error, []

    def __call__(self, params):
        self.calls.append(params)
        if self.error:
            raise self.error
        for key, items in self.answers.items():
            if key.lower() in params["q"].lower():
                return items
        return []


class Clock:
    def __init__(self):
        self.t, self.sleeps = 1000.0, []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def store(fetch, tmp, clock=None, **kw):
    clock = clock or Clock()
    BS._offline_until[0] = 0.0
    BS._last_request[0] = 0.0
    return BS.BoundaryStore(Path(tmp), fetch, now=clock.now, sleep=clock.sleep, iso_of_name=PF.iso_of_country_name, **kw), clock


def plan(text, st=None, **kw):
    return PF.focus_events(estimate_words(INTRO + text + OUTRO), store=st, **kw)


class TestLocalBoundaries(unittest.TestCase):
    def test_a_county_with_its_state_a_state_and_a_country_get_their_real_outlines(self):
        r = plan("Flooding is spreading across Miami-Dade County, Florida, and the water keeps rising. Texas faces another week of rain. "
                 "Meanwhile the storm is approaching Kenya from the east.")
        kinds = [(e["geo_focus"]["entity"], e["geo_focus"]["kind"]) for e in r.events]
        self.assertEqual(kinds, [("Miami-Dade", "county"), ("Texas", "admin1"), ("Kenya", "country")])
        self.assertEqual(r.events[2]["iso"], ["KEN"])                                    # a country is the engine's own outline
        self.assertGreater(len(r.events[1]["polys"]), 1)                                 # Texas: several parts, passed through untouched
        for e in r.events:
            self.assertEqual(e["type"], "fill")

    def test_the_geometry_is_the_apps_own_polygon_not_a_box_or_a_circle(self):
        from map_scene.places import _dataset
        miami = next(f for f in _dataset("us_counties") if f["n"] == "Miami-Dade")
        r = plan("Flooding is spreading across Miami-Dade County, Florida, and the water keeps rising.")
        self.assertEqual(r.events[0]["polys"], miami["g"]["coordinates"])

    def test_an_island_state_keeps_every_part(self):
        r = plan("The system is moving toward Nova Scotia and the water keeps rising.")
        from map_scene.places import _dataset
        ns = next(f for f in _dataset("admin1") if f["n"] == "Nova Scotia")
        self.assertEqual(len(r.events[0]["polys"]), len(ns["g"]["coordinates"]))
        self.assertGreater(len(r.events[0]["polys"]), 1)


class TestDiscussedNotMentioned(unittest.TestCase):
    def names(self, text):
        return [e["geo_focus"]["entity"] for e in plan(text).events]

    def test_motion_and_location_cues_count(self):
        self.assertEqual(self.names("The hurricane has made landfall in Texas today."), ["Texas"])
        self.assertEqual(self.names("The storm is approaching Kenya and the coast is empty."), ["Kenya"])
        self.assertEqual(self.names("Texas faces another week of rain."), ["Texas"])

    def test_the_subject_of_a_reported_clause_counts(self):
        self.assertEqual(self.names("Forecasters say Kenya is bracing for the strongest winds of the night."), ["Kenya"])

    def test_possessives_parts_of_a_place_and_passing_mentions_do_not(self):
        self.assertEqual(self.names("Canada's east coast has the highest tides on Earth."), [])
        self.assertEqual(self.names("The system is moving toward the Texas coast tonight."), [])
        self.assertEqual(self.names("Heavy snow fell across northern Texas on Monday."), [])
        self.assertEqual(self.names("A book about Kenya was published last year."), [])

    def test_the_reasons_are_reported(self):
        r = plan("The system is moving toward the Texas coast tonight. Canada's east coast has the highest tides on Earth.")
        reasons = " | ".join(s.reason for s in r.skipped)
        self.assertIn("part of the place", reasons)
        self.assertIn("possessive", reasons)
        self.assertFalse(any(s.notable for s in r.skipped))                              # not discussed: nothing to tell the author


class TestAmbiguity(unittest.TestCase):
    def test_namesakes_without_evidence_are_skipped_never_settled_by_size(self):
        for text, name in (("Residents of Portland were told to stay home tonight.", "Portland"), ("Georgia braces for heavy rain this week.", "Georgia"),
                           ("Heavy rain is moving across Washington tonight.", "Washington"), ("Flooding hit Harris County overnight.", "Harris")):
            r = plan(text)
            self.assertEqual(r.events, [], text)
            self.assertTrue(any(name in s.reason and s.notable for s in r.skipped), (text, [s.reason for s in r.skipped]))

    def test_the_script_itself_is_the_evidence(self):
        r = plan("Flooding is spreading across Miami-Dade County, Florida, tonight. The hurricane has made landfall in Florida a day later.")
        self.assertEqual([e["geo_focus"]["entity"] for e in r.events], ["Miami-Dade", "Florida"])
        self.assertEqual(r.events[1]["geo_focus"]["country"], "USA")                      # not Uruguay's Florida
        r = plan("Tbilisi is bracing for rain. Georgia braces for heavy rain this week.")
        self.assertEqual([(e["geo_focus"]["entity"], e["geo_focus"]["country"]) for e in r.events], [("Georgia", "GEO")])    # the country: the script is about Tbilisi

    def test_an_explicit_state_decides(self):
        r = plan("Residents of Harris County, Texas were told to stay home tonight.")
        self.assertEqual([(e["geo_focus"]["entity"], e["geo_focus"]["state"]) for e in r.events], [("Harris", "Texas")])

    def test_a_state_that_is_also_a_city_is_not_guessed(self):
        r = plan("Heavy rain is moving across New York tonight.")
        self.assertEqual(r.events, [])


class TestCityBoundaries(unittest.TestCase):
    TEXT = "The storm is approaching Houston and the sky is dark."

    def test_a_valid_city_boundary_is_validated_cached_and_credited(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeNominatim({"Houston": [item()]})
            st, _ = store(fake, tmp)
            r = plan(self.TEXT, st)
            self.assertEqual([e["geo_focus"]["entity"] for e in r.events], ["Houston"])
            ev = r.events[0]
            self.assertEqual(ev["geo_focus"]["source"], "OpenStreetMap")
            self.assertEqual(ev["geo_focus"]["osm"], "relation/2688911")
            self.assertEqual(ev["polys"][0][0][0], [-95.57, 29.56])                       # the real outline, rounded, not a point or circle
            self.assertIn(BS.ATTRIBUTION, r.credits)
            self.assertEqual(len(fake.calls), 1)
            again, _ = store(fake, tmp)                                                   # a new run, the same cache
            r2 = plan(self.TEXT, again)
            self.assertEqual(len(fake.calls), 1)                                          # not asked twice
            self.assertEqual(r2.events[0]["polys"], ev["polys"])
            self.assertIn("(cached)", r2.events[0]["geo_focus"]["source"])

    def test_the_request_identifies_the_app_and_asks_for_a_polygon(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeNominatim({"Houston": [item()]})
            plan(self.TEXT, store(fake, tmp)[0])
            q = fake.calls[0]
            self.assertEqual((q["polygon_geojson"], q["format"]), ("1", "jsonv2"))
            self.assertIn("Houston", q["q"])
            self.assertIn("SemanticYTStudio/", BS._user_agent())

    def test_wrong_answers_are_rejected_with_a_reason_and_remembered(self):
        cases = {
            "a point": item(osm_type="node"),
            "wrong kind": item(category="highway", typ="residential"),
            "another name": item(name="Houston Heights"),
            "another country": item(country="Canada"),
            "a point geometry": item(geom={"type": "Point", "coordinates": [-95.37, 29.76]}),
            "elsewhere": item(lon=-80.0, lat=25.0),
            "huge": item(geom={"type": "Polygon", "coordinates": [square(-95.37, 29.76, 6.0)]}),
        }
        for label, answer in cases.items():
            with tempfile.TemporaryDirectory() as tmp:
                fake = FakeNominatim({"Houston": [answer]})
                r = plan(self.TEXT, store(fake, tmp)[0])
                self.assertEqual(r.events, [], label)
                self.assertTrue(any("no confirmed city boundary" in s.reason for s in r.skipped), label)
                plan(self.TEXT, store(fake, tmp)[0])
                self.assertEqual(len(fake.calls), 1, label + ": a rejected place is not asked again")

    def test_two_valid_but_different_areas_are_not_guessed_between(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeNominatim({"Houston": [item(osm=1), item(osm=2, geom={"type": "Polygon", "coordinates": [square(-95.37, 29.76, 0.3)]})]})
            r = plan(self.TEXT, store(fake, tmp)[0])
            self.assertEqual(r.events, [])
            self.assertTrue(any("not guessing" in s.reason for s in r.skipped))

    def test_a_multipart_city_with_a_hole_keeps_both_parts_and_the_hole(self):
        outer, hole, island = square(-95.37, 29.76, 0.3), square(-95.55, 29.55, 0.05), square(-94.7, 29.3, 0.05)
        geom = {"type": "MultiPolygon", "coordinates": [[outer, hole[::-1]], [island]]}
        with tempfile.TemporaryDirectory() as tmp:
            r = plan(self.TEXT, store(FakeNominatim({"Houston": [item(geom=geom)]}), tmp)[0])
            polys = r.events[0]["polys"]
            self.assertEqual((len(polys), len(polys[0])), (2, 2))                          # two parts, the first with its hole
            self.assertFalse(BS.contains_point(polys, -95.55, 29.55))                      # the hole is a hole
            self.assertTrue(BS.contains_point(polys, -95.37, 29.76))
            self.assertTrue(BS.contains_point(polys, -94.7, 29.3))                         # the island

    def test_a_heavy_outline_is_simplified_but_stays_a_closed_polygon(self):
        import math
        ring = [[-95.37 + 0.3 * math.cos(a / 4000 * 6.2832), 29.76 + 0.3 * math.sin(a / 4000 * 6.2832)] for a in range(4000)]
        ring.append(ring[0])
        out = BS.simplify([[ring]])
        self.assertLess(sum(len(r) for p in out for r in p), 2600)
        self.assertEqual(out[0][0][0], out[0][0][-1])
        self.assertTrue(BS.contains_point(out, -95.37, 29.76))

    def test_missing_unavailable_and_over_budget_are_graceful(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = plan(self.TEXT, store(FakeNominatim({}), tmp)[0])                        # OSM has nothing
            self.assertEqual(r.events, [])
            self.assertTrue(any("no confirmed city boundary" in s.reason and s.notable for s in r.skipped))
        with tempfile.TemporaryDirectory() as tmp:
            down = FakeNominatim(error=OSError("offline"))
            st, _ = store(down, tmp)
            r = plan(self.TEXT, st)
            self.assertEqual(r.events, [])
            self.assertIn("could not be reached", r.skipped[0].reason)
            plan(self.TEXT, st)
            self.assertEqual(len(down.calls), 1)                                          # it does not hammer a service that is down
            self.assertFalse(list(Path(tmp).glob("*.json")))                              # and does not remember the failure as an answer
        with tempfile.TemporaryDirectory() as tmp:
            st, _ = store(FakeNominatim({"Houston": [item()]}), tmp, network=False)
            self.assertEqual(plan(self.TEXT, st).events, [])                              # not cached, network off: skipped, no request

    def test_requests_are_throttled_and_capped(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeNominatim({"Houston": [item()], "Miami": [item(name="Miami", lon=-80.19, lat=25.76, osm=5)]})
            st, clock = store(fake, tmp)
            plan("The storm is approaching Houston now. Later the storm is approaching Miami and the sea is rising.", st)
            self.assertEqual(len(fake.calls), 2)
            self.assertTrue(all(s >= 1.0 for s in clock.sleeps) or len(clock.sleeps) <= 1)
        with tempfile.TemporaryDirectory() as tmp:
            st, _ = store(FakeNominatim({"Houston": [item()]}), tmp, max_queries=0)
            r = plan(self.TEXT, st)
            self.assertEqual(r.events, [])
            self.assertIn("limit", r.skipped[0].reason)


class TestTimingAndRepeats(unittest.TestCase):
    def test_the_outline_starts_at_the_word_and_ends_with_the_sentence(self):
        text = "Texas faces another week of rain and everyone is tired of it."
        words = estimate_words(INTRO + text + OUTRO)
        r = PF.focus_events(words)
        ev = r.events[0]
        start = next(a for w, a, _b in words if w == "Texas")
        end = next(b for w, _a, b in words if w == "it.")
        self.assertAlmostEqual(ev["t_in"], start, places=2)                                # "Texas" opens its sentence: the outline does not start earlier
        self.assertAlmostEqual(ev["t_out"], end + PF.TAIL_S, places=2)
        self.assertGreaterEqual(ev["t_out"] - ev["t_in"], PF.MIN_SHOW_S)

    def test_a_new_place_replaces_the_previous_focus(self):
        r = plan("Texas faces another week of rain. Heavy snow is moving across Kenya tonight.")
        a, b = r.events
        self.assertLessEqual(a["t_out"], b["t_in"] + 0.31)

    def test_the_same_place_in_the_next_sentence_extends_one_outline(self):
        r = plan("Texas faces another week of rain. Texas is bracing for more flooding.")
        self.assertEqual(len(r.events), 1)
        one = plan("Texas faces another week of rain.").events[0]
        self.assertGreater(r.events[0]["t_out"], one["t_out"])

    def test_a_repeat_mention_soon_after_adds_nothing_and_the_same_run_twice_is_the_same(self):
        text = ("Texas faces another week of rain. Heavy snow is moving across Kenya tonight and nobody expected it at all this year. "
                "Rivers are rising near the coast and the dams are full. Texas faces yet another week of rain.")
        r = plan(text)
        self.assertEqual([e["geo_focus"]["entity"] for e in r.events], ["Texas", "Kenya"])
        self.assertTrue(any("a moment ago" in s.reason for s in r.skipped))
        self.assertEqual(json.dumps(plan(text).events, sort_keys=True), json.dumps(r.events, sort_keys=True))

    def test_nothing_is_added_when_the_narration_is_over_covering_footage(self):
        words = estimate_words(INTRO + "Texas faces another week of rain." + OUTRO)
        r = PF.focus_events(words, footage=[(0.0, 60.0)])
        self.assertEqual(r.events, [])
        self.assertTrue(any("full-screen footage" in s.reason for s in r.skipped))

    def test_a_place_the_plan_already_outlines_is_not_outlined_again(self):
        words = estimate_words(INTRO + "Heavy snow is moving across Kenya tonight." + OUTRO)
        mine = PF.focus_events(words).events[0]
        r = PF.focus_events(words, existing_events=[{"id": "f", "type": "fill", "iso": ["KEN"], "t_in": mine["t_in"], "t_out": mine["t_out"]}])
        self.assertEqual(r.events, [])


class TestWarningsStayDistinct(unittest.TestCase):
    def test_the_focus_is_never_a_warning_and_never_touches_warning_polygons(self):
        warning = {"id": "wx_warn", "type": "fill", "polys": [[square(-95.0, 30.0)]], "color": "#DF2721", "opacity": 0.4, "t_in": 0.0, "t_out": 60.0}
        before = json.dumps(warning, sort_keys=True)
        words = estimate_words(INTRO + "Texas faces another week of rain." + OUTRO)
        r = PF.focus_events(words, existing_events=[warning])
        ev = r.events[0]
        self.assertFalse(ev["geo_focus"]["official_warning"])
        self.assertNotIn(ev["color"].lower(), PF.WARNING_COLOURS)
        self.assertNotIn(ev.get("role", ""), ("subject", "primary", "orange", "featured"))
        self.assertEqual(json.dumps(warning, sort_keys=True), before)                    # the warning layer is untouched
        self.assertNotEqual(ev["color"], warning["color"])


class TestCompilerIntegration(unittest.TestCase):
    HEAD = "item_no,vo_anchor,layer_type,layer_id,geo_ref,label_text,sub_text,value_to,params\n"

    def test_the_switch_off_changes_nothing_and_on_adds_focus_fills_and_the_credit(self):
        text = INTRO + "Texas faces another week of rain." + OUTRO
        csv_text = self.HEAD + '1,This is a long,hud_title,,,PART 1,,,\n'
        words = estimate_words(text)
        off = compile_csv(text=csv_text, words=words, validate=False)
        on = compile_csv(text=csv_text, words=words, validate=False, auto_templates=True)
        self.assertEqual([e["type"] for e in off.spec["events"]], ["hud_title"])
        fills = [e for e in on.spec["events"] if e["type"] == "fill"]
        self.assertEqual([f["geo_focus"]["entity"] for f in fills], ["Texas"])
        self.assertTrue(any(e.id == fills[0]["id"] for e in on.report.events))

    def test_a_plan_without_places_compiles_exactly_as_before(self):
        text = INTRO + "The numbers are rising everywhere you look this year." + OUTRO
        csv_text = self.HEAD + '1,This is a long,hud_title,,,PART 1,,,\n'
        a = compile_csv(text=csv_text, words=estimate_words(text), validate=False)
        b = compile_csv(text=csv_text, words=estimate_words(text), validate=False, auto_templates=True)
        self.assertEqual(a.spec["events"], b.spec["events"])


if __name__ == "__main__":
    unittest.main()
