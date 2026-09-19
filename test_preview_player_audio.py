"""Audio-availability honesty in PreviewPlayer (ui/preview_player.py).

Reported live: a real running instance of the app had NO sound in the
Editor's preview at all — traced to the actual runtime environment
missing the `sounddevice` dependency (installed in the dev/test venv used
by this repo's automated tests, but not in the environment `python app.py`
was actually launched from). The video-only playback silently looked
"normal", giving no indication audio wasn't playing — exactly the kind of
fake/silent behavior the editor must never have. This file covers the fix:
a visible, honest indicator whenever real audio truly cannot play.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class TestAudioAvailabilityIndicator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import customtkinter as ctk
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")
        try:
            cls.root = ctk.CTk()
            cls.root.withdraw()
        except Exception as exc:
            raise unittest.SkipTest(f"no Tk display available: {exc}")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def test_no_sounddevice_shows_a_visible_no_audio_indicator(self):
        import ui.preview_player as pp

        orig_sd = pp._sd
        pp._sd = None
        try:
            player = pp.PreviewPlayer(self.root)
            try:
                self.assertFalse(player._audio.available)
                self.assertIn("no audio device", player._audio_status_label.cget("text"))
            finally:
                player.destroy()
        finally:
            pp._sd = orig_sd

    def test_sounddevice_available_shows_no_warning(self):
        import ui.preview_player as pp

        if pp._sd is None:
            self.skipTest("sounddevice genuinely unavailable in this environment")
        player = pp.PreviewPlayer(self.root)
        try:
            self.assertTrue(player._audio.available)
            self.assertEqual(player._audio_status_label.cget("text"), "")
        finally:
            player.destroy()

    def test_audio_play_returns_false_when_sounddevice_missing(self):
        """_AudioPlayer.play() now reports success/failure (was a bare
        None-returning no-op) so PreviewPlayer.play() can surface a
        runtime failure distinctly from "never available"."""
        import ui.preview_player as pp

        orig_sd = pp._sd
        pp._sd = None
        try:
            audio = pp._AudioPlayer()
            with tempfile.TemporaryDirectory() as td:
                fake = Path(td) / "x.wav"
                fake.write_bytes(b"RIFF....WAVEfmt ")
                ok = audio.play(fake, start_s=0.0)
                self.assertFalse(ok)
        finally:
            pp._sd = orig_sd

    def test_stream_open_failure_surfaces_a_distinct_message(self):
        """A stream that fails to actually START (device busy/denied,
        etc.) even though sounddevice itself IS available must show a
        DIFFERENT message than "no audio device" — a genuine runtime
        error, not simply "unsupported here"."""
        import ui.preview_player as pp

        if pp._sd is None:
            self.skipTest("sounddevice genuinely unavailable in this environment")

        import subprocess

        if not __import__("shutil").which("ffmpeg"):
            self.skipTest("ffmpeg not on PATH")
        with tempfile.TemporaryDirectory() as td:
            wav = Path(td) / "a.wav"
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(wav)],
                check=True, capture_output=True,
            )
            player = pp.PreviewPlayer(self.root)
            try:
                player._video_path = Path(td) / "does_not_need_to_exist.mp4"
                player._audio_path = wav
                player._duration = 1.0

                class _BrokenAudio:
                    available = True

                    def play(self, *a, **k):
                        return False

                    def stop(self):
                        pass

                player._audio = _BrokenAudio()
                player._seek_decoder = lambda *a, **k: None  # skip real ffmpeg decode for this check
                player.play()
                self.assertIn("audio device error", player._audio_status_label.cget("text"))
            finally:
                player.destroy()


class TestPlaybackSmoothness(unittest.TestCase):
    """Reported live: "the player is not smooth". Two concrete, provable
    Tk-side causes were found and fixed (never claimed as the ONLY
    possible cause — genuine perceptual smoothness cannot be verified
    without physically watching playback, which this environment cannot
    do):
      1. the canvas frame image was delete()d and recreated via
         create_image() on EVERY tick (up to PROXY_FPS/sec) instead of
         reusing one persistent item via itemconfigure — real, avoidable
         per-frame Tk overhead.
      2. _tick() rescheduled itself with a flat `self.after(interval, ...)`
         computed AFTER its own work finished, so any per-tick cost (or
         unrelated UI activity sharing the same Tk event loop) let the
         real-world interval between frames drift upward, compounding
         into visibly uneven pacing over time — now anchored to a
         monotonic clock instead.
    """

    @classmethod
    def setUpClass(cls):
        try:
            import customtkinter as ctk
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")
        try:
            cls.root = ctk.CTk()
            cls.root.withdraw()
        except Exception as exc:
            raise unittest.SkipTest(f"no Tk display available: {exc}")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def test_frame_image_item_is_reused_not_recreated_every_tick(self):
        import ui.preview_player as pp
        from PIL import Image

        player = pp.PreviewPlayer(self.root)
        try:
            before_ids = set(player._canvas.find_all())
            for i in range(5):
                img = Image.new("RGB", (4, 4), (i * 10, 0, 0))
                player._frame_queue.put((float(i), img))
                player._tick()
            after_ids = set(player._canvas.find_all())
            # No new canvas items were created across 5 delivered frames —
            # the same image item (plus the static empty-text item) is
            # reused throughout, not delete()+recreate()d each time.
            self.assertEqual(before_ids, after_ids)
            self.assertEqual(player._canvas.itemcget(player._frame_item, "state"), "normal")
        finally:
            player.destroy()

    def test_tick_scheduling_compensates_for_elapsed_work_time(self):
        """If a tick's own work takes real wall-clock time, the NEXT
        scheduled delay must shrink to compensate (anchored to a fixed
        cadence) rather than always re-adding a flat interval on top of
        however long this tick actually took (the old drift-prone
        pattern)."""
        import unittest.mock

        import ui.preview_player as pp

        player = pp.PreviewPlayer(self.root)
        try:
            delays = []
            player.after = lambda delay, fn: delays.append(delay)
            interval = 1000.0 / pp.PROXY_FPS
            base = 1_000_000.0  # an arbitrary monotonic-clock origin

            with unittest.mock.patch("time.monotonic", return_value=base):
                player._tick()
            self.assertAlmostEqual(delays[0], interval, delta=2)

            # The scheduled `after(interval, ...)` fires roughly on time,
            # but THIS tick's own work (queue drain, PhotoImage
            # conversion, canvas update) then eats an extra 0.5-interval
            # bite out of the cadence before it finishes and reschedules.
            second_now = base + (interval + 0.5 * interval) / 1000.0
            with unittest.mock.patch("time.monotonic", return_value=second_now):
                player._tick()
            # The next delay must shrink to compensate — NOT a flat
            # `interval` stacked on top of the time already lost.
            self.assertLess(delays[1], interval)
            self.assertAlmostEqual(delays[1], interval * 0.5, delta=2)
        finally:
            player.destroy()

    def test_a_genuine_stall_resyncs_instead_of_bursting_catch_up_ticks(self):
        """If the app was blocked for a long time (well over one frame
        interval — a real stall, not routine jitter), the next tick must
        resync to "now" rather than scheduling a rapid burst of catch-up
        ticks to make up for lost time."""
        import unittest.mock

        import ui.preview_player as pp

        player = pp.PreviewPlayer(self.root)
        try:
            delays = []
            player.after = lambda delay, fn: delays.append(delay)
            interval = 1000.0 / pp.PROXY_FPS
            base = 2_000_000.0

            with unittest.mock.patch("time.monotonic", return_value=base):
                player._tick()
            # Simulate a real multi-second stall before the next tick.
            with unittest.mock.patch("time.monotonic", return_value=base + 3.0):
                player._tick()
            self.assertAlmostEqual(delays[1], interval, delta=2)
        finally:
            player.destroy()


if __name__ == "__main__":
    unittest.main()
