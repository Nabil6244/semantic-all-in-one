"""War outside the app uses the app's download settings (2026-11-09: a script with transcript matching off cut every clip from the blind
middle of its video), and a clip repeated across scenes is found."""
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from cinematic_explainer.war import app_section as A, headless as H

ROOT = Path(__file__).resolve().parent


class SameSettingsAsApp(unittest.TestCase):
    def test_defaults_match_app_py(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        for key, val in H.YOUTUBE_DEFAULTS.items():
            m = re.search(r'self\._settings\.get\(\s*"' + key + r'"\s*,\s*([^)]+)\)', src)
            self.assertIsNotNone(m, key)
            self.assertEqual(str(m.group(1)).strip(), repr(val) if not isinstance(val, bool) else str(val), key)

    def test_transcript_matching_on_by_default(self):
        self.assertEqual(H.youtube_options({}), (3.5, 5, True))
        self.assertFalse(H.youtube_options({"youtube_transcript_matching": False})[2])

    def test_built_downloader_matches_on_transcripts(self):
        with tempfile.TemporaryDirectory() as d:
            mgr = H.build_manager(Path(d), settings={}, log=lambda m: None)
            yt = getattr(mgr, "youtube_provider", None)
            if yt is None:
                self.skipTest("yt-dlp not installed")
            self.assertTrue(yt.transcript_matching)


class Repeats(unittest.TestCase):
    def _manifest(self, d, recs):
        from asset_manager import AssetManifest

        m = AssetManifest(Path(d))
        for no, rec in recs.items():
            m.set(no, {"status": "complete", "local_path": str(Path(d, f"{int(no):03d}.mp4")), **rec})

    def test_same_moment_of_same_video_is_a_repeat(self):
        with tempfile.TemporaryDirectory() as d:
            self._manifest(d, {"5": {"video_id": "X", "clip_start": 13.5, "timestamp_end": 21.5},
                               "10": {"video_id": "X", "clip_start": 13.5, "timestamp_end": 21.5},
                               "14": {"video_id": "X", "clip_start": 60.0, "timestamp_end": 68.0},       # another moment: fine
                               "20": {"video_id": "X", "clip_start": 14.0, "timestamp_end": 22.0},
                               "3": {"video_id": "Y", "clip_start": 13.5, "timestamp_end": 21.5},
                               "8": {"video_id": "X", "clip_start": 13.5, "timestamp_end": 21.5, "user_override": True}})
            rows = [SimpleNamespace(scene_number=n) for n in (3, 5, 8, 10, 14, 20)]
            self.assertEqual(A.repeated_clips(Path(d), rows), ["10", "20"])

    def test_fix_repeats_asks_for_an_alternative(self):
        with tempfile.TemporaryDirectory() as d:
            self._manifest(d, {"1": {"video_id": "X", "clip_start": 0, "timestamp_end": 8}, "2": {"video_id": "X", "clip_start": 0, "timestamp_end": 8}})
            asked = []

            class M:
                def alternative_scene(self, row):
                    asked.append(row.scene_number)
                    from asset_manager import AssetManifest

                    AssetManifest(Path(d)).set("2", {"status": "complete", "video_id": "Z", "clip_start": 0, "timestamp_end": 8, "user_override": True})

            rows = [SimpleNamespace(scene_number=1), SimpleNamespace(scene_number=2)]
            A.fix_repeats(Path(d), rows, M())
            self.assertEqual(asked, [2])
            from asset_manager import AssetManifest

            self.assertFalse(AssetManifest(Path(d)).get("2").get("user_override"))     # still the CSV's own search, not the user's pick


if __name__ == "__main__":
    unittest.main()
