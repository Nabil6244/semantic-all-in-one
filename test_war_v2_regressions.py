"""War Documentary, Bakhmut v2 render QA (2026-11-09): 2.8 s of bare grid at 0:13.8, 12.9 s of sparse grid, two short footage shots.

Causes, each reproduced here from the plan alone and, for the bare grid and the short shots, on tiny real renders through render_qa:
  bare grid     a dark situation map (map_card) counted as covering; the compositor lifts blacks so its dark land is the colour of the plate
  sparse grid   dark tactical maps over land the same grey as the plate; a US map that is mostly sea
  2.1 s shot    a captured clip that cuts to another shot inside the file (1.5 s limo, then 2.1 s studio): two visible pieces
  0.2 s shot    a clip whose first 0.2 s is another shot, then a portrait card dims the rest: 0.2 s of visible footage
  sliver        a card ending 1.1 s before its clip ends leaves a 1.1 s glimpse
"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from cinematic_explainer.render import Layer, Shot
from cinematic_explainer.war import backdrop as BD, direction as D, planner, render_qa as Q, segments as SG

TXT = ["Wagner fighters attacked in small groups around Bakhmut.", "President Zelensky visited troops in the city in December.",
       "The city fell in May after months of street fighting.", "Officials claimed the front had barely moved all winter."]
MAP_CARD = {"places": ["Bakhmut"], "frame": [35.0, 46.79, 41.0, 50.39], "style": "dark", "pins": [{"lat": 48.59, "lon": 38.0, "label": "Bakhmut"}], "arrows": [],
            "caption": {"title": "Places named in the narration", "sub": "Schematic"}, "as_of": "", "status": "illustrative", "illustrative": True}


def _rows(total, n=4):
    step = total / n
    return [{"_no": i + 1, "_start": i * step, "_end": (i + 1) * step, "text": TXT[i % len(TXT)], "words": None} for i in range(n)]


def _plan(shots=(), layers=()):
    return SimpleNamespace(shots=list(shots), layers=list(layers), stats={}, log=[])


def _harden(plan, total, hook_end=0.0, cuts=None, plate=None):
    """What a render does to a plan: the direction pass's last step, then the measured pass (integration.run_war_documentary)."""
    counts = {}
    rows = _rows(total)
    cat = planner._default_catalog()
    D._harden(plan, rows, cat, {}, counts, total, hook_end, {})
    counts.update(D.harden_measured(plan, rows, plate, hook_end, cat))
    return counts


def _pic(path):
    return True


class Fixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.d = Path(cls.tmp.name)
        cls.plate = BD.ensure_backdrop(cls.d)
        cls.pf = D.plate_frames(cls.plate)
        cls.long = str(cls.d / "long.mp4")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:d=9", "-r", "25", "-pix_fmt", "yuv420p", cls.long], check=True)
        cls.cut = str(cls.d / "cut.mp4")              # two different shots in one file, the cut at 1.5 s (captured clip 009 of the v2 run)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "smptebars=s=320x180:d=1.5", "-f", "lavfi", "-i", "rgbtestsrc=s=320x180:r=25:d=2.1",
                        "-filter_complex", "[0:v]fps=25,format=yuv420p[a];[1:v]fps=25,format=yuv420p[b];[a][b]concat=n=2:v=1:a=0", cls.cut], check=True)
        D._PIC_CACHE.update({cls.long: True, cls.cut: True})

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()


class BareGrid(Fixtures):
    def test_dark_map_card_is_measured_thin_and_the_plan_oracle_now_sees_it(self):
        plan = _plan(layers=[Layer("map_card", 13.6, 16.6, dict(MAP_CARD))])
        self.assertEqual(D.uncovered_spans(plan, 16.6, picture=_pic)[0][:2], (0.0, 13.6))          # structural: 13.6-16.6 trusted as covered (the v2 gap)
        self.assertEqual([x for x in D.uncovered_spans(plan, 16.6, picture=_pic) if x[0] >= 13.0], [])
        meas = D.uncovered_spans_measured(plan, 16.6, picture=_pic, plate=self.pf)
        self.assertTrue(any(a <= 13.6 and b >= 16.5 for a, b, _ in meas), meas)
        self.assertIn("drawn thin", meas[-1][2])

    def test_harden_makes_it_cover(self):
        plan = _plan([Shot(self.long, 0, 4, 0)], [Layer("map_card", 4, 7.6, dict(MAP_CARD))])
        c = _harden(plan, 7.6, plate=self.plate)
        self.assertGreaterEqual(c.get("thin_maps_fixed", 0) + c.get("thin_maps_replaced", 0), 1, c)
        self.assertEqual(D.uncovered_spans_measured(plan, 7.6, plate=self.pf), [])
        self.assertEqual(D.thin_layers(plan, self.pf), [])

    def test_real_render_before_and_after(self):
        total = 9.0
        for fixed in (False, True):
            plan = _plan([Shot(self.long, 5.0, total, 0)], [Layer("map_card", 0.0, 5.0, dict(MAP_CARD))])
            if fixed:
                _harden(plan, total, plate=self.plate)
            shots = BD.fill_gaps(list(plan.shots), total, self.plate)
            out = str(self.d / f"bare_{fixed}.mp4")
            r = SG.render_with_fallback(shots, list(plan.layers), out, backdrop_path=self.plate, state_dir=str(self.d / f"st_bare_{fixed}"))
            self.assertTrue(r.get("ok"), r)
            res = Q.check(out, self.plate)
            if fixed:
                self.assertEqual(res["bare_plate_s"], 0.0, Q.text(res))
                self.assertEqual([s for s in res["shots"] if s["kind"] == "footage" and s["seconds"] < 3.0], [], Q.text(res))
            else:
                self.assertGreater(res["bare_plate_s"] + res["sparse_plate_s"], 2.0, Q.text(res))          # the v2 finding reproduced


