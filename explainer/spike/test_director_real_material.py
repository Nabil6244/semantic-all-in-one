"""Regression tests for the failures the real-material readiness gate found (docs/explainer/real_material_gate_evidence/): a map of South Lebanon for "Look at Korea", a fly-to for
"the size of England", phrases that ran into the next sentence ("... family business it's", "... strange 80"), a phrase ending on "he's", and a board that ended with no text.

Offline, deterministic, writes only to a temporary folder (materialize=False: no clip is encoded).
usage: python3 -B explainer/spike/test_director_real_material.py   (from the repository root)"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from explainer.beats.relevance import beat_tokens, find_phrase                      # noqa: E402
from explainer.director import DirectorOptions, direct                              # noqa: E402
from explainer.director import compose as CP                                        # noqa: E402
from explainer.director import segment as SG                                        # noqa: E402
from explainer.director import select as SEL                                        # noqa: E402
from explainer.director.segment import norm                                         # noqa: E402

FX = Path(__file__).resolve().parent / "fixtures" / "korea"
SCRIPT = (FX / "script.txt").read_text().strip()
_d = json.loads((FX / "words.json").read_text())
WORDS = [tuple(w) for w in _d["words"]]
DUR = float(_d["duration_s"])
TEXT_KINDS = ("visual", "title", "caption", "card", "header")


def synth(script: str, speed: float = 0.294, pause: float = 0.7, start: float = 0.5):
    """Words with evenly spaced times for a script (punctuation removed, sentence pauses added)."""
    words, t = [], start
    for sent in re.split(r"(?<=[.!?])\s+", script.strip()):
        for tok in sent.split():
            clean = re.sub(r"[^\w']+", "", tok.lower().replace("-", ""))
            if clean:
                words.append((clean, round(t, 3), round(t + speed * 0.85, 3)))
                t += speed
        t += pause
    return words, round(words[-1][2] + 0.4, 3)


def run(words, script, duration, **kw):
    kw.setdefault("look", "reference")
    return direct(words, script, DirectorOptions(**kw), duration=duration, materialize=False)


def map_places(plan):
    """Every place name a plan's map beats show or fly to."""
    out = []
    for b in plan["beats"]:
        if b["mode"] != "map":
            continue
        out += [c.get("place") for c in b.get("camera", []) if c.get("place")]
        for l in b.get("layers", []):
            out += [l["place"]] if l.get("place") else []
            out += list(l.get("places") or [])
    return out


def text_cues(spec_list):
    return [c for c in spec_list if c["kind"] in TEXT_KINDS and c.get("text") and c["text"] != "?"]


def true_owner(words, script, duration):
    """word index -> script sentence index, from the script's own sentence times (hybrid.narration) and each word's midpoint: independent of the director's sentence code."""
    from hybrid.narration import build_sentences
    ss = build_sentences(words, script, duration)
    out = {}
    for i, w in enumerate(words):
        mid = (w[1] + w[2]) / 2
        for s_ in ss:
            if s_.start - 1e-6 <= mid < s_.end + 1e-6:
                out[i] = s_.index
                break
    return out


class KoreaCache:
    _res = {}

    @classmethod
    def get(cls, look="reference"):
        if look not in cls._res:
            cls._res[look] = run(WORDS, SCRIPT, DUR, look=look)
        return cls._res[look]


