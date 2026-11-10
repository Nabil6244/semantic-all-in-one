"""Voxel Map voice-over timing reads the whole voice-over (a joined MP3 once read as 19 s and cut a 25-min film to 22 s)."""
import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("vm_narration_timing", HERE / "voxelmap-engine" / "tools" / "narration_timing.py")
nt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nt)


class LoadAudio(unittest.TestCase):
    def test_ffmpeg_output_becomes_16k_float_samples(self):
        samples = np.linspace(-1, 1, 32000, dtype=np.float32)
        seen = {}

        def run(cmd, **kw):
            seen["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, stdout=samples.tobytes(), stderr=b"")
        a = nt.load_audio("vo.mp3", run=run)
        self.assertEqual(a.size, 32000)
        self.assertIn("16000", seen["cmd"])
        self.assertIn("f32le", seen["cmd"])

    def test_ffmpeg_failure_falls_back_to_whisper_reading_the_file(self):
        def run(cmd, **kw):
            raise subprocess.CalledProcessError(1, cmd)
        self.assertIsNone(nt.load_audio("vo.mp3", run=run))

    @unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
    def test_two_mp3_clips_joined_are_read_to_the_end(self):
        with tempfile.TemporaryDirectory() as d:
            parts = []
            for i, (f, dur) in enumerate(((440, 3), (660, 5))):
                p = Path(d) / f"p{i}.mp3"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency={f}:duration={dur}",
                                "-ar", "24000", "-ac", "1", str(p)], check=True)
                parts.append(p.read_bytes())
            joined = Path(d) / "joined.mp3"
            joined.write_bytes(b"".join(parts))      # raw byte join, as voice-over tools do
            a = nt.load_audio(str(joined))
            self.assertGreater(a.size / nt.SR, 7.5)


if __name__ == "__main__":
    unittest.main()
