"""Phases 2–5: Audio / Music / Pacing directors + Editorial QA."""

from __future__ import annotations

import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from editorial.audio_director import (
    ambience_intensity_for_scene,
    apply_ambience_intensity_to_beds,
    enrich_scene_audio_fields,
    filter_sfx_events,
)
from editorial.builder import build_editorial_plan
from editorial.music_director import (
    build_music_cues,
    build_music_plan,
    render_ducked_music,
)
from editorial.pacing import authoritative_transition_map, finalize_transitions
from editorial.qa import run_editorial_qa, save_editorial_qa
from editorial.schema import EditorialPlan, EditorialScene


def _write_wav(path: Path, *, seconds: float, freq: float = 440.0, amp: float = 0.4, sr: int = 16000) -> None:
    n = int(seconds * sr)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        frames = bytearray()
        for i in range(n):
            # Loud first half, quiet second half
            local_amp = amp if i < n // 2 else amp * 0.08
            sample = int(32767 * local_amp * math.sin(2 * math.pi * freq * i / sr))
            frames += struct.pack("<h", sample)
        wf.writeframes(frames)


def _plan_three() -> EditorialPlan:
    rows = [
        {"scene_number": "1", "script_segment": "Welcome to the secret story.", "asset_type": "image", "prompt": "city"},
        {"scene_number": "2", "script_segment": "Scientists found shocking evidence in the data.", "asset_type": "image", "prompt": "lab"},
        {"scene_number": "3", "script_segment": "Thank you for watching.", "asset_type": "image", "prompt": "sunset"},
    ]
    aligned = [
        {"scene_number": "1", "script_segment": rows[0]["script_segment"], "start_time": 0.0, "end_time": 2.0},
        {"scene_number": "2", "script_segment": rows[1]["script_segment"], "start_time": 2.0, "end_time": 5.0},
        {"scene_number": "3", "script_segment": rows[2]["script_segment"], "start_time": 5.0, "end_time": 7.0},
    ]
    return build_editorial_plan(rows, aligned, 7.0)


class TestAudioDirector(unittest.TestCase):
    def test_intensity_mapping(self) -> None:
        plan = _plan_three()
        hook = plan.scenes[0]
        self.assertGreater(hook.ambience_intensity, 0.5)
        beds = [
            {"scene_number": s.scene_number, "start": s.start, "end": s.end, "volume": 0.30}
            for s in plan.scenes
        ]
        out = apply_ambience_intensity_to_beds(beds, plan)
        self.assertEqual(len(out), 3)
        for bed, scene in zip(out, plan.scenes):
            self.assertAlmostEqual(bed["start"], scene.start, places=3)
            self.assertAlmostEqual(bed["end"], scene.end, places=3)
            self.assertLessEqual(bed["volume"], 0.42)
            self.assertGreaterEqual(bed["volume"], 0.05)

    def test_silence_suppresses_beat_sfx(self) -> None:
        plan = EditorialPlan(
            audio_end=6.0,
            scenes=[
                EditorialScene(
                    scene_number="1",
                    start=0,
                    end=3,
                    duration=3,
                    purpose="explanation",
                    attention_score=0.3,
                    allow_silence=True,
                ),
                EditorialScene(
                    scene_number="2",
                    start=3,
                    end=6,
                    duration=3,
                    purpose="hook",
                    attention_score=0.9,
                ),
            ],
        )
        events = [
            {"type": "impact", "start": 1.0, "volume": 0.4, "scene_number": "1"},
            {"type": "whoosh", "start": 2.9, "volume": 0.4, "scene_number": "1"},
            {"type": "impact", "start": 4.0, "volume": 0.4, "scene_number": "2"},
        ]
        filtered = filter_sfx_events(events, plan)
        kinds = [(e["scene_number"], e["type"]) for e in filtered]
        self.assertNotIn(("1", "impact"), kinds)
        self.assertIn(("1", "whoosh"), kinds)
        self.assertIn(("2", "impact"), kinds)

    def test_sfx_boundary_safety(self) -> None:
        plan = EditorialPlan(
            audio_end=4.0,
            scenes=[
                EditorialScene(scene_number="1", start=0, end=2, duration=2, purpose="hook", attention_score=0.9),
                EditorialScene(scene_number="2", start=2, end=4, duration=2, purpose="context", attention_score=0.5),
            ],
        )
        # Event claimed for scene 1 but past its end — must drop
        events = [{"type": "impact", "start": 2.5, "volume": 0.4, "scene_number": "1"}]
        filtered = filter_sfx_events(events, plan)
        self.assertEqual(filtered, [])

    def test_purpose_sfx_weight_hook_vs_explanation(self) -> None:
        enrich_scene_audio_fields(
            EditorialPlan(
                scenes=[
                    EditorialScene(
                        scene_number="1", start=0, end=3, duration=3, purpose="hook", attention_score=0.9
                    )
                ]
            )
        )
        hook_i = ambience_intensity_for_scene(
            EditorialScene(scene_number="1", start=0, end=3, duration=3, purpose="hook", attention_score=0.9)
        )
        expl_i = ambience_intensity_for_scene(
            EditorialScene(
                scene_number="2", start=40, end=44, duration=4, purpose="explanation", attention_score=0.4
            )
        )
        self.assertGreater(hook_i, expl_i)


