"""Wall Moments planner (wall/planner.py) and the Aviation adapter (aviation/wall_moments.py): docs/wall/PLAN.md Phases 2-3.

Scripts: the Lisbon TAP timeline as the app built it (test_fixtures/wall_lisbon_timeline.json, real scene times, shots and layers),
plus two long scripts from the repo split into sentences on an even voice (Rome, Pluto)."""

import csv
import json
import re
import unittest
from pathlib import Path

from aviation import wall_moments as AW
from wall import planner as WP

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "test_fixtures" / "wall_lisbon_timeline.json"


def lisbon():
    fx = json.loads(FIX.read_text(encoding="utf-8"))
    shots = [dict(s, path=f"/clips/{s['name']}") for s in fx["shots"]]
    scenes = [{"scene_no": s["no"], "text": s["text"], "start": s["start"], "end": s["end"]} for s in fx["scenes"]]
    return fx, shots, scenes


def sentences(texts):
    t, sc, sh, words, i = 0.0, [], [], [], 0
    for para in texts:
        for sent in re.split(r"(?<=[.!?])\s+", para.strip()):
            toks = re.findall(r"[A-Za-z0-9’'\-]+", sent)
            if not toks:
                continue
            d = max(1.5, len(toks) / 2.6)
            card = i % 3 != 0
            sc.append({"no": i + 1, "text": sent, "start": round(t, 3), "end": round(t + d, 3), "card": 1.0 if card else 0.0, "keep": False})
            sh.append({"start": round(t, 3), "end": round(t + d, 3), "seek": 0.0, "path": f"/clips/{i}.mp4", "kind": "black" if card else "footage"})
            words += [[w.lower(), round(t + d * k / len(toks), 3), round(t + d * (k + 1) / len(toks), 3)] for k, w in enumerate(toks)]
            t += d
            i += 1
    return sc, sh, words, t


def rome():
    rows = csv.DictReader(open(ROOT / "roblox-cinema-engine" / "samples" / "rome_history.csv", encoding="utf-8"))
    return sentences([r["text"] for r in rows if r["row"] == "beat" and r["text"]])


def pluto():
    return sentences([r["script_segment"] for r in csv.DictReader(open(ROOT / "ai_visual_plan.csv", encoding="utf-8"))])


class BudgetTest(unittest.TestCase):
    def test_lisbon_in_band(self):
        fx, shots, scenes = lisbon()
        ws, wsh, blocks = AW.planner_input(shots, fx["layers"], scenes)
        total = shots[-1]["end"]
        pl = WP.plan(ws, fx["words"], total, wsh, pct=20, blocks=blocks, cues=False)
        self.assertGreaterEqual(pl["share"], 18.0)
        self.assertLessEqual(pl["share"], 22.0)

    def test_rome_in_band(self):
        sc, sh, w, total = rome()
        pl = WP.plan(sc, w, total, sh, pct=20, cues=False)
        self.assertGreaterEqual(pl["share"], 18.0)
        self.assertLessEqual(pl["share"], 22.0)

    def test_number_light_script_never_pads(self):
        """Pluto has few numbers: the wall takes what the narration gives and never goes over the band to make up for it."""
        sc, sh, w, total = pluto()
        pl = WP.plan(sc, w, total, sh, pct=20, cues=False)
        self.assertGreater(pl["share"], 8.0)
        self.assertLessEqual(pl["share"], 22.0)

    def test_never_above_25(self):
        sc, sh, w, total = rome()
        self.assertLessEqual(WP.plan(sc, w, total, sh, pct=30, cues=False)["share"], 25.0)
        self.assertEqual(WP.plan(sc, w, total, sh, pct=0, cues=False)["segments"], [])


