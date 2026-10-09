"""Modern Tech News (modern_tech/): wording-based concepts and evidence framing, guidance for the existing VisualDirector,
and the deterministic refinement of its VisualPlan (rhythm, product-first prompts, UI routing, filler, technical
progression). The output is the Normal 4-column CSV and the script is rebuilt word for word; nothing runs unless the
project chose Modern Tech News."""

import csv
import tempfile
import unittest
from pathlib import Path

from modern_tech import classify_concept, classify_evidence, editorial_guidance, refine_plan, smart_editing_settings
from visual_director.schema import parse_visual_plan

ROWS = [  # narration, asset_type, prompt
    ("Samsung's next foldable could finally solve the crease problem, and early reports suggest the company is testing a redesigned hinge.",
     "stock_video", "modern smartphone technology"),
    ("The new hinge uses two thin layers that reduce pressure on the display and allow a flatter screen when the phone opens.",
     "video", "futuristic circuit board glowing"),
    ("Apple announced the iPhone 17 Pro on stage in Cupertino.", "stock_video", "person holding phone"),
    ("The new iOS 26 lock screen widgets can now be edited with a long press.", "stock_video", "person using smartphone app"),
    ("Leaks suggest the Pixel 11 Fold will be thinner.", "image", "Pixel 11 Fold concept render on a white desk"),
    ("Analysts expect sales to rise.", "stock_video", "busy city street at night"),
]


def plan(rows=ROWS):
    return parse_visual_plan({"title": "t", "scenes": [
        {"scene_id": i + 1, "narration": n, "visual_goal": n, "visual_description": q, "asset_type": a,
         "provider_preference": {"video": "flow_video", "image": "flow_image"}.get(a, a),
         **({"search_queries": q.split("||")} if a.startswith(("stock", "youtube")) else {})}
        for i, (n, a, q) in enumerate(rows)]})


class Classification(unittest.TestCase):
    def test_evidence_framing(self):
        self.assertEqual(classify_evidence("Apple announced the new chip"), "CONFIRMED")
        self.assertEqual(classify_evidence("Bloomberg reports Apple is testing it"), "REPORTED")
        self.assertEqual(classify_evidence("Leaks suggest a thinner hinge"), "LEAKED")
        self.assertEqual(classify_evidence("Rumors indicate a delay"), "RUMORED")
        self.assertEqual(classify_evidence("Analysts expect strong sales"), "ANALYSIS")
        self.assertEqual(classify_evidence("It could change everything"), "SPECULATIVE")
        self.assertEqual(classify_evidence("The phone is made of titanium"), "")

    def test_concepts(self):
        self.assertEqual(classify_concept("The Fold 8 versus the iPhone Fold"), "COMPARISON")
        self.assertEqual(classify_concept("The hinge uses two layers of glass"), "TECHNICAL_EXPLAINER")
        self.assertEqual(classify_concept("Samsung unveiled the phone"), "NEWS")
        self.assertEqual(classify_concept("Shipments grew across the industry"), "MARKET_CONTEXT")
        self.assertEqual(classify_concept("The Galaxy Z Fold 8 is here"), "PRODUCT")
        self.assertEqual(classify_concept("Ultimately, it remains to be seen"), "CONCLUSION")

    def test_guidance_names_the_scripts_own_subjects_and_rules(self):
        g = editorial_guidance("Samsung's Galaxy Z Fold 8 arrives. The iPhone 17 Pro follows.")
        self.assertIn("Galaxy Z Fold 8", g)
        self.assertIn("iPhone 17 Pro", g)
        self.assertIn("1-2.5 s", g)
        self.assertNotIn("Galaxy", editorial_guidance("A story about sleep."), "no facts are hard-coded")


