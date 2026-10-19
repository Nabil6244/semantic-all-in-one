"""Framing of automatic place outlines (place_focus.frame_camera): moved into view and back, never over a script's own camera, never a stop."""

import copy
import json
import os
import unittest

os.environ["VIDEOGEN_BOUNDARY_NETWORK"] = "0"

import place_focus as PF
from pakmap.compile import compile_csv
from pakmap.words import estimate_words

W, H = 640, 360
WORLD = {"start": {"lon": 20.0, "lat": 20.0, "zoom": 2.0}, "drift": {"pct_per_s": 0.5, "heading_deg": 60}, "moves": []}
US = {"start": {"lon": -98.26, "lat": 39.27, "zoom": 3.3}, "drift": {"pct_per_s": 0.5, "heading_deg": 60}, "moves": []}


def box_ev(eid, w, s, e, n, t0, t1, name="X", **extra):
    ring = [[w, s], [e, s], [e, n], [w, n], [w, s]]
    ev = {"id": eid, "type": "fill", "t_in": t0, "t_out": t1, "polys": [[ring]], "geo_focus": {"entity": name, "official_warning": False}}
    ev.update(extra)
    return ev


HOUSTON = (-95.91, 29.55, -95.01, 30.11)
FLORIDA = (-87.63, 24.54, -80.03, 31.0)


