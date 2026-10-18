"""Learning phase 3 + 5 logic: exact CSV/render linkage, signed-out runs, validation, scene failures, pre-render events, ratings flow."""
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from learning import events as ev
from learning import ledger as lg
from learning import rating_flow as rf
from learning.scope import resolve_scope
from licensing.generation_tracking import GenerationTracker
from production import events as pe


class Ws:
    project_id = "proj-1"

    def __init__(self, state_dir, meta=None):
        self.state_dir, self.meta = state_dir, meta or {}

    def read_meta(self):
        return self.meta

    def starmap_settings(self):
        return self.meta.get("starmap_settings", {})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.led = lg.Ledger(self.dir / "l.sqlite")
        self.app = SimpleNamespace(generation_mode="normal", _workspace=Ws(self.dir), _settings={})

    def csv(self, name, text):
        p = self.dir / name
        p.write_text(text, encoding="utf-8")
        return p

    def run_(self, gid="g1", engine="normal"):
        return SimpleNamespace(generation_id=gid, project_id="proj-1", render_engine=engine)


class ScopeTests(Base):
    def test_real_substyle_identifiers(self):
        self.assertEqual(resolve_scope(SimpleNamespace(generation_mode="pakmap", _workspace=None, _settings={"doc_style": True})), "pakmap/doc")
        self.assertEqual(resolve_scope(SimpleNamespace(generation_mode="hybrid", _workspace=None, _settings={})), "hybrid/default")
        a = SimpleNamespace(generation_mode="starmap", _workspace=Ws(self.dir, {"starmap_settings": {"cinema": {"enabled": True}}}))
        self.assertEqual(resolve_scope(a), "starmap/cinema")
        self.assertEqual(resolve_scope(SimpleNamespace(generation_mode="whatif", _workspace=None)), "whatif/default")

    def test_scope_frozen_at_render_start(self):
        self.app._workspace.meta = {"video_style": {"style_id": "history"}}
        ev.begin_render_op(self.app, "normal", self.run_(), ledger=self.led)
        self.app._workspace.meta = {"video_style": {"style_id": "news"}}      # user switches style mid-render
        ev.note_render_outcome(self.app, self.run_(), "completed", ledger=self.led)
        self.assertEqual(self.led.events(event_type="render_outcome")[0]["style_scope"], "normal/history")


