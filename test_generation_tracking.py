"""Supabase video_generation_events tracking (licensing/generation_tracking.py).

The fake backend below enforces the migration's contract
(supabase/migrations/20260927000001_video_generation_events.sql):
  * RLS: a row's user_id must equal the caller's auth.uid() (from the JWT),
  * upsert on generation_id (Prefer: resolution=merge-duplicates),
  * the lifecycle trigger: a row that is no longer 'running' is final.
Aggregation runs the same SQL shape the analytics use, in SQLite.
"""

from __future__ import annotations

import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import requests

from licensing import generation_tracking as gt
from licensing.auth_client import AuthSession

ROOT = Path(__file__).resolve().parent
MIGRATION = ROOT / "supabase" / "migrations" / "20260927000001_video_generation_events.sql"

USER_A = "aaaaaaaa-0000-0000-0000-00000000000a"
USER_B = "bbbbbbbb-0000-0000-0000-00000000000b"


class FakeSupabase:
    def __init__(self):
        self.tokens = {"token-a": USER_A, "token-b": USER_B}
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.execute(
            "create table video_generation_events (generation_id text primary key, user_id text not null,"
            " project_id text, status text not null, started_at text, completed_at text,"
            " video_duration_seconds real, render_time_seconds real, render_engine text,"
            " app_version text, platform text, error_category text, error_message text)"
        )
        self.lock = threading.Lock()
        self.down = False
        self.calls = 0

    def post(self, url, *, headers, params, json, timeout):
        self.calls += 1
        if self.down:
            raise requests.ConnectionError("offline")
        assert url.endswith("/rest/v1/video_generation_events")
        assert params == {"on_conflict": "generation_id"}
        assert "merge-duplicates" in headers["Prefer"]
        uid = self.tokens.get(headers["Authorization"].removeprefix("Bearer "))
        if uid is None:
            return SimpleNamespace(status_code=401)
        if json.get("user_id") != uid:  # RLS with check (user_id = auth.uid())
            return SimpleNamespace(status_code=403)
        with self.lock:
            row = self.db.execute("select status from video_generation_events where generation_id=?",
                                  (json["generation_id"],)).fetchone()
            if row is not None and row[0] != "running":
                return SimpleNamespace(status_code=201)  # trigger returns NULL: update skipped
            cols = list(json)
            if row is None:
                self.db.execute(f"insert into video_generation_events ({','.join(cols)}) values "
                                f"({','.join('?' * len(cols))})", [json[c] for c in cols])
            else:
                self.db.execute(f"update video_generation_events set {','.join(c + '=?' for c in cols)} "
                                "where generation_id=?", [json[c] for c in cols] + [json["generation_id"]])
        return SimpleNamespace(status_code=201)

    def rows(self, status=None):
        q = "select * from video_generation_events" + (" where status=?" if status else "")
        cur = self.db.execute(q, (status,) if status else ())
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]

    def completed_count(self, user=None):
        return len([r for r in self.rows("completed") if user is None or r["user_id"] == user])


def _session(token="token-a", user=USER_A):
    return AuthSession(access_token=token, refresh_token="r", user_id=user, email="a@x")


class _Base(unittest.TestCase):
    def setUp(self):
        self.server = FakeSupabase()
        self.addCleanup(self.server.db.close)
        self.tmp = Path(tempfile.mkdtemp())
        self.session = _session()
        self.creds = mock.patch.object(gt, "supabase_credentials", return_value=("https://x.supabase.co", "anon"))
        self.creds.start()
        self.addCleanup(self.creds.stop)
        self.video = self.tmp / "final.mp4"
        self.video.write_bytes(b"\x00" * 64)

    def tracker(self, **kw):
        return gt.GenerationTracker(lambda: self.session, pending_dir=lambda: self.tmp,
                                    http_post=self.server.post, background=False, **kw)