class TestFraming(unittest.TestCase):
    def test_default_camera_is_moved_to_the_outline_and_back(self):
        cam = copy.deepcopy(WORLD)
        notes = PF.frame_camera(cam, [box_ev("f", *HOUSTON, 10.0, 14.0, "Houston")], False, 60.0, W, H)
        self.assertEqual(notes, [])
        a, b = cam["moves"]
        self.assertEqual((a["type"], b["type"]), ("fly_to", "fly_to"))
        self.assertAlmostEqual(a["to"]["lon"], -95.46, delta=0.6)       # aimed a little off centre: the engine's drift carries it back
        self.assertLessEqual(a["to"]["zoom"], PF.FRAME_MAX_ZOOM)
        self.assertGreater(a["to"]["zoom"], 5.0)                                  # a city is framed close, not left at world scale
        self.assertLessEqual(a["t"] + a["dur"], 10.0 + 0.4 + 1e-6)                # in place as the outline appears
        self.assertEqual(b["to"], {"lon": 20.0, "lat": 20.0, "zoom": 2.0})        # back to the shot it was
        self.assertAlmostEqual(b["t"], 14.0)

    def test_the_fitted_view_really_shows_the_outline_inside_the_safe_area(self):
        cam = copy.deepcopy(US)
        PF.frame_camera(cam, [box_ev("f", *FLORIDA, 13.0, 16.0, "Florida")], False, 60.0, W, H)
        to = cam["moves"][0]["to"]
        px = PF._view_box(FLORIDA, (to["lon"], to["lat"], to["zoom"]), W, H)
        self.assertTrue(PF._shown(px, W, H, 0.0), px)

    def test_an_outline_already_in_view_causes_no_move(self):
        cam = copy.deepcopy(US)
        PF.frame_camera(cam, [box_ev("f", -100, 33, -92, 38, 5.0, 9.0, "Oklahoma")], False, 60.0, W, H)
        self.assertEqual(cam["moves"], [])

    def test_the_clipped_outlines_of_the_real_test_are_framed(self):
        for box in (HOUSTON, FLORIDA):
            cam = copy.deepcopy(US)
            PF.frame_camera(cam, [box_ev("f", *box, 10.0, 14.0)], False, 60.0, W, H)
            self.assertEqual(len(cam["moves"]), 2, box)

    def test_a_script_with_camera_rows_is_never_moved_only_told(self):
        cam = copy.deepcopy(US)
        before = json.dumps(cam, sort_keys=True)
        notes = PF.frame_camera(cam, [box_ev("f", *FLORIDA, 13.0, 16.0, "Florida")], True, 60.0, W, H)
        self.assertEqual(json.dumps(cam, sort_keys=True), before)
        self.assertTrue(any("Florida" in n and "left as written" in n for n in notes), notes)

    def test_an_authored_move_under_way_gives_no_note_and_no_move(self):
        cam = copy.deepcopy(US)
        cam["moves"] = [{"type": "fly_to", "t": 12.0, "dur": 5.0, "to": {"lon": -90, "lat": 30, "zoom": 5}}]
        before = json.dumps(cam, sort_keys=True)
        self.assertEqual(PF.frame_camera(cam, [box_ev("f", *FLORIDA, 13.0, 16.0)], True, 60.0, W, H), [])
        self.assertEqual(json.dumps(cam, sort_keys=True), before)

    def test_a_repeat_in_quick_succession_is_one_move_pair_and_chains_without_a_return(self):
        cam = copy.deepcopy(WORLD)
        evs = [box_ev("a", *HOUSTON, 10.0, 13.0, "Houston"), box_ev("b", *FLORIDA, 14.0, 17.0, "Florida")]
        PF.frame_camera(cam, evs, False, 60.0, W, H)
        kinds = [(m["t"], m["to"]["zoom"]) for m in cam["moves"]]
        self.assertEqual(len(cam["moves"]), 3, kinds)                             # fit, fit, one return (none between the two)
        self.assertEqual(cam["moves"][-1]["to"]["zoom"], 2.0)
        for a, b in zip(cam["moves"], cam["moves"][1:]):
            self.assertLess(a["t"] + a["dur"], b["t"])                            # no overlap: _camera's spacing rule can never trip

    def test_unusable_extents_and_huge_regions_are_skipped_with_a_note(self):
        for name, ev in {"bad": box_ev("f", float("nan"), 0, 1, 1, 5.0, 9.0, "bad"),
                         "flat": box_ev("f", 0, 0, 0, 0, 5.0, 9.0, "flat"),
                         "antimeridian": box_ev("f", -179, -17, 179, -16, 5.0, 9.0, "antimeridian")}.items():
            cam = copy.deepcopy(WORLD)
            notes = PF.frame_camera(cam, [ev], False, 60.0, W, H)
            self.assertEqual(cam["moves"], [], name)
            self.assertTrue(notes and name in notes[0], (name, notes))
        cam = copy.deepcopy(US)                                                   # a region needing more than 2 levels of pull-back
        cam["start"]["zoom"] = 5.0
        notes = PF.frame_camera(cam, [box_ev("f", -120, 10, 40, 80, 5.0, 9.0, "Huge")], False, 60.0, W, H)
        self.assertEqual(cam["moves"], [])
        self.assertTrue(any("too large" in n for n in notes))

    def test_a_region_that_cannot_fit_even_at_the_minimum_zoom_is_not_moved_to(self):
        cam = copy.deepcopy(WORLD)                                                # Nunavut: fits neither height nor safe margins at zoom 1.5
        notes = PF.frame_camera(cam, [box_ev("f", -120.68, 51.92, -61.09, 83.12, 5.0, 9.0, "Nunavut")], False, 60.0, W, H)
        self.assertEqual(cam["moves"], [])
        self.assertTrue(any("Nunavut cannot be framed" in n for n in notes), notes)

    def test_a_narrow_small_town_is_framed_not_rejected_for_being_small(self):
        cam = copy.deepcopy(WORLD)
        town = (-93.26, 41.58, -93.22, 41.64)                                      # about 3 km wide
        notes = PF.frame_camera(cam, [box_ev("f", *town, 5.0, 9.0, "Town")], False, 60.0, W, H)
        self.assertEqual(notes, [])
        self.assertEqual(len(cam["moves"]), 2)
        z = cam["moves"][0]["to"]["zoom"]
        px = PF._view_box(town, ((town[0] + town[2]) / 2, (town[1] + town[3]) / 2, z), W, H)    # centred: how big it is on screen at that zoom
        self.assertEqual(z, PF.FRAME_MAX_ZOOM)
        self.assertFalse(PF._shown(px, W, H, 0.0), "narrow on screen (under the 'already visible' minimum width), yet framed")

    def test_no_time_for_the_move_is_a_note_not_an_error(self):
        cam = copy.deepcopy(WORLD)
        notes = PF.frame_camera(cam, [box_ev("f", *HOUSTON, 0.1, 3.0, "Houston")], False, 60.0, W, H)
        self.assertEqual(cam["moves"], [])
        self.assertTrue(any("no time" in n for n in notes), notes)

    def test_events_are_never_touched_and_warning_polygons_are_ignored(self):
        warn = {"id": "wx", "type": "fill", "t_in": 0.0, "t_out": 60.0, "polys": [[[[-95, 29], [-94, 29], [-94, 30], [-95, 29]]]], "color": "#DF2721"}
        flagged = box_ev("w2", *HOUSTON, 10.0, 14.0, "W", )
        flagged["geo_focus"]["official_warning"] = True
        evs = [warn, flagged, box_ev("f", *HOUSTON, 20.0, 24.0, "Houston")]
        before = json.dumps(evs, sort_keys=True)
        cam = copy.deepcopy(WORLD)
        PF.frame_camera(cam, evs, False, 60.0, W, H)
        self.assertEqual(json.dumps(evs, sort_keys=True), before)
        self.assertTrue(all(m["t"] >= 19.0 for m in cam["moves"]), cam["moves"])  # only the neutral focus event was framed

    def test_without_focus_events_nothing_changes(self):
        cam = copy.deepcopy(US)
        self.assertEqual(PF.frame_camera(cam, [{"id": "x", "type": "fill", "t_in": 0, "t_out": 5}], False, 60.0, W, H), [])
        self.assertEqual(cam, US)


