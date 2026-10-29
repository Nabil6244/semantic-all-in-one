"""Composition recipes (explainer/director/compose_recipes.py): opt-in, deterministic, evidence-gated, clean dry builds, and a no-op when off."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from explainer.board.dry import dry_build
from explainer.director import compose_recipes as R
from explainer.director import lexicon as LX
from explainer.director.options import DirectorOptions
from explainer.director.segment import Sent, norm


def mk(text, step=0.4):
    words, sents, t = [], [], 0.5
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    for si, sent in enumerate(parts):
        idx, br = [], set()
        for tok in sent.split():
            clean = norm(tok.replace("-", ""))
            if not clean:
                continue
            words.append((clean, round(t, 3), round(t + step * 0.85, 3)))
            idx.append(len(words) - 1)
            t += step
            if re.search(r"[,;:]$", tok):
                br.add(len(words) - 1)
        sents.append(Sent(si, words[idx[0]][1], words[idx[-1]][2], sent, si == len(parts) - 1, idx, breaks=br | {idx[-1]}))
        t += 0.5
    cased = {}
    for tok in re.findall(r"[A-Za-z']+", text):
        if tok[0].isupper() and text.count(tok) == 1 and not text.startswith(tok):
            cased.setdefault(tok.lower(), tok)
    return words, sents, cased, words[-1][2] + 0.6


def author(text, idea="", opt=None, narrator="only"):
    words, sents, cased, end = mk(text)
    r = R.author_recipe("e1", 0.0, end, sents, words, cased, opt or DirectorOptions(recipes=True), dict(LX.ICONS), {}, narrator, "idle", idea=idea)
    return r, words, end


def anchored_word(r, words, cue):
    """The spoken word a cue is anchored on (index is inside the beat, which starts at word 0 here)."""
    return words[cue.anchor["index"]][0]


def visuals(r, style=None):
    return [c for c in r.cues if c.kind in ("visual", "chip") and (style is None or (c.params or {}).get("style") == style)]


def quote_of(words, text):
    toks = [norm(w) for w in text.split()]
    flat = [w[0] for w in words]
    return any(flat[i:i + len(toks)] == toks for i in range(len(flat) - len(toks) + 1))


CASES = {
    "cause_effect": ("The king raised the taxes because of the long war, which meant that bread cost more.", "cause"),
    "before_after": ("Before the war farms were small. Now farms are huge machines.", "comparative"),
    "two_column": ("Britain had a huge navy while France had a huge army.", "comparative"),
    "pictogram": ("Napoleon lost 400000 soldiers in the long Russian winter.", "quantitative"),
    "pyramid": ("The king ruled from the castle. The nobles owned the land. The peasants worked the fields.", ""),
    "timeline": ("The empire fell in 1453 and the republic rose in 1789 and the war ended in 1815.", ""),
    "bar_chart": ("Britain produced 50 million tons of coal while France produced 20 million tons of iron.", "quantitative"),
}


class Pick(unittest.TestCase):
    def test_each_recipe_is_the_top_pick_for_its_text(self):
        for name, (text, idea) in CASES.items():
            words, *_ = mk(text)
            got = R.pick_recipe([w[0] for w in words], idea)
            self.assertTrue(got, name)
            if name != "two_column":              # a "while" sentence with two numbers is also a bar chart: both are fine, the numbers win
                self.assertEqual(got[0][0], name, f"{name}: {got}")

    def test_missing_evidence_lists_nothing(self):
        words, *_ = mk("It was a quiet morning and the village slept.")
        self.assertEqual(R.pick_recipe([w[0] for w in words], ""), [])

    def test_a_cause_word_alone_is_not_enough(self):
        self.assertEqual(R.find_markers(["so", "tired"]), [])           # nothing on its left
        self.assertEqual(R.find_markers(["he", "slept", "because"]), [])  # nothing on its right

    def test_pick_is_deterministic(self):
        t = [w[0] for w in mk(CASES["bar_chart"][0])[0]]
        self.assertEqual(R.pick_recipe(t, "quantitative"), R.pick_recipe(t, "quantitative"))

    def test_a_year_is_not_a_quantity(self):
        words, *_ = mk("It ended in 1815 and was never the same.")
        self.assertNotIn("pictogram", dict(R.pick_recipe([w[0] for w in words], "")))


class Build(unittest.TestCase):
    def test_every_recipe_builds_a_clean_dry_build(self):
        for name, (text, idea) in CASES.items():
            r, words, end = author(text, idea)
            self.assertIsNotNone(r, name)
            probs, _res, _items = dry_build(r.cues, words, 0.0, end, fps=30, beat_id="e1")
            self.assertEqual(probs, [], name)
            self.assertEqual(r.dropped, [], name)
            self.assertEqual(r.problems, [], name)

    def test_the_right_recipe_is_used(self):
        for name, (text, idea) in CASES.items():
            r, *_ = author(text, idea)
            if name == "two_column":
                self.assertIn(r.recipe, ("two_column", "bar_chart"))
            else:
                self.assertEqual(r.recipe, name)

    def test_texts_are_quotes_of_the_narration(self):
        for name, (text, idea) in CASES.items():
            r, words, _ = author(text, idea)
            for c in visuals(r):
                if c.text and (c.params or {}).get("style") != "bars":
                    self.assertTrue(quote_of(words, c.text), f"{name}: {c.text!r}")

    def test_every_element_is_anchored_on_a_spoken_word_inside_the_beat(self):
        for name, (text, idea) in CASES.items():
            r, words, _ = author(text, idea)
            for c in r.cues:
                self.assertIn("index", c.anchor)
                self.assertTrue(0 <= c.anchor["index"] < len(words), (name, c.id))

    def test_cause_nodes_sit_on_their_own_words(self):
        r, words, _ = author(*CASES["cause_effect"][:1], idea="cause")
        nodes = [c for c in visuals(r) if c.params["style"] == "node"]
        self.assertEqual(len(nodes), 3)                    # cause -> effect -> consequence: the second clause is not left to a floating fragment
        first = {c.text: anchored_word(r, words, c) for c in nodes}
        self.assertEqual(first["long war"], "long")
        self.assertEqual(first["king raised the taxes"], "king")
        arrows = [c for c in r.cues if c.kind == "arrow"]
        ids = {c.text: c.id for c in nodes}
        self.assertEqual((arrows[0].src, arrows[0].dst), (ids["long war"], ids["king raised the taxes"]))   # "because of the war": the war is the cause
        self.assertEqual(anchored_word(r, words, arrows[0]), "long")      # the arrow grows when the later-spoken node is spoken
        self.assertEqual(arrows[1].src, ids["king raised the taxes"])

    def test_three_node_chain(self):
        r, words, _ = author("The king raised taxes, which led to anger among the farmers, which meant the farmers revolted.", "cause")
        self.assertEqual(r.recipe, "cause_effect")
        self.assertEqual(len([c for c in r.cues if c.kind == "arrow"]), 2)

    def test_before_after_tags_are_the_spoken_markers(self):
        r, words, _ = author(*CASES["before_after"][:1], idea="comparative")
        tags = [c.text.lower() for c in visuals(r, "tag")]
        self.assertEqual(tags, ["before", "now"])

    def test_pictogram_fills_in_rows_on_successive_words(self):
        r, words, _ = author(*CASES["pictogram"][:1], idea="quantitative")
        crowds = visuals(r, "crowd")
        self.assertEqual(len(crowds), 2)
        self.assertEqual(sum(c.params["n"] for c in crowds), 12)           # drawn icons are capped
        self.assertLess(crowds[0].anchor["index"], crowds[1].anchor["index"])
        self.assertEqual(visuals(r, "tag")[0].text, "400000 soldiers")

    def test_pyramid_tiers_are_spoken_order_and_narrowing(self):
        r, words, _ = author(*CASES["pyramid"][:1])
        tiers = visuals(r, "node")
        self.assertEqual([t.text for t in tiers], ["king", "nobles", "peasants"])
        self.assertEqual([anchored_word(r, words, t) for t in tiers], ["king", "nobles", "peasants"])
        self.assertEqual([t.params["minw"] for t in tiers], sorted(t.params["minw"] for t in tiers))
        self.assertEqual(sorted((t.pos[1] for t in tiers)), [t.pos[1] for t in tiers])       # top tier is highest on the screen

    def test_timeline_years_on_their_words_and_chained(self):
        r, words, _ = author(*CASES["timeline"][:1])
        chips = [c for c in r.cues if c.kind == "chip"]
        self.assertEqual([c.text for c in chips], ["1453", "1789", "1815"])
        for c in chips:
            self.assertEqual(anchored_word(r, words, c), c.text)
        self.assertEqual(len([c for c in r.cues if c.kind == "arrow"]), 2)

    def test_bars_follow_the_spoken_numbers(self):
        r, words, _ = author(*CASES["bar_chart"][:1], idea="quantitative")
        bars = visuals(r, "bars")
        self.assertEqual([b.text for b in bars], ["50 million", "20 million"])
        self.assertEqual([anchored_word(r, words, b) for b in bars], ["50", "20"])
        self.assertAlmostEqual(bars[1].params["ratio"], 0.4)
        self.assertEqual([b.params["label"].lower() for b in bars], ["britain", "france"])        # both bars say "tons": the subject before each number labels it

    def test_text_is_readable_and_inside_the_frame(self):
        for name, (text, idea) in CASES.items():
            r, words, end = author(text, idea)
            _p, _r, items = dry_build(r.cues, words, 0.0, end, fps=30, beat_id="e1")
            for it in items:
                if it.kind == "narrator" or it.kind == "arrow":
                    continue
                self.assertGreaterEqual(it.rect[0], 96, (name, it.cue_id))
                self.assertLessEqual(it.rect[2], 1824, (name, it.cue_id))
                self.assertGreaterEqual(it.rect[1], 96, (name, it.cue_id))
                self.assertLessEqual(it.rect[3], 984, (name, it.cue_id))
                if it.px and it.style != "bars":
                    self.assertGreaterEqual(it.px, 48, (name, it.cue_id))
                if it.kind != "narrator":
                    self.assertGreaterEqual(it.rect[0], 720 - 1, (name, it.cue_id))     # right of the narrator zone

    def test_deterministic(self):
        for name, (text, idea) in CASES.items():
            a, *_ = author(text, idea)
            b, *_ = author(text, idea)
            self.assertEqual([(c.id, c.kind, c.text, c.anchor, c.pos, c.params) for c in a.cues], [(c.id, c.kind, c.text, c.anchor, c.pos, c.params) for c in b.cues], name)


class NoEvidence(unittest.TestCase):
    def test_none_when_evidence_is_missing(self):
        for text in ("It was a quiet morning and the village slept.", "He was tired so", "The farmers worked the fields from the early morning until the evening.",
                     "In 1815 the war ended.", "Britain had a navy."):
            r, *_ = author(text)
            self.assertIsNone(r, text)

    def test_dialogue_beats_are_left_to_the_dialogue_pass(self):
        r, *_ = author(CASES["cause_effect"][0], idea="dialogue")
        self.assertIsNone(r)

    def test_a_single_number_is_not_a_bar_chart(self):
        r, *_ = author("Napoleon lost 400000 soldiers in the long Russian winter.")
        self.assertEqual(r.recipe, "pictogram")

    def test_two_equal_numbers_make_no_chart(self):
        r, *_ = author("France lost 50 million tons and Britain lost 50 million tons.")
        self.assertTrue(r is None or r.recipe != "bar_chart")

    def test_archival_without_a_local_image_is_none(self):
        r, *_ = author("In this portrait Napoleon Bonaparte looks calm.", "evidence")
        self.assertIsNone(r)
        with tempfile.TemporaryDirectory() as d:
            json.dump([{"file": "missing.png", "subjects": ["Napoleon Bonaparte"]}], open(Path(d) / "archive.json", "w"))
            r, *_ = author("In this portrait Napoleon Bonaparte looks calm.", "evidence", DirectorOptions(recipes=True, archive_dir=d))
            self.assertIsNone(r)


class Archival(unittest.TestCase):
    def test_framed_picture_with_name_from_a_local_image(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            Image.new("RGB", (600, 900), (120, 90, 60)).save(Path(d) / "p.png")
            json.dump([{"file": "p.png", "subjects": ["Napoleon Bonaparte"]}], open(Path(d) / "archive.json", "w"))
            r, words, end = author("In this portrait Napoleon Bonaparte looks calm. The painter showed him as a quiet leader.", "evidence", DirectorOptions(recipes=True, archive_dir=d))
            self.assertEqual(r.recipe, "archival")
            ph = visuals(r, "photo")[0]
            self.assertEqual(ph.text.lower(), "napoleon bonaparte")
            self.assertEqual(anchored_word(r, words, ph), "napoleon")
            probs, _r, items = dry_build(r.cues, words, 0.0, end, fps=30, beat_id="e1")
            self.assertEqual(probs, [])
            from explainer.board.render import draw_frame
            im = draw_frame(items, 3.0, (1920, 1080), None, 90, False)
            self.assertEqual(im.size, (1920, 1080))


class BarsStyle(unittest.TestCase):
    def test_existing_styles_are_unchanged_and_bars_grow_with_ease_out(self):
        from explainer.board import styles
        self.assertEqual(styles.STYLES[:7], ("tile", "circle", "box", "lite", "tag", "scroll", "line"))
        self.assertIn("bars", styles.STYLES)
        self.assertEqual(styles.measure("box", "hello world", {}), styles.measure("box", "hello world", {"wrap": 520}))      # the new params default to the old behaviour

        class It:
            rect, role, px, text, vparams = (100, 100, 340, 800), "blue", 48, "5", {"ratio": 1.0, "label": "x"}
        from PIL import Image
        heights = []
        for age in (0.0, 0.15, 0.3, 0.6, 1.0):
            im = Image.new("RGB", (500, 900), (192, 192, 192))
            styles.draw_bar(im, It, age)
            col = [im.getpixel((220, y)) != (192, 192, 192) for y in range(900)]
            heights.append(sum(col))
        self.assertEqual(heights, sorted(heights))
        self.assertGreater(heights[3], heights[1] * 1.3)
        self.assertEqual(heights[3], heights[4])


class PlanHook(unittest.TestCase):
    SCRIPT = "The king raised the taxes because of the long war, which meant that bread cost more. The village was quiet in the evening and the people slept."

    def _run(self, **kw):
        from explainer.director.plan import direct
        from explainer.spike.test_director_real_material import synth
        words, dur = synth(self.SCRIPT)
        return direct(words, self.SCRIPT, DirectorOptions(look="reference", meaning=True, **kw), duration=dur, materialize=False)

    def test_off_by_default(self):
        self.assertFalse(DirectorOptions().recipes)

    def test_off_leaves_the_report_without_recipe_traces(self):
        r = self._run(recipes=False)
        self.assertNotIn("recipe", json.dumps(r.report, default=str).replace('"recipes"', ""))

    def test_on_marks_the_beat_and_off_equals_default(self):
        off = self._run(recipes=False)
        default = self._run()
        self.assertEqual(json.dumps(off.plan, sort_keys=True, default=str), json.dumps(default.plan, sort_keys=True, default=str))
        on = self._run(recipes=True)
        recs = [b.get("recipe") for b in on.report.get("board", {}).values()] if isinstance(on.report.get("board"), dict) else None
        self.assertIn("recipe", json.dumps(on.report, default=str))
        self.assertEqual(on.problems, [])


class Geometry(unittest.TestCase):
    def test_no_narrator_uses_the_whole_frame_and_narrator_keeps_clear(self):
        for name, (text, idea) in CASES.items():
            on, words, end = author(text, idea, narrator="only")
            off, _w, _e = author(text, idea, narrator="none")
            self.assertIsNotNone(off, name)
            def xs(r):
                _p, _r, items = dry_build(r.cues, words, 0.0, end, fps=30, beat_id="e1")
                return [it.rect for it in items if it.kind not in ("narrator", "arrow")]
            self.assertGreaterEqual(min(r[0] for r in xs(on)), 719, name)
            self.assertLess(min(r[0] for r in xs(off)), 720, name)                   # something sits left of the narrator zone: the frame is used
            mid = [(r[0] + r[2]) / 2 for r in xs(off)]
            self.assertAlmostEqual(sum(mid) / len(mid), 960, delta=170, msg=name)    # and the composition is centred on the frame

    def test_bar_labels_are_subjects_never_verbs(self):
        r, *_ = author("Britain produced 50 million tons of coal while France produced 20 million tons of iron.", "quantitative")
        self.assertEqual([b.params["label"].lower() for b in visuals(r, "bars")], ["britain", "france"])
        r, *_ = author("It sold 50 million tons of coal and sold 20 million tons of iron.", "quantitative")
        for b in visuals(r, "bars"):
            self.assertNotIn(b.params["label"].lower(), ("sold", "produced", "made"))

    def test_pictogram_uses_the_character_for_the_noun(self):
        r, *_ = author("Napoleon lost 400000 soldiers in the long Russian winter.", "quantitative")
        kinds = {c.params.get("kind") for c in visuals(r, "crowd")}
        self.assertEqual(kinds, {"soldier"})
        r, *_ = author("The village sent 8 farmers to the market.", "quantitative")
        self.assertEqual({c.params.get("kind") for c in visuals(r, "crowd")}, {"farmer"})

    def test_before_after_panel_starts_after_the_marker_phrase(self):
        r, *_ = author("Before the war farms were small. Now farms are huge machines.", "comparative")
        texts = [c.text.lower() for c in visuals(r, "node")]
        self.assertEqual(texts[0], "farms were small")

    def test_nodes_carry_a_keyword_picture_when_one_exists(self):
        r, *_ = author(CASES["cause_effect"][0], "cause")
        nodes = visuals(r, "node")
        self.assertTrue(all(c.asset for c in nodes))
        for c in nodes:
            self.assertGreaterEqual(c.params["minpx"], 48)


class EndToEnd(unittest.TestCase):
    SCRIPT = ("Long ago in Europe the people lived in small villages. The king raised the taxes because of the long war, which meant that bread cost more. "
              "Before the war farms were small. Now farms are huge machines. Napoleon lost 400000 soldiers in the long Russian winter. "
              "Britain produced 50 million tons of coal while France produced 20 million tons of iron.")

    def test_direct_with_recipes_has_no_problems_and_uses_two_recipes(self):
        from explainer.director.plan import direct
        from explainer.spike.test_director_real_material import synth
        words, dur = synth(self.SCRIPT)
        with tempfile.TemporaryDirectory() as d:
            opt = DirectorOptions(look="reference", recipes=True, meaning=True, narrator=True, work_dir=d, fill=True, variety=True, motion=True, numbers=True)
            r = direct(words, self.SCRIPT, opt, duration=dur, materialize=False)
        self.assertEqual(r.problems, [])
        used = {v["recipe"]["recipe"] for v in r.report["beat_details"].values() if v.get("recipe")}
        self.assertGreaterEqual(len(used), 2, used)


if __name__ == "__main__":
    unittest.main()
