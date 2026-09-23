"""SECTION 7's end-to-end user-workflow test:

    Select Overscaled -> upload overscaled_sample.csv -> select/import
    voiceover -> Generate -> SceneGraph -> media resolution -> layout ->
    composition -> camera -> voiceover sync -> EditorialTimeline -> Preview
    -> existing FFmpeg -> final MP4

exercised through the ONE pure function (scene_graph.app_integration.
generate_overscaled_video) app.py's "Generate" button will call — this is
exactly what a user clicking through the real UI triggers, minus the
Tk event loop itself. Uses local-asset-type CSV rows (no network) so CI
never depends on Flow/Pexels/YouTube credentials, per Section 7's own
"use local deterministic media fixtures where network providers are
inappropriate for CI" instruction.

Also re-confirms the normal CSV workflow is completely unaffected
(Section 8).
"""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from providers.base import SceneRow
from scene_graph.app_integration import generate_overscaled_video

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None
FIXTURE = Path(__file__).resolve().parent / "overscaled_sample.csv"

_LOCAL_CSV = """scene_number,script_segment,node_id,node_type,role,asset_type,prompt,caption,highlight,camera_action,camera_target,edge_from,edge_to,edge_label
1,"The engine was a marvel of its time.",n1,image,entity,local,,,,establish,n1,,,
2,"But the cooling system could not keep up.",n2,diagram,design_flaw,local,,,,focus,n2,,,
3,"It overheated and seized within minutes.",n3,image,consequence,local,,,,focus,n3,n2,n3,caused overheating
"""


