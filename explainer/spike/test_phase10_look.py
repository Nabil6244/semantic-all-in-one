"""Phase 10 tests: the look. Board backgrounds beyond the reference's flat grey, and a serious narrator. Offline and deterministic; frames are drawn in memory.
usage: python3 -B explainer/spike/test_phase10_look.py   (from the repository root)"""
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True

from test_director_real_material import synth, run                                  # noqa: E402
from explainer.board.cues import Cue                                                # noqa: E402
from explainer.board.dry import dry_build                                           # noqa: E402
from explainer.board import render as R                                             # noqa: E402

WORDS = [(w, 0.5 + 0.3 * i, 0.5 + 0.3 * i + 0.25) for i, w in enumerate("the farmers worked the field all day and the village grew rich from the harvest".split())]
H = lambda im: hashlib.sha256(im.tobytes()).hexdigest()


def board(background="grey", narrator_style=None, t=3.0):
    p = {"action": "show", "pose": "idle", "side": "left", "scale": 1.0, "enter": "none"}
    if narrator_style:
        p["style"] = narrator_style
    cues = [Cue("n", "narrator", {"index": 0}, offset_s=0.0, params=p), Cue("s", "visual", {"index": 1}, text="the farmers worked", pos=(900, 300), params={"style": "scroll"})]
    probs, _r, items = dry_build(cues, WORDS, 0.0, 6.0, beat_id="t10")
    assert probs == [], probs
    return R.draw_frame(items, t, (1920, 1080), None, int(t * 30), False, None if not any(i.kind == "narrator" for i in items) else _narrator(cues), background)


def _narrator(cues):
    from explainer.board.cues import resolve_cues
    from explainer.board.dry import clip_geometry
    from explainer.narrator import timeline as TL
    origin, length = clip_geometry(0.0, 6.0, 0.0)
    resolved = resolve_cues(cues, WORDS, 0.0, 6.0, origin, 30, length, None)
    return TL.build_track(resolved, WORDS, origin, length, 30, "t10")


class Backgrounds(unittest.TestCase):
    def test_the_styles_are_full_frame_deterministic_and_light_enough_for_the_ink(self):
        from explainer.board import backdrops as B
        self.assertEqual(B.STYLES[0], "grey")
        for name in B.STYLES:
            a, b = B.image(name, (1920, 1080)), B.image(name, (1920, 1080))
            self.assertEqual(a.size, (1920, 1080))
            self.assertEqual(H(a), H(b))
            lum = sum(a.resize((64, 36)).convert("L").getdata()) / (64 * 36)
            self.assertGreater(lum, 180, f"{name} is too dark for the dark ink")

    def test_grey_is_still_the_flat_reference_board(self):
        from explainer.board import backdrops as B
        im = B.image("grey", (1920, 1080))
        self.assertEqual(im.getpixel((5, 5)), (192, 192, 192))
        self.assertEqual(im.getpixel((960, 540)), (192, 192, 192))
        self.assertEqual(H(board("grey")), H(board()))               # the default draw_frame is unchanged

    def test_the_other_styles_differ_from_grey_and_keep_every_element_readable(self):
        from explainer.board import backdrops as B
        grey = board("grey")
        for name in B.STYLES[1:]:
            im = board(name)
            self.assertNotEqual(H(im), H(grey), name)
            # the scroll (cream) must stay distinguishable from the background it sits on
            bg = im.getpixel((1700, 100))
            scroll = im.getpixel((1050, 400))
            self.assertGreater(sum(abs(a - b) for a, b in zip(bg, scroll)), 24, f"{name}: the scroll blends into the board")

    def test_an_unknown_background_is_refused(self):
        from explainer.board import backdrops as B
        with self.assertRaises(ValueError):
            B.image("neon", (1920, 1080))

    def test_the_director_default_is_not_grey_and_is_part_of_the_clip_name(self):
        words, dur = synth("The farmers worked the fields from the early morning until the evening. Every family in the village depended on the harvest. When the rains failed the people went hungry.")
        a = run(words, "The farmers worked the fields from the early morning until the evening. Every family in the village depended on the harvest. When the rains failed the people went hungry.", dur)
        self.assertIsNotNone(a.plan, a.problems)
        self.assertEqual(a.report["options"]["background"], "paper")
        g = run(words, "The farmers worked the fields from the early morning until the evening. Every family in the village depended on the harvest. When the rains failed the people went hungry.", dur, background="grey")
        name = lambda r: [b["footage"]["clips"][0]["asset"] for b in r.plan["beats"] if b["mode"] == "footage"]
        self.assertNotEqual(name(a), name(g))
        bad = run(words, "x y z", dur, background="neon")
        self.assertIsNone(bad.plan)
        self.assertTrue(any("background" in p for p in bad.problems), bad.problems)

    def test_a_board_clip_is_encoded_on_the_chosen_background(self):
        import tempfile
        from explainer.board.builder import build_board_clip
        cues = [Cue("s", "visual", {"index": 1}, text="the farmers worked", pos=(900, 300), params={"style": "scroll"})]
        with tempfile.TemporaryDirectory() as d:
            a = build_board_clip(cues, WORDS, 0.0, 2.0, Path(d) / "a.mp4", strict=True, beat_id="t10", background="paper")
            b = build_board_clip(cues, WORDS, 0.0, 2.0, Path(d) / "b.mp4", strict=True, beat_id="t10")
            c = build_board_clip(cues, WORDS, 0.0, 2.0, Path(d) / "c.mp4", strict=True, beat_id="t10", background="paper")
            sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
            self.assertNotEqual(sha(Path(d) / "a.mp4"), sha(Path(d) / "b.mp4"))
            self.assertEqual(sha(Path(d) / "a.mp4"), sha(Path(d) / "c.mp4"))


