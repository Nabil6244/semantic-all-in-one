"""Reddit Shorts (reddit_shorts/, ui/reddit_shorts_section.py): story beats, cast rule, cue timing, app wiring. No network."""
import re
import unittest
from pathlib import Path

from reddit_shorts import paint, story
from reddit_shorts import render as R

ROOT = Path(__file__).resolve().parent


class StoryTests(unittest.TestCase):
    def test_builtin_cues_are_in_their_story(self):
        for sid in story.builtin_ids():
            st = story.builtin(sid)
            body = [R._norm(w) for w in st["body"].split() if R._norm(w)]
            pos = 0
            for ph, _ in st["beats"][1:]:
                p = [R._norm(x) for x in ph.split() if R._norm(x)]
                hit = next((i for i in range(pos, len(body)) if body[i:i + len(p)] == p), None)
                self.assertIsNotNone(hit, f"{sid}: {ph!r}")
                pos = hit + 1

    def test_custom_story_beats(self):
        body = " ".join(f"Sentence number {i} tells what I did with my sister that day." for i in range(16))
        st = story.custom("My sister borrowed my car, so I took her bike", body, sub="r/PettyPayback")
        self.assertEqual(st["sub"], "PettyPayback")
        self.assertTrue(story.MIN_BEATS + 1 <= len(st["beats"]) <= story.MAX_BEATS + 1)
        self.assertEqual(st["beats"][0][0], "")
        self.assertNotIn(" I ", st["beats"][1][1])
        self.assertIn("the narrator", st["beats"][1][1])

    def test_custom_story_needs_text(self):
        with self.assertRaises(ValueError):
            story.custom("Title", "too short")
        with self.assertRaises(ValueError):
            story.custom("", "word " * 60)

    def test_absent_people_are_named(self):
        cast = "Narrator: young woman, green sweater. Grandma: old lady, white bun"
        p = paint.with_cast("the narrator at a dinner table.", cast)
        self.assertIn("Narrator: young woman", p)
        self.assertIn("Grandma is NOT in this picture", p)
        self.assertNotIn("..", p)
        self.assertEqual(len(paint.cast_people("Narrator: a; Sister: b")), 2)

    def test_beat_times_follow_the_voice(self):
        words = [{"word": w, "start": i * 0.5, "end": i * 0.5 + 0.4} for i, w in enumerate("My title here then the story starts now and I'm done".split())]
        beats = [["", "a"], ["the story", "b"], ["I'm done", "c"]]
        self.assertEqual(R.beat_times(beats, words, 3), [0.0, 2.0, 4.5])
        with self.assertRaises(RuntimeError):
            R.beat_times([["", "a"], ["never said", "b"]], words, 3)

    def test_caption_chunks_are_short(self):
        words = [{"word": w, "start": i * 0.3, "end": i * 0.3 + 0.25} for i, w in enumerate("one two three four five six seven".split())]
        self.assertTrue(all(len(c) <= 3 for c in R.chunks_of(words)))


class WiringTests(unittest.TestCase):
    def test_registered_in_stories_group(self):
        from ui import style_registry as reg
        self.assertIn("Reddit Shorts", reg.STANDALONE)
        self.assertIn("Reddit Shorts", dict(reg.GROUPS)["Stories"])
        self.assertIn("Reddit Shorts", reg.EXTRA_BLURBS)

    def test_app_hooks_present(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        for hook in ("_rs_section.activate(self)", "_rs_section.deactivate(self)", "_rs_section.sync_cta(self)",
                     "_rs_section.cta(self, action)", "_rs_section.resume_on_open(self)", '"_rs_running"'):
            self.assertIn(hook, src)
        import visual_bridge
        self.assertIn("reddit_shorts", visual_bridge.OWNERS)

    def test_section_imports(self):
        from ui import reddit_shorts_section as sec
        self.assertEqual(sec.STYLE, "Reddit Shorts")
        self.assertTrue(re.match(r"01\. ", next(iter(sec._builtins()))))


if __name__ == "__main__":
    unittest.main()