class TestLifecycle(_Base):
    def test_valid_final_video_gives_exactly_one_completed_event(self):
        t = self.tracker()
        run = t.start(render_engine="exp_solar", project_id="project_1")
        self.assertEqual(self.server.rows()[0]["status"], "running")
        self.assertEqual(self.server.completed_count(), 0)  # start never counts
        with mock.patch("media_duration.probe_media_duration", return_value=612.4):
            t.complete(run, self.video, validated=True)
        rows = self.server.rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["status"], row["project_id"], row["render_engine"]),
                         ("completed", "project_1", "exp_solar"))
        self.assertEqual(row["video_duration_seconds"], 612.4)  # probed, not planned
        self.assertIsNotNone(row["completed_at"])
        self.assertGreaterEqual(row["render_time_seconds"], 0)

    def test_render_failure_is_failed_and_not_counted(self):
        t = self.tracker()
        run = t.start(render_engine="overscaled", project_id="p")
        t.fail(run, "Render failed: ffmpeg exited 1\n" + "x" * 5000)
        row = self.server.rows()[0]
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["error_category"], "ffmpeg")
        self.assertTrue(row["error_message"].startswith("Render failed: ffmpeg exited 1"))
        self.assertEqual(self.server.completed_count(), 0)

    def test_stop_pressed_is_cancelled_and_not_counted(self):
        t = self.tracker()
        run = t.start(render_engine="normal", project_id="p")
        t.cancel(run)
        self.assertEqual(self.server.rows()[0]["status"], "cancelled")
        self.assertEqual(self.server.completed_count(), 0)

    def test_output_exists_but_final_validation_fails_is_not_completed(self):
        t = self.tracker()
        run = t.start(render_engine="normal", project_id="p")
        with mock.patch("scene_graph.app_integration.validate_rendered_output",
                        return_value="no audio stream (narration missing)"):
            t.complete(run, self.video, validated=False)
        row = self.server.rows()[0]
        self.assertEqual((row["status"], row["error_category"]), ("failed", "validation"))
        self.assertEqual(self.server.completed_count(), 0)

    def test_missing_output_file_is_never_completed_even_when_marked_validated(self):
        t = self.tracker()
        run = t.start(render_engine="overscaled", project_id="p")
        t.complete(run, self.tmp / "nope.mp4", validated=True)
        self.assertEqual(self.server.completed_count(), 0)

    def test_completion_handler_called_twice_counts_once(self):
        t = self.tracker()
        run = t.start(render_engine="overscaled", project_id="p")
        with mock.patch("media_duration.probe_media_duration", return_value=10.0):
            t.complete(run, self.video, validated=True)
            t.complete(run, self.video, validated=True)
            t.fail(run, "late error")  # a later failure cannot un-complete it
        self.assertEqual(len(self.server.rows()), 1)
        self.assertEqual(self.server.completed_count(), 1)

    def test_server_ignores_a_duplicate_upload_of_the_same_generation(self):
        t = self.tracker()
        run = t.start(render_engine="overscaled", project_id="p")
        with mock.patch("media_duration.probe_media_duration", return_value=10.0):
            t.complete(run, self.video, validated=True)
        # e.g. a second process / network retry re-sends the same generation_id
        payload = t._payload(run, "completed")
        self.assertTrue(t._upsert(payload))
        self.assertTrue(t._upsert(t._payload(run, "failed")))
        self.assertEqual(len(self.server.rows()), 1)
        self.assertEqual(self.server.rows()[0]["status"], "completed")

    def test_failed_then_retry_success_counts_once(self):
        t = self.tracker()
        first = t.start(render_engine="exp_solar", project_id="p")
        t.fail(first, "Media resolution failed for 3 scenes")
        second = t.start(render_engine="exp_solar", project_id="p")
        with mock.patch("media_duration.probe_media_duration", return_value=10.0):
            t.complete(second, self.video, validated=True)
        self.assertNotEqual(first.generation_id, second.generation_id)
        self.assertEqual(self.server.completed_count(), 1)
        self.assertEqual(len(self.server.rows("failed")), 1)


class TestAttribution(_Base):
    def test_event_belongs_to_the_signed_in_user(self):
        t = self.tracker()
        run = t.start(render_engine="normal", project_id="p")
        t.cancel(run)
        self.assertEqual(self.server.rows()[0]["user_id"], USER_A)

    def test_rls_rejects_another_users_id(self):
        t = self.tracker()
        run = t.start(render_engine="normal", project_id="p")
        run.user_id = USER_B  # even a tampered run cannot write as B with A's token
        payload = t._payload(run, "completed")
        self.assertFalse(t._upsert(payload))
        self.assertEqual(self.server.completed_count(USER_B), 0)

    def test_signed_out_generation_is_not_tracked_and_does_not_raise(self):
        self.session = None
        t = self.tracker()
        self.assertIsNone(t.start(render_engine="normal", project_id="p"))
        t.complete(None, self.video, validated=True)
        self.assertEqual(self.server.rows(), [])

    def test_queued_event_is_only_sent_for_its_own_user(self):
        t = self.tracker()
        self.server.down = True
        run = t.start(render_engine="normal", project_id="p")
        t.cancel(run)
        self.server.down = False
        self.session = _session("token-b", USER_B)  # B signs in on this machine
        t.flush_pending()
        self.assertEqual(self.server.rows(), [])
        self.session = _session()
        t.flush_pending()
        self.assertEqual(self.server.rows()[0]["user_id"], USER_A)


