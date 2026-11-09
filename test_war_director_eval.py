"""War Footage Director Stage 0: the evaluation set and its scorer (cinematic_explainer/war/director_eval.py). Offline."""

import json
import sys
import unittest

from cinematic_explainer.war import director_eval as E


def _clip(vid, start=10.0, **kw):
    c = {"video_id": vid, "clip_start": start, "clip_end": start + 8.0, "title": "", "channel": "", "frame_flags": [], "tile_hashes": []}
    c.update(kw)
    return c


def _report(render, scenes):
    return {"version": 1, "render": render, "scenes": [{"scene": no, "decision": d, "clip": c} for no, d, c in scenes]}


class EvalSetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ev = E.load_eval()

    def test_both_renders_every_scene(self):
        self.assertEqual(len(self.ev["renders"]["038"]["scenes"]), 23)
        self.assertEqual(len(self.ev["renders"]["033"]["scenes"]), 25)
        self.assertEqual(len(self.ev["renders"]["040"]["scenes"]), 18)

    def test_labels_are_well_formed(self):
        types = set(self.ev["types"])
        for rid, r in self.ev["renders"].items():
            nos = [s["scene"] for s in r["scenes"]]
            self.assertEqual(len(nos), len(set(nos)), rid)
            for s in r["scenes"]:
                self.assertTrue(s["text"].strip(), (rid, s["scene"]))
                self.assertTrue(s["types"] and set(s["types"]) <= types, (rid, s["scene"], s["types"]))
                if s["footage_wanted"]:
                    self.assertTrue(s["key_terms"], (rid, s["scene"]))
                for j in s["judged"]:
                    self.assertIn(j["verdict"], ("match", "partial", "generic", "wrong"))
                self.assertFalse(set(s["likely_ok"]) & set(s["bad_ids"]), (rid, s["scene"]))

    def test_broken_csv_row_keeps_its_narration(self):
        s13 = next(s for s in self.ev["renders"]["038"]["scenes"] if s["scene"] == "013")
        self.assertTrue(s13["text"].startswith("Second, Russians are feeling it"))
        self.assertTrue(s13["csv_row_broken"])

    def test_claims_and_questions_want_no_footage(self):
        for r in self.ev["renders"].values():
            for s in r["scenes"]:
                if set(s["types"]) <= {"CLAIM", "STATISTIC", "QUESTION", "TRANSITION", "ANALYSIS"}:
                    self.assertFalse(s["footage_wanted"], s["text"])


class ScoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ev = E.load_eval()

    def test_judged_clip_keeps_its_verdict_only_near_its_start(self):
        m = E.evaluate(_report("038", [("009", "footage", _clip("hy1hGxnomKI", 246.0))]), self.ev)
        self.assertEqual(m["wrong"], 1)
        m = E.evaluate(_report("038", [("008", "footage", _clip("uQYu8H_g6mY", 10.5)), ("003", "footage", _clip("nlSUJNlcGyQ", 400.0))]), self.ev)
        self.assertEqual((m["match"], m["unjudged"]), (1, 1))      # same video, another moment: not judged

    def test_bad_and_likely_ids(self):
        m = E.evaluate(_report("033", [("018", "footage", _clip("an6qfBicbTI", 300.0)), ("019", "footage", _clip("PRwEadk0nnM"))]), self.ev)
        self.assertEqual((m["wrong"], m["likely_match"]), (1, 1))

    def test_entity_must_be_named_and_not_wrong(self):
        ok = _clip("FqyaMETWWH8", title="Ukrainian drones attacked the Kirishi Oil Refinery")
        bad = _clip("hy1hGxnomKI", 246.0, title="Kirishi Refinery Erupts In Flames")
        self.assertEqual(E.evaluate(_report("038", [("009", "footage", ok)]), self.ev)["entity_named"], 1)
        self.assertEqual(E.evaluate(_report("038", [("009", "footage", bad)]), self.ev)["entity_named"], 0)

    def test_repeats_same_video_and_same_picture_other_url(self):
        same = _report("038", [("001", "footage", _clip("A", 88.5)), ("004", "footage", _clip("A", 90.0)), ("006", "footage", _clip("A", 200.0))])
        self.assertEqual(E.evaluate(same, self.ev)["repeats"], 1)        # 200 s is another moment of the same video
        h = ["0f0f0f0f0f0f0f0f", "00ff00ff00ff00ff", "123456789abcdef0", "fedcba9876543210"]
        near = ["0f0f0f0f0f0f0f0e", "00ff00ff00ff00fe", "aaaaaaaaaaaaaaaa", "5555555555555555"]
        reupload = _report("038", [("003", "footage", _clip("A", tile_hashes=h)), ("017", "footage", _clip("B", tile_hashes=near))])
        self.assertEqual(E.evaluate(reupload, self.ev)["repeats"], 1)
        back = _report("038", [("003", "footage", _clip("A")), ("017", "footage", _clip("A", reused=True))])
        self.assertEqual(E.evaluate(back, self.ev)["repeats"], 0)          # a deliberate return is not a repeat

    def test_footage_on_claim_is_a_graphics_violation_except_its_speaker(self):
        m = E.evaluate(_report("038", [("001", "footage", _clip("X")), ("002", "graphics", {})]), self.ev)
        self.assertEqual(m["graphics_violations"], 1)
        m = E.evaluate(_report("033", [("008", "footage", _clip("Z", title="Zelensky: address to the nation"))]), self.ev)
        self.assertEqual(m["graphics_violations"], 0)

    def test_provenance_authenticity_and_moment(self):
        full = _clip("uQYu8H_g6mY", 10.5, channel="Reuters", upload_date="20260615", authenticity="verified_event", moment_verified=True)
        thin = _clip("hy1hGxnomKI", 246.0, channel="MIRROR NOW", authenticity="unverified")
        m = E.evaluate(_report("038", [("008", "footage", full), ("009", "footage", thin)]), self.ev)
        self.assertEqual((m["provenance_complete"], m["event_unverified"], m["moment_verified"]), (1, 1, 1))

    def test_not_footage_flags_from_frames_count(self):
        m = E.evaluate(_report("038", [("003", "footage", _clip("NEW", frame_flags=["text_screen"]))]), self.ev)
        self.assertEqual(m["not_footage_placed"], 1)

    def test_manifest_adapter(self):
        man = {"001": {"source": "youtube_video", "video_id": "RxZltZjIZeI", "clip_start": 88.5, "clip_duration": 8.0, "status": "complete"},
               "019": {"source": "flow_video", "status": "complete"},
               "022": {"source": "stock_video", "provider_asset_id": "pixabay:188778", "status": "complete"}}
        rep = E.from_manifest(man, "038")
        d = {s["scene"]: s for s in rep["scenes"]}
        self.assertEqual((d["001"]["decision"], d["019"]["decision"]), ("footage", "ai"))
        self.assertEqual(d["001"]["clip"]["clip_end"], 96.5)
        m = E.evaluate(rep, self.ev)
        self.assertEqual((m["generic"], m["placed"]), (2, 2))

    def test_offline_no_network_or_gemini(self):
        src = open(E.__file__, encoding="utf-8").read()
        for word in ("requests", "urllib", "yt_dlp", "gemini", "google"):
            self.assertNotIn(f"import {word}", src)
        self.assertNotIn("providers", src)


if __name__ == "__main__":
    unittest.main()
