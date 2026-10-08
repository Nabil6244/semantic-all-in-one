"""Visual actions: a resolved event becomes something the viewer SEES -- a liftoff, a landing, a flyby, an orbit insertion, a
departure, a rover's drive -- through the generic camera (follow shots on any trajectory) and the clock or a narration-paced
motion. One code path for every mission: no mission is named in the action logic, and missing data is reported, never
faked."""

import csv
import io
import json
import re
import unittest
from pathlib import Path

from starmap import Catalog, DatasetIndex, check_csv, compile_plan, read_plan
from starmap.actions import ACTIONS, event_action
from starmap.beat_csv import COLUMNS
from starmap.catalog import PACKS, base_body_ids

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "test_fixtures" / "starmap_datasets"
IDX = DatasetIndex([PACKS, FIXTURES], base_body_ids=base_body_ids())


def csv_of(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(COLUMNS), lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: (json.dumps(v) if k == "extra" and isinstance(v, dict) else v) for k, v in r.items()})
    return buf.getvalue()


def one(action, place, frame, date, craft, path="", length=10.0, extra=None, now="2026-10-08"):
    rows = [dict(beat="plan", row="plan", date=now),
            dict(beat="b1", row="beat", start="0", mode="map", type=action, place=place, frame=frame, date=date, text="x",
                 **({"extra": extra} if extra else {}))]
    if craft:
        rows.append(dict(beat="b1", row="layer", t="0.3", type="craft", id=craft))
    if path:
        rows.append(dict(beat="b1", row="layer", t="0.3", type="path", id=path))
    return csv_of(rows), length


def compiled(text, length):
    return compile_plan(read_plan(text, duration=length), Catalog(index=IDX))


def follows(spec):
    return [m["to"] for m in spec["camera"]["moves"] if m["to"].get("follow")]


class Liftoff(unittest.TestCase):
    def test_apollo_11_lifted_off_from_earth(self):
        """The acceptance case: frame the launch region, the craft on its pad, the clock through the ascent, the camera
        following the craft as it climbs, then pulling back -- all glides on the existing camera."""
        comp = compiled(*one("liftoff", "launch complex 39a", "body", "apollo11.launch", "apollo11.csm", "apollo11.earth_orbit"))
        a = comp.actions["b1"]
        self.assertEqual((a.action, a.craft, a.body, a.site), ("liftoff", "apollo11.csm", "earth", (-80.604, 28.608)))
        self.assertEqual(a.span, ("1969-07-16T13:31:52Z", "1969-07-16T13:43:49Z"), "from just before liftoff to the end of the ascent track")
        spec = comp.spec
        self.assertEqual(spec["camera"]["start"]["target"], "earth@-80.604,28.608", "frame the launch region first")
        f = follows(spec)
        self.assertEqual([x["follow"]["trajectory"] for x in f], ["apollo11_csm", "apollo11_csm"], "then follow the craft")
        self.assertLess(f[0]["distance"]["km"], f[1]["distance"]["km"], "and pull back")
        self.assertEqual(spec["clock"]["keys"][0], {"t": 0.0, "utc": "1969-07-16T13:31:52Z"})
        self.assertEqual(spec["clock"]["keys"][-1]["utc"], "1969-07-16T13:43:49Z", "the clock runs through the ascent")
        craft = next(L for L in spec["layers"] if L["type"] == "spacecraft")
        self.assertEqual(craft["show"], "always", "on the pad before liftoff")
        self.assertIn("FLIGHT PATH ILLUSTRATED", [L["text"] for L in spec["layers"] if L["type"] == "footnote"], "still honest about the geometry")

    def test_the_same_action_for_any_mission(self):
        for craft, date, site in (("artemis3.orion", "artemis3.launch", (-80.6208, 28.6272)), ("chandrayaan3.spacecraft", "chandrayaan3.launch", None)):
            with self.subTest(craft=craft):
                comp = compiled(*one("launch", "earth", "body", date, craft))
                a = comp.actions["b1"]
                self.assertEqual((a.action, a.asked), ("liftoff", "launch"))
                if site:
                    self.assertEqual(a.site, site)
                self.assertTrue(follows(comp.spec))
        planned = compiled(*one("liftoff", "earth", "body", "artemis3.launch", "artemis3.orion")).spec
        self.assertIn("PLANNED · NET SEP 2027", [L["text"] for L in planned["layers"] if L["type"] == "status_badge"], "labels stay")

    def test_no_mission_is_named_in_the_action_logic(self):
        src = (HERE / "starmap" / "actions.py").read_text(encoding="utf-8")
        for did in IDX.datasets:
            self.assertIsNone(re.search(rf"\b{did}\b", src), did)
        for f in ("lib/camera.mjs", "layers/spacecraft.mjs", "layers/trajectory.mjs"):
            eng = (HERE / "starmap-engine" / f).read_text(encoding="utf-8").lower()
            for word in ("apollo", "artemis", "voyager", "juno", "perseverance"):
                self.assertNotIn(word, re.sub(r"//.*", "", eng), f"{f}: {word}")


