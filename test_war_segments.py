"""War Documentary segmented renderer and entry point: frame-exact pieces, cache keys, cancel/failure cleanup, audio length, isolation."""
import json
import shutil
import subprocess
import tempfile
import unittest

from war_test_media import clip
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from cinematic_explainer import look as L
from cinematic_explainer.render import Layer, Shot
from cinematic_explainer.war import integration, segments as S

ROOT = Path(__file__).resolve().parent
A = clip("008.mp4")   # Images/ when present, else a generated stand-in (Images/ is not in git)
B = clip("013.mp4")
HAVE_FFMPEG = bool(shutil.which("ffmpeg"))


def _probe(path, entry="duration"):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", f"format={entry}", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return float(r.stdout.strip())


class PlanTests(unittest.TestCase):
    def test_boundaries_are_whole_frames_and_contiguous(self):
        shots = [Shot(A, 0.0, 4.61), Shot(B, 4.61, 9.0, seek=1.0)]
        ps = S.plan_pieces(shots, [])
        self.assertEqual(ps[0].f0, 0)
        for a, b in zip(ps, ps[1:]):
            self.assertEqual(a.f1, b.f0)
        self.assertEqual(ps[-1].f1, 225)

    def test_long_shot_splits_without_cutting_a_card_or_dim_ramp(self):
        layers = [Layer("number", 9.0, 14.0, {"value": 5}, dim=True)]
        ps = S.plan_pieces([Shot(A, 0.0, 30.0)], layers)
        self.assertGreater(len(ps), 1)
        for p in ps[:-1]:
            t = p.f1 / L.FPS
            self.assertFalse(9.0 - L.DIM_IN_S < t < 14.0 + L.DIM_IN_S, t)
        self.assertEqual(ps[-1].f1, 750)
        self.assertAlmostEqual(ps[1].seek, ps[0].frames / L.FPS, places=3)

    def test_graph_has_colour_fix_and_pixel_format_fix(self):
        p = S.Piece(0, A, 0, 125, 0.0)
        no_dim = S.piece_graph(p, [])
        self.assertIn("setparams=colorspace=bt709", no_dim)
        self.assertIn("format=yuva420p", no_dim)
        with_dim = S.piece_graph(p, [(1.0, 3.0)])
        self.assertEqual(with_dim.count("overlay=enable"), 1)
        self.assertNotIn("split", with_dim)             # the dim plate is a second decode, never a split (that was the memory growth)


