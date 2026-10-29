"""Tests for story_align (synthetic rows + fake Whisper words; no Whisper, no network)."""
import types
import unittest

import story_align as sa


def mk_words(text, t0=0.0, rate=0.3, spell=None, drop=()):
    """Fake Whisper: one word per token, `rate` seconds each; `spell` maps token -> Whisper's spelling; `drop` = token indices Whisper missed."""
    out, t = [], t0
    for i, tok in enumerate(text.split()):
        d = rate
        if i not in drop:
            out.append((spell.get(tok, tok) if spell else tok, round(t, 3), round(t + d, 3)))
        t += d
    return out, t


HI = [
    "आज रात किसी ऑर्डर का ट्रैकिंग पेज खोलिए और आपको वहाँ कोई दुकान दिखाई नहीं देगी।",
    "आपको एक बिंदु दिखाई देगा जो गोदाम से बाहर निकलता है।",
    "उस बिंदु के पीछे एक ऐसी इमारत होती है जो बहुत बड़ी होती है।",
    "वहाँ एक रोबोट किसी शेल्फ़ को उठा रहा होता है।",
]
WHISPER_SPELL = {"ऑर्डर": "अडर", "ट्रैकिंग": "ट्रकिन", "खोलिए": "खोलिए", "दिखाई": "दिखाए", "बिंदु": "बिू", "ऐसी": "आसी", "बड़ी": "बडी", "वहाँ": "वहां",
                 "रोबोट": "रोभोट", "शेल्फ़": "शेल्फ"}


def build(drop_scene=None, spell=WHISPER_SPELL, gap=0.0):
    rows, words, t = [], [], 0.0
    truth = []
    for i, line in enumerate(HI):
        rows.append({"scene_number": str(i + 1), "script_segment": line, "extra": i})
        toks = line.replace("।", "").split()
        drop = set(range(len(toks))) if drop_scene == i else set()
        w, t_end = mk_words(" ".join(toks), t0=t, spell=spell, drop=drop)
        truth.append((t, t_end))
        words += w
        t = t_end + gap
    return rows, words, truth


class Keys(unittest.TestCase):
    def test_loanword_and_spelling_variants_share_a_key(self):
        self.assertEqual(sa.phon_key("Amazon"), sa.phon_key("अमेज़न"))
        self.assertGreaterEqual(sa._key_sim(sa.phon_key("Amazon"), sa.phon_key("आमजोन")), 0.8)
        self.assertEqual(sa.phon_key("पहुँचता"), sa.phon_key("पहुचता"))
        self.assertEqual(sa.phon_key("होगगगगग"), sa.phon_key("होग"))

    def test_syllables(self):
        self.assertEqual(sa.syllables("1997"), 8)
        self.assertGreaterEqual(sa.syllables("कंपनी"), 3)
        self.assertEqual(sa.syllables("Amazon"), 3)
        self.assertEqual(sa.syllables("है"), 1)

    def test_tokenize_splits_hyphen_and_marks_pauses(self):
        toks = sa.tokenize("साल-दर-साल घाटे में, चलती रही।")
        self.assertEqual([t for t, _ in toks], ["साल", "दर", "साल", "घाटे", "में", "चलती", "रही"])
        self.assertGreater(toks[-1][1], 2.0)        # sentence end
        self.assertGreater(dict(enumerate(p for _, p in toks))[4], 0)    # comma after में