class OtherActions(unittest.TestCase):
    def test_landing_descends_to_the_site_and_settles(self):
        for craft, date, place, body in (("apollo11.lm", "apollo11.pdi", "tranquility base", "moon"),
                                         ("perseverance.lander", "perseverance.landing-00:07", "perseverance.jezero landing site", "mars")):
            with self.subTest(craft=craft):
                comp = compiled(*one("landing", place, "surface", date, craft))
                a, moves = comp.actions["b1"], comp.spec["camera"]["moves"]
                self.assertEqual((a.action, a.body), ("landing", body))
                self.assertTrue(follows(comp.spec))
                self.assertIn("@", moves[-1]["to"]["target"], "it settles on the landing site")

    def test_flyby_follows_through_closest_approach(self):
        comp = compiled(*one("flyby", "moon", "body", "artemis1.closest_approach", "artemis1.orion"))
        a = comp.actions["b1"]
        self.assertEqual((a.action, a.body), ("flyby", "moon"))
        self.assertLess(a.span[0], "2022-11-21T12:57:00Z")
        self.assertGreater(a.span[1], "2022-11-21T12:57:00Z")
        self.assertEqual(len(follows(comp.spec)), 2)

    def test_orbit_insertion_burns_and_settles(self):
        comp = compiled(*one("orbit_insert", "moon", "body", "apollo11.loi", "apollo11.csm"))
        a = comp.actions["b1"]
        self.assertEqual((a.action, a.body), ("orbit_insert", "moon"))
        craft = next(L for L in comp.spec["layers"] if L["type"] == "spacecraft")
        self.assertEqual(len(craft["burns"]), 1, "the burn glows on the craft")
        orbit = compiled(*one("orbit", "jupiter", "system", "juno.observed_pass", "juno.juno")).actions["b1"]
        self.assertEqual(orbit.intro["distance"]["km"], round(3.4 * 3200000), "the whole orbit is framed, from its data")

    def test_departure_picks_the_leg_at_that_moment(self):
        out = compiled(*one("departure", "earth+moon", "system", "apollo8.tli", "apollo8.csm")).actions["b1"]
        home = compiled(*one("departure", "earth+moon", "system", "apollo8.tei", "apollo8.csm")).actions["b1"]
        self.assertEqual((out.body, home.body), ("earth", "moon"))
        mars = compiled(*one("departure", "earth", "inner", "mars_crewed_2040.departure", "mars_crewed_2040.crew_ship")).actions["b1"]
        self.assertEqual([c[2]["target"] for c in mars.camera], ["earth+mars"], "across the solar system: the whole leg")

    def test_long_journeys_move_by_narration_not_by_spinning_planets(self):
        for act, craft, date, place, frame in (("rover_drive", "perseverance.rover", "perseverance.landing", "perseverance.jezero landing site", "surface"),
                                               ("deep_space_departure", "voyager1.voyager1", "voyager1.saturn_flyby", "sun", "heliosphere"),
                                               ("transfer", "juice.juice", "juice.launch", "earth", "inner")):
            with self.subTest(act=act):
                comp = compiled(*one(act, place, frame, date, craft))
                a = comp.actions["b1"]
                self.assertEqual(a.strategy, "motion")
                craft_layer = next(L for L in comp.spec["layers"] if L["type"] == "spacecraft")
                self.assertEqual((craft_layer["motion"]["from_utc"], craft_layer["motion"]["to_utc"]), a.span)
                self.assertLessEqual(len(comp.spec["clock"].get("keys", [])), 2, "the universe clock is not run across years")

    def test_earth_to_asteroid(self):
        a = compiled(*one("transfer", "earth", "inner", "osiris_rex.launch", "osiris_rex.osiris_rex")).actions["b1"]
        self.assertEqual((a.action, a.body), ("transfer", "earth"))
        self.assertEqual(a.intro["target"], "earth+bennu")


