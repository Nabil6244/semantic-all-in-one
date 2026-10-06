#!/usr/bin/env python3
"""Every style's copyable CSV prompt (composition_styles/*_prompt.txt) teaches a CSV its importer accepts: the prompt's own
example loads through the real importer without errors, its rows rebuild the example script word for word where the
format carries the narration, and the prompt ends with the script placeholder the app's "Copy the CSV prompt" fills."""

from __future__ import annotations

import csv
import io
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "composition_styles"
PLACEHOLDER = "<<<PASTE THE SCRIPT HERE>>>"


def _example(name: str):
    text = (ROOT / name).read_text(encoding="utf-8")
    ex = text.split("EXAMPLE", 1)[1]
    script = ex.split("Script:", 1)[1].split("CSV:", 1)[0].strip() if "Script:" in ex else ""
    body = ex.split("CSV:", 1)[1] if "CSV:" in ex else ex.split("\n", 1)[1]
    csv_text = body.split("NOW WRITE", 1)[0].strip() + "\n"
    return text, script, csv_text


def _words(script: str, gap: float = 0.4):
    out, t = [], 0.0
    for w in script.split():
        out.append((w.strip(".,;:"), round(t, 2), round(t + 0.3, 2)))
        t += gap
    return out


class TestCsvPrompts(unittest.TestCase):
    def test_every_prompt_ends_with_the_script_placeholder(self):
        from app_csv_prompts import CSV_PROMPTS

        for style, name in CSV_PROMPTS.items():
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertEqual(text.count(PLACEHOLDER), 1, style)
            self.assertTrue(text.rstrip().endswith(PLACEHOLDER), style)

    def test_normal(self):
        from map_scene.spec import parse_map_prompt
        from providers.base import SceneRow

        _text, script, csv_text = _example("normal_csv_prompt.txt")
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        self.assertEqual(list(rows[0].keys()), ["scene_number", "script_segment", "asset_type", "prompt"])
        self.assertEqual(" ".join(r["script_segment"] for r in rows), script)
        self.assertEqual([r["scene_number"] for r in rows], [str(i) for i in range(1, len(rows) + 1)])
        allowed = {"stock_video", "stock_image", "youtube_video", "archive_video", "nasa_video", "commons_image", "commons_video",
                   "flow_video", "flow_image", "map"}
        for r in rows:
            self.assertIn(r["asset_type"], allowed)
            scene = SceneRow.from_csv_row(r)
            wants = (scene.wants_flow or scene.wants_stock or scene.wants_youtube or scene.wants_archive or scene.wants_nasa
                     or scene.wants_commons_image or scene.wants_commons_video or scene.wants_map)
            self.assertTrue(wants, f"scene {r['scene_number']} would resolve to nothing")
            if r["asset_type"] == "map":
                parse_map_prompt(r["prompt"])

    def test_overscaled(self):
        from scene_graph.overscaled_csv import ALL_COLUMNS, compile_overscaled_csv

        _text, _script, csv_text = _example("overscaled_csv_prompt.txt")
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        self.assertEqual(tuple(rows[0].keys()), ALL_COLUMNS)
        result = compile_overscaled_csv(rows, segment_id="seg1", title="t")
        self.assertTrue(result.ok, getattr(result, "errors", None))

    def test_exp_solar(self):
        from scene_graph.exp_solar_csv import ALL_COLUMNS, compile_exp_solar_csv

        _text, script, csv_text = _example("exp_solar_csv_prompt.txt")
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        self.assertEqual(tuple(rows[0].keys()), ALL_COLUMNS)
        self.assertEqual(" ".join(r["script_segment"] for r in rows), script)
        result = compile_exp_solar_csv(rows, segment_id="seg1", title="t")
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.warnings, [])

    def test_pakmap(self):
        from pakmap.compile import compile_csv

        _text, script, csv_text = _example("pakmap_csv_prompt.txt")
        words = _words(script)
        result = compile_csv(text=csv_text, words=words, duration=words[-1][2] + 1.0)
        report = getattr(result, "report", result)
        self.assertEqual(list(getattr(report, "errors", [])), [])

    def test_hybrid(self):
        from hybrid.beat_csv import import_beats

        _text, script, csv_text = _example("hybrid_beats_prompt.txt")
        words = _words(script)
        got = import_beats(csv_text, words, words[-1][2] + 0.5)
        self.assertFalse([n for n in got.notes if "outside beat" in n], got.notes)


if __name__ == "__main__":
    unittest.main()
