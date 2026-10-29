"""Meaning-aware selection (explainer/director/meaning.py + select.py): deterministic, opt-in, and a no-op when off."""
import unittest

from explainer.director import meaning as MN
from explainer.director.options import DirectorOptions
from explainer.director import select as S


def toks(text):
    return text.lower().replace(",", "").replace(".", "").split()


class Classify(unittest.TestCase):
    def test_quantity(self):
        m = MN.classify(toks("Napoleon lost 400000 soldiers in russia"))
        self.assertEqual(m.idea, "quantitative")

    def test_comparison(self):
        m = MN.classify(toks("Britain was richer than France while the French army was bigger"))
        self.assertEqual(m.idea, "comparative")

    def test_dialogue_from_quote(self):
        m = MN.classify(toks("He said no I will not sign"), text='He said "No, I will not sign."')
        self.assertEqual(m.idea, "dialogue")

    def test_evidence(self):
        m = MN.classify(toks("According to historians this painting and the letters prove it"))
        self.assertEqual(m.idea, "evidence")

    def test_cause(self):
        m = MN.classify(toks("The tax rose because of the war which meant bread cost more"))
        self.assertEqual(m.idea, "cause")

    def test_spatial(self):
        m = MN.classify(toks("The army marched across the border toward the capital"), has_place=True)
        self.assertEqual(m.idea, "spatial")

    def test_weak_or_tied_signal_decides_nothing(self):
        self.assertEqual(MN.classify(toks("It was a quiet morning")).idea, "")
        self.assertEqual(MN.classify(toks("He said more")).idea, "")      # dialogue 2 vs comparative 1: lead too small

    def test_a_year_is_not_a_quantity(self):
        self.assertNotEqual(MN.classify(toks("In 1815 it ended")).idea, "quantitative")

    def test_real_false_positives_found_on_the_napoleon_script(self):
        self.assertNotEqual(MN.classify(toks("but just over 200 years ago")).idea, "quantitative")      # a span of time
        self.assertEqual(MN.classify(toks("napoleon was exiled to elba an island off the coast of italy")).scores["cause"], 0)      # 'exiled to' is not 'led to'
        self.assertEqual(MN.classify(toks("in 1798 he led a military expedition across the sea to egypt")).scores["cause"], 0)      # led = commanded
        self.assertEqual(MN.classify(toks("the russians refused to surrender")).scores["dialogue"], 1)      # refusing is not speech
        self.assertGreater(MN.classify(toks("the reform led to a famine")).scores["cause"], 0)

    def test_deterministic(self):
        a = MN.classify(toks("Because of the war 5 million people left")).to_dict()
        b = MN.classify(toks("Because of the war 5 million people left")).to_dict()
        self.assertEqual(a, b)


class OffMode(unittest.TestCase):
    def test_default_option_is_off(self):
        self.assertFalse(DirectorOptions().meaning)

    def test_beatplan_idea_defaults_empty(self):
        self.assertEqual(S.BeatPlan("e1", 0, 1, []).idea, "")

    def test_setting_reader(self):
        from explainer.integration import extras
        self.assertFalse(extras({})["meaning"])
        self.assertTrue(extras({"explainer_meaning": True})["meaning"])


class Synthetic(unittest.TestCase):
    """A hand-written narration with unmistakable quantity, comparison, dialogue and evidence beats: old selection vs meaning on."""

    SCRIPT = ("The farmers brought five million tons of grain to the market in the city. The traders paid less than the farmers hoped. "
              "The king said, \"Bread will cost more, because the war must be paid for.\" The farmers shouted at the soldiers in the village square. "
              "According to historians, this letter and the painting of the harbour prove the story.")

    def _kinds(self, meaning):
        import re
        from explainer.director import segment as SG
        words, t = [], 0.0
        for sent in re.split(r"(?<=[.!?])\s+", self.SCRIPT):
            for w in re.findall(r"[A-Za-z']+", sent):
                words.append((w.lower(), t, t + 0.34))
                t += 0.38
            t += 0.4
        dur = t + 0.5
        opt = DirectorOptions(cartoon_share=1.0, footage_share=1.0, scenes2=True, meaning=meaning, min_beat_s=2.5)
        ss = SG.sentences(words, self.SCRIPT, dur, opt.split_over_s)
        SG.label_sentences(ss, words, self.SCRIPT)
        SG.compute_breaks(ss, words)
        beats = S.group(ss, dur, opt)
        info = S.choose_kinds(beats, words, self.SCRIPT, dur, opt)
        return {b.id: (b.kind, b.idea, " ".join(w[0] for w in words if b.start - 1e-6 <= w[1] < b.end)) for b in beats}, info

    def test_a_comparison_is_a_board_and_a_quote_is_acted_out(self):
        old, _ = self._kinds(False)
        new, info = self._kinds(True)
        cmp_ids = [i for i, v in new.items() if v[1] == "comparative"]
        dlg_ids = [i for i, v in new.items() if v[1] == "dialogue"]
        self.assertTrue(cmp_ids and dlg_ids)
        for i in cmp_ids:
            self.assertEqual(new[i][0], "board")
        for i in dlg_ids:
            self.assertEqual(new[i][0], "cartoon")
        self.assertTrue(any(old[i][0] != new[i][0] for i in cmp_ids + dlg_ids))          # the meaning layer really changed something
        self.assertTrue(info.get("meaning_effects"))
        self.assertTrue(all(r.get("reason") for r in info.get("cartoon_skipped", []) + info.get("footage_skipped", [])))


class Veto(unittest.TestCase):
    """A quantity or comparison beat is not turned into a cartoon or footage beat when meaning is on; with it off the old rules decide."""

    def _words(self, text, start=0.0, step=0.4):
        out, t = [], start
        for w in text.split():
            out.append((w.lower(), t, t + step - 0.05))
            t += step
        return out

    def _run(self, meaning):
        text = "the farmers sold five million tons of grain at the market and the farmers sold two hundred thousand tons of wheat at the market"
        words = self._words(text)
        dur = words[-1][2] + 0.5
        from explainer.director.segment import Sent
        sent = Sent(0, 0.0, dur, text, True, list(range(len(words))))
        beats = [S.BeatPlan("e1", 0.0, dur, [sent])]
        opt = DirectorOptions(cartoon_share=1.0, footage_share=1.0, meaning=meaning)
        info = {"named_subjects": []}
        if meaning:
            S.annotate_meaning(beats, words, [])
        S._assign_cartoons(beats, words, dur, opt, info)
        if beats[0].kind == "board":
            S._assign_footage(beats, words, dur, opt, info)
        return beats[0], info

    def test_off_keeps_the_old_choice(self):
        b, _ = self._run(False)
        self.assertEqual(b.idea, "")
        self.assertIn(b.kind, ("cartoon", "footage"))

    def test_on_keeps_a_quantity_beat_a_board(self):
        b, info = self._run(True)
        self.assertEqual(b.idea, "quantitative")
        self.assertEqual(b.kind, "board")
        reasons = [r["reason"] for r in info.get("cartoon_skipped", []) + info.get("footage_skipped", [])]
        self.assertTrue(any("quantitative" in r for r in reasons))


if __name__ == "__main__":
    unittest.main()