class LinkageTests(Base):
    def test_render_links_to_csv_in_force_at_start_not_latest(self):
        ev.note_import(self.app, "normal", path=self.csv("a.csv", "scene_number\n1\n"), ledger=self.led)
        first = self.led.events(event_type="csv_import")[0]
        ev.begin_render_op(self.app, "normal", self.run_(), ledger=self.led)
        ev.note_import(self.app, "normal", path=self.csv("b.csv", "scene_number\n1\n2\n"), ledger=self.led)   # later import
        ev.note_render_outcome(self.app, self.run_(), "completed", ledger=self.led)
        r = self.led.events(event_type="render_outcome")[0]
        self.assertEqual(r["payload"]["import_event_id"], first["event_id"])
        self.assertEqual(r["csv_sha256"], first["csv_sha256"])
        self.assertEqual(r["payload"]["association_point"], "render_start")

    def test_unknown_association_is_explicit(self):
        ev.begin_render_op(self.app, "normal", self.run_(), ledger=self.led)
        ev.note_render_outcome(self.app, self.run_(), "completed", ledger=self.led)
        r = self.led.events(event_type="render_outcome")[0]
        self.assertEqual(r["payload"]["association"], "unknown")
        self.assertIsNone(r["csv_sha256"])

    def test_signed_out_run_gets_local_operation_id(self):
        ev.begin_render_op(self.app, "normal", None, ledger=self.led)
        self.assertTrue(ev.note_render_outcome(self.app, None, "failed", "ffmpeg", ledger=self.led))
        r = self.led.events(event_type="render_outcome")[0]
        self.assertTrue(r["event_id"].startswith("render:"))
        self.assertIsNone(r["generation_id"])
        self.assertFalse(r["payload"]["generation_tracked"])
        self.assertEqual(r["payload"]["failure_category"], "ffmpeg")

    def test_nothing_without_run_or_operation(self):
        self.assertFalse(ev.note_render_outcome(self.app, None, "completed", ledger=self.led))

    def test_duplicate_callbacks_and_distinct_renders(self):
        ev.begin_render_op(self.app, "normal", self.run_("g1"), ledger=self.led)
        self.assertTrue(ev.note_render_outcome(self.app, self.run_("g1"), "failed", ledger=self.led))
        self.assertFalse(ev.note_render_outcome(self.app, self.run_("g1"), "completed", ledger=self.led))
        ev.begin_render_op(self.app, "normal", self.run_("g2"), ledger=self.led)
        self.assertTrue(ev.note_render_outcome(self.app, self.run_("g2"), "completed", ledger=self.led))
        self.assertEqual(len(self.led.events(event_type="render_outcome")), 2)

    def test_validation_is_a_separate_later_event(self):
        ev.begin_render_op(self.app, "normal", self.run_(), ledger=self.led)
        ev.note_render_outcome(self.app, self.run_(), "completed", ledger=self.led)
        self.assertTrue(ev.note_validation({"generation_id": "g1", "status": "failed", "error_category": "validation"}, ledger=self.led))
        self.assertFalse(ev.note_validation({"generation_id": "g1", "status": "failed"}, ledger=self.led))     # replay
        self.assertEqual(self.led.events(event_type="render_outcome")[0]["payload"]["outcome"], "success")      # history untouched
        v = self.led.events(event_type="render_validation")[0]
        self.assertFalse(v["payload"]["validated"])
        self.assertFalse(ev.note_validation({"generation_id": "nope", "status": "completed"}, ledger=self.led))

    def test_tracker_observer_sees_terminal_payload_and_delivery_is_unchanged(self):
        seen, posted = [], []

        class Resp:
            status_code = 200

        tr = GenerationTracker(lambda: SimpleNamespace(user_id="u1", access_token="t"), pending_dir=lambda: self.dir,
                               http_post=lambda *a, **k: posted.append(k["json"]) or Resp(), background=False, on_terminal=seen.append)
        import licensing.generation_tracking as gt
        orig = gt.supabase_credentials
        gt.supabase_credentials = lambda: ("http://x", "k")
        try:
            run = tr.start(render_engine="normal", project_id="p")
            tr.fail(run, "boom")
        finally:
            gt.supabase_credentials = orig
        self.assertEqual([p["status"] for p in posted], ["running", "failed"])
        self.assertEqual([p["status"] for p in seen], ["failed"])

    def test_failing_observer_cannot_break_tracker(self):
        def boom(_):
            raise RuntimeError("x")
        tr = GenerationTracker(lambda: None, pending_dir=lambda: self.dir, background=False, on_terminal=boom)
        tr._send({"status": "failed", "user_id": "u"})   # no raise


class SceneFailureTests(Base):
    def test_sanitized_idempotent_and_windowed(self):
        t0 = time.time()
        pe._append(self.dir, {"t": t0 - 500, "kind": "asset", "scene": "001", "source": "flow_image", "outcome": "failed", "error_class": "old"})
        pe._append(self.dir, {"t": t0 + 1, "kind": "asset", "scene": "002", "source": "Flow_Video", "outcome": "failed",
                              "error_class": "quota", "error": "SECRET prompt text /Users/me"})
        pe._append(self.dir, {"t": t0 + 2, "kind": "asset", "scene": "003", "source": "pexels", "outcome": "generated"})
        pe._append(self.dir, {"t": t0 + 3, "kind": "job", "scene": "004", "type": "asset", "state": "failed", "attempt": 2, "error_class": "net"})
        n = ev._record_scene_failures(self.app, self.led, "g1", "g1", "normal/default", "proj-1", "abc", t0)
        self.assertEqual(n, 2)
        self.assertEqual(ev._record_scene_failures(self.app, self.led, "g1", "g1", "normal/default", "proj-1", "abc", t0), 0)
        rows = self.led.events(event_type="scene_failure")
        self.assertNotIn("SECRET", str(rows))
        self.assertEqual({r["payload"]["scene"] for r in rows}, {"002", "004"})
        self.assertEqual(rows[0]["generation_id"], "g1")
        self.assertEqual(rows[0]["csv_sha256"], "abc")

    def test_end_to_end_via_render_outcome(self):
        ev.begin_render_op(self.app, "normal", self.run_(), ledger=self.led)
        pe._append(self.dir, {"t": time.time() + 1, "kind": "asset", "scene": "007", "source": "pexels", "outcome": "failed", "error_class": "none_found"})
        ev.note_render_outcome(self.app, self.run_(), "failed", "asset", ledger=self.led)
        self.assertEqual(len(self.led.events(event_type="scene_failure")), 1)


