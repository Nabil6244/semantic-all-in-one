"""The app must never reuse a Flow engine that runs OUTDATED code.

Reproduced on a real machine: the Node engine (flow-engine/server.js) had
been running since three days earlier. Node only loads code at start, so
after batch-runner.js moved Flow VIDEO to the UI-based path, that engine
kept executing its old direct-RPC video code — and the app's "Reusing an
already-running engine on port 8787" handed every Flow video job to it.

Now the engine reports a fingerprint of the code it loaded (INFO.codeVersion)
and the app compares it with the files on disk; a missing (pre-fingerprint)
or different version is retired and replaced.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from providers.flow import engine_manager as em

ENGINE_DIR = Path(__file__).resolve().parent / "flow-engine"


class _FakeClient:
    def __init__(self, info):
        self._info = info
        self.sent = []

    def get_info(self):
        return self._info

    def send(self, msg):
        self.sent.append(msg)

    def close(self):
        pass


class TestCodeFingerprint(unittest.TestCase):
    def test_fingerprint_changes_when_engine_code_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "flow-engine"
            (root / "lib").mkdir(parents=True)
            (root / "server.js").write_text("// server")
            (root / "lib" / "batch-runner.js").write_text("generateOneVideo()")
            before = em.engine_code_version(root)
            (root / "lib" / "batch-runner.js").write_text("generateOneVideoViaUI()")
            self.assertNotEqual(before, em.engine_code_version(root))

    @unittest.skipUnless(shutil.which("node") or (Path(__file__).parent / "bin" / "node").exists(), "node required")
    def test_python_fingerprint_matches_what_server_js_computes(self):
        node = shutil.which("node") or str(Path(__file__).parent / "bin" / "node")
        script = (
            "import('node:crypto').then(async c=>{const fs=await import('node:fs');const path=await import('node:path');"
            "const root=process.argv[1];const files=['server.js'].concat(fs.readdirSync(path.join(root,'lib'))"
            ".filter(f=>f.endsWith('.js')).sort().map(f=>'lib/'+f));const h=c.createHash('sha256');"
            "for(const r of files){h.update(r);h.update('\\0');h.update(fs.readFileSync(path.join(root,r)));h.update('\\0');}"
            "console.log(h.digest('hex').slice(0,16));})"
        )
        out = subprocess.run([node, "-e", script, str(ENGINE_DIR)], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.stdout.strip(), em.engine_code_version(ENGINE_DIR))
        # And server.js really embeds the same algorithm.
        server = (ENGINE_DIR / "server.js").read_text()
        self.assertIn("ENGINE_CODE_VERSION", server)
        self.assertIn("codeVersion: ENGINE_CODE_VERSION", server)


class TestReuseDecision(unittest.TestCase):
    def setUp(self):
        self.mgr = em.FlowEngineManager(engine_dir=ENGINE_DIR, log=lambda *_: None)

    def test_engine_from_before_fingerprints_is_not_reused(self):
        self.assertFalse(self.mgr._running_engine_is_current(_FakeClient({}), wait_s=0.2))

    def test_engine_with_different_code_is_not_reused(self):
        self.assertFalse(self.mgr._running_engine_is_current(_FakeClient({"codeVersion": "0000"}), wait_s=0.2))

    def test_engine_with_current_code_is_reused(self):
        current = em.engine_code_version(ENGINE_DIR)
        self.assertTrue(self.mgr._running_engine_is_current(_FakeClient({"codeVersion": current}), wait_s=0.2))

    def test_retire_asks_the_engine_to_shut_down_first(self):
        client = _FakeClient({})
        with mock.patch.object(self.mgr, "_wait_port_free", return_value=True):
            self.mgr._retire_running_engine(client)
        self.assertEqual(client.sent, [{"type": "SHUTDOWN"}])

    def test_only_a_node_server_js_process_is_ever_terminated(self):
        client = _FakeClient({})
        with mock.patch.object(self.mgr, "_wait_port_free", side_effect=[False, True]), \
                mock.patch.object(em, "_pids_listening_on", return_value=[111, 222]), \
                mock.patch.object(em, "_is_flow_engine_process", side_effect=lambda pid: pid == 222), \
                mock.patch.object(em, "_terminate_pid") as kill:
            self.mgr._retire_running_engine(client)
        kill.assert_called_once_with(222)

    def test_unstoppable_old_engine_fails_clearly_instead_of_running_old_code(self):
        with mock.patch.object(self.mgr, "_wait_port_free", return_value=False), \
                mock.patch.object(em, "_pids_listening_on", return_value=[]):
            with self.assertRaises(em.FlowEngineError):
                self.mgr._retire_running_engine(_FakeClient({}))

    def test_old_engine_that_lingers_after_graceful_stop_is_forced(self):
        # Measured: SIGTERM freed the port but the old process stayed alive
        # because another app window kept its WebSocket open.
        client = _FakeClient({})
        with mock.patch.object(self.mgr, "_wait_port_free", return_value=True), \
                mock.patch.object(em, "_pids_listening_on", return_value=[222]), \
                mock.patch.object(em, "_is_flow_engine_process", return_value=True), \
                mock.patch.object(em, "_pid_alive", return_value=True), \
                mock.patch.object(em.time, "sleep"), \
                mock.patch.object(em, "_terminate_pid") as kill:
            self.mgr._retire_running_engine(client)
        kill.assert_called_with(222, force=True)

    def test_dead_cached_client_is_not_returned(self):
        dead = mock.Mock()
        dead.is_alive.return_value = False
        self.mgr._client = dead
        with mock.patch.object(em, "_find_node_binary", return_value=None):
            with self.assertRaises(em.FlowEngineError):  # it tried to (re)start rather than reuse
                self.mgr.start(timeout=1)

    def test_this_process_is_not_a_flow_engine(self):
        import os

        self.assertFalse(em._is_flow_engine_process(os.getpid()))


class _SpawnAttempted(Exception):
    pass


class TestEngineOwnership(unittest.TestCase):
    """A Flow engine this app didn't spawn must never be reused, even when it
    runs current code: its owner controls its lifetime (on a user's Mac its
    Chrome windows closed 0.3s into Generate and the batch hung until Stop),
    and its output never reaches the app log."""

    def setUp(self):
        self.mgr = em.FlowEngineManager(engine_dir=ENGINE_DIR, log=lambda *_: None)
        current = em.engine_code_version(ENGINE_DIR)
        probe = mock.Mock()
        probe.get_info.return_value = {"codeVersion": current}
        probe.get_state.return_value = {"running": False}
        self.probe = probe
        self.patches = [
            mock.patch.object(em, "FlowClient", return_value=probe),
            mock.patch.object(em, "_find_node_binary", return_value="node"),
            mock.patch.object(self.mgr, "is_installed", return_value=True),
            mock.patch.object(self.mgr, "ensure_browser"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_foreign_engine_with_current_code_is_replaced_not_reused(self):
        with mock.patch.object(self.mgr, "_retire_running_engine") as retire, \
                mock.patch.object(em.hidden_subprocess, "popen", side_effect=_SpawnAttempted):
            with self.assertRaises(_SpawnAttempted):
                self.mgr.start(timeout=1)
        retire.assert_called_once_with(self.probe)

    def test_our_own_live_engine_is_still_reused(self):
        own = mock.Mock()
        own.poll.return_value = None  # the Node process we spawned is alive
        self.mgr._proc = own
        with mock.patch.object(self.mgr, "_retire_running_engine") as retire, \
                mock.patch.object(em.hidden_subprocess, "popen", side_effect=_SpawnAttempted):
            client = self.mgr.start(timeout=1)
        self.assertIs(client, self.probe)
        retire.assert_not_called()


if __name__ == "__main__":
    unittest.main()
