"""Rep Theory variety: the code-drawn cards, the variety director on a 30-minute plan, the 3D clip variants and the label scale. No video is rendered, no Flow call, no network: scenes are planned from synthetic
narration and single frames are drawn at Preview size."""
from __future__ import annotations
import importlib, os, tempfile, time, unittest
from pathlib import Path

os.environ.setdefault("REP_THEORY_ASSET_DIR", tempfile.mkdtemp(prefix="rt_var_lib_"))

from PIL import Image, ImageDraw, ImageStat
from reptheory import beats as B, clip3d as C3, draw as D, library as L, planner as P, scenes as S, variety as V

def _art(name, kind, size=(600, 900)):
    if L.find(name): return
    im = Image.new("RGB", size, (0, 0, 0)); d = ImageDraw.Draw(im); d.ellipse((120, 80, size[0] - 120, size[1] - 80), fill=(190, 190, 190))
    p = Path(os.environ["REP_THEORY_ASSET_DIR"]) / f"src_{name}.png"; im.save(p); L.register(p, id=name, kind=kind, subject=name, prompt="test", source="supplied")

def setUpModule():
    for n, k in (("rep_stand_v1", "character"), ("rep_hang_v1", "character"), ("prop_bottle_2l_v1", "prop"), ("anat_forearm_v1", "anatomy")): _art(n, k)

def sentences(texts, per=3.0):
    out, t = [], 0.0
    for x in texts: n = len(x.split()); d = max(per, n / 2.4); out.append({"text": x, "start": t, "end": t + d}); t += d
    return out

