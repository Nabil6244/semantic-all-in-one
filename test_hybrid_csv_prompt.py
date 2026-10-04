"""The Hybrid CSV prompt teaches by example, so its example must be a CSV the app accepts: right header, compiles against the narration with
no error and no warning, footage and cards where the prompt says, and the opening on the globe."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from pakmap.compile import compile_csv
from pakmap.schema import COLUMNS

PROMPT = Path(__file__).with_name("composition_styles") / "hybrid_csv_prompt.txt"


def parts():
    t = PROMPT.read_text(encoding="utf-8")
    script = t.split("Script:\n", 1)[1].split("\n\nCSV:", 1)[0].strip()
    csv_text = t.split("CSV:\n", 1)[1].split("\n\nNOW WRITE", 1)[0].strip()
    return t, script, csv_text


class TestHybridCsvPrompt(unittest.TestCase):
    def test_the_header_uses_real_columns_and_matches_the_one_the_prompt_demands(self):
        t, _, csv_text = parts()
        header = csv_text.splitlines()[0]
        self.assertTrue(set(header.split(",")) <= set(COLUMNS))
        self.assertIn("HEADER (exactly this, in this order)\n" + header, t)

    def test_the_example_compiles_cleanly_against_its_narration(self):
        _, script, csv_text = parts()
        toks = re.findall(r"[A-Za-z']+", script)
        words = [(w, round(i / 2.6, 3), round(i / 2.6 + 0.3, 3)) for i, w in enumerate(toks)]
        res = compile_csv(text=csv_text, words=words, duration=words[-1][2] + 0.5, validate=True)
        self.assertEqual(res.report.errors, [])
        self.assertEqual(res.report.warnings, [], "no layer is cut short by its item ending")
        kinds = [e["type"] for e in res.spec["events"]]
        self.assertGreaterEqual(kinds.count("media_full"), 2)           # footage
        self.assertGreaterEqual(kinds.count("pip"), 2)                  # photo cards
        foot = [e for e in res.spec["events"] if e["type"] == "media_full"]
        self.assertTrue(all(e.get("cover_ui") and e.get("fit") == "slow" for e in foot))
        ends = sorted((e["t_in"], e["t_out"]) for e in foot)
        self.assertTrue(all(a[1] <= b[0] + 1e-6 for a, b in zip(ends, ends[1:])), "footage clips never overlap")

    def test_the_rules_that_matter_are_in_the_prompt(self):
        t = PROMPT.read_text(encoding="utf-8")
        for needle in ("frame=globe", "offset_s=1.4", "can NEVER outlive its item", "NEVER type the number itself", "never use a coordinate for a camera",
                       "stock_video:", "cover_ui", "Never use Flow", "44 characters"):
            self.assertIn(needle, t)


if __name__ == "__main__":
    unittest.main()
