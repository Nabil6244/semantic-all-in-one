"""War Documentary footage/graphics balance (Bakhmut v2, 2026-11-09): a clip the Footage Director earned stays full-frame for most of its scene;
maps and full-frame cards belong to scenes without footage; a film with no footage still gets its maps and cards and no bare grid."""
import os
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace

from cinematic_explainer.render import Layer, Shot
from cinematic_explainer.war import direction as D
from cinematic_explainer.war import planner

HAVE_FFMPEG = shutil.which("ffmpeg") is not None
TXT = ["The fighting around Bakhmut began in the summer, and Russian troops pushed on the city from the east.",
       "Ukraine said it had lost 5,000 soldiers in the battle for Bakhmut that winter.",
       "The Wagner Group's leader said his fighters attacked in small groups through the ruins of Bakhmut.",
       "Then, by September, Ukrainian forces advanced south of the city near Klishchiivka and Andriivka.",
       "Russia claimed the capture of Bakhmut in May 2023, but the cost was seventy thousand casualties.",
       "The Kremlin said the operation was a success for the Wagner Group.",
       "President Zelensky visited troops near Bakhmut in December 2022.",
       "Nobody expected the battle to last that long."]


def _clip(dirpath, name, seconds):
    path = os.path.join(dirpath, name)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=160x90:rate=10:duration={seconds}", "-pix_fmt", "yuv420p", path], check=True)
    return path


def _scenes(dirpath, earned_idx=(), graphic=None, clip_s=9.0):
    out = []
    for i, text in enumerate(TXT):
        sc = {"scene_no": i + 1, "text": text, "start": i * 8.0, "end": i * 8.0 + 8.0}
        if i in earned_idx:
            sc["footage"] = _clip(dirpath, f"{i + 1:03d}.mp4", clip_s)
            sc["footage_meta"] = {"csv_pick": True, "source": "youtube_video", "kind": "youtube", "selection_method": "war_director", "footage_class": "illustrative",
                                  "relevance": 0.4}
        if graphic and i in graphic:
            sc["graphic"] = graphic[i]
        out.append(sc)
    return out


