"""Script bible (reptheory/bible.py): a beat's picture knows the whole script - its own cast, the move being taught, the study a number belongs to, what its named moves mean.
Synthetic scripts only (other people, other move names), never the one video that showed the gaps."""
import unittest

from reptheory import beat_art as BA, bible as BB

SCRIPT = ("A 90-kilo bodybuilder with massive arms races a skinny farmer up a rope. Halfway up, the bodybuilder's grip fails and he slides down. That's not strength. "
          "Move number one: the claw. Sit on a chair and hold a full water jug by its cap with your fingertips only. Keep your knuckles bent. 15 seconds in, your fingers shake. "
          "Here's why the claw matters. Your fingertips are the last link of the chain. "
          "In a 10-week study, researchers had climbers train one hand with light loads and the other with heavy loads. Only the heavy hand got stronger. "
          "Move number two: the hook pull. Hang a towel over a door and pull it down with two fingers. "
          "Subscribe if you want more. Before you copy the weekly plan, one rule. Make the Claw your main focus.")

def scenes_of(text, n=8):
    t = text.split()
    return [{"no": i + 1, "text": " ".join(t[j:j + n]), "kind": "trainee"} for i, j in enumerate(range(0, len(t), n))]

def scene_with(scenes, words):
    return next(sc for sc in scenes if words in sc["text"])

class BibleTest(unittest.TestCase):
    def setUp(self):
        self.scenes = scenes_of(SCRIPT); self.bb = BA.script_bible(self.scenes, log=lambda *_: None)

    def test_cast_is_the_scripts_people_and_who_wins(self):
        cast = {c["key"]: c for c in self.bb["cast"]}
        self.assertIn("bodybuilder", cast); self.assertIn("farmer", cast)
        self.assertEqual(cast["bodybuilder"]["role"], "loses"); self.assertEqual(cast["farmer"]["role"], "wins")
        self.assertIn("90-kilo", cast["bodybuilder"]["phrase"])

    def test_intro_line_shows_the_cast_not_our_trainee(self):
        p = BA.scene_prompt(scene_with(self.scenes, "grip fails"), self.bb)
        self.assertIn("farmer", p); self.assertIn("bodybuilder", p); self.assertNotIn("skinny beginner build", p)

    def test_setup_fragment_carries_the_whole_exercise(self):
        p = BA.scene_prompt(scene_with(self.scenes, "knuckles"), self.bb)
        self.assertNotIn("water jug", scene_with(self.scenes, "knuckles")["text"]); self.assertIn("water jug", p); self.assertIn("taught is claw", p)

    def test_explain_line_is_not_forced_into_the_exercise(self):
        self.assertEqual(scene_with(self.scenes, "last link").get("_bible", {}).get("mode"), "explain")

    def test_study_lines_keep_the_study(self):
        sc = scene_with(self.scenes, "Only the heavy"); self.assertEqual(sc["_bible"]["kind"], "study")
        self.assertIn("10-week study", BA.scene_prompt(sc, self.bb))

    def test_named_move_later_means_the_move_not_the_object(self):
        p = BA.scene_prompt(self.scenes[-1], self.bb)
        self.assertIn("not an everyday object", p); self.assertIn("water jug", p)

    def test_roadmap_mention_before_the_move_gets_no_meaning(self):
        s = scenes_of("Three tricks: the claw, the hook and the pinch. Move number one: the claw. Sit and hold a jug by the cap. Keep your knuckles bent.", 6)
        BA.script_bible(s, log=lambda *_: None)
        self.assertEqual((s[0].get("_bible") or {}).get("means", []), [])

    def test_csv_prompt_naming_a_cast_member_gets_their_look(self):
        p = BA.own_prompt("the farmer climbing the rope easily", self.bb["cast"])
        self.assertIn("calloused", p); self.assertNotIn("buzz cut", p)

    def test_script_without_cast_or_moves_keeps_the_old_prompt(self):
        s = [{"no": 1, "text": "Drink water every morning before you train", "kind": "trainee"}]
        self.assertIsNone(BA.script_bible(s, log=lambda *_: None))
        self.assertEqual(BA.scene_prompt(s[0], None), BA.prompt_for(s[0]["text"]))

if __name__ == "__main__":
    unittest.main()
