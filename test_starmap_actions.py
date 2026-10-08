"""Visual actions: a resolved event becomes something the viewer SEES -- a liftoff, a landing, a flyby, an orbit insertion, a
departure, a rover's drive -- through the generic camera and the clock or a narration-paced motion. The camera HOLDS on the
stretch of path the beat shows (worked out from the data) and the craft moves through it with a tracking box; a camera move
only where it has a reason. One code path for every mission: no mission is named in the action logic, and missing data is
reported, never faked."""

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


def shots(spec):
    return [spec["camera"]["start"]] + [m["to"] for m in spec["camera"]["moves"]]


def held(spec):
    """The path frames: shots that hold on a stretch of a craft's path (a creep in to the same frame counts once)."""
    out = []
    for s in shots(spec):
        if s.get("path") and not (out and {**out[-1]["path"], "fit": 0} == {**s["path"], "fit": 0}):
            out.append(s)
    return out


def tracker(spec):
    return next(L for L in spec["layers"] if L["type"] == "tracker")


class Liftoff(unittest.TestCase):
    def test_apollo_11_lifted_off_from_earth(self):
        """The acceptance case: the whole climb framed and held, the craft on its pad, the clock through the ascent, the
        tracked rocket rising across the still frame -- no chase, no extra moves."""
        comp = compiled(*one("liftoff", "launch complex 39a", "body", "apollo11.launch", "apollo11.csm", "apollo11.earth_orbit"))
        a = comp.actions["b1"]
        self.assertEqual((a.action, a.craft, a.body, a.site), ("liftoff", "apollo11.csm", "earth", (-80.604, 28.608)))
        self.assertEqual(a.span, ("1969-07-16T13:31:52Z", "1969-07-16T13:43:49Z"), "from just before liftoff to the end of the ascent track")
        spec = comp.spec
        start = spec["camera"]["start"]
        frame = {"trajectory": "apollo11_csm", "from_utc": "1969-07-16T13:32:00Z", "to_utc": "1969-07-16T13:43:49Z", "fit": 1.35,
                 "ref_utc": "1969-07-16T13:37:54Z"}
        self.assertEqual(start["path"], frame, "the whole ascent in one frame, worked out once (mid-climb)")
        self.assertEqual(spec["camera"]["moves"], [], "no push_in, no follow: the rocket moves through a stable frame")
        self.assertGreater(spec["camera"]["drift_deg_per_s"], 0, "and the drift keeps the shot alive")
        self.assertEqual(follows(spec), [], "never a chase")
        self.assertNotIn("still", spec["camera"], "the drift never rests")
        tr = tracker(spec)
        self.assertEqual((tr["craft"], tr["trajectory"], tr["altitude_of"], tr["readouts"], tr["approx"]),
                         ("apollo11.csm", "apollo11_csm", "earth", ["altitude"], True), "tracked, with an honest ≈ altitude (no speed: drawn path)")
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
                self.assertEqual(held(comp.spec)[0]["path"]["trajectory"], comp.actions["b1"].trajectory)
                self.assertEqual(len(held(comp.spec)), 1, "one frame of the climb, crept into; nothing chases the craft")
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
                h = held(comp.spec)
                self.assertEqual(len(h), 1, "one held frame of the whole descent")
                self.assertTrue(a.span[0] <= h[0]["path"]["from_utc"] < h[0]["path"]["to_utc"] < a.span[1], "down to touchdown, then it rests")
                self.assertLessEqual(len(moves), 1, "at most the glide into it")
                self.assertEqual(tracker(comp.spec)["altitude_of"], body, "the altitude counts down above the body it lands on")

    def test_flyby_follows_through_closest_approach(self):
        comp = compiled(*one("flyby", "moon", "body", "artemis1.closest_approach", "artemis1.orion"))
        a = comp.actions["b1"]
        self.assertEqual((a.action, a.body), ("flyby", "moon"))
        self.assertLess(a.span[0], "2022-11-21T12:57:00Z")
        self.assertGreater(a.span[1], "2022-11-21T12:57:00Z")
        h = held(comp.spec)
        self.assertEqual((len(h), h[0]["path"].get("up")), (1, "plane"), "the bend of the pass, seen from above its plane, held")
        self.assertEqual((h[0]["path"]["from_utc"], h[0]["path"]["to_utc"]), a.span)

    def test_orbit_insertion_burns_and_settles(self):
        comp = compiled(*one("orbit_insert", "moon", "body", "apollo11.loi", "apollo11.csm"))
        a = comp.actions["b1"]
        self.assertEqual((a.action, a.body), ("orbit_insert", "moon"))
        craft = next(L for L in comp.spec["layers"] if L["type"] == "spacecraft")
        self.assertEqual(len(craft["burns"]), 1, "the burn glows on the craft")
        self.assertEqual(held(comp.spec)[0]["path"]["up"], "plane", "the orbit seen from above its plane: going round is across the screen")
        orbit = compiled(*one("orbit", "jupiter", "system", "juno.observed_pass", "juno.juno")).actions["b1"]
        self.assertEqual((orbit.intro["path"]["from_utc"], orbit.intro["path"]["to_utc"]), orbit.span, "the stretch of orbit the beat shows")

    def test_departure_picks_the_leg_at_that_moment(self):
        out = compiled(*one("departure", "earth+moon", "system", "apollo8.tli", "apollo8.csm")).actions["b1"]
        home = compiled(*one("departure", "earth+moon", "system", "apollo8.tei", "apollo8.csm")).actions["b1"]
        self.assertEqual((out.body, home.body), ("earth", "moon"))
        mars = compiled(*one("departure", "earth", "inner", "mars_crewed_2040.departure", "mars_crewed_2040.crew_ship")).actions["b1"]
        self.assertEqual(len(mars.camera), 1, "one move, with a reason: pull back to where it is going")
        leg = mars.camera[0][2]["path"]
        self.assertEqual((leg["from_utc"], leg["to_utc"], leg["up"]), ("2039-11-01T00:00:00Z", "2040-06-01T00:00:00Z", "plane"), "the whole leg")
        self.assertEqual((out.camera, home.camera), ([], []), "Earth to the Moon: the departure is held, no move")
        self.assertEqual(mars.dest, "mars")

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
                clk = next((L for L in comp.spec["layers"] if L["type"] == "mission_clock"), None)
                if clk is not None:
                    m = clk["motions"][0]
                    self.assertEqual((m["from_utc"], m["to_utc"], m["t0"], m["t1"]), (*a.span, craft_layer["motion"]["t0"], craft_layer["motion"]["t1"]),
                                     "the date on screen follows the craft, never launch day while it arrives")

    def test_earth_to_asteroid(self):
        a = compiled(*one("transfer", "earth", "inner", "osiris_rex.launch", "osiris_rex.osiris_rex")).actions["b1"]
        self.assertEqual((a.action, a.body), ("transfer", "earth"))
        self.assertEqual((a.intro["path"]["from_utc"], a.intro["path"]["to_utc"]), a.span, "the whole leg, held")
        self.assertEqual(a.dest, "bennu")