class SparseMaps(Fixtures):
    def test_dark_tactical_map_becomes_the_coloured_look(self):
        lay = Layer("tac_map", 0, 6.5, {"theme": "tactical", "places": [{"name": "Bakhmut", "kind": "pin"}], "focus": [["Bakhmut"], ["Bakhmut"]], "focus_times": [0.0, 5.0],
                                       "close_steps": [False, True]})
        self.assertTrue(D.layer_cover(lay, self.pf)["thin"])
        plan = _plan(layers=[lay])
        c = _harden(plan, 6.5, plate=self.plate)
        self.assertEqual(c.get("thin_maps_fixed"), 1, c)
        self.assertEqual(plan.layers[0].params["theme"], "political")
        self.assertFalse(D.layer_cover(plan.layers[0], self.pf)["thin"])

    def test_map_that_is_mostly_sea_gets_lighter_land(self):
        lay = Layer("tac_map", 0, 6.0, {"theme": "political", "fills": [{"iso3": "USA", "role": "gold"}], "focus": [[{"country": "United States"}]]})
        self.assertTrue(D.layer_cover(lay, self.pf)["thin"])
        plan = _plan(layers=[lay])
        _harden(plan, 6.0, plate=self.plate)
        self.assertTrue(plan.layers[0].params.get("context_fill"))
        self.assertFalse(D.layer_cover(plan.layers[0], self.pf)["thin"])

    def test_overlapping_maps_do_not_hide_each_other(self):
        plan = _plan(layers=[Layer("tac_map", 0, 4.6, {"theme": "political"}), Layer("map_card", 3.3, 6.3, dict(MAP_CARD))])
        c = _harden(plan, 6.3, plate=self.plate)
        full = sorted((ly for ly in plan.layers if ly.kind in ("tac_map", "map_card")), key=lambda x: x.start)
        self.assertEqual(len(full), 1)
        self.assertAlmostEqual(full[0].end, 6.3, delta=0.05)
        self.assertEqual(full[0].start, 0)
        self.assertEqual(c.get("overlaps_merged"), 1)


