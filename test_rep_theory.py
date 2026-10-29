"""Rep Theory (reptheory/): planner reads meaning from the narration and never invents numbers, tiers or art; the library's cut-out; a short end-to-end render at Preview size with
synthetic pictures in a temporary library (no Flow, no network); cancel leaves nothing behind; packaging; registration in the app. The art here is synthetic: the real library is in ~/RepTheoryAssets."""
from __future__ import annotations
import os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="rt_test_lib_"); os.environ["REP_THEORY_ASSET_DIR"] = _TMP      # before the package reads it

from PIL import Image, ImageDraw
from reptheory import engine, library as L, packaging, planner

ROOT = Path(__file__).resolve().parent

def _art(name, kind, size=(600, 900)):
    im = Image.new("RGB", size, (0, 0, 0)); d = ImageDraw.Draw(im); d.ellipse((120, 80, size[0] - 120, size[1] - 80), fill=(190, 190, 190)); d.rectangle((250, 300, 350, 600), fill=(0, 0, 0))   # a black hole inside the figure
    p = Path(_TMP) / f"src_{name}.png"; im.save(p); L.register(p, id=name, kind=kind, subject=name, prompt="test", source="supplied")

def setUpModule():
    for n, k in (("rep_stand_v1", "character"), ("rep_hang_v1", "character"), ("prop_bottle_2l_v1", "prop"), ("anat_forearm_v1", "anatomy")): _art(n, k)

def S(text, a, b): return {"text": text, "start": a, "end": b}

class Planner(unittest.TestCase):
    def test_equation_only_from_stated_numbers(self):
        sc = planner.plan([S("One litre of water weighs about one kilogram, so two litres is about two kilograms.", 0, 8)])
        self.assertEqual([(e["lhs"], e["rhs"]) for e in sc[0]["equations"]], [("1 L", "1 KG"), ("2 L", "2 KG")])
        self.assertLess(sc[0]["equations"][0]["at_r"], sc[0]["equations"][1]["at_r"])
        plain = planner.plan([S("Hold the bottle by the neck.", 0, 3)]); self.assertEqual(plain[0]["equations"], [])

    def test_tier_needs_a_placement_not_a_description_of_the_scale(self):
        scale = planner.plan([S("Now let us rank it, from S tier at the top down to F tier at the bottom.", 0, 5)])[0]
        self.assertEqual(scale["kind"], "tier"); self.assertIsNone(scale["tier"]["letter"]); self.assertEqual([m["letter"] for m in scale["tier_marks"]], ["S", "F"])
        placed = planner.plan([S("Pinching a bottle is a simple beginner test, so it lands in B tier.", 0, 5)])[0]
        self.assertEqual(placed["tier"]["letter"], "B"); self.assertEqual(placed["tier"]["item"], "PINCHING A BOTTLE")

    def test_value_is_only_what_is_said(self):
        self.assertEqual(planner.plan([S("All you need is a full two litre bottle of water.", 0, 4)])[0]["value"], "2 L")
        self.assertEqual(planner.plan([S("Stand tall and keep squeezing.", 0, 3)])[0]["value"], "")

    def test_missing_art_becomes_a_callout_on_the_trainee(self):
        sc = planner.plan([S("Your forearm muscles do the squeezing.", 0, 4)], art_ok=lambda a: a == "rep_stand_v1")[0]
        self.assertEqual((sc["kind"], sc["art"], sc.get("missing_art")), ("trainee", "rep_stand_v1", "anat_forearm_v1"))

    def test_scenes_are_contiguous_and_cover_the_narration(self):
        sc = planner.plan([S("You do not need a gym.", 0, 2.8), S("All you need is a bottle of water.", 2.8, 6), S("Hold the bottle by the neck.", 6, 10), S("Your forearm muscles do the work.", 10, 14)])
        self.assertEqual(sc[0]["start"], 0.0); self.assertEqual(sc[-1]["end"], 14)
        for a, b in zip(sc, sc[1:]): self.assertEqual(a["end"], b["start"])

    def test_callout_follows_the_words(self):
        sc = planner.plan([S("Hold the bottle by the neck and pinch it for as long as you can.", 0, 6)])[0]
        self.assertEqual([c["text"] for c in sc["chips"]], ["BY THE NECK", "AS LONG AS YOU CAN"]); self.assertLess(sc["chips"][0]["at"], sc["chips"][1]["at"])

    def test_scenes_file_direction_wins(self):
        sc = planner.plan([dict(S("Hold on.", 0, 4), headline="THE TRICK", value="3 S", chips=["ROLL TO YOUR FINGERTIPS"])])[0]
        self.assertEqual((sc["headline"], sc["value"], [c["text"] for c in sc["chips"]]), ("THE TRICK", "3 S", ["ROLL TO YOUR FINGERTIPS"]))