class Contract(unittest.TestCase):
    def test_same_keys_as_app_contract_and_tiling(self):
        rows, words, truth = build()
        al, end, rep = sa.align_story(rows, words, log=lambda *a: None)
        self.assertEqual(len(al), len(rows))
        for r, src in zip(al, rows):
            for k in ("scene_number", "script_segment", "start_time", "end_time", "confidence"):
                self.assertIn(k, r)
            self.assertEqual(r["extra"], src["extra"])          # other row keys are kept
        self.assertEqual(al[0]["start_time"], 0.0)
        self.assertAlmostEqual(al[-1]["end_time"], end)
        self.assertAlmostEqual(end, words[-1][2])
        for a, b in zip(al, al[1:]):
            self.assertAlmostEqual(a["end_time"], b["start_time"])
            self.assertLess(a["start_time"], a["end_time"])

    def test_boundaries_land_on_first_word(self):
        rows, words, truth = build(gap=0.6)
        al, end, rep = sa.align_story(rows, words, log=lambda *a: None)
        for r, (t0, t1) in zip(al[1:], truth[1:]):
            self.assertLessEqual(r["start_time"], t0 + 0.01)
            self.assertGreaterEqual(r["start_time"], t0 - 0.45)

    def test_deterministic(self):
        rows, words, _ = build(drop_scene=2)
        a = sa.align_story(rows, words, log=lambda *a: None)
        b = sa.align_story(rows, words, log=lambda *a: None)
        self.assertEqual(a, b)

    def test_does_not_mutate_inputs(self):
        rows, words, _ = build()
        before = [dict(r) for r in rows]
        sa.align_story(rows, words, log=lambda *a: None)
        self.assertEqual(rows, before)

    def test_min_duration_respected(self):
        rows, words, _ = build()
        al, _, _ = sa.align_story(rows, words, min_dur=1.2, log=lambda *a: None)
        self.assertTrue(all(r["end_time"] - r["start_time"] >= 1.2 - 1e-9 for r in al))


class Accuracy(unittest.TestCase):
    def test_dropped_scene_is_placed_by_syllables_between_heard_neighbours(self):
        rows, words, truth = build(drop_scene=2)
        al, end, rep = sa.align_story(rows, words, log=lambda *a: None)
        t0, t1 = truth[2]
        r = al[2]
        self.assertLess(abs(r["start_time"] - t0), 0.6)
        self.assertLess(abs(r["end_time"] - t1), 0.6)
        self.assertIn("3", rep["weak"])
        self.assertLess(r["confidence"], 0.5)
        # scenes next to it are still exact
        self.assertLess(abs(al[3]["start_time"] - truth[3][0]), 0.45)

    def test_drop_inside_scene_keeps_next_boundary(self):
        rows, words, truth = build()
        # Whisper misses the first 4 words of scene 2 and the last 3 of scene 3
        w2, _ = mk_words(" ".join(HI[1].replace("।", "").split()), t0=truth[1][0], spell=WHISPER_SPELL, drop={0, 1, 2, 3})
        w3, _ = mk_words(" ".join(HI[2].replace("।", "").split()), t0=truth[2][0], spell=WHISPER_SPELL, drop={9, 10, 11})
        words = [w for w in words if not (truth[1][0] - 1e-6 <= w[1] < truth[3][0] - 1e-6)] + w2 + w3
        words.sort(key=lambda w: w[1])
        al, _, _ = sa.align_story(rows, words, log=lambda *a: None)
        self.assertLess(abs(al[2]["start_time"] - truth[2][0]), 0.5)
        self.assertLess(abs(al[3]["start_time"] - truth[3][0]), 0.5)
        self.assertLess(abs(al[1]["start_time"] - truth[1][0]), 1.2)

    def test_repeated_phrase_does_not_pull_boundaries(self):
        phrase = "यह एक बहुत पुरानी कहानी है जो हर बार सुनाई जाती है"
        rows = [{"scene_number": str(i + 1), "script_segment": phrase + (" और अलग शब्द %d" % i if False else "")} for i in range(3)]
        words, t = [], 0.0
        starts = []
        for i in range(3):
            starts.append(t)
            w, t = mk_words(phrase, t0=t)
            words += w
        al, _, _ = sa.align_story(rows, words, min_dur=1.0, log=lambda *a: None)
        for r, s in zip(al, starts):
            self.assertLess(abs(r["start_time"] - s), 0.5)

    def test_english_and_digits_and_loanwords(self):
        rows = [
            {"scene_number": "1", "script_segment": "Amazon ने 1997 में शेयर बाज़ार में कदम रखा।"},
            {"scene_number": "2", "script_segment": "आज कंपनी का बाज़ार मूल्य तीन ट्रिलियन डॉलर है।"},
            {"scene_number": "3", "script_segment": "Borders और Circuit City ख़त्म हो गई।"},
        ]
        spoken = "आमाजों ने उन्निस्सो सत्तानवे में शेर बाजार में कदम रखा आज कंपनी का भाजार मुल्य तीन ट्रिल्यन डोलर है बोर्टर्स और सरकिट सिटी कहत्म होगगगगग"
        words, _ = mk_words(spoken)
        starts = [0.0, 10 * 0.3, 19 * 0.3]
        al, _, rep = sa.align_story(rows, words, log=lambda *a: None)
        self.assertLess(abs(al[1]["start_time"] - starts[1]), 0.6)
        self.assertLess(abs(al[2]["start_time"] - starts[2]), 0.6)

    def test_chain_rejects_jump_ahead_match(self):
        # a scene's last word sounds like the next scene's first word; the clock must stop it from stealing it
        rows = [{"scene_number": "1", "script_segment": "पहले हम एक लंबी कहानी सुनते हैं जो बहुत दूर तक जाती है और आपका"},
                {"scene_number": "2", "script_segment": "आपको कुछ नया दिखाई देगा यहाँ"}]
        w1, t = mk_words("पहले हम एक लंबी कहानी सुनते हैं जो बहुत दूर तक जाती है और आपका")
        w2, _ = mk_words("आपको कुछ नया दिखाई देगा यहाँ", t0=t)
        al, _, _ = sa.align_story(rows, w1 + w2, log=lambda *a: None)
        self.assertLess(abs(al[1]["start_time"] - t), 0.7)