class RulesTest(unittest.TestCase):
    def setUp(self):
        self.fx, self.shots, self.scenes = lisbon()
        self.ws, self.wsh, self.blocks = AW.planner_input(self.shots, self.fx["layers"], self.scenes)
        self.total = self.shots[-1]["end"]
        self.pl = WP.plan(self.ws, self.fx["words"], self.total, self.wsh, pct=20, blocks=self.blocks)

    def test_segment_rules(self):
        segs = self.pl["segments"]
        self.assertTrue(segs)
        for s in segs:
            self.assertGreaterEqual(s["end"] - s["start"], WP.MIN_S - 1e-6)
            self.assertLessEqual(s["end"] - s["start"], WP.MAX_S + 1e-6)
            self.assertGreaterEqual(s["start"], WP.NO_WALL_BEFORE_S)
            self.assertNotIn(self.scenes[-1]["scene_no"], s["scenes"])
        for a, b in zip(segs, segs[1:]):
            self.assertGreaterEqual(b["start"] - a["end"], WP.MIN_GAP_S - 1e-6)

    def test_maps_and_must_stay_scenes_untouched(self):
        keep = [(s["start"], s["end"]) for s in self.ws if s["keep"]]
        self.assertTrue(keep)
        for s in self.pl["segments"]:
            for a, b in keep:
                self.assertLessEqual(min(s["end"], b) - max(s["start"], a), 1e-6, (s["start"], s["end"], a, b))
            for a, b in self.blocks:                                  # never cuts through a card, stage or map
                self.assertFalse(a + 0.05 < s["start"] < b - 0.05 or a + 0.05 < s["end"] < b - 0.05)

    def test_never_opens_or_closes_on_real_footage(self):
        by_no = {s["no"]: s for s in self.ws}
        for s in self.pl["segments"]:
            for no in (s["scenes"][0], s["scenes"][-1]):
                self.assertLessEqual(WP._strong_share(self.wsh, by_no[no]), 0.5)

    def test_deterministic(self):
        again = WP.plan(self.ws, self.fx["words"], self.total, self.wsh, pct=20, blocks=self.blocks)
        self.assertEqual(json.dumps(self.pl, sort_keys=True, default=list), json.dumps(again, sort_keys=True, default=list))

    def test_entry_and_exit_hand_off_full_screen(self):
        for s in self.pl["segments"]:
            cam, p = s["params"]["cam"], s["params"]
            ids = {i.get("id") for i in p["items"]}
            if "entry" in ids:
                self.assertEqual((cam[0]["t"], cam[0].get("fs"), cam[0].get("edge")), (0.0, "entry", True))
            if "exit" in ids:
                self.assertEqual((cam[-1].get("fs"), cam[-1].get("edge")), ("exit", True))
                self.assertAlmostEqual(cam[-1]["t"], p["dur"], places=3)
                ex = next(i for i in p["items"] if i.get("id") == "exit")
                nxt = WP._shot_at(self.wsh, s["end"] + 0.02)                                                    # may end mid-shot
                self.assertAlmostEqual(ex["clip"]["seek"] + (p["dur"] - ex["clip"]["t0"]), nxt["seek"] + (s["end"] - nxt["start"]), places=2)

    def test_opening_moment_items_land_on_words(self):
        seg = next(s for s in self.pl["segments"] if s["start"] < 40)
        ctrs = [i for i in seg["params"]["items"] if i["type"] == "counter"]
        self.assertEqual([c["fmt"]["suf"] for c in ctrs], [" BN", "%"])
        self.assertAlmostEqual(seg["start"] + ctrs[0]["t_land"], 10.4, delta=0.15)   # "billion" is spoken at 10.3 s
        self.assertAlmostEqual(seg["start"] + ctrs[1]["t_land"], 12.3, delta=0.15)   # "44 ... 9": the 9 at 12.2 s
        kinds = [i["type"] for i in seg["params"]["items"]]
        self.assertIn("pen", kinds)                                                   # "percent of TAP"
        self.assertIn("note", kinds)                                                  # "about 1.2 billion"


class AdapterTest(unittest.TestCase):
    def test_wall_replaces_cards_only_inside_moments(self):
        from cinematic_explainer.render import Layer, Shot
        fx, shots, scenes = lisbon()
        S = [Shot(s["path"], s["start"], s["end"], s["seek"]) for s in shots]
        L = [Layer(l["kind"], l["start"], l["end"], {}) for l in fx["layers"]]
        out, rep = AW.apply(S, L, scenes, fx["words"], pct=20)
        spans = rep["spans"]
        self.assertTrue(spans)
        walls = [ly for ly in out if ly.kind == "wall.lay_wall"]
        self.assertEqual([(w.start, w.end) for w in walls], spans)
        for ly in out:
            if ly.kind == "wall.lay_wall":
                continue
            for a, b in spans:
                self.assertLessEqual(min(ly.end, b) - max(ly.start, a), 1e-6, (ly.kind, ly.start, ly.end))
        outside = [(l.kind, l.start, l.end) for l in L if not any(min(l.end, b) - max(l.start, a) > 1e-6 for a, b in spans)]
        kept = [(l.kind, l.start, l.end) for l in out if l.kind != "wall.lay_wall"]
        for k in outside:
            self.assertIn(k, kept)
        self.assertTrue(all(a <= t <= b for t, _n in rep["cues"] for a, b in [next(sp for sp in spans if sp[0] <= t <= sp[1] + 1e-6)]))

    def test_sound_cues_join_the_mix_events(self):
        from aviation import sound as SD
        evs = [{"t": 30.0, "file": "x", "gain_db": -20, "kind": "whoosh"}, {"t": 200.0, "file": "x", "gain_db": -20, "kind": "whoosh"}]
        out = SD.with_wall(evs, [(25.0, 35.0)], [(26.0, "stamp"), (26.1, "pop"), (27.0, "ticks:1.2")])
        ts = [(e["t"], Path(e["file"]).name) for e in out]
        self.assertIn((200.0, "x"), ts)
        self.assertNotIn((30.0, "x"), ts)                      # the card's sound left with the card
        self.assertIn((26.0, "stamp.wav"), ts)
        self.assertNotIn((26.1, "pop.wav"), ts)               # MIN_GAP: the stronger stamp keeps its slot
        self.assertIn((27.0, "ticks_10.wav"), ts)


if __name__ == "__main__":
    unittest.main()