class ShortPieces(Fixtures):
    def test_internal_cut_makes_two_visible_pieces(self):                    # 0:08.2 (2.1 s): the clip cuts at 1.5 s into the file
        plan = _plan([Shot(self.cut, 0.0, 3.6, 0.0)])
        pcs = D.visible_footage_pieces(plan, 9.0, picture=_pic)
        self.assertEqual([(round(a, 1), round(b, 1)) for a, b, _ in pcs], [(0.0, 1.5), (1.5, 3.6)])
        self.assertEqual(len(D.short_footage_pieces(plan, 9.0, picture=_pic)), 2)
        self.assertEqual(D.short_footage_pieces(plan, 9.0, picture=_pic, hook_end=4.0), [])      # inside the montage hook the cuts are deliberate

    def test_planner_absorbs_both_pieces_with_a_graphic_never_a_freeze(self):
        plan = _plan([Shot(self.cut, 0.0, 3.6, 0.0), Shot(self.long, 3.6, 9.0, 0.0)])
        c = _harden(plan, 9.0, plate=self.plate)
        self.assertEqual(D.short_footage_pieces(plan, 9.0, picture=_pic), [])
        self.assertGreaterEqual(c.get("short_pieces_covered", 0) + c.get("short_pieces_absorbed", 0), 1, c)
        self.assertTrue(any(ly.kind in D.SELF_BACKED and ly.start <= 0.05 and ly.end >= 3.5 for ly in plan.layers))
        self.assertEqual(D.uncovered_spans(plan, 9.0, picture=_pic), [])

    def test_sliver_after_a_portrait_card(self):                             # 0:44.4 (0.2 s): the first 0.2 s of the file is another shot, then the card dims it
        plan = _plan([Shot(self.long, 0.0, 6.0, 0.0)], [Layer("figure_card", 0.6, 6.0, {"name": "A Person"}, dim=True)])
        cuts = lambda p: [0.2] if p == self.long else []                    # noqa: E731
        self.assertEqual(len(D.short_footage_pieces(plan, 6.0, picture=_pic, cuts=cuts)), 2)      # 0.2 s of another shot, then 0.2 s before the card dims it
        D._absorb_short_pieces(plan, _rows(6.0), planner._default_catalog(), {}, {}, 6.0, cuts=cuts, picture=_pic)
        self.assertEqual(D.short_footage_pieces(plan, 6.0, picture=_pic, cuts=cuts), [])

    def test_visible_sliver_after_a_full_card(self):                         # a card ends 1.1 s before its clip does
        plan = _plan([Shot(self.long, 0.0, 9.0, 0.0)], [Layer("kit_title", 0.0, 7.9, {"text": "Bakhmut"})])
        cuts = lambda p: []                                                  # noqa: E731
        pcs = D.visible_footage_pieces(plan, 9.0, picture=_pic, cuts=cuts)
        self.assertEqual([(round(a, 1), round(b, 1)) for a, b, _ in pcs], [(7.9, 9.0)])
        D._absorb_short_pieces(plan, _rows(9.0), planner._default_catalog(), {}, {}, 9.0, cuts=cuts, picture=_pic)
        self.assertEqual(D.short_footage_pieces(plan, 9.0, picture=_pic, cuts=cuts), [])
        self.assertEqual(D.uncovered_spans(plan, 9.0, picture=_pic), [])

    def test_a_clip_nearly_all_under_a_card_leaves_no_sliver(self):
        plan = _plan([Shot(self.long, 0.0, 9.0, 0.0)], [Layer("kit_title", 0.0, 8.9, {"text": "Bakhmut"})])
        cuts = lambda p: []                                                  # noqa: E731
        self.assertEqual([(round(a, 1), round(b, 1)) for a, b, _ in D.visible_footage_pieces(plan, 9.0, picture=_pic, cuts=cuts)], [(8.9, 9.0)])
        D._absorb_short_pieces(plan, _rows(9.0), planner._default_catalog(), {}, {}, 9.0, cuts=cuts, picture=_pic)
        self.assertEqual(D.visible_footage_pieces(plan, 9.0, picture=_pic, cuts=cuts), [])

    def test_over_card_that_would_stack_on_the_clip_is_promoted(self):
        plan = _plan([Shot(self.cut, 0.0, 3.6, 0.0)], [Layer("kit_datecard", 0.0, 3.6, {"date": "May 2023", "over": True})])
        D._absorb_short_pieces(plan, _rows(3.6), planner._default_catalog(), {}, {}, 3.6, picture=_pic)
        self.assertFalse((plan.layers[0].params or {}).get("over"))
        self.assertEqual([ly.kind for ly in plan.layers], ["kit_datecard"])

    def test_real_render_with_an_internal_cut_has_no_short_footage_shot(self):
        total = 9.0
        before = _plan([Shot(self.cut, 0.0, 3.6, 0.0), Shot(self.long, 3.6, total, 0.0)])
        after = _plan([Shot(self.cut, 0.0, 3.6, 0.0), Shot(self.long, 3.6, total, 0.0)])
        _harden(after, total, plate=self.plate)
        res = {}
        for name, plan in (("before", before), ("after", after)):
            shots = BD.fill_gaps(list(plan.shots), total, self.plate)
            out = str(self.d / f"cut_{name}.mp4")
            r = SG.render_with_fallback(shots, list(plan.layers), out, backdrop_path=self.plate, state_dir=str(self.d / f"st_cut_{name}"))
            self.assertTrue(r.get("ok"), r)
            res[name] = Q.check(out, self.plate)
        self.assertTrue(res["before"]["short_shots"], Q.text(res["before"]))
        self.assertEqual(res["after"]["short_shots"], [], Q.text(res["after"]))
        self.assertEqual(res["after"]["bare_plate_s"], 0.0, Q.text(res["after"]))


class WholePlan(Fixtures):
    def test_planned_film_has_no_bare_second_no_thin_layer_no_short_piece(self):
        sc = [{"text": t, "start": i * 8.0, "end": i * 8.0 + 8.0, "scene_no": i + 1} for i, t in enumerate(TXT)]
        p = planner.plan(sc, config={})
        self.assertNotIn("error", p.stats["direction"])
        D.harden_measured(p, sc, self.plate)                                  # the render's measured pass
        chk = D.plan_check(p, 32.0, plate=self.pf, picture=_pic)
        self.assertEqual(chk["uncovered"], [])
        self.assertEqual(chk["sparse_risk"], [])
        self.assertEqual(chk["short_pieces"], [])


if __name__ == "__main__":
    unittest.main()