class TestSupabaseUnavailable(_Base):
    def test_offline_never_raises_and_the_event_is_delivered_later_once(self):
        t = self.tracker()
        self.server.down = True
        run = t.start(render_engine="exp_solar", project_id="p")
        with mock.patch("media_duration.probe_media_duration", return_value=10.0):
            t.complete(run, self.video, validated=True)  # must not raise
        self.assertTrue((self.tmp / gt._PENDING_FILE).exists())
        self.server.down = False
        t.flush_pending()
        t.flush_pending()
        self.assertEqual(self.server.completed_count(), 1)
        self.assertFalse((self.tmp / gt._PENDING_FILE).exists())

    def test_api_error_is_non_fatal(self):
        def broken(*a, **k):
            return SimpleNamespace(status_code=500)

        t = gt.GenerationTracker(lambda: self.session, pending_dir=lambda: self.tmp,
                                 http_post=broken, background=False)
        run = t.start(render_engine="normal", project_id="p")
        t.complete(run, self.video, validated=True)
        self.assertTrue((self.tmp / gt._PENDING_FILE).exists())

    def test_expired_token_is_refreshed_once_and_the_event_lands(self):
        self.session = _session("expired", USER_A)
        fresh = _session()

        def refresh():
            self.session = fresh
            return fresh

        t = self.tracker(refresh_session=refresh)
        run = t.start(render_engine="normal", project_id="p")
        t.cancel(run)
        self.assertEqual(self.server.rows()[0]["status"], "cancelled")

    def test_background_mode_returns_immediately(self):
        release = threading.Event()

        def slow(*a, **k):
            release.wait(5)
            return SimpleNamespace(status_code=201)

        t = gt.GenerationTracker(lambda: self.session, pending_dir=lambda: self.tmp, http_post=slow)
        run = t.start(render_engine="normal", project_id="p")  # would block 5s if synchronous
        t.cancel(run)
        release.set()


