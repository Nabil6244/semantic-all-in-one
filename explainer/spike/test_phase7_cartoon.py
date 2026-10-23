"""Phase 7 tests: the Explainer cartoon kit (sets, cast, props; `visual` styles set / figure / crowd / prop; opt-in cartoon beats).

Offline and deterministic; nothing is encoded or downloaded (frames are drawn in memory, plans are built with materialize=False).
usage: python3 -B explainer/spike/test_phase7_cartoon.py   (from the repository root)"""
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True

from test_director_real_material import synth, run, text_cues, KoreaCache      # noqa: E402
from explainer.board.cues import Cue                                            # noqa: E402
from explainer.board.dry import dry_build                                       # noqa: E402
from explainer.board import render as R                                         # noqa: E402

KIT_DIR = ROOT / "explainer" / "assets" / "cartoon"
WORDS = [(w, 0.5 + 0.3 * i, 0.5 + 0.3 * i + 0.25) for i, w in enumerate("the farmers worked the field all day and the village grew rich from the harvest".split())]


def dry(cues, words=WORDS, start=0.0, end=6.0):
    return dry_build(cues, words, start, end, beat_id="t7")


def set_cue(name="town", tod="day", cid="set1"):
    return Cue(cid, "visual", {"index": 0}, pos=(0, 0), offset_s=0.0, params={"style": "set", "set": name, "tod": tod})


def fig(cid, x, y, role="blue", pose="idle", idx=1, height=420, flip=False, kit="a"):
    return Cue(cid, "visual", {"index": idx}, role=role, pos=(x, y), params={"style": "figure", "cast": role, "pose": pose, "kit": kit, "height": height, "flip": flip})


class Assets(unittest.TestCase):
    def test_the_kit_is_built_once_and_the_files_on_disk_are_exactly_the_build(self):
        from explainer.cartoon import build_assets as B
        files = B.build()
        on_disk = {p.name: p.read_bytes() for p in KIT_DIR.glob("*")}
        self.assertEqual(sorted(files), sorted(on_disk))
        self.assertEqual([n for n in files if files[n] != on_disk[n]], [])

    def test_manifest_counts_and_hashes(self):
        m = json.loads((KIT_DIR / "manifest.json").read_text())
        self.assertEqual(sorted(m["sets"]), ["city", "field", "harbour", "room", "town"])
        for s in m["sets"].values():
            self.assertEqual(sorted(s["tod"]), ["day", "dusk"])
            for t in s["tod"].values():
                self.assertEqual(hashlib.sha256((KIT_DIR / t["file"]).read_bytes()).hexdigest(), t["sha256"])
                self.assertEqual(t["size"], [1920, 1080])
        self.assertEqual(sorted(m["cast"]), ["blue", "gold", "green", "red"])
        for role, poses in m["cast"].items():
            self.assertEqual(sorted(poses), ["idle", "point", "surprise", "think"])
            self.assertEqual(sorted(poses["idle"]), ["a", "b", "c"])
        self.assertEqual(sorted(m["props"]), ["cactus", "crate", "fence", "flag", "house", "sign", "tree"])

    def test_the_loader_refuses_a_damaged_file_and_never_builds(self):
        from explainer.cartoon import kit
        self.assertFalse(hasattr(kit, "build"), "the loader must not be able to build assets during a render")
        m = json.loads((KIT_DIR / "manifest.json").read_text())
        bad = dict(m["props"]["flag"], sha256="0" * 64)
        with self.assertRaises(kit.AssetError):
            kit.check_file(KIT_DIR / bad["file"], bad["sha256"], bad["bytes"])

    def test_cast_sprites_are_visible_and_inside_their_canvas(self):
        from explainer.cartoon import kit
        for role in ("blue", "red"):
            for pose in ("idle", "point", "surprise", "think"):
                sp = kit.cast_sprite(role, pose, "a", 420, False)
                bb = sp.getchannel("A").getbbox()
                self.assertIsNotNone(bb)
                self.assertGreater(bb[2] - bb[0], 100)
                self.assertLessEqual(bb[3], sp.height)

    def test_the_cast_looks_different_from_the_narrator_but_shares_its_body(self):
        from explainer.cartoon import kit
        from explainer.narrator import rig
        nar = rig.sprite("idle", "open", "closed", 100, False).convert("RGB")
        cast = kit.cast_sprite("blue", "idle", "a", 560, False).convert("RGB")
        self.assertEqual(nar.size[1], cast.size[1])
        self.assertNotEqual(hashlib.sha256(nar.tobytes()).hexdigest(), hashlib.sha256(cast.tobytes()).hexdigest())

    def test_narrator_assets_are_untouched_by_building_the_kit(self):
        from explainer.narrator import build_assets as NB
        files = NB.build()
        for p in (ROOT / "explainer" / "assets" / "narrator").glob("*"):
            self.assertEqual(files[p.name], p.read_bytes(), p.name)