import pathlib
import shutil
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
NODE_PROBE = r"""
import fs from 'fs';
import {createCamera, lonLatToWorld} from '%s';
const j = JSON.parse(fs.readFileSync(process.argv[2]));
const cam = createCamera({camera: j.camera, width: j.w, height: j.h, duration: j.duration});
const out = [];
for (const t of j.times) {
  const c = cam.at(t), b = lonLatToWorld(c.lon, c.lat), k = 512 * 2 ** c.zoom;
  let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
  for (const [lon, lat] of j.pts) { const a = lonLatToWorld(lon, lat); const x = j.w / 2 + (a[0] - b[0]) * k, y = j.h / 2 + (a[1] - b[1]) * k; x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); }
  out.push([x0, y0, x1, y1]);
}
console.log(JSON.stringify(out));
""" % (ROOT / "pakmap-engine" / "lib" / "camera.mjs").as_uri()   # a file:// URL: Node rejects a bare D:\ path in an import on Windows


@unittest.skipUnless(shutil.which("node"), "node not available")
class TestAgainstTheEngineCamera(unittest.TestCase):
    """The planned moves are checked with the engine's own camera (idle drift included), not with the planner's model."""

    def check(self, box, t0, t1, cam0):
        cam = copy.deepcopy(cam0)
        notes = PF.frame_camera(cam, [box_ev("f", *box, t0, t1)], False, 60.0, W, H)
        self.assertEqual(notes, [])
        self.assertEqual(len(cam["moves"]), 2)
        end = cam["moves"][0]["t"] + cam["moves"][0]["dur"]
        times = [max(t0, end), (max(t0, end) + t1) / 2, t1]
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "in.json").write_text(json.dumps({"camera": cam, "w": W, "h": H, "duration": 60.0, "times": times, "pts": [[box[0], box[1]], [box[2], box[3]]]}))
        (d / "probe.mjs").write_text(NODE_PROBE)
        r = subprocess.run(["node", str(d / "probe.mjs"), str(d / "in.json")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        for px in json.loads(r.stdout):
            self.assertTrue(PF._inside(px, W, H, 0.0), (box, px))

    def test_houston_florida_a_small_town_and_a_big_state_stay_inside_the_frame(self):
        for box in (HOUSTON, FLORIDA, (-99.05, 31.64, -98.96, 31.76), (-93.30, 41.58, -93.22, 41.64), (-124.4, 32.5, -114.1, 42.0)):
            for cam0 in (WORLD, US):
                self.check(box, 10.0, 14.0, cam0)


NARR = ("The hurricane is approaching Houston tonight and the sky is dark. Crews have spent the whole week preparing the shelters and the roads for the first heavy rain. "
        "Forecasters say the worst of it will arrive after midnight. Meanwhile the storm made landfall in Florida early on Friday morning. Emergency teams are checking the coast.")


class TestInCompile(unittest.TestCase):
    def setUp(self):
        # Houston's outline from a fake OpenStreetMap answer (test_place_focus's fixture), not the network or this machine's cache:
        # a CI runner has neither, and the city then (correctly) gets no outline
        from test_place_focus import FakeNominatim, item, store
        st, _ = store(FakeNominatim({"Houston": [item()]}), tempfile.mkdtemp())
        orig = PF.focus_events
        self.addCleanup(setattr, PF, "focus_events", orig)
        PF.focus_events = lambda *a, **k: orig(*a, **{**k, "store": k.get("store") or st})

    def run_compile(self, csv, on=True):
        import tempfile
        d = tempfile.mkdtemp()
        p = os.path.join(d, "s.csv")
        open(p, "w").write(csv)
        w0 = estimate_words(NARR)
        k = 19.0 / w0[-1][2]
        words = [(a, b * k, c * k) for a, b, c in w0]
        return compile_csv(p, words, duration=19.5, width=W, height=H, fps=30, base_dir=d, auto_templates=on)

    HEAD = "item_no,vo_anchor,layer_type,layer_id,label_text,sub_text,geo_ref,value_to,value_format,camera_action,frame\n1,The hurricane,hud_title,,HURRICANE,GULF COAST,,,,,\n"

    def test_no_camera_row_frames_both_outlines(self):
        r = self.run_compile(self.HEAD)
        self.assertEqual([e["geo_focus"]["entity"] for e in r.spec["events"] if e.get("geo_focus")], ["Houston", "Florida"])
        self.assertGreaterEqual(len(r.spec["camera"]["moves"]), 3)
        self.assertEqual(r.spec["camera"]["moves"], r.report.moves)

    def test_a_camera_row_keeps_the_camera_exactly_and_warns(self):
        csv = self.HEAD + "1,The hurricane,camera,c0,,,United States,,,start,continental\n"
        on, off = self.run_compile(csv), self.run_compile(csv, on=False)
        self.assertEqual(on.spec["camera"], off.spec["camera"])
        self.assertTrue(any("left as written" in w for w in on.report.warnings), on.report.warnings)

    def test_feature_off_has_no_focus_and_no_extra_moves(self):
        r = self.run_compile(self.HEAD, on=False)
        self.assertEqual(r.spec["camera"]["moves"], [])


if __name__ == "__main__":
    unittest.main()
