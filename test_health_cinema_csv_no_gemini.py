"""A scenes CSV directs Health Cinema: no Gemini call anywhere in the run (planning, footage retries, frame checks), even with a key set."""
from __future__ import annotations
import shutil, subprocess, tempfile, unittest
from pathlib import Path
from unittest import mock

from health_cinema import assets, engine, relevance
from visual_qa import semantic

HAVE_FFMPEG = bool(assets.ffmpeg_path())
ROWS = [{"text": "Your heart beats about seventy times a minute.", "start": 0.0, "end": 4.0, "visual": "footage", "footage": "heart beating monitor"},
        {"text": "Every beat pushes blood through narrow tubes.", "start": 4.0, "end": 8.0, "visual": "footage", "footage": "blood vessels animation"}]


class _Boom:
    def __init__(self, *a, **k): raise AssertionError("Gemini was called on a CSV-directed run")


class CsvDirects(unittest.TestCase):
    def test_detects_directed_rows(self):
        self.assertTrue(engine.csv_directs(ROWS))
        self.assertFalse(engine.csv_directs([{"text": "Plain sentence.", "start": 0, "end": 2}]))

    def test_vision_check_is_skipped_when_gemini_is_off(self):
        with mock.patch("visual_director.llm.resolve_gemini_api_key", side_effect=AssertionError("key read")):
            self.assertEqual(semantic.vision_semantic_score(object(), ["f.jpg"], settings={"gemini_enabled": False}), (None, []))

    def test_relevance_frame_check_is_skipped_when_gemini_is_off(self):
        rec = {"ok": True, "path": "x.mp4", "source_url": "", "qa": {}}
        with mock.patch.object(relevance, "title_verdict", return_value="unknown"), mock.patch.object(relevance, "_frames", side_effect=AssertionError("frames read")):
            self.assertIs(relevance.check(rec, "the heart", "heart", "heart", {"gemini_enabled": False}), rec)


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not available")
class CsvRunMakesNoGeminiCall(unittest.TestCase):
    def test_failed_footage_retries_without_gemini(self):
        d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        wav = d / "v.wav"; subprocess.run([assets.ffmpeg_path(), "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "8", str(wav)], check=True)
        logs = []
        with mock.patch("visual_director.llm.GeminiLLM", _Boom), mock.patch("visual_director.llm.gemini_configured", return_value=True):
            engine.run_health_cinema(d, [dict(r) for r in ROWS], str(wav), str(d / "o.mp4"), quality="preview", settings={"gemini_api_key": "test"}, log=logs.append,
                                     acquirer=lambda rows: {int(x.scene_number): {"ok": False, "path": "", "error": "no results"} for x in rows})
        text = "\n".join(logs)
        self.assertIn("Gemini is not used for this run", text)
        self.assertNotIn("Gemini was unavailable", text)


if __name__ == "__main__":
    unittest.main()
