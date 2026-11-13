"""War Documentary plate coverage (owner, 2026-11-09: Bakhmut render, no footage, 11 s of bare grey grid and 10 s of a figure on the grid).
The plan has no stretch over 0.3 s without a clip that has a picture or a full-frame graphic with its own opaque background; checked from the plan
(direction.uncovered_spans) and, on two tiny renders, from the finished video by render_qa."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from cinematic_explainer.render import Layer, Shot
from cinematic_explainer.war import backdrop as BD, direction as D, planner, render_qa as Q, segments as SG

TXT = ["The assault began in August and nobody expected it to last this long.", "More than 100 thousand soldiers were reported killed or wounded there.",
       "The city fell in May after months of street fighting.", "Officials claimed the front had barely moved all winter."]


def _rows(total, n=4):
    step = total / n
    return [{"_no": i + 1, "_start": i * step, "_end": (i + 1) * step, "text": TXT[i % len(TXT)], "words": None} for i in range(n)]


def _plan(shots=(), layers=()):
    return SimpleNamespace(shots=list(shots), layers=list(layers), stats={}, log=[])


def _fix(plan, total, rows=None, **kw):
    counts = {}
    D._cover_plate(plan, rows or _rows(total), planner._default_catalog(), {}, counts, total)
    return counts


def _picture(path):
    return True


class Coverage(unittest.TestCase):
    def test_oracle_names_the_cause(self):
        plan = _plan(layers=[Layer("kit_stamp", 2, 6, {}), Layer("tac_map", 6, 10, {}), Layer("lay_stat_split", 12, 16, {})])
        sp = D.uncovered_spans(plan, 20, picture=_picture)
        self.assertEqual([(a, b) for a, b, _ in sp], [(0.0, 6.0), (10.0, 20.0)])
        self.assertIn("kit_stamp", sp[0][2])
        self.assertIn("lay_stat_split", sp[1][2])
        self.assertEqual(D.uncovered_spans(_plan(layers=[Layer("tac_map", 0, 4, {})]), 4.2, picture=_picture), [])    # under 0.3 s is not a stretch

    def test_missing_clip_scene(self):
        plan = _plan([Shot("a.mp4", 0, 6, 0), Shot("b.mp4", 12, 20, 0)])
        D._PIC_CACHE.update({"a.mp4": True, "b.mp4": True})
        _fix(plan, 20)
        self.assertEqual(D.uncovered_spans(plan, 20), [])

    def test_failed_download_clip_without_picture(self):
        D._PIC_CACHE.update({"good.mp4": True, "empty.mp4": False})
        plan = _plan([Shot("good.mp4", 0, 5, 0), Shot("empty.mp4", 5, 12, 0)])
        self.assertTrue(D.uncovered_spans(plan, 12))
        _fix(plan, 12)
        self.assertEqual(D.uncovered_spans(plan, 12), [])
        self.assertTrue(any(ly.kind in D.SELF_BACKED and ly.start <= 5.1 and ly.end >= 11.9 for ly in plan.layers))

    def test_blank_timeline_gap_is_held_or_filled(self):
        plan = _plan(layers=[Layer("tac_map", 0, 5, {}), Layer("kit_title", 5.8, 10, {"text": "Bakhmut"})])
        _fix(plan, 10)
        self.assertEqual(D.uncovered_spans(plan, 10), [])
        plan = _plan(layers=[Layer("tac_map", 0, 4, {}), Layer("tac_map", 11, 15, {})])
        _fix(plan, 15)
        self.assertEqual(D.uncovered_spans(plan, 15), [])

    def test_whole_film_without_footage(self):
        plan = _plan(layers=[Layer("kit_stamp", 0, 6, {"csv_graphic": True}), Layer("kit_bignum", 8, 14, {"value": 100}),
                             Layer("lay_stat_split", 14, 20, {"value": 5}), Layer("kicker", 14, 21, {})])
        self.assertTrue(D.uncovered_spans(plan, 24, picture=_picture))
        c = _fix(plan, 24)
        self.assertEqual(D.uncovered_spans(plan, 24), [])
        self.assertGreaterEqual(c.get("plate_motion", 0) + c.get("plate_backed", 0), 1)
        order = [ly.kind for ly in plan.layers]
        self.assertLess(order.index("kit_field"), order.index("kit_bignum"))         # the backing is drawn first, the figure on top

    def test_whole_planned_film_without_footage_has_no_bare_second(self):
        sc = [{"text": t, "start": i * 8.0, "end": i * 8.0 + 8.0, "scene_no": i + 1} for i, t in enumerate(TXT)]
        p = planner.plan(sc, config={})
        self.assertNotIn("error", p.stats["direction"])
        self.assertEqual(D.uncovered_spans(p, 32.0), [])

    def test_card_that_fails_to_draw_still_has_a_backing(self):
        # a self-backed card that raises is replaced by a full-frame kinetic card at render time (segments._fallback_card); a transparent one is backed here
        plan = _plan(layers=[Layer("lay_stat_split", 0, 6, {"value": None})])
        _fix(plan, 6)
        self.assertEqual(D.uncovered_spans(plan, 6), [])

    def test_sparse_transparent_cards_are_backed(self):
        plan = _plan(layers=[Layer("kit_bignum", 0, 6.4, {"value": "46,000"}), Layer("lay_stat_split", 6.4, 12, {"value": 3})])
        _fix(plan, 12)
        self.assertEqual(D.uncovered_spans(plan, 12), [])
        self.assertTrue(any(ly.kind == "kit_field" for ly in plan.layers))

    def test_over_footage_card_is_not_a_cover(self):
        plan = _plan(layers=[Layer("kit_kinetic", 0, 5, {"over": True})])
        self.assertTrue(D.uncovered_spans(plan, 5, picture=_picture))

    def test_field_card_is_opaque_and_moves(self):
        a, b = D.__dict__.get("kit_field") or __import__("cinematic_explainer.war.cards_motion", fromlist=["x"]).kit_field, None
        im1, im2 = a(0.2, 5.0, {"seed": 2}), a(3.0, 5.0, {"seed": 2})
        self.assertEqual(im1.getchannel("A").getextrema(), (255, 255))
        self.assertNotEqual(im1.tobytes(), im2.tobytes())


class EmptyBackingField(unittest.TestCase):
    """Kill Zone v3 (2026-11-14): the faint backing field showed alone on screen for 0.3-6 s (render_qa 'black or flat frames')."""

    def test_a_field_with_nothing_on_it_is_not_covered(self):
        plan = _plan(layers=[Layer("kit_field", 0, 6, {}), Layer("kit_stamp", 0, 2, {})])
        self.assertEqual([(a, b) for a, b, _ in D.uncovered_spans(plan, 6, picture=_picture)], [(2.0, 6.0)])
        self.assertEqual(D.uncovered_spans(_plan(layers=[Layer("kit_field", 0, 6, {"last_resort": True})]), 6, picture=_picture), [])

    def test_a_mark_ending_early_is_held_to_the_next_clip(self):
        plan = _plan([Shot("a.mp4", 0, 4, 0), Shot("b.mp4", 6.5, 10, 0)],
                     [Layer("kit_field", 4, 6.5, {}), Layer("kit_stamp", 3, 5.2, {"text": "CAN'T BE VERIFIED"})])
        _fix(plan, 10)
        self.assertEqual(D.uncovered_spans(plan, 10, picture=_picture), [])
        self.assertAlmostEqual(next(ly for ly in plan.layers if ly.kind == "kit_stamp").end, 6.5, delta=0.05)     # snapped to a frame

    def test_a_csv_stamp_ending_early_leaves_no_bare_field(self):
        rows = [{"_no": 1, "_start": 0.0, "_end": 10.0, "words": None,
                 "text": "Imagine that. An army that can't talk to itself. And soldiers too scared to say anything anyway."}]
        plan = _plan(layers=[Layer("kit_field", 0, 10, {}), Layer("kit_stamp", 0, 1.0, {"csv_graphic": True})])
        _fix(plan, 10, rows)
        self.assertEqual(D.uncovered_spans(plan, 10, picture=_picture), [])
        bare = [ly for ly in plan.layers if (ly.params or {}).get("last_resort") and ly.end - ly.start > 1.0]
        self.assertEqual(bare, [])

    def test_whole_line_when_no_phrase(self):
        S = SimpleNamespace
        short = [S(text="They fly to a roadside, land, and switch themselves off."), S(text="No signal."), S(text="No heat."), S(text="No sound.")]
        self.assertEqual(D._whole_line(short, short[1]), "No signal. No heat. No sound.")
        one = [S(text="And the reason they believed it is one of the most surprising stories of this entire war.")]
        self.assertEqual(D._whole_line(one, one[0]), "The reason they believed it is one of the most surprising stories of this entire war.")
        self.assertEqual(D._whole_line([S(text=" ".join(["word"] * 30))], None), "")


class TinyRenders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.d = Path(cls.tmp.name)
        cls.plate = BD.ensure_backdrop(cls.d)
        cls.short = str(cls.d / "short.mp4")
        cls.long = str(cls.d / "long.mp4")
        for p, secs in ((cls.short, 1.0), (cls.long, 8.0)):
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s=320x180:d={secs}", "-r", "25", p], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _render(self, plan, total, name):
        shots = BD.fill_gaps(list(plan.shots), total, self.plate)
        out = str(self.d / name)
        r = SG.render_with_fallback(shots, list(plan.layers), out, backdrop_path=self.plate, state_dir=str(self.d / ("st_" + name)))
        self.assertTrue(r.get("ok"), r)
        return Q.check(out, self.plate)

    def test_no_footage_render_never_shows_the_bare_plate(self):
        plan = _plan(layers=[Layer("kit_stamp", 0, 4, {"status": "claimed", "text": "Claimed by Moscow"}), Layer("kit_bignum", 4, 8, {"value": "100,000", "label": "CASUALTIES"})])
        self.assertTrue(D.uncovered_spans(plan, 8, picture=_picture))
        _fix(plan, 8, _rows(8, 2))
        self.assertEqual(D.uncovered_spans(plan, 8), [])
        res = self._render(plan, 8, "nofoot.mp4")
        self.assertEqual(res["bare_plate_s"], 0.0, Q.text(res))
        self.assertEqual(res["short_shots"], [], Q.text(res))

    def test_one_second_clip_remainder_is_not_a_short_shot(self):
        D._PIC_CACHE.update({self.short: True, self.long: True})
        plan = _plan([Shot(self.short, 0.0, 5.0, 0.0), Shot(self.long, 5.0, 10.0, 0.0)], [])
        D._fit_short_clips(plan, {}, probe=lambda p: 1.0 if p == self.short else 8.0)       # 1 s is left of the first clip: it goes, no flash
        _fix(plan, 10, _rows(10, 2))
        self.assertEqual(D.uncovered_spans(plan, 10), [])
        res = self._render(plan, 10, "short.mp4")
        self.assertEqual([s for s in res["shots"] if s["kind"] == "footage" and s["seconds"] < 3.0], [], Q.text(res))
        self.assertEqual(res["bare_plate_s"], 0.0, Q.text(res))


if __name__ == "__main__":
    unittest.main()
