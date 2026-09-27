"""Voiceover <-> script validation for Overscaled / Exp Solar Generate.

History: the first version of this check compared WORD COUNTS (script vs
transcript) and blocked when the transcript had >12% fewer words. That
blocked valid work: a reworded take of the same story (real project: 240
transcribed words vs a 323-349 word script, 53-62% of the script spoken in
order) failed even though it is plainly the same content, and a count can't
tell a matching take from a different script of similar length anyway.

It now aligns the actual narration text (order-preserving word alignment
after comparison-only normalization) and classifies PASS / WARN / FAIL.
Thresholds come from real project recordings (fixtures below):
  matching take 0.90-1.00 · reworded take 0.53-0.62 · different script 0.01-0.12
Only FAIL (< 35%, or no speech) blocks Generate, before any asset download.

The retimer (voiceover_sync.retime_to_whisper_words) also no longer
collapses the final beats into the audio's last instant when the counts
differ — that collapse was what made layout fail with "overlapping nodes".
"""

from __future__ import annotations

import csv
import json
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scene_graph.app_integration import check_voiceover_matches_script, generate_overscaled_video

FIXTURES = Path(__file__).resolve().parent / "test_fixtures" / "voiceover_check"


def _words(text: str, pace: float = 0.4):
    return [(w, i * pace, i * pace + pace * 0.8) for i, w in enumerate(text.split())]


def _rows(*segments):
    return [{"scene_number": str(i + 1), "script_segment": s} for i, s in enumerate(segments)]


_SCRIPT = [
    "For nearly a century, Hoover Dam has stood between Arizona and Nevada.",
    "Engineers diverted the Colorado River through four enormous tunnels in 1931.",
    "NASA's Artemis-III mission will use lessons learned from projects like this.",
    "Workers poured concrete day and night for almost two years.",
]


