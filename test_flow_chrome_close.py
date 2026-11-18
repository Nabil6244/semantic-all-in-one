"""Flow Chrome must be closed cleanly so Google sign-in cookies survive."""
import subprocess
import unittest
from unittest import mock

from providers.flow import chrome_close
from providers.flow import engine_manager


class ChromeMainOnlyTest(unittest.TestCase):
    def test_only_main_process_on_flow_profile(self):
        main = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome --user-data-dir=/u/.semantic-automator-desktop/profiles/a"
        helper = "Google Chrome Helper --type=utility --user-data-dir=/u/.semantic-automator-desktop/profiles/a"
        own = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        self.assertTrue(chrome_close.is_flow_chrome_main(main))
        self.assertFalse(chrome_close.is_flow_chrome_main(helper))
        self.assertFalse(chrome_close.is_flow_chrome_main(own))

    def test_gentle_first_force_only_if_still_running(self):
        calls = []
        lists = iter([[11], [], []])
        with mock.patch.object(chrome_close, "_flow_mains", side_effect=lambda: next(lists)), \
             mock.patch.object(chrome_close, "_ask_quit", side_effect=lambda pid, force: calls.append((pid, force))):
            self.assertEqual(chrome_close.close_flow_chrome(grace=1.0), 1)
        self.assertEqual(calls, [(11, False)])


class EngineStopAsksFirstTest(unittest.TestCase):
    def test_stop_sends_shutdown_and_waits_before_kill(self):
        mgr = engine_manager.FlowEngineManager.__new__(engine_manager.FlowEngineManager)
        mgr.log = lambda *_: None
        client = mock.Mock()
        proc = mock.Mock()
        state = {"alive": True}
        proc.poll.side_effect = lambda: None if state["alive"] else 0
        proc.pid = 123

        def wait(timeout=None):
            state["alive"] = False
            return 0

        proc.wait.side_effect = wait
        mgr._client, mgr._proc = client, proc
        with mock.patch.object(subprocess, "run") as run:
            mgr.stop()
        client.send.assert_called_once_with({"type": "SHUTDOWN"})
        run.assert_not_called()
        proc.terminate.assert_not_called()
        proc.kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