class Refinement(unittest.TestCase):
    def setUp(self):
        self.p = plan()
        self.changes = refine_plan(self.p)
        self.scenes = self.p.scenes

    def by_text(self, words):
        return next(s for s in self.scenes if words in s.narration)

    def test_script_is_rebuilt_word_for_word_and_numbered(self):
        self.assertEqual(" ".join(s.narration for s in self.scenes), " ".join(n for n, _, _ in ROWS))
        self.assertEqual([s.scene_id for s in self.scenes], list(range(1, len(self.scenes) + 1)))

    def test_pacing(self):
        hook = [s for s in self.scenes if "foldable" in s.narration or "crease" in s.narration or "hinge." in s.narration]
        self.assertTrue(all(len(s.narration.split()) / 2.5 <= 3.2 for s in hook), "hook shots stay ~1-2.5 s")
        self.assertGreater(len(self.scenes), len(ROWS))
        self.assertTrue(all(1.5 <= s.duration <= 6.0 for s in self.scenes))
        short = self.by_text("Analysts expect")
        self.assertEqual(short.narration, ROWS[5][0], "a short line is not split")

    def test_generic_prompt_becomes_product_first(self):
        first = self.scenes[0]
        self.assertEqual(first.asset_type, "stock_image", "no known product: a still of the company's new device")
        self.assertIn("Samsung new foldable device", first.search_queries[0], "unknown product: company + category")
        self.assertEqual(first.fallbacks, [], "never a generic or Flow fallback")
        self.assertNotIn("modern smartphone", first.search_queries[0])

    def test_event_narration_goes_to_official_footage(self):
        s = self.by_text("Apple announced")
        self.assertEqual(s.asset_type, "youtube_video")
        self.assertIn("Apple iPhone 17 Pro official launch event", s.search_queries, "company + product")
        self.assertIn("stock_image", s.fallbacks)

    def test_ui_narration_goes_to_real_footage(self):
        s = self.by_text("iOS 26")
        self.assertEqual(s.asset_type, "youtube_video")
        self.assertTrue(any("demo" in q or "screen recording" in q for q in s.search_queries))

    def test_technical_scene_progresses_and_filler_is_replaced(self):
        tech = [s for s in self.scenes if s.narration in ROWS[1][0]]
        self.assertGreater(len(tech), 1)
        self.assertEqual(tech[0].asset_type, "stock_image", "the generic AI circuit board became a still of the company's device")
        self.assertIn("Samsung new foldable device hinge", tech[0].search_queries[0])
        self.assertEqual(tech[1].asset_type, "image")
        self.assertIn("technical cutaway diagram of the hinge", tech[1].visual_description)
        self.assertFalse(any(s.asset_type == "video" for s in tech[1:]), "no extra Flow video credits")

    def test_unconfirmed_product_keeps_its_ai_reconstruction(self):
        s = self.by_text("Pixel 11 Fold")
        self.assertEqual((s.asset_type, s.visual_description), ("image", ROWS[4][2]))

    def test_no_subject_leaves_the_scene_and_explains_why(self):
        s = self.by_text("Analysts expect")
        self.assertEqual(s.search_queries, ["busy city street at night"])

    def test_decisions_are_explained(self):
        kinds = {c["kind"] for c in self.changes}
        self.assertTrue({"still", "motion", "pacing"} <= kinds)
        c = next(c for c in self.changes if c["kind"] == "still")
        self.assertTrue(c["before"] and c["after"] and c["concept"] and isinstance(c["scene"], int))


def queries(scene):
    return " || ".join(scene.search_queries) or scene.visual_description


class FlowCost(unittest.TestCase):
    """Modern Tech never adds Flow work: no new Flow video, and one original Flow scene stays at most one generation."""

    LONG = "The new hinge uses two thin layers that reduce pressure on the display and allow a flatter screen when the phone opens."

    def check(self, rows):
        from modern_tech import flow_generations

        p = plan(rows)
        before = flow_generations(p)
        refine_plan(p)
        after = flow_generations(p)
        self.assertLessEqual(after["video"], before["video"])
        self.assertLessEqual(after["video"] + after["image"], before["video"] + before["image"])
        self.assertLessEqual(after["fallback"], before["fallback"])
        return p

    def test_one_flow_video_scene_split_is_at_most_one_generation(self):
        p = self.check([("Samsung's Galaxy Z Fold 8 is official.", "stock_video", "Galaxy Z Fold 8"),
                        (self.LONG, "video", "macro shot of a precision steel hinge mechanism slowly folding, studio light")])
        self.assertGreater(len(p.scenes), 2, "the long scene was still split for rhythm")
        self.assertLessEqual(sum(s.asset_type in ("video", "image") for s in p.scenes), 1)

    def test_generic_ai_scene_split_uses_its_one_generation_for_the_diagram_at_most(self):
        p = self.check([("Samsung's Galaxy Z Fold 8 is official.", "stock_video", "Galaxy Z Fold 8"),
                        (self.LONG, "video", "futuristic circuit board glowing")])
        self.assertEqual(sum(s.asset_type == "video" for s in p.scenes), 0)
        self.assertEqual(sum(s.asset_type == "image" for s in p.scenes), 1, "the freed generation became the diagram")

    def test_stock_scenes_never_gain_flow(self):
        p = self.check([("Samsung's Galaxy Z Fold 8 is official.", "stock_video", "Galaxy Z Fold 8"),
                        (self.LONG, "stock_video", "close-up of a phone hinge")])
        self.assertEqual(sum(s.asset_type in ("video", "image") for s in p.scenes), 0, "no diagram generation from a stock scene")

    def test_ai_scene_without_a_subject_is_not_multiplied(self):
        line = "Imagine a world where every surface in your home could become a screen that folds away when you are done."
        p = self.check([("Meanwhile, the weather turned cold.", "stock_video", "snowy street"),
                        (line, "video", "a living room whose walls fold into screens, cinematic")])
        self.assertEqual([s.narration for s in p.scenes if s.asset_type == "video"], [line], "one shot, one generation")

    def test_whole_sample_is_cost_neutral(self):
        self.check(ROWS)