class CameraRules(unittest.TestCase):
    """The camera moves only where it is needed; tracking follows the subject instead."""

    def test_a_jump_between_missions_is_a_cut_behind_the_time_jump_card(self):
        rows = [dict(beat="plan", row="plan", date="2026-10-08"),
                dict(beat="b1", row="beat", start="0", mode="map", type="landing", place="tranquility base", frame="surface", date="apollo11.pdi", text="x"),
                dict(beat="b1", row="layer", t="0.3", type="craft", id="apollo11.lm"),
                dict(beat="b2", row="beat", start="10", mode="map", type="landing", place="perseverance.jezero landing site", frame="surface",
                     date="perseverance.landing-00:07", text="y"),
                dict(beat="b2", row="layer", t="10.3", type="craft", id="perseverance.lander")]
        spec = compiled(csv_of(rows), 20.0).spec
        into = [m for m in spec["camera"]["moves"] if m["t"] == 10.0]
        self.assertEqual(into[0]["dur"], 0.0, "no sweep from the Moon to Mars: a cut while the map is dark")
        self.assertTrue(all(m["to"].get("path", {}).get("trajectory") == into[0]["to"]["path"]["trajectory"] for m in into), "then only a creep in")
        self.assertIn(10.0, [L["at"] for L in spec["layers"] if L["type"] == "time_jump"])

    def test_a_craft_carrying_on_into_the_next_beat_stays_one_object(self):
        """It used to fade out and a second copy fade in, leaving 0.3 s with no craft, tracker or path mid-pull_out."""
        rows = [dict(beat="plan", row="plan"),
                dict(beat="b1", row="beat", start="0", mode="map", type="liftoff", place="launch complex 39a", frame="body", date="apollo11.launch", text="x"),
                dict(beat="b1", row="layer", t="0.3", type="craft", id="apollo11.csm"), dict(beat="b1", row="layer", t="0.3", type="path", id="apollo11.earth_orbit"),
                dict(beat="b2", row="beat", start="10", mode="map", type="departure", place="earth+moon", frame="system", date="apollo11.tli", text="y"),
                dict(beat="b2", row="layer", t="10.3", type="craft", id="apollo11.csm"), dict(beat="b2", row="layer", t="10.3", type="path", id="apollo11.translunar_coast")]
        spec = compiled(csv_of(rows), 20.0).spec
        for ty in ("spacecraft", "tracker"):
            a, b = [L for L in spec["layers"] if L["type"] == ty]
            self.assertEqual((a["end"], a["fade_out"], b["start"], b["fade_in"]), (10.0, 0, 10.0, 0), f"{ty}: handed over at one moment, no fade, no gap")
        old, new = [L for L in spec["layers"] if L["type"] == "trajectory" and L.get("start") is not None]
        self.assertEqual((new["start"], old["end"], old["fade_out"]), (10.0, 11.0, 1.0), "the old path fades out while the new one draws in")

    def test_tracking_rides_on_every_craft_and_numbers_only_during_an_action(self):
        rows = [dict(beat="plan", row="plan", date="2026-10-08"),
                dict(beat="b1", row="beat", start="0", mode="map", place="earth+moon", frame="system", date="1969-07-17T12:00:00Z", text="x"),
                dict(beat="b1", row="layer", t="0.3", type="craft", id="apollo11.csm", label="COLUMBIA")]
        spec = compiled(csv_of(rows), 10.0).spec
        tr = [L for L in spec["layers"] if L["type"] == "tracker"]
        self.assertEqual([(t["label"], t["readouts"]) for t in tr], [("COLUMBIA", [])], "a craft that is just travelling: its name, no HUD")
        craft = next(L for L in spec["layers"] if L["type"] == "spacecraft")
        self.assertEqual(craft["label"], "", "the name lives in the tracking box")
        self.assertEqual({m["to"]["target"] for m in spec["camera"]["moves"]}, {"earth+moon"}, "only a creep in the same view: the craft is not followed")
        self.assertNotIn("still", spec["camera"])

    def test_a_quiet_beat_creeps_a_little_whatever_its_length(self):
        for length in (8.0, 30.0):
            spec = compiled(*one("", "moon", "body", "apollo11.loi", "", length=length)).spec
            self.assertNotIn("still", spec["camera"], "the drift never rests")
            k = spec["camera"]["moves"][-1]["to"]["fill"] / spec["camera"]["start"]["fill"]
            self.assertTrue(1.0 < k <= 1.25, f"a slow push-in, never more than a quarter ({k})")

    def test_framings_vary_by_beat_but_the_same_csv_gives_the_same_video(self):
        els = set()
        for bid in ("b1", "launch", "liftoff_a", "x7"):
            text, n = one("liftoff", "launch complex 39a", "body", "apollo11.launch", "apollo11.csm")
            text = text.replace("\nb1,", f"\n{bid},")
            els.add(compiled(text, n).spec["camera"]["start"]["el_deg"])
        self.assertGreater(len(els), 1, "not every launch is shot from the same height")
        text, n = one("liftoff", "launch complex 39a", "body", "apollo11.launch", "apollo11.csm")
        self.assertEqual(json.dumps(compiled(text, n).spec, sort_keys=True), json.dumps(compiled(text, n).spec, sort_keys=True))

    def test_the_frame_shows_what_the_clock_shows(self):
        from pakmap.words import estimate_words

        S = HERE / "starmap" / "samples"
        words = estimate_words((S / "chandrayaan3_script.txt").read_text(encoding="utf-8"), words_per_second=2.5)
        comp = check_csv((S / "chandrayaan3_beats.csv").read_text(encoding="utf-8"), words,
                         media=json.loads((S / "chandrayaan3_media.json").read_text())).compiled
        keys = comp.spec["clock"]["keys"]
        for m in comp.spec["camera"]["moves"]:
            pth = m["to"].get("path")
            if not pth:
                continue
            b = next(x for x in read_plan((S / "chandrayaan3_beats.csv").read_text(encoding="utf-8"), words).beats if x.start - 1e-3 <= m["t"] + m["dur"] <= x.end + 1e-3)
            at = [k["utc"] for k in keys if b.start - 1e-3 <= k["t"] <= b.end + 1e-3]
            self.assertLessEqual(pth["from_utc"], min(at), f"{b.id}: the frame starts where the clock does (or before)")
        sep = next(m["to"]["path"] for m in comp.spec["camera"]["moves"] if m["to"].get("path") and m["to"]["path"]["from_utc"].startswith("2023-07-14T09:21"))
        self.assertEqual((sep["to_utc"], sep["up"]), ("2023-07-31T18:30:00Z", "plane"), "seventeen days of widening orbits, framed whole from above")


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


