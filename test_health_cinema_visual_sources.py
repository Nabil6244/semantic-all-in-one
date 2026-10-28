"""Health Cinema visual-source fixes: the 3D models are found where they really live, a missing 3D model never becomes a card while footage can be had,
and a failed footage search is retried with other queries before any card is shown."""
from __future__ import annotations
import os, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace

from health_cinema import assets, direction, engine, planner


def _env(**kv):
    old = {k: os.environ.get(k) for k in kv}
    for k, v in kv.items(): (os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v))
    return lambda: [(os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)) for k, v in old.items()]


class TestAssetDiscovery(unittest.TestCase):
    def test_env_var_is_authoritative(self):
        with tempfile.TemporaryDirectory() as d:
            undo = _env(HEALTH_CINEMA_ASSET_DIR=d)
            try:
                self.assertEqual(assets.asset_dirs(), [Path(d)]); self.assertIsNone(assets.anatomy_assets("head")); self.assertFalse(assets.template_ready("brain_journey"))
                for f in assets.ASSET_FILES["head"]: (Path(d) / f).write_bytes(b"x")
                self.assertTrue(assets.template_ready("brain_journey")); self.assertTrue(assets.template_ready("eye_journey")); self.assertFalse(assets.template_ready("heart_journey"))
            finally: undo()

    def test_without_env_the_per_user_folder_then_the_local_library_are_searched(self):
        undo = _env(HEALTH_CINEMA_ASSET_DIR=None)
        try:
            ds = assets.asset_dirs(); self.assertEqual(len(ds), 2); self.assertEqual(ds[1], assets.LOCAL_LIBRARY)
            self.assertIn("anatomy_status", dir(assets)); st = assets.anatomy_status(); self.assertEqual(set(st["ready"]), set(assets.TEMPLATE_ASSET))
        finally: undo()


SENT = [{"text": t, "start": a, "end": b} for t, a, b in [("The brain needs a steady supply of blood.", 0, 6), ("When an artery to the brain is blocked, cells begin to die.", 6, 12)]]
def D(i, narr, at, q): return {"scene_id": str(i), "narration": narr, "asset_type": at, "queries": list(q), "description": "", "scene": None}


class TestNoCardWhenFootageIsPossible(unittest.TestCase):
    def plan(self, at, tpl=False, footage=True):
        ds = [D(1, SENT[0]["text"] + " " + SENT[1]["text"], at, ["brain blood flow animation"])]
        return planner.plan_directed(SENT, "mix", ds, lambda t: tpl, allow_footage=footage)["scenes"]

    def test_missing_3d_model_gives_footage_not_a_card(self):
        for at in ("stock_video", "flow_image", "image"):
            with self.subTest(at):
                sc = self.plan(at); self.assertEqual([s.kind for s in sc], ["footage"]); self.assertEqual(sc[0].visual.get("anatomy_wanted"), None if at == "stock_video" else "brain")
                self.assertIn(sc[0].visual["asset_type"], planner.FOOTAGE_TYPES)

    def test_image_type_scene_about_an_organ_is_searched_with_the_organ_named(self):
        self.assertIn("brain", self.plan("flow_image")[0].visual["query"].lower())
        self.assertEqual(self.plan("stock_video")[0].visual["query"], "brain blood flow animation")     # the director's own query is kept

    def test_3d_is_still_used_when_the_model_exists(self):
        self.assertEqual(self.plan("stock_video", tpl=True)[0].kind, "anatomy_3d")

    def test_card_only_when_no_footage_source_exists(self):
        self.assertEqual(self.plan("stock_video", footage=False)[0].kind, "text_card")


