"""The AI scene-writer: its answer is checked and clamped, a bad answer falls back to the rules, footage items are resolved from a (fake) stock search,
and a film planned with them uses the clips, the scenes and 3D shots where a clip is missing."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from product_trailer import footage, llm_director, review, studio

SCRIPT = ("Samsung says the battery got a certification in India.\nThe phone has a bigger battery than last year.\n"
          "A tipster says charging is faster.\nPeople will hold it in one hand.\nThe frame is thin.\n")
GOOD = json.dumps({"scenes": [
    {"line": 1, "type": "doc", "chip": "BIS CERTIFICATION", "title": "Battery listing", "highlight": 9},
    {"line": 2, "type": "phones", "title": "Battery", "phones": [{"label": "Before", "color": "purple", "cams": 9, "text": "5000mAh"},
                                                                {"label": "Now", "color": "#2b2b2e", "badge": "+700mAh", "cutaway": True, "cell": 4}]},
    {"line": 3, "type": "tweet", "author": "A tipster", "text": "Charging is faster.", "highlight": "faster"},
    {"line": 4, "type": "footage", "query": "hand holding white smartphone"},
    {"line": 4, "type": "xray"}, {"line": 99, "type": "xray"}, {"line": 5, "type": "banana"},
    {"line": 5, "type": "macro", "move": "nonsense", "text": "Frame"}]})


class Llm(unittest.TestCase):
    def setUp(self):
        self.parsed = review.parse_script(SCRIPT)

    def test_reply_is_checked_and_clamped(self):
        got = llm_director.parse_reply("sure!\n" + GOOD + "\nbye", 5)
        self.assertEqual(sorted(got), [1, 2, 3, 4, 5])              # duplicates, out-of-range lines and unknown types are dropped
        self.assertEqual(got[1]["layer"]["highlight"], 6)
        ph = got[2]["layer"]["phones"]
        self.assertEqual(ph[0]["cams"], 4)
        self.assertEqual(ph[1]["cell"], 1.0)
        self.assertEqual(got[5]["move"], "island")
        self.assertEqual(got[4]["kind"], "footage")

    def test_names_the_narration_did_not_give_are_removed(self):
        lines = [i["text"] for c in self.parsed["chapters"] for i in c["items"] if i["kind"] == "line"]
        reply = json.dumps({"scenes": [{"line": 3, "type": "tweet", "author": "Tech Leaker", "handle": "@techleaks", "text": "x faster"},
                                       {"line": 1, "type": "doc", "chip": "FCC CERTIFICATION", "title": "t"}]})
        got = llm_director.parse_reply(reply, 5, lines)
        self.assertEqual((got[3]["author"], got[3]["handle"]), ("As reported", ""))
        self.assertEqual(got[1]["layer"]["chip"], "CERTIFICATION")

    def test_unreadable_answers_return_none(self):
        for bad in ("", "no json here", '{"scenes": "x"}', '{"scenes": [{"line": 1, "type": "banana"}]}'):
            self.assertIsNone(llm_director.parse_reply(bad, 5))

    def test_direct_inserts_scenes_before_their_lines_and_falls_back(self):
        out = llm_director.llm_direct(self.parsed, "galaxy s27 ultra", lambda s, u: GOOD, lambda m: None)
        kinds = [i["kind"] for c in out["chapters"] for i in c["items"]]
        self.assertEqual(kinds[:2], ["scene", "line"])
        self.assertEqual(kinds.count("line"), 5)
        def boom(s, u):
            raise RuntimeError("no key")
        self.assertIsNone(llm_director.llm_direct(self.parsed, "x", boom, lambda m: None))
        self.assertIsNone(llm_director.llm_direct(self.parsed, "x", lambda s, u: "garbage", lambda m: None))


class Footage(unittest.TestCase):
    def test_resolve_and_plan(self):
        cand = SimpleNamespace(provider="pexels", asset_id="7", duration=9.0, width=1920, height=1080)

        class B:
            def search(self, q, kind, n):
                return [cand] if "hand" in q else []
        def dl(c, d, n, log=print):
            p = Path(d) / f"{n}.mp4"
            p.write_bytes(b"not a real video")
            return p
        with tempfile.TemporaryDirectory() as d:
            parsed = llm_director.llm_direct(review.parse_script(SCRIPT), "galaxy s27 ultra", lambda s, u: GOOD, lambda m: None)
            self.assertEqual(footage.resolve_footage(parsed, d, {}, lambda m: None, backends=[B()], download=dl), {"found": 1, "missing": 0})
            r = studio.plan_film("Review", out_dir=d, script=SCRIPT, phone="galaxy s27 ultra", llm_run=lambda s, u: GOOD, stock_settings=None, log=lambda m: None)
            spec = json.loads(Path(r["spec_path"]).read_text())
        self.assertTrue({"pt_doc", "pt_flatphones", "pt_tweet"} <= {L["type"] for L in spec["layers"]})
        self.assertTrue([n for n in spec["whatif"]["notes"] if "no footage" in n], "an unresolved footage line falls back to a 3D shot and says so")


if __name__ == "__main__":
    unittest.main()
