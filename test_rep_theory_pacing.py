"""Rep Theory pacing from the final 3 audit (docs/rep_theory/AUDIT_2026-11-01_final3.md): slot names said in a joined scene, cards that finish before the cut,
one key line a chapter with pictures on. Plan-level only: no render, no Flow."""
from __future__ import annotations
import unittest

from reptheory import cards as K, variety as V

def _sc(text, no, start, end, **kw):
    toks = text.split(); step = (end - start) / max(1, len(toks))
    ws = [{"w": w.strip(".,!?").lower(), "t0": start + step * i, "t1": start + step * (i + 0.85)} for i, w in enumerate(toks)]
    return dict({"no": no, "kind": "callout", "start": start, "end": end, "words": ws, "text": text, "pages": [], "decisions": [], "art": "", "section": "X", "topic": ""}, **kw)

class SlotsFromJoinedScene(unittest.TestCase):
    def test_item_names_inside_the_next_scene_name_the_slots(self):
        scs = [_sc("Training your tendons makes you win.", 1, 0, 3), _sc("Every match comes down to four moments.", 2, 3, 5.5),
               _sc("The go. The wrist. The squeeze. And the line. You've seen it happen at the table.", 3, 5.5, 12.0)]
        self.assertEqual(V.absorb_slot_items(scs), 4)
        self.assertEqual(len(scs), 3); self.assertTrue(scs[2]["text"].startswith("You've seen")); self.assertGreater(scs[1]["end"], 5.5)
        V.direct(scs, flow=True); s = next(x for x in scs if x["kind"] == "slots")
        self.assertEqual([i["text"] for i in s["slots"]["items"]], ["THE GO", "THE WRIST", "THE SQUEEZE", "THE LINE"])

    def test_a_short_remainder_joins_the_count_too(self):
        scs = [_sc("Every match comes down to three moments.", 1, 0, 2.5), _sc("The go. The wrist. The squeeze. Yes.", 2, 2.5, 6.0)]
        V.absorb_slot_items(scs); self.assertEqual(len(scs), 1)

    def test_directed_slots_card_is_rebuilt_with_the_names(self):
        scs = [_sc("Every match comes down to four moments.", 1, 0, 2.5, directed_look=True, look="slots"), _sc("The go. The wrist. The squeeze. And the line. Then it starts.", 2, 2.5, 9.0)]
        V.absorb_slot_items(scs); self.assertEqual([i["text"] for i in scs[0]["look_payload"]["items"]], ["THE GO", "THE WRIST", "THE SQUEEZE", "THE LINE"])

    def test_no_count_no_change(self):
        scs = [_sc("Grip strength matters a lot.", 1, 0, 2.5), _sc("The go. The wrist.", 2, 2.5, 4.0)]
        self.assertEqual(V.absorb_slot_items(scs), 0); self.assertEqual(len(scs), 2)

class CardsFinish(unittest.TestCase):
    def setUp(self): self._old = getattr(K, "CARD_DONE", None); K.CARD_DONE = {"race": lambda c: c["at"] + 3.0}
    def tearDown(self):
        if self._old is None: del K.CARD_DONE
        else: K.CARD_DONE = self._old

    def test_card_borrows_time_but_the_next_scene_keeps_its_share(self):
        a = _sc("Stiff tendons get it there fast.", 1, 10.0, 11.6, kind="race", race={"at": 10.0}); b = _sc("And in an arm wrestle, late loses badly.", 2, 11.6, 14.6)
        self.assertEqual(V.let_cards_finish([a, b]), 1)
        self.assertAlmostEqual(a["end"], b["start"]); self.assertGreaterEqual(b["end"] - b["start"], 1.5 - 1e-6); self.assertLessEqual(a["end"], 13.5 + 1e-6)

    def test_finished_card_is_left_alone_and_missing_table_is_harmless(self):
        a = _sc("Stiff tendons get it there fast.", 1, 10.0, 14.0, kind="race", race={"at": 10.0}); b = _sc("Late loses.", 2, 14.0, 16.0)
        self.assertEqual(V.let_cards_finish([a, b]), 0)
        del K.CARD_DONE; self.assertEqual(V.let_cards_finish([a, b]), 0); K.CARD_DONE = {}

class KeyLine(unittest.TestCase):
    def test_at_most_one_key_line_a_chapter_and_never_the_opening(self):
        scs = [_sc(f"This one short claim number {w} matters.", i + 1, 3.5 * i, 3.5 * i + 3.4) for i, w in enumerate("one two three four five six".split())]
        V.direct(scs, flow=True, roles={i: "claim" for i in range(6)})
        keys = [sc for sc in scs if sc.get("look") == "takeaway"]
        self.assertNotEqual(scs[0].get("look"), "takeaway"); self.assertLessEqual(len(keys), 1)

if __name__ == "__main__":
    unittest.main()
