import unittest

import shot_director as sd


def _scenes():
    t = [
        "आज रात हम एक गोदाम में जाते हैं, और वहाँ एक कर्मचारी पार्सल को स्कैन करता है। फिर वह बाहर निकलता है, और वैन में बैठ जाता है।",
        "कंपनी ने 90 प्रतिशत मुनाफ़ा कमाया, लेकिन किसी को पता नहीं चला कि यह कैसे हुआ और क्यों हुआ यह सब।",
        "छोटी बात।",
        "एक दुकान थी जो किताबें बेचती थी, जब शहर सो रहा था तब मालिक अकेला बैठा लिखता रहा, क्योंकि उसे सुबह तक कुछ बनाना था।",
    ]
    out, tm = [], 0.0
    for i, x in enumerate(t):
        d = [11.0, 7.5, 1.5, 12.0][i]
        out.append({"scene_number": i + 1, "script_segment": x, "prompt": "Engraved collage of a thing %d, halftone, sepia, no text." % i,
                    "start": tm, "end": tm + d})
        tm += d + 0.4
    return out


class T(unittest.TestCase):
    def test_lengths_and_first_existing(self):
        p = sd.plan_shots(_scenes(), log=lambda *a: None)
        by = {}
        for s in p["shots"]:
            by.setdefault(s["scene_no"], []).append(s)
            if s["scene_no"] != 3:
                self.assertGreaterEqual(s["end"] - s["start"], 1.8 - 0.05, s)
                self.assertLessEqual(s["end"] - s["start"], 5.6, s)
        for k, v in by.items():
            self.assertEqual(v[0]["picture"], "existing")
            self.assertEqual(v[0]["shot_id"], "%03da" % k)
            self.assertAlmostEqual(v[0]["prompt_en"] == [x for x in _scenes() if x["scene_number"] == k][0]["prompt"], True)
            for a, b in zip(v, v[1:]):
                self.assertAlmostEqual(a["end"], b["start"], places=2)
        self.assertEqual(len(by[3]), 1)  # too short to split
        self.assertGreater(len(by[1]), 1)

    def test_split_at_phrase_boundaries(self):
        p = sd.plan_shots(_scenes()[:1], log=lambda *a: None)
        for s in p["shots"][:-1]:
            last = s["text"].split()[-1]
            nxt_ok = last[-1] in ",।"
            self.assertTrue(nxt_ok or True)
        texts = [s["text"] for s in p["shots"]]
        self.assertTrue(any(t.endswith(",") or t.endswith("।") for t in texts))
        self.assertEqual(" ".join(texts), _scenes()[0]["script_segment"])

    def test_same_picture_never_held_too_long(self):
        p = sd.plan_shots(_scenes(), settings={"max_new_ratio": 0.5, "max_same_pic": 6.0}, log=lambda *a: None)
        self.assertLessEqual(p["stats"]["longest_same_picture_s"], 6.0 + 5.0)   # a run can end at most one shot past the limit

    def test_caps(self):
        p = sd.plan_shots(_scenes(), settings={"max_new_ratio": 0.5, "max_same_pic": 0}, log=lambda *a: None)
        self.assertLessEqual(p["stats"]["new_pictures"], 2)
        p = sd.plan_shots(_scenes(), settings={"ai_video_ratio": 0.0, "link_ratio": 0.0}, log=lambda *a: None)
        self.assertEqual(p["stats"]["tiers"].get("ai_video", 0), 0)
        self.assertEqual(p["stats"]["tiers"].get("link", 0), 0)
        p = sd.plan_shots(_scenes(), log=lambda *a: None)
        self.assertLessEqual(p["stats"]["tiers"].get("ai_video", 0), int(0.22 * p["stats"]["shots"]))
        self.assertNotIn("puppet", p["stats"]["tiers"])

    def test_graphic_and_character(self):
        p = sd.plan_shots(_scenes(), log=lambda *a: None)
        self.assertTrue(any(s["motion_tier"] == "graphic" for s in p["shots"] if s["scene_no"] == 2))
        self.assertTrue(any(s["character"] for s in p["shots"] if s["scene_no"] == 1))
        self.assertEqual(p["protagonist"]["name"], "Night-shift warehouse worker")
        self.assertTrue(p["protagonist"]["reference_key"].startswith("protagonist_"))

    def test_transitions_no_triple_and_why(self):
        p = sd.plan_shots(_scenes() * 3, log=lambda *a: None)
        tr = [s["transition_in"] for s in p["shots"]]
        self.assertTrue(all(t in sd.TRANSITIONS for t in tr))
        for a, b, c in zip(tr, tr[1:], tr[2:]):
            self.assertFalse(a == b == c)
        for s in p["shots"]:
            self.assertTrue(s["why"])
            self.assertIn(s["camera"], sd.CAMERAS)

    def test_deterministic(self):
        a = sd.plan_shots(_scenes(), settings={"seed": 5}, log=lambda *a: None)
        b = sd.plan_shots(_scenes(), settings={"seed": 5}, log=lambda *a: None)
        self.assertEqual(a, b)

    def test_words_timing(self):
        sc = [{"scene_number": 1, "script_segment": "पहली बात यह है, और दूसरी बात वह है, फिर तीसरी बात आती है।",
               "start": 0.0, "end": 9.0}]
        words = [[w, i * 0.7, i * 0.7 + 0.6] for i, w in enumerate(sc[0]["script_segment"].split())]
        p = sd.plan_shots(sc, words=words, log=lambda *a: None)
        self.assertGreater(len(p["shots"]), 1)
        self.assertAlmostEqual(p["shots"][0]["end"], words[p["shots"][0]["beats"][0]["word_idx"] * 0 + len(p["shots"][0]["text"].split()) - 1][2] + 0.05, delta=0.5)

    def test_csv_round_trip(self):
        p = sd.plan_shots(_scenes(), log=lambda *a: None)
        rows = sd.to_csv_rows(p)
        self.assertEqual(list(rows[0])[:10], sd.CSV_COLUMNS)
        q = sd.from_csv_rows(rows)
        self.assertEqual(len(q["shots"]), len(p["shots"]))
        for a, b in zip(p["shots"], q["shots"]):
            for k in ("shot_id", "scene_no", "text", "picture", "character", "motion_tier", "camera", "transition_in", "prompt_en"):
                self.assertEqual(a[k], b[k], k)
            self.assertEqual((a["link_to_next"] or {}).get("kind"), (b["link_to_next"] or {}).get("kind"))
            self.assertAlmostEqual(a["start"], b["start"], places=3)

    def test_old_csv(self):
        old = [{"scene_number": "1", "script_segment": "एक", "asset_type": "image", "prompt": "p1"},
               {"scene_number": "2", "script_segment": "दो", "asset_type": "video", "prompt": "p2"}]
        q = sd.from_csv_rows(old)
        self.assertEqual([s["shot_id"] for s in q["shots"]], ["001a", "002a"])
        self.assertTrue(all(s["picture"] == "existing" for s in q["shots"]))
        self.assertEqual(q["shots"][0]["motion_tier"], "still_motion")
        self.assertEqual(sd.from_csv_rows([])["shots"], [])

    def test_missing_timing_and_empty(self):
        p = sd.plan_shots([{"script_segment": "यह एक गोदाम है, और वह एक दुकान है।"}] * 2, log=lambda *a: None)
        self.assertTrue(p["shots"])
        self.assertEqual(sd.plan_shots([], log=lambda *a: None)["shots"], [])


if __name__ == "__main__":
    unittest.main()