SAMSUNG = ("Samsung's Galaxy Z Fold 8 is finally here.", "stock_video", "folding phone on a table")


class SubjectContinuity(unittest.TestCase):
    def refined(self, rows):
        """The query of the shot that starts each original line (splits may add shots in between)."""
        p = plan(rows)
        refine_plan(p)
        return [queries(next(s for s in p.scenes if r[0].startswith(s.narration))) for r in rows]

    def test_product_established_then_component_lines_keep_it(self):
        q = self.refined([SAMSUNG, ("The hinge is thinner.", "stock_video", "close-up of a phone hinge"),
                          ("The display is also brighter.", "stock_image", "bright phone display")])
        self.assertIn("Samsung Galaxy Z Fold 8", q[0])
        self.assertIn("Samsung Galaxy Z Fold 8 hinge", q[1])
        self.assertIn("Samsung Galaxy Z Fold 8 display", q[2])

    def test_pronoun_continuation(self):
        q = self.refined([SAMSUNG, ("It is also lighter than before.", "stock_video", "person holding smartphone")])
        self.assertIn("Samsung Galaxy Z Fold 8", q[1])

    def test_company_says_keeps_the_product(self):
        q = self.refined([SAMSUNG, ("Samsung says the new hinge is 3.8 mm.", "stock_video", "phone hinge macro")])
        self.assertIn("Samsung Galaxy Z Fold 8 hinge", q[1])
        self.assertNotIn("Samsung hinge", q[1])

    def test_subject_switch(self):
        q = self.refined([SAMSUNG, ("Apple's new foldable takes a different approach.", "stock_video", "folding smartphone"),
                          ("Its hinge is hidden.", "stock_video", "phone hinge close-up")])
        self.assertIn("Apple new foldable device", q[1])
        self.assertIn("Apple new foldable device hinge", q[2])
        self.assertNotIn("Samsung", q[2])

    def test_known_product_then_new_product(self):
        q = self.refined([SAMSUNG, ("The Pixel 11 Pro arrives in October.", "stock_video", "smartphone on a desk"),
                          ("Its camera is bigger.", "stock_video", "phone camera close-up")])
        self.assertIn("Pixel 11 Pro camera", q[2])
        self.assertNotIn("Samsung", q[2])

    def test_unrelated_line_does_not_inherit(self):
        q = self.refined([SAMSUNG, ("Meanwhile, the wider economy slowed down.", "stock_video", "busy stock exchange floor")])
        self.assertEqual(q[1], "busy stock exchange floor")

    def test_reporting_outlet_is_not_the_subject(self):
        q = self.refined([SAMSUNG, ("Bloomberg reports the hinge is cheaper to make.", "stock_video", "factory hinge close-up")])
        self.assertIn("Samsung Galaxy Z Fold 8 hinge", q[1])

    def test_unknown_product_is_not_invented(self):
        q = self.refined([("Samsung announced a new foldable device.", "stock_video", "modern smartphone technology"),
                          ("Meanwhile, the weather turned cold.", "stock_video", "snowy street")])
        self.assertIn("Samsung new foldable device", q[0])
        self.assertNotIn("Galaxy", q[0])

    def test_narration_is_never_changed(self):
        rows = [SAMSUNG, ("The hinge is thinner.", "stock_video", "close-up of a phone hinge")]
        p = plan(rows)
        refine_plan(p)
        self.assertEqual(" ".join(s.narration for s in p.scenes), " ".join(r[0] for r in rows))


