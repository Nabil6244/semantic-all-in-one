"""Acceptance tests for the fixed-canvas Overscaled compositor.

Covers the requirements the camera-leg architecture violated or never
proved:
  - the canvas is fixed at the output resolution and never moves (no
    camera module, no per-leg intermediate files, one final encode)
  - an object is genuinely invisible before its appear_at and visible after
  - objects are persistent (still visible near the end of the segment)
  - a video_loop card plays REAL decoded video frames inside its card, not
    a single frozen thumbnail

Real ffmpeg/ffprobe subprocess calls, no mocking — same style as
test_overscaled_pipeline_e2e.py.
"""

from __future__ import annotations

import dataclasses
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from scene_graph.layout import compute_layout
from scene_graph.render import render_overscaled_segment
from scene_graph.schema import CaptionSpec, SceneEdge, SceneGraph, SceneNode, TitleCue
from scene_graph.style_presets import load_style_preset

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _style_without_decoration():
    """A copy of the "overscaled" style with shadow/border switched off at
    the STYLE level (scene_graph.composition reads shadow/border enablement
    from the style preset, not from SceneNode.shadow/.border) — used where a
    test needs a clean signal free of the shadow's own blur gradient."""
    style = load_style_preset("overscaled")
    nodes_cfg = dict(style.nodes or {})
    nodes_cfg["shadow"] = {"enabled": False}
    nodes_cfg["border"] = {"enabled": False}
    return dataclasses.replace(style, nodes=nodes_cfg)


def _extract_frame(video_path: Path, at: float, out_png: Path) -> Image.Image:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{at:.3f}", "-i", str(video_path),
         "-frames:v", "1", str(out_png)],
        check=True, capture_output=True,
    )
    return Image.open(out_png).convert("RGB")


def _probe_wh(video_path: Path):
    import json

    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "json", str(video_path)],
        capture_output=True, text=True,
    )
    stream = json.loads(proc.stdout or "{}")["streams"][0]
    return int(stream["width"]), int(stream["height"])


