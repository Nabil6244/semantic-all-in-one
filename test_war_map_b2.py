"""Stage B.2 (render 050 repair): maps never carry places from an earlier topic. No network, no render.

- direction._point_bare_maps: a bare map's place comes only from its own line(s) or the line just before, in the same section;
- map_build: no 'context' fallback, runs break at a section heading, after about MAX_RUN_S and where the geography changes, so pins reset."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


def _rows(lines):
    out, t = [], 0.0
    for i, (text, dur) in enumerate(lines, 1):
        out.append({"_no": str(i), "text": text, "_start": t, "_end": t + dur, "words": None})
        t += dur
    return out


def _cat():
    from cinematic_explainer.war import planner as P

    return P._default_catalog()


def _bare_map(a, b):
    from cinematic_explainer.render import Layer

    return Layer("tac_map", a, b, {"theme": "political", "fills": [{"iso3": "RUS", "role": "red", "start": 0.0}]}, dim=False)


def _plan(scenes, **cfg):
    from cinematic_explainer.war import integration as I, planner as P

    d = Path(tempfile.mkdtemp())
    return P.plan(I.load_scenes(d, [dict(s, no_footage=True) for s in scenes]), config=cfg)


def _scenes(lines):
    out, t = [], 0.0
    for i, (text, dur) in enumerate(lines, 1):
        out.append({"scene_no": i, "text": text, "start": t, "end": t + dur})
        t += dur
    return out


def _pins(layer):
    return [p["name"] for p in (layer.params or {}).get("places") or []]


class PointBareMaps(unittest.TestCase):
    def _point(self, rows, layers):
        from cinematic_explainer.war.direction import _point_bare_maps

        plan = SimpleNamespace(layers=list(layers))
        counts = {}
        _point_bare_maps(plan, rows, _cat(), counts)
        return plan, counts

    def test_abu_dhabi_does_not_inherit_st_petersburg(self):
        rows = _rows([("On the night of the ninth of November, more than a hundred drones flew toward the outskirts of Saint Petersburg.", 8.0),
                      ("Part one. The talks in Abu Dhabi.", 2.4),
                      ("On the tenth and eleventh of November, the United States hosted a new round of three-way talks in Abu Dhabi.", 8.2)])
        plan, counts = self._point(rows, [_bare_map(10.5, 18.6)])
        self.assertEqual(_pins(plan.layers[0]), [])
        # control: the same map placed over the Saint Petersburg line still gets its own pin
        plan2, _ = self._point(rows, [_bare_map(0.5, 7.5)])
        self.assertTrue(any("Petersburg" in n for n in _pins(plan2.layers[0])), _pins(plan2.layers[0]))

    def test_washington_not_on_unrelated_oil_export_line(self):
        rows = _rows([("Agreement between Kyiv, Washington and European capitals on guarantees.", 7.0),
                      ("And while the diplomats talked, the missiles and drones never stopped.", 4.0),
                      ("Part two. The oil war.", 2.0),
                      ("Every tank, every truck and every aircraft runs on refined fuel.", 6.0),
                      ("Oil products are one of Russia's biggest sources of export income.", 7.5)])
        plan, _ = self._point(rows, [_bare_map(19.5, 26.0)])
        self.assertNotIn("Washington", _pins(plan.layers[0]))
        self.assertEqual(_pins(plan.layers[0]), [])

    def test_only_the_line_just_before_in_the_same_section(self):
        rows = _rows([("Ukrainian drones attacked the Kirishi oil refinery in the Leningrad region.", 7.0),
                      ("The plant is one of the largest in the country.", 6.0),
                      ("It processes about twenty million tonnes a year.", 6.0)])
        plan, _ = self._point(rows, [_bare_map(13.2, 18.8)])              # two lines after Kirishi: too far back
        self.assertEqual(_pins(plan.layers[0]), [])
        plan, _ = self._point(rows, [_bare_map(7.2, 12.8)])               # the line right after Kirishi: allowed
        self.assertEqual(_pins(plan.layers[0]), ["Kirishi"])


class MapRuns(unittest.TestCase):
    def test_old_pins_do_not_linger_across_unrelated_subjects(self):
        sc = _scenes([("Ukrainian drones struck the Kirishi oil refinery near Saint Petersburg.", 7.0),
                      ("Fire crews worked through the night at the plant.", 7.0),
                      ("The refinery stopped one of its main units.", 7.0),
                      ("Far to the south, Russian glide bombs hit Zaporizhzhia.", 7.0),
                      ("Several apartment blocks were damaged in the city.", 7.0),
                      ("Rescue teams searched the rubble until morning.", 7.0)])
        plan = _plan(sc)
        maps = [ly for ly in plan.layers if ly.kind == "tac_map"]
        south = [m for m in maps if m.start >= 21.0 - 0.05]
        self.assertTrue(south, [(m.start, m.end, _pins(m)) for m in maps])
        for m in south:
            self.assertNotIn("Kirishi", _pins(m))
            self.assertFalse(any("Petersburg" in n for n in _pins(m)))
        self.assertFalse(any(m.start < 21.0 - 0.5 and m.end > 21.0 + 0.5 for m in maps))   # no map spans the change of subject

    def test_a_map_never_spans_two_sections(self):
        lines = [("Ukrainian drones struck the Kirishi oil refinery near Saint Petersburg.", 7.0)]
        lines += [("The plant burned for hours as crews fought the fire.", 7.0)] * 3
        lines += [("Part two. The war on Ukraine's cities.", 2.0)]
        lines += [("Russian missiles hit Kharkiv overnight.", 7.0)] + [("Several apartment blocks were damaged.", 7.0)] * 3
        plan = _plan(_scenes(lines))
        heading_at = 28.0
        maps = [ly for ly in plan.layers if ly.kind == "tac_map"]
        self.assertTrue(maps)
        for m in maps:
            self.assertFalse(m.start < heading_at - 0.1 and m.end > heading_at + 0.1, (m.start, m.end))
            if m.start >= heading_at:
                self.assertNotIn("Kirishi", _pins(m))

    def test_runs_end_after_about_ninety_seconds(self):
        from cinematic_explainer.war import map_build as MB

        rows = _rows([("Ukrainian drones struck the Kirishi oil refinery again.", 6.0)] * 40)       # 240 s, one place, one section
        log = {r["_no"]: SimpleNamespace(flags=["no_footage"]) for r in rows}
        runs = MB._runs(rows, log)
        self.assertGreaterEqual(len(runs), 3)
        for run in runs:
            self.assertLessEqual(run[-1]["_end"] - run[0]["_start"], MB.MAX_RUN_S + 0.01)

    def test_runs_break_at_a_section_heading(self):
        from cinematic_explainer.war import map_build as MB

        rows = _rows([("Drones hit Kirishi.", 6.0), ("The fire burned all night.", 6.0), ("Part two. The oil war.", 2.0),
                      ("Refineries matter to an army.", 6.0)])
        log = {r["_no"]: SimpleNamespace(flags=["no_footage"]) for r in rows}
        runs = MB._runs(rows, log)
        self.assertEqual([[r["_no"] for r in run] for run in runs], [["1", "2"], ["3", "4"]])

    def test_no_context_fallback(self):
        from cinematic_explainer.war import map_build as MB

        beats = [{"a": 0.0, "b": 5.0, "text": "Nobody expected what came next.", "places": [], "countries": [], "card": None, "strike": False,
                  "drones": False, "route": None, "no": "1"}]
        self.assertIsNone(MB._plan_params(beats, 0.0, {}))

    def test_same_subject_stays_one_map(self):
        from cinematic_explainer.war import map_build as MB

        rows = _rows([("Ukrainian drones struck the Kirishi oil refinery near Saint Petersburg.", 7.0),
                      ("Hours later drones hit the port of Ust-Luga on the Baltic Sea.", 7.0),
                      ("Both sites sit in the Leningrad region.", 7.0),
                      ("Far to the south, Russian glide bombs hit Zaporizhzhia.", 7.0)])
        parts = MB.split_by_geography(rows, _cat())
        self.assertEqual([[r["_no"] for r in p] for p in parts], [["1", "2", "3"], ["4"]])     # nearby places: one map; far away: a new one


if __name__ == "__main__":
    unittest.main()