class UiContinuity(unittest.TestCase):
    ROWS = [("Apple introduced a new camera control on the iPhone 17 Pro.", "stock_video", "smartphone camera"),
            ("Users can now swipe across it to zoom.", "stock_video", "person using smartphone"),
            ("And it works in third-party apps too.", "stock_video", "generic phone user")]

    def setUp(self):
        self.p = plan(self.ROWS)
        refine_plan(self.p)

    def test_continuation_keeps_the_ui_footage_family(self):
        for s in self.p.scenes[1:]:
            self.assertEqual(s.asset_type, "youtube_video", s.narration)
            self.assertIn("Apple iPhone 17 Pro camera", queries(s))

    def test_ui_continuation_never_falls_back_to_generic_stock_or_flow(self):
        for s in self.p.scenes[1:]:
            self.assertNotIn("stock_video", s.fallbacks)
            self.assertFalse(set(s.fallbacks) & {"flow_video", "video", "flow_image", "image"})
            self.assertNotIn("person using", queries(s))

    def test_back_to_hardware_ends_the_ui_family(self):
        p = plan(self.ROWS + [("The hinge is thinner.", "stock_video", "close-up of a phone hinge")])
        refine_plan(p)
        self.assertNotIn("feature", queries(p.scenes[-1]))
        self.assertIn("Apple iPhone 17 Pro hinge", queries(p.scenes[-1]))


class NormalCsv(unittest.TestCase):
    def test_refined_plan_writes_the_normal_csv(self):
        p = plan()
        refine_plan(p)
        out = Path(tempfile.mkdtemp()) / "plan.csv"
        p.write_csv(out)
        with out.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(list(rows[0]), ["scene_number", "script_segment", "asset_type", "prompt"])
        self.assertEqual([r["scene_number"] for r in rows], [str(i) for i in range(1, len(rows) + 1)])
        self.assertEqual(" ".join(r["script_segment"] for r in rows), " ".join(n for n, _, _ in ROWS))
        self.assertTrue(all(r["prompt"].strip() for r in rows))


class OffMeansUnchanged(unittest.TestCase):
    def test_sound_rules_only_touch_the_given_copy(self):
        from smart_editing import SmartEditingSettings

        base = SmartEditingSettings()
        mt = smart_editing_settings(base)
        self.assertEqual(base, SmartEditingSettings(), "the Normal settings object is untouched")
        self.assertEqual((mt.sound_effects_intensity, mt.visual_transitions_intensity, mt.scene_ambience), ("low", "low", False))

    def test_selector_defaults_off_and_is_per_project(self):
        from project_workspace import create_project

        ws = create_project("Tech", projects_root=Path(tempfile.mkdtemp()))
        self.assertEqual(ws.editing_system(), "")
        ws.set_editing_system("modern_tech")
        self.assertEqual(ws.editing_system(), "modern_tech")
        ws.set_editing_system("")
        self.assertEqual(ws.editing_system(), "")

    def test_app_calls_are_gated(self):
        src = Path(__file__).with_name("app.py").read_text(encoding="utf-8")
        self.assertIn("if modern_tech:\n                    # last, after allocation", src)
        self.assertIn("if self._modern_tech_on():\n            from modern_tech import smart_editing_settings", src)


if __name__ == "__main__":
    unittest.main()


