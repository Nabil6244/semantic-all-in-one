"""War Documentary render resilience (Yousaf's Windows render, 2026-11-08: the segmented renderer failed and the Phase 1 fallback dropped
every War card, leaving merged clips only). A failing piece is re-rendered plainly, then over the backdrop; the fallback keeps the War
cards and the narration; a mixed track that fails the sync check is replaced by the plain voiceover."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cinematic_explainer.render import Layer, Shot
from cinematic_explainer.war import segments as SG


def _probe_audio(path: str) -> bool:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())


class ResilienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        cls.clip = str(d / "c.mp4")
        cls.plate = str(d / "plate.mp4")
        cls.voice = str(d / "v.wav")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:d=6", "-r", "25", cls.clip], check=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=0x101418:s=320x180:d=24", "-r", "25", cls.plate], check=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=f=220:d=4", cls.voice], check=True)
        cls.shots = [Shot(cls.clip, 0.0, 2.0, 0.0), Shot(cls.clip, 2.0, 4.0, 2.0)]
        cls.layers = [Layer("bc_label", 0.4, 1.8, {"text": "44 missiles"}, dim=False), Layer("kit_title", 2.2, 3.8, {"text": "Stalingrad"}, dim=False)]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_a_failing_piece_is_retried_not_fatal(self):
        real = SG._render_piece
        calls = {"n": 0}

        def flaky(piece, *a, **k):
            calls["n"] += 1
            if piece.index == 0 and piece.treat is not None or (piece.index == 0 and calls["n"] == 1):
                raise SG.RenderError("simulated Windows ffmpeg failure")
            return real(piece, *a, **k)

        out = str(Path(self.tmp.name, "a.mp4"))
        with mock.patch.object(SG, "_render_piece", side_effect=flaky):
            res = SG.render_with_fallback(self.shots, self.layers, out, audio_path=self.voice, backdrop_path=self.plate)
        self.assertTrue(res["ok"])
        self.assertFalse(res["fallback"])
        self.assertEqual(res["retried_pieces"], [0])

    def test_fallback_keeps_war_cards_and_narration(self):
        seen = {}

        def phase1(shots, layers, out, card_table=None, **k):
            seen["kinds"] = [ly.kind for ly in layers]
            seen["table"] = card_table
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=1280x720:d=4", "-r", "25", out], check=True)
            return {"frames": 100}

        out = str(Path(self.tmp.name, "b.mp4"))
        with mock.patch.object(SG, "render_segmented", side_effect=SG.RenderError("boom")), \
                mock.patch("cinematic_explainer.render.render", side_effect=phase1):
            res = SG.render_with_fallback(self.shots, self.layers, out, audio_path=self.voice)
        self.assertTrue(res["fallback"])
        self.assertEqual(seen["kinds"], ["bc_label", "kit_title"])            # nothing dropped
        self.assertIn("bc_label", seen["table"])
        self.assertTrue(_probe_audio(out))

    def test_basic_renderer_draws_war_cards_with_a_table(self):
        from cinematic_explainer import render as R
        from cinematic_explainer.war import registry

        data, n = R._frame_bytes(1.0, self.layers, bytes(1280 * 720 * 4), registry.all_cards())
        self.assertEqual(n, 1)
        self.assertNotEqual(data, bytes(1280 * 720 * 4))
        data2, _ = R._frame_bytes(1.0, [Layer("no_such_card", 0, 5, {})], bytes(1280 * 720 * 4), registry.all_cards())
        self.assertEqual(data2, bytes(1280 * 720 * 4))                       # an unknown card is skipped, never a crash


if __name__ == "__main__":
    unittest.main()


class PicturelessClipTests(unittest.TestCase):
    """2026-11-08: two archive downloads were empty MP4 shells (371 and 261 bytes, no streams). They counted as clips and stopped the render
    ("Stream specifier ... matches no streams")."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        cls.good = str(d / "good.mp4")
        cls.plate = str(d / "plate.mp4")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:d=4", "-r", "25", cls.good], check=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=0x101418:s=320x180:d=24", "-r", "25", cls.plate], check=True)
        cls.shell = str(d / "shell.mp4")                  # what ffmpeg writes when the cut starts past the source's end
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", "60", "-i", cls.good, "-t", "3", "-c:v", "libx264", "-f", "mp4", cls.shell])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_shell_has_no_picture_and_is_not_footage(self):
        from cinematic_explainer.war import integration as I
        self.assertFalse(SG.has_video(self.shell))
        self.assertTrue(SG.has_video(self.good))
        self.assertEqual(I.footage_from_record({"status": "complete", "local_path": self.shell}, Path(self.tmp.name)),
                         (None, "downloaded file has no picture"))

    def test_render_survives_a_shell_clip(self):
        shots = [Shot(self.good, 0.0, 2.0, 0.0), Shot(self.shell, 2.0, 4.0, 0.0)]
        out = str(Path(self.tmp.name, "s.mp4"))
        res = SG.render_with_fallback(shots, [Layer("bc_label", 2.2, 3.8, {"text": "44 missiles"}, dim=False)], out, backdrop_path=self.plate)
        self.assertTrue(res["ok"])
        self.assertFalse(res["fallback"])
