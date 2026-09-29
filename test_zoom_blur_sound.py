"""Transition sound for zoom-blur cuts, and the render/Editor-timeline sound
bugs found while fixing it (the first cut's sounds never reached the final
mix; timeline SFX were cut to 0.4 s)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from editorial.timeline import EditorialTimeline, TimelineEvent
from smart_editing import SmartEditingSettings, apply_zoom_blur_whooshes, zoom_blur_whoosh_events


def _effective_peak_db(ev: dict) -> float:
    """The level a whoosh actually hits the cut at: its file's peak x its volume."""
    import math

    from smart_editing import _event_path, _peak_profile

    path = _event_path(ev)
    return _peak_profile(str(path), path.stat().st_mtime)[1] + 20 * math.log10(float(ev["volume"]))


class TestTimelineSoundAuthority(unittest.TestCase):
    def test_engine_placeholders_are_not_an_audible_timeline(self):
        tl = EditorialTimeline(events=[TimelineEvent(event_id="a", track="AMBIENCE", start=0, end=5, metadata={"profile": "room"})])
        self.assertFalse(EditorialTimeline.from_dict(tl.to_dict()).audio_materialized)

    def test_first_cut_materialized_sounds_are(self):
        import editorial_timeline_edit as tl_edit

        tl = EditorialTimeline(events=[TimelineEvent(event_id="v", track="VIDEO_1", start=0, end=5)])
        tl_edit.materialize_sfx_ambience_events(tl, sfx_events=[{"start": 1.0, "duration": 0.5, "volume": 0.6,
                                                                "file": "whoosh/whoosh_05.wav", "zoom_blur": True}],
                                                ambience_beds=[])
        again = EditorialTimeline.from_dict(tl.to_dict())
        self.assertTrue(again.audio_materialized)
        # An operator who deleted every sound keeps a silent video (flag survives, no events).
        again.events = [e for e in again.events if e.track not in ("SFX", "AMBIENCE")]
        self.assertTrue(EditorialTimeline.from_dict(again.to_dict()).audio_materialized)

    def test_export_keeps_sfx_length_and_the_zoom_blur_flag(self):
        import editorial_timeline_edit as tl_edit

        tl = EditorialTimeline(events=[TimelineEvent(event_id="s", track="SFX", start=2.0, end=4.5, source="x.wav",
                                                     metadata={"file": "cinematic/c.wav", "volume": 0.3, "zoom_blur": True})])
        sfx, _ = tl_edit.sfx_ambience_events_for_export(tl)
        self.assertEqual((sfx[0]["duration"], sfx[0]["zoom_blur"]), (2.5, True))

    def test_render_reads_the_editor_timeline_before_the_compile_overwrites_it(self):
        src = (Path(__file__).resolve().parent / "app.py").read_text(encoding="utf-8")
        snap, compile_at = src.index("pre_compile_timeline = _tl_pre.load_timeline(state_dir)"), src.index("editorial_plan = compile_editorial_plan(")
        self.assertLess(snap, compile_at)
        self.assertIn("operator_timeline = pre_compile_timeline", src)
        self.assertIn("if op_tl.audio_materialized or op_sfx or op_amb:", src)


class TestZoomBlurWhooshes(unittest.TestCase):
    def test_added_raised_never_doubled_and_a_text_pop_does_not_count(self):
        existing = [{"start": 11.48, "file": "whoosh/whoosh_05.wav", "volume": 0.3},
                    {"start": 15.06, "file": "text/text_pop_01.wav", "volume": 0.25}]
        out, added, raised = apply_zoom_blur_whooshes(existing, [("3", 11.6), ("4", 15.06)], SmartEditingSettings())
        self.assertEqual((added, raised), (1, 1))
        self.assertTrue(out[0]["zoom_blur"] and out[0]["volume"] > 0.6)  # whoosh_05 plays at full zoom-blur level
        self.assertEqual(out[1]["volume"], 0.25)  # the text pop is untouched
        from smart_editing import _peak_at

        new = [e for e in out if e.get("scene_number") == "4"][0]
        self.assertAlmostEqual(_peak_at(new), 15.06, delta=0.06)  # its loudest moment lands on the cut
        out2, added2, raised2 = apply_zoom_blur_whooshes(out, [("3", 11.6), ("4", 15.06)], SmartEditingSettings())
        self.assertEqual((added2, raised2, len(out2)), (0, 0, len(out)))

    def test_a_late_peaking_riser_is_started_early_so_its_peak_hits_the_cut(self):
        from smart_editing import _peak_at

        raised, _, _ = apply_zoom_blur_whooshes(
            [{"start": 11.48, "end": 11.98, "file": "transition/transition_02.wav", "volume": 0.3}],
            [("3", 11.6)], SmartEditingSettings())
        e = raised[0]
        self.assertAlmostEqual(_peak_at(e), 11.6, delta=0.06)
        self.assertGreater(e["duration"], 1.0)  # plays through its peak, not just the quiet build-up
        self.assertTrue(e["zoom_blur"])

    def test_loud_fast_sounds_alternate(self):
        events = zoom_blur_whoosh_events([("2", 6.0), ("3", 12.0), ("4", 18.0)], [], SmartEditingSettings())
        ids = [e["sfx_id"] for e in events]
        self.assertEqual(len(ids), 3)
        self.assertNotEqual(ids[0], ids[1])
        self.assertTrue(all(e["zoom_blur"] for e in events))
        levels = [_effective_peak_db(e) for e in events]
        self.assertLess(max(levels) - min(levels), 1.5)  # every cut hits at the same loudness

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not available")
    def test_zoom_blur_whoosh_is_mixed_louder_than_the_normal_sfx_cap(self):
        import numpy as np

        from smart_editing import mix_sfx_with_narration, sfx_library_root

        with tempfile.TemporaryDirectory() as tmp:
            narration = Path(tmp) / "n.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "3",
                            str(narration)], check=True)

            def level(flag: bool) -> float:
                out = Path(tmp) / f"o{int(flag)}.wav"
                ev = {"start": 1.0, "duration": 0.5, "volume": 0.67, "file": "whoosh/whoosh_05.wav"}
                if flag:
                    ev["zoom_blur"] = True
                mix_sfx_with_narration(narration, [ev], out, sfx_root=sfx_library_root(), ambience_beds=[])
                raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(out), "-f", "s16le", "-ac", "1", "-"],
                                     capture_output=True, check=True).stdout
                a = np.frombuffer(raw, dtype=np.int16).astype(float)
                return float((a ** 2).mean() ** 0.5)

            normal, zoom = level(False), level(True)
            self.assertGreater(normal, 0)
            self.assertGreater(zoom, normal * 1.5)  # 0.67 vs the 0.40 cap


if __name__ == "__main__":
    unittest.main()