FOLD7 = [  # the real-test story (Galaxy Z Fold 7), as the narration lines that broke
    ("Samsung's Galaxy Z Fold 7 is the thinnest foldable the company has ever made.", "stock_image", "Galaxy Z Fold 7 hands on thin profile"),
    ("Unfolded, it is only 4.2 millimetres thick, and it weighs 215 grams.", "stock_video", "phone side view thickness"),
    ("The hinge is thinner.", "stock_video", "Macro shot of the folded hinge with a clean graphic overlay"),
    ("It is 43 percent lighter than the hinge in the Fold 6.", "stock_image", "A dynamic 3D diagram rendering comparing the cross-sections of two hinges"),
    ("Samsung also made the ultra thin glass on the inner display 50 percent thicker than before.", "image", "layers of glass"),
    ("The main camera jumps to 200 megapixels, up from 50 on the Fold 6.", "stock_video", "camera module close up"),
    ("The battery stays at 4,400 mAh, and the inner display grows to 8 inches.", "stock_video", "phone battery"),
    ("On the software side, One UI 8 lets users run three apps side by side on the big screen.", "youtube_video", "Galaxy Z Fold 7 multitasking||Samsung One UI 8"),
    ("Users can drag content between them with a finger.", "stock_video", "person using smartphone"),
    ("The company says this also improves durability.", "stock_video", "phone drop test"),
    ("Imagine opening the phone every morning.", "stock_video", "person waking up"),
    ("Meanwhile, Samsung's revenue rose sharply last quarter across the industry.", "stock_video", "stock market chart"),
]


class StoryContextRealTest(unittest.TestCase):
    """The exact failures of the first real Modern Tech production (2026-10-08)."""

    def setUp(self):
        from modern_tech import build_story

        self.story = build_story([r[0] for r in FOLD7])
        self.p = plan(FOLD7)
        self.trace = [c for c in refine_plan(self.p) if c["kind"] == "context"]

    def first(self, words):
        return next(s for s in self.p.scenes if s.narration.startswith(words))

    def subject_of(self, words):
        sc = self.first(words)
        return next(t for t in self.trace if t["scene"] == sc.scene_id)["scene_subject"]

    def test_story_primary_and_comparison(self):
        self.assertEqual((self.story.primary_company, self.story.primary_product), ("Samsung", "Galaxy Z Fold 7"))
        self.assertEqual(self.story.comparison_entities, ["Fold 6"])
        self.assertEqual(self.story.ui_name, "One UI 8")

    def test_primary_subject_holds_across_the_story(self):
        for words in ("Unfolded", "The hinge", "It is 43", "Samsung also", "The main camera", "The battery", "On the software",
                      "Users can", "The company says"):
            self.assertEqual(self.subject_of(words), "Samsung Galaxy Z Fold 7", words)

    def test_component_lines_search_the_story_product(self):
        self.assertIn("Samsung Galaxy Z Fold 7 hinge", queries(self.first("The hinge")))
        self.assertIn("Samsung Galaxy Z Fold 7 camera", queries(self.first("The main camera")))
        self.assertIn("Samsung Galaxy Z Fold 7 durability", queries(self.first("The company says")))

    def test_comparison_never_hijacks(self):
        for s in self.p.scenes:
            q = queries(s)
            self.assertNotRegex(q, r"(^|\|\| )Fold 6", s.narration)
        sc = next(s for s in self.p.scenes if "Fold 6" in s.narration)
        t = next(t for t in self.trace if t["scene"] == sc.scene_id)
        self.assertEqual((sc.asset_type, t["scene_subject"]), ("stock_image", "Samsung Galaxy Z Fold 7"),
                         "a comparison line is a still of the story product")
        self.assertIn("Fold 6", t["comparison_entities"])

    def test_openers_are_not_companies(self):
        from modern_tech.editorial import names

        self.assertEqual(names("Unfolded, it is only 4.2 millimetres thick."), [])
        self.assertEqual(names("Imagine opening the phone every morning."), [])
        self.assertEqual(names("Users can drag content between them."), [])
        self.assertEqual(names("Meanwhile, the economy slowed."), [])
        self.assertEqual(names("Samsung says the hinge is new."), ["Samsung"])
        self.assertEqual(names("Apple announced a new phone."), ["Apple"])

    def test_units_and_product_names_are_protected(self):
        from modern_tech.editorial import _split_narration, names

        self.assertEqual(names("The battery stays at 4,400 mAh."), [])
        self.assertEqual(names("It has 24 GB of memory and a 120 Hz screen on 3 nm."), [])
        line = "The battery stays at 4,400 mAh and the Samsung Galaxy Z Fold 7 inner display grows to 8 inches today."
        for n in (2, 3, 4):
            pieces = _split_narration(line, n)
            self.assertEqual(" ".join(pieces), line)
            for a, b in zip(pieces, pieces[1:]):
                self.assertFalse(a.endswith("4,400") and b.startswith("mAh"))
                self.assertFalse(b.split()[0] in ("Galaxy", "Z", "Fold", "7") and a.split()[-1] in ("Samsung", "Galaxy", "Z", "Fold"), (a, b))
        self.assertIn("4,400 mAh", " ".join(s.narration for s in self.p.scenes), "narration never changes")

    def test_ui_lines_stay_product_specific(self):
        ui = self.first("Users can")
        self.assertEqual(ui.asset_type, "youtube_video")
        self.assertIn("Samsung Galaxy Z Fold 7 One UI 8 drag and drop", queries(ui))
        self.assertEqual(ui.fallbacks, ["stock_image"])
        self.assertIn("One UI 8 multitasking", queries(self.first("On the software")))

    def test_market_line_is_not_the_product(self):
        q = queries(self.first("Meanwhile"))
        self.assertNotIn("Fold 7", q)
        self.assertIn("Samsung", q)

    def test_unrelated_opener_line_inherits_only_through_reference(self):
        self.assertEqual(self.subject_of("Imagine"), "Samsung Galaxy Z Fold 7", "'the phone' refers back to the story")

    def test_no_cinematic_paragraph_reaches_a_search(self):
        for s in self.p.scenes:
            if s.asset_type not in ("image", "video"):
                for q in s.search_queries:
                    self.assertLessEqual(len(q.split()), 12, q)
                    self.assertNotRegex(q.lower(), r"cinematic|macro shot|dynamic 3d|rendering")

    def test_named_product_scenes_never_fall_back_to_generic_or_flow(self):
        for s in self.p.scenes:
            if "Fold 7" in queries(s) and s.asset_type not in ("image", "video"):
                self.assertNotIn("stock_video", s.fallbacks)
                self.assertFalse(set(s.fallbacks) & {"flow_video", "video", "flow_image", "image"})

    def test_cost_neutral(self):
        from modern_tech import flow_generations

        before = flow_generations(plan(FOLD7))
        after = flow_generations(self.p)
        self.assertLessEqual(after["video"], before["video"])
        self.assertLessEqual(after["video"] + after["image"], before["video"] + before["image"])