class TestAppNeverReportsATrackingFailure(unittest.TestCase):
    def setUp(self):
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(str(exc))
        self.app = _app

    def _fake_app(self, tracker):
        fake = mock.MagicMock()
        fake._normal_tracking = object()
        fake._get_generation_tracker.return_value = tracker
        fake._track_generation_end = (
            lambda *a, **k: self.app.VideoGeneratorApp._track_generation_end(fake, *a, **k))
        return fake

    def test_successful_render_stays_successful_when_supabase_breaks(self):
        tracker = mock.Mock()
        tracker.complete.side_effect = RuntimeError("supabase exploded")
        fake = self._fake_app(tracker)
        with mock.patch.object(self.app.messagebox, "showinfo") as info:
            self.app.VideoGeneratorApp._on_finished(fake, True, "/out/final.mp4")
        tracker.complete.assert_called_once()
        info.assert_called_once_with("Done", "Video saved to:\n/out/final.mp4")
        fake.status_var.set.assert_any_call("Done — /out/final.mp4")
        fake._show_error_dialog.assert_not_called()
        self.assertIsNone(fake._normal_tracking)

    def test_failure_and_cancel_route_to_the_tracker(self):
        for kwargs, method in (({"success": False, "message": "boom"}, "fail"),
                               ({"success": False, "message": "stop", "cancelled": True}, "cancel")):
            tracker = mock.Mock()
            fake = self._fake_app(tracker)
            with mock.patch.object(self.app.messagebox, "showinfo"):
                self.app.VideoGeneratorApp._on_finished(fake, **kwargs)
            getattr(tracker, method).assert_called_once()
            tracker.complete.assert_not_called()

    def test_normal_completion_is_validated_before_counting(self):
        tracker = mock.Mock()
        fake = self._fake_app(tracker)
        with mock.patch.object(self.app.messagebox, "showinfo"):
            self.app.VideoGeneratorApp._on_finished(fake, True, "/out/final.mp4")
        self.assertIs(tracker.complete.call_args.kwargs["validated"], False)

    def test_overscaled_finish_uses_the_validated_result(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        block = src[src.index("        def finish(result) -> None:"):src.index("threading.Thread(target=worker")]
        self.assertIn("self._track_generation_end(", block)
        self.assertIn('"completed" if result.ok', block)
        self.assertIn("validated=True", block)


class TestDailyAggregation(unittest.TestCase):
    def test_daily_counts_exclude_running_failed_and_cancelled(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.execute("create table video_generation_events (user_id text, status text, completed_at text)")
        rows = ([(USER_A, "completed", "2026-09-27T10:00:00+00:00")] * 3
                + [(USER_A, "completed", "2026-09-28T09:00:00+00:00")] * 5
                + [(USER_A, "failed", "2026-09-27T11:00:00+00:00"),
                   (USER_A, "cancelled", "2026-09-28T11:00:00+00:00"),
                   (USER_A, "running", None),
                   (USER_B, "completed", "2026-09-28T12:00:00+00:00")])
        db.executemany("insert into video_generation_events values (?,?,?)", rows)
        per_user = db.execute(
            "SELECT DATE(completed_at) AS day, COUNT(*) FROM video_generation_events "
            "WHERE user_id = ? AND status = 'completed' GROUP BY DATE(completed_at) ORDER BY day DESC",
            (USER_A,)).fetchall()
        self.assertEqual(per_user, [("2026-09-28", 5), ("2026-09-27", 3)])
        everyone = db.execute(
            "SELECT user_id, DATE(completed_at) AS day, COUNT(*) FROM video_generation_events "
            "WHERE status = 'completed' GROUP BY user_id, DATE(completed_at) ORDER BY day DESC, user_id"
        ).fetchall()
        self.assertEqual(everyone, [(USER_A, "2026-09-28", 5), (USER_B, "2026-09-28", 1),
                                    (USER_A, "2026-09-27", 3)])


class TestMigrationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8").lower()

    def test_generation_id_is_unique_and_statuses_are_constrained(self):
        self.assertIn("unique (generation_id)", self.sql)
        self.assertIn("check (status in ('running', 'completed', 'failed', 'cancelled'))", self.sql)

    def test_rls_is_own_rows_only_and_there_is_no_delete(self):
        self.assertIn("alter table public.video_generation_events enable row level security", self.sql)
        self.assertEqual(self.sql.count("user_id = auth.uid()"), 4)  # select, insert, update using+check
        self.assertNotIn("for delete", self.sql)
        self.assertNotIn("to anon", self.sql)
        self.assertNotIn("grant delete", self.sql)

    def test_finished_rows_are_final_server_side(self):
        self.assertIn("if old.status <> 'running' then\n            return null;", self.sql)

    def test_views_respect_the_callers_rls(self):
        self.assertEqual(self.sql.count("with (security_invoker = true)"), 2)

    def test_no_service_role_key_in_the_desktop_app(self):
        for path in (ROOT / "licensing").glob("*.py"):
            self.assertNotIn("service_role", path.read_text(encoding="utf-8").lower(), path.name)


class TestErrorCategories(unittest.TestCase):
    def test_existing_failure_texts_map_to_categories(self):
        cases = {
            "The voiceover doesn't match this plan": "audio",
            "Flow engine did not respond": "flow",
            "[Errno 35] Resource temporarily unavailable": "resource",
            "Final video failed validation: no decodable video stream": "validation",
            "Media resolution failed for 2 scenes": "asset",
            "Segment join failed: ffmpeg exited 1": "ffmpeg",
            "Render failed (segment 3)": "render",
            "something odd": "unknown",
        }
        for text, expected in cases.items():
            self.assertEqual(gt.categorize_error(text), expected, text)

    def test_traceback_keeps_its_real_last_line(self):
        tb = "Traceback (most recent call last):\n  File x\nValueError: bad frame size"
        self.assertEqual(gt._short_error(tb), "ValueError: bad frame size")


if __name__ == "__main__":
    unittest.main()