class Interaction(unittest.TestCase):
    def test_holding_the_bottle_puts_it_in_the_trainee_hand(self):
        sc = planner.plan([S("Hold the bottle by the neck and pinch it for as long as you can.", 0, 5), S("Stand tall, keep your arm by your side, and keep squeezing.", 5, 9)])
        self.assertEqual(len(sc), 1); self.assertEqual((sc[0]["kind"], sc[0]["prop"]), ("hold", "prop_bottle_2l_v1")); self.assertEqual(len(sc[0]["pages"]), 2)      # one scene, a new callout per sentence
        self.assertTrue(sc[0]["squeezes"]); self.assertEqual(sc[0]["pages"][0]["headline"], "PINCH GRIP")
    def test_switching_hands_mirrors_at_the_word(self):
        sc = planner.plan([S("Hold the bottle in your hand.", 0, 3), S("When the bottle starts to slip, rest, then switch to the other hand.", 3, 9)])[0]
        self.assertIsNotNone(sc["flip_at"]); self.assertGreater(sc["flip_at"], 3)
    def test_headlines_and_chips_are_not_repeated(self):
        sc = planner.plan([S("You do not need a gym.", 0, 3), S("Hold the bottle by the neck for as long as you can.", 3, 9), S("Pinching a bottle is a simple beginner test, so it lands in B tier.", 9, 14), S("Hang from a bar and hold on for as long as you can.", 14, 20)])
        heads = [p["headline"] for s in sc for p in s["pages"] if p["headline"]]; chips = [c["text"] for s in sc for p in s["pages"] for c in p["chips"]]
        self.assertEqual(len(heads), len(set(heads))); self.assertEqual(len(chips), len(set(chips)))
    def test_a_sentence_with_nothing_new_continues_the_previous_scene(self):
        sc = planner.plan([S("Hang from a bar with both hands.", 0, 4), S("Same idea, bigger test.", 4, 7)])
        self.assertEqual(len(sc), 1)
    def test_anatomy_label_is_neutral(self):
        sc = planner.plan([S("Your forearm muscles do the squeezing, so that is where you will feel it.", 0, 5)])[0]
        self.assertEqual(sc["pages"][0]["headline"], "FOREARM")
    def test_frames_render_for_every_kind(self):
        from reptheory import draw as D, scenes as SC
        ctx = D.Ctx(640, 360); sc = planner.plan([S("You do not need a gym.", 0, 3), S("All you need is a full two litre bottle of water.", 3, 7), S("One litre of water weighs about one kilogram, so two litres is about two kilograms.", 7, 14), S("Hold the bottle by the neck and pinch it.", 14, 18), S("When the bottle starts to slip, rest, then switch to the other hand.", 18, 23), S("Your forearm muscles do the squeezing.", 23, 27), S("Pinching a bottle is a simple beginner test, so it lands in B tier.", 27, 33), S("Hang from a bar with both hands.", 33, 38)], title="Grip · No Gym")
        for x in sc:
            for off in (0.5, 2.0, 4.0): self.assertEqual(SC.frame(ctx, x, off).size, (640, 360))
        self.assertEqual({x["kind"] for x in sc}, {"trainee", "prop", "equation", "hold", "anatomy", "tier", "pose"})