class Cues(unittest.TestCase):
    def test_a_backdrop_figure_and_prop_build_without_problems(self):
        probs, res, items = dry([set_cue(), Cue("p1", "visual", {"index": 0}, pos=(300, 520), params={"style": "prop", "prop": "house", "height": 300}), fig("f1", 900, 300)])
        self.assertEqual(probs, [])
        self.assertEqual([i.style for i in items if i.kind == "visual"], ["set", "prop", "figure"])

    def test_the_backdrop_may_cover_everything_and_is_exempt_from_collision(self):
        probs, _r, _i = dry([Cue("c1", "card", {"index": 0}, text="the farmers worked", slot="C1"), set_cue()])
        self.assertEqual(probs, [])

    def test_two_figures_may_not_overlap(self):
        probs, _r, _i = dry([fig("f1", 900, 300), fig("f2", 960, 320, role="green")])
        self.assertTrue(any("f2" in p and "collides" in p for p in probs), probs)

    def test_a_figure_may_not_cover_a_caption_slot_or_leave_the_margins(self):
        cap = Cue("cap", "caption", {"index": 0}, text="the farmers worked the field", params={"mode": "words"})
        probs, _r, _i = dry([cap, fig("f1", 900, 520, height=420)])
        self.assertTrue(any("f1" in p and "collides" in p for p in probs), probs)
        probs, _r, _i = dry([fig("f2", 1800, 300)])
        self.assertTrue(any("f2" in p and "margin" in p for p in probs), probs)

    def test_a_prop_behind_a_figure_is_allowed_but_not_behind_text(self):
        prop = Cue("p1", "visual", {"index": 0}, pos=(900, 300), params={"style": "prop", "prop": "house", "height": 400})
        probs, _r, _i = dry([prop, fig("f1", 960, 360)])
        self.assertEqual(probs, [])
        probs, _r, _i = dry([Cue("l1", "visual", {"index": 0}, text="the farmers worked", pos=(900, 340), params={"style": "line", "width": 700, "px": 56, "lines": 1}), prop])
        self.assertTrue(any("p1" in p and "collides" in p for p in probs), probs)

    def test_a_crowd_is_a_row_of_n_figures_inside_the_margins_and_the_same_every_time(self):
        crowd = Cue("cr", "visual", {"index": 2}, pos=(760, 780), params={"style": "crowd", "n": 8, "height": 170, "seed": 3})
        probs, _r, items = dry([crowd])
        self.assertEqual(probs, [])
        it = [i for i in items if i.style == "crowd"][0]
        self.assertGreater(it.rect[2] - it.rect[0], 8 * 40)
        frame_a = R.draw_frame(items, 3.0, (1920, 1080), None, 90, False)
        frame_b = R.draw_frame(dry([crowd])[2], 3.0, (1920, 1080), None, 90, False)
        self.assertEqual(hashlib.sha256(frame_a.tobytes()).hexdigest(), hashlib.sha256(frame_b.tobytes()).hexdigest())

    def test_unknown_set_role_pose_or_prop_is_a_problem_not_a_crash(self):
        for params in ({"style": "set", "set": "moon", "tod": "day"}, {"style": "figure", "cast": "purple", "pose": "idle"}, {"style": "figure", "cast": "blue", "pose": "dance"},
                       {"style": "prop", "prop": "spaceship"}, {"style": "set", "set": "town", "tod": "midnight"}):
            probs, _r, _i = dry([Cue("x", "visual", {"index": 0}, pos=(500, 300), params=params)])
            self.assertTrue(probs and "x" in probs[0], (params, probs))

    def test_a_figure_appears_on_the_word_it_is_anchored_to_and_the_frame_is_deterministic(self):
        cues = [set_cue(), fig("f1", 900, 300, idx=4)]
        _p, res, items = dry(cues)
        f = [r for r in res if r.cue.id == "f1"][0]
        import math
        self.assertEqual(f.first_frame, math.ceil((WORDS[4][1] + 0.1) * 30 - 1e-9))     # the default offset of a visual cue is 0.1 s
        a = R.draw_frame(items, 4.0, (1920, 1080), None, 120, False)
        b = R.draw_frame(dry(cues)[2], 4.0, (1920, 1080), None, 120, False)
        self.assertEqual(a.tobytes(), b.tobytes())
        before = R.draw_frame(items, 0.0, (1920, 1080), None, 0, False)
        self.assertNotEqual(before.tobytes(), a.tobytes())

    def test_the_set_is_drawn_underneath_everything(self):
        cap = Cue("cap", "caption", {"index": 0}, text="the farmers worked the field", params={"mode": "words"})
        _p, _r, items = dry([cap, set_cue()])           # authored in the "wrong" order on purpose
        im = R.draw_frame(items, 4.0, (1920, 1080), None, 120, False)
        self.assertNotEqual(im.getpixel((10, 10)), (192, 192, 192))      # not the grey board: the set shows
        from explainer.cartoon import kit
        self.assertEqual(im.getpixel((10, 10)), kit.set_image("town", "day").getpixel((10, 10)))

    def test_existing_styles_and_kinds_are_unchanged(self):
        from explainer.board import styles
        self.assertEqual(styles.STYLES[:7], ("tile", "circle", "box", "lite", "tag", "scroll", "line"))
        from explainer.board.cues import KINDS
        self.assertIn("narrator", KINDS)


