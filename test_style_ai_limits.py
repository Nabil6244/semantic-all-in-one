"""A style's opt-in AI limits (selection_rules.real_subjects / max_ai_share / max_ai_run / artworks). Visual correctness
first: real things go to real sources; over the limits a reconstruction gives way only to a real artwork known to show
its subject, else it stays AI -- never to unrelated stock. A style without the rules allocates exactly as before."""

import csv
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import visual_allocation.allocator as A
from style_engine import resolve_style
from style_engine.loader import load_style
from visual_allocation import apply_allocation_to_plan, load_allocation_settings
from visual_director.schema import parse_visual_plan

NARR = ["The Watchers descended in a storm of fire.",                    # artwork: Blake
        "Their giant children walked the earth.",                        # no artwork
        "Angels bound the leader and cast him into darkness.",           # artwork: Doré, rebel angels
        "A house of crystal stood among flames.",                        # no artwork
        "A great abyss opened with pillars of fire.",                    # artwork: John Martin
        "The stars of heaven were imprisoned in the dark.",              # no artwork
        "The archangels cried out to heaven.",                           # artwork: Reni
        "Ethiopic manuscripts kept the book alive.",                     # real
        "Snow lay on the summit of Mount Hermon.",                       # real
        "Scholars studied the Dead Sea Scrolls.",                        # real
        "The flood swept over the world.",                               # artwork: Doré, Deluge
        "The giants fought among themselves in the night."]              # no artwork
REAL = {8, 9, 10}
AI = ("image", "video")


def plan():
    scenes = [{"scene_id": i + 1, "narration": t, "visual_goal": t, "visual_description": t + " dramatic cinematic scene",
               "importance": "high", "asset_type": "video", "provider_preference": "flow_video"} for i, t in enumerate(NARR)]
    return parse_visual_plan({"title": "t", "scenes": scenes})


def allocate(style_id, limits=True):
    p = plan()
    with mock.patch.object(A, "_apply_style_ai_limits", A._apply_style_ai_limits if limits else (lambda *a, **k: {})):
        b = apply_allocation_to_plan(p, load_allocation_settings(None), resolve_style(mode="manual", style_id=style_id, script=""))
    return p, {d.scene_id: d for d in b.decisions}


class StyleAILimits(unittest.TestCase):
    def setUp(self):
        self.rules = load_style("book_of_enoch").selection_rules
        self.plan, self.after = allocate("book_of_enoch")
        _, self.before = allocate("book_of_enoch", limits=False)          # the same allocation without the rules
        self.artwork = {sid for sid, d in self.after.items() if A.ARTWORK_REASON in d.reason}

    def test_1_a_real_historical_subject_goes_to_a_real_source(self):
        for sid in REAL:
            self.assertNotIn(self.after[sid].asset_type, AI, f"scene {sid}: {self.after[sid].reason}")

    def test_2_a_known_artwork_is_preferred_and_searched_by_name(self):
        self.assertTrue(self.artwork, "some reconstructions give way to a real artwork")
        scenes = {s.scene_id: s for s in self.plan.scenes}
        for sid in self.artwork:
            q = self.after[sid].reason.split(A.ARTWORK_REASON, 1)[1].split(";")[0].strip()
            self.assertEqual(self.after[sid].asset_type, "stock_image", "a painting or engraving is a still")
            self.assertEqual(scenes[sid].search_queries[0], q, "the named artwork is what gets searched")
            self.assertTrue(any(m in NARR[sid - 1].lower() for a in self.rules.artworks if a["query"] == q for m in a["match"]),
                            "matched from what the narration says")

    def test_3_a_reconstruction_without_artwork_stays_ai(self):
        no_art = {2, 4, 6, 12}
        for sid in no_art:
            if self.before[sid].asset_type in AI:
                self.assertIn(self.after[sid].asset_type, AI, f"scene {sid} has no real artwork: it stays AI")

    def test_4_the_cap_never_forces_unrelated_stock(self):
        for sid, d in self.after.items():
            if self.before[sid].asset_type in AI and d.asset_type not in AI:
                self.assertTrue(sid in REAL or sid in self.artwork, f"scene {sid} left AI only for a real source or artwork: {d.reason}")
        n_ai = sum(1 for d in self.after.values() if d.asset_type in AI)
        cap = int(len(NARR) * self.rules.max_ai_share)
        if n_ai > cap:
            self.assertFalse([sid for sid, d in self.after.items() if d.asset_type in AI and
                              any(m in NARR[sid - 1].lower() for a in self.rules.artworks for m in a["match"])],
                             "over the cap only where no artwork exists")

    def test_5_the_ai_run_limit_still_holds_where_an_artwork_can_break_it(self):
        run = []
        for sid in sorted(self.after):
            if self.after[sid].asset_type in AI:
                run.append(sid)
                continue
            self._check_run(run)
            run = []
        self._check_run(run)

    def _check_run(self, run):
        if len(run) > self.rules.max_ai_run:
            arts = [sid for sid in run if any(m in NARR[sid - 1].lower() for a in self.rules.artworks for m in a["match"])]
            self.assertFalse(arts, f"a long AI run {run} kept scenes that have a real artwork")

    def test_6_a_style_without_rules_allocates_exactly_as_before(self):
        r = load_style("mystery_documentary").selection_rules
        self.assertEqual((r.real_subjects, r.max_ai_share, r.max_ai_run, r.artworks), ([], None, None, []))
        _, with_hook = allocate("mystery_documentary")
        _, without = allocate("mystery_documentary", limits=False)
        self.assertEqual({k: (d.asset_type, d.reason) for k, d in with_hook.items()}, {k: (d.asset_type, d.reason) for k, d in without.items()})

    def test_7_flow_choices_are_only_ever_removed_never_added_or_changed(self):
        for sid, d in self.after.items():
            if d.asset_type in AI:
                self.assertEqual(d.asset_type, self.before[sid].asset_type, f"scene {sid}: the Flow choice itself is unchanged")

    def test_8_the_csv_keeps_its_four_columns(self):
        out = Path(tempfile.mkdtemp()) / "plan.csv"
        self.plan.write_csv(out)
        rows = list(csv.DictReader(out.open()))
        self.assertEqual(list(rows[0].keys()), ["scene_number", "script_segment", "asset_type", "prompt"])
        sid = min(self.artwork)
        self.assertEqual(rows[sid - 1]["prompt"], self.plan.scenes[sid - 1].search_queries[0], "the artwork search is the scene's prompt")

    def test_the_rules_survive_a_brand_kit_merge(self):
        from style_engine.schema import VideoStyle

        s = load_style("book_of_enoch")
        self.assertEqual(VideoStyle.from_dict(s.to_dict()).selection_rules, s.selection_rules)


if __name__ == "__main__":
    unittest.main()
