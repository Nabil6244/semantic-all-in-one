"""edge_voiceover.py: splitting, the ffmpeg join list, and a full synthesize() run against a fake edge_tts (no network)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

import edge_voiceover as ev

FFMPEG = shutil.which("ffmpeg")


class SplitTests(unittest.TestCase):
    def test_pieces_end_on_sentences_and_stay_under_the_limit(self):
        text = " ".join(f"Sentence number {i} is here." for i in range(200))
        pieces = ev.split_script(text, 300)
        self.assertGreater(len(pieces), 5)
        self.assertTrue(all(len(p) <= 300 for p in pieces))
        self.assertTrue(all(p.endswith(".") for p in pieces))
        self.assertEqual(" ".join(pieces), text)

    def test_one_oversize_sentence_is_cut_at_spaces(self):
        pieces = ev.split_script("word " * 500, 100)
        self.assertTrue(all(len(p) <= 100 for p in pieces))
        self.assertEqual(" ".join(pieces).split(), ["word"] * 500)

    def test_empty_script_gives_no_pieces(self):
        self.assertEqual(ev.split_script("  \n "), [])

    def test_concat_line_escapes_quotes(self):
        self.assertEqual(ev._concat_line("/a/b'c.mp3"), "file '/a/b'\\''c.mp3'\n")

    def test_rate_string(self):
        self.assertEqual(ev._rate(1.0), "+0%")
        self.assertEqual(ev._rate(0.9), "-10%")
        self.assertEqual(ev._rate(1.25), "+25%")


@unittest.skipUnless(FFMPEG, "ffmpeg not installed")
class SynthesizeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        tone = os.path.join(self.tmp, "tone.mp3")
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=300:d=1",
                        "-c:a", "libmp3lame", tone], check=True)
        data = Path(tone).read_bytes()
        calls = {"n": 0}

        class Comm:
            def __init__(self, text, voice, **kw):
                self.text = text

            async def stream(self):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise RuntimeError("throttled")   # the first try of the first piece fails and is retried
                yield {"type": "audio", "data": data}
                yield {"type": "WordBoundary", "text": "hi", "offset": 0, "duration": 5_000_000}

        fake = types.ModuleType("edge_tts")
        fake.Communicate = Comm
        self._old = sys.modules.get("edge_tts")
        sys.modules["edge_tts"] = fake
        self.calls = calls

    def tearDown(self):
        if self._old is None:
            sys.modules.pop("edge_tts", None)
        else:
            sys.modules["edge_tts"] = self._old

    def test_pieces_are_retried_joined_and_timed(self):
        old = ev.split_script
        ev.split_script = lambda t, m=20: old(t, m)
        self.addCleanup(setattr, ev, "split_script", old)
        out = os.path.join(self.tmp, "sub dir", "vo's.mp3")   # a space and a quote in the path
        seen = []
        res = ev.synthesize("One short line. Two short lines. Three short lines.", out,
                            progress=lambda d, n: seen.append((d, n)))
        self.assertEqual(res["pieces"], 3)
        self.assertEqual(seen[-1], (3, 3))
        self.assertTrue(os.path.getsize(out) > 0)
        # 3 one-second pieces + 3 gaps (loudnorm may trim a little)
        self.assertGreater(res["duration"], 3.0)
        words = json.load(open(res["words_path"]))
        self.assertEqual(len(words), 3)
        self.assertTrue(words[0]["start"] < words[1]["start"] < words[2]["start"])
        self.assertGreaterEqual(self.calls["n"], 4)   # 3 pieces + 1 retry


if __name__ == "__main__":
    unittest.main()


class Languages(unittest.TestCase):
    """The Voiceover tab's other languages (2026-11-04): sentence ends of every script, and a voice list per language."""

    def test_sentence_ends_of_each_script(self):
        self.assertEqual(ev.split_sentences("یہ پہلا جملہ ہے۔ یہ دوسرا ہے۔کیا یہ تیسرا ہے؟ ٹھیک"),
                         ["یہ پہلا جملہ ہے۔", "یہ دوسرا ہے۔", "کیا یہ تیسرا ہے؟", "ٹھیک"])
        self.assertEqual(ev.split_sentences("यह पहला वाक्य है। यह दूसरा है।"), ["यह पहला वाक्य है।", "यह दूसरा है।"])
        self.assertEqual(ev.split_sentences("这是第一句。这是第二句！对吗？"), ["这是第一句。", "这是第二句！", "对吗？"])
        self.assertEqual(ev.split_sentences("It costs 3.5 dollars. Next!"), ["It costs 3.5 dollars.", "Next!"])

    def test_long_urdu_and_chinese_scripts_split_on_their_own_sentence_ends(self):
        urdu = "یہ ایک لمبا جملہ ہے جس میں بہت سے الفاظ ہیں۔ " * 40
        pieces = ev.split_script(urdu, 300)
        self.assertGreater(len(pieces), 1)
        self.assertTrue(all(len(p) <= 300 and p.endswith("۔") for p in pieces), pieces[:2])
        chinese = "这是一个很长的句子，里面有很多字。" * 60
        pieces = ev.split_script(chinese, 300)
        self.assertTrue(all(len(p) <= 300 and p.endswith("。") for p in pieces))

    def test_word_count_for_scripts_without_spaces(self):
        self.assertEqual(ev.word_count("one two three"), 3)
        self.assertGreater(ev.word_count("这是第一句这是第二句这是第三句"), 3)

    def test_every_language_has_its_own_voices_and_english_stays_first(self):
        from ui.voiceover_view import LANGUAGES, VOICES, voices_for
        import re
        self.assertEqual(LANGUAGES[0], ("English", VOICES))
        names = [n for n, _ in LANGUAGES]
        self.assertTrue({"Urdu", "Hindi", "Arabic", "Spanish"} <= set(names))
        ids = [vid for _, vs in LANGUAGES for _, vid in vs]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(re.fullmatch(r"[a-z]{2,3}-[A-Z]{2}-\w+Neural", v) for v in ids), ids)
        self.assertTrue(all(v.startswith("ur-") for _, v in voices_for("Urdu")))
        self.assertEqual(voices_for("Klingon"), VOICES)
