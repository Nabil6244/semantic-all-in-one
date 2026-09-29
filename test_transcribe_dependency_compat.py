#!/usr/bin/env python3
"""Regression: the installed PyAV must be one faster-whisper can decode audio with.

A CI build resolved av 19.0.0, whose av.open() no longer accepts the
``metadata_errors`` keyword faster-whisper passes, so every render failed at
"Transcribing..." with a TypeError. This decodes a real file through the same
call the render pipeline makes.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from faster_whisper.audio import decode_audio
except Exception:  # pragma: no cover - dependency not installed
    decode_audio = None


@unittest.skipIf(decode_audio is None, "faster-whisper not installed")
@unittest.skipIf(shutil.which("ffmpeg") is None, "ffmpeg not available")
class TestFasterWhisperCanDecodeAudio(unittest.TestCase):
    def test_decode_audio_reads_a_real_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "tone.wav"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=d=1", str(wav)],
                check=True,
            )
            samples = decode_audio(str(wav))
        self.assertGreater(len(samples), 15000)

    def test_requirements_keep_pyav_below_19(self):
        text = (Path(__file__).parent / "requirements.txt").read_text()
        self.assertIn("av>=11,<19", text)


if __name__ == "__main__":
    unittest.main()