class PlaceSpotting(unittest.TestCase):
    def test_look_at_korea_is_not_south_lebanon(self):
        r = KoreaCache.get()
        self.assertIsNotNone(r.plan, r.problems)
        names = map_places(r.plan)
        self.assertNotIn("South", names)
        self.assertNotIn("North", names)
        self.assertFalse(any("lebanon" in n.lower() for n in names), names)

    def test_standalone_direction_words_are_not_places(self):
        cands, weak = SEL.place_candidates("The South is blazing with light. The North is dark.", DirectorOptions())
        resolved, ignored = SEL.resolve_places(cands, weak)
        self.assertNotIn("South", resolved)
        self.assertNotIn("North", resolved)
        self.assertTrue(any(i.startswith("South") and "direction" in i for i in ignored), ignored)

    def test_direction_word_inside_a_name_still_resolves(self):
        cands, weak = SEL.place_candidates("They fled from North Korea to South Korea.", DirectorOptions())
        resolved, _ig = SEL.resolve_places(cands, weak)
        self.assertIn("North Korea", resolved)
        self.assertIn("South Korea", resolved)

    def test_size_comparison_is_not_a_fly_to(self):
        words, dur = synth("It was a black hole the size of England where people should be. Then the lights went out.")
        r = run(words, "It was a black hole the size of England where people should be. Then the lights went out.", dur, fallback_place="Europe")
        self.assertIsNotNone(r.plan, r.problems)
        self.assertNotIn("England", map_places(r.plan))
        self.assertIn("England", " ".join(r.report["selection"].get("places_comparison", [])))

    def test_england_as_a_destination_still_gets_a_map(self):
        s = ("Then the ship sailed to England. The crew landed at the port and walked into the market. Nobody there had seen such a large vessel before. "
             "The harbour master counted the barrels and wrote down the cost. By evening the whole town knew the news. People gathered along the quay to look at the sails.")
        words, dur = synth(s)
        r = run(words, s, dur, max_map_share=0.5)
        self.assertIsNotNone(r.plan, r.problems)
        self.assertIn("England", map_places(r.plan))

    def test_north_and_south_korea_stay_distinct(self):
        s = "The border runs between North Korea and South Korea. Nobody crosses it."
        words, dur = synth(s)
        cands, weak = SEL.place_candidates(s, DirectorOptions())
        resolved, _ig = SEL.resolve_places(cands, weak)
        beat = SEL.BeatPlan("e1", 0.0, dur, [])
        hits = SEL.places_in(beat, words, resolved)
        self.assertEqual(sorted(h.name for h in hits), ["North Korea", "South Korea"])

    def test_unresolvable_place_is_never_substituted(self):
        s = "Look at Korea from space at night. The city lights are bright."
        words, dur = synth(s)
        cands, weak = SEL.place_candidates(s, DirectorOptions())
        resolved, ignored = SEL.resolve_places(cands, weak)
        self.assertNotIn("Korea", resolved)
        self.assertTrue(any(i.startswith("Korea") for i in ignored))
        r = run(words, s, dur)
        self.assertIsNotNone(r.plan, r.problems)
        self.assertFalse(any("korea" in n.lower() for n in map_places(r.plan)), map_places(r.plan))
        self.assertTrue(any("arbitrary fallback" in w for w in r.warnings + r.report["selection"].get("warnings", [])), "the required opening map must be reported as an arbitrary fallback")

    def test_budget_never_hides_a_relevant_place_without_a_reason(self):
        s = ("The empire of Rome was the largest of the ancient world. The river city of Paris grew slowly in those years. Traders visited Cairo beside the great river for centuries. "
             "A small town called Berlin was nothing then. The fortress of Madrid was only a border post at first.")
        words, dur = synth(s)
        r = run(words, s, dur, max_map_share=0.15)
        self.assertIsNotNone(r.plan, r.problems)
        sel = r.report["selection"]
        shown = set(map_places(r.plan))
        not_shown = {d["place"]: d["reason"] for d in sel.get("places_not_shown", [])}
        for name in ("Rome", "Paris", "Cairo", "Berlin", "Madrid"):
            self.assertTrue(name in shown or name in not_shown, f"{name} is neither on a map nor explained: shown={shown} not_shown={not_shown}")
        for reason in not_shown.values():
            self.assertTrue(reason.strip())


