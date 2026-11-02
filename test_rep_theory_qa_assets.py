"""Phase 5: viewer questions (reptheory/qa.py) and the Flow asset library (reptheory/assets.py), read from the script's words only."""
import unittest

from PIL import Image

from reptheory import assets as AS, direction as DR, draw as D, qa as QA


def scene(text, start, look="callout"):
    ws = [{"w": w, "t0": start + i * 0.3} for i, w in enumerate(text.split())]
    return {"text": text, "words": ws, "start": start, "end": start + len(ws) * 0.3 + 1.0, "kind": "callout", "look": look, "pages": [], "decisions": []}


class Questions(unittest.TestCase):
    def video(self):
        return [scene("Today I answer the three questions you ask most.", 0), scene("Question one: how often should I train?", 5), scene("Three times a week is plenty.", 9),
                scene("You asked: do I need weights?", 13), scene("The most common question is: will it hurt my wrists?", 18)]

    def test_list_and_tracker(self):
        ss = self.video(); QA.plan(ss)
        self.assertEqual([i["text"] for i in ss[0]["qlist"]["items"]], ["How often should I train?", "Do I need weights?", "Will it hurt my wrists?"])
        self.assertEqual([s.get("qtrack", {}).get("n") for s in ss], [None, 1, 1, 2, 3])
        self.assertTrue(ss[1]["qtrack"]["new"]); self.assertFalse(ss[2]["qtrack"]["new"])

    def test_needs_two_questions(self):
        ss = [scene("People ask me why I train.", 0), scene("Question one: how often should I train?", 4)]
        self.assertEqual(QA.plan(ss), 0); self.assertFalse(any(s.get("qtrack") for s in ss))

    def test_draws(self):
        ss = self.video(); QA.plan(ss); ctx = D.Ctx(640, 360)
        for s in ss:
            for t in (s["start"], s["start"] + 1.0, s["end"]):
                cv = Image.new("RGB", (640, 360))
                if s.get("qlist"): QA.draw_list(cv, ctx, s["qlist"], t)
                if s.get("qtrack"): QA.draw_track(cv, ctx, s["qtrack"], t)


class Assets(unittest.TestCase):
    def test_match_and_fixed_id(self):
        self.assertEqual(AS.match("The tendons in your forearm take months to adapt."), "xray_forearm")
        self.assertEqual(AS.match("Squeeze your shoulder blades together."), "back_shoulder_blades")
        self.assertEqual(AS.match("Add a plate to the bar."), "")
        self.assertEqual(AS.art_id("obj_backpack"), "asset_obj_backpack_v1")
        self.assertIn("no text", AS.prompt("obj_backpack"))

    def test_plan_reuse_gap_and_hook(self):
        ss = [scene("Your brain learns the move first.", 0, look="flow"), scene("Your brain adapts in days.", 5, look="flow"), scene("Your nerves fire faster.", 40, look="flow")]
        ss[0]["hook"] = True; AS.plan(ss)
        self.assertEqual([s.get("asset") for s in ss], [None, "brain_spine", "brain_spine"])
        ss = [scene("Your brain adapts in days.", 0, look="flow"), scene("And your brain again here.", 6, look="flow")]; AS.plan(ss)
        self.assertEqual([s.get("asset") for s in ss], ["brain_spine", None])      # not twice within REUSE_GAP_S

    def test_csv_asks_by_name(self):
        g = DR.parse_graphic("asset: xray forearm", "any script"); self.assertEqual(g, {"kind": "asset", "name": "xray_forearm"})
        self.assertIsNone(DR.parse_graphic("asset: unicorn", "any script"))
        s = scene("Hold it like this.", 0, look="flow"); s["graphic_csv"] = g; AS.plan([s]); self.assertEqual(s["asset"], "xray_forearm")


if __name__ == "__main__":
    unittest.main()