class OutletIsNotUi(unittest.TestCase):
    def test_android_authority_does_not_start_a_ui_run(self):
        from modern_tech import SceneContext, build_story, scene_context

        story = build_story([r[0] for r in FOLD7])
        line = "Android Authority reported that some demo units did not open fully flat."
        self.assertFalse(scene_context(story, SceneContext(), line, "NEWS").ui)
        self.assertFalse(scene_context(story, SceneContext(), "According to Android Police, the hinge is stiff.", "NEWS").ui)
        self.assertTrue(scene_context(story, SceneContext(), "Android 16 adds a new lock screen.", "NEWS").ui)


def route_one(line, asset_type="stock_video", prompt="phone on a desk", story_lines=()):
    """Refine a two-line plan (story line + the line under test, no split) and return the tested scene and its trace."""
    rows = [("Samsung's Galaxy Z Fold 7 is here.", "stock_image", "Galaxy Z Fold 7"), *story_lines, (line, asset_type, prompt)]
    p = plan(rows)
    trace = [c for c in refine_plan(p) if c["kind"] == "context"]
    sc = next(s for s in p.scenes if line.startswith(s.narration))
    return sc, next(t for t in trace if t["scene"] == sc.scene_id)


class MotionRouting(unittest.TestCase):
    """A named product is not a reason for YouTube: footage only where the line needs motion."""

    def test_static_lines_are_product_stills(self):
        for line in ("The Galaxy Z Fold 7 features a refined hinge design.", "The Fold 7 weighs 215 grams.",
                     "The battery capacity is 4,400 mAh.", "The Armor FlexHinge uses a redesigned structure."):
            sc, t = route_one(line)
            self.assertEqual(sc.asset_type, "stock_image", line)
            self.assertEqual(sc.fallbacks, [], "a still needs no fallback")
            self.assertTrue(sc.search_queries[0].startswith("Samsung Galaxy Z Fold 7"), sc.search_queries)
        self.assertIn("battery", route_one("The battery capacity is 4,400 mAh.")[0].search_queries[0])

    def test_motion_lines_are_footage(self):
        for line in ("One UI 8 lets users drag an app into split screen.", "The phone unfolds smoothly in the user's hand."):
            sc, _ = route_one(line)
            self.assertEqual(sc.asset_type, "youtube_video", line)
            self.assertEqual(sc.fallbacks, ["stock_image"])
            self.assertIn("Samsung Galaxy Z Fold 7", sc.search_queries[0])

    def test_states_are_not_motion(self):
        for line in ("Unfolded, it is only 4.2 millimetres thick.", "Samsung dropped support for the S Pen.",
                     "The folding screen lies flatter when the phone is open."):
            self.assertEqual(route_one(line)[0].asset_type, "stock_image", line)
        self.assertEqual(route_one("Some demo units did not open fully flat.")[0].asset_type, "youtube_video")

    def test_comparison_is_a_still_of_the_story_product(self):
        sc, t = route_one("The Fold 7 is thinner than the Fold 6.")
        self.assertEqual(sc.asset_type, "stock_image")
        self.assertEqual(t["scene_subject"], "Samsung Galaxy Z Fold 7")
        self.assertIn("Fold 6", t["comparison_entities"])
        self.assertFalse(sc.search_queries[0].startswith("Fold 6"))

    def test_split_pieces_take_their_own_topic(self):
        line = ("The display on the Fold 7 is brighter than ever before in a foldable. "
                "The battery remains at 4,400 mAh for the whole day of use.")
        p = plan([("Samsung's Galaxy Z Fold 7 is here.", "stock_image", "Galaxy Z Fold 7"), (line, "stock_video", "phone")])
        refine_plan(p)
        pieces = [s for s in p.scenes if s.narration in line]
        self.assertGreaterEqual(len(pieces), 2)
        self.assertIn("display", pieces[0].search_queries[0])
        bat = next(s for s in pieces if "battery" in s.narration)
        self.assertIn("battery", bat.search_queries[0])
        self.assertTrue(all(s.asset_type == "stock_image" for s in pieces), "static pieces stay stills")
        self.assertTrue(all(s.search_queries[0].startswith("Samsung Galaxy Z Fold 7") for s in pieces), "subject kept")

    def test_allocated_technical_flow_is_kept(self):
        sc, _ = route_one("The hinge spreads the pressure across the panel.", "video",
                          "cutaway of a precision steel hinge spreading pressure across a flexible panel")
        self.assertEqual(sc.asset_type, "video")
        self.assertIn("cutaway of a precision steel hinge", sc.visual_description)
        self.assertEqual(sc.search_queries, ["Samsung Galaxy Z Fold 7 hinge"], "only its fallback search changes")
        self.assertEqual(sc.fallbacks, ["stock_image"])

    def test_generic_flow_is_not_preserved(self):
        sc, _ = route_one("The hinge spreads the pressure across the panel.", "video", "A futuristic generic server room")
        self.assertNotIn(sc.asset_type, ("video", "image"))

    def test_routing_is_semantic_not_a_quota(self):
        src = Path(__file__).with_name("modern_tech").joinpath("editorial.py").read_text(encoding="utf-8")
        self.assertNotRegex(src, r"youtube_count|max_youtube|youtube_share")


class RelevanceCheck(unittest.TestCase):
    def setUp(self):
        from modern_tech import build_story, scene_context

        self.story = build_story([r[0] for r in FOLD7])
        self.ctx = scene_context(self.story, __import__("modern_tech").SceneContext(), "The hinge is thinner.", "CONTEXT")

    def check(self, text):
        from modern_tech import is_relevant

        return is_relevant(text, self.story, self.ctx)

    def test_unrelated_results_are_rejected(self):
        for bad in ("old wooden door hinge close-up", "person holding a smartphone", "starry night sky galaxy",
                    "elephant skin texture", "cute kitten", "vintage camera on a table", "white flowers and a pocket watch"):
            self.assertFalse(self.check(bad), bad)

    def test_product_results_pass(self):
        for good in ("Samsung Galaxy Z Fold 7 hands-on", "Galaxy Z Fold7 hinge teardown", "Fold 7 review", "samsung foldable phone"):
            self.assertTrue(self.check(good), good)

    def test_scenes_without_a_product_are_not_gated(self):
        from modern_tech import SceneContext, is_relevant

        self.assertTrue(is_relevant("busy stock exchange floor", self.story, SceneContext()))
