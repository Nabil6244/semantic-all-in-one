#!/usr/bin/env python3
"""Agent batches: a lost app<->engine connection is never a failed batch.

The app reconnects to the SAME engine, asks for the results it missed (RUN_EVENTS) and never sends the batch again; only a
gone engine process fails the waiting scenes, with a reason. Finished images are placed off the connection thread (slow
Visual QA there blocked keepalive replies until the socket dropped). Waiting for an earlier agent batch never stops or resets
it. Normal (non-agent) batches keep their old behaviour. No real engine or Flow call is used.
"""

from __future__ import annotations

import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from providers.base import SceneRow, SceneStatus
from providers.flow import provider as provider_mod
from providers.flow.provider import FlowProvider


def _png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 96)


class FakeClient:
    """A scriptable engine connection. Messages are delivered on a separate thread, like the real socket."""

    def __init__(self, root: Path, state=None):
        self.root = root
        self.alive = True
        self.subs = []
        self.sent = []
        self.generates = []
        self.stops = 0
        self.resets = 0
        self.state = state or {"running": False, "accounts": []}
        self.on_generate = None
        self.on_send = None
        self.deliver_threads = set()

    # connection
    def is_alive(self):
        return self.alive

    def subscribe(self, fn):
        self.subs.append(fn)
        return lambda: self.subs.remove(fn) if fn in self.subs else None

    def deliver(self, msg):
        self.deliver_threads.add(threading.current_thread().name)
        for fn in list(self.subs):
            fn(msg)

    def get_state(self):
        return dict(self.state)

    def get_info(self):
        return {"downloadsRoot": str(self.root)}

    def wait_for(self, predicate, timeout=600.0):
        got = []
        ev = threading.Event()

        def watch(m):
            if predicate(m):
                got.append(m)
                ev.set()
        self.subs.append(watch)
        try:
            if not ev.wait(timeout):
                raise TimeoutError("no answer")
            return got[0]
        finally:
            self.subs.remove(watch)

    # commands
    def send(self, msg):
        self.sent.append(msg)
        if self.on_send:
            self.on_send(msg)

    def generate(self, prompts, settings=None, account_ids=None, prompt_keys=None):
        self.generates.append(settings)
        if self.on_generate:
            threading.Thread(target=self.on_generate, args=(settings,), name="ws-thread", daemon=True).start()

    def stop(self):
        self.stops += 1

    def force_stop(self):
        self.stops += 1

    def reset_generate(self):
        self.resets += 1


class FakeManager:
    def __init__(self, client, reconnect_to=None):
        self.client = client
        self.reconnect_to = reconnect_to
        self.reconnects = 0

    def ensure_running(self):
        return self.client

    def reconnect(self):
        self.reconnects += 1
        if self.reconnect_to is not None:
            self.client = self.reconnect_to
        return self.reconnect_to

    def start(self):
        return self.client


def _scenes(n):
    return [SceneRow(scene_number=str(i + 1), script_segment=f"s{i}", asset_type="image", prompt=f"p{i}") for i in range(n)]


AGENT = {"model": "BELUGA", "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE", "generationMode": "agent"}


