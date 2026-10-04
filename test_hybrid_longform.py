"""Hybrid Map for documentaries of 30, 40 and 60 minutes: chapters, bounded requests, one master timeline, continuity, resume, identity.
All synthetic (hybrid_longform_fixtures): no network, no credits, no media."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hybrid.compile import compile_plan, plan_to_rows
from hybrid.director import chapter_state
from hybrid.identity import UNATTACHED, load_descriptors, match_rows, reconcile, row_descriptors, save_descriptors
from hybrid.narration import build_sentences, plan_chunks
from hybrid.pipeline import chunks_from_plan, plan_hybrid, repair_errors
from hybrid.plan import Clip, HybridPlan
from hybrid.validate import validate
from hybrid_longform_fixtures import FakeGemini, make_narration

_CACHE = {}


def narration(minutes):
    if minutes not in _CACHE:
        words, script = make_narration(minutes)
        _CACHE[minutes] = (words, script, words[-1][2] + 0.4, build_sentences(words, script, words[-1][2] + 0.4))
    return _CACHE[minutes]


class TestChapters(unittest.TestCase):
    def test_chapters_tile_the_narration_and_cut_only_between_sentences(self):
        for minutes in (30, 40, 60):
            with self.subTest(minutes=minutes):
                _, _, total, sents = narration(minutes)
                chunks = plan_chunks(sents, total)
                self.assertGreaterEqual(len(chunks), 2)
                self.assertEqual(chunks[0].start, 0.0)
                self.assertEqual(chunks[-1].end, total)
                for a, b in zip(chunks, chunks[1:]):
                    self.assertEqual(a.end, b.start)              # no gap, no overlap
                    self.assertEqual(a.last + 1, b.first)          # every sentence in exactly one chapter
                    self.assertLessEqual(sents[a.last].end, a.end)  # the cut falls after the last sentence's words ...
                    self.assertLessEqual(a.end, sents[b.first].start)  # ... and before the next sentence's
                self.assertEqual(sum(c.last - c.first + 1 for c in chunks), len(sents))
                self.assertTrue(all(c.end - c.start <= 540 for c in chunks), "every request is for a few minutes of narration, however long the video")

    def test_a_short_narration_is_one_request_as_before(self):
        _, _, _, sents = narration(30)
        short = [s for s in sents if s.end < 400]
        self.assertEqual(len(plan_chunks(short, 400.0)), 1)
        self.assertEqual(len(plan_chunks(short, 540.0)), 1)

    def test_a_cut_prefers_the_end_of_a_paragraph(self):
        _, _, total, sents = narration(60)
        chunks = plan_chunks(sents, total)
        ends = [sents[c.last].para_end for c in chunks[:-1]]
        self.assertGreaterEqual(sum(ends), len(ends) - 1, "almost every chapter ends where a paragraph ends")


class TestMasterPlan(unittest.TestCase):
    def check(self, minutes):
        words, script, total, sents = narration(minutes)
        llm = FakeGemini(beat_sentences=3)
        res = plan_hybrid(words, llm, script=script, duration=total, use_critic=False)
        plan = res.plan
        chunks = plan_chunks(sents, total)
        self.assertEqual(res.stats["chapters"], len(chunks))
        self.assertEqual([c["kind"] for c in llm.calls].count("director"), len(chunks))   # one request per chapter, nothing more
        self.assertLess(max(c["chars"] for c in llm.calls), 40000)                       # bounded, whatever the length
        # one master timeline: contiguous, complete, unique ids, in order
        self.assertEqual(plan.beats[0].start, 0.0)
        self.assertAlmostEqual(plan.beats[-1].end, plan.duration, places=2)
        for a, b in zip(plan.beats, plan.beats[1:]):
            self.assertAlmostEqual(a.end, b.start, places=3)
        ids = [b.id for b in plan.beats]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, [f"b{i + 1}" for i in range(len(ids))])
        # no sentence lost or doubled
        self.assertEqual(" ".join(b.narration for b in plan.beats), " ".join(s.text for s in sents))
        # chapters
        self.assertEqual([c["id"] for c in plan.chapters], list(range(1, len(chunks) + 1)))
        self.assertEqual([b.chapter for b in plan.beats], sorted(b.chapter for b in plan.beats))
        for c in plan.chapters:
            inside = [b for b in plan.beats if b.chapter == c["id"]]
            self.assertAlmostEqual(inside[0].start, c["start"], places=2)
            self.assertAlmostEqual(inside[-1].end, c["end"], places=2)
        return res, llm

    def test_30_40_and_60_minutes_make_one_valid_master_plan(self):
        for minutes in (30, 40, 60):
            with self.subTest(minutes=minutes):
                res, _ = self.check(minutes)
                self.assertEqual([f for f in validate(res.plan) if f.severity == "error"], [])
                self.assertGreater(len(res.plan.beats), 60 if minutes == 30 else 80)

    def test_the_camera_never_restarts_at_a_chapter_boundary(self):
        res, llm = self.check(60)
        steps = [(b.id, c) for b in res.plan.beats for c in b.camera]
        self.assertEqual([c.action for _, c in steps].count("start"), 1)               # one opening for the whole documentary
        self.assertEqual(steps[0][1].frame, "globe")
        self.assertTrue(all(c.frame != "globe" for _, c in steps[2:]) or all(c.place for _, c in steps), "no later globe reset")
        for chap in res.plan.chapters[1:]:
            first = next(b for b in res.plan.beats if b.chapter == chap["id"])
            self.assertNotIn("start", [c.action for c in first.camera])
        # no camera move happens under footage
        wins = res.plan.footage_windows()
        for _, c in steps:
            for a, b in wins:
                self.assertFalse(a + 0.01 < c.t < b - 0.01, f"camera step at {c.t} is under footage {a}-{b}")

    def test_every_chapter_after_the_first_is_told_where_the_story_is(self):
        res, llm = self.check(40)
        directors = [c for c in llm.calls if c["kind"] == "director"]
        self.assertFalse(directors[0]["context"] is False)
        self.assertIn("opening chapter", directors[0]["user"])
        for c in directors[1:]:
            self.assertIn("do NOT open on the globe", c["user"])
            self.assertIn("currently looking at", c["user"])
            self.assertIn("Titles already used", c["user"]) if "hud_title" in c["user"] else None
        st = chapter_state(res.plan.beats[:10])
        self.assertTrue(st["camera"][0])

    def test_overlays_that_outlive_their_beat_are_decided_on_the_master_plan(self):
        from hybrid.compile import layer_end
        res, _ = self.check(30)
        plan = res.plan
        held = [(b, l) for b in plan.beats for l in b.layers if l.until == "after_footage"]
        self.assertTrue(held, "the fixture uses after_footage")
        for b, l in held:
            end = layer_end(plan, b, l)
            self.assertLessEqual(end, plan.duration + 1e-6)
            later = plan.beats[plan.beats.index(b) + 1:]
            foot = next((k for k, x in enumerate(later) if x.mode == "footage"), None)
            if foot is not None:
                nxt = next((x for x in later[foot + 1:] if plan.is_map_mode(x)), None)
                if nxt is not None:
                    self.assertLessEqual(end, nxt.end + 1e-6, "it leaves with the first map beat after the next footage, never indefinitely")


class TestResume(unittest.TestCase):
    def test_a_failure_in_chapter_5_costs_only_the_chapters_not_yet_planned(self):
        words, script, total, sents = narration(60)
        n = len(plan_chunks(sents, total))
        with tempfile.TemporaryDirectory() as d:
            llm = FakeGemini(beat_sentences=3, fail_on_chapter=5, fail_times=99)
            import hybrid.director as D
            old = D.RETRY_DELAYS
            D.RETRY_DELAYS = (0.0,)
            try:
                with self.assertRaises(Exception):
                    plan_hybrid(words, llm, script=script, duration=total, use_critic=False, checkpoint_dir=d)
            finally:
                D.RETRY_DELAYS = old
            done = sorted(p.name for p in Path(d).glob("chapter_*.json"))
            self.assertEqual(done, [f"chapter_{i:03d}.json" for i in range(1, 5)])         # chapters 1-4 were kept
            again = FakeGemini(beat_sentences=3)
            res = plan_hybrid(words, again, script=script, duration=total, use_critic=False, checkpoint_dir=d)
            self.assertEqual(res.stats["checkpoint_hits"], 4)
            self.assertEqual([c["chapter"] for c in again.calls if c["kind"] == "director"], list(range(5, n + 1)))
            fresh = plan_hybrid(words, FakeGemini(beat_sentences=3), script=script, duration=total, use_critic=False)
            self.assertEqual([(b.id, b.mode, round(b.start, 2), round(b.end, 2)) for b in res.plan.beats], [(b.id, b.mode, round(b.start, 2), round(b.end, 2)) for b in fresh.plan.beats])

    def test_a_changed_script_does_not_reuse_stale_chapters(self):
        words, script, total, sents = narration(30)
        with tempfile.TemporaryDirectory() as d:
            plan_hybrid(words, FakeGemini(beat_sentences=3), script=script, duration=total, use_critic=False, checkpoint_dir=d)
            other = FakeGemini(beat_sentences=3)
            res = plan_hybrid(words, other, script=script, duration=total, use_critic=False, checkpoint_dir=d, style_guidance="more cards please")
            self.assertEqual(res.stats["checkpoint_hits"], 0)


class TestCriticAndRepairPerChapter(unittest.TestCase):
    def test_chapters_are_reviewed_together_and_repairs_change_no_time_or_id(self):
        words, script, total, sents = narration(40)
        llm = FakeGemini(beat_sentences=3, weak_first=True)
        res = plan_hybrid(words, llm, script=script, duration=total, max_repairs=1, critic_policy="always")
        chunks = plan_chunks(sents, total)
        kinds = [c["kind"] for c in llm.calls]
        self.assertEqual(kinds.count("director"), len(chunks))
        self.assertLess(kinds.count("critic"), 2 * len(chunks))      # the chapters travel together in a few compact requests, not one each
        self.assertGreaterEqual(kinds.count("critic"), 2)
        hit = {b.chapter for b in res.plan.beats if b.id in (res.repaired[0] if res.repaired else [])}
        self.assertGreater(len(hit), 1)
        self.assertEqual(kinds.count("repair"), len(hit))             # one targeted repair request per chapter that had a weak beat, none for the others
        self.assertLess(max(c["chars"] for c in llm.calls), 40000)
        plain = plan_hybrid(words, FakeGemini(beat_sentences=3), script=script, duration=total, use_critic=False, max_repairs=0)
        self.assertEqual([(b.id, round(b.start, 2), round(b.end, 2), b.chapter) for b in res.plan.beats], [(b.id, round(b.start, 2), round(b.end, 2), b.chapter) for b in plain.plan.beats])
        self.assertTrue(all(b.purpose == "repaired" for b in res.plan.beats if b.id in res.repaired[0]))
        self.assertEqual([f for f in validate(res.plan) if f.severity == "error"], [])

    def test_a_clean_long_plan_costs_only_the_director_calls(self):
        words, script, total, sents = narration(40)
        llm = FakeGemini(beat_sentences=3, weak_first=True)         # a critic WOULD complain, if it were asked
        res = plan_hybrid(words, llm, script=script, duration=total)
        kinds = [c["kind"] for c in llm.calls]
        self.assertEqual(set(kinds), {"director"})
        self.assertEqual(res.stats["critic_calls"] + res.stats["repair_calls"], 0)
        self.assertTrue(res.stats["critic_skipped"])

    def test_repair_errors_on_a_long_plan_also_goes_chapter_by_chapter(self):
        words, script, total, sents = narration(40)
        res = plan_hybrid(words, FakeGemini(beat_sentences=3), script=script, duration=total, use_critic=False, max_repairs=0)
        plan = HybridPlan.from_dict(res.plan.to_dict())
        self.assertEqual(len(chunks_from_plan(plan, sents)), len(plan.chapters))
        broken = next(b for b in plan.beats if b.chapter == 3 and b.mode != "footage" and b.cam_place)
        broken.cam_place = "Nowhere At All"
        for l in broken.layers:
            l.place = "Nowhere At All"
        llm = FakeGemini(beat_sentences=3)
        out = repair_errors(plan, words, llm, script=script, duration=total, max_repairs=1)
        calls = [c for c in llm.calls if c["kind"] == "repair"]
        self.assertEqual(len(calls), 1)
        self.assertLess(calls[0]["chars"], 20000)                    # one chapter's narration, not the whole documentary's


class TestIdentity(unittest.TestCase):
    def setup_project(self, d):
        from asset_manager import AssetManifest
        words, script, total, _ = narration(30)
        plan = plan_hybrid(words, FakeGemini(beat_sentences=3), script=script, duration=total, use_critic=False).plan
        old = row_descriptors(plan)
        self.mid = old[len(old) // 2]["scene"]               # the row the user replaced: somewhere in the middle of the documentary
        images = Path(d)
        man = AssetManifest(images)
        for r in old:
            n = int(r["scene"])
            f = images / f"{n:03d}.jpg"
            f.write_bytes(f"pic {r['beat']} {r['kind']}{r['idx']}".encode())
            man.set(str(n), {"status": "complete", "source": "manual" if str(n) == self.mid else "stock_image", "user_override": str(n) == self.mid, "local_path": str(f), "prompt": f"p{n}"})
        return plan, old, man

    def test_a_users_clip_follows_its_beat_when_rows_are_added_before_it(self):
        from asset_manager import AssetManifest
        with tempfile.TemporaryDirectory() as d:
            plan, old, _ = self.setup_project(d)
            mine = next(r for r in old if r["scene"] == self.mid)
            # a repair turns an early map beat into footage: one more row, so every later row number moves up by one
            early = next(b for b in plan.beats if b.mode == "map" and 30 < b.start < mine["start"] - 100 and not any(c.action == "start" for c in b.camera))
            early.mode, early.layers, early.camera = "footage", [], []
            early.clips = [Clip(asset="stock_video:new clip")]
            new = row_descriptors(plan)
            self.assertEqual(len(new), len(old) + 1)
            moved = next(r for r in new if r["beat"] == mine["beat"] and r["kind"] == mine["kind"] and r["idx"] == mine["idx"])
            self.assertNotEqual(moved["scene"], self.mid)
            out = reconcile(d, old, new)
            self.assertGreater(out["moved"], 10)
            self.assertEqual(out["unattached"], [])
            rec = AssetManifest(d).get(moved["scene"])
            self.assertTrue(rec["user_override"] and rec["source"] == "manual")
            self.assertEqual(Path(rec["local_path"]).read_text(), f"pic {mine['beat']} {mine['kind']}{mine['idx']}")
            self.assertEqual(Path(rec["local_path"]).name, f"{int(moved['scene']):03d}.jpg")
            # the row number that used to be the user's clip is now someone else's cached picture, not the override
            other = AssetManifest(d).get(self.mid)
            self.assertFalse(other and other.get("user_override"))
            # every other picture followed its row too
            for r in new:
                if r["scene"] == moved["scene"]:
                    continue
                match = next((o for o in old if (o["beat"], o["kind"], o["idx"]) == (r["beat"], r["kind"], r["idx"])), None)
                if match:
                    self.assertEqual((Path(d) / f"{int(r['scene']):03d}.jpg").read_text(), f"pic {match['beat']} {match['kind']}{match['idx']}")

    def test_a_clip_whose_row_is_gone_is_set_aside_never_deleted_and_never_given_to_another_row(self):
        from asset_manager import AssetManifest
        with tempfile.TemporaryDirectory() as d:
            plan, old, _ = self.setup_project(d)
            mine = next(r for r in old if r["scene"] == self.mid)
            beat = next(b for b in plan.beats if b.id == mine["beat"])
            beat.mode, beat.clips, beat.support, beat.footage_intent = "map", [], None, ""
            new = row_descriptors(plan)
            out = reconcile(d, old, new)
            self.assertIn(self.mid, out["unattached"])
            kept = list((Path(d) / UNATTACHED).glob(f"was_scene_{int(self.mid):03d}.*"))
            self.assertEqual(len(kept), 1)
            self.assertTrue(kept[0].read_text().startswith("pic"))
            for r in new:
                rec = AssetManifest(d).get(r["scene"])
                self.assertFalse(rec and rec.get("user_override"), "the override is attached to no row")

    def test_an_unchanged_plan_touches_nothing_and_matching_is_one_to_one(self):
        with tempfile.TemporaryDirectory() as d:
            plan, old, _ = self.setup_project(d)
            before = sorted(p.name for p in Path(d).iterdir())
            self.assertEqual(reconcile(d, old, row_descriptors(plan)), {"moved": 0, "unattached": []})
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), before)
            m = match_rows(old, row_descriptors(plan))
            self.assertEqual(m, {r["scene"]: r["scene"] for r in old})

    def test_the_row_identities_are_saved_beside_the_plan(self):
        with tempfile.TemporaryDirectory() as d:
            plan, old, _ = self.setup_project(d)
            save_descriptors(d, old)
            self.assertEqual(load_descriptors(d), old)


class TestCompileAtLength(unittest.TestCase):
    def test_a_30_minute_plan_compiles_to_the_renderers_rules(self):
        words, script, total, _ = narration(30)
        plan = plan_hybrid(words, FakeGemini(beat_sentences=3), script=script, duration=total, use_critic=False).plan
        res = compile_plan(plan, validate=True)             # includes the engine's own timeline rules, when node is available
        self.assertEqual(res.report.errors, [])
        rows, _, _ = plan_to_rows(plan)
        clips = [r for r in rows if r.layer_type == "media_full"]
        cards = [r for r in rows if r.layer_type == "pip"]
        self.assertEqual(len(clips), sum(len(b.clips) for b in plan.beats if b.mode == "footage"))
        self.assertEqual(len(cards), sum(1 for b in plan.beats if b.support))
        self.assertTrue(all(0 <= r.t_start < r.t_end <= plan.duration + 1e-6 for r in clips + cards))
        self.assertTrue(res.spec.get("media_lazy"), "long videos cut their clip frames lazily")


if __name__ == "__main__":
    unittest.main()