def long_script(minutes=30):
    """Structured narration (parts, numbers, comparisons, sequences, muscles, claims) of the requested length, written only for this test."""
    parts = ["Part {n}: the {ex} in detail."]; body = [
        "Hold it for thirty seconds, three times, with one minute of rest between sets.",
        "The incline version is easier than the full push-up, so start there if you are new.",
        "First set your hands under your shoulders, then lower slowly, and finally push back up.",
        "Your triceps straighten the elbow and your chest does most of the pushing.",
        "Most people rush this, and that is why their progress stalls after a few weeks.",
        "Studies show that slow reps build the same muscle as heavy ones, which is good news at home.",
        "Keep your core tight, because a sagging back takes the work away from the muscles you want to train.",
        "Your lats pull the body up while your biceps help bend the elbow.",
        "Do twelve reps with good form, rather than twenty with bad form.",
        "Rest for two days before you train the same muscle again.",
        "The squat loads your quads and glutes, and your calves keep you balanced.",
        "Three sets of eight is a simple place to start for every exercise in this plan.",
        "Never train through sharp pain, and stop the set if your form breaks down.",
        "The key point is that small improvements every week add up to a big change over a year."]
    exs = ["push-up", "pull-up", "squat", "plank", "deadlift", "curl", "overhead press", "calf raise"]; texts, n = [], 0; target_words = int(minutes * 145)
    while sum(len(t.split()) for t in texts) < target_words:
        texts.append(parts[0].format(n=n // 8 + 1, ex=exs[(n // 8) % len(exs)]) if n % 8 == 0 else body[(n * 5 + n // 3) % len(body)]); n += 1
    return texts

class Cards(unittest.TestCase):
    def setUp(self): self.ctx = D.Ctx(1280, 720)

    def _scene(self, text):
        sc = P.plan(sentences([text]))[0]; sc["text"] = text; return sc

    def test_stat_from_the_stated_number_only(self):
        sc = self._scene("Hold it for thirty seconds, three times."); sc["words"] = sc.get("words") or []
        st = V._stat(sc, "Hold it for thirty seconds, three times.")
        self.assertEqual((st["value"], st["unit"], st["mode"]), (30.0, "S", "full"))
        self.assertIsNone(V._stat(sc, "Stand tall and keep squeezing."))
        pct = V._stat(sc, "That is a twelve percent drop in strains."); self.assertEqual((pct["unit"], pct["mode"]), ("%", "fill"))

    def test_versus_needs_two_stated_sides(self):
        sc = {"start": 0.0, "end": 4.0, "words": []}
        v = V._versus(sc, "The incline push-up is easier than the full push-up."); self.assertTrue(v and v["a"]["text"] and v["b"]["text"] and v["a"]["text"] != v["b"]["text"])
        self.assertIsNone(V._versus(sc, "Keep your core tight."))
        self.assertIsNone(V._versus(sc, "Your lats pull the body up while your biceps help bend the elbow."), "two muscles working together are not a comparison")

    def test_a_bare_figure_scene_gets_its_words_as_a_takeaway(self):
        ws = [{"w": w, "t0": 0.3 * i, "t1": 0.3 * i + 0.25} for i, w in enumerate("Your triceps straighten the elbow and your shoulders stabilise".split())]
        sc = {"start": 0.0, "end": 6.0, "words": ws, "text": " ".join(w["w"] for w in ws), "kind": "trainee", "art": "rep_stand_v1", "pages": [{"at": 0, "headline": "", "headline_at": 0, "value": "", "chips": [], "kicker": ""}], "decisions": [], "no": 1, "section": "T", "topic": "T"}
        self.assertIn("takeaway", V.evidence(sc))

    def test_steps_need_a_spoken_sequence(self):
        sc = {"start": 0.0, "end": 6.0, "words": []}
        it = V._steps(sc, "First set your hands under your shoulders, then lower slowly, and finally push back up.")
        self.assertEqual(len(it), 3); self.assertEqual([i["text"].split()[0] for i in it], ["SET", "LOWER", "PUSH"])
        self.assertIsNone(V._steps(sc, "Lower slowly."))

    def _frames(self, sc, ts):
        return [S.frame(self.ctx, sc, t, tag=False) for t in ts]

    def _assert_drawn(self, im): self.assertGreater(ImageStat.Stat(im.convert("L")).stddev[0], 8, "a card frame must not be blank")

    def test_every_card_draws_and_changes_over_time(self):
        txt = {"stat": "Hold it for thirty seconds, three times.", "versus": "The incline push-up is easier than the full push-up.", "steps": "First set your hands, then lower slowly, and finally push back up.",
               "takeaway": "Small improvements every week add up to a big change over a year."}
        for look, text in txt.items():
            ws = [{"w": w, "t0": 0.2 * i, "t1": 0.2 * i + 0.18} for i, w in enumerate(text.split())]; sc = {"start": 0.0, "end": 6.0, "words": ws, "text": text, "kind": "callout", "no": 1, "pages": [{"at": 0.0, "headline": "HOLD", "headline_at": 0.0, "value": "", "chips": [], "kicker": ""}],
                                                                                               "section": "T", "topic": "T", "decisions": [], "art": "", "prop": "", "chapter": ""}
            payload = {"stat": V._stat, "versus": V._versus, "steps": V._steps}.get(look, lambda s, t: V._takeaway(s, t, True, "claim"))(sc, text); self.assertTrue(payload, look)
            sc[look] = payload; sc["kind"] = look; a, b = self._frames(sc, (0.2, 5.0)); self._assert_drawn(b); self.assertNotEqual(a.tobytes(), b.tobytes(), f"{look} must develop")

    def test_chapter_banner_shows_then_leaves(self):
        sc = {"start": 0.0, "end": 8.0, "kind": "callout", "no": 1, "pages": [], "section": "T", "topic": "T", "decisions": [], "art": "", "prop": "", "chapter_card": {"n": 2, "of": 5, "title": "WEEK TWO"}}
        on, off = self._frames(sc, (1.2, 6.0)); self.assertNotEqual(on.tobytes(), off.tobytes())

class Director(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        t0 = time.time(); cls.texts = long_script(30); cls.sents = sentences(cls.texts); cls.total = cls.sents[-1]["end"]
        cls.res = B.plan(cls.sents, title="Gym", per_beat=True); cls.plan_s = time.time() - t0; cls.scenes = cls.res["scenes"]
        cls.free = [sc["kind"] in V.UPGRADABLE for sc in cls.scenes]; cls.m = V.direct(cls.scenes, total_s=cls.total)

    def test_thirty_minutes_plan_in_reasonable_time(self):
        self.assertGreater(self.total, 25 * 60); self.assertLess(self.plan_s, 120, f"planning 30 minutes took {self.plan_s:.0f} s")

    def test_no_look_runs_more_than_twice_among_free_scenes(self):
        run = 1
        for i in range(1, len(self.scenes)):
            a, b = self.scenes[i - 1], self.scenes[i]
            run = run + 1 if (a.get("look") == b.get("look") and a.get("look") in ("3d", "flow", "stat", "steps", "versus", "takeaway")) else 1
            self.assertLessEqual(run, 2, f"scene {b['no']}: {b.get('look')} three times in a row")

    def test_every_five_minutes_shows_several_looks(self):
        for k, n in enumerate(self.m["distinct_per_5min"][:6]): self.assertGreaterEqual(n, 4, f"minutes {5 * k}-{5 * k + 5}: only {n} distinct looks ({self.m['looks']})")

    def test_new_looks_are_used_and_supported_by_the_words(self):
        looks = self.m["looks"]
        for l in ("3d", "flow", "stat", "versus", "steps"): self.assertGreater(looks.get(l, 0), 0, f"{l} never used: {looks}")
        for sc in self.scenes:
            if sc.get("look") == "stat": self.assertTrue(sc["stat"]["value"] > 0 and sc["text"])
            if sc.get("want3d"): self.assertTrue(C3.groups_for(sc["text"])[0], "a 3D clip only where a muscle or exercise is named")

    def test_budgets_and_spacing(self):
        d3 = [sc for sc in self.scenes if sc.get("want3d")]; gap = min(20.0, max(6.0, self.total / 4))
        for a, b in zip(d3, d3[1:]): self.assertGreaterEqual(b["start"] - a["end"], gap - 1e-6)
        self.assertLessEqual(sum(1 for sc in self.scenes if sc.get("look") == "flow"), max(2, int(self.total / 30)))
        for a, b in zip(self.scenes, self.scenes[1:]): self.assertFalse(a.get("want3d") and b.get("want3d"))
        styles = {sc["cam3d"] for sc in d3}; self.assertGreaterEqual(len(styles), min(4, len(d3)))

    def test_grounded_scenes_are_never_replaced(self):
        for sc in self.scenes:
            if sc.get("was_kind"): self.assertIn(sc["was_kind"], V.UPGRADABLE)

    def test_parts_get_a_chapter_banner_with_progress(self):
        cards = [sc for sc in self.scenes if sc.get("chapter_card")]; self.assertGreaterEqual(len(cards), 5); self.assertEqual([c["chapter_card"]["n"] for c in cards], list(range(2, 2 + len(cards))))
        self.assertTrue(all(c["chapter_card"]["of"] == len(cards) + 1 for c in cards)); self.assertGreaterEqual(self.m["chapters"], 6)

    def test_made_up_data_stays_text(self):
        sc = P.plan(sentences(["That is made up data, used only to test this video planner."]))[0]; sc["text"] = "That is made up data, used only to test this video planner."
        V.direct([sc], total_s=5.0); self.assertEqual(sc["kind"], sc["kind"]); self.assertNotIn(sc.get("look"), ("3d", "flow", "stat"))

class Clip3d(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        BM = importlib.import_module("health_cinema.bodymap")      # imported by name: only the app and tests of health_cinema may import it literally (see test_health_cinema_style)
        m, a = C3.model_paths()
        if m is None: raise unittest.SkipTest("gym body model not built")
        cls.A = BM.load_anchors(a)

    def test_styles_differ_but_name_the_same_muscles(self):
        specs = {s: C3.spec_for("Your lats pull the body up while your biceps help bend the elbow.", 6.0, self.A, s) for s in C3.STYLES}
        self.assertEqual({v[1] for v in specs.values()}, {"Lats + Biceps"}); az = {s: tuple(k["az"] for k in v[0]["camera"]) for s, v in specs.items()}; self.assertEqual(len(set(az.values())), 3)      # push and xray share a camera
        self.assertLess(specs["xray"][0]["layers"]["Layer_Skin"][0][1], specs["push"][0]["layers"]["Layer_Skin"][0][1]); self.assertGreater(specs["xray"][0]["layers"]["Layer_Skeleton"][0][1], specs["push"][0]["layers"]["Layer_Skeleton"][0][1])
        self.assertTrue(all(v[0]["label_scale"] > 1 for v in specs.values()))

    def test_label_scale_makes_labels_bigger(self):
        O = importlib.import_module("health_cinema.overlay")
        im = Image.new("RGB", (800, 450), (10, 10, 20)); lb = [{"a": 1.0, "xy": (200, 200), "side": "right", "text": "Triceps", "t": 0.0}]
        a, b = O.draw_labels(im, lb, 450), O.draw_labels(im, lb, 450, 1.5); box = lambda x: Image.eval(x.convert("L"), lambda v: 255 if v > 60 else 0).getbbox()
        self.assertGreater(box(b)[2] - box(b)[0], box(a)[2] - box(a)[0])

    def test_clip_lengths_are_bucketed_for_reuse(self):
        import math; self.assertEqual([min(12.0, max(2.0, 2.0 * math.ceil(s / 2.0))) for s in (2.1, 5.0, 6.0, 26)], [4.0, 6.0, 6.0, 12.0])

class Shipping(unittest.TestCase):
    ROOT = Path(__file__).resolve().parent

    def test_the_model_ships_with_its_licence_and_the_build_lists_it(self):
        from reptheory import packaging
        names = sorted(Path(s).name for s, d in packaging.model_data_files(self.ROOT)); self.assertEqual(names, ["LICENSE_Z-Anatomy.txt", "NOTICE.txt", "anchors_gym.json", "body_gym.glb"])
        self.assertIn("CC BY-SA 4.0", (self.ROOT / "assets/reptheory_3d/NOTICE.txt").read_text(encoding="utf-8")); self.assertIn("model_data_files", (self.ROOT / "VideoGenerator.spec").read_text(encoding="utf-8"))
        self.assertLess((self.ROOT / "assets/reptheory_3d/body_gym.glb").stat().st_size, 20_000_000)

    def test_model_is_found_in_the_shipped_folder_or_the_env_override(self):
        m, a = C3.model_paths(); self.assertTrue(m and a and m.name == "body_gym.glb")
        old = os.environ.get("REP_THEORY_3D_DIR")
        try:
            os.environ["REP_THEORY_3D_DIR"] = tempfile.mkdtemp(); self.assertEqual(C3.model_paths(), (None, None)); self.assertFalse(C3.available())      # an empty exact folder: unavailable, never a crash
            os.environ["REP_THEORY_3D_DIR"] = str(self.ROOT / "assets/reptheory_3d"); self.assertEqual(C3.model_paths()[0].parent, self.ROOT / "assets/reptheory_3d")
        finally:
            if old is None: os.environ.pop("REP_THEORY_3D_DIR", None)
            else: os.environ["REP_THEORY_3D_DIR"] = old

    def test_panel_carries_the_credit(self):
        from reptheory import theme as T; self.assertIn("Z-ANATOMY", T.MODEL_CREDIT); self.assertIn("CC BY-SA", T.MODEL_CREDIT)

if __name__ == "__main__": unittest.main()
