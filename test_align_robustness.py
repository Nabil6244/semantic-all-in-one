"""align_rows robustness: inflection mismatches and far-away duplicate words.

Regression for a real narration (lighthouse history, 24 scenes, Whisper base): Whisper heard
"towers" where scene 2's script says "tower"; the forward search then matched scene 9's
"stone tower" ~90 words later, the rest of scene 2's words were not found after that point,
the anchor was rejected and scene 2 was interpolated (confidence 0) with its cut at 3.82 s
while scene 1 was still speaking (true start ~5.85 s).
"""
import unittest

from video_generator import _align_words_match, align_rows, split_words

# Whisper base word timestamps of the real narration, up to the end of scene 9 (word@start-end).
_REAL_WORDS = """
for@0-0.14 more@0.14-0.34 than@0.34-0.58 2@0.58-0.9 0@0.9-1.3 years@1.3-1.76 lighthousees@2.22-2.82
have@2.82-2.98 guarded@2.98-3.34 the@3.34-3.62 edges@3.62-3.82 of@3.82-4.06 the@4.06-4.2 sea@4.2-4.52
the@5.6-5.92 most@5.92-6.18 famous@6.18-6.6 early@6.6-7.04 towers@7.04-7.42 stood@7.42-7.72 on@7.72-7.9
the@7.9-8.06 island@8.06-8.38 of@8.38-8.62 pharaohs@8.62-9.26 near@9.5-9.7 alexandria@9.7-10.16 and@10.16-10.8
egypt@10.8-11.24 built@12.28-12.78 around@12.78-13.08 280@13.08-13.82 bc@13.82-14.38 it@14.8-14.9
rose@14.9-15.08 more@15.08-15.38 than@15.38-15.56 100@15.56-16.18 meters@16.18-16.62 above@16.62-16.94
the@16.94-17.18 harbor@17.18-17.46 sailors@18.92-19.3 could@19.3-19.48 see@19.48-19.72 its@19.72-19.92
fire@19.92-20.22 from@20.22-20.5 almost@20.5-20.8 50@20.8-21.38 kilometers@21.38-22 away@22-22.36
on@22.36-22.58 a@22.58-22.68 clear@22.68-22.94 night@22.94-23.32 after@24.16-24.92 the@24.92-25.14
romans@25.14-25.48 lighthouse@26.02-26.28 buildings@26.28-26.84 slowed@26.84-27.22 for@27.22-27.46
nearly@27.46-27.72 a@27.72-28 thousand@28-28.36 years@28.36-29.02 medieval@30.1-30.66 ports@30.66-31.06
relied@31.06-31.36 on@31.36-31.68 simple@31.68-32.08 bonfires@32.08-32.72 and@32.72-33.06 lanterns@33.06-33.64
hung@33.64-33.76 from@33.76-34 church@34-34.34 towers@34.34-34.8 everything@35.92-36.68 changed@36.68-37.2
in@37.2-37.32 the@37.32-37.46 18th@37.46-38.04 century@38.04-38.5 when@38.5-39.02 trade@39.02-39.34
across@39.34-39.7 the@39.7-40.04 atlantic@40.04-40.46 exploded@40.46-41.28 ships@42.4-42.9 carried@42.9-43.32
sugar@43.32-43.7 cotton@44.14-44.4 and@44.4-44.64 timber@44.64-44.96 and@45.24-45.48 every@45.48-45.74
wreck@45.74-45.96 cost@45.96-46.38 a@46.38-46.52 fortune@46.52-47 in@48-48.42 1759@48.42-49.74
john@50.28-50.46 smeaton@50.46-50.9 finished@50.9-51.42 a@51.42-51.56 stone@51.56-51.88 tower@51.88-52.24
on@52.24-52.44 the@52.44-52.58 deadly@52.58-52.9 eddie@52.9-53.2 stone@53.2-53.54 rocks@53.54-54.02
"""

_REAL_SCENES = [
    "For more than two thousand years, lighthouses have guarded the edges of the sea.",
    "The most famous early tower stood on the island of Pharos, near Alexandria in Egypt.",
    "Built around 280 BC, it rose more than one hundred meters above the harbor.",
    "Sailors could see its fire from almost fifty kilometers away on a clear night.",
    "After the Romans, lighthouse building slowed for nearly a thousand years.",
    "Medieval ports relied on simple bonfires and lanterns hung from church towers.",
    "Everything changed in the eighteenth century, when trade across the Atlantic exploded.",
    "Ships carried sugar, cotton and timber, and every wreck cost a fortune.",
    "In 1759, John Smeaton finished a stone tower on the deadly Eddystone Rocks.",
]