def _probe(path: Path) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    return json.loads(proc.stdout or "{}")


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestEndToEndUserWorkflow(unittest.TestCase):
    """Local-asset fixture — fast, no network, exercises the full app-facing
    entry point exactly as the (future) UI's Generate button will call it."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.csv_path = cls.tmp / "overscaled_local.csv"
        cls.csv_path.write_text(_LOCAL_CSV, encoding="utf-8")

        media_dir = cls.tmp / "work" / "media"
        media_dir.mkdir(parents=True)
        Image.new("RGB", (640, 360), (200, 40, 40)).save(media_dir / "001.png")
        Image.new("RGB", (640, 360), (40, 160, 60)).save(media_dir / "002.png")
        Image.new("RGB", (640, 360), (40, 60, 200)).save(media_dir / "003.png")

        cls.voiceover = cls.tmp / "voiceover.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=10", str(cls.voiceover)],
            check=True, capture_output=True,
        )

        cls.output_path = cls.tmp / "final.mp4"
        cls.progress_log = []
        cls.result = generate_overscaled_video(
            str(cls.csv_path), str(cls.voiceover), str(cls.output_path),
            resolution="640x360", fps=15, segment_id="engine_seg", title="The Engine",
            work_dir=str(cls.tmp / "work"),
            progress_cb=lambda msg, frac: cls.progress_log.append((msg, frac)),
        )

    def test_generation_succeeds(self):
        self.assertTrue(self.result.ok, self.result.errors)

    def test_video_exists_and_is_playable(self):
        self.assertTrue(self.output_path.is_file())
        probe = _probe(self.output_path)
        codec_types = {s["codec_type"] for s in probe["streams"]}
        self.assertIn("video", codec_types)

    def test_audio_exists(self):
        probe = _probe(self.output_path)
        codec_types = {s["codec_type"] for s in probe["streams"]}
        self.assertIn("audio", codec_types)

    def test_duration_matches_the_voiceover(self):
        probe = _probe(self.output_path)
        self.assertAlmostEqual(float(probe["format"]["duration"]), 10.0, delta=0.5)

    def test_output_resolution_matches_requested(self):
        probe = _probe(self.output_path)
        video_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
        self.assertEqual((video_stream["width"], video_stream["height"]), (640, 360))

    def test_no_unexpected_timeline_tracks(self):
        tracks = {e.track for e in self.result.timeline.events}
        self.assertEqual(tracks, {"VIDEO_1", "VOICEOVER"})

    def test_voiceover_marker_is_on_voiceover_track(self):
        vo_events = [e for e in self.result.timeline.events if e.track == "VOICEOVER"]
        self.assertEqual(len(vo_events), 1)

    def test_composed_video_is_on_video_1_track(self):
        video_events = [e for e in self.result.timeline.events if e.track == "VIDEO_1"]
        self.assertEqual(len(video_events), 1)
        self.assertTrue(Path(video_events[0].source).is_file())

    def test_camera_is_not_a_timeline_event(self):
        for e in self.result.timeline.events:
            self.assertNotEqual(e.track, "GRAPHICS")
            self.assertNotIn("camera", (e.metadata or {}))

    def test_scene_graph_and_debug_files_were_produced(self):
        self.assertIsNotNone(self.result.scene_graph)
        self.assertEqual(self.result.scene_graph.validate(), [])
        debug_dir = self.tmp / "work" / "overscaled"
        self.assertTrue((debug_dir / "overscaled_scene_graph.json").is_file())
        self.assertTrue((debug_dir / "overscaled_layout.json").is_file())

    def test_progress_callback_was_invoked(self):
        self.assertGreater(len(self.progress_log), 0)
        self.assertEqual(self.progress_log[-1][1], 1.0)


class TestNormalCsvWorkflowUnaffected(unittest.TestCase):
    """Section 8: the normal CSV contract/parser must not notice or be
    changed by anything in this feature."""

    def test_normal_scene_row_parsing_still_works(self):
        row = {"scene_number": "1", "script_segment": "hello", "asset_type": "video", "prompt": "a shot"}
        scene_row = SceneRow.from_csv_row(row)
        self.assertEqual(scene_row.asset_type, "video")
        self.assertEqual(scene_row.prompt, "a shot")

    def test_app_integration_module_does_not_import_visual_director_or_gemini(self):
        import ast

        import scene_graph.app_integration as mod

        tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)

        for banned in ("visual_director", "google.generativeai", "google"):
            self.assertFalse(
                any(m == banned or m.startswith(banned + ".") for m in imported_modules),
                f"scene_graph/app_integration.py imports {banned!r}",
            )


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestRealSampleFixtureAlsoGenerates(unittest.TestCase):
    """Same workflow, but using the actual overscaled_sample.csv fixture
    (7 nodes, 2 real causal edges, camera targets) with synthetic local
    media rather than the smaller 3-node CSV above."""

    def test_full_sample_fixture_generates_a_final_video(self):
        with open(FIXTURE, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        # Real CSV asset_types are flow_image/flow_video/stock_video — force
        # everything to "local" for a network-free CI run while preserving
        # every other column (roles, captions, edges, camera targets).
        for row in rows:
            if row.get("asset_type"):
                row["asset_type"] = "local"
                row["prompt"] = ""

        tmp = Path(tempfile.mkdtemp())
        csv_path = tmp / "overscaled_sample_local.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

        media_dir = tmp / "work" / "media"
        media_dir.mkdir(parents=True)
        for row in rows:
            if row.get("asset_type") == "local":
                Image.new("RGB", (640, 360), (80, 80, 80)).save(media_dir / f"{row['scene_number']}.png")

        voiceover = tmp / "voiceover.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=20", str(voiceover)],
            check=True, capture_output=True,
        )

        output_path = tmp / "final.mp4"
        result = generate_overscaled_video(
            str(csv_path), str(voiceover), str(output_path),
            resolution="640x360", fps=15, segment_id="aurora_bridge", title="The Aurora Bridge",
            work_dir=str(tmp / "work"),
        )
        self.assertTrue(result.ok, result.errors)
        self.assertTrue(output_path.is_file())
        probe = _probe(output_path)
        self.assertEqual({s["codec_type"] for s in probe["streams"]}, {"video", "audio"})


if __name__ == "__main__":
    unittest.main()