class TestAgentConnectionLoss(unittest.TestCase):
    def test_lost_connection_reconnects_catches_up_and_never_resends(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            c1, c2 = FakeClient(root), FakeClient(root)
            missed = []

            def engine(settings):
                out = settings["outputDir"]
                f0, f1 = root / "a" / "001.png", root / "a" / "002.png"
                _png(f0)
                c1.deliver({"type": "BATCH_PROGRESS", "index": 0, "status": "running", "label": "A1", "message": "Agent generating"})
                c1.deliver({"type": "BATCH_PROGRESS", "index": 0, "status": "done", "path": str(f0)})
                c1.alive = False            # the app's socket drops; the engine carries on
                _png(f1)
                missed.extend([{"type": "BATCH_PROGRESS", "index": 1, "status": "done", "path": str(f1)},
                               {"type": "GENERATE_DONE", "outputDir": out}])

            def replay(msg):
                if msg.get("type") == "RUN_EVENTS":
                    def go():
                        for ev in missed:
                            c2.deliver(ev)
                        c2.deliver({"type": "RUN_EVENTS_END", "outputDir": msg["outputDir"], "known": True, "count": len(missed), "running": False})
                    threading.Thread(target=go, daemon=True).start()

            c1.on_generate = engine
            c2.on_send = replay
            mgr = FakeManager(c1, reconnect_to=c2)
            logs = []
            res = FlowProvider(mgr, media_kind="image", flow_settings=AGENT).resolve_batch(_scenes(2), root, log=logs.append)
            self.assertEqual([res[s].status for s in ("1", "2")], [SceneStatus.READY, SceneStatus.READY])
            self.assertEqual(len(c1.generates) + len(c2.generates), 1, "the batch is sent exactly once")
            self.assertEqual(mgr.reconnects, 1)
            self.assertEqual((c1.stops, c1.resets, c2.stops, c2.resets), (0, 0, 0, 0), "nothing stopped or reset")
            self.assertTrue(any("Caught up on 2 result" in m for m in logs))
            self.assertFalse(any("stopped unexpectedly" in m for m in logs))

    def test_engine_process_gone_fails_waiting_scenes_with_a_reason_and_sends_nothing_again(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            c1 = FakeClient(root)

            def engine(_settings):
                c1.deliver({"type": "BATCH_PROGRESS", "index": 0, "status": "running", "label": "A1", "message": "Agent generating"})
                c1.alive = False
            c1.on_generate = engine
            mgr = FakeManager(c1, reconnect_to=None)
            res = FlowProvider(mgr, media_kind="image", flow_settings=AGENT).resolve_batch(_scenes(2), root, log=lambda *_: None)
            for s in ("1", "2"):
                self.assertNotEqual(res[s].status, SceneStatus.READY)
                self.assertIn("process stopped", res[s].error)
                self.assertIn("Nothing was sent again", res[s].error)
            self.assertEqual(len(c1.generates), 1)
            self.assertEqual((c1.stops, c1.resets), (0, 0))

    def test_finished_images_are_placed_off_the_connection_thread(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            c1 = FakeClient(root)
            ready_threads = []
            delivery_times = []

            def engine(settings):
                for i in range(2):
                    f = root / "a" / f"{i + 1:03d}.png"
                    _png(f)
                    t0 = time.monotonic()
                    c1.deliver({"type": "BATCH_PROGRESS", "index": i, "status": "done", "path": str(f)})
                    delivery_times.append(time.monotonic() - t0)
                c1.deliver({"type": "GENERATE_DONE", "outputDir": settings["outputDir"]})
            c1.on_generate = engine

            def slow_ready(scene, result):
                ready_threads.append(threading.current_thread().name)
                time.sleep(0.5)      # stands in for Visual QA

            FlowProvider(FakeManager(c1), media_kind="image", flow_settings=AGENT).resolve_batch(
                _scenes(2), root, log=lambda *_: None, on_scene_ready=slow_ready)
            self.assertEqual(len(ready_threads), 2)
            self.assertNotIn("ws-thread", ready_threads, "slow placement never runs on the connection thread")
            self.assertTrue(all(t < 0.2 for t in delivery_times), delivery_times)


class TestAgentIdleWait(unittest.TestCase):
    def test_an_earlier_agent_batch_is_waited_for_never_stopped_or_reset(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            c = FakeClient(root, state={"running": True, "accounts": [{"progress": {"status": "running"}}]})
            threading.Timer(1.5, lambda: c.state.update({"running": False})).start()
            fp = FlowProvider(FakeManager(c), media_kind="image", flow_settings=AGENT)
            err, client = fp._wait_for_agent_engine_idle(c, lambda *_: None, None)
            self.assertIsNone(err)
            self.assertEqual((c.stops, c.resets), (0, 0))

    def test_a_stale_busy_flag_with_no_account_working_is_cleared(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            c = FakeClient(root, state={"running": True, "accounts": [{"progress": {"status": "idle"}}]})
            c.reset_generate = lambda: (setattr(c, "resets", c.resets + 1), c.state.update({"running": False}))
            fp = FlowProvider(FakeManager(c), media_kind="image", flow_settings=AGENT)
            with mock.patch.object(provider_mod, "_AGENT_STALE_FLAG_SECONDS", 0.5):
                err, _ = fp._wait_for_agent_engine_idle(c, lambda *_: None, None)
            self.assertIsNone(err)
            self.assertEqual((c.stops, c.resets), (0, 1))


class TestNormalBatchesUnchanged(unittest.TestCase):
    def test_a_normal_batch_keeps_the_old_wait_and_connection_handling(self):
        fp = FlowProvider(FakeManager(None), media_kind="image", flow_settings={"model": "BELUGA"})
        self.assertFalse(fp._is_agent_batch())
        self.assertFalse(FlowProvider(FakeManager(None), media_kind="video", flow_settings=AGENT)._is_agent_batch())
        self.assertTrue(FlowProvider(FakeManager(None), media_kind="image", flow_settings=AGENT)._is_agent_batch())


if __name__ == "__main__":
    unittest.main()
