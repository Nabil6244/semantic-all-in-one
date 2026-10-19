"""A stuck download or media tool never freezes a Generate (News Doc sat 36 min on one download on Windows, 2026-10-19).

Real ffmpeg processes, made to hang on purpose: the watchdog stops the stuck one, leaves a busy one alone, and writes a report that
says where the app was waiting. Runs on Windows and both Macs in CI."""

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

import stall_guard


def _ffmpeg():
    try:
        from map_scene.render import _ffmpeg as find

        f = find()
        if f and Path(f).is_file():
            return str(f)
    except Exception:
        pass
    return shutil.which("ffmpeg")


FFMPEG = _ffmpeg()


def _hung_ffmpeg(out: Path) -> subprocess.Popen:
    """ffmpeg waiting on an input nobody ever writes: alive, using no CPU — a stalled download looks exactly like this."""
    return subprocess.Popen([FFMPEG, "-y", "-v", "error", "-f", "s16le", "-ar", "8000", "-ac", "1", "-i", "pipe:0", str(out)],
                            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _dog(folder: Path, *, quiet_since: float, logs: list, stall_s: float = 1.0, report_s: float = 600.0):
    return stall_guard.StallWatchdog(last_activity=lambda: quiet_since, is_running=lambda: True, log=logs.append,
                                     report_dir=lambda: folder, last_step=lambda: "News Doc: downloading 35s", stall_s=stall_s,
                                     report_s=report_s, check_every=0.2)


def _until(cond, seconds: float = 20.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.2)
    return cond()


@unittest.skipUnless(FFMPEG and stall_guard._psutil(), "needs ffmpeg and psutil")
class StuckTools(unittest.TestCase):
    def test_a_hung_ffmpeg_is_stopped_and_reported(self):
        with tempfile.TemporaryDirectory() as d:
            proc, logs = _hung_ffmpeg(Path(d) / "x.wav"), []
            try:
                dog = _dog(Path(d), quiet_since=time.monotonic() - 3600, logs=logs).start()
                self.assertTrue(_until(lambda: proc.poll() is not None), "the stuck ffmpeg was never stopped")
                dog.close()
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait()
            self.assertTrue(dog.stopped and "ffmpeg" in dog.stopped[0].lower(), dog.stopped)
            self.assertTrue(any("[Watchdog]" in m and "stopped" in m for m in logs), logs)
            report = list(Path(d).glob("stall_*.txt"))
            self.assertEqual(len(report), 1)
            text = report[0].read_text(encoding="utf-8")
            self.assertIn("News Doc: downloading 35s", text)
            self.assertIn("--- thread MainThread", text)        # where every thread was waiting

    def test_the_waiting_step_gets_an_error_and_goes_on(self):
        """The code that waited on the stuck tool returns (with a failure) instead of waiting forever."""
        with tempfile.TemporaryDirectory() as d:
            done = {}

            r_fd, w_fd = os.pipe()   # the input stays open and silent, like a stalled network read

            def step():
                r = subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "s16le", "-ar", "8000", "-ac", "1", "-i", "pipe:0",
                                    str(Path(d) / "y.wav")], stdin=r_fd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                done["rc"] = r.returncode

            t = threading.Thread(target=step, daemon=True)
            t.start()
            dog = _dog(Path(d), quiet_since=time.monotonic() - 3600, logs=[]).start()
            t.join(25)
            dog.close()
            os.close(w_fd)
            os.close(r_fd)
            self.assertFalse(t.is_alive(), "the step still waits on the stuck ffmpeg")
            self.assertNotEqual(done.get("rc"), 0)

    def test_a_busy_encode_is_left_alone(self):
        with tempfile.TemporaryDirectory() as d:
            proc = subprocess.Popen([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30", "-t", "8",
                                     "-c:v", "mpeg4", "-q:v", "2", "-f", "null", "-"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                dog = _dog(Path(d), quiet_since=time.monotonic() - 3600, logs=[], stall_s=2.0)
                end = time.monotonic() + 5
                while time.monotonic() < end and proc.poll() is None:
                    dog.check_once()
                    time.sleep(0.5)
                self.assertEqual(dog.stopped, [])
            finally:
                proc.kill()
                proc.wait()

    def test_nothing_is_stopped_while_the_app_keeps_logging(self):
        with tempfile.TemporaryDirectory() as d:
            proc = _hung_ffmpeg(Path(d) / "x.wav")
            try:
                dog = _dog(Path(d), quiet_since=0, logs=[])
                dog.last_activity = time.monotonic   # a log line every moment
                for _ in range(8):
                    dog.check_once()
                    time.sleep(0.3)
                self.assertIsNone(proc.poll())
                self.assertEqual(dog.stopped, [])
            finally:
                proc.kill()
                proc.wait()


class QuietStretch(unittest.TestCase):
    def test_a_long_quiet_wait_gets_one_report(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(stall_guard.StallWatchdog, "_children", lambda self: []):
            logs = []
            dog = _dog(Path(d), quiet_since=time.monotonic() - 700, logs=logs)
            dog.check_once()
            dog.check_once()                                      # same quiet stretch: no second report
            self.assertEqual(len(list(Path(d).glob("stall_*.txt"))), 1)
            self.assertTrue(any("No progress" in m and "Press Stop" in m for m in logs), logs)

    def test_off_when_no_generate_runs(self):
        with tempfile.TemporaryDirectory() as d:
            dog = stall_guard.StallWatchdog(last_activity=lambda: 0.0, is_running=lambda: False, log=lambda m: None,
                                            report_dir=lambda: Path(d), report_s=0.0)
            self.assertEqual(dog.check_once(), [])
            self.assertEqual(list(Path(d).glob("*")), [])

    def test_watches_only_media_and_download_tools(self):
        for name in ("ffmpeg", "ffmpeg.exe", "FFPROBE.EXE", "yt-dlp", "yt-dlp.exe"):
            self.assertTrue(stall_guard._watched(name), name)
        for name in ("chrome.exe", "node", "python", "ffplay", "Semantic YT Studio.exe"):
            self.assertFalse(stall_guard._watched(name), name)


class AppWiring(unittest.TestCase):
    def test_app_starts_the_watchdog_and_marks_real_log_lines(self):
        src = Path(__file__).with_name("app.py").read_text(encoding="utf-8")
        self.assertIn("from stall_guard import install_for_app", src)
        self.assertIn("self._last_real_log_at = self._last_log_at", src)
        spec = Path(__file__).with_name("VideoGenerator.spec").read_text(encoding="utf-8")
        self.assertIn('"stall_guard", "psutil"', spec)

    def test_install_for_app_reads_the_app_flags(self):
        app = NS(_RUN_FLAGS=("_running",), _running=False, _workspace=None, _append_log=lambda m: None, _last_log_at=0.0)
        dog = stall_guard.install_for_app(app)
        try:
            self.assertIsNotNone(dog)
            self.assertEqual(dog.check_once(), [])
        finally:
            dog.close()


if __name__ == "__main__":
    unittest.main()