class StagedTiming(unittest.TestCase):
    """A departure's burn and coast get their own share of the beat (presentation pacing); the clock stays the true date of
    where the craft is, and the camera plan does not change. Actions without stages keep exactly the old clock."""

    ROWS = [dict(beat="plan", row="plan"),
            dict(beat="b1", row="beat", start="0", mode="map", type="liftoff", place="launch complex 39a", frame="body", date="apollo11.launch", text="x"),
            dict(beat="b1", row="layer", t="0.3", type="craft", id="apollo11.csm"), dict(beat="b1", row="layer", t="0.3", type="path", id="apollo11.earth_orbit"),
            dict(beat="b2", row="beat", start="10", mode="map", type="departure", place="earth+moon", frame="system", date="apollo11.tli", text="y"),
            dict(beat="b2", row="layer", t="10.3", type="craft", id="apollo11.csm"), dict(beat="b2", row="layer", t="10.3", type="path", id="apollo11.translunar_coast")]

    def both(self, rows=None, length=20.0):
        """(compiled with stages, compiled with every action's stages removed: the behaviour before stages existed)"""
        from unittest import mock

        import starmap.compile as C

        text = csv_of(rows or self.ROWS)
        staged = compiled(text, length)
        real = C.resolve_actions

        def unstaged(*a, **kw):
            acts, errs, warns = real(*a, **kw)
            for x in acts.values():
                x.stages = []
            return acts, errs, warns
        with mock.patch.object(C, "resolve_actions", unstaged):
            plain = compiled(text, length)
        return staged, plain

    def test_without_stages_the_clock_is_exactly_the_old_one(self):
        staged, plain = self.both()
        a = staged.actions["b2"]
        boundary = a.stages[0].until
        self.assertEqual([k for k in staged.spec["clock"]["keys"] if k["utc"] != boundary], plain.spec["clock"]["keys"],
                         "the only difference is the stage key")
        # and every other action type in every shipped sample: identical clocks (no stages anywhere else)
        S = HERE / "starmap" / "samples"
        from pakmap.words import estimate_words
        for pid in ("apollo8", "apollo11", "apollo13", "artemis1", "chandrayaan3", "change4"):
            with self.subTest(pack=pid):
                words = estimate_words((S / f"{pid}_script.txt").read_text(encoding="utf-8"), words_per_second=2.5)
                text = (S / f"{pid}_beats.csv").read_text(encoding="utf-8")
                media = json.loads((S / f"{pid}_media.json").read_text())
                comp = check_csv(text, words, media=media).compiled
                staged_beats = {k for k, x in comp.actions.items() if x.stages}
                self.assertTrue(all(comp.actions[k].action in ("departure", "flyby") for k in staged_beats), "only departures and flybys have stages")

    def test_a_departure_gives_its_burn_the_first_third_then_coasts_to_the_same_end(self):
        staged, plain = self.both()
        a = staged.actions["b2"]
        self.assertEqual([x.name for x in a.stages], ["burn", "coast"])
        burn, coast = a.stages
        self.assertEqual((burn.until, coast.until), (a.burns[0][1], a.span[1]), "the burn ends when its glow does; the coast at the span end")
        keys = staged.spec["clock"]["keys"]
        b2 = [k for k in keys if k["t"] >= 10.0]
        self.assertEqual(len(b2), 3, "start, the burn/coast boundary, end")
        self.assertAlmostEqual(b2[1]["t"], 10.0 + 0.35 * (20.0 - 0.05 - 10.0), places=2, msg="the burn has the first 35% of the beat")
        self.assertEqual(b2[1]["utc"], burn.until, "the clock reads the true date at the boundary")
        self.assertEqual(b2[-1]["utc"], plain.spec["clock"]["keys"][-1]["utc"], "the departure still reaches its original final date")
        self.assertEqual(b2[-1]["utc"], a.span[1])

    def test_time_never_runs_backwards_and_stages_stay_inside_the_beat_and_span(self):
        from starmap.catalog import iso_seconds

        staged, _ = self.both()
        keys = staged.spec["clock"]["keys"]
        for x, y in zip(keys, keys[1:]):
            self.assertGreater(y["t"], x["t"])
            self.assertGreaterEqual(iso_seconds(x["utc"], y["utc"]), 0, f"{x} -> {y}")
        a = staged.actions["b2"]
        lo = a.span[0]
        for stg in a.stages:
            self.assertGreater(iso_seconds(lo, stg.until), 0, "contiguous, in order, never zero length")
            lo = stg.until
        self.assertEqual(lo, a.span[1], "the last stage ends at the span end")

    def test_the_camera_plan_is_identical_with_or_without_stages(self):
        staged, plain = self.both()
        self.assertEqual(json.dumps(staged.spec["camera"], sort_keys=True), json.dumps(plain.spec["camera"], sort_keys=True))
        others = {k: v for k, v in staged.spec.items() if k not in ("clock",)}
        self.assertEqual(json.dumps(others, sort_keys=True), json.dumps({k: v for k, v in plain.spec.items() if k != "clock"}, sort_keys=True),
                         "nothing but the clock changes: layers, trajectories, world")