def _own_visible(plan, sc, total):
    pcs = D.visible_footage_pieces(plan, total, hook_end=0.0)
    a, b = sc["start"], sc["end"]
    return sum(max(0.0, min(b, y) - max(a, x)) for x, y, p in pcs if p == sc["footage"])


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg is needed to make test clips")
class EarnedFootage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_earned_scene_keeps_its_clip_under_csv_map_and_number(self):
        sc = _scenes(self.tmp, earned_idx=(0, 1, 2, 3), graphic={0: "map", 1: "number", 2: "map"})
        plan = planner.plan(sc, config={})
        self.assertNotIn("error", plan.stats["direction"])
        total = 64.0
        for i in (0, 1, 2, 3):
            self.assertGreaterEqual(_own_visible(plan, sc[i], total), 0.7 * 8.0 - 0.1, f"scene {i + 1}")

    def test_footage_share_of_eight_scene_plan_with_four_earned_clips(self):
        sc = _scenes(self.tmp, earned_idx=(0, 2, 4, 6), graphic={0: "map", 4: "number"})
        plan = planner.plan(sc, config={})
        vis = sum(b - a for a, b, _p in D.visible_footage_pieces(plan, 64.0))
        self.assertGreaterEqual(vis / 64.0, 0.40)
        self.assertEqual(D.short_footage_pieces(plan, 64.0), [])
        self.assertEqual(D.uncovered_spans(plan, 64.0), [])

    def test_no_opaque_card_or_map_on_an_earned_scene_beyond_one_short_insert(self):
        sc = _scenes(self.tmp, earned_idx=(0, 1, 2, 3, 4, 5, 6, 7))
        plan = planner.plan(sc, config={})
        for i, row in enumerate(sc):
            a, b = row["start"], row["end"]
            hidden = D._spans_union([(max(a, ly.start), min(b, ly.end)) for ly in plan.layers if D._covers(ly) and ly.end > a and ly.start < b])
            self.assertLessEqual(sum(y - x for x, y in hidden), D.EARNED_INSERT_S + 0.5, f"scene {i + 1}: {hidden}")

    def test_map_build_never_covers_an_earned_clip(self):
        from cinematic_explainer.war import map_build as MB

        sc = _scenes(self.tmp, earned_idx=(1, 2))
        rows = [dict(s, _start=s["start"], _end=s["end"], _no=s["scene_no"]) for s in sc]
        plan = SimpleNamespace(shots=[Shot(sc[1]["footage"], 8.0, 16.0, 0.0), Shot(sc[2]["footage"], 16.0, 24.0, 0.0)], layers=[], stats={})
        log = {str(r["_no"]): SimpleNamespace(flags=["no_footage"] if r["_no"] not in (2, 3) else [], candidates=[]) for r in rows}
        cat = planner._default_catalog()
        MB.build(plan, rows, cat, log, {}, [], tuple(D.FULL_KINDS - {"tac_map", "tac_route", "map_card"}), broll=True)
        maps = [ly for ly in plan.layers if ly.kind == "tac_map"]
        self.assertTrue(maps)
        for ly in maps:
            self.assertFalse(ly.start < 24.0 - 0.05 and ly.end > 8.0 + 0.05, (ly.start, ly.end))

    def test_protect_earned_turns_map_into_locator_and_cards_into_over(self):
        sc = _scenes(self.tmp, earned_idx=(0,))
        rows = [dict(s, _start=s["start"], _end=s["end"], _no=s["scene_no"]) for s in sc[:1]]
        plan = SimpleNamespace(shots=[Shot(sc[0]["footage"], 0.0, 8.0, 0.0)], stats={}, layers=[
            Layer("tac_map", 0.0, 8.0, {"places": [{"name": "Bakhmut", "kind": "pin"}], "csv_graphic": True}),
            Layer("kit_title", 2.0, 6.0, {"text": "Bakhmut", "csv_graphic": True}, dim=False), Layer("kit_recap", 1.0, 5.0, {"items": ["a"]}, dim=True)])
        counts = {}
        done = D.protect_earned(plan, rows, counts)
        self.assertEqual(D.visible_footage_pieces(plan, 8.0), [(0.0, 8.0, sc[0]["footage"])])
        self.assertTrue(any(ly.kind == "map_inset" for ly in plan.layers))
        self.assertTrue(next(ly for ly in plan.layers if ly.kind == "kit_title").params.get("over"))
        self.assertTrue(done and counts.get("earned_locator"))

    def test_map_without_a_place_is_cut_out_and_logged(self):
        sc = _scenes(self.tmp, earned_idx=(0,))
        rows = [dict(s, _start=s["start"], _end=s["end"], _no=s["scene_no"]) for s in sc[:1]]
        plan = SimpleNamespace(shots=[Shot(sc[0]["footage"], 0.0, 8.0, 0.0)], stats={}, layers=[
            Layer("tac_map", 0.0, 12.0, {"places": [], "csv_graphic": True}), Layer("kit_field", 2.0, 5.0, {})])
        counts = {}
        D.protect_earned(plan, rows, counts)
        self.assertEqual([ly for ly in plan.layers if D._covers(ly) and ly.start < 8.0 - 0.05], [])
        self.assertEqual(counts.get("earned_map_cut"), 1)
        pcs = D.visible_footage_pieces(plan, 8.0)
        self.assertEqual(pcs, [(0.0, 8.0, sc[0]["footage"])])

    def test_earned_clip_is_never_frozen_or_stretched(self):
        """Owner's rule: no frozen or stretched footage. An earned clip shorter than its scene ends with its frames; one with under 3 s of
        footage is dropped (the gap rules fill the scene), never shown as a sliver or held on its last frame."""
        short = _clip(self.tmp, "short.mp4", 2.2)
        plan = SimpleNamespace(shots=[Shot(short, 0.0, 3.3, 0.0)], layers=[], stats={})
        D._fit_short_clips(plan, {}, earned=[short])
        self.assertEqual(plan.shots, [])
        mid = _clip(self.tmp, "mid.mp4", 4.0)
        plan = SimpleNamespace(shots=[Shot(mid, 0.0, 6.0, 0.0)], layers=[], stats={})
        D._fit_short_clips(plan, {}, earned=[mid])
        self.assertEqual(len(plan.shots), 1)
        self.assertLessEqual(plan.shots[0].end - plan.shots[0].start, 4.0)       # ends with its frames, no hold
        self.assertGreaterEqual(plan.shots[0].end - plan.shots[0].start, 3.0)

    def test_returns_only_from_earned_clips_and_never_the_same_seconds(self):
        a, b = _clip(self.tmp, "ra.mp4", 7.0), _clip(self.tmp, "rb.mp4", 7.0)
        rows = [{"_no": i + 1, "_start": i * 8.0, "_end": (i + 1) * 8.0, "text": "Bakhmut Wagner fighting", "footage": f_} for i, f_ in enumerate([a, "", b])]
        plan = SimpleNamespace(shots=[Shot(a, 0, 7.0, 0), Shot(b, 16.0, 23.0, 0)], layers=[], stats={})
        D._broll_returns(plan, rows, {}, {}, {}, earned=[a, b])
        seen = {}
        for s in plan.shots:
            for lo, hi in seen.get(s.path, []):
                self.assertFalse(s.seek < hi - 0.05 and s.seek + (s.end - s.start) > lo + 0.05, "same seconds shown twice")
            seen.setdefault(s.path, []).append((s.seek, s.seek + (s.end - s.start)))


class NoFootageRun(unittest.TestCase):
    def test_film_without_footage_still_gets_maps_and_cards_and_no_grid(self):
        sc = _scenes(tempfile.gettempdir(), earned_idx=())
        plan = planner.plan(sc, config={})
        self.assertNotIn("error", plan.stats["direction"])
        self.assertEqual(D.uncovered_spans(plan, 64.0), [])
        self.assertTrue([ly for ly in plan.layers if ly.kind in ("tac_map", "tac_route", "map_card")])
        self.assertTrue([ly for ly in plan.layers if ly.kind in D.FULL_KINDS])

    def test_earned_footage_needs_a_real_file(self):
        self.assertFalse(D.earned_footage("/no/such/file.mp4", {"csv_pick": True}))
        self.assertFalse(D.earned_footage(__file__, {"generic": True, "csv_pick": True}))
        self.assertTrue(D.earned_footage(__file__, {"selection_method": "war_director"}))


if __name__ == "__main__":
    unittest.main()
