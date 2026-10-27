"""Phase D tests: map relation lines (the plan's own `line` layer, kind flow, between two places the narration joins with a relation word). Opt-in (DirectorOptions.maplines), offline,
deterministic, nothing encoded; hybrid/ and pakmap/ are only read.
usage: python3 -B explainer/spike/test_motion_maplines.py   (from the repository root)"""
import hashlib
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True

from test_director_real_material import synth, run, SCRIPT as KOREA_SCRIPT, WORDS as KOREA_WORDS, DUR as KOREA_DUR      # noqa: E402
from explainer.beats import framing as FR                                      # noqa: E402
from explainer.director import DirectorOptions                                 # noqa: E402
from explainer.director import compose_maplines as CM                          # noqa: E402

EVIDENCE = ROOT / "docs" / "explainer" / "phase_motion_evidence"
S = ("The war began quietly. In the spring the army marched from France into Germany along the old roads. The generals said the plan could not fail. Soon the troops crossed from Egypt to Libya in the heat. "
     "Nobody at home knew how far they had gone. The trade ships sailed from Italy to Egypt every month. The harbour was busy and the market was full.")


class Cache:
    _r = {}

    @classmethod
    def plan(cls, script=S, **kw):
        k = (script, tuple(sorted(kw.items())))
        if k not in cls._r:
            w, d = synth(script)
            cls._r[k] = (run(w, script, d, max_map_share=0.6, **kw), w, d)
        return cls._r[k]


def map_lines(plan):
    return [(b["id"], l) for b in plan["beats"] if b["mode"] == "map" for l in b.get("layers", []) if l["type"] == "line"]


def hit(name, a, b):
    return SimpleNamespace(name=name, match={"start": float(a), "word_indices": list(range(a, b + 1))})


def words_of(text):
    return [(w, i * 0.3, i * 0.3 + 0.25) for i, w in enumerate(text.split())]


def sent_of(n):
    return SimpleNamespace(widx=list(range(n)))


class Rule(unittest.TestCase):
    VIEW = (31.0, 28.0, 4.75)          # the view the director chose for Egypt and Libya in the fixture

    def cam(self, view=None):
        return {"view": view or self.VIEW, "ready": {}}

    def test_two_shown_places_joined_by_a_relation_word_give_one_flow_line(self):
        w = words_of("troops crossed from Egypt to Libya in the heat")
        ls, notes = CM.relation_lines([hit("Egypt", 3, 3), hit("Libya", 5, 5)], self.cam(), w, [sent_of(len(w))], {"Egypt": 0.0, "Libya": 0.4})
        self.assertEqual(ls, [{"places": ["Egypt", "Libya"], "kind": "flow", "offset_s": 0.4}])

    def test_no_relation_word_too_far_other_sentence_or_same_place_give_no_line(self):
        w = words_of("Egypt and Libya are both large countries in Africa today")
        self.assertEqual(CM.relation_lines([hit("Egypt", 0, 0), hit("Libya", 2, 2)], self.cam(), w, [sent_of(len(w))], {})[0], [])     # "and" is not a relation
        w = words_of("troops crossed from Egypt after a very long and hard march to Libya")
        self.assertEqual(CM.relation_lines([hit("Egypt", 3, 3), hit("Libya", 12, 12)], self.cam(), w, [sent_of(len(w))], {})[0], [])   # more than four words between
        w = words_of("troops left Egypt. Then they went to Libya")
        two = [SimpleNamespace(widx=[0, 1, 2]), SimpleNamespace(widx=[3, 4, 5, 6, 7])]
        ls, notes = CM.relation_lines([hit("Egypt", 2, 2), hit("Libya", 7, 7)], self.cam(), w, two, {})
        self.assertEqual(ls, [])
        w = words_of("troops moved from Egypt to Egypt")
        self.assertEqual(CM.relation_lines([hit("Egypt", 3, 3), hit("Egypt", 5, 5)], self.cam(), w, [sent_of(len(w))], {})[0], [])

    def test_the_line_needs_a_view_that_holds_both_places(self):
        w = words_of("troops crossed from Egypt to Libya in the heat")
        h = [hit("Egypt", 3, 3), hit("Libya", 5, 5)]
        ls, notes = CM.relation_lines(h, {"view": None, "ready": {}}, w, [sent_of(len(w))], {})
        self.assertEqual(ls, [])
        self.assertTrue(any("no single camera view" in n for n in notes), notes)
        ls, notes = CM.relation_lines(h, self.cam((100.0, 60.0, 8.0)), w, [sent_of(len(w))], {})        # a view far away from both
        self.assertEqual(ls, [])
        self.assertTrue(any("does not hold both" in n for n in notes), notes)


