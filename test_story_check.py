import json, csv, unittest
from pathlib import Path
import story_check as sc

HRT = Path("/Users/muhammadnabil/Downloads/video_generator-main/out/story/hrt_dense.csv")

class T(unittest.TestCase):
    def test_empty_and_missing_columns(self):
        self.assertFalse(sc.check_csv([])["ok"])
        r = sc.check_csv([{"scene_number": 1, "script_segment": "a b c d e"}]); self.assertFalse(r["ok"]); self.assertIn("prompt", r["text"])

    def test_flags(self):
        p = "Vintage engraved sepia paper collage of a warehouse with loading docks and a red dot, torn parchment"
        rows = [{"scene_number": 1, "script_segment": "one two", "prompt": p, "asset_type": "image"},
                {"scene_number": 2, "script_segment": "this one is fine and long enough to show a picture", "prompt": p, "asset_type": "reuse"},
                {"scene_number": 3, "script_segment": " ".join(["w"] * 30), "prompt": "short", "asset_type": "image"},
                {"scene_number": 4, "script_segment": "", "prompt": p + " different", "asset_type": "image"}]
        r = sc.check_csv(rows); t = r["text"]
        self.assertFalse(r["ok"])                       # row 4 has no words
        for s in ("Row 1: only 2", "Row 2: the same prompt", "'reuse'", "Row 3: 30 words", "Row 3: the picture prompt is very short", "Row 4"): self.assertIn(s, t)

    def test_hrt_dense_csv_passes_offline(self):
        if not HRT.is_file(): self.skipTest("hrt_dense.csv not present")
        rows = list(csv.DictReader(open(HRT, encoding="utf-8"))); r = sc.check_csv(rows)
        self.assertTrue(r["ok"], r["text"]); self.assertEqual(r["stats"]["rows"], len(rows))

    def test_with_words(self):
        rows = [{"scene_number": str(i + 1), "script_segment": s, "prompt": "Engraved sepia paper collage illustration number %d with a warehouse and a delivery van and torn parchment edges" % i, "asset_type": "image"}
                for i, s in enumerate(["the first sentence is read right here", "and the second one follows it quite closely", "then a third sentence ends the story today"])]
        words = []; t = 0.0
        for row in rows:
            for w in row["script_segment"].split(): words.append([w, t, t + 0.3]); t += 0.4
        r = sc.check_csv(rows, words); self.assertTrue(r["ok"], r["text"]); self.assertIn("Plan:", r["text"]); self.assertGreaterEqual(r["stats"]["shots"], 3)

if __name__ == "__main__": unittest.main()
