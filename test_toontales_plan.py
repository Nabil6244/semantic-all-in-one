"""Toon Tales plan checker + action library (docs/toontales/PLAN.md step 4). Pure Python, no Blender."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

from toontales.plan import check as C
from toontales.plan import schema as S

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "toontales" / "library"))
import actions as A  # noqa: E402

SAMPLE = ROOT / "toontales" / "stories" / "moon_hoax" / "plan.json"   # passes every rule, incl. places + retention
M = {"arm_len": 0.567, "leg_len": 0.84, "shoulder_z": 1.22, "hip_z": 0.84, "head_r": 0.27, "body_w": 0.44}


def shot(text="Walt sold Pip a cart of rocks.", speaker="narrator", camera="medium", cast=None, **kw):
    s = {"beat": "concept", "speaker": speaker, "text": text, "set": "mine", "camera": camera, "move": "push",
         "cast": cast if cast is not None else [{"id": "walt", "mark": "A", "acts": [{"do": "point", "at": 0.2}]}]}
    s.update(kw)
    return s


def plan(*shots):
    return {"id": "t", "title": "Test", "topic": "test topic", "cast": ["walt", "pip"], "shots": list(shots)}


def rules(r, level=None):
    return {(x["rule"], x["level"]) if level is None else x["rule"] for x in r["issues"]
            if level is None or x["level"] == level}


class SampleStory(unittest.TestCase):
    def test_sample_plan_is_clean(self):
        r = C.check(S.load_plan(SAMPLE), fix=False)
        self.assertTrue(r["ok"], C.format_report(r))
        self.assertEqual(r["issues"], [], C.format_report(r))
        self.assertTrue(S.STORY_MIN <= r["plan"]["est_total"] <= S.STORY_MAX)

    def test_check_does_not_change_the_input(self):
        p = plan(shot(), shot())
        before = copy.deepcopy(p)
        C.check(p, fix=True)
        self.assertEqual(p, before)


class ShotLength(unittest.TestCase):
    LONG = "Walt kept the old tile hidden in his back pocket and the real price locked in his head all day."

    def test_long_shot_is_an_error_without_fix(self):
        r = C.check(plan(shot(self.LONG)), fix=False)
        self.assertFalse(r["ok"])
        self.assertIn(("shot_len", "error"), rules(r))

    def test_long_shot_splits_at_a_natural_break(self):
        r = C.check(plan(shot(self.LONG)), fix=True)
        a, b = r["plan"]["shots"][:2]
        self.assertTrue(b["text"].startswith("and "), (a["text"], b["text"]))
        self.assertEqual(a["text"] + " " + b["text"], self.LONG)
        self.assertNotEqual(a["camera"], b["camera"])
        self.assertEqual([s["id"] for s in r["plan"]["shots"]], ["s01", "s02"])
        for s in r["plan"]["shots"]:
            self.assertLessEqual(S.shot_dur(s, *S.load_cast()), S.SHOT_MAX)

    def test_split_without_punctuation_breaks_before_a_preposition(self):
        cut = C._split_point("In 1849, a miner named Pip struck gold on his very first swing.")
        self.assertEqual("In 1849, a miner named Pip struck gold on his very first swing."[cut:], "on his very first swing.")

    def test_short_shot_merges_into_next_same_speaker(self):
        r = C.check(plan(shot("Black line."), shot("Fool's gold, again and again.", camera="close")), fix=True)
        self.assertEqual(len(r["plan"]["shots"]), 1)
        self.assertEqual(r["plan"]["shots"][0]["text"], "Black line. Fool's gold, again and again.")

    def test_real_voice_too_long_is_an_error_not_a_split(self):
        r = C.check(plan(shot(dur=4.2)), fix=True)
        self.assertIn(("shot_len", "error"), rules(r))
        self.assertEqual(len(r["plan"]["shots"]), 1)

    def test_estimate_matches_the_narrator_pace(self):
        cast, nar = S.load_cast()
        d = S.estimate_dur("In 1849, Pip struck gold on his very first swing.", S.voice_of("narrator", cast, nar))
        self.assertTrue(2.4 < d < 3.5, d)


class Library(unittest.TestCase):
    def test_action_typo_is_repaired(self):
        s = shot(cast=[{"id": "walt", "mark": "A", "acts": [{"do": "celebrat", "at": 0.1}]}])
        r = C.check(plan(s), fix=True)
        self.assertEqual(r["plan"]["shots"][0]["cast"][0]["acts"][0]["do"], "celebrate")
        self.assertIn(("library", "fixed"), rules(r))

    def test_unknown_action_is_an_error(self):
        s = shot(cast=[{"id": "walt", "mark": "A", "acts": [{"do": "moonwalk_backflip", "at": 0.1}]}])
        r = C.check(plan(s), fix=True)
        self.assertIn(("library", "error"), rules(r))

    def test_face_typo_is_repaired(self):
        s = shot(cast=[{"id": "walt", "mark": "A", "eyes": "dizy", "acts": [{"do": "bonk", "at": 0.1}]}])
        r = C.check(plan(s), fix=True)
        self.assertEqual(r["plan"]["shots"][0]["cast"][0]["eyes"], "dizzy")

    def test_every_action_runs_and_walks_carry_position(self):
        for name, (fn, dur, moves, about) in A.ACTIONS.items():
            for k in range(11):
                st = A.state_at(name, dur * k / 10, dur, M, {})
                self.assertTrue(all(len(j) == 3 for arm in st["arm"] for j in arm), name)
                self.assertEqual(len(st["foot"]), 2, name)
            self.assertTrue(about, name)
        self.assertEqual(A.final_root("walk", 1.6, M, {"to": [1.2, -0.5]}), (1.2, -0.5))
        self.assertEqual(A.final_root("jump", 0.9, M, {}), (0.0, 0.0))


class Staging(unittest.TestCase):
    def test_unknown_set_mark_and_cast_are_errors(self):
        r = C.check(plan(shot(set="moon_base")), fix=True)
        self.assertIn(("set_known", "error"), rules(r))
        r = C.check(plan(shot(cast=[{"id": "walt", "mark": "Z9", "acts": [{"do": "point", "at": 0}]}])), fix=True)
        self.assertIn(("set_known", "error"), rules(r))
        r = C.check(plan(shot(cast=[{"id": "rick", "mark": "A", "acts": [{"do": "point", "at": 0}]}])), fix=True)
        self.assertIn(("cast_known", "error"), rules(r))

    def test_speaker_missing_from_shot_is_added(self):
        r = C.check(plan(shot("Trust me, son.", speaker="walt",
                              cast=[{"id": "pip", "mark": "B", "acts": [{"do": "shrug", "at": 0}]}])), fix=True)
        ids = {c["id"]: c["mark"] for c in r["plan"]["shots"][0]["cast"]}
        self.assertIn("walt", ids)
        self.assertNotEqual(ids["walt"], "B")

    def test_offscreen_speaker_is_allowed(self):
        r = C.check(plan(shot("Trust me, son.", speaker="walt", offscreen=True,
                              cast=[{"id": "pip", "mark": "B", "acts": [{"do": "shrug", "at": 0}]}])), fix=False)
        self.assertNotIn("speaker_seen", rules(r, "error"))

    def test_shared_mark_is_resolved(self):
        cast = [{"id": "walt", "mark": "A", "acts": [{"do": "point", "at": 0}]},
                {"id": "pip", "mark": "A", "acts": [{"do": "shock", "at": 0}]}]
        r = C.check(plan(shot(cast=cast)), fix=True)
        marks = [c["mark"] for c in r["plan"]["shots"][0]["cast"]]
        self.assertEqual(len(set(marks)), 2)
        self.assertFalse(C.check(plan(shot(cast=cast)), fix=False)["ok"])

    def test_text_prop_needs_text(self):
        r = C.check(plan(shot(props=[{"type": "sign", "spot": "wall_r"}])), fix=True)
        self.assertIn(("props", "error"), rules(r))
        r = C.check(plan(shot(props=[{"type": "sign", "text": "SURE THING", "spot": "wall_r"}])), fix=True)
        self.assertNotIn("props", rules(r, "error"))


class Rhythm(unittest.TestCase):
    def test_same_camera_twice_is_changed(self):
        r = C.check(plan(shot(camera="close"), shot("Pip paid in coins.", camera="close")), fix=True)
        a, b = r["plan"]["shots"]
        self.assertNotEqual(a["camera"], b["camera"])

    def test_shot_where_nothing_happens_gets_a_gesture(self):
        s = shot("Walt explained the deal slowly.", speaker="walt",
                 cast=[{"id": "walt", "mark": "A", "acts": [{"do": "idle", "at": 0}]}])
        r = C.check(plan(s), fix=True)
        self.assertIn(("visual", "fixed"), rules(r))
        self.assertIn("explain", [a["do"] for a in r["plan"]["shots"][0]["cast"][0]["acts"]])
        self.assertFalse(C.check(plan(s), fix=False)["ok"])

    def test_long_still_stretch_gets_a_nod(self):
        s = shot("Pip stared at the cart for a very long while.",
                 cast=[{"id": "pip", "mark": "B", "acts": [{"do": "shock", "at": 0.0}]}])
        r = C.check(plan(s), fix=True)
        self.assertIn(("still", "fixed"), rules(r))
        self.assertLessEqual(C._still_gap(C._acts(r["plan"]["shots"][0]), 3.0), S.STILL_MAX)

    def test_long_action_counts_as_movement(self):
        acts = [("walt", {"do": "explain", "at": 0.0})]
        self.assertLess(C._still_gap(acts, 2.6), S.STILL_MAX)

    def test_action_outside_shot_is_pulled_in(self):
        s = shot(cast=[{"id": "walt", "mark": "A", "acts": [{"do": "point", "at": 9.0}]}])
        r = C.check(plan(s), fix=True)
        at = r["plan"]["shots"][0]["cast"][0]["acts"][0]["at"]
        self.assertLess(at, S.shot_dur(r["plan"]["shots"][0], *S.load_cast()))

    def test_dissolve_only_on_time_jumps(self):
        r = C.check(plan(shot(), shot("Next morning, Pip woke up rich.", camera="wide", transition="dissolve")), fix=True)
        self.assertEqual(r["plan"]["shots"][1]["transition"], "cut")
        r = C.check(plan(shot(), shot("Next morning, Pip woke up rich.", camera="wide", transition="dissolve",
                                      time_jump=True)), fix=True)
        self.assertEqual(r["plan"]["shots"][1]["transition"], "dissolve")


class StoryShape(unittest.TestCase):
    def test_hook_and_payoff_and_beat_order(self):
        r = C.check(plan(shot(beat="twist"), shot("Then he set it all up.", camera="close", beat="setup")), fix=True)
        warns = rules(r, "warn")
        self.assertIn("hook_first", warns)
        self.assertIn("payoff_last", warns)
        self.assertIn("beat_order", warns)
        self.assertIn("length", warns)

    def test_repeated_topic_is_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "index.json").write_text(json.dumps({"stories": [{"id": "old", "topic": "Test topic"}]}))
            r = C.check(plan(shot()), fix=True, stories=d)
            self.assertIn("topic_repeat", rules(r, "warn"))
            r = C.check(dict(plan(shot()), topic="something new"), fix=True, stories=d)
            self.assertNotIn("topic_repeat", rules(r, "warn"))


if __name__ == "__main__":
    unittest.main()


class Compile(unittest.TestCase):
    """Plan shot -> Blender shot (pure Python part of step 5)."""

    def setUp(self):
        from toontales.shots import compile as K
        self.K = K
        self.cast, _ = S.load_cast()
        self.kit = S.load_kits()["mine"]
        self.line = {"dur": 2.0, "cues": [{"t0": 0.0, "t1": 2.0, "shape": "B"}], "wav": "x.wav"}

    def cam_ok(self, cam):
        b = self.kit["bounds"]
        for end in ("from", "to"):
            x, y, z = self.K._cam_pos(cam[end])
            self.assertTrue(b["x"][0] - 1e-6 <= x <= b["x"][1] + 1e-6, (end, x))
            self.assertTrue(b["y"][0] - 1e-6 <= y, (end, y))
            self.assertTrue(b["z"][0] - 1e-6 <= z <= b["z"][1] + 1e-6, (end, z))

    def test_every_camera_and_move_stays_inside_the_set(self):
        cast = [{"id": "walt", "mark": "A", "acts": [{"do": "point", "at": 0}]},
                {"id": "pip", "mark": "B", "acts": [{"do": "shock", "at": 0}]}]
        for i, cam in enumerate(S.CAMERAS):
            for mv in S.MOVES:
                s = shot(speaker="walt", camera=cam, move=mv, cast=cast, id="s01",
                         props=[{"type": "gold", "spot": "wall_r"}])
                sj = self.K.compile_shot(s, i, self.line, self.cast, self.kit)
                self.cam_ok(sj["camera"])

    def test_shot_timing_lines_and_actions(self):
        s = shot(speaker="walt", id="s01", cast=[{"id": "walt", "mark": "A", "acts": [{"do": "point", "at": 9}]}])
        sj = self.K.compile_shot(s, 0, self.line, self.cast, self.kit)
        self.assertAlmostEqual(sj["dur"], 2.0 + self.K.BREATH)
        self.assertEqual(sj["lines"][0]["who"], "walt")
        self.assertLess(sj["actions"][0]["t0"], sj["dur"])
        nar = self.K.compile_shot(dict(s, speaker="narrator"), 0, self.line, self.cast, self.kit)
        self.assertEqual(nar["lines"], [])  # nobody's mouth moves on narration

    def test_fall_widens_the_frame(self):
        cast = [{"id": "walt", "mark": "A", "acts": [{"do": "fall", "at": 0.3}]},
                {"id": "pip", "mark": "B", "acts": [{"do": "cower", "at": 0}]}]
        still = [dict(c, acts=[{"do": "shock", "at": 0}]) for c in cast]
        s = shot(camera="two_shot", cast=cast, id="s01")
        a = self.K.compile_shot(s, 0, self.line, self.cast, self.kit)
        b = self.K.compile_shot(shot(camera="two_shot", cast=still, id="s01"), 0, self.line, self.cast, self.kit)
        # walt stands right of centre, so he falls left (into open floor) and the frame follows
        self.assertEqual(a["actions"][0]["params"]["side"], "left")
        self.assertLess(a["camera"]["to"]["target"][0], b["camera"]["to"]["target"][0])
        self.assertNotIn("params", s["cast"][0]["acts"][0])  # the plan itself is not edited

    def test_props_go_to_spots_walls_and_hands(self):
        s = shot(id="s01", cast=[{"id": "pip", "mark": "B", "acts": [{"do": "pick_up", "at": 0}]}],
                 props=[{"type": "board", "text": "STREAK TEST", "spot": "wall_l"},
                        {"type": "gold", "picked_by": "pip"}])
        sj = self.K.compile_shot(s, 0, self.line, self.cast, self.kit, art=lambda k, t: f"/art/{k}.png")
        board, gold = sj["props"]
        self.assertEqual(board["wall"], "l")
        self.assertEqual(board["image"], "/art/board.png")
        self.assertEqual(gold["picked_by"], "pip")
        self.assertEqual(gold["pos"][2], 0.0)


class Edit(unittest.TestCase):
    """Edit step (pure parts): caption timing, dissolve timeline, sound cues."""

    def setUp(self):
        from toontales.edit import edit as E
        self.E = E

    def test_captions_hold_until_the_next_word(self):
        ws = [{"w": "Black", "t0": 0.0, "t1": 0.3}, {"w": "line.", "t0": 0.4, "t1": 0.7}, {"w": "—", "t0": 0.8, "t1": 0.9}]
        wins = self.E.caption_windows(ws, 1.0)
        self.assertEqual(wins[0], ("Black", 0.0, 0.4))
        self.assertEqual(wins[1][1:], (0.4, 0.8))
        self.assertEqual(len(wins), 2)  # punctuation-only "word" gets no caption

    def test_dissolve_overlaps_only_on_time_jumps(self):
        clips = [{"dur": 2.0}, {"dur": 2.0, "transition": "dissolve"}, {"dur": 1.5}]
        starts, _freezes, total = self.E.timeline(clips)
        self.assertEqual(starts, [0.0, 2.0 - self.E.DISSOLVE, 4.0 - self.E.DISSOLVE])
        self.assertAlmostEqual(total, 5.5 - self.E.DISSOLVE)

    def test_sound_cues_add_action_sounds_without_doubling_the_plan(self):
        clips = [{"sfx": [{"name": "thud", "at": 0.9}], "overlay": {"type": "chalk", "text": "X"}}]
        shots = [{"actions": [{"do": "fall", "t0": 0.3}, {"do": "throw", "t0": 1.0}], "camera": {"ease": "out_fast"}}]
        cues = self.E.sound_cues(clips, shots, [10.0])
        names = [n for n, _ in cues]
        self.assertEqual(names.count("thud"), 1)   # plan thud at 10.9 swallows the auto one at 10.92
        self.assertIn("whoosh", names)
        self.assertIn("pop", names)
        self.assertEqual(cues, sorted(cues, key=lambda c: c[1]))