class SentenceAndPhraseHygiene(unittest.TestCase):
    def test_a_word_that_touches_the_sentence_boundary_belongs_to_the_next_sentence(self):
        ss = SG.sentences(WORDS, SCRIPT, DUR, 8.0)
        text = [" ".join(WORDS[i][0] for i in s.widx) for s in ss]
        self.assertTrue(any(t.startswith("that dark country") for t in text), text)
        self.assertFalse(any(t.endswith(" that") for t in text), text)
        self.assertFalse(any(t.endswith("family business it's") for t in text), text)
        self.assertFalse(any(t.endswith("truly strange 80") for t in text), text)

    def test_every_phrase_stays_inside_one_sentence(self):
        for look in ("reference", "classic"):
            r = KoreaCache.get(look)
            self.assertIsNotNone(r.plan, r.problems)
            owner = true_owner(WORDS, SCRIPT, DUR)
            for bid, d in r.report["beat_details"].items():
                for ph in d.get("phrases", []) if isinstance(d, dict) else []:
                    self.assertEqual(owner[ph["first"]], owner[ph["last"]], f"{look} {bid}: {ph['phrase']!r} crosses a sentence boundary")

    def test_map_captions_do_not_cross_sentences(self):
        owner = true_owner(WORDS, SCRIPT, DUR)
        for look in ("reference", "classic"):
            r = KoreaCache.get(look)
            for b in r.plan["beats"]:
                for l in b.get("layers", []) if b["mode"] == "map" else []:
                    if l["type"] != "caption":
                        continue
                    tk = beat_tokens(WORDS, b["start"], b["end"])
                    m = find_phrase(tk, l["text"])
                    self.assertIsNotNone(m, l["text"])
                    self.assertEqual(len({owner[i] for i in m["word_indices"]}), 1, f"{look} {b['id']}: map caption {l['text']!r} crosses a sentence")

    def test_map_caption_repair_stays_inside_a_sentence_on_a_small_script(self):
        s = "Then the ship sailed to England. The crew landed at the port and walked into the market. Nobody there had seen such a large vessel before."
        words, dur = synth(s)
        owner = true_owner(words, s, dur)
        r = run(words, s, dur, max_map_share=1.0)
        self.assertIsNotNone(r.plan, r.problems)
        for b in r.plan["beats"]:
            for l in b.get("layers", []) if b["mode"] == "map" else []:
                if l["type"] == "caption":
                    m = find_phrase(beat_tokens(words, b["start"], b["end"]), l["text"])
                    self.assertEqual(len({owner[i] for i in m["word_indices"]}), 1, l["text"])

    def test_no_phrase_ends_on_a_dangling_contraction(self):
        dangling = re.compile(r"(?:^|\s)(?:it|he|she|that|there|here|what|who|where|how|let|i|you|we|they)['’](?:s|m|re|ve|ll|d)$", re.I)
        for look in ("reference", "classic"):
            r = KoreaCache.get(look)
            for bid, d in r.report["beat_details"].items():
                for c in text_cues(d.get("cue_specs", []) if isinstance(d, dict) else []):
                    self.assertIsNone(dangling.search(c["text"].strip()), f"{look} {bid}: {c['text']!r}")

    def test_best_phrases_never_ends_on_a_contraction(self):
        words, _d = synth("Its founder died in 1994 and officially he's still its eternal leader.")
        # a clause that ends right after the contraction: "... officially he's"
        idx = list(range(0, 8))
        got = CP.best_phrases(idx, words, {}, {}, {7}, k=2, max_words=8)
        for p in got:
            self.assertFalse(p.text.split()[-1].lower().endswith(("'s", "'re", "'ve", "'ll", "'d", "'m")), p.text)

    def test_phrases_are_contiguous_quotes_of_their_beat(self):
        r = KoreaCache.get()
        for b in r.report["selection"]["beats"]:
            d = r.report["beat_details"].get(b["id"])
            if not isinstance(d, dict) or "cue_specs" not in d:
                continue
            tk = beat_tokens(WORDS, b["start"], b["end"])
            for c in text_cues(d["cue_specs"]):
                t = c["text"].lower() if c["kind"] == "title" else c["text"]
                self.assertIsNotNone(find_phrase(tk, t), f"{b['id']}: {c['text']!r} is not a contiguous quote of its beat")

    def test_caption_matches_stay_in_the_anchor_sentence(self):
        from explainer.board.cues import Cue
        from explainer.board.dry import dry_build
        r = KoreaCache.get()
        owner = true_owner(WORDS, SCRIPT, DUR)
        for b in r.report["selection"]["beats"]:
            d = r.report["beat_details"].get(b["id"])
            if not isinstance(d, dict) or "cue_specs" not in d:
                continue
            bw = [i for i, w in enumerate(WORDS) if b["start"] - 1e-6 <= w[1] < b["end"] - 1e-6]
            cues = [Cue(**{k: (tuple(v) if k == "pos" and v else v) for k, v in s.items()}) for s in d["cue_specs"]]
            probs, resolved, _items = dry_build(cues, WORDS, b["start"], b["end"], beat_id=b["id"])
            self.assertEqual(probs, [])
            for rc in resolved:
                rec = rc.caption
                if not rec or not rec.get("matched"):
                    continue
                anchor_sent = owner[bw[rc.cue.anchor["index"]]]
                for m in rec["matched"]:
                    self.assertEqual(owner[m["narration_index"]], anchor_sent, f"{b['id']} {rc.cue.id}: matched word {m} leaves sentence {anchor_sent}")

    def test_short_sentences_punctuation_repeats_and_the_final_sentence(self):
        s = ("Go. Go now! The harbour was quiet at dawn and the ships were ready to sail. Same language, same food, same families. Traders carried news along the coast every season. "
             "The old roads were crowded with carts and walkers. It's over. So,")
        words, dur = synth(s)
        r = run(words, s, dur)
        self.assertIsNotNone(r.plan, r.problems)
        self.assertEqual(r.problems, [])
        specs = [c for d in r.report["beat_details"].values() if isinstance(d, dict) for c in text_cues(d.get("cue_specs", []))]
        self.assertTrue(any("same" in c["text"].lower() for c in specs), [c["text"] for c in specs])
        for c in specs:
            self.assertNotIn(norm(c["text"].split()[-1]), {"so", "it's"}, c["text"])