class Director(unittest.TestCase):
    SCRIPT = ("The farmers worked the fields from the early morning until the evening. Every family in the village depended on the harvest. "
              "When the rains failed the people of the village went hungry. The king sent grain from the cities to the farmers. "
              "Trade across the harbour brought new ships and new goods every season. In the evening the whole village gathered in the square to celebrate. "
              "The old fences were mended and the houses were repaired. By the end of the year the village was richer than before.")

    def test_the_default_plan_has_no_cartoon_beat(self):
        words, dur = synth(self.SCRIPT)
        r = run(words, self.SCRIPT, dur)
        self.assertIsNotNone(r.plan, r.problems)
        self.assertFalse([b for b in r.plan["beats"] if "cartoon" in b.get("purpose", "")])
        self.assertEqual(json.dumps(r.plan, sort_keys=True), json.dumps(run(words, self.SCRIPT, dur, cartoon_share=0.0).plan, sort_keys=True))

    def test_cartoon_beats_are_opt_in_capped_and_never_three_in_a_row(self):
        words, dur = synth(self.SCRIPT)
        r = run(words, self.SCRIPT, dur, cartoon_share=0.4)
        self.assertIsNotNone(r.plan, r.problems)
        kinds = [b["kind"] for b in r.report["selection"]["beats"]]
        self.assertIn("cartoon", kinds)
        share = sum(b["end"] - b["start"] for b in r.report["selection"]["beats"] if b["kind"] == "cartoon") / dur
        self.assertLessEqual(share, 0.4 + 1e-6)
        self.assertNotIn(("cartoon", "cartoon", "cartoon"), list(zip(kinds, kinds[1:], kinds[2:])))

    def test_a_cartoon_beat_has_a_set_a_figure_a_grounded_caption_and_no_narrator(self):
        words, dur = synth(self.SCRIPT)
        r = run(words, self.SCRIPT, dur, cartoon_share=0.4)
        from explainer.beats.relevance import beat_tokens, find_phrase
        seen = 0
        for b in r.report["selection"]["beats"]:
            if b["kind"] != "cartoon":
                continue
            seen += 1
            d = r.report["beat_details"][b["id"]]
            styles = [c["params"].get("style") for c in d["cue_specs"] if c["kind"] == "visual"]
            self.assertIn("set", styles)
            self.assertIn("figure", styles)
            self.assertEqual(styles.count("set"), 1)
            self.assertLessEqual(styles.count("prop"), 1)
            self.assertFalse([c for c in d["cue_specs"] if c["kind"] == "narrator"])
            tk = beat_tokens(words, b["start"], b["end"])
            caps = [c for c in d["cue_specs"] if c["kind"] == "caption"]
            self.assertTrue(caps, "a cartoon beat shows the spoken words as a caption")
            for c in caps:
                self.assertIsNotNone(find_phrase(tk, c["text"]), c["text"])
            self.assertEqual(d["problems"], [])
        self.assertGreater(seen, 0)

    def test_the_set_follows_the_words_and_dusk_follows_evening(self):
        words, dur = synth(self.SCRIPT)
        r = run(words, self.SCRIPT, dur, cartoon_share=0.5)
        sets = {}
        for b in r.report["selection"]["beats"]:
            if b["kind"] == "cartoon":
                for c in r.report["beat_details"][b["id"]]["cue_specs"]:
                    if (c.get("params") or {}).get("style") == "set":
                        sets[b["id"]] = (c["params"]["set"], c["params"]["tod"], b)
        self.assertTrue(sets)
        for _bid, (name, tod, b) in sets.items():
            said = " ".join(w[0] for w in words if b["start"] - 1e-6 <= w[1] < b["end"] - 1e-6)
            if "evening" in said:
                self.assertEqual(tod, "dusk")
            from explainer.director import lexicon as LX
            self.assertTrue(set(said.split()) & set(LX.SET_WORDS[name]), f"{name} is not suggested by anything said: {said!r}")
        first = [(n, b) for _b, (n, t, b) in sets.items() if "farmers worked the fields" in " ".join(w[0] for w in words if b["start"] - 1e-6 <= w[1] < b["end"] - 1e-6)]
        for n, _b in first:
            self.assertEqual(n, "field")

    def test_the_plan_with_cartoon_beats_passes_every_gate_and_is_deterministic(self):
        words, dur = synth(self.SCRIPT)
        a = run(words, self.SCRIPT, dur, cartoon_share=0.4)
        b = run(words, self.SCRIPT, dur, cartoon_share=0.4)
        self.assertIsNotNone(a.plan, a.problems)
        self.assertEqual(a.problems, [])
        self.assertEqual(json.dumps(a.plan, sort_keys=True), json.dumps(b.plan, sort_keys=True))
        self.assertEqual(a.report["hybrid_validate"].get("errors"), [])

    def test_phase_4_maps_are_untouched_by_the_cartoon_option(self):
        off = KoreaCache.get()
        words = [tuple(w) for w in json.loads((ROOT / "explainer" / "spike" / "fixtures" / "korea" / "words.json").read_text())["words"]]
        from test_director_real_material import SCRIPT, DUR
        on = run(words, SCRIPT, DUR, cartoon_share=0.4)
        self.assertIsNotNone(on.plan, on.problems)
        maps_off = [b for b in off.plan["beats"] if b["mode"] == "map"]
        maps_on = [b for b in on.plan["beats"] if b["mode"] == "map"]
        self.assertEqual(json.dumps(maps_off, sort_keys=True), json.dumps(maps_on, sort_keys=True))


