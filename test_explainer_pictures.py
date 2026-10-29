"""Pictures for thin boards (explainer/director/compose_pictures.py, opt-in DirectorOptions.pictures): metrics, upgrade choice, query quality, caps, off-mode. Planning only: no network, no rendering."""
import json
import re
import unittest
from types import SimpleNamespace

from explainer.director import compose_pictures as CP
from explainer.director import select as S
from explainer.director.options import DirectorOptions
from explainer.director.plan import direct
from explainer.director.segment import casing, sentences

SCRIPT = (
    "Napoleon Bonaparte ruled France and most of Europe. "
    "But then he lost the Battle of Waterloo. "
    "Napoleon was exiled to Elba. "
    "The economy slowly changed because of new ideas and habits. "
    "Later he was sent to Saint Helena where he died. "
    "People wondered what it all meant for the future of the continent."
)


def words_for(script, wps=0.4, gap=0.5):
    out, t = [], 0.0
    for sent in re.split(r"(?<=[.!?])\s+", script):
        for w in re.findall(r"[A-Za-z0-9']+", sent):
            out.append([w.lower(), round(t, 3), round(t + wps * 0.9, 3)])
            t += wps
        t += gap
    return out


def item(onset, kind="card", text="x", asset="", style="", rect=(800, 200, 1200, 400), hide=None):
    return SimpleNamespace(kind=kind, onset=onset, text=text, asset=asset, style=style, rect=rect, bbox=rect, hide_at=hide)


class Metrics(unittest.TestCase):
    def test_thin_text_only(self):
        m = CP.thin_beat_metrics([item(0.0, "type", "a", rect=(800, 200, 900, 240))], 5.0)
        self.assertTrue(m["thin"])
        self.assertEqual(m["elements"], 1)
        self.assertEqual(m["text_only_share"], 1.0)
        self.assertGreater(m["longest_still_s"], 2.6)

    def test_busy_board_not_thin(self):
        its = [item(i * 1.0, "card", "w", asset="icon:coin", rect=(760 + i * 200, 150, 760 + i * 200 + 330, 600)) for i in range(5)]
        m = CP.thin_beat_metrics(its, 5.0)
        self.assertFalse(m["thin"], m)
        self.assertEqual(m["pictures"], 5)
        self.assertLessEqual(m["longest_still_s"], 1.0 + 1e-9)


class Queries(unittest.TestCase):
    PH = CP.cased_phrases(SCRIPT)

    def test_phrases(self):
        self.assertEqual(self.PH[:3], ["Napoleon Bonaparte", "Battle of Waterloo", "Saint Helena"])

    def q(self, text, named=None, **kw):
        return CP.build_query(text.lower().split(), self.PH, named if named is not None else {"napoleon", "bonaparte", "waterloo", "elba", "helena", "prussia"}, casing(SCRIPT), **kw)

    def test_full_name(self):
        self.assertEqual(self.q("napoleon bonaparte ruled france")["query"], "Napoleon Bonaparte")
        self.assertEqual(self.q("sent to saint helena where he died")["query"], "Saint Helena")
        self.assertEqual(self.q("he lost the battle of waterloo")["query"], "Battle of Waterloo")

    def test_single_name_when_phrase_not_spoken(self):
        self.assertEqual(self.q("napoleon was exiled to elba")["query"], "Napoleon")

    def test_only_spoken_words(self):
        for text in ("napoleon bonaparte ruled", "prussia sent its army in 1815", "he reached the remote island of elba", "the old ships in the harbour"):
            r = self.q(text)
            self.assertIsNotNone(r)
            self.assertTrue(set(r["words"]) <= set(text.split()), (text, r))

    def test_weak_name_needs_context(self):
        r = self.q("prussia sent its army")
        self.assertEqual(r["query"], "Prussia army")
        self.assertFalse(r["vague"])
        r = self.q("prussia was rising")
        self.assertTrue(r["vague"])
        self.assertNotIn("1815", r["query"])

    def test_vague_words_dropped(self):
        r = self.q("a remote island far away")
        self.assertTrue(r["vague"])
        self.assertNotIn("remote", r["query"])
        r = self.q("the remote harbour town")
        self.assertNotIn("remote", r["query"])

    def test_evidence_word_added_if_spoken(self):
        self.assertEqual(self.q("a portrait of napoleon bonaparte")["query"], "Napoleon Bonaparte portrait")

    def test_max_uses_and_determinism(self):
        a = self.q("napoleon was exiled to elba", avoid={"napoleon": 2})
        self.assertEqual(a["query"], "Elba")
        self.assertEqual(self.q("napoleon was exiled to elba"), self.q("napoleon was exiled to elba"))

    def test_nothing_to_show(self):
        self.assertIsNone(self.q("the economy slowly changed", named=set()))


def run_kinds(script, opt, wps=0.4):
    words = words_for(script, wps)
    total = words[-1][2] + 0.3
    sents = sentences([tuple(w) for w in words], script, total, opt.split_over_s)
    beats = S.group(sents, total, opt)
    info = S.choose_kinds(beats, [tuple(w) for w in words], script, total, opt)
    return beats, info, [tuple(w) for w in words], total


