"""After a checked Explainer export only the plan, the fetched pictures and the video stay (explainer/cleanup.py)."""

import tempfile
import unittest
from pathlib import Path

from explainer.cleanup import after_export


class Cleanup(unittest.TestCase):
    def test_working_files_go_plan_pictures_and_video_stay(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d) / "hybrid" / "_work"
            ex = Path(d) / "hybrid" / "explainer"
            (work / ".pakmap_segments").mkdir(parents=True)
            (work / "flow").mkdir()
            ex.mkdir()
            gone = [ex / "board_a.mp4", ex / "board_b.mov", ex / "baked_c.mp4", ex / "still_d.mp4", ex / "e1_overlay.mov", ex / "map_narrator_serious.mov",
                    ex / "explainer_audio.wav", work / "pakmap_map.mp4", work / "pakmap_audio.wav", work / ".pakmap_segments" / "x.mp4"]
            kept = [ex / "render_report.json", ex / "pending_boards.pkl", ex / "baked_boards.json", work / "flow" / "001.png", work / "pakmap_spec.json",
                    Path(d) / "final" / "video.mp4"]
            for f in gone + kept:
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(b"x" * 10)
            self.assertEqual(after_export(work), 100)
            self.assertEqual([f for f in gone if f.exists()], [])
            self.assertEqual([f for f in kept if not f.exists()], [])

    def test_not_an_explainer_project_is_left_alone(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d) / "_work"
            work.mkdir()
            (work / "pakmap_map.mp4").write_bytes(b"x")
            self.assertEqual(after_export(work), 0)
            self.assertTrue((work / "pakmap_map.mp4").exists())


if __name__ == "__main__":
    unittest.main()
