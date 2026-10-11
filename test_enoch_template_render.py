"""Enoch Template, Phases 7 and 8: the style's plan through the REAL renderer (video_generator.render_video -> ffmpeg),
then its opt-in audio finishing and QC, measured on the actual output. Local only: synthetic narration and pictures
stand in for cached assets, and NoPaidCalls guards every step."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import video_generator as vg
from ancient_texts import audio as A
from ancient_texts import integration
from ancient_texts.plan import refine_plan
from ancient_texts.qc import evaluate, measure_render
from ancient_texts.subjects import load_pack
from enoch_template_testutil import NoPaidCalls
from project_workspace import ProjectWorkspace
from style_engine.loader import load_style
from test_enoch_template_plan import MIXED, plan_from

FFMPEG = shutil.which("ffmpeg") is not None


def _project(root: Path, style_id=None) -> ProjectWorkspace:
    ws = ProjectWorkspace(project_id="p1", title="Test", seq=1, root=root / "proj")
    for d in ("assets", "state", "final", "audio"):
        (ws.root / d).mkdir(parents=True, exist_ok=True)
    ws.set_video_style_settings(mode="manual" if style_id else "", style_id=style_id)
    return ws


@unittest.skipUnless(FFMPEG, "ffmpeg not on PATH")
class RenderAndFinish(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.ws = _project(cls.tmp, "enoch_template")
        cls.images = cls.ws.assets_dir
        cls.plan = plan_from(MIXED[:6])
        with NoPaidCalls() as guard:
            cls.result = refine_plan(cls.plan, style=load_style("enoch_template"), pack=load_pack("enoch"), images_dir=cls.images,
                                     card_requests={3: {"kind": "section_break", "fields": {"title": "The flood"}}})
        guard.assert_clean()
        # stand-ins for the cached pictures of every non-card scene (the providers are never called)
        for sc in cls.plan.scenes:
            p = cls.images / f"{sc.scene_id:03d}.png"
            if not p.exists():
                Image.new("RGB", (1280, 720), (60 + 20 * sc.scene_id, 50, 40)).save(p)
        cls.audio = cls.tmp / "narration.wav"     # deliberately hot: forces the finishing pass to work
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=180:d=12", "-f", "lavfi", "-i", "anoisesrc=d=12:a=0.2",
                        "-filter_complex", "[0][1]amix=inputs=2:normalize=0,volume=2.2", str(cls.audio)], check=True)
        cls.rows = [{"scene_number": str(sc.scene_id), "start_time": 2.0 * i, "script_segment": sc.narration}
                    for i, sc in enumerate(cls.plan.scenes)]
        cls.out = cls.ws.final_dir / "final.mp4"
        cwd = os.getcwd()
        os.chdir(cls.tmp)
        try:
            with NoPaidCalls() as guard:
                vg.render_video(cls.rows, 12.0, cls.images, str(cls.audio), str(cls.out), "640x360", 30, zoom=True,
                                visual_transitions=False)
            guard.assert_clean()
        finally:
            os.chdir(cwd)
        cls.before_md5 = A.video_stream_md5(cls.out)
        cls.before_loud = A.measure(cls.out)
        with NoPaidCalls() as guard:
            cls.report = integration.finish_render(cls.out, cls.ws)
        guard.assert_clean()

    def test_render_is_valid_and_complete(self):
        self.assertTrue(self.out.is_file())
        dur = A._stream_duration(self.out, "v")
        self.assertAlmostEqual(dur, 12.0, delta=0.5)

    def test_card_scene_shows_the_card_at_its_time(self):
        frame = self.tmp / "frame.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "5.0", "-i", str(self.out), "-frames:v", "1", str(frame)], check=True)
        with Image.open(frame) as im, Image.open(self.images / "003.png") as card:
            a = im.convert("L").resize((64, 36)).getdata()
            b = card.convert("L").resize((64, 36)).getdata()
            diff = sum(abs(x - y) for x, y in zip(a, b)) / len(a)
        self.assertLess(diff, 30, "scene 3 (2-4 s window plus Ken Burns) shows its section card")

    def test_audio_finished_and_measured_on_the_output(self):
        fin = self.report["audio_finishing"]
        self.assertEqual(fin["status"], "finished")
        after = A.measure(self.out)
        self.assertLessEqual(after.true_peak_dbtp, -1.0)
        self.assertLessEqual(abs(after.integrated_lufs - (-16.0)), 1.5)
        self.assertGreater(self.before_loud.integrated_lufs, -14.5, "the input really was outside the target")

    def test_video_stream_and_sync_are_preserved(self):
        self.assertEqual(A.video_stream_md5(self.out), self.before_md5)
        self.assertLessEqual(abs(A._stream_duration(self.out, "a") - A._stream_duration(self.out, "v")), 0.15)

    def test_qc_report_has_three_lists_and_no_equivalence_claim(self):
        rep = json.loads((integration.state_dir(self.ws) / "qc_report.json").read_text(encoding="utf-8"))
        for key in ("hard_failures", "soft_deviations", "review_items"):
            self.assertIn(key, rep)
        self.assertIn("not a judgement that the video is equivalent", rep["verdict"])
        self.assertEqual([i for i in rep["hard_failures"] if i["code"] in ("target_true_peak_dbtp", "audio_finishing_failed")], [])
        self.assertTrue(any(i["code"] == "visuals_match" for i in rep["review_items"]))

    def test_plan_scenes_are_ordered_and_complete(self):
        self.assertEqual([m.scene for m in self.result.scenes], [1, 2, 3, 4, 5, 6])
        self.assertEqual(self.result.scenes[2].reason, "sections")


@unittest.skipUnless(FFMPEG, "ffmpeg not on PATH")
class Isolation(unittest.TestCase):
    def test_other_styles_are_never_finished_or_refined(self):
        tmp = Path(tempfile.mkdtemp())
        for style in (None, "book_of_enoch", "premium_documentary"):
            ws = _project(tmp / str(style), style)
            f = tmp / f"{style}.mp4"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:d=2", "-f", "lavfi", "-i",
                            "sine=d=2,volume=3", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(f)], check=True)
            before = f.read_bytes()
            self.assertIsNone(integration.finish_render(f, ws))
            self.assertEqual(f.read_bytes(), before, f"{style}: file untouched")
            plan = plan_from(MIXED[:4])
            snapshot = [(s.asset_type, list(s.search_queries)) for s in plan.scenes]
            self.assertIsNone(integration.refine(plan, ws, script="x", images_dir=ws.assets_dir))
            self.assertEqual([(s.asset_type, list(s.search_queries)) for s in plan.scenes], snapshot)
            self.assertFalse((ws.state_dir / "enoch_template").exists())

    def test_a_failed_refine_leaves_the_plan_as_it_was(self):
        ws = _project(Path(tempfile.mkdtemp()), "enoch_template")
        plan = plan_from(MIXED[:4])
        before = [(s.asset_type, list(s.search_queries)) for s in plan.scenes]
        import ancient_texts.plan as P

        real = P._restore_csv_sources

        def boom(p, rows):
            real(p, rows)
            raise RuntimeError("simulated failure mid-pass")

        with mock.patch.object(P, "_restore_csv_sources", boom):
            with self.assertRaises(RuntimeError):
                integration.refine(plan, ws, script="x", csv_rows=[{"scene_number": "1", "asset_type": "stock_image",
                                                                    "prompt": "Ethiopic manuscript"}])
        self.assertEqual([(s.asset_type, list(s.search_queries)) for s in plan.scenes], before)

    def test_smart_editing_override_only_for_this_style(self):
        from smart_editing import SmartEditingSettings

        base = SmartEditingSettings()
        s = integration.smart_editing_settings(base)
        self.assertEqual((s.intensity, s.sound_effects_intensity, s.visual_transitions_intensity, s.scene_ambience),
                         ("low", "low", "low", False))
        self.assertEqual(SmartEditingSettings(), base, "the base settings object is not modified")


@unittest.skipUnless(FFMPEG, "ffmpeg not on PATH")
class AudioEdgeCases(unittest.TestCase):
    def test_no_audio_is_left_untouched(self):
        f = Path(tempfile.mkdtemp()) / "silent.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:d=2", "-c:v", "libx264", str(f)], check=True)
        before = f.read_bytes()
        r = A.finish(f)
        self.assertEqual(r.status, "no_audio")
        self.assertEqual(f.read_bytes(), before)

    def test_already_within_target_is_left_untouched(self):
        f = Path(tempfile.mkdtemp()) / "ok.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:d=6", "-f", "lavfi", "-i",
                        "anoisesrc=d=6:a=0.1", "-af", "loudnorm=I=-16:TP=-2", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(f)],
                       check=True)
        if not (A.measure(f).within_target() and A.measure(f).peak_ok()):
            self.skipTest("fixture did not land inside the target on this ffmpeg build")
        before = f.read_bytes()
        self.assertEqual(A.finish(f).status, "finished")
        self.assertEqual(f.read_bytes(), before)

    def test_missing_ffmpeg_gives_a_clear_diagnostic(self):
        f = Path(tempfile.mkdtemp()) / "x.mp4"
        f.write_bytes(b"")
        with mock.patch.object(A.shutil, "which", return_value=None), mock.patch.object(Path, "is_file", return_value=False):
            r = A.finish(f)
        self.assertEqual(r.status, "failed")
        self.assertIn("ffmpeg was not found", r.message)

    def test_missing_filter_gives_a_clear_diagnostic(self):
        with mock.patch.object(A, "_run", return_value=subprocess.CompletedProcess([], 0, stdout=" ... volume  A->A ...", stderr="")):
            with self.assertRaises(A.AudioToolError) as ctx:
                A.check_filters("ffmpeg")
        self.assertIn("ebur128", str(ctx.exception))


class MissingAssets(unittest.TestCase):
    def test_a_card_scene_without_its_file_fails_actionably(self):
        from providers.base import SceneRow
        from providers.router import SceneAssetRouter

        d = Path(tempfile.mkdtemp())
        scene = SceneRow.from_csv_row({"scene_number": "7", "script_segment": "x", "asset_type": "local", "prompt": "statement card"})
        errors = SceneAssetRouter.validate([scene], d)
        self.assertEqual(len(errors), 1)
        self.assertIn("007", errors[0])
        Image.new("RGB", (64, 36)).save(d / "007.png")
        self.assertEqual(SceneAssetRouter.validate([scene], d), [], "with its card in place the scene resolves")

    def test_card_scenes_resolve_to_their_file_not_a_stock_search(self):
        from providers.router import SceneAssetRouter

        plan = plan_from(MIXED[:3])
        with tempfile.TemporaryDirectory() as d:
            refine_plan(plan, style=load_style("enoch_template"), pack=load_pack("enoch"), images_dir=Path(d),
                        card_requests={2: {"kind": "section_break", "fields": {"title": "A title"}}})
            csv_path = Path(d) / "plan.csv"
            plan.write_csv(csv_path)
            import csv as _csv

            rows = list(_csv.DictReader(open(csv_path, encoding="utf-8")))
        lossy = plan.to_scene_rows()
        self.assertEqual(SceneAssetRouter.classify(lossy[1]).value, "stock_video", "the shared conversion has no local branch")
        fixed = integration.csv_local_rows_win(lossy, rows)
        self.assertIsNone(SceneAssetRouter.classify(fixed[1]), "the card scene resolves to its own numbered file")
        self.assertEqual([r.scene_number for r in fixed], [r.scene_number for r in lossy])
        self.assertIs(fixed[0], lossy[0], "other scenes are untouched")

    def test_no_overlay_is_drawn_over_a_card(self):
        tmp = Path(tempfile.mkdtemp())
        ws = _project(tmp, "enoch_template")
        d = integration.state_dir(ws)
        d.mkdir(parents=True)
        (d / "plan_report.json").write_text(json.dumps({"scenes": [{"scene": 6, "card": {"installed": True}},
                                                                   {"scene": 7, "card": None}]}), encoding="utf-8")
        tl = {"tracks": [], "events": [{"scene_number": "6", "metadata": {"graphic": True}}, {"scene_number": "6", "metadata": {}},
                                       {"scene_number": "7", "metadata": {"graphic": True}}]}
        out = integration.drop_graphics_on_cards(tl, ws)
        self.assertEqual(out["events"], tl["events"][1:], "only the graphic over the card goes; the scene's own event stays")
        self.assertEqual(integration.drop_graphics_on_cards(tl, _project(tmp / "n", None)), tl, "no report: unchanged")

    def test_qc_flags_timeline_problems_as_hard(self):
        rep = evaluate(render={"shots": [4.0, 5.0], "loudness": {"integrated_lufs": -16.0, "true_peak_dbtp": -0.2,
                                                                  "loudness_range_lu": 4}, "av_duration_delta_s": 0.4},
                       profile_id="enoch_ref_01")
        hard = {i["code"] for i in rep["hard_failures"]}
        self.assertIn("target_true_peak_dbtp", hard)
        self.assertIn("target_av_duration_delta_s", hard)

    def test_measure_render_on_a_real_file(self):
        if not FFMPEG:
            self.skipTest("ffmpeg not on PATH")
        f = Path(tempfile.mkdtemp()) / "m.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:d=3", "-f", "lavfi", "-i",
                        "color=c=red:s=320x180:d=3", "-f", "lavfi", "-i", "sine=d=6", "-filter_complex", "[0][1]concat=n=2:v=1[v]",
                        "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(f)], check=True)
        m = measure_render(f)
        self.assertGreaterEqual(len(m["shots"]), 2)
        self.assertIsNotNone(m["loudness"])


if __name__ == "__main__":
    unittest.main()
