"""Rep Theory labels and CSV words (docs/rep_theory/AUDIT_2026-11-01_final3.md items 4-5): "arm wrestling" names no body part, glow labels carry the word as said,
the same label is not repeated on two picture scenes running, and a CSV row's own text decides its card when the transcript dropped a word. Plan-level only: no render."""
from __future__ import annotations
import unittest

from reptheory import direction as DR, picture as PIC, states as ST

def _ws(text, start=0.0):
    return [{"w": w.strip(",.!?"), "t0": start + 0.3 * i, "t1": start + 0.3 * i + 0.25} for i, w in enumerate(text.split())]

def _sc(text, no=1, start=0.0, kind="callout", **kw):
    ws = _ws(text, start)
    return dict({"no": no, "kind": kind, "start": start, "end": start + 0.3 * len(ws) + 0.5, "words": ws, "text": text, "pages": [], "decisions": [], "art": "", "section": "X", "topic": ""}, **kw)

class Labels(unittest.TestCase):
    def test_arm_wrestling_is_not_a_body_part(self):
        for t in ("And in an arm wrestle, late loses.", "Pro arm wrestling has weight classes.", "Most arm wrestlers fix this."):
            self.assertEqual(ST.parts_named(_ws(t), t), [], t)
        t = "Your arms do the work."; self.assertEqual([p for p, _ in ST.parts_named(_ws(t), t)], ["arms"])

    def test_glow_keeps_the_word_as_said(self):
        sc = _sc("Rest your forearm on the table and curl your bicep.")
        ST.apply([sc], lambda a: True)
        words = {g["label"]: g["word"] for g in sc.get("glows", [])}
        self.assertEqual(words.get("FOREARMS"), "FOREARM"); self.assertEqual(words.get("ARMS"), "BICEP")

    def test_same_label_on_two_picture_scenes_is_shown_once(self):
        a = _sc("Your tendons carry it.", 1, 0.0, kind="illus", art="", glows=[{"at": 0.3, "label": "ARMS", "word": "TENDONS"}])
        b = _sc("Stiff tendons are fast.", 2, 2.0, kind="illus", art="", glows=[{"at": 2.3, "label": "ARMS", "word": "TENDONS"}])
        c = _sc("Curl your wrist.", 3, 4.0, kind="illus", art="", glows=[{"at": 4.3, "label": "FOREARMS", "word": "WRIST"}])
        PIC.plan([a, b, c])
        self.assertFalse(a.get("_label_off")); self.assertTrue(b.get("_label_off")); self.assertFalse(c.get("_label_off"))

class ScriptText(unittest.TestCase):
    def test_csv_text_decides_the_card_when_the_transcript_lost_a_word(self):
        heard = "tendon stiffness alone explained up to about 30 of the difference"
        sc = _sc(heard, 1, 0.0)
        row = {"text": "Tendon stiffness alone explained up to about thirty percent of the difference.", "start": 0.0, "end": sc["end"], "look": "stat"}
        DR.apply([sc], [row])
        self.assertEqual(sc.get("script_text"), row["text"]); self.assertEqual(sc.get("look"), "stat"); self.assertTrue(sc.get("directed_look"))

    def test_no_script_text_when_two_rows_share_a_scene(self):
        sc = _sc("the go. the wrist.", 1, 0.0)
        rows = [{"text": "The go.", "start": 0.0, "end": 0.6}, {"text": "The wrist.", "start": 0.6, "end": sc["end"]}]
        DR.apply([sc], rows); self.assertNotIn("script_text", sc)

if __name__ == "__main__":
    unittest.main()
