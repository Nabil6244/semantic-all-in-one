"""Dialogue tests: speech bubbles and the stage spot (explainer/motion/bubbles.py) and the opt-in dialogue pass (explainer/director/compose_dialogue.py).

Offline and deterministic; nothing is encoded (frames are drawn in memory). Also writes a before/after contact sheet to docs/explainer/phase_dialogue_evidence/.
usage: python3 -B explainer/spike/test_motion_bubbles.py   (from the repository root)"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True

from PIL import Image, ImageDraw                                          # noqa: E402
from test_director_real_material import synth                             # noqa: E402
from explainer.board import render as R                                   # noqa: E402
from explainer.board import styles as ST                                  # noqa: E402
from explainer.board.cues import Cue                                      # noqa: E402
from explainer.board.dry import dry_build                                 # noqa: E402
from explainer.director import DirectorOptions                            # noqa: E402
from explainer.director import compose_dialogue as CD                     # noqa: E402
from explainer.director import segment as SG                              # noqa: E402
from explainer.director.segment import norm                               # noqa: E402
from explainer.motion import bubbles as BU                                # noqa: E402

EVIDENCE = ROOT / "docs" / "explainer" / "phase_dialogue_evidence"
SIZE = (1920, 1080)
SCRIPT = ('The delegates gathered in the old hall at dusk. "We must adapt to the new Europe," the minister said. '
          'Then a farmer stood up and shouted "this is nonsense and I will not pay a single coin". Everyone in the village was furious. The long road home began.')
PLAIN = "The delegates gathered in the old hall at dusk. The minister spoke about the new Europe and the farmers listened. The long road home began that summer."


def fig(cid, x, role, pose, idx, flip=False):
    p = {"style": "figure", "cast": role, "pose": pose, "kit": "a", "height": 420, "flip": flip}
    return Cue(cid, "visual", {"index": idx}, role=role, pos=(x, 880 - ST.measure_cartoon("figure", p)["h"]), params=p)


def beat(script, tod="dusk", with_script=True):
    words, dur = synth(script)
    opt = DirectorOptions(look="reference")
    sents = SG.sentences(words, script if with_script else None, dur, opt.split_over_s)
    cues = [Cue("b_set1", "visual", {"index": 0}, pos=(0, 0), offset_s=0.0, params={"style": "set", "set": "room", "tod": tod}),
            fig("b_fig1", 560, "blue", "idle", 0), fig("b_fig2", 1060, "gold", "idle", 3, flip=True)]
    return SimpleNamespace(cues=cues, repairs=[]), words, dur, sents, opt


def run(script, **kw):
    br, words, dur, sents, opt = beat(script, **kw)
    rec = CD.dialogue_pass(br, "b", 0.0, dur, sents, words, opt, CD.new_state())
    return br, words, dur, sents, opt, rec


def build(br, words, dur):
    return dry_build(br.cues, words, 0.0, dur, beat_id="b")


class Bubbles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.br, cls.words, cls.dur, cls.sents, cls.opt, cls.rec = run(SCRIPT)

    def test_a_quote_gets_a_bubble_with_the_contiguous_quote(self):
        self.assertTrue(self.rec["bubbles"], self.rec)
        toks = [norm(w[0]) for w in self.words]
        for b in self.rec["bubbles"]:
            q = [norm(t) for t in b["text"].split()]
            self.assertTrue(any(toks[i:i + len(q)] == q for i in range(len(toks))), b["text"])
        self.assertEqual(self.rec["bubbles"][0]["text"].lower().startswith("we must adapt"), True)

    def test_the_text_fits_in_one_or_two_lines_inside_the_frame(self):
        probs, res, items = build(self.br, self.words, self.dur)
        self.assertEqual(probs, [])
        for it in (i for i in items if i.style == "bubble"):
            self.assertLessEqual(len(it.lines), 2)
            self.assertTrue(96 <= it.rect[0] and it.rect[2] <= 1824 and 96 <= it.rect[1] and it.rect[3] <= 984)

    def test_onset_is_on_the_first_quoted_word(self):
        probs, res, items = build(self.br, self.words, self.dur)
        for b in self.rec["bubbles"]:
            r = next(r for r in res if r.cue.id == b["cue"])
            self.assertGreaterEqual(r.onset_abs - b["t"], -1e-6)
            self.assertLessEqual(r.onset_abs - b["t"], 0.3)

    def test_no_collisions_and_no_problem(self):
        probs, res, items = build(self.br, self.words, self.dur)
        self.assertEqual(probs, [])
        bub = [i for i in items if i.style == "bubble"]
        for b in bub:
            for o in items:
                if o is not b and o.kind == "visual" and o.style in ("figure", "bubble"):
                    self.assertFalse(R.LY.intersects(b.rect, o.rect), (b.cue_id, o.cue_id))

    def test_the_speaker_turns_to_a_speaking_pose(self):
        poses = {c.id: c.params["pose"] for c in self.br.cues if c.params.get("style") == "figure"}
        self.assertIn("point", poses.values())
        for c in self.br.cues:                       # feet still on the stage line
            if c.params.get("style") == "figure":
                self.assertEqual(c.pos[1] + ST.measure_cartoon("figure", c.params)["h"], 880)

    def test_a_cry_word_makes_a_one_line_shout(self):
        br, words, dur, sents, opt, rec = run("The delegates gathered in the old hall at dusk. Everyone in the village was furious about the tax. The long road home began.", with_script=False)
        self.assertEqual([b["text"].lower() for b in rec["bubbles"]], ["furious"], rec)
        _p, _r, items = build(br, words, dur)
        sh = next(i for i in items if i.style == "bubble")
        self.assertEqual(len(sh.lines), 1)
        self.assertEqual(sh.lines[0], "FURIOUS")

    def test_works_without_punctuation_or_capitals(self):
        br, words, dur, sents, opt, rec = run(SCRIPT, with_script=False)          # words only: no quotation marks to read
        self.assertTrue(rec["bubbles"])
        self.assertTrue(all(b["kind"] == "cry" and b["text"].lower() in CD.CRY for b in rec["bubbles"]), rec["bubbles"])

    def test_no_quote_and_no_cry_means_no_bubble_and_no_change(self):
        br, words, dur, sents, opt = beat(PLAIN)
        before = [(c.id, c.pos, dict(c.params)) for c in br.cues]
        rec = CD.dialogue_pass(br, "b", 0.0, dur, sents, words, opt, CD.new_state())
        self.assertEqual(rec["bubbles"], [])
        self.assertEqual(before, [(c.id, c.pos, dict(c.params)) for c in br.cues])

    def test_a_scare_quote_is_not_speech(self):
        br, words, dur, sents, opt = beat('The farmers had to "adapt" to the new Europe and nobody liked it at all.')
        self.assertEqual(CD.dialogue_pass(br, "b", 0.0, dur, sents, words, opt, CD.new_state())["bubbles"], [])

    def test_the_spot_is_added_only_on_a_dusk_set(self):
        self.assertTrue(self.rec["spots"])
        br, words, dur, sents, opt, rec = run(SCRIPT, tod="day")
        self.assertTrue(rec["bubbles"])
        self.assertEqual(rec["spots"], [])

    def test_the_gap_between_bubbles_is_kept(self):
        ts = [b["t"] for b in self.rec["bubbles"]]
        self.assertLessEqual(len(ts), CD.MAX_PER_BEAT)
        self.assertTrue(all(b - a >= CD.MIN_GAP_S - 1e-6 for a, b in zip(ts, ts[1:])))

    def test_a_beat_with_a_problem_is_left_alone(self):
        br, words, dur, sents, opt = beat(SCRIPT)
        br.cues.append(Cue("b_bad", "visual", {"index": 0}, pos=(0, 0), text="x", params={"style": "stamp"}))     # outside the margins
        n = len(br.cues)
        self.assertEqual(CD.dialogue_pass(br, "b", 0.0, dur, sents, words, opt, CD.new_state())["bubbles"], [])
        self.assertEqual(len(br.cues), n)


class Drawing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.br, cls.words, cls.dur, cls.sents, cls.opt, cls.rec = run(SCRIPT)
        cls.probs, cls.res, cls.items = build(cls.br, cls.words, cls.dur)
        cls.bub = next(i for i in cls.items if i.style == "bubble")
        cls.spot = next(i for i in cls.items if i.style == "spot")

    def frame(self, t, items=None):
        return R.draw_frame(items or self.items, t, SIZE, None, int(t * 30), False)

    def test_pop_in_is_deterministic_and_settles(self):
        for v in range(BU.VARIANTS):
            a = [BU.pop_frame(k / 30, v) for k in range(12)]
            self.assertEqual(a, [BU.pop_frame(k / 30, v) for k in range(12)])
            self.assertEqual(a[-1][:2], (1.0, 1.0))
            self.assertEqual(a[-1][2], 0)
            self.assertGreater(len({x for x in a}), 4)
        t = self.bub.onset + 0.1
        self.assertEqual(self.frame(t).tobytes(), self.frame(t).tobytes())
        self.assertNotEqual(self.frame(self.bub.onset).tobytes(), self.frame(self.bub.onset + 0.5).tobytes())

    def test_the_bubble_is_not_drawn_before_its_onset_and_stays_inside_the_frame(self):
        without = [i for i in self.items if i.style not in ("bubble", "spot")]
        t = self.bub.onset - 0.05
        self.assertEqual(self.frame(t).tobytes(), self.frame(t, without).tobytes())
        for k in range(0, 10):
            im = self.frame(self.bub.onset + k / 30)
            self.assertEqual(im.size, SIZE)

    def test_the_spot_is_light_only_inside_its_rect(self):
        without = [i for i in self.items if i.style != "spot"]
        t = self.spot.onset + 0.6
        a, b = self.frame(t), self.frame(t, without)
        from PIL import ImageChops
        bb = ImageChops.difference(a, b).getbbox()
        self.assertIsNotNone(bb)
        r = self.spot.rect
        self.assertTrue(r[0] <= bb[0] and bb[2] <= r[2] and r[1] <= bb[1] and bb[3] <= r[3], (bb, r))
        self.assertTrue(0 <= r[0] and r[2] <= 1920 and 0 <= r[1] and r[3] <= 1080)
        self.assertGreater(sum(ImageChops.subtract(a, b).convert("L").getdata()), 0)        # it adds light, never darkens

    def test_spot_ramps_in_and_is_deterministic(self):
        ps = [BU.spot_power(k / 30) for k in range(0, 20)]
        self.assertEqual(ps, [BU.spot_power(k / 30) for k in range(0, 20)])
        self.assertLess(ps[0], ps[8])

    def test_contact_sheet(self):
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        without = [i for i in self.items if i.style not in ("bubble", "spot")]
        t0 = self.bub.onset
        shots = [("before (no dialogue)", self.frame(t0 + 0.9, without)), ("after, t+0.9 s", self.frame(t0 + 0.9))]
        strip = [self.frame(t0 + k / 30) for k in (0, 2, 4, 6)]
        w, h = 640, 360
        sheet = Image.new("RGB", (w * 2 + 30, h * 2 + 70), (30, 30, 34))
        d = ImageDraw.Draw(sheet)
        for i, (lab, im) in enumerate(shots):
            sheet.paste(im.resize((w, h)), (10 + i * (w + 10), 30))
            d.text((10 + i * (w + 10), 10), lab, fill=(240, 240, 240))
        d.text((10, h + 40), "pop-in frames 0, 2, 4, 6", fill=(240, 240, 240))
        for i, im in enumerate(strip):
            c = im.crop((self.bub.rect[0] - 150, self.bub.rect[1] - 40, self.bub.rect[0] - 150 + 960, self.bub.rect[1] - 40 + 540)).resize((w // 2 + 0, h // 2 + 0))
            sheet.paste(c, (10 + (i % 2) * (w // 2 + 0 + 10), h + 60 + (i // 2) * (h // 2 + 10)))
        cry, words, dur, sents, opt, rec = run("The delegates gathered in the old hall at dusk. Everyone in the village was furious about the tax. The long road home began.", with_script=False)
        _p, _r, its = build(cry, words, dur)
        sh = next(i for i in its if i.style == "bubble")
        sheet.paste(R.draw_frame(its, sh.onset + 0.9, SIZE, None, 0, False).resize((w, h)), (10 + w + 10, h + 60 + 0))
        d.text((10 + w + 10, h + 44), "one-word cry on a dusk set", fill=(240, 240, 240))
        sheet.save(EVIDENCE / "dialogue_before_after.jpg", quality=88)
        self.assertTrue((EVIDENCE / "dialogue_before_after.jpg").exists())


class DefaultPaths(unittest.TestCase):
    def test_old_styles_are_unchanged_and_new_ones_registered(self):
        for s in ("tile", "stamp", "plate", "cross", "figure"):
            self.assertIn(s, ST.STYLES)
        self.assertIn("bubble", ST.STYLES)
        self.assertIn("spot", ST.STYLES)
        self.assertEqual(ST.MOTION_STYLES, ("stamp", "plate", "cross"))
        self.assertIsNone(ST.measure("bubble", "a " * 80, {"px": 52}))


if __name__ == "__main__":
    unittest.main(verbosity=1)