class Director(unittest.TestCase):
    def test_the_line_is_added_between_the_two_places_the_narration_joins(self):
        on, w, _d = Cache.plan(maplines=True)
        self.assertIsNotNone(on.plan, on.problems)
        self.assertEqual(on.problems, [])
        ls = map_lines(on.plan)
        self.assertEqual([(b, l["places"], l["kind"]) for b, l in ls], [("e2", ["Egypt", "Libya"], "flow")])         # France to Germany is not drawn: France is not shown on that map
        self.assertEqual(on.report["hybrid_validate"].get("errors"), [])
        self.assertEqual(FR.check_framing(on.plan), [])                                                              # the framing proof still holds

    def test_the_line_appears_when_the_second_place_is_spoken_and_never_before_both_exist(self):
        on, w, _d = Cache.plan(maplines=True)
        bid, ln = map_lines(on.plan)[0]
        beat = next(b for b in on.plan["beats"] if b["id"] == bid)
        layer_t = {l["place"]: l["t"] for l in beat["layers"] if l["type"] == "fill"}
        egypt = next(x[1] for x in w if x[0] == "egypt")
        libya = next(x[1] for x in w if x[0] == "libya")
        self.assertGreaterEqual(ln["t"], max(egypt, libya) - 1e-6)
        self.assertGreaterEqual(ln["t"], max(layer_t["Egypt"], layer_t["Libya"]) - 1e-6)                             # after both outlines exist
        self.assertLess(ln["t"], beat["end"] - 1.0)

    def test_everything_else_in_the_plan_is_unchanged(self):
        on, _w, _d = Cache.plan(maplines=True)
        off, _w2, _d2 = Cache.plan(maplines=False)
        self.assertEqual(map_lines(off.plan), [])
        # layer ids are numbered in order of creation, so adding the line moves the number of the layers after it (caption4 for caption3): compare everything but those ids
        def strip(p):
            return json.dumps([{k: ([{a: c for a, c in l.items() if a != "id"} for l in v if l["type"] != "line"] if k == "layers" else v) for k, v in b.items()} for b in p["beats"]], sort_keys=True)
        self.assertEqual(strip(on.plan), strip(off.plan))

    def test_off_by_default_and_equal_to_recorded_head(self):
        self.assertIs(DirectorOptions().maplines, False)
        r, _w, _d = Cache.plan(maplines=False)
        self.assertNotIn("maplines", r.report["options"])
        base = json.loads((EVIDENCE / "disabled_path_baseline_HEAD.json").read_text())
        sha = lambda o: hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()
        for look in ("reference", "classic"):
            r = run(KOREA_WORDS, KOREA_SCRIPT, KOREA_DUR, look=look, maplines=False)
            bd = r.report["beat_details"]
            self.assertEqual(sha(r.plan), base[f"korea/{look}"]["plan_sha"], look)
            self.assertEqual(sha(r.report["options"]), base[f"korea/{look}"]["options_sha"], look)

    def test_a_line_only_joins_places_that_have_their_own_layer_on_that_beat(self):
        for r in (Cache.plan(maplines=True)[0], run(KOREA_WORDS, KOREA_SCRIPT, KOREA_DUR, maplines=True)):
            for b in r.plan["beats"]:
                if b["mode"] != "map":
                    continue
                own = {l["place"] for l in b.get("layers", []) if l["type"] in ("fill", "marker")}
                for l in b["layers"]:
                    if l["type"] == "line":
                        self.assertTrue(set(l["places"]) <= own, (b["id"], l["places"], own))

    def test_the_same_plan_twice_is_identical(self):
        w, d = synth(S)
        a, b = run(w, S, d, max_map_share=0.6, maplines=True), run(w, S, d, max_map_share=0.6, maplines=True)
        self.assertEqual(json.dumps(a.plan, sort_keys=True), json.dumps(b.plan, sort_keys=True))

    def test_the_korea_story_gets_no_invented_line(self):
        on = run(KOREA_WORDS, KOREA_SCRIPT, KOREA_DUR, maplines=True)
        off = run(KOREA_WORDS, KOREA_SCRIPT, KOREA_DUR, maplines=False)
        self.assertEqual(json.dumps(on.plan, sort_keys=True), json.dumps(off.plan, sort_keys=True))               # no two relation-joined places there: nothing changes


if __name__ == "__main__":
    unittest.main(verbosity=2)