class EmptyAndCrowdedBoards(unittest.TestCase):
    def _board_sentences(self, r):
        sents = SG.sentences(WORDS, SCRIPT, DUR, 8.0)
        out = []
        for b in r.report["selection"]["beats"]:
            if b["kind"] != "board":
                continue
            d = r.report["beat_details"][b["id"]]
            bw = [i for i, w in enumerate(WORDS) if b["start"] - 1e-6 <= w[1] < b["end"] - 1e-6]
            have = set()
            for c in text_cues(d["cue_specs"]):
                a = c["anchor"]
                if "index" in a and a["index"] < len(bw):
                    have.add(bw[a["index"]])
            for s in sents:
                if b["start"] - 1e-6 <= s.start < b["end"] - 1e-6:
                    content = [norm(WORDS[i][0]) for i in s.widx if norm(WORDS[i][0]) not in {"so", "and", "the", "a"}]
                    out.append((b["id"], s, len(content) >= 3 and not (have & set(s.widx))))
        return out

    def test_every_narrated_board_sentence_with_content_has_text(self):
        r = KoreaCache.get()
        empty = [(bid, " ".join(WORDS[i][0] for i in s.widx)) for bid, s, is_empty in self._board_sentences(r) if is_empty]
        self.assertEqual(empty, [], f"board sentences with no text: {empty}")

    def test_the_final_board_has_meaningful_text(self):
        r = KoreaCache.get()
        last = [b for b in r.report["selection"]["beats"] if b["kind"] == "board"][-1]
        d = r.report["beat_details"][last["id"]]
        self.assertTrue(text_cues(d["cue_specs"]), "the final board carries no text")
        self.assertGreater(d["peak_occupancy_share"], 0.05)

    def test_dropped_text_is_rescued_not_lost(self):
        """Force every authored text cue off the board (an unreachable position, so the layout gate drops all of them) and require a deterministic rescue that keeps the collision gate on."""
        from explainer.director import compose_ref as CR
        real = CR.author_ref

        def hostile(*a, **k):
            res = real(*a, **k)
            for c in res.cues:
                if c.kind in ("visual", "title") and c.pos is not None:
                    c.pos = (3000, 3000)
            return res
        CR.author_ref = hostile
        try:
            r = run(WORDS, SCRIPT, DUR)
        finally:
            CR.author_ref = real
        self.assertIsNotNone(r.plan, r.problems)
        for b in r.report["selection"]["beats"]:
            if b["kind"] != "board":
                continue
            d = r.report["beat_details"][b["id"]]
            self.assertTrue(text_cues(d["cue_specs"]), f"{b['id']}: every text cue was lost")
            self.assertTrue(d.get("rescued"), f"{b['id']}: the loss is not reported")
            self.assertEqual(d["problems"], [])

    def test_rescue_keeps_collision_checking(self):
        from explainer.board.cues import Cue
        from explainer.board.dry import dry_build
        r = KoreaCache.get()
        for b in r.report["selection"]["beats"]:
            d = r.report["beat_details"].get(b["id"])
            if not isinstance(d, dict) or "cue_specs" not in d:
                continue
            cues = [Cue(**{k: (tuple(v) if k == "pos" and v else v) for k, v in s.items()}) for s in d["cue_specs"]]
            probs, _res, _items = dry_build(cues, WORDS, b["start"], b["end"], beat_id=b["id"])
            self.assertEqual(probs, [], f"{b['id']}: {probs[:1]}")

    def test_a_crowded_sentence_keeps_its_important_phrases_or_says_why_not(self):
        r = KoreaCache.get()
        for bid, d in r.report["beat_details"].items():
            if not isinstance(d, dict) or "dropped" not in d:
                continue
            authored = [x for x in d["dropped"] if not re.search(r"_r\d", x["cue"])]
            if authored:
                self.assertTrue(d.get("rescued") is not None, f"{bid}: authored cues were dropped and nothing says what happened")


class Determinism(unittest.TestCase):
    def test_same_inputs_same_plan(self):
        a = run(WORDS, SCRIPT, DUR)
        b = run(WORDS, SCRIPT, DUR)
        self.assertEqual(json.dumps(a.plan, sort_keys=True), json.dumps(b.plan, sort_keys=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
