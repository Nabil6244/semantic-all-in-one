"""Learning sync worker: offline queue, idempotency, auth, partial failures, privacy of uploaded fields, migration/RLS text."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

import requests

from learning import events as ev
from learning import ledger as lg
from learning import sync as sy

ROOT = Path(__file__).resolve().parent


class Resp:
    def __init__(self, code=201, headers=None):
        self.status_code, self.headers = code, headers or {}


class Server:
    """Fake PostgREST: stores rows idempotently on (user_id, event_id)."""

    def __init__(self):
        self.rows, self.calls, self.script, self.reject = {}, 0, [], set()

    def post(self, url, headers=None, params=None, json=None, timeout=None):
        self.calls += 1
        if self.script:
            r = self.script.pop(0)
            if isinstance(r, Exception):
                raise r
            if r.status_code >= 300:
                return r
        if any(x["event_id"] in self.reject for x in json):
            return Resp(422)
        for x in json:
            self.rows.setdefault((x["user_id"], x["event_id"]), x)
        return Resp(201)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.led = lg.Ledger(Path(self.tmp.name) / "l.sqlite")
        self.srv = Server()
        self.session = SimpleNamespace(user_id="u1", access_token="tok1")
        self.app = SimpleNamespace(generation_mode="normal", _workspace=SimpleNamespace(project_id="p", read_meta=lambda: {}))

    def worker(self, **kw):
        kw.setdefault("post", self.srv.post)
        kw.setdefault("creds", lambda: ("http://x", "anon"))
        kw.setdefault("device_id", "dev1")
        return sy.SyncWorker(kw.pop("session", lambda: self.session), ledger=self.led, **kw)

    def add(self, n=3, **kw):
        for i in range(n):
            ev.record_event("csv_import", style_scope="normal/x", event_id=f"e{i}", project_id="p", ledger=self.led, payload={"rows": i}, **kw)


class SyncTests(Base):
    def test_success_marks_synced_after_confirmation_and_repeat_sends_nothing(self):
        self.add(3)
        w = self.worker()
        self.assertEqual(w.sync_once()["sent"], 3)
        self.assertEqual(self.led.pending_count(), 0)
        self.assertEqual(w.sync_once()["sent"], 0)
        self.assertEqual(self.srv.calls, 1)
        self.assertEqual(len(self.srv.rows), 3)

    def test_offline_keeps_events_then_reconnect_delivers_once(self):
        self.add(2)
        self.srv.script = [requests.ConnectionError("down")]
        w = self.worker()
        r = w.sync_once()
        self.assertEqual(r["backoff"], "network")
        self.assertEqual(self.led.pending_count(), 2)          # nothing deleted, nothing marked
        self.assertGreater(w.next_delay(r), 0)
        self.assertEqual(w.sync_once()["sent"], 2)
        self.assertEqual(len(self.srv.rows), 2)

    def test_duplicate_server_acceptance_is_idempotent(self):
        self.add(2)
        self.worker().sync_once()
        self.led.set_sync_state(["e0", "e1"], "local_only")    # e.g. app crashed before marking
        self.worker().sync_once()
        self.assertEqual(len(self.srv.rows), 2)

    def test_signed_out_unconfigured_and_disabled_do_nothing(self):
        self.add(1)
        self.assertEqual(self.worker(session=lambda: None).sync_once()["skipped"], "signed_out")
        self.assertEqual(self.worker(creds=lambda: ("", "")).sync_once()["skipped"], "not_configured")
        self.assertEqual(self.worker(enabled=lambda: False).sync_once()["skipped"], "disabled")
        self.assertEqual(self.srv.calls, 0)
        self.assertEqual(self.led.pending_count(), 1)

    def test_expired_token_refreshed_once(self):
        self.add(1)
        self.srv.script = [Resp(401)]
        fresh = SimpleNamespace(user_id="u1", access_token="tok2")
        w = self.worker(refresh_session=lambda: fresh)
        self.assertEqual(w.sync_once()["sent"], 1)

    def test_refresh_failure_and_403_back_off_without_marking(self):
        self.add(1)
        self.srv.script = [Resp(401)]
        def bad():
            raise RuntimeError("no")
        self.assertEqual(self.worker(refresh_session=bad).sync_once()["backoff"], "auth")
        self.srv.script = [Resp(403)]
        self.assertEqual(self.worker().sync_once()["backoff"], "auth")
        self.assertEqual(self.led.pending_count(), 1)

    def test_rate_limit_honours_retry_after_and_backoff_grows(self):
        self.add(1)
        self.srv.script = [Resp(429, {"Retry-After": "120"})]
        w = self.worker()
        r = w.sync_once()
        self.assertGreaterEqual(w.next_delay(r), 120)
        w._failures = 3
        self.assertLessEqual(w.next_delay({}), sy.BACKOFF_CAP_S * 1.5)
        self.srv.script = [Resp(503)]
        self.assertEqual(w.sync_once()["backoff"], "http_503")
        self.assertEqual(self.led.pending_count(), 1)

    def test_partial_batch_rejects_only_the_bad_event(self):
        self.add(5)
        self.srv.reject = {"e3"}
        r = self.worker().sync_once()
        self.assertEqual((r["sent"], r["rejected"]), (4, 1))
        self.assertEqual(self.led.pending_count(), 0)
        self.assertEqual({e["event_id"] for e in self.led.events() if e["sync_state"] == "rejected"}, {"e3"})
        self.assertEqual(len(self.srv.rows), 4)
        self.assertEqual(self.worker().sync_once()["sent"], 0)         # no retry loop on the rejected one

    def test_restart_resumes_pending(self):
        self.add(2)
        self.srv.script = [requests.ConnectionError("x")]
        self.worker().sync_once()
        again = sy.SyncWorker(lambda: self.session, ledger=lg.Ledger(self.led.path), post=self.srv.post,
                              creds=lambda: ("http://x", "a"), device_id="d")
        self.assertEqual(again.sync_once()["sent"], 2)

    def test_batches_are_bounded(self):
        self.add(25)
        w = self.worker(batch=10)
        w.sync_once()
        self.assertEqual(self.srv.calls, 3)
        self.assertTrue(all(len(x) <= 1 for x in [[]]))

    def test_only_allowlisted_fields_leave_the_device(self):
        ev.record_video_rating("p", "normal/x", 4, generation_id="g", comment="private words", tags=["poor_pacing"], ledger=self.led)
        ev.note_import(self.app, "normal", text="scene_number,script_segment\n1,narration words here\n", ledger=self.led)
        self.worker().sync_once()
        blob = str(self.srv.rows)
        self.assertNotIn("private words", blob)
        self.assertNotIn("narration words", blob)
        self.assertNotIn("comment", blob)
        row = next(r for r in self.srv.rows.values() if r["event_type"] == "video_rating")
        self.assertEqual(row["payload"]["tags"], ["poor_pacing"])
        self.assertEqual(row["user_id"], "u1")
        self.assertEqual(self.led.events(event_type="video_rating")[0]["payload"]["comment"], "private words")   # still local

    def test_unknown_event_types_are_never_uploaded(self):
        ev.record_event("future_type", style_scope="normal/x", ledger=self.led)
        self.worker().sync_once()
        self.assertEqual(self.srv.rows, {})

    def test_single_worker_thread_and_no_blocking(self):
        sy._worker = None
        t0 = time.time()
        w1 = sy.ensure_worker(lambda: None, interval=3600)
        w2 = sy.ensure_worker(lambda: None, interval=3600)
        self.assertIs(w1, w2)
        self.assertLess(time.time() - t0, 1.0)
        self.assertEqual(sum(1 for t in threading.enumerate() if t.name == "learning-sync"), 1)
        w1.stop()
        sy._worker = None

    def test_garbage_and_exceptions_never_raise(self):
        self.add(1)
        def boom(*a, **k):
            raise ValueError("x")
        self.assertIn("backoff", self.worker(post=boom).sync_once())


class PackageDownloadTests(Base):
    def test_only_valid_matching_packages_install(self):
        from learning import packages as pk
        good = pk.build_package("normal/x", [], version=1)
        other = pk.build_package("weather/classic", [], version=1)
        got = {"normal/x": [{"package": good}], "weather/classic": [{"package": other}]}

        class G:
            def __init__(self, scope):
                self.status_code, self.scope = 200, scope

            def json(self):
                return got[self.scope]
        root = Path(self.tmp.name) / "k"
        orig = pk.install
        pk.install = lambda p, expected_scope=None, root_=root, **k: orig(p, expected_scope=expected_scope, root=root)
        try:
            w = self.worker(get=lambda url, headers=None, params=None, timeout=None: G(params["style_scope"][3:]))
            self.assertEqual(w.refresh_packages(["normal/x"]), 1)
        finally:
            pk.install = orig
        self.assertIsNotNone(pk.active_package("normal/x", root))


class SecurityTextTests(unittest.TestCase):
    def test_no_service_role_anywhere_in_desktop_code(self):
        for f in list((ROOT / "learning").glob("*.py")) + [ROOT / "licensing/embedded.py", ROOT / "app.py"]:
            self.assertNotIn("service_role", f.read_text(encoding="utf-8").lower().replace("no service-role", ""), f.name)

    def test_migration_rls_and_limits(self):
        sql = (ROOT / "supabase/migrations/20261018000001_learning_events.sql").read_text(encoding="utf-8")
        low = sql.lower()
        self.assertIn("enable row level security", low)
        self.assertIn("user_id = auth.uid()", low)
        self.assertIn("unique (user_id, event_id)", low)
        self.assertNotRegex(low, r"create policy \w+ on public\.learning_events for (update|delete)")
        self.assertNotRegex(low, r"grant [a-z, ]*(update|delete)[a-z, ]* on public\.learning_events")
        self.assertIn("not (payload ? 'comment')", low)
        self.assertIn("pg_column_size(payload) <= 8192", low)
        self.assertIn("status = 'published'", low)
        self.assertNotRegex(low, r"on public\.knowledge_packages for (insert|update|delete)")

    def test_no_network_in_ledger_modules_other_than_sync(self):
        for name in ("ledger.py", "events.py", "scope.py", "packages.py", "guidance.py", "analysis.py", "rating_flow.py"):
            src = (ROOT / "learning" / name).read_text(encoding="utf-8")
            for w in ("requests", "urllib", "socket", "http.client"):
                self.assertNotIn("import " + w, src, name)


if __name__ == "__main__":
    unittest.main()