class TestMusicDirector(unittest.TestCase):
    def test_no_music_path_remains_disabled(self) -> None:
        plan = _plan_three()
        mp = build_music_plan(plan, music_path=None)
        self.assertFalse(mp.enabled)
        self.assertEqual(mp.source, "none")

    def test_sections_and_cues(self) -> None:
        plan = _plan_three()
        with tempfile.TemporaryDirectory() as tmp:
            music = Path(tmp) / "bed.wav"
            narr = Path(tmp) / "vo.wav"
            _write_wav(music, seconds=8.0, freq=220.0, amp=0.3)
            _write_wav(narr, seconds=7.0, freq=300.0, amp=0.5)
            mp = build_music_plan(plan, music_path=music, narration_path=narr)
            self.assertTrue(mp.enabled)
            self.assertGreaterEqual(len(mp.sections), 2)
            self.assertGreater(len(mp.cues), 3)
            roles = {s.role for s in mp.sections}
            self.assertTrue({"intro", "outro"} & roles or "build" in roles)

    def test_ducking_rms_decreases_then_recovers(self) -> None:
        plan = _plan_three()
        with tempfile.TemporaryDirectory() as tmp:
            music = Path(tmp) / "bed.wav"
            narr = Path(tmp) / "vo.wav"
            out = Path(tmp) / "ducked.wav"
            _write_wav(music, seconds=8.0, freq=220.0, amp=0.5)
            _write_wav(narr, seconds=7.0, freq=300.0, amp=0.6)
            cues = build_music_cues(plan, narration_path=narr, window_s=0.5)
            # Cue volumes: loud narration half should average lower than quiet half
            mid_t = 3.5
            loud = [c.volume for c in cues if c.end <= mid_t]
            quiet = [c.volume for c in cues if c.start >= mid_t]
            self.assertTrue(loud and quiet)
            self.assertLess(sum(loud) / len(loud), sum(quiet) / len(quiet))
            self.assertTrue(render_ducked_music(music, cues, out, duration=7.0))
            self.assertTrue(out.is_file())
            self.assertGreater(out.stat().st_size, 1000)


class TestPacingDirector(unittest.TestCase):
    def test_authoritative_map_single_source(self) -> None:
        plan = _plan_three()
        tmap = authoritative_transition_map(plan)
        self.assertIsInstance(tmap, dict)
        # Density should stay reasonable
        self.assertLessEqual(len(tmap), len(plan.scenes))
        finalize_transitions(plan)
        self.assertEqual(plan.scenes[0].transition_in, "fade")

    def test_explicit_visual_transition_wins(self) -> None:
        plan = EditorialPlan(
            audio_end=6.0,
            scenes=[
                EditorialScene(scene_number="1", start=0, end=2, duration=2, transition_in="fade"),
                EditorialScene(
                    scene_number="2",
                    start=2,
                    end=4,
                    duration=2,
                    purpose="emotion",
                    attention_score=0.8,
                    transition_in="dissolve",
                ),
                EditorialScene(scene_number="3", start=4, end=6, duration=6, purpose="outro", attention_score=0.4),
            ],
        )
        tmap = authoritative_transition_map(plan)
        self.assertEqual(tmap.get("2"), "dissolve")


class TestEditorialQA(unittest.TestCase):
    def test_qa_scores_and_persists(self) -> None:
        plan = _plan_three()
        beds = [
            {
                "scene_number": s.scene_number,
                "start": s.start,
                "end": s.end,
                "profile": "room",
                "volume": 0.3,
            }
            for s in plan.scenes
        ]
        report = run_editorial_qa(plan, ambience_beds=beds, transition_map=plan.transition_style_map())
        self.assertIn(report.verdict, ("PASS", "WARN", "FAIL"))
        self.assertGreaterEqual(report.score, 0)
        self.assertLessEqual(report.score, 100)
        with tempfile.TemporaryDirectory() as tmp:
            path = save_editorial_qa(Path(tmp), report)
            self.assertTrue(path.is_file())
            self.assertTrue((Path(tmp) / "editorial_qa.txt").is_file())

    def test_cross_cut_ambience_detected(self) -> None:
        plan = _plan_three()
        bad_beds = [
            {
                "scene_number": "1",
                "start": 0.0,
                "end": 5.0,  # spans into scene 2
                "profile": "room",
                "volume": 0.3,
            }
        ]
        report = run_editorial_qa(plan, ambience_beds=bad_beds)
        cats = {i.category for i in report.issues}
        self.assertIn("ambience", cats)

    def test_missing_ambience_warn(self) -> None:
        plan = _plan_three()
        # beds for only one scene while many expected
        beds = [{"scene_number": "1", "start": 0, "end": 2, "profile": "room", "volume": 0.3}]
        # Force more scenes so missing ratio triggers
        for i in range(4, 12):
            plan.scenes.append(
                EditorialScene(
                    scene_number=str(i),
                    start=float(i),
                    end=float(i + 1),
                    duration=1.0,
                    ambience_profile="room",
                )
            )
        report = run_editorial_qa(plan, ambience_beds=beds)
        self.assertTrue(any(i.category == "ambience" for i in report.issues))


class TestManualCsvStillWorks(unittest.TestCase):
    def test_csv_only_full_enrichment(self) -> None:
        plan = _plan_three()
        self.assertTrue(plan.film_sections)
        self.assertTrue(all(s.ambience_intensity > 0 for s in plan.scenes))
        self.assertTrue(any(s.sfx_moments is not None for s in plan.scenes))
        self.assertIn(plan.scenes[0].purpose, ("hook", "context"))


if __name__ == "__main__":
    unittest.main()