class TestFootageRetry(unittest.TestCase):
    def setUp(self):
        from visual_director.schema import VisualScene
        vs = VisualScene(scene_id=1, narration="A man reads in his chair.", visual_goal="g", visual_description="old man reading a book", asset_type="stock_video", provider_preference="stock",
                         search_queries=["senior man reading"], timestamp_needed=False, timestamp_hint="", duration=4.0, importance="medium", fallbacks=[], visual_treatment="", transition="")
        self.d = {"scene_id": "1", "narration": vs.narration, "asset_type": "stock_video", "queries": ["senior man reading"], "description": vs.visual_description, "goal": "g", "scene": vs}
        self.sc = planner.Scene(1, 0, 4, vs.narration, "footage", visual={"query": "senior man reading"}, dscene_ids=["1"])
        self._undo = _env(PEXELS_API_KEY=None)
        import visual_director.llm as vl; self._cfg = vl.gemini_configured; vl.gemini_configured = lambda st=None: False; self.addCleanup(lambda: setattr(vl, "gemini_configured", self._cfg))

    def tearDown(self): self._undo()

    def test_alternative_queries_never_repeat_a_tried_query_and_use_the_scene_wording(self):
        alts = direction.alternative_queries(self.d, ["senior man reading", "old man reading a book"], {"gemini_enabled": False})
        self.assertTrue(alts); self.assertNotIn("senior man reading", [a.lower() for a in alts]); self.assertNotIn("old man reading a book", [a.lower() for a in alts])

    def test_retry_finds_footage_with_another_query_before_any_card(self):
        calls = []
        def acquirer(rows):
            calls.append([r.stock for r in rows]); out = {}
            for r in rows: out[int(r.scene_number)] = {"ok": len(calls) == 2, "path": "/x/clip.mp4", "provider": "pexels"}
            return out
        acq = {"requested": 1, "ok": 0, "failed": 0, "sources": {}}
        self.assertTrue(engine._retry_footage(self.sc, self.d, acquirer, False, False, {"gemini_enabled": False}, lambda m: None, acq))
        self.assertEqual(len(calls), 2); self.assertEqual(self.sc.visual["path"], "/x/clip.mp4"); self.assertEqual(acq["ok"], 1); self.assertEqual(acq["retried_ok"], 1)
        self.assertNotEqual(calls[0], ["senior man reading"])

    def test_retry_gives_up_after_two_rounds(self):
        calls = []
        def acquirer(rows): calls.append(1); return {int(r.scene_number): {"ok": False} for r in rows}
        acq = {"requested": 1, "ok": 0, "failed": 0, "sources": {}}
        self.assertFalse(engine._retry_footage(self.sc, self.d, acquirer, False, False, {"gemini_enabled": False}, lambda m: None, acq)); self.assertEqual(len(calls), 2)

    def test_weak_match_is_retried_and_only_a_better_clip_replaces_it(self):
        from health_cinema import acquire
        weak = {"ok": True, "path": "/x/a.mp4", "qa": {"vision_used": True, "semantic_match": 0.1}}
        self.assertTrue(acquire.is_weak(weak)); self.assertFalse(acquire.is_weak(dict(weak, qa={"vision_used": False, "semantic_match": 0.1})))   # text-only QA is not trusted to reject
        self.assertFalse(acquire.is_weak({"ok": True, "qa": {"vision_used": True, "semantic_match": 0.6}}))
        acq = {"requested": 1, "ok": 0, "failed": 0, "sources": {}}
        better = lambda rows: {int(r.scene_number): {"ok": True, "path": "/x/b.mp4", "provider": "pexels", "qa": {"vision_used": True, "semantic_match": 0.7}} for r in rows}
        self.assertTrue(engine._retry_footage(self.sc, self.d, better, False, False, {"gemini_enabled": False}, lambda m: None, acq, better_than=weak)); self.assertEqual(self.sc.visual["path"], "/x/b.mp4")
        same = lambda rows: {int(r.scene_number): {"ok": True, "path": "/x/c.mp4", "qa": {"vision_used": True, "semantic_match": 0.05}} for r in rows}
        sc2 = planner.Scene(2, 0, 4, "t", "footage", visual={"query": "q"}, dscene_ids=["1"])
        self.assertFalse(engine._retry_footage(sc2, self.d, same, False, False, {"gemini_enabled": False}, lambda m: None, dict(acq), better_than=weak)); self.assertNotIn("path", sc2.visual)


class TestRelevance(unittest.TestCase):
    from health_cinema import relevance as RL
    def rec(self, slug): return {"ok": True, "path": "/x.mp4", "source_url": f"https://www.pexels.com/video/{slug}-123456/", "qa": {"vision_used": False, "semantic_match": 0.85}}

    def test_title_naming_something_else_is_rejected_for_an_anatomy_scene(self):
        from health_cinema import relevance as RL, acquire
        r = RL.check(self.rec("a-close-up-of-a-person-walking-on-a-snowy-mountain"), "cartilage covers the ends", "knee anatomy", "joints", None)
        self.assertTrue(acquire.is_weak(r)); self.assertEqual(r["qa"]["status"], "TITLE_MISMATCH")

    def test_title_naming_the_body_part_passes_without_any_model(self):
        from health_cinema import relevance as RL, acquire
        self.assertFalse(acquire.is_weak(RL.check(self.rec("3d-animation-of-a-human-knee-joint"), "t", "q", "knee", None)))

    def test_ordinary_scenes_are_rejected_only_when_the_title_shares_nothing_with_the_search(self):
        from health_cinema import relevance as RL, acquire
        ok = RL.check(self.rec("elderly-couple-climbing-a-staircase"), "t", "woman climbing stairs slowly", None, None); self.assertFalse(acquire.is_weak(ok))      # climbing + stairs/staircase
        bad = RL.check(self.rec("silhouette-of-a-man-with-a-cello-at-sunset"), "t", "woman climbing stairs slowly", None, None); self.assertTrue(acquire.is_weak(bad))
        self.assertFalse(acquire.is_weak(RL.check(self.rec("seniors-in-a-garden"), "t", "elderly man park", None, None)))      # senior/elderly and garden/park are the same words
        self.assertFalse(acquire.is_weak(RL.check({"ok": True, "source_url": "", "qa": {"vision_used": False}}, "t", "anything", None, None)))     # no title: unknown, never guessed

    def test_pixabay_tags_judge_clips_that_have_no_readable_title(self):
        from health_cinema import relevance as RL, acquire
        rec = lambda: {"ok": True, "path": "/x.mp4", "source_url": "https://pixabay.com/videos/id-6840/", "qa": {"vision_used": False, "semantic_match": 0.85}}
        old = RL.pixabay_tags
        try:
            RL.pixabay_tags = lambda r, st: {"plasma", "abstract", "colorful"}; self.assertTrue(acquire.is_weak(RL.check(rec(), "t", "q", "knee", {})))
            RL.pixabay_tags = lambda r, st: {"knee", "joint", "x-ray"}; self.assertFalse(acquire.is_weak(RL.check(rec(), "t", "q", "knee", {})))
        finally: RL.pixabay_tags = old

    def test_no_title_and_no_key_is_not_guessed(self):
        from health_cinema import relevance as RL, acquire
        import visual_qa.semantic as vs
        old = vs.vision_semantic_score; vs.vision_semantic_score = lambda *a, **k: (None, [])
        try:
            rec = {"ok": True, "path": "/nonexistent.mp4", "source_url": "https://pixabay.com/videos/id-1/", "qa": {"vision_used": False, "semantic_match": 0.85}}
            self.assertFalse(acquire.is_weak(RL.check(rec, "t", "q", "liver", {})))
        finally: vs.vision_semantic_score = old


if __name__ == "__main__": unittest.main()
