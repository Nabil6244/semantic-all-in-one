"""The progression chain (reptheory/chain.py), the section-aware director (variety.section_kind) and the CSV `section` / `graphic` columns: plan-level, any topic."""
from __future__ import annotations
import unittest

from reptheory import chain as CH, direction as DR, variety as V, draw as D, scenes as S

def _sc(text, no, s0, s1, section="", **kw):
    ws = [{"w": w, "t0": s0 + 0.3 * i} for i, w in enumerate(text.split())]
    return dict({"no": no, "kind": "callout", "start": s0, "end": s1, "words": ws, "text": text, "pages": [], "decisions": [], "art": "", "section": section, "topic": ""}, **kw)

def _units(word="MOVE", names=("GLUTE BRIDGE", "BIRD DOG", "DEAD BUG", "SIDE PLANK")):
    scs, t = [_sc("Four moves fix most back pain.", 1, 0, 4)], 4.0
    for i, nm in enumerate(names, 1):
        scs.append(_sc(f"{word.title()} {i}, the {nm.lower()}. Hold it for thirty seconds.", len(scs) + 1, t, t + 5, section=f"{word} {i} · {nm}")); t += 5
    scs.append(_sc("Comment your number below and train like it's day one.", len(scs) + 1, t, t + 5)); return scs

class Chain(unittest.TestCase):
    def test_units_become_a_chain_at_every_unit_and_the_end(self):
        scs = _units(); self.assertEqual(CH.plan(scs), 5)
        ch = scs[2]["chain"]; self.assertEqual(ch["current"], 1); self.assertEqual([i["name"] for i in ch["items"]], ["GLUTE BRIDGE", "BIRD DOG", "DEAD BUG", "SIDE PLANK"])
        self.assertEqual(ch["items"][0]["target"], "30 S"); self.assertTrue(scs[-1]["chain"].get("done"))

    def test_numbering_follows_the_script(self):
        scs = _units("RULE")
        for k, sc in enumerate(scs[1:5]): sc["section"] = f"RULE {k + 2} · X{k}"
        CH.plan(scs); self.assertEqual(scs[1]["chain"]["items"][0].get("n"), 2)

    def test_no_units_no_chain(self):
        scs = [_sc("Sleep is when you grow.", 1, 0, 4), _sc("Eat enough protein.", 2, 4, 8)]; self.assertEqual(CH.plan(scs), 0)

    def test_chain_draws(self):
        scs = _units(); CH.plan(scs); ctx = D.Ctx(640, 360); a = S.frame(ctx, dict(scs[2], chain=None), 0.8, tag=False); b = S.frame(ctx, scs[2], 0.8, tag=False); self.assertNotEqual(a.tobytes(), b.tobytes())

class Sections(unittest.TestCase):
    def test_section_kind_by_sentence_and_unit(self):
        self.assertEqual(V.section_kind(_sc("That's why skinny guys have the edge.", 1, 0, 3)), "why")
        self.assertEqual(V.section_kind(_sc("If your wrist hurts, stop.", 1, 0, 3)), "warning")
        self.assertEqual(V.section_kind(_sc("Train four days a week.", 1, 0, 3)), "plan")
        self.assertEqual(V.section_kind(_sc("Squeeze your glutes.", 1, 0, 3, section="LINK 1 · THE PLANK")), "howto")
        self.assertEqual(V.section_kind(_sc("Squeeze your glutes.", 1, 0, 3, section_csv="why")), "why")

class CsvGraphic(unittest.TestCase):
    def test_chain_from_the_graphic_column(self):
        script = "Link one the plank. Link two the lean. Link three frog stand. Link four is a warning about tendons."
        g = DR.parse_graphic("chain: plank 30s | lean 3x15s | frog stand 30s | WARNING tendons", script)
        self.assertEqual([i["target"] for i in g["items"]], ["30 S", "3 × 15 S", "30 S", ""]); self.assertTrue(g["items"][3]["warn"])
        self.assertIsNone(DR.parse_graphic("chain: plank | handstand", script)); self.assertIsNone(DR.parse_graphic("lever: weight | pivot", script))

if __name__ == "__main__":
    unittest.main()