class SeriousNarrator(unittest.TestCase):
    def test_the_serious_set_is_built_once_checked_and_loaded_from_its_manifest(self):
        from explainer.narrator import build_assets as NB
        files = NB.build("serious")
        d = ROOT / "explainer" / "assets" / "narrator_serious"
        self.assertEqual(sorted(files), sorted(p.name for p in d.glob("*")))
        self.assertEqual([n for n in files if (d / n).read_bytes() != files[n]], [])
        from explainer.narrator import rig
        a = rig.load_assets("serious")
        self.assertEqual(a.manifest["style"], "serious")
        self.assertNotEqual(a.manifest["asset_id"], rig.load_assets("cartoon").manifest["asset_id"])

    def test_the_original_narrator_is_byte_identical_after_the_new_build_code(self):
        from explainer.narrator import build_assets as NB
        files = NB.build()
        for p in (ROOT / "explainer" / "assets" / "narrator").glob("*"):
            self.assertEqual(files[p.name], p.read_bytes(), p.name)

    def test_the_serious_face_has_no_blush_no_tuft_and_no_bright_clothes(self):
        from explainer.narrator import rig
        sp = rig.sprite("idle", "open", "closed", 100, False, "serious")
        cart = rig.sprite("idle", "open", "closed", 100, False)
        px = sp.convert("RGBA").getdata()
        blush = [p for p in px if p[3] > 200 and abs(p[0] - 240) < 14 and abs(p[1] - 150) < 14 and abs(p[2] - 140) < 14]
        self.assertEqual(blush, [], "no rosy cheeks")
        top = lambda im: im.getchannel("A").getbbox()[1]
        self.assertGreater(top(sp) - top(cart), 25, "the spiky tuft is gone: the head top is lower")
        body = [p for p in px if p[3] > 200]
        bright = [p for p in body if max(p[:3]) > 200 and min(p[:3]) < 90]            # saturated red / teal clothing
        self.assertLess(len(bright) / max(1, len(body)), 0.02)

    def test_the_cue_style_selects_the_set_and_the_default_is_unchanged(self):
        a, b, c = board("grey"), board("grey", "serious"), board("grey", "cartoon")
        self.assertNotEqual(H(a), H(b))
        self.assertEqual(H(a), H(c))

    def test_an_unknown_style_is_a_problem(self):
        cues = [Cue("n", "narrator", {"index": 0}, offset_s=0.0, params={"action": "show", "pose": "idle", "style": "clown"})]
        probs, _r, _i = dry_build(cues, WORDS, 0.0, 6.0, beat_id="t10")
        self.assertTrue(probs and "style" in probs[0], probs)

    def test_the_director_uses_the_serious_narrator_by_default(self):
        s = "The farmers worked the fields from the early morning until the evening. Every family in the village depended on the harvest. When the rains failed the people went hungry. The king sent grain to the farmers."
        words, dur = synth(s)
        r = run(words, s, dur)
        styles = [(c["params"] or {}).get("style") for d in r.report["beat_details"].values() if isinstance(d, dict) for c in d.get("cue_specs", []) if c["kind"] == "narrator" and c["params"].get("action") == "show"]
        self.assertTrue(styles and set(styles) == {"serious"}, styles)
        r2 = run(words, s, dur, narrator_style="cartoon")
        styles2 = [(c["params"] or {}).get("style") for d in r2.report["beat_details"].values() if isinstance(d, dict) for c in d.get("cue_specs", []) if c["kind"] == "narrator" and c["params"].get("action") == "show"]
        self.assertTrue(styles2 and set(styles2) == {None}, styles2)

    def test_the_serious_set_keeps_poses_blinks_and_collision_boxes(self):
        from explainer.narrator import rig
        m = rig.load_assets("serious").manifest
        self.assertEqual(sorted(m["poses"]), ["explain", "idle", "point", "shrug", "surprise", "think"])
        self.assertEqual(sorted(m["eyes"]), ["blink", "happy", "open"])
        self.assertEqual(sorted(m["mouths"]), ["closed", "o", "open", "wide"])


class Settings(unittest.TestCase):
    def test_the_look_settings_are_optional_and_validated(self):
        from explainer.integration import look_settings
        self.assertEqual(look_settings({}), ("paper", "serious"))
        self.assertEqual(look_settings(None), ("paper", "serious"))
        self.assertEqual(look_settings({"explainer_background": "grid", "explainer_narrator": "cartoon"}), ("grid", "cartoon"))
        self.assertEqual(look_settings({"explainer_background": "neon", "explainer_narrator": 7}), ("paper", "serious"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