class PreRenderTests(Base):
    def test_prerender_and_assets_events_are_not_renders(self):
        self.assertTrue(ev.note_prerender_failure(self.app, "normal", "csv_import", error=ValueError("secret text"), text="a,b\n1,2\n", ledger=self.led))
        self.assertTrue(ev.note_assets_outcome(self.app, True, 5, 5, ledger=self.led))
        self.assertEqual(self.led.events(event_type="render_outcome"), [])
        f = self.led.events(event_type="pre_render_failure")[0]
        self.assertEqual(f["payload"]["error_type"], "ValueError")
        self.assertNotIn("secret", str(f))
        self.assertEqual(self.led.events(event_type="assets_outcome")[0]["payload"], {"ok": True, "ready": 5, "total": 5})


class RatingFlowTests(Base):
    def finished(self, gid="g1", engine="normal"):
        ev.begin_render_op(self.app, engine, self.run_(gid, engine), ledger=self.led)
        ev.note_render_outcome(self.app, self.run_(gid, engine), "completed", ledger=self.led)

    def test_prompt_target_rules(self):
        self.assertIsNone(rf.pending_prompt_target("proj-1", self.led))
        self.finished()
        h = rf.pending_prompt_target("proj-1", self.led)
        self.assertEqual(h["render_key"], "g1")
        self.assertIsNone(rf.pending_prompt_target("proj-1", self.led, now=time.time() + 5000))            # stale
        rf.skip("g1", self.led)
        self.assertIsNone(rf.pending_prompt_target("proj-1", self.led))                                    # skipped: no re-prompt
        self.assertEqual(self.led.events(event_type="video_rating"), [])                                   # and no negative rating

    def test_failed_render_or_failed_validation_not_offered(self):
        ev.begin_render_op(self.app, "normal", self.run_("gf"), ledger=self.led)
        ev.note_render_outcome(self.app, self.run_("gf"), "failed", "render", ledger=self.led)
        self.assertIsNone(rf.pending_prompt_target("proj-1", self.led))
        self.finished("g2")
        ev.note_validation({"generation_id": "g2", "status": "failed"}, ledger=self.led)
        self.assertIsNone(rf.pending_prompt_target("proj-1", self.led))

    def test_exact_render_association_revision_and_history(self):
        self.finished("g1")
        self.finished("g2")
        h = {x["render_key"]: x for x in rf.render_history("proj-1", self.led)}
        self.assertTrue(rf.submit(h["g1"], 5, ledger=self.led).ok)
        r2 = rf.submit(rf.render_history("proj-1", self.led)[1], 2, tags=["poor_pacing"], ledger=self.led)   # g1 again (older)
        self.assertEqual((r2.status, r2.revision), ("revised", 2))
        hist = {x["render_key"]: x for x in rf.render_history("proj-1", self.led)}
        self.assertEqual(hist["g1"]["rating"]["payload"]["rating"], 2)
        self.assertIsNone(hist["g2"]["rating"])
        self.assertEqual(len(self.led.events(event_type="video_rating")), 2)                                # nothing overwritten

    def test_signed_out_render_can_be_rated_by_operation_key(self):
        ev.begin_render_op(self.app, "normal", None, ledger=self.led)
        ev.note_render_outcome(self.app, None, "completed", ledger=self.led)
        h = rf.render_history("proj-1", self.led)[0]
        self.assertTrue(h["render_key"].startswith("op-"))
        self.assertTrue(rf.submit(h, 4, ledger=self.led).ok)
        self.assertEqual(rf.render_history("proj-1", self.led)[0]["rating"]["payload"]["rating"], 4)

    def test_db_error_returns_failure_not_exception(self):
        bad = lg.Ledger(self.dir)
        self.assertEqual(rf.submit({"rendered": {"project_id": "p"}, "style_scope": "a/b", "render_key": "k"}, 3, ledger=bad).status, "error")

    def test_ui_modules_import_and_dialog_class_exists(self):
        import learning.rating_ui as ui
        self.assertTrue(callable(ui.RatingDialog) and callable(ui.open_history) and callable(ui.schedule_prompt))


if __name__ == "__main__":
    unittest.main()