class KeyTests(unittest.TestCase):
    def setUp(self):
        self.p = S.Piece(0, A, 0, 125, 0.0)
        self.consts = "x"

    def key(self, layers, spans=()):
        return S.segment_key(self.p, layers, list(spans), "x264", self.consts)

    def test_same_inputs_same_key_any_dict_order(self):
        a = [Layer("number", 1.0, 4.0, {"value": 5, "label": "x"})]
        b = [Layer("number", 1.0, 4.0, {"label": "x", "value": 5})]
        self.assertEqual(self.key(a), self.key(b))

    def test_changed_card_or_timing_changes_key(self):
        base = self.key([Layer("number", 1.0, 4.0, {"value": 5})])
        self.assertNotEqual(base, self.key([Layer("number", 1.0, 4.0, {"value": 6})]))
        self.assertNotEqual(base, self.key([Layer("number", 1.04, 4.0, {"value": 5})]))
        self.assertEqual(base, self.key([Layer("number", 1.0, 4.0, {"value": 5}), Layer("number", 50.0, 52.0, {"value": 9})]))   # outside the piece

    def test_image_and_file_params_are_keyed_by_content(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "p.png"
            Image.new("RGB", (8, 8), (255, 0, 0)).save(f)
            k1 = self.key([Layer("portrait", 1.0, 4.0, {"image": str(f)})])
            Image.new("RGB", (8, 8), (0, 0, 255)).save(f)           # same path, different picture: a different key
            k2 = self.key([Layer("portrait", 1.0, 4.0, {"image": str(f)})])
            self.assertNotEqual(k1, k2)
            self.assertNotEqual(self.key([Layer("portrait", 1.0, 4.0, {"image": Image.new("RGB", (4, 4), (1, 2, 3))})]),
                                self.key([Layer("portrait", 1.0, 4.0, {"image": Image.new("RGB", (4, 4), (3, 2, 1))})]))


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg needed")
class RenderTests(unittest.TestCase):
    def shots(self):
        return [Shot(A, 0.0, 2.0), Shot(B, 2.0, 4.4, seek=1.0)]

    def layers(self):
        return [Layer("kicker", 2.2, 4.0, {"text": "Test"}), Layer("number", 2.2, 4.0, {"value": 5, "label": "x", "sub": ""}, dim=True)]

    def test_render_exact_length_cache_hit_audio_and_cleanup(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "tmp"
            tmp.mkdir()
            out = Path(td) / "o.mp4"
            r1 = S.render_segmented(self.shots(), self.layers(), str(out), state_dir=td, temp_dir=str(tmp), workers=2)
            self.assertEqual(r1["frames"], 110)
            self.assertEqual((r1["cache_hits"], r1["cache_misses"]), (0, 2))
            self.assertAlmostEqual(_probe(out), 4.4, delta=0.05)
            self.assertEqual(list(tmp.iterdir()), [])                    # temp folders removed
            self.assertFalse(list(Path(td).glob("*.part*")))
            r2 = S.render_segmented(self.shots(), self.layers(), str(Path(td) / "o2.mp4"), state_dir=td, temp_dir=str(tmp))
            self.assertEqual((r2["cache_hits"], r2["cache_misses"]), (2, 0))
            self.assertEqual(out.read_bytes(), (Path(td) / "o2.mp4").read_bytes())          # deterministic
            changed = self.layers()
            changed[1].params["value"] = 7
            r3 = S.render_segmented(self.shots(), changed, str(Path(td) / "o3.mp4"), state_dir=td, temp_dir=str(tmp))
            self.assertEqual((r3["cache_hits"], r3["cache_misses"]), (1, 1))                # only the edited segment re-renders
            tone = Path(td) / "tone.m4a"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=9", "-c:a", "aac", str(tone)], check=True)
            r4 = S.render_segmented(self.shots(), self.layers(), str(Path(td) / "o4.mp4"), audio_path=str(tone), state_dir=td, temp_dir=str(tmp))
            self.assertAlmostEqual(_probe(r4["out"]), 4.4, delta=0.06)                       # long audio cut to the video length
            streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", r4["out"]],
                                     capture_output=True, text=True).stdout.split()
            self.assertEqual(sorted(streams), ["audio", "video"])

    def test_missing_clip_is_a_clear_error_and_leaves_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(S.MissingInput) as cm:
                S.render_segmented([Shot(str(Path(td) / "nope.mp4"), 0.0, 2.0)], [], str(Path(td) / "o.mp4"), temp_dir=td)
            self.assertIn("nope.mp4", str(cm.exception))
            self.assertEqual([p.name for p in Path(td).iterdir()], [])

    def test_cancel_stops_cleans_and_writes_no_output(self):
        with tempfile.TemporaryDirectory() as td:
            calls = {"n": 0}

            def cancel():
                calls["n"] += 1
                return calls["n"] > 30

            with self.assertRaises(S.RenderCancelled):
                S.render_segmented(self.shots(), self.layers(), str(Path(td) / "o.mp4"), cancel_check=cancel, temp_dir=td, workers=1)
            self.assertEqual([p.name for p in Path(td).iterdir()], [])

    def test_ffmpeg_failure_raises_and_cleans(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad.mp4"
            bad.write_text("not a video")
            out = Path(td) / "o.mp4"
            with self.assertRaises(S.RenderError):
                S.render_segmented([Shot(str(bad), 0.0, 1.0)], [], str(out), temp_dir=td)
            self.assertFalse(out.exists())
            self.assertFalse([p for p in Path(td).iterdir() if p.name.startswith("ce_war_")])

    def test_a_broken_card_does_not_stop_the_render(self):
        def boom(t, dur, p):
            raise ValueError("bad card")

        with tempfile.TemporaryDirectory() as td:
            orig = S.all_cards
            S.all_cards = lambda: {"boom": boom, **orig()}
            try:
                r = S.render_segmented([Shot(A, 0.0, 1.0)], [Layer("boom", 0.2, 0.9, {})], str(Path(td) / "o.mp4"), temp_dir=td)
            finally:
                S.all_cards = orig
            self.assertTrue(r["ok"])
            self.assertTrue(any("boom" in e for e in r["card_errors"]))

    def test_clip_shorter_than_shot_keeps_exact_length(self):
        short = clip("007.mp4")            # 2.9 s
        with tempfile.TemporaryDirectory() as td:
            r = S.render_segmented([Shot(str(short), 0.0, 4.0, seek=2.0)], [], str(Path(td) / "o.mp4"), temp_dir=td)
            self.assertAlmostEqual(_probe(r["out"]), 4.0, delta=0.05)


class EntryPointTests(unittest.TestCase):
    def test_style_entry_and_default_off(self):
        e = integration.style_entry()
        self.assertEqual(e["name"], "War Documentary")
        self.assertEqual(len(e["card"]), 4)

    def test_load_scenes_resolves_footage_and_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            pd = Path(td)
            (pd / "Images").mkdir()
            shutil.copy(A, pd / "Images" / "001.mp4")
            (pd / "Images" / ".asset_manifest.json").write_text(json.dumps({"1": {"local_path": str(pd / "Images" / "001.mp4"), "author": "X"}}))
            sc = integration.load_scenes(pd, [{"text": "t", "start": 0, "end": 2}, {"text": "u", "start": 2, "end": 4, "footage": "nope.mp4"}])
            self.assertTrue(sc[0]["footage"].endswith("001.mp4"))
            self.assertEqual(sc[0]["footage_meta"]["author"], "X")
            self.assertIsNone(sc[1]["footage"])                       # missing footage -> None, never an exception

    @unittest.skipUnless(HAVE_FFMPEG, "ffmpeg needed")
    def test_run_with_a_stub_planner_renders_and_reports(self):
        with tempfile.TemporaryDirectory() as td:
            pd = Path(td)
            plan = SimpleNamespace(shots=[Shot(A, 0.0, 2.0)], layers=[Layer("shot_head", 0.3, 1.8, {"text": "Sample"})], log=[{"scene": 1, "choice": "headline"}],
                                   credits=["Sample credit"], stats={"cards": 1})
            r = integration.run_war_documentary(str(pd), [{"text": "t", "start": 0, "end": 2}], None, str(pd / "out.mp4"), plan_fn=lambda sc, **k: plan)
            self.assertTrue(r["ok"])
            self.assertAlmostEqual(_probe(r["out"]), 2.0, delta=0.05)
            rep = json.loads(Path(r["report_path"]).read_text())
            self.assertEqual(rep["credits"], ["Sample credit"])


class FootageAttributionTests(unittest.TestCase):
    """Footage comes from the project's own asset manifest; nothing is invented; unknown rights are listed, not hidden."""

    @staticmethod
    def _project(td):
        pd = Path(td)
        (pd / "Images").mkdir()
        recs = {
            "001": {"source": "stock", "provider": "pexels", "provider_asset_id": "123", "author": "A Person", "source_url": "https://www.pexels.com/video/123/",
                    "type": "video", "status": "complete", "local_path": A, "width": 1280, "height": 720, "duration": 8.0},
            "002": {"source": "youtube_video", "provider": "youtube", "provider_asset_id": "abc", "channel": "Some Channel", "source_url": "https://youtu.be/abc",
                    "video_title": "A clip", "license": "Standard YouTube License", "type": "video", "status": "complete", "local_path": B},
            "003": {"source": "manual", "type": "video", "status": "complete", "local_path": A},
            "004": {"source": "stock", "provider": "pixabay", "provider_asset_id": "9", "status": "failed", "local_path": None},
            "005": {"source": "stock", "provider": "pixabay", "provider_asset_id": "10", "status": "complete", "local_path": str(pd / "gone.mp4")},
            "006": {"source": "stock", "provider": "openverse", "provider_asset_id": "o", "type": "image", "status": "complete", "local_path": str(ROOT / "Images" / "002.png")},
        }
        (pd / "Images" / ".asset_manifest.json").write_text(json.dumps(recs), encoding="utf-8")
        return pd

    def test_manifest_records_map_to_honest_footage_meta(self):
        with tempfile.TemporaryDirectory() as td:
            pd = self._project(td)
            sc = integration.load_scenes(pd, [{"text": f"scene {i}", "start": i, "end": i + 1, "scene_no": i} for i in range(1, 7)])
            m = {s["scene_no"]: s for s in sc}
            stock, yt, user = m[1]["footage_meta"], m[2]["footage_meta"], m[3]["footage_meta"]
            self.assertEqual((stock["provider"], stock["author"], stock["source_url"]), ("pexels", "A Person", "https://www.pexels.com/video/123/"))
            self.assertTrue(stock["generic"] and stock["verification"] == "unverified")
            self.assertNotIn("license", stock)                                     # nothing invented: the record has none
            self.assertFalse(yt["generic"])
            self.assertEqual(yt["license"], "Standard YouTube License")
            self.assertIn("clearance needed", yt["rights"])                       # public video is never treated as reusable
            self.assertFalse(yt["rights_known"])
            self.assertTrue(user["user_supplied"] and "stated by the user" in user["rights"] and user["verification"] == "unverified")
            for n in (4, 5, 6):                                                   # failed, file missing, still image: no footage, no placeholder
                self.assertIsNone(m[n]["footage"], n)
                self.assertTrue(m[n]["footage_meta"].get("no_footage_reason"), n)

    def test_generic_footage_is_labelled_not_headlined_and_youtube_gets_a_source_chip(self):
        from cinematic_explainer.war import planner
        with tempfile.TemporaryDirectory() as td:
            pd = self._project(td)
            txt = "Engineers rebuilt the bridge near the port in nine days after the flood."
            sc = integration.load_scenes(pd, [{"text": txt, "start": 0, "end": 5, "scene_no": 1}, {"text": txt, "start": 5, "end": 10, "scene_no": 2}])
            plan = planner.plan(sc)
            kinds = {(ly.kind, round(ly.start)) for ly in plan.layers}
            self.assertFalse(any(k == "shot_headline" and t < 5 for k, t in kinds))          # no headline claiming anything over generic stock
            chips = [ly.params["text"] for ly in plan.layers if ly.kind == "status_chip"]
            badges = [ly.params.get("kind") for ly in plan.layers if ly.kind == "kit_badge"]     # the direction pass shows the same label as a badge
            self.assertTrue("ILLUSTRATIVE FOOTAGE" in chips or "illustrative" in badges)
            self.assertTrue(any(c.startswith("UNVERIFIED") and "Some Channel" in c for c in chips))
            flags = {d.scene_no: d.flags for d in plan.log}
            self.assertIn("footage_generic", flags[1])
            self.assertIn("rights_clearance_needed", flags[2])

    @unittest.skipUnless(HAVE_FFMPEG, "ffmpeg needed")
    def test_run_writes_credits_and_report_and_a_second_run_is_a_cache_hit(self):
        with tempfile.TemporaryDirectory() as td:
            pd = self._project(td)
            scenes = [{"text": "Engineers rebuilt the bridge near the port in nine days after the flood.", "start": 0, "end": 3, "scene_no": 1},
                      {"text": "A third party published this clip and its rights are not cleared.", "start": 3, "end": 6, "scene_no": 2},
                      {"text": "Scene without any usable asset record.", "start": 6, "end": 8, "scene_no": 4}]
            out = pd / "out.mp4"
            r1 = integration.run_war_documentary(str(pd), scenes, None, str(out))
            self.assertTrue(r1["ok"])
            self.assertAlmostEqual(_probe(out), 8.0, delta=0.1)
            cred = Path(r1["credits_path"]).read_text(encoding="utf-8")
            self.assertIn("A Person", cred)
            self.assertIn("https://www.pexels.com/video/123/", cred)
            self.assertIn("Rights not established", cred)
            self.assertIn("clearance needed", cred)
            rep = json.loads(Path(r1["report_path"]).read_text(encoding="utf-8"))
            by = {s["scene_no"]: s for s in rep["scenes"]}
            self.assertTrue(by["1"]["asset"]["generic"])
            self.assertEqual(by["2"]["asset"]["provider"], "youtube")
            self.assertIsNone(by["4"]["asset"])
            self.assertTrue(by["4"]["no_footage_reason"])
            r2 = integration.run_war_documentary(str(pd), scenes, None, str(out))
            self.assertEqual(r2["render"]["cache_misses"], 0)
            self.assertGreater(r2["render"]["cache_hits"], 0)


class IsolationTests(unittest.TestCase):
    def test_nothing_outside_the_pack_imports_the_war_package(self):
        offenders = []
        for p in ROOT.glob("*.py"):
            if p.name.startswith("test_war") or p.name.startswith("test_cinematic"):
                continue
            if p.name == "app.py":
                continue   # the one lazy, additive style-picker hook (checked by test_war_app_section.py)
            if "cinematic_explainer" in p.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(p.name)
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