class SceneMeaning(unittest.TestCase):
    """Round 2: a cartoon scene needs a real reason in the words; weak hints ("family", "people") never pick a desert town for a story about a country."""

    def test_weak_words_alone_choose_no_scene(self):
        from explainer.director import compose_cartoon as CC
        self.assertIsNone(CC.scene_for("run the place like a family business".split()))
        self.assertIsNone(CC.scene_for("get you sent to a prison camp and the people were afraid".split()))
        self.assertEqual(CC.scene_for("the farmers worked the fields all day".split()), "field")
        self.assertEqual(CC.scene_for("the whole village gathered in the square".split()), "town")

    def test_the_korea_script_gets_no_cartoon_beat_at_all(self):
        from test_director_real_material import SCRIPT, WORDS, DUR
        r = run(WORDS, SCRIPT, DUR, cartoon_share=0.5)
        self.assertIsNotNone(r.plan, r.problems)
        self.assertNotIn("cartoon", [b["kind"] for b in r.report["selection"]["beats"]])
        self.assertTrue(r.report["selection"].get("cartoon_skipped"), "the report says why no beat became a cartoon")

    def test_a_beat_with_a_real_scene_still_becomes_a_cartoon(self):
        words, dur = synth(Director.SCRIPT)
        r = run(words, Director.SCRIPT, dur, cartoon_share=0.4)
        self.assertIn("cartoon", [b["kind"] for b in r.report["selection"]["beats"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
