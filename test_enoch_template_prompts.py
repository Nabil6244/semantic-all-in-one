"""Enoch Template prompts and packaging: the CSV prompt's own example goes through the real importer and rebuilds its script
word for word (test_csv_prompts.py's rule for every style), the research and script prompts never invite invention, and
the packaged app ships the style file, the prompts, the subject pack and the reference profile."""

from __future__ import annotations

import csv
import io
import unittest
from pathlib import Path

from test_csv_prompts import _example

ROOT = Path(__file__).resolve().parent


class CsvPrompt(unittest.TestCase):
    def test_example_loads_through_the_real_importer(self):
        from providers.base import SceneRow

        _text, script, csv_text = _example("enoch_template_csv_prompt.txt")
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        self.assertEqual(list(rows[0].keys()), ["scene_number", "script_segment", "asset_type", "prompt"])
        self.assertEqual(" ".join(r["script_segment"] for r in rows), script)
        self.assertEqual([r["scene_number"] for r in rows], [str(i) for i in range(1, len(rows) + 1)])
        for r in rows:
            scene = SceneRow.from_csv_row(r)
            self.assertTrue(scene.wants_flow or scene.wants_stock or scene.wants_map or scene.wants_commons_image, r)
        ai = sum(1 for r in rows if r["asset_type"].startswith("flow"))
        self.assertLessEqual(ai, 1, "the example itself respects the style's AI rule")

    def test_registered_for_the_copy_button(self):
        from app_csv_prompts import CSV_PROMPTS, STYLE_NAMES, build_prompt

        self.assertEqual(CSV_PROMPTS["enoch_template"], "enoch_template_csv_prompt.txt")
        self.assertEqual(STYLE_NAMES["enoch_template"], "Enoch Template")
        self.assertIn("El texto.", build_prompt("enoch_template", "El texto."))
        self.assertEqual(CSV_PROMPTS["normal"], "normal_csv_prompt.txt", "Normal's prompt is unchanged")


class ResearchAndScriptPrompts(unittest.TestCase):
    def test_research_prompt_forbids_invention_and_lists_open_questions(self):
        from ancient_texts.prompts import research_prompt
        from ancient_texts.subjects import load_pack

        text = research_prompt("The Son of Man in 1 Enoch", load_pack("enoch"))
        for needle in ('ALWAYS "unchecked"', '"verified" is ALWAYS false', "NEVER invent a page", 'ALWAYS {"state": "unreviewed"}',
                       "W-01", "The Son of Man in 1 Enoch"):
            self.assertIn(needle, text)
        self.assertNotIn("<<<", text)

    def test_script_prompt_follows_the_language_and_requires_qualification(self):
        from ancient_texts.prompts import script_prompt

        text = script_prompt('{"claims": []}', "Spanish")
        self.assertIn("Write in this language: Spanish", text)
        self.assertIn("MUST be", text)
        self.assertIn("counterargument: REQUIRED", text)
        self.assertIn("as many sections as the evidence supports", text)
        self.assertNotIn("<<<", text)


class Packaging(unittest.TestCase):
    def test_the_spec_ships_every_runtime_file(self):
        spec = (ROOT / "VideoGenerator.spec").read_text(encoding="utf-8")
        self.assertIn('for _data_dir_name in ("styles", "brand_kits")', spec)      # styles/enoch_template.json
        self.assertIn("*_prompt.txt", spec)                                          # the three prompts
        self.assertIn('ROOT / "ancient_texts" / _at_sub', spec)                     # packs + reference profiles
        for sub in ("packs", "reference_profiles"):
            self.assertTrue(list((ROOT / "ancient_texts" / sub).glob("*.json")), sub)


if __name__ == "__main__":
    unittest.main()