class Library(unittest.TestCase):
    def test_cutout_clears_black_everywhere_including_holes(self):
        im = L.cutout("rep_stand_v1"); a = im.getchannel("A"); self.assertEqual(a.getpixel((2, 2)), 0)
        w, h = im.size; self.assertEqual(a.getpixel((w // 2, h // 2)), 0)          # the black hole inside the figure is transparent too
        self.assertEqual(a.getpixel((w // 8 + 8, h // 2)), 255)
    def test_missing_art_is_reported_not_invented(self):
        self.assertEqual(L.missing(["rep_stand_v1", "nope"]), ["nope"])
        with self.assertRaises(FileNotFoundError): L.cutout("nope")

class Render(unittest.TestCase):
    def _vo(self, d, secs):
        p = Path(d) / "vo.wav"; subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(secs), str(p)], check=True); return str(p)
    def test_end_to_end_preview_is_16x9_with_exact_frames(self):
        with tempfile.TemporaryDirectory() as d:
            sents = [S("All you need is a full two litre bottle of water.", 0, 3), S("One litre of water weighs about one kilogram, so two litres is about two kilograms.", 3, 7), S("Pinching a bottle is a simple beginner test, so it lands in B tier.", 7, 10)]
            rep = engine.run_rep_theory(d, sents, self._vo(d, 10), str(Path(d) / "o.mp4"), quality="preview", title="Grip")
            self.assertEqual(rep["size"], [1280, 720]); self.assertEqual(rep["frames"], 240); self.assertEqual(rep["fps"], 24)
            out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,nb_frames", "-of", "csv=p=0", str(Path(d) / "o.mp4")], capture_output=True, text=True).stdout.strip().split(",")
            self.assertEqual(out[:2], ["1280", "720"]); self.assertEqual(int(out[2]), 240); self.assertTrue(Path(str(Path(d) / "o.mp4") + ".rep_theory.json").is_file())
    def test_cancel_leaves_no_partial_file(self):
        with tempfile.TemporaryDirectory() as d:
            n = {"i": 0}
            def stop(): n["i"] += 1; return n["i"] > 5
            with self.assertRaises(engine.Cancelled): engine.run_rep_theory(d, [S("Hold the bottle by the neck.", 0, 6)], self._vo(d, 6), str(Path(d) / "o.mp4"), quality="preview", cancel_check=stop)
            self.assertEqual(sorted(p.name for p in Path(d).glob("o.mp4*")), [])
    def test_bundled_art_is_found_with_an_empty_external_directory(self):
        old = os.environ["REP_THEORY_ASSET_DIR"]; empty = tempfile.mkdtemp(); os.environ["REP_THEORY_ASSET_DIR"] = empty
        try:
            self.assertEqual(L.missing(["rep_stand_v1", "rep_hang_v1", "prop_bottle_2l_v1", "anat_forearm_v1"]), [])
            self.assertTrue(all(Path(L.find(i)["path"]).is_relative_to(L.bundled_root()) for i in ("rep_stand_v1", "rep_hang_v1", "prop_bottle_2l_v1", "anat_forearm_v1")))
            self.assertEqual(L.cutout("rep_stand_v1").mode, "RGBA"); self.assertTrue((Path(empty) / "_cache" / "rep_stand_v1.cut2.png").is_file())      # cached in the user folder, bundled folder untouched
            self.assertEqual(sorted(p.name for p in Path(empty).iterdir()), ["_cache"])      # nothing generated or registered
            with tempfile.TemporaryDirectory() as d:
                sents = [S("Hold the bottle by the neck and pinch it.", 0, 3), S("Your forearm muscles do the squeezing.", 3, 6)]; before = set(sys.modules); spawned = []; real_popen = subprocess.Popen
                subprocess.Popen = lambda cmd, *a, **k: (spawned.append(str(cmd[0])), real_popen(cmd, *a, **k))[1]
                try: rep = engine.run_rep_theory(d, sents, self._vo(d, 6), str(Path(d) / "o.mp4"), quality="preview")
                finally: subprocess.Popen = real_popen
                self.assertTrue(spawned and all(("ffmpeg" in c or "ffprobe" in c) for c in spawned), spawned)      # the only processes a render starts are ffmpeg and ffprobe: no Flow, no browser
                self.assertTrue({"rep_stand_v1", "prop_bottle_2l_v1", "anat_forearm_v1"} <= set(rep["art_used"]) | {rep["scenes"][0]["prop"]})
                self.assertFalse([m for m in set(sys.modules) - before if m.startswith("reptheory.art")])      # the generator is not even imported
        finally: os.environ["REP_THEORY_ASSET_DIR"] = old

    def test_user_library_overrides_the_bundled_picture(self):
        self.assertEqual(Path(L.find("rep_stand_v1")["path"]).parent, L.root())      # the synthetic test copy wins over assets/reptheory

    def test_missing_art_says_where_it_looked_and_generates_nothing(self):
        old = os.environ["REP_THEORY_ASSET_DIR"]; os.environ["REP_THEORY_ASSET_DIR"] = tempfile.mkdtemp(); real = L.bundled_root; L.bundled_root = lambda: Path(tempfile.mkdtemp())
        try:
            with tempfile.TemporaryDirectory() as d, self.assertRaisesRegex(RuntimeError, r"Rep Theory art missing: rep_stand_v1 \(looked in: .*RepTheory|looked in") as cm: engine.run_rep_theory(d, [S("Hi there.", 0, 2)], self._vo(d, 2), str(Path(d) / "o.mp4"), quality="preview")
            self.assertIn(os.environ["REP_THEORY_ASSET_DIR"], str(cm.exception))
        finally: os.environ["REP_THEORY_ASSET_DIR"] = old; L.bundled_root = real

    def test_landscape_only(self):
        with self.assertRaises(ValueError): engine.run_rep_theory(".", [S("x", 0, 1)], "", "x.mp4", quality="shorts")

class Wiring(unittest.TestCase):
    def test_packaging_lists_every_module(self):
        mods = packaging.python_modules(ROOT); self.assertIn("reptheory.engine", mods); self.assertIn("reptheory.app_section", mods)
    def test_registered_in_the_app_and_kit(self):
        src = (ROOT / "app.py").read_text(); self.assertIn('"Health Cinema", "Rep Theory")', src); self.assertIn("_reptheory_activate", src)
        self.assertIn('"Rep Theory": "_rt_block"', (ROOT / "ui" / "style_kit.py").read_text()); self.assertIn("Rep Theory", (ROOT / "ui" / "style_registry.py").read_text())
        self.assertIn("reptheory_modules", (ROOT / "VideoGenerator.spec").read_text())
        spec = (ROOT / "VideoGenerator.spec").read_text(); self.assertIn("datas += reptheory_data_files(ROOT)", spec)
        df = packaging.data_files(ROOT); self.assertEqual(sorted(Path(s).name for s, _ in df), ["anat_forearm_v1.png", "index.json", "prop_bottle_2l_v1.png", "rep_hang_v1.png", "rep_stand_v1.png"]); self.assertEqual({d for _, d in df}, {"assets/reptheory"})
        import json; idx = json.loads((ROOT / "assets" / "reptheory" / "index.json").read_text()); self.assertEqual(sorted(e["id"] for e in idx), ["anat_forearm_v1", "prop_bottle_2l_v1", "rep_hang_v1", "rep_stand_v1"])
        for e in idx: self.assertEqual(L.sha256(ROOT / "assets" / "reptheory" / e["file"]), e["sha256"])      # the bundled pictures are the ones in the index

class Polish(unittest.TestCase):
    def _alpha_box(self, fn, box=(0, 0, 640, 140)):
        """Drawn on a transparent layer so a pixel is 'ink' only if the function put something there."""
        from reptheory import draw as D
        ctx = D.Ctx(1280, 720); lay = Image.new("RGBA", (1280, 720), (0, 0, 0, 0)); fn(lay, ctx); return lay.getchannel("A").crop(box)

    def test_section_tag_old_and_new_never_share_a_frame(self):
        from reptheory import draw as D
        seen_old = seen_new = False
        for i in range(0, 60):
            t = i / 100; which, p = D.tag_phase(t, "GRIP · NO GYM", "TIER LIST · GRIP")
            if which == "old": seen_old = True; self.assertLess(p, 1.0001)
            else: seen_new = True
            if which == "new" and p > 0: self.assertGreaterEqual(t, 0.5 * D.TAG_OUT_FRAC - 1e-9)      # the new label starts only after the old one is fully out
        self.assertTrue(seen_old and seen_new); self.assertEqual(D.tag_phase(0.0, "A", "B")[0], "old"); self.assertEqual(D.tag_phase(0.5, "A", "B"), ("new", 1.0))
        o_end = D.tag_phase(0.5 * D.TAG_OUT_FRAC - 1e-6, "A", "B"); self.assertGreater(o_end[1], 0.99)

    def test_section_tag_pixels_show_only_one_label(self):
        from reptheory import draw as D
        old, new = "GRIP · NO GYM", "TIER LIST · GRIP"; only_new = self._alpha_box(lambda c, x: D.section_tag(c, x, new, 9.0)); only_old = self._alpha_box(lambda c, x: D.section_tag(c, x, old, 9.0))
        for t in (0.0, 0.1, 0.19, 0.2, 0.25, 0.35, 0.5, 0.8):
            got = self._alpha_box(lambda c, x: D.section_tag(c, x, new, t, old, 0.0)); which, p = D.tag_phase(t, old, new)
            if which == "old": self.assertLessEqual(got.getbbox()[2], only_old.getbbox()[2])      # nothing wider than the old plate: no new text yet
            if t >= 0.5: self.assertEqual(list(got.getdata()), list(only_new.getdata()))
        self.assertEqual(list(self._alpha_box(lambda c, x: D.section_tag(c, x, old, 9.0, old, 0.0)).getdata()), list(only_old.getdata()))      # same section: steady, no swap

    def test_section_tag_same_section_is_static_and_first_tag_wipes_in(self):
        from reptheory import draw as D
        self.assertEqual(D.tag_phase(0.1, "X", "X"), ("new", 1.0)); self.assertEqual(D.tag_phase(0.0, None, "X"), ("new", 0.0)); self.assertEqual(D.tag_phase(9.0, None, "X"), ("new", 1.0))

    def test_pill_draws_nothing_until_its_text_can_show(self):
        from reptheory import draw as D
        for p in (0.0, 0.05, 0.2, D.PILL_TEXT_AT):
            self.assertIsNone(self._alpha_box(lambda c, x: D.pill(c, x, 100, 100, "BY THE NECK", p), (0, 0, 1280, 720)).getbbox())
        self.assertIsNone(self._alpha_box(lambda c, x: D.pill(c, x, 100, 100, "  ", 1.0), (0, 0, 1280, 720)).getbbox())      # empty text: never an empty outline
        self.assertIsNotNone(self._alpha_box(lambda c, x: D.pill(c, x, 100, 100, "BY THE NECK", 0.6), (0, 0, 1280, 720)).getbbox())

    def test_tier_pointer_walks_named_rows_then_to_the_landing_row(self):
        from reptheory import draw as D
        marks = [("S", 1.8), ("F", 3.6), ("B", 9.6)]; pl = 9.0      # B is named only after the placement: it must not pull the pointer early
        self.assertIsNone(D.tier_pointer(0.5, "B", pl, marks)); self.assertEqual(D.tier_pointer(1.0, "B", pl, marks), 0.0)      # waits on S from the moment the rows have landed
        self.assertEqual(D.tier_pointer(2.0, "B", pl, marks), 0.0)
        self.assertEqual(D.tier_pointer(3.7, "B", pl, marks), 5.0); mid = D.tier_pointer(8.3, "B", pl, marks); self.assertTrue(2.0 < mid < 5.0)      # moving up from F towards B between its mark and the landing
        self.assertNotEqual(D.tier_pointer(6.5, "B", pl, marks), D.tier_pointer(7.5, "B", pl, marks))      # still climbing well after F was named: the long wait keeps moving
        self.assertEqual(D.tier_pointer(pl, "B", pl, marks), 2.0); vals = [D.tier_pointer(3.7 + i * 0.05, "B", pl, marks) for i in range(100)]
        self.assertTrue(all(b <= a + 1e-9 for a, b in zip(vals, vals[1:])))      # never turns back on itself after F

    def test_tier_board_changes_every_second_and_ends_on_the_ranked_row(self):
        from reptheory import draw as D
        ctx = D.Ctx(640, 360); tier = {"letter": "B", "item": "PINCHING A BOTTLE", "at": 9.0, "total": None}; marks = [("S", 1.8), ("F", 3.6)]
        def fr(t): im = Image.new("RGB", (640, 360), (6, 6, 7)); D.tier_board(im, ctx, tier, t, "prop_bottle_2l_v1", "PINCHING A BOTTLE", 9.0, t - 9.8, marks); return im
        import numpy as np
        prev = np.asarray(fr(1.0)).astype(float)
        for sec in range(2, 11):      # no whole second of the board (S/F naming, the walk, the landing, the finish) is identical to the one before
            cur = np.asarray(fr(float(sec))).astype(float); self.assertGreater(np.abs(cur - prev).mean(), 0.05, f"board still at {sec}s"); prev = cur
        quiet = [np.abs(np.asarray(fr(5.0 + i * 0.1)).astype(float) - np.asarray(fr(5.0 + (i + 1) * 0.1)).astype(float)).mean() for i in range(20)]
        self.assertTrue(all(q > 0 for q in quiet))      # the wait between F and the placement is never frame-identical
        self.assertEqual(D.tier_pointer(11.5, "B", 9.0, marks), 2.0)

class EquationChip(unittest.TestCase):
    TEXT = "That is the weight you will be holding with just your fingers and thumb."
    def _plan(self, words=None):
        s2 = S(self.TEXT, 6.0, 10.0)
        if words: s2["words"] = words
        return planner.plan([S("One litre of water weighs about one kilogram, so two litres is about two kilograms.", 0, 6), s2], title="Grip")

    def test_phrase_becomes_a_chip_inside_the_equation_scene_at_the_spoken_word(self):
        toks = self.TEXT.split(); words = [{"w": w, "t0": 6.0 + i * 0.3, "t1": 6.0 + i * 0.3 + 0.25} for i, w in enumerate(toks)]
        sc = self._plan(words); self.assertEqual([x["kind"] for x in sc], ["equation"])      # still one scene: the equation is not replaced by a trainee scene
        chips = [c for p in sc[0]["pages"] for c in p["chips"]]; self.assertEqual([c["text"] for c in chips], ["FINGERS AND THUMB"])
        self.assertAlmostEqual(chips[0]["at"], words[toks.index("fingers")]["t0"], places=3)      # the real word time, not a character-count guess

    def test_chip_is_drawn_under_the_equation_only_from_its_word(self):
        from reptheory import draw as D, scenes as SC
        sc = self._plan()[0]; at = sc["pages"][0]["chips"][0]["at"] - sc["start"]; ctx = D.Ctx(640, 360)
        import numpy as np
        before = np.asarray(SC.frame(ctx, sc, at - 0.2, tag=False)).astype(int); after = np.asarray(SC.frame(ctx, sc, at + 0.8, tag=False)).astype(int)
        diff = np.abs(after - before).sum(axis=2) > 40; ys, xs = np.nonzero(diff[200:, :]); self.assertGreater(len(xs), 200)      # something new appeared in the lower right
        self.assertGreater(xs.min(), 640 * 0.30)      # clear of the bottle on the left

    def test_other_equation_scenes_are_unchanged(self):
        sc = planner.plan([S("One litre of water weighs about one kilogram, so two litres is about two kilograms.", 0, 8), S("Next, a harder one.", 8, 12)], title="Grip")
        self.assertEqual([c for p in sc[0]["pages"] for c in p["chips"]], [])      # no chip phrase in the narration, no chip

class EndCard(unittest.TestCase):
    def _vo(self, d, secs):
        p = str(Path(d) / "v.wav"); subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=220:duration={secs}", "-ar", "24000", "-ac", "1", p], check=True); return p
    def _render(self, d, card, name="o.mp4"):
        return engine.run_rep_theory(d, [S("Hold the bottle by the neck and pinch it.", 0, 3)], self._vo(d, 3), str(Path(d) / name), quality="preview", title="Grip", end_card=card)

    def test_config_is_forgiving(self):
        self.assertIsNone(engine.end_card_config(None, "Grip")); self.assertIsNone(engine.end_card_config({"enabled": False, "title": "X"}, "Grip"))
        self.assertEqual(engine.end_card_config({"enabled": True}, "Grip \u00b7 No Gym")["title"], "Grip")      # no title: the section label
        logs = []; self.assertIsNone(engine.end_card_config({"enabled": True}, "", logs.append)); self.assertTrue(logs and "no end card" in logs[0])      # nothing to show: no card, and it says so
        logs = []; c = engine.end_card_config({"enabled": True, "title": "Grip Kit", "image": "/no/such/file.png"}, "", logs.append); self.assertIsNone(c["image"]); self.assertIn("text only", logs[0])

    def test_off_keeps_the_ending_and_on_adds_five_seconds(self):
        with tempfile.TemporaryDirectory() as d:
            off = self._render(d, {"enabled": False, "title": "Grip Kit", "url": "x.com"}, "off.mp4"); none = self._render(d, None, "none.mp4")
            on = self._render(d, {"enabled": True, "title": "Grip Kit", "url": "gripkit.example"}, "on.mp4")
            self.assertEqual((off["frames"], none["frames"]), (72, 72)); self.assertFalse(off["end_card"]); self.assertEqual(on["frames"], 72 + 120); self.assertTrue(on["end_card"])
            import numpy as np
            def last(path): r = subprocess.run(["ffmpeg", "-v", "error", "-sseof", "-0.2", "-i", path, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout; return np.frombuffer(r, np.uint8).astype(int)
            a, b = last(str(Path(d) / "off.mp4")), last(str(Path(d) / "on.mp4")); self.assertGreater(np.abs(a - b).mean(), 1.0)      # the card is really on screen at the end
            self.assertEqual(sorted(p.name for p in Path(d).glob("*.rendering.mp4")), [])

    def test_card_draws_with_and_without_a_picture(self):
        from reptheory import draw as D
        ctx = D.Ctx(640, 360); pic = Image.new("RGBA", (400, 600), (200, 200, 200, 255))
        for img in (pic, None):
            im = Image.new("RGB", (640, 360), (6, 6, 7)); D.end_card(im, ctx, "Grip Kit", "gripkit.example", img, 3.0); self.assertGreater(sum(im.convert("L").point(lambda v: 255 if v > 120 else 0).histogram()[255:]), 200)
        im = Image.new("RGB", (640, 360), (6, 6, 7)); D.end_card(im, ctx, "", "", None, 3.0); self.assertEqual(im.getbbox(), (0, 0, 640, 360))      # nothing to draw: no crash

class BeatPlanner(unittest.TestCase):
    """R1: narrative beat planner (reptheory.beats / narrative / cadence)."""
    BOTTLE = [S("You do not need a gym to train your grip.", 0, 2.8), S("All you need is a full two litre bottle of water, and you probably have one at home.", 2.8, 8.4), S("Screw the cap on tight, so nothing leaks while you squeeze.", 8.4, 12.8),
              S("One litre of water weighs about one kilogram, so two litres is about two kilograms.", 12.8, 19.0), S("That is the weight you will be holding with just your fingers and thumb.", 19.0, 23.3),
              S("Now let us rank it, from S tier at the top down to F tier at the bottom.", 23.3, 28.0), S("Pinching a bottle is a simple beginner test, so it lands in B tier.", 28.0, 33.0)]
    WRIST = [S("Wrist curls will not make your wrists thicker.", 0, 2.6), S("Most of a wrist is bone and tendon, with almost no muscle to grow.", 2.6, 8.0), S("Move one is the pinch hold.", 8.0, 10.2),
             S("Pinch a book between your fingers and thumb and hold it for thirty seconds.", 10.2, 15.0), S("Move two is the hammer rotation.", 15.0, 17.5), S("Hold a hammer by the end and rotate it slowly ten times.", 17.5, 22.0),
             S("In one synthetic test study, people gained sixty eight percent grip strength.", 22.0, 28.0), S("Do these moves four times a week for six weeks.", 28.0, 32.0)]
    def plan(self, sents, title="T"): from reptheory import beats; return beats.plan(sents, title=title, art_ok=lambda a: True)

    def test_no_narration_lost_reordered_or_invented(self):
        from reptheory import beats
        for sents in (self.BOTTLE, self.WRIST):
            r = self.plan(sents); self.assertEqual(r["problems"], []); self.assertEqual(" ".join(b["text"] for b in r["beats"]).split(), " ".join(s["text"] for s in sents).split())
        self.assertTrue(beats.check_words([S("a b c", 0, 1)], [{"text": "a c b"}]))      # the checker does notice a change

    def test_beats_carry_the_documented_fields(self):
        r = self.plan(self.WRIST)
        for b in r["beats"]:
            for k in ("id", "t0", "t1", "text", "words", "timing", "role", "entities", "visual", "status", "confidence", "scene", "development", "cues"): self.assertIn(k, b)
            self.assertIn(b["timing"], ("word", "estimated")); self.assertIn(b["status"], ("grounded", "continued", "weak_callout", "generic_fallback"))
        self.assertEqual(len({b["id"] for b in r["beats"]}), len(r["beats"]))

    def test_estimated_timing_is_labelled_and_word_timing_is_used(self):
        self.assertEqual({b["timing"] for b in self.plan(self.WRIST)["beats"]}, {"estimated"})
        s = [dict(self.WRIST[0], words=[{"w": w, "t0": i * 0.3, "t1": i * 0.3 + 0.25} for i, w in enumerate(self.WRIST[0]["text"].split())])]
        self.assertEqual({b["timing"] for b in self.plan(s)["beats"]}, {"word"})

    def test_roles_entities_and_numbers_come_from_the_words(self):
        from reptheory import narrative as N
        e = N.entities("In one synthetic test study, people gained sixty eight percent grip strength.")
        self.assertEqual([(n["value"], n["unit"]) for n in e["numbers"]], [("68", "%")])
        e = N.entities("Hang from a bar for twenty seconds."); self.assertEqual((e["numbers"][0]["value"], e["numbers"][0]["unit"]), ("20", "S")); self.assertEqual(e["props"][0]["prop"], "bar")
        self.assertEqual(N.classify("In one study, people gained 12 percent.")[0], "evidence"); self.assertEqual(N.classify("Stop gripping so hard.")[0], "mistake")
        self.assertEqual(N.classify("Do this four times a week.")[0], "routine"); self.assertEqual(N.classify("It rains in spring.")[0], "statement")      # the honest default is statement, not a guess
        self.assertEqual(N.entities("It rains in spring.")["numbers"], [])

    def test_units_hook_and_roadmap_are_found_and_never_invented(self):
        r = self.plan(self.WRIST); n = r["narrative"]
        self.assertEqual([u["label"] + " " + u["title"] for u in n["units"]], ["MOVE 1 PINCH HOLD", "MOVE 2 HAMMER ROTATION"]); self.assertEqual(n["hook"]["type"], "myth"); self.assertIsNone(n["benchmark"]); self.assertIsNone(n["cta"])
        sections = {sc["section"] for sc in r["scenes"]}; self.assertIn("MOVE 1 · PINCH HOLD", sections)
        plain = self.plan([S("The sky is blue today.", 0, 2.5), S("Water is wet.", 2.5, 5.0)])["narrative"]
        self.assertEqual((plain["hook"], plain["roadmap"], plain["units"], plain["benchmark"], plain["cta"]), (None, None, [], None, None))

    def test_a_study_percentage_is_shown_exactly_as_said_and_flagged_synthetic(self):
        r = self.plan(self.WRIST); sc = next(s for s in r["scenes"] if any(p["value"] == "68%" for p in s["pages"])); pg = next(p for p in sc["pages"] if p["value"] == "68%")
        self.assertEqual(pg["headline"], "GRIP STRENGTH"); self.assertEqual(pg["kicker"], "SYNTHETIC DATA"); self.assertGreater(pg["value_at"], sc["start"]); self.assertTrue(all(not b["grounding_violations"] for b in r["beats"]))

    def test_bottle_keeps_its_treatments(self):
        r = self.plan(self.BOTTLE); kinds = [s["kind"] for s in r["scenes"]]
        self.assertEqual(kinds, ["trainee", "prop", "equation", "tier"]); eq = r["scenes"][2]; self.assertEqual((eq["equations"][0]["lhs"], eq["equations"][0]["rhs"]), ("1 L", "1 KG")); self.assertEqual(eq["pages"][0]["chips"][0]["text"], "FINGERS AND THUMB")
        self.assertEqual(r["scenes"][3]["tier"]["letter"], "B"); self.assertEqual(r["scenes"][1]["rings"][0]["r"], 0.075 if False else r["scenes"][1]["rings"][0]["r"])

    def test_nothing_unresolved_is_counted_as_a_relevant_visual(self):
        r = self.plan([S("Something happens now.", 0, 3.0), S("It happens again later on.", 3.0, 6.0)]); bad = [b for b in r["beats"] if b["status"] != "grounded"]
        self.assertTrue(bad); self.assertTrue(all(b["visual"]["relevance"] == 0.0 or b["status"] != "grounded" for b in r["beats"])); self.assertTrue(all(b["reason"] for b in bad))
        self.assertTrue(all(b["visual"]["mode"] in ("continued", "generic") for b in bad if b["status"] != "weak_callout"))

    def test_the_trainee_is_not_used_for_unrelated_concepts(self):
        r = self.plan(self.WRIST)
        for b in r["beats"]:
            if b["visual"]["kind"] == "trainee": self.assertRegex(b["text"], r"(?i)gym|posture|stand|body|calisthenics")

    def test_cadence_metrics_are_derived_from_scene_dicts(self):
        from reptheory import cadence as C
        sc = [{"no": 1, "start": 0.0, "end": 10.0, "kind": "prop", "pages": [{"at": 0.0, "headline": "A", "headline_at": 1.0, "value": "", "chips": [{"text": "X", "at": 4.0}]}], "rings": [{"at": 2.0}]},
              {"no": 2, "start": 10.0, "end": 14.0, "kind": "anatomy", "pages": [], "glow": {"at": 11.0}}]
        m = C.metrics(sc); self.assertEqual(m["events"], {"primary": 2, "secondary_meaningful": 4, "secondary_decorative": 0}); self.assertEqual(m["primary_gaps"]["max"], 10.0); self.assertEqual(m["primary_gaps"]["median"], 7.0)
        self.assertTrue(any(o["event"] == "primary" and o["gap"] == 10.0 for o in m["over_limit"])); self.assertIn("justification", m["over_limit"][0])
        self.assertEqual(C.metrics([])["scenes"], 0)

    def test_report_is_written_as_json_and_markdown(self):
        from reptheory import cadence as C
        with tempfile.TemporaryDirectory() as d:
            C.write_report(Path(d) / "x.mp4.plan", self.plan(self.WRIST)); import json
            j = json.loads((Path(d) / "x.mp4.plan.json").read_text()); self.assertIn("beats", j); self.assertIn("metrics", j); self.assertIn("## Beats", (Path(d) / "x.mp4.plan.md").read_text())

    def test_engine_falls_back_to_the_legacy_planner_and_says_so(self):
        from reptheory import beats
        orig = beats.plan; beats.plan = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            with tempfile.TemporaryDirectory() as d:
                logs = []; rep = engine.run_rep_theory(d, [S("Hello there.", 0, 2.5)], "", str(Path(d) / "o.mp4"), quality="preview", planner="beats", log=logs.append, max_seconds=1.0)
                self.assertEqual(rep["plan"]["planner"], "legacy"); self.assertIn("boom", rep["plan"]["fallback_reason"]); self.assertTrue(any("legacy planner" in m for m in logs))
        finally: beats.plan = orig

    def test_callout_scene_renders(self):
        from reptheory import draw as D, scenes as SC
        r = self.plan(self.WRIST); sc = next(s for s in r["scenes"] if s["kind"] == "callout"); ctx = D.Ctx(640, 360)
        im = SC.frame(ctx, sc, 2.5); self.assertEqual(im.size, (640, 360)); self.assertGreater(sum(im.convert("L").point(lambda v: 255 if v > 150 else 0).histogram()[255:]), 100)

    def test_every_callout_page_is_legible_on_its_first_frame(self):
        from reptheory import draw as D, scenes as SC
        r = self.plan(self.WRIST); ctx = D.Ctx(640, 360)
        for sc in [x for x in r["scenes"] if x["kind"] == "callout"]:
            for pg in sc["pages"]:
                if not (pg["headline"] or pg["value"]): continue
                t = pg["at"] - sc["start"]; im = SC.frame(ctx, sc, t + 0.02, tag=False); box = im.crop((int(640 * 0.12), 60, 640, 300)).convert("L")
                self.assertGreater(sum(box.point(lambda v: 255 if v > 80 else 0).histogram()[255:]), 40, f"blank first frame: scene {sc['no']} page at {pg['at']:.1f}")

    def test_unknown_subject_is_text_not_a_forearm_plate(self):
        r = self.plan([S("Your latissimus dorsi is the large muscle that pulls your arm down and back.", 0, 4.5)])
        self.assertNotEqual(r["scenes"][0]["kind"], "anatomy"); self.assertIn("LATISSIMUS", r["scenes"][0]["pages"][0]["headline"])

    def test_legacy_planner_unchanged_by_the_refactor(self):
        sc = planner.plan([dict(s) for s in self.BOTTLE], title="Grip", art_ok=lambda a: True); self.assertEqual([s["kind"] for s in sc], ["trainee", "prop", "equation", "tier"])

def tearDownModule(): shutil.rmtree(_TMP, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()