class Inference(unittest.TestCase):
    def test_events_name_their_action(self):
        for name, act in (("launch", "liftoff"), ("landing", "landing"), ("pdi", "descent"), ("powered_descent", "descent"), ("loi", "orbit_insert"),
                          ("orbit_insertion", "orbit_insert"), ("dro_insertion", "orbit_insert"), ("tli", "departure"), ("tei", "departure"),
                          ("outbound_flyby", "flyby"), ("closest_approach", "flyby"), ("jupiter_flyby", "flyby"), ("undocking", "undocking"),
                          ("docking", "docking"), ("lander_separation", "separation"), ("impact", "impact"), ("splashdown", "reentry"),
                          ("free_return_burn", "trajectory_follow"), ("farthest_point", None)):
            self.assertEqual(event_action(name), act, name)
        self.assertEqual(event_action("anything", "flyby"), "flyby", "a dataset may declare the action of an event")

    def test_inferred_only_when_the_beat_shows_a_craft(self):
        text, n = one("", "earth", "body", "apollo11.launch", "")
        self.assertEqual(compiled(text, n).actions, {})
        text, n = one("", "launch complex 39a", "body", "apollo11.launch", "apollo11.csm")
        comp = compiled(text, n)
        self.assertEqual((comp.actions["b1"].action, comp.actions["b1"].source), ("liftoff", "event"))
        self.assertEqual(comp.spec["clock"]["keys"][0]["utc"], "1969-07-16T13:32:00Z", "an inferred action keeps the beat's own date as its start")

    def test_old_camera_moves_still_mean_camera_moves(self):
        for move in ("push_in", "pull_out", "hold"):
            comp = compiled(*one(move, "moon", "body", "apollo11.loi", ""))
            self.assertEqual(comp.actions, {}, move)
        comp = compiled(*one("orbit", "moon", "body", "apollo11.loi", ""))
        self.assertEqual(comp.actions, {})
        self.assertTrue(any(m["to"].get("orbit_deg_per_s") for m in comp.spec["camera"]["moves"]) or comp.spec["camera"]["start"].get("orbit_deg_per_s"))


class MissingData(unittest.TestCase):
    def test_an_asked_action_without_its_data_is_an_error(self):
        rep = check_csv(*one("liftoff", "earth", "body", "apollo11.launch", "")[:1], duration=10, catalog=Catalog(index=IDX))
        self.assertFalse(rep.ok)
        self.assertIn("Launch visual incomplete: no spacecraft resolved", rep.to_text())
        rep = check_csv(*one("liftoff", "jupiter", "system", "juno.observed_pass", "juno.juno")[:1], duration=10, catalog=Catalog(index=IDX))
        self.assertIn("Launch visual incomplete", rep.to_text())
        self.assertIn("no launch track from a surface site", rep.to_text())
        rep = check_csv(*one("landing", "jupiter", "system", "juno.observed_pass", "juno.juno")[:1], duration=10, catalog=Catalog(index=IDX))
        self.assertIn("Landing visual incomplete", rep.to_text())
        rep = check_csv(*one("surface_traverse", "earth", "body", "iss.observed_pass", "iss.iss")[:1], duration=10, catalog=Catalog(index=IDX))
        self.assertIn("Surface drive visual incomplete", rep.to_text())

    def test_an_inferred_action_without_its_data_warns_and_shows_a_plain_shot(self):
        rows = [dict(beat="b1", row="beat", start="0", mode="map", place="earth", frame="body", date="iss.observed_pass", text="x"),
                dict(beat="b1", row="layer", t="0.3", type="craft", id="iss.iss")]
        rep = check_csv(csv_of(rows), duration=10, catalog=Catalog(index=IDX))
        self.assertTrue(rep.ok, rep.to_text())
        self.assertEqual(rep.compiled.actions, {})

    def test_check_plan_lists_the_visual_actions(self):
        rep = check_csv(*one("liftoff", "launch complex 39a", "body", "apollo11.launch", "apollo11.csm")[:1], duration=10, catalog=Catalog(index=IDX))
        text = rep.to_text()
        self.assertIn("Visual actions:", text)
        self.assertIn("b1 → liftoff: apollo11.csm lifts off from earth@-80.604,28.608", text)
        self.assertEqual(len(ACTIONS), 25)


class SixMissions(unittest.TestCase):
    def test_every_production_sample_resolves_its_actions_cleanly(self):
        from pakmap.words import estimate_words

        S = HERE / "starmap" / "samples"
        want = {"apollo11": {"orbit_insert", "departure", "landing"}, "apollo8": {"orbit_insert", "departure"},
                "apollo13": {"orbit_insert", "trajectory_follow"}, "artemis1": {"departure", "flyby"},
                "chandrayaan3": {"liftoff", "separation", "departure", "landing"}, "change4": {"departure", "orbit_insert", "landing"}}
        for pid, acts in want.items():
            with self.subTest(pid=pid):
                words = estimate_words((S / f"{pid}_script.txt").read_text(encoding="utf-8"), words_per_second=2.5)
                rep = check_csv((S / f"{pid}_beats.csv").read_text(encoding="utf-8"), words, media=json.loads((S / f"{pid}_media.json").read_text()))
                self.assertTrue(rep.ok, rep.to_text())
                self.assertEqual({a.action for a in rep.compiled.actions.values()}, acts)
                self.assertFalse([w for w in rep.warnings if "visual incomplete" in w])


if __name__ == "__main__":
    unittest.main()
