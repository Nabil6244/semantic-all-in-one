"""Rep Theory's "Copy the CSV prompt": its own example loads through the real scenes-file reader, untimed rows align to the voiceover's word times,
the script goes in place of the placeholder, and the prompt file is bundled."""
from __future__ import annotations
import csv, io, re, tempfile, unittest
from pathlib import Path

from app_csv_prompts import SCRIPT_PLACEHOLDER
from health_cinema import scenes_csv
from reptheory import app_section as A, packaging

ROOT = Path(__file__).resolve().parent

def _example():
    text = A.prompt_text()
    script = re.search(r"Script:\n(.*?)\n\nCSV:", text, re.S).group(1).strip()
    csv_text = re.search(r"CSV:\n(.*?)\n\nSCRIPT", text, re.S).group(1).strip()
    return text, script, csv_text

def _read(csv_text):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f: f.write(csv_text)
    return A.read_scenes_file(f.name)

class RepTheoryCsvPrompt(unittest.TestCase):
    def test_example_loads_untimed_and_rebuilds_the_script(self):
        text, script, csv_text = _example()
        rows = _read(csv_text)
        self.assertEqual(" ".join(r["text"] for r in rows), script)
        self.assertTrue(all("start" not in r for r in rows))
        self.assertEqual([r["chapter"] for r in rows], ["Grip strength", "", "The hang"])
        self.assertTrue(text.rstrip().endswith(SCRIPT_PLACEHOLDER))

    def test_untimed_rows_take_the_voiceover_word_times(self):
        _text, script, csv_text = _example()
        words = [(w, 0.4 * i, 0.4 * i + 0.3) for i, w in enumerate(script.split())]
        rows, frac = scenes_csv.align_to_words(_read(csv_text), words, words[-1][2] + 0.5)
        self.assertGreater(frac, 0.95)
        self.assertEqual([r["chapter"] for r in rows], ["Grip strength", "", "The hang"])
        self.assertTrue(all(r["end"] > r["start"] for r in rows)); self.assertEqual(rows[0]["start"], 0.0)

    def test_timed_csv_unchanged_and_half_timed_refused(self):
        rows = _read("text,start,end\nOne.,0,1.5\nTwo.,1.5,3\n")
        self.assertEqual([(r["start"], r["end"]) for r in rows], [(0.0, 1.5), (1.5, 3.0)])
        with self.assertRaises(ValueError): _read("text,start,end\nOne.,,\nTwo.,1.5,3\n")
        with self.assertRaises(ValueError): _read("chapter\nx\n")

    def test_script_replaces_the_placeholder(self):
        text = A.prompt_text("Hang from the bar.")
        self.assertNotIn(SCRIPT_PLACEHOLDER, text); self.assertTrue(text.rstrip().endswith("Hang from the bar."))

    def test_prompt_file_is_bundled(self):
        self.assertEqual(packaging.prompt_files(ROOT), [(str(ROOT / "reptheory" / n), "reptheory") for n in ("scenes_csv_prompt.txt", "full_guide_prompt.txt")])
        self.assertIn("datas += reptheory_prompt_files(ROOT)", (ROOT / "VideoGenerator.spec").read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