def _region_is_mostly_white(img: Image.Image, box) -> bool:
    crop = np.array(img.crop(box))
    return bool((crop > 245).all(axis=-1).mean() > 0.98)


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestNoCameraArchitecture(unittest.TestCase):
    def test_camera_module_was_removed(self):
        with self.assertRaises(ModuleNotFoundError):
            import scene_graph.camera  # noqa: F401

    def test_render_module_never_imports_camera(self):
        import scene_graph.render as render_mod

        source = Path(render_mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("resolve_camera_keyframes", source)
        self.assertNotIn("crop=", source)


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestSingleEncodeNoIntermediates(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.style = load_style_preset("overscaled")

    def test_one_output_file_and_no_leftover_leg_or_frame_files(self):
        sg = SceneGraph(
            segment_id="seg", duration=3.0,
            nodes=[SceneNode(id="n1", type="image", appear_at=0.5,
                              caption=CaptionSpec(text="hello"))],
        )
        layout = compute_layout(sg, canvas_width=640, canvas_height=360)
        out_path = self.tmp / "out.mp4"
        work_dir = self.tmp / "work"
        render_overscaled_segment(
            sg, layout, self.style, out_path=out_path, resolution="640x360", fps=10,
            work_dir=work_dir,
        )
        self.assertTrue(out_path.is_file())
        # The render's own scratch dir is cleaned up after a successful encode —
        # no leg_*.mp4 / concat.txt / _frames left behind on disk.
        self.assertFalse(work_dir.exists())

    def test_output_resolution_matches_requested_even_if_canvas_differs(self):
        sg = SceneGraph(
            segment_id="seg", duration=2.0,
            nodes=[SceneNode(id="n1", type="image", appear_at=0.0)],
        )
        layout = compute_layout(sg, canvas_width=800, canvas_height=500)
        out_path = self.tmp / "out2.mp4"
        render_overscaled_segment(
            sg, layout, self.style, out_path=out_path, resolution="640x360", fps=10,
            work_dir=self.tmp / "work2",
        )
        self.assertEqual(_probe_wh(out_path), (640, 360))


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestObjectTimelineGatingAndPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.style = load_style_preset("overscaled")
        self.canvas_w, self.canvas_h = 640, 360

    def _build(self, appear_at: float, duration: float):
        sg = SceneGraph(
            segment_id="seg", duration=duration,
            nodes=[SceneNode(id="n1", type="image", appear_at=appear_at, border=True, shadow=False)],
        )
        layout = compute_layout(sg, canvas_width=self.canvas_w, canvas_height=self.canvas_h)
        rect = layout.node_rects["n1"]
        out_path = self.tmp / "gating.mp4"
        render_overscaled_segment(
            sg, layout, self.style, out_path=out_path, resolution=f"{self.canvas_w}x{self.canvas_h}",
            fps=10, work_dir=self.tmp / "work",
        )
        return out_path, rect

    def test_node_is_not_visible_before_its_appear_at(self):
        out_path, rect = self._build(appear_at=2.0, duration=4.0)
        box = (int(rect.x) + 5, int(rect.y) + 5, int(rect.x2) - 5, int(rect.y2) - 5)
        frame = _extract_frame(out_path, 0.3, self.tmp / "before.png")
        self.assertTrue(_region_is_mostly_white(frame, box), "node rect should still be blank white before appear_at")

    def test_the_only_chapter_in_the_segment_holds_until_the_end(self):
        # A single, unrelated node has nothing to replace it, so it's the
        # (degenerate) last chapter and legitimately holds to the segment end.
        out_path, rect = self._build(appear_at=1.0, duration=4.0)
        box = (int(rect.x) + 5, int(rect.y) + 5, int(rect.x2) - 5, int(rect.y2) - 5)
        soon_after = _extract_frame(out_path, 1.6, self.tmp / "soon.png")
        near_end = _extract_frame(out_path, 3.8, self.tmp / "end.png")
        self.assertFalse(_region_is_mostly_white(soon_after, box), "node should be visible shortly after appear_at")
        self.assertFalse(_region_is_mostly_white(near_end, box), "the only chapter should still be visible near the end")


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestUnrelatedChaptersReplaceEachOther(unittest.TestCase):
    """The critical fix: an EARLIER, causally-UNRELATED node must actually
    leave the canvas once a later chapter begins — the board is a timed
    editorial composition, not a static graph overview that only grows."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.style = load_style_preset("overscaled")
        self.canvas_w, self.canvas_h = 640, 360

    def test_earlier_unrelated_node_fades_out_once_the_next_chapter_starts(self):
        # n1 and n2 are unrelated singleton chapters, so they legitimately
        # share the SAME screen slot (never simultaneous) — distinct solid
        # media colors let the test tell "n1 still showing" apart from
        # "n2 has replaced it", rather than just checking for non-white.
        red_png = self.tmp / "red.png"
        blue_png = self.tmp / "blue.png"
        Image.new("RGB", (64, 36), (220, 20, 20)).save(red_png)
        Image.new("RGB", (64, 36), (20, 20, 220)).save(blue_png)

        sg = SceneGraph(
            segment_id="seg", duration=10.0,
            nodes=[
                SceneNode(id="n1", type="image", appear_at=0.5, border=False, shadow=False,
                          caption=CaptionSpec(text="only n1 has this caption")),
                SceneNode(id="n2", type="image", appear_at=5.0, border=False, shadow=False),
            ],
        )
        layout = compute_layout(sg, canvas_width=self.canvas_w, canvas_height=self.canvas_h)
        rect = layout.node_rects["n1"]  # n2 shares the identical rect (same slot, time-disjoint)
        n1_start, n1_end = layout.active_windows["n1"]
        self.assertLess(n1_end, sg.duration, "an unrelated earlier node must not persist to the segment end")
        self.assertLessEqual(n1_end, 5.0, "n1 must be gone by the time the unrelated n2 chapter begins")

        out_path = self.tmp / "replace.mp4"
        render_overscaled_segment(
            sg, layout, _style_without_decoration(), out_path=out_path,
            resolved_media={"n1": str(red_png), "n2": str(blue_png)},
            resolution=f"{self.canvas_w}x{self.canvas_h}", fps=10, work_dir=self.tmp / "work",
        )
        box = (int(rect.x) + 5, int(rect.y) + 5, int(rect.x2) - 5, int(rect.y2) - 5)
        soon_after = np.array(_extract_frame(out_path, 1.2, self.tmp / "soon.png").crop(box))
        long_after = np.array(_extract_frame(out_path, 8.0, self.tmp / "long_after.png").crop(box))

        def _mean_color(arr):
            return arr.reshape(-1, 3).mean(axis=0)

        soon_color = _mean_color(soon_after)
        long_color = _mean_color(long_after)
        self.assertGreater(soon_color[0], soon_color[2], f"n1 (red) should be showing shortly after its appear_at: {soon_color}")
        self.assertGreater(long_color[2], long_color[0], f"n1 (red) must have been replaced by n2 (blue) by t=8s: {long_color}")

        # n2 has NO caption, so the caption band BELOW the (identical) rect
        # must be genuinely clear at t=8s too — this is the exact spot a
        # stale/frozen overlay (ffmpeg's default eof_action=repeat) would
        # keep bleeding n1's old caption text into, since n2's card doesn't
        # cover it (regression guard for that bug). Starts 6px below the
        # rect (not 2px): H.264 edge ringing at a sharp saturated-color
        # boundary bleeds a couple of near-white px right at the edge
        # regardless of any real caption content — confirmed by manual
        # pixel inspection (white fraction 0.95 at +2px vs 1.0 at +6px),
        # not a stale-frame regression.
        caption_band = (int(rect.x), int(rect.y2) + 6, int(rect.x2), int(rect.y2) + 26)
        long_after_caption = _extract_frame(out_path, 8.0, self.tmp / "long_after_caption.png").crop(caption_band)
        self.assertTrue(
            _region_is_mostly_white(long_after_caption, (0, 0, caption_band[2] - caption_band[0], caption_band[3] - caption_band[1])),
            "n1's caption must not still be bleeding through under n2's (caption-less) card",
        )

    def test_five_node_causal_chain_slides_through_at_most_max_active_slots(self):
        # A 10-node acceptance case (spec's own example) needs a genuinely
        # CONNECTED chain to exercise sliding-window eviction — 5 linked
        # nodes (n0->n1->n2->n3->n4), spaced 2s apart. Members reuse only
        # MAX_ACTIVE_PER_CHAPTER screen slots (i % template_size), and
        # eviction is designed so two members sharing a slot are NEVER
        # simultaneously active, so counting how many of the physical slot
        # rects show content at a given time IS the true simultaneous-card
        # count, without needing per-node color tagging. Frames at
        # 0/20/40/60/80/100% must differ.
        from scene_graph.layout import MAX_ACTIVE_PER_CHAPTER

        nodes = [SceneNode(id=f"n{i}", type="image", appear_at=float(i) * 2.0) for i in range(5)]
        edges = [
            SceneEdge(id=f"e{i}", from_node=f"n{i}", to_node=f"n{i + 1}", draw_at=float(i + 1) * 2.0)
            for i in range(4)
        ]
        sg = SceneGraph(segment_id="seg", duration=14.0, nodes=nodes, edges=edges)
        layout = compute_layout(sg, canvas_width=self.canvas_w, canvas_height=self.canvas_h)
        self.assertEqual(len(layout.chapters), 1, "a fully connected chain must be one chapter")

        out_path = self.tmp / "chain5.mp4"
        render_overscaled_segment(
            sg, layout, self.style, out_path=out_path, resolution=f"{self.canvas_w}x{self.canvas_h}",
            fps=10, work_dir=self.tmp / "work5",
        )

        # n0..n(template_size-1) each cover one distinct physical slot once.
        slot_rects = [layout.node_rects[f"n{i}"] for i in range(min(len(nodes), MAX_ACTIVE_PER_CHAPTER))]
        active_counts = []
        for pct in (0, 20, 40, 60, 80, 100):
            t = min(sg.duration - 0.1, sg.duration * pct / 100.0)
            frame = np.array(_extract_frame(out_path, t, self.tmp / f"f{pct}.png"))
            count = 0
            for rect in slot_rects:
                box = (int(rect.x) + 3, int(rect.y) + 3, int(rect.x2) - 3, int(rect.y2) - 3)
                crop = frame[box[1]:box[3], box[0]:box[2]]
                if crop.size and (crop < 245).any():
                    count += 1
            active_counts.append(count)

        for count in active_counts:
            self.assertLessEqual(
                count, MAX_ACTIVE_PER_CHAPTER, f"too many simultaneous cards across the segment: {active_counts}"
            )
        self.assertGreater(
            len(set(active_counts)), 1,
            f"the composition looked identical (same card count) at every sampled timestamp: {active_counts}",
        )


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestVideoCardPlaysRealMotion(unittest.TestCase):
    def test_video_loop_card_shows_changing_frames_not_a_frozen_thumbnail(self):
        tmp = Path(tempfile.mkdtemp())
        style = load_style_preset("overscaled")
        source_video = tmp / "source.mp4"
        # Three concatenated solid colors — unambiguous: any two samples a
        # second apart MUST differ, unlike a periodic test pattern that
        # could coincidentally repeat.
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-f", "lavfi", "-i", "color=red:s=320x180:d=1:r=10",
             "-f", "lavfi", "-i", "color=blue:s=320x180:d=1:r=10",
             "-f", "lavfi", "-i", "color=lime:s=320x180:d=1:r=10",
             "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[outv]", "-map", "[outv]",
             str(source_video)],
            check=True, capture_output=True,
        )

        sg = SceneGraph(
            segment_id="seg", duration=3.0,
            nodes=[SceneNode(id="n1", type="video_loop", appear_at=0.0, border=False, shadow=False)],
        )
        layout = compute_layout(sg, canvas_width=640, canvas_height=360)
        rect = layout.node_rects["n1"]
        out_path = tmp / "video_card.mp4"
        render_overscaled_segment(
            sg, layout, style, out_path=out_path, resolved_media={"n1": str(source_video)},
            resolution="640x360", fps=10, work_dir=tmp / "work",
        )

        cx, cy = int(rect.center[0]), int(rect.center[1])
        box = (cx - 20, cy - 20, cx + 20, cy + 20)
        frame_a = np.array(_extract_frame(out_path, 0.5, tmp / "a.png").crop(box))
        frame_b = np.array(_extract_frame(out_path, 2.5, tmp / "b.png").crop(box))
        self.assertFalse(np.array_equal(frame_a, frame_b), "video card should play real motion, not a static frame")


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestPersistentChapterTitle(unittest.TestCase):
    """Reference-verified: a subject's bold title persists independent of
    any image node, and disappears (hard cut) when the next title begins."""

    def test_title_text_renders_during_its_window_and_hard_cuts_at_the_end(self):
        tmp = Path(tempfile.mkdtemp())
        style = load_style_preset("overscaled")
        sg = SceneGraph(
            segment_id="seg", duration=8.0,
            title_cues=[TitleCue(text="Vasa", at=0.0), TitleCue(text="HMS Captain", at=4.0)],
        )
        layout = compute_layout(sg, canvas_width=640, canvas_height=360)
        self.assertEqual(len(layout.title_windows), 2)

        out_path = tmp / "titles.mp4"
        render_overscaled_segment(
            sg, layout, style, out_path=out_path, resolution="640x360", fps=10, work_dir=tmp / "work",
        )
        title_band = (0, 30, 640, 110)  # near the top, where MARGIN_PX places the title baseline

        during_first = np.array(_extract_frame(out_path, 1.0, tmp / "t1.png").crop(title_band))
        during_second = np.array(_extract_frame(out_path, 5.0, tmp / "t2.png").crop(title_band))
        self.assertTrue((during_first < 245).any(), "title text should be visible during its own window")
        self.assertTrue((during_second < 245).any(), "second title should be visible during its own window")
        # Different text -> different ink pattern, not just "something is there".
        self.assertFalse(np.array_equal(during_first, during_second), "two different titles produced identical pixels")


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestHardCutRemovalNotFadeOut(unittest.TestCase):
    """Reference-verified: an element that's no longer needed disappears
    instantly (hard cut) rather than fading out — no lingering soft tail."""

    def test_node_disappears_abruptly_at_window_end_not_gradually(self):
        tmp = Path(tempfile.mkdtemp())
        style = _style_without_decoration()
        sg = SceneGraph(
            segment_id="seg", duration=6.0,
            nodes=[
                SceneNode(id="n1", type="image", appear_at=0.5),
                SceneNode(id="n2", type="image", appear_at=3.0),
            ],
        )
        layout = compute_layout(sg, canvas_width=640, canvas_height=360)
        rect = layout.node_rects["n1"]
        n1_end = layout.active_windows["n1"][1]

        red_png = tmp / "red.png"
        Image.new("RGB", (64, 36), (220, 20, 20)).save(red_png)
        out_path = tmp / "hardcut.mp4"
        render_overscaled_segment(
            sg, layout, style, out_path=out_path, resolved_media={"n1": str(red_png)},
            resolution="640x360", fps=10, work_dir=tmp / "work",
        )

        box = (int(rect.x) + 5, int(rect.y) + 5, int(rect.x2) - 5, int(rect.y2) - 5)
        just_before = np.array(_extract_frame(out_path, n1_end - 0.15, tmp / "before.png").crop(box)).reshape(-1, 3).mean(axis=0)
        just_after = np.array(_extract_frame(out_path, n1_end + 0.05, tmp / "after.png").crop(box)).reshape(-1, 3).mean(axis=0)
        # n1 (red) fully opaque just before its window ends: red channel
        # clearly dominant over green/blue.
        before_dominance = just_before[0] - (just_before[1] + just_before[2]) / 2.0
        self.assertGreater(before_dominance, 40, f"n1 (red) should still be fully visible just before its window ends: {just_before}")
        # A FADE would still show red > green/blue, just fainter (blending
        # toward white). A HARD CUT shows red's dominance vanish almost
        # immediately — whatever (if anything) replaces n1 is neutral-toned
        # (background white or a colorless placeholder), not "faded pink".
        after_dominance = just_after[0] - (just_after[1] + just_after[2]) / 2.0
        self.assertLess(after_dominance, 10, f"n1's red tint should be gone almost immediately, not fading out: {just_after}")


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestEdgeLabelRenders(unittest.TestCase):
    """Reference-verified: arrows carry an inline text label (e.g. "In 1628")
    near their midpoint once fully drawn — scene_graph/overscaled_csv.py's
    edge_label column already fed this into edge.metadata, but nothing
    rendered it until now."""

    def test_labeled_edge_has_more_ink_near_its_midpoint_than_an_unlabeled_one(self):
        style = load_style_preset("overscaled")
        from_rect_kwargs = dict(x=100, y=100, width=200, height=150)
        to_rect_kwargs = dict(x=500, y=400, width=200, height=150)
        from scene_graph.composition import render_edge_reveal_frame
        from scene_graph.layout import NodeRect

        from_rect = NodeRect(node_id="a", **from_rect_kwargs)
        to_rect = NodeRect(node_id="b", **to_rect_kwargs)

        unlabeled = SceneEdge(id="e1", from_node="a", to_node="b", draw_at=0.0, duration=0.8)
        labeled = SceneEdge(id="e2", from_node="a", to_node="b", draw_at=0.0, duration=0.8,
                             metadata={"label": "In 1628"})

        frame_unlabeled = render_edge_reveal_frame(unlabeled, from_rect, to_rect, style, canvas_size=(800, 600), progress=1.0)
        frame_labeled = render_edge_reveal_frame(labeled, from_rect, to_rect, style, canvas_size=(800, 600), progress=1.0)

        alpha_unlabeled = int(np.array(frame_unlabeled.split()[-1]).astype(int).sum())
        alpha_labeled = int(np.array(frame_labeled.split()[-1]).astype(int).sum())
        self.assertGreater(alpha_labeled, alpha_unlabeled, "labeled arrow frame should have strictly more visible ink")


if __name__ == "__main__":
    unittest.main()
