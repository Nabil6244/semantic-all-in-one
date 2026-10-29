"""The characters pack: files match their manifest, the kit draws them, and the director chooses them from the words of a beat."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class Pack(unittest.TestCase):
    def test_the_files_on_disk_are_what_the_builder_makes(self):
        r = subprocess.run([sys.executable, "-B", str(ROOT / "explainer/cartoon/build_characters.py"), "--check"], capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_every_character_has_every_pose_and_stands_on_the_bottom_edge(self):
        from explainer.cartoon import characters as CH
        self.assertGreaterEqual(len(CH.types()), 14)
        for k in CH.types():
            for pose in ("idle", "point", "surprise", "think"):
                self.assertEqual(CH.problem(k, pose), "")
                im = CH.full(k, pose)
                self.assertEqual(im.size, (440, 560))
                self.assertGreaterEqual(im.getchannel("A").getbbox()[3], 540)

    def test_the_kit_accepts_a_character_as_a_cast_and_as_a_crowd(self):
        from explainer.cartoon import characters, kit
        characters.install()
        self.assertEqual(kit.problem("figure", {"cast": "soldier", "pose": "point", "kit": "a"}), "")
        self.assertIn("unknown", kit.problem("figure", {"cast": "wizard", "pose": "idle", "kit": "a"}))
        self.assertEqual(kit.problem("crowd", {"n": 7, "kind": "soldier"}), "")
        self.assertIn("unknown crowd kind", kit.problem("crowd", {"n": 7, "kind": "wizard"}))
        a = kit.crowd_sprite(7, 250, 0, "soldier")
        b = kit.crowd_sprite(7, 250, 0)
        self.assertNotEqual(a.tobytes(), b.tobytes())
        self.assertEqual(kit.cast_sprite("police", "idle", "a", 400, False).height, 400)


class Words(unittest.TestCase):
    def test_words_choose_who_stands_on_the_stage(self):
        from explainer.director import lexicon_v2 as LV
        t = "the army marched while the emperor and the general watched".split()
        self.assertEqual([k for k, _ in LV.characters_for(t)], ["soldier", "king", "officer"])
        self.assertEqual(LV.crowd_for(t), ("soldier", 1))
        self.assertIsNone(LV.crowd_for("the general spoke".split()))
        self.assertEqual([k for k, _ in LV.characters_for("police arrested the workers".split())], ["police", "worker"])


if __name__ == "__main__":
    unittest.main()