class Fallback(unittest.TestCase):
    def test_garbage_audio_uses_fallback_when_given(self):
        rows, _, _ = build()
        words = [("xyzzy", i * 0.3, i * 0.3 + 0.3) for i in range(60)]
        called = []

        def fb(r, w):
            called.append(1)
            return ([{"scene_number": x["scene_number"], "script_segment": x["script_segment"], "start_time": 0.0, "end_time": 1.0, "confidence": 0.0}
                     for x in r], 18.0)

        al, end, rep = sa.align_story(rows, words, log=lambda *a: None, fallback=fb)
        self.assertTrue(called)
        self.assertTrue(rep["fallback"])
        al2, end2, rep2 = sa.align_story(rows, words, log=lambda *a: None)
        self.assertTrue(rep2.get("fallback_recommended"))
        self.assertEqual(len(al2), len(rows))


class Hook(unittest.TestCase):
    def test_applied_swaps_and_restores(self):
        rows, words, _ = build()
        calls = []

        def original(r, w):
            calls.append("orig")
            return [], 0.0

        vg = types.SimpleNamespace(align_rows=original)
        with sa.applied(vg, log=lambda *a: None):
            self.assertIsNot(vg.align_rows, original)
            al, end = vg.align_rows(rows, words)
            self.assertEqual(len(al), len(rows))
        self.assertIs(vg.align_rows, original)
        self.assertFalse(calls)

    def test_applied_falls_back_on_exception(self):
        msgs = []
        vg = types.SimpleNamespace(align_rows=lambda r, w: ("orig", 1.0))
        with sa.applied(vg, log=msgs.append):
            self.assertEqual(vg.align_rows([{"scene_number": "1", "script_segment": "x"}], []), ("orig", 1.0))
        self.assertTrue(any("failed" in m for m in msgs))

    def test_compare(self):
        rows, words, _ = build()
        al, _, _ = sa.align_story(rows, words, log=lambda *a: None)
        shifted = [dict(r, start_time=r["start_time"] + 1.0, end_time=r["end_time"] + 1.0) for r in al]
        c = sa.compare(al, shifted)
        self.assertEqual(len(c), len(rows))
        self.assertTrue(all(abs(x["start_shift"] - 1.0) < 1e-6 for x in c))


if __name__ == "__main__":
    unittest.main()