class CrossBeatStages(unittest.TestCase):
    """A flyby's stages pace its own continuous clock segment (its beat's start key to the next key), crossing undated
    beats but never footage, a time jump or the segment before; framing uses the stage-free clock, so the camera plan never
    changes. A beat whose time would 'run on' to the very same date ends on its action's span end instead."""

    def both(self, rows, length):
        return StagedTiming.both(self, rows, length)

    @staticmethod
    def beat(bid, start, place, frame, date="", mode="map", typ=""):
        return dict(beat=bid, row="beat", start=str(start), mode=mode, type=typ, place=place, frame=frame, date=date, text=bid)

    @staticmethod
    def craft(bid, t):
        return dict(beat=bid, row="layer", t=str(t), type="craft", id="voyager1.voyager1")

    def keys_at(self, comp, a, b):
        return [k for k in comp.spec["clock"]["keys"] if a - 1e-6 <= k["t"] <= b + 1e-6]

    def test_a_flyby_paces_its_segment_across_an_undated_beat_and_never_touches_the_one_before(self):
        rows = [dict(beat="plan", row="plan"),
                self.beat("b0", 0, "sun", "solar", "voyager1.launch"), self.craft("b0", 0.3),
                self.beat("b1", 6, "jupiter", "system", "voyager1.jupiter_flyby", typ="flyby"), self.craft("b1", 6.3),
                self.beat("b2", 10, "sun", "solar"), self.craft("b2", 10.3),                    # undated: time runs through it
                self.beat("b3", 20, "sun", "solar", "voyager1.saturn_flyby"), self.craft("b3", 20.3)]
        staged, plain = self.both(rows, 28.0)
        a = staged.actions["b1"]
        self.assertEqual([s.name for s in a.stages], ["approach", "departure"])
        self.assertEqual(self.keys_at(staged, 0, 6), self.keys_at(plain, 0, 6), "the segment before is never rewritten")
        new = [k for k in staged.spec["clock"]["keys"] if k not in plain.spec["clock"]["keys"]]
        self.assertEqual(len(new), 1, "one boundary: the end of the pass, then the onward transit")
        self.assertEqual(new[0]["utc"], a.span[1], "the boundary is exactly the stage's own mission moment")
        self.assertTrue(10.0 < new[0]["t"] < 20.0, f"it falls inside the undated beat b2 ({new[0]['t']}): stages cross ordinary beats")
        from starmap.catalog import iso_seconds
        ks = staged.spec["clock"]["keys"]
        self.assertTrue(all(iso_seconds(x["utc"], y["utc"]) >= 0 and y["t"] > x["t"] for x, y in zip(ks, ks[1:])), "time never runs back")
        self.assertEqual(json.dumps(staged.spec["camera"], sort_keys=True), json.dumps(plain.spec["camera"], sort_keys=True),
                         "framing uses the stage-free clock: the camera plan is unchanged")

    def test_stages_stop_at_footage_and_at_a_time_jump(self):
        footage = [dict(beat="plan", row="plan"),
                   self.beat("b1", 0, "jupiter", "system", "voyager1.jupiter_flyby", typ="flyby"), self.craft("b1", 0.3),
                   dict(beat="b2", row="beat", start="8", mode="footage", text="b2"),
                   dict(beat="b2", row="clip", asset="file:x.jpg"),
                   self.beat("b3", 14, "sun", "solar", "voyager1.saturn_flyby"), self.craft("b3", 14.3)]
        jump = [dict(beat="plan", row="plan"),
                self.beat("b1", 0, "jupiter", "system", "voyager1.jupiter_flyby", typ="flyby"), self.craft("b1", 0.3),
                self.beat("b2", 10, "earth", "body", "apollo11.launch")]
        for name, rows, cut in (("footage", footage, 8.0), ("time jump", jump, 10.0 - 0.02)):
            with self.subTest(boundary=name):
                staged, plain = self.both(rows, 20.0)
                self.assertTrue(staged.actions["b1"].stages)
                new = [k for k in staged.spec["clock"]["keys"] if k not in plain.spec["clock"]["keys"]]
                self.assertTrue(all(k["t"] < cut - 1e-6 for k in new), f"no stage key at or past the {name} ({new})")
                self.assertEqual([k for k in staged.spec["clock"]["keys"] if k["t"] >= cut - 1e-6],
                                 [k for k in plain.spec["clock"]["keys"] if k["t"] >= cut - 1e-6], f"from the {name} on, nothing changes")

    def test_a_beat_that_would_stand_still_at_one_date_runs_through_its_action(self):
        rows = [dict(beat="plan", row="plan"),
                self.beat("b0", 0, "sun", "solar", "voyager1.jupiter_flyby"), self.craft("b0", 0.3),     # time runs in from Jupiter
                self.beat("b1", 10, "saturn", "system", "voyager1.saturn_flyby", typ="flyby"), self.craft("b1", 10.3),
                self.beat("b2", 20, "sun", "solar", "voyager1.saturn_flyby"), self.craft("b2", 20.3)]   # the very same date
        comp = compiled(csv_of(rows), 30.0)
        a, keys = comp.actions["b1"], comp.spec["clock"]["keys"]
        self.assertEqual([(k["t"], k["utc"]) for k in keys if 10.0 <= k["t"] <= 20.0],
                         [(10.0, "1980-11-12T23:46:00Z"), (19.95, a.span[1]), (20.0, a.span[1])],
                         "Saturn's closest approach, then the end of the pass; the next beat carries on from there (never back)")

    def test_no_action_no_invented_end(self):
        rows = [dict(beat="plan", row="plan"),
                self.beat("b1", 0, "saturn", "system", "voyager1.saturn_flyby"),          # a date, but no craft: no action
                self.beat("b2", 10, "sun", "solar", "voyager1.saturn_flyby")]
        comp = compiled(csv_of(rows), 20.0)
        self.assertNotIn("b1", comp.actions)
        self.assertEqual({k["utc"] for k in comp.spec["clock"]["keys"] if k["t"] <= 10.0}, {"1980-11-12T23:46:00Z"},
                         "without an action span the beat keeps its date: nothing is made up")