class Upgrade(unittest.TestCase):
    def test_off_is_identical(self):
        b0, i0, _w, _t = run_kinds(SCRIPT, DirectorOptions(footage_share=0.2))
        b1, i1, _w, _t = run_kinds(SCRIPT, DirectorOptions(footage_share=0.2, pictures=False))
        self.assertEqual([b.kind for b in b0], [b.kind for b in b1])
        self.assertNotIn("pictures", i0)
        self.assertNotIn("pictures", i1)

    def test_concrete_chosen_abstract_kept(self):
        opt = DirectorOptions(pictures=True, footage_share=0.0)
        beats, info, words, total = run_kinds(SCRIPT, opt)
        pic = info["pictures"]
        by = {b.id: b for b in beats}
        ups = {r["beat"]: r for r in pic["upgraded"]}
        self.assertTrue(ups, pic)
        for r in ups.values():
            self.assertEqual(r["decision"], "footage")
            self.assertEqual(by[r["beat"]].kind, "footage")
            self.assertTrue(r["query"].split()[0] in ("Napoleon", "Elba", "Saint", "Battle"), r)
        econ = [b for b in beats if "economy" in " ".join(s.text for s in b.sents).lower()]
        self.assertTrue(econ)
        for b in econ:
            if "napoleon" not in " ".join(s.text for s in b.sents).lower():
                self.assertEqual(b.kind, "board")

    def test_elba_beat_becomes_still(self):
        opt = DirectorOptions(pictures=True, min_beat_s=1.0, max_beat_s=3.0)
        beats, info, words, total = run_kinds("This is a story about an emperor. Napoleon was exiled to Elba. The economy slowly changed because of new ideas.", opt)
        fb = [b for b in beats if b.kind == "footage"]
        self.assertTrue(fb, info["pictures"])
        self.assertEqual(fb[0].source, "stock_image")
        self.assertIn(fb[0].picture_query, ("Napoleon", "Elba"))

    def test_caps_and_runs(self):
        script = " ".join(f"Napoleon Bonaparte fought battle {i} at Waterloo." for i in range(12))
        opt = DirectorOptions(pictures=True)
        beats, info, words, total = run_kinds(script, opt)
        kinds = [b.kind for b in beats]
        for i in range(len(kinds) - 2):
            self.assertNotEqual(kinds[i:i + 3], ["footage"] * 3)
        used = sum(b.dur for b in beats if b.kind == "footage")
        self.assertLessEqual(used, max(CP.PICTURE_SHARE * total, opt.max_beat_s) + 1e-6)
        counts = {}
        for b in beats:
            if b.picture_query:
                counts[b.picture_query] = counts.get(b.picture_query, 0) + 1
        self.assertTrue(all(n <= CP.QUERY_MAX_USES for n in counts.values()), counts)

    def test_hook_and_numbers_stay_boards(self):
        opt = DirectorOptions(pictures=True, min_beat_s=1.0)
        beats, info, words, total = run_kinds("Napoleon lost 400000 soldiers. Why did Napoleon fall?", opt)
        self.assertTrue(all(b.kind != "footage" for b in beats), [(b.kind, [s.text for s in b.sents]) for b in beats])


class WholePlan(unittest.TestCase):
    def test_direct_plan_checks(self):
        words = words_for(SCRIPT)
        opt = DirectorOptions(pictures=True, work_dir="/private/tmp/claude-501/s/pics_work")
        res = direct(words, SCRIPT, opt, materialize=False)
        self.assertEqual(res.problems, [], res.problems)
        pic = res.report["pictures"]
        self.assertIn("board_metrics", pic)
        self.assertTrue(pic["queries"], pic)
        beats = {b["id"]: b for b in res.plan["beats"]}
        for bid, ref in pic["queries"].items():
            self.assertEqual(beats[bid]["footage"]["clips"][0]["asset"], ref)

    def test_map_cards_full_name_and_cap(self):
        sc = ("Few stories are stranger than this one, and nobody saw it coming. In 1815 Napoleon Bonaparte was defeated at Waterloo in Belgium, and his army broke, and the troops fled home to France. "
              "He was then sent to Saint Helena, a rock in the Atlantic. Nobody expected him to return from it.")
        res = direct(words_for(sc), sc, DirectorOptions(pictures=True, work_dir="/private/tmp/claude-501/s/pics_work"), materialize=False)
        self.assertEqual(res.problems, [])
        cards = [b for b in res.plan["beats"] if b["mode"] == "map_footage"]
        self.assertTrue(cards)
        for b in cards:
            allc = [b["support"]] + b.get("more_cards", [])
            self.assertLessEqual(len(allc), 2)
        self.assertEqual(cards[0]["support"]["asset"], "stock_image:Napoleon Bonaparte")

    def test_direct_off_has_no_report_key(self):
        words = words_for(SCRIPT)
        res = direct(words, SCRIPT, DirectorOptions(work_dir="/private/tmp/claude-501/s/pics_work"), materialize=False)
        self.assertNotIn("pictures", res.report)
        self.assertNotIn("pictures", res.report["options"])


if __name__ == "__main__":
    unittest.main()