def _parse_words(blob):
    out = []
    for item in blob.split():
        word, span = item.split("@")
        start, end = span.split("-")
        out.append((word, float(start), float(end)))
    return out


def _rows(texts):
    return [{"scene_number": str(i + 1), "script_segment": t} for i, t in enumerate(texts)]


def _whisper_from_text(text, t0=0.0, dt=0.4):
    out, t = [], t0
    for w in split_words(text):
        out.append((w, t, t + dt * 0.8))
        t += dt
    return out


class TestRealNarrationRepro(unittest.TestCase):
    def test_scene2_anchors_after_scene1_speech(self):
        results, _ = align_rows(_rows(_REAL_SCENES), _parse_words(_REAL_WORDS))
        s1, s2 = results[0], results[1]
        self.assertGreater(s2["confidence"], 0.0, results[:3])
        self.assertLess(abs(s2["start_time"] - 5.85), 0.3, s2)
        # Scene 1 ends on its last word "sea" (4.52 s), not on "edges" (3.82 s)
        self.assertAlmostEqual(s1["end_time"], 4.52, places=2)
        self.assertLessEqual(s1["end_time"], s2["start_time"])
        self.assertAlmostEqual(s2["end_time"], 11.24, places=2)   # "egypt"
        self.assertTrue(all(r["confidence"] == 1.0 for r in results), results)
        # Scene 9 (the real "stone tower") keeps its own anchor
        self.assertAlmostEqual(results[8]["start_time"], 48.42, places=2)


class TestInflectionMatching(unittest.TestCase):
    def test_simple_inflections_match(self):
        for a, b in [("tower", "towers"), ("harbors", "harbor"), ("walked", "walk"),
                     ("building", "build"), ("lighthouses", "lighthousees"), ("matches", "match"),
                     ("trained", "trains")]:
            self.assertTrue(_align_words_match(a, b), (a, b))
            self.assertTrue(_align_words_match(b, a), (b, a))

    def test_unrelated_and_short_words_do_not_match(self):
        for a, b in [("snow", "plow"), ("cars", "card"), ("used", "uses"), ("tower", "power"),
                     ("pharos", "pharaohs"), ("25", "250")]:
            self.assertFalse(_align_words_match(a, b), (a, b))
        self.assertTrue(_align_words_match("twenty", "20"))   # number equivalence kept

    def test_plural_in_transcript_anchors_row(self):
        rows = _rows([
            "Harbor pilots guided every vessel home.",
            "Each keeper climbed the tower nightly.",
            "Storm warnings reached distant villages quickly.",
        ])
        whisper = _whisper_from_text(
            "harbor pilots guided every vessel home "
            "each keepers climbed the towers nightly "
            "storm warning reached distant village quickly")
        results, _ = align_rows(rows, whisper)
        self.assertEqual([r["confidence"] for r in results], [1.0, 1.0, 1.0], results)
        self.assertAlmostEqual(results[1]["start_time"], 6 * 0.4, places=6)   # "each"
        self.assertAlmostEqual(results[2]["start_time"], 12 * 0.4, places=6)


class TestFarDuplicateGuard(unittest.TestCase):
    def test_far_duplicate_cannot_pull_anchor(self):
        """A word Whisper misheard ("power" for "tower") must not anchor on a later scene's "tower"."""
        filler = " ".join(f"filler{n}" for n in range(60))
        rows = _rows([
            "Lighthouses guarded rocky coastlines.",
            "The famous tower stood on the island near Alexandria.",
            filler,
            "Smeaton finished a stone tower offshore.",
        ])
        whisper = _whisper_from_text(
            "lighthouses guarded rocky coastlines "
            "the famous power stood on the island near alexandria "
            + filler + " smeaton finished a stone tower offshore")
        results, _ = align_rows(rows, whisper)
        self.assertEqual([r["confidence"] for r in results], [1.0, 1.0, 1.0, 1.0], results)
        self.assertAlmostEqual(results[1]["start_time"], 5 * 0.4, places=6)          # "famous"
        self.assertAlmostEqual(results[1]["end_time"], 12 * 0.4 + 0.32, places=6)    # "alexandria"
        self.assertAlmostEqual(results[3]["start_time"], 73 * 0.4, places=6)         # "smeaton"


if __name__ == "__main__":
    unittest.main()
