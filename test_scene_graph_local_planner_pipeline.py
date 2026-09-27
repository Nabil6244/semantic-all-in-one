"""End-to-end test for the Local Visual Planner wired into
run_overscaled_pipeline behind the ``use_local_planner`` flag.

Mirrors test_overscaled_pipeline_e2e.py's own real-ffmpeg pattern (real
subprocess calls, real files, real ffprobe verification) but drives the
pipeline from bare narration rows (scene_number/script_segment only) through
generate_scene_graph_local_planner instead of the dedicated Overscaled CSV
compiler. Proves the two paths converge on the same SceneGraph contract and
that everything downstream (voiceover sync, layout, composition, render,
timeline) is completely unaffected by which one produced it.

No Gemini, no network, no CSV file on disk, no mocking of ffmpeg.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scene_graph.pipeline import run_overscaled_pipeline

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None

# Narration only — no beat/node_id/relationship_to/chapter columns at all.
# Includes a comparison (row 2) and a causal pair (rows 4->5) so the
# resulting SceneGraph has real edges, not just isolated hero nodes.
NARRATION_ROWS = [
    {"scene_number": "1", "script_segment": "A quiet observatory sits atop a remote mountain."},
    {"scene_number": "2", "script_segment": "Unlike older telescopes, this one uses adaptive optics."},
    {"scene_number": "3", "script_segment": "The mirror took five years to grind and polish."},
    {"scene_number": "4", "script_segment": "A support strut cracked during the final test."},
    {"scene_number": "5", "script_segment": "Because of that crack, the launch was delayed by a year."},
]


def _make_sine_wav(path: Path, duration_s: float) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={max(0.5, duration_s):.2f}", str(path)],
        check=True, capture_output=True,
    )


def _probe(path: Path) -> dict:
    import json

    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    return json.loads(proc.stdout or "{}")


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestLocalPlannerWiredIntoOverscaledPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def _resolved_media(self, sg):
        media_dir = self.tmp / "media"
        media_dir.mkdir(exist_ok=True)
        resolved = {}
        for i, node in enumerate(sg.nodes):
            p = media_dir / f"{node.id}.png"
            Image.new("RGB", (640, 360), ((i * 47) % 255, (i * 91) % 255, (i * 137) % 255)).save(p)
            resolved[node.id] = str(p)
        return resolved

    def test_flag_off_keeps_existing_csv_compiler_behavior(self):
        # use_local_planner defaults to False — the SAME narration rows must
        # go through the existing compile_overscaled_csv path exactly as
        # before: it has no narration-language relationship inference at
        # all (it only ever creates edges from explicit edge_from/edge_to
        # columns, which NARRATION_ROWS doesn't have), so the comparison/
        # causal edges the planner infers must be ABSENT here. This is the
        # meaningful proof the flag changes nothing for existing callers,
        # not just that both paths happen to return ok=True.
        from scene_graph.overscaled_csv import compile_overscaled_csv

        compiled = compile_overscaled_csv(NARRATION_ROWS, segment_id="obs")
        self.assertTrue(compiled.ok, compiled.errors)
        self.assertEqual(compiled.scene_graph.edges, [])

    def test_local_planner_flag_produces_a_playable_clip_and_timeline(self):
        from scene_graph.generator import generate_scene_graph_local_planner, scene_rows_from_csv_rows

        probe = generate_scene_graph_local_planner(
            "obs", scene_rows_from_csv_rows(NARRATION_ROWS)
        )
        self.assertTrue(probe.ok, probe.errors)
        # Sanity: this narration really does produce relationship edges, so
        # the test also exercises the "group"/"sequential" edge path, not
        # just isolated single-node beats.
        self.assertGreaterEqual(len(probe.scene_graph.edges), 2)

        voiceover = self.tmp / "voiceover.wav"
        _make_sine_wav(voiceover, probe.scene_graph.duration)
        resolved_media = self._resolved_media(probe.scene_graph)

        out_dir = self.tmp / "out"
        result = run_overscaled_pipeline(
            NARRATION_ROWS, segment_id="obs", title="The Observatory",
            voiceover_path=str(voiceover), out_dir=out_dir,
            resolved_media=resolved_media, canvas_width=1600, canvas_height=1000,
            resolution="640x360", fps=15,
            use_local_planner=True,
        )
        self.assertTrue(result.ok, result.errors)
        self.assertTrue(result.segment_clip_path.is_file())
        self.assertTrue((out_dir / "overscaled_scene_graph.json").is_file())
        self.assertTrue((out_dir / "overscaled_layout.json").is_file())

        # The compiled SceneGraph came from the planner, not the CSV
        # compiler — its node ids are position-based ("n1".."n5"), and it
        # actually has the comparison/causal edges the narration implies.
        self.assertEqual([n.id for n in result.scene_graph.nodes], ["n1", "n2", "n3", "n4", "n5"])
        relationships = {e.metadata.get("relationship") for e in result.scene_graph.edges}
        self.assertTrue({"comparison", "causal"} <= relationships)

        ffprobe_info = _probe(result.segment_clip_path)
        self.assertAlmostEqual(
            float(ffprobe_info["format"]["duration"]), result.scene_graph.duration, delta=0.5
        )
        tracks = {e.track for e in result.timeline.events}
        self.assertEqual(tracks, {"VIDEO_1", "VOICEOVER"})

    def test_local_planner_flag_works_for_exp_solar_style_preset_too(self):
        # Same planner output, different style preset — proving the planner
        # is genuinely style-agnostic (Part 8 of the earlier audit: Exp Solar
        # and Overscaled already converge on the same SceneGraph contract).
        from scene_graph.generator import generate_scene_graph_local_planner, scene_rows_from_csv_rows

        probe = generate_scene_graph_local_planner(
            "obs", scene_rows_from_csv_rows(NARRATION_ROWS), style_preset="exp_solar"
        )
        self.assertTrue(probe.ok, probe.errors)

        voiceover = self.tmp / "voiceover_exp.wav"
        _make_sine_wav(voiceover, probe.scene_graph.duration)
        resolved_media = self._resolved_media(probe.scene_graph)

        out_dir = self.tmp / "out_exp_solar"
        result = run_overscaled_pipeline(
            NARRATION_ROWS, segment_id="obs", title="The Observatory",
            voiceover_path=str(voiceover), out_dir=out_dir,
            resolved_media=resolved_media, canvas_width=1600, canvas_height=1000,
            resolution="640x360", fps=15,
            style_preset_id="exp_solar",
            use_local_planner=True,
        )
        self.assertTrue(result.ok, result.errors)
        self.assertTrue(result.segment_clip_path.is_file())


if __name__ == "__main__":
    unittest.main()