class TestClassification(unittest.TestCase):
    def test_1_exact_same_script_passes(self):
        check = check_voiceover_matches_script(_rows(*_SCRIPT), _words(" ".join(_SCRIPT)))
        self.assertEqual(check.status, "pass")
        self.assertGreater(check.coverage, 0.99)

    def test_2_punctuation_case_whitespace_and_quote_variants_pass(self):
        spoken = " ".join(_SCRIPT).upper().replace(",", "").replace(".", " ").replace("'", "’")
        check = check_voiceover_matches_script(_rows(*_SCRIPT), _words("  ".join(spoken.split())))
        self.assertEqual(check.status, "pass")

    def test_3_minor_whisper_differences_do_not_block(self):
        spoken = " ".join(_SCRIPT).replace("1931", "nineteen thirty one").replace("Artemis-III", "Artemis three")
        spoken = spoken.replace("Hoover", "Hover").replace("two years", "2 years")
        check = check_voiceover_matches_script(_rows(*_SCRIPT), _words(spoken))
        self.assertIn(check.status, ("pass", "warn"))
        self.assertNotEqual(check.status, "fail")

    def test_4_narration_speed_never_matters(self):
        text = " ".join(_SCRIPT)
        fast = check_voiceover_matches_script(_rows(*_SCRIPT), _words(text, pace=0.2))
        slow = check_voiceover_matches_script(_rows(*_SCRIPT), _words(text, pace=1.5))
        self.assertEqual((fast.status, slow.status), ("pass", "pass"))

    def test_5_continuation_and_visual_only_rows_are_not_false_mismatches(self):
        rows = _rows(_SCRIPT[0], "", _SCRIPT[1], "", "", _SCRIPT[2], _SCRIPT[3])  # empty = visual/continuation
        check = check_voiceover_matches_script(rows, _words(" ".join(_SCRIPT)))
        self.assertEqual(check.status, "pass")
        self.assertEqual(check.script_words, sum(len(s.split()) for s in _SCRIPT))

    def test_6_one_narration_beat_on_several_visual_rows_is_counted_once(self):
        rows = _rows(_SCRIPT[0], _SCRIPT[1], _SCRIPT[1], _SCRIPT[1], _SCRIPT[2], _SCRIPT[3])
        check = check_voiceover_matches_script(rows, _words(" ".join(_SCRIPT)))
        self.assertEqual(check.status, "pass")
        self.assertGreater(check.coverage, 0.99)

    def test_7_long_form_script_with_realistic_transcription_noise_passes(self):
        random.seed(7)
        vocab = [f"word{i}" for i in range(900)] + ["the", "a", "of", "and", "river", "dam"] * 50
        script_words = [random.choice(vocab) for _ in range(3200)]  # ~20+ minutes of narration
        rows = [{"scene_number": str(i // 20 + 1), "script_segment": " ".join(script_words[i:i + 20])}
                for i in range(0, len(script_words), 20)]
        spoken = list(script_words)
        for i in random.sample(range(len(spoken)), 160):  # 5% misheard
            spoken[i] = "misheard"
        del spoken[1000:1012]  # a dropped phrase
        check = check_voiceover_matches_script(rows, [(w, 0.0, 0.1) for w in spoken])
        self.assertEqual(check.status, "pass")

    def test_8_a_different_scripts_voiceover_fails(self):
        other = ("The Great Wall stretches thousands of kilometres across northern China, built over "
                 "centuries by many dynasties to hold back raiders from the steppe.")
        check = check_voiceover_matches_script(_rows(*_SCRIPT), _words(other))
        self.assertEqual(check.status, "fail")
        self.assertIn("different script", check.message)

    def test_9_empty_or_silent_voiceover_fails_clearly(self):
        check = check_voiceover_matches_script(_rows(*_SCRIPT), [])
        self.assertEqual(check.status, "fail")
        self.assertIn("No speech", check.message)

    def test_no_transcript_or_no_narration_skips_the_check(self):
        self.assertIsNone(check_voiceover_matches_script(_rows(*_SCRIPT), None))
        self.assertIsNone(check_voiceover_matches_script(_rows("", ""), _words("hello there")))


class TestRealProjectRecordings(unittest.TestCase):
    """Real CSV + real Whisper transcripts from the project that was blocked."""

    @classmethod
    def setUpClass(cls):
        with open(FIXTURES / "hoover_plan.csv", newline="", encoding="utf-8-sig") as f:
            cls.rows = list(csv.DictReader(f))

    def _take(self, name):
        return [tuple(w) for w in json.loads((FIXTURES / name).read_text(encoding="utf-8"))]

    def test_10_matching_take_passes(self):
        check = check_voiceover_matches_script(self.rows, self._take("hoover_matching_take.json"))
        self.assertEqual(check.status, "pass")

    def test_reworded_take_of_the_same_story_warns_but_does_not_block(self):
        check = check_voiceover_matches_script(self.rows, self._take("hoover_reworded_take.json"))
        self.assertEqual(check.status, "warn")

    def test_another_projects_recording_is_rejected(self):
        check = check_voiceover_matches_script(self.rows, self._take("other_script_take.json"))
        self.assertEqual(check.status, "fail")

    def test_retime_never_collapses_scenes_into_the_last_instant(self):
        from scene_graph.generator import generate_scene_graph_local_planner, scene_rows_from_csv_rows
        from scene_graph.layout import compute_layout, find_overlaps
        from scene_graph.pipeline import _merge_grouped_beats_for_retime, _sync_grouped_node_timing
        from scene_graph.voiceover_sync import retime_to_whisper_words

        for take in ("hoover_matching_take.json", "hoover_reworded_take.json"):
            words = self._take(take)
            graph = generate_scene_graph_local_planner(
                "s", scene_rows_from_csv_rows(self.rows), style_preset="exp_solar").scene_graph
            retimed = _sync_grouped_node_timing(retime_to_whisper_words(_merge_grouped_beats_for_retime(graph), words))
            self.assertAlmostEqual(retimed.duration, words[-1][2], delta=0.5, msg=take)
            last_starts = sorted(n.appear_at for n in retimed.nodes)[-4:]
            self.assertGreater(last_starts[-1] - last_starts[0], 3.0, msg=f"{take}: tail scenes piled up")
            # Exactly as run_overscaled_pipeline lays it out (Exp Solar's own
            # four-cards-per-chapter cap included).
            from scene_graph.style_presets import load_style_preset

            cap = (load_style_preset("exp_solar").metadata or {}).get("max_active_per_chapter")
            self.assertEqual(find_overlaps(compute_layout(retimed, max_active_per_chapter=cap)), [], msg=take)


class TestGenerateBoundary(unittest.TestCase):
    def _csv(self, tmp: Path) -> Path:
        path = tmp / "plan.csv"
        path.write_text((FIXTURES / "hoover_plan.csv").read_text(encoding="utf-8-sig"), encoding="utf-8")
        return path

    def _run(self, take: str):
        words = [tuple(w) for w in json.loads((FIXTURES / take).read_text(encoding="utf-8"))]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            vo = tmp / "vo.wav"
            vo.write_bytes(b"RIFF")
            resolve = mock.Mock(return_value={})
            pipeline = mock.Mock(return_value=mock.Mock(ok=False, cancelled=False, errors=["stop here"]))
            with mock.patch("scene_graph.app_integration.resolve_scene_graph_media", resolve), \
                    mock.patch("scene_graph.app_integration.run_overscaled_pipeline", pipeline):
                result = generate_overscaled_video(
                    str(self._csv(tmp)), str(vo), str(tmp / "o.mp4"), style_preset_id="exp_solar",
                    use_local_planner=True, whisper_words=words, log=lambda *_: None,
                )
            return result, resolve

    def test_matching_and_reworded_takes_proceed_to_asset_resolution(self):
        for take in ("hoover_matching_take.json", "hoover_reworded_take.json"):
            _, resolve = self._run(take)
            resolve.assert_called_once()

    def test_different_script_is_stopped_before_any_download(self):
        result, resolve = self._run("other_script_take.json")
        self.assertFalse(result.ok)
        self.assertIn("doesn't match", result.errors[0])
        resolve.assert_not_called()


class TestRetimeCountsEqualIsUnchanged(unittest.TestCase):
    def test_exact_count_match_uses_the_same_word_spans_as_before(self):
        from scene_graph.generator import generate_scene_graph_local_planner, scene_rows_from_csv_rows
        from scene_graph.voiceover_sync import retime_to_whisper_words

        graph = generate_scene_graph_local_planner("s", scene_rows_from_csv_rows(_rows(*_SCRIPT))).scene_graph
        words = _words(" ".join(_SCRIPT))
        retimed = retime_to_whisper_words(graph, words)
        cursor = 0
        for beat in retimed.beats:
            n = len(beat.narration.split())
            self.assertAlmostEqual(beat.start, words[cursor][1], places=3)
            self.assertAlmostEqual(beat.end, words[cursor + n - 1][2], places=3)
            cursor += n


if __name__ == "__main__":
    unittest.main()
