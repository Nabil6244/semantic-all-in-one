"""Phase 4 regression tests: Explainer map beats framed, labelled and grounded through the existing pakMap path.

Independent of the code under test, the camera is checked in the COMPILED pakMap spec (hybrid.compile.compile_plan, the application's own compiler): the view in force when a layer
appears is rebuilt from spec["camera"] with pakmap.geo's own projection constants, and the place's bounding box must lie inside it. Offline, deterministic, imagery-free (no render).
usage: python3 -B explainer/spike/test_phase4_maps.py   (from the repository root)"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True

from test_director_real_material import (SCRIPT, WORDS, DUR, KoreaCache, map_places, run, synth)       # noqa: E402
from explainer.beats.relevance import beat_tokens, check_plan, find_phrase                              # noqa: E402

MARGIN = 0.03          # the view must hold the whole bounding box with this fraction of the frame to spare (the camera drifts slowly)


def view_box(lon, lat, zoom, w=1920, h=1080):
    from pakmap import geo as G
    k = 512 * 2 ** zoom
    dx = w / k * 360.0
    cy, dy = G.merc_y(lat), h / k
    ys = sorted((G.merc_lat(cy - dy / 2), G.merc_lat(cy + dy / 2)))
    return (lon - dx / 2, ys[0], lon + dx / 2, ys[1])


def camera_views(spec):
    """[(time, (lon, lat, zoom))]: the compiled camera; a move counts from 60% of its duration."""
    cam = spec["camera"]
    s = cam["start"]
    out = [(0.0, (s["lon"], s["lat"], s["zoom"]))]
    cur = [s["lon"], s["lat"], s["zoom"]]
    for m in sorted(cam.get("moves", []), key=lambda x: x["t"]):
        to = m["to"]
        cur = [to.get("lon", cur[0]), to.get("lat", cur[1]), to.get("zoom", cur[2])]
        out.append((m["t"] + 0.6 * m["dur"], tuple(cur)))      # a move counts once it is 60% done: that is what a viewer sees when a layer appears
    return out


def view_at(spec, t):
    cur = None
    for tt, v in camera_views(spec):
        if tt <= t + 1e-9:
            cur = v
    return cur


def inside(box, bbox, margin=MARGIN):
    w, s, e, n = box
    bw, bs, be, bn = bbox
    mx, my = (e - w) * margin, (n - s) * margin
    return bw >= w + mx and be <= e - mx and bs >= s + my and bn <= n - my


def layer_frames(plan):
    """For every map layer with a place: (layer id, place, time, in-view?) judged on the compiled spec."""
    from hybrid.compile import compile_plan
    from hybrid.plan import HybridPlan
    from pakmap import geo as G
    hp = HybridPlan.from_dict(json.loads(json.dumps(plan)))
    spec = compile_plan(hp, base_dir=str(ROOT), validate=False).spec
    out = []
    for b in plan["beats"]:
        if b["mode"] != "map":
            continue
        for l in b.get("layers", []):
            if l["type"] in ("fill", "marker", "zone_label") and l.get("place"):
                loc = G.resolve(l["place"])
                bbox = loc.bbox if loc.is_area else (loc.lon - 0.01, loc.lat - 0.01, loc.lon + 0.01, loc.lat + 0.01)
                v = view_at(spec, l["t"])
                out.append((l["id"], l["place"], l["t"], v is not None and inside(view_box(*v), bbox)))
    return out


def beat_of(plan, kind="map"):
    return [b for b in plan["beats"] if b["mode"] == kind]


TWO_KOREAS = ("Look at the lights of the peninsula from space at night. Then the border runs between South Korea and North Korea and nobody crosses it. "
              "The South is bright and the North is dark. Over the sea the weather is calm and the sky is clear tonight. Every night the same lights burn in the same cities. "
              "Nothing about the picture has changed for a very long time.")


class Framing(unittest.TestCase):
    def test_korea_places_are_inside_the_compiled_camera_view(self):
        r = KoreaCache.get()
        self.assertIsNotNone(r.plan, r.problems)
        frames = layer_frames(r.plan)
        self.assertTrue(frames)
        bad = [(i, p, t) for i, p, t, ok in frames if not ok]
        self.assertEqual(bad, [], f"layers whose place is not fully inside the camera view: {bad}")

    def test_korea_has_no_off_screen_warning(self):
        r = KoreaCache.get()
        self.assertFalse([w for w in r.warnings if "off screen" in w], r.warnings)

    def test_two_neighbours_spoken_two_seconds_apart_share_one_good_view(self):
        words, dur = synth(TWO_KOREAS)
        r = run(words, TWO_KOREAS, dur, max_map_share=0.6)
        self.assertIsNotNone(r.plan, r.problems)
        maps = beat_of(r.plan)
        self.assertTrue(maps)
        names = map_places(r.plan)
        self.assertIn("South Korea", names)
        self.assertIn("North Korea", names)
        self.assertEqual([x for x in layer_frames(r.plan) if not x[3]], [])

    def test_a_single_place_is_framed_on_that_place(self):
        s = ("The ancient empire of Egypt grew along a great river. Farmers planted wheat each year. Traders carried grain downstream to the cities. "
             "Priests recorded the harvest on papyrus. Every season the river rose and fell. The kings built storehouses to hold the grain.")
        words, dur = synth(s)
        r = run(words, s, dur, max_map_share=0.6)
        self.assertIsNotNone(r.plan, r.problems)
        first = beat_of(r.plan)[0]
        start = [c for c in first.get("camera", []) if c["action"] == "start"]
        self.assertTrue(start and start[0]["place"] == "Egypt", first.get("camera"))
        self.assertEqual([x for x in layer_frames(r.plan) if not x[3]], [])

    def test_far_apart_places_in_a_short_beat_are_never_drawn_off_screen(self):
        s = ("The trade route ran from Rome to Beijing across the whole continent in only a few months. Nobody had ever travelled so far. "
             "Merchants carried silk and glass along the way. The journey changed every city it touched. Stories travelled faster than the caravans did.")
        words, dur = synth(s)
        r = run(words, s, dur, max_map_share=0.9, min_beat_s=3.2)
        self.assertIsNotNone(r.plan, r.problems)
        self.assertEqual([x for x in layer_frames(r.plan) if not x[3]], [], "a layer was drawn where the camera does not show its place")
        for b in beat_of(r.plan):
            for c in b.get("camera", []):
                if c["action"] != "start":
                    self.assertLessEqual(c["t"] + float(c.get("dur") or 0), b["end"] + 1e-6, f"camera move runs past the end of {b['id']}")
                    self.assertGreaterEqual(c["t"], b["start"] - 1e-6)

    def test_a_place_that_cannot_be_framed_is_rejected_with_a_reason(self):
        s = ("From Lisbon to Tokyo the ships sailed for years. Nobody believed the distance could be crossed. Every harbour on the way had its own stories. "
             "Captains kept careful logs of the winds and the currents. The crews were hungry and tired. In the end a few of them came home.")
        words, dur = synth(s)
        r = run(words, s, dur, max_map_share=0.9)
        self.assertIsNotNone(r.plan, r.problems)
        self.assertEqual([x for x in layer_frames(r.plan) if not x[3]], [])
        rej = r.report["selection"].get("map_layers_rejected", [])
        shown = set(map_places(r.plan))
        for name in ("Lisbon", "Tokyo"):
            self.assertTrue(name in shown or any(d["place"] == name and d["reason"].strip() for d in rej), f"{name}: neither framed nor explained ({shown}, {rej})")

    def test_the_framing_module_rejects_a_hand_built_out_of_frame_layer(self):
        from explainer.beats import framing
        plan = {"beats": [{"id": "m1", "mode": "map", "start": 0.0, "end": 6.0,
                           "camera": [{"action": "start", "place": "Pakistan", "frame": "country"}],
                           "layers": [{"id": "m1_fill1", "type": "fill", "t": 1.0, "place": "Japan", "role": "subject"}]}]}
        found = framing.check_framing(plan)
        self.assertTrue(found and "Japan" in found[0], found)


class MapLayers(unittest.TestCase):
    def test_every_filled_country_gets_a_label_at_or_after_its_fill(self):
        r = KoreaCache.get()
        for b in beat_of(r.plan):
            fills = [l for l in b["layers"] if l["type"] == "fill"]
            labels = {l["place"]: l for l in b["layers"] if l["type"] == "zone_label"}
            self.assertTrue(fills)
            for f in fills:
                self.assertIn(f["place"], labels, f"{b['id']}: {f['place']} is outlined but not labelled")
                self.assertGreaterEqual(labels[f["place"]]["t"], f["t"] - 1e-6)

    def test_a_spoken_quantity_in_a_map_beat_becomes_a_stat_grounded_in_the_words(self):
        s = ("Look at the delta where the river meets the sea. About 40 million people live in Egypt today and almost all of them live beside the water. "
             "The desert covers the rest of the country. Cities spread along the banks. Farmers still use the old canals. Boats carry goods from town to town.")
        words, dur = synth(s)
        r = run(words, s, dur, max_map_share=0.9)
        self.assertIsNotNone(r.plan, r.problems)
        stats = [l for b in beat_of(r.plan) for l in b["layers"] if l["type"] == "stat"]
        self.assertEqual(len(stats), 1, [l for b in beat_of(r.plan) for l in b["layers"]])
        self.assertEqual(float(stats[0]["to"]), 40.0)
        self.assertIn("million", (stats[0]["format"] + stats[0].get("sub", "")).lower())
        b = [x for x in beat_of(r.plan) if stats[0] in x["layers"]][0]
        tk = beat_tokens(words, b["start"], b["end"])
        self.assertIsNotNone(find_phrase(tk, "40 million people") or find_phrase(tk, "40 million"))

    def test_a_year_is_not_a_statistic(self):
        s = ("In 1994 the leader of Egypt opened the new canal. Cities spread along the banks of the river. Farmers still use the old channels. "
             "Boats carry goods from town to town. The desert covers the rest of the country. Every season the river rose and fell.")
        words, dur = synth(s)
        r = run(words, s, dur, max_map_share=0.9)
        self.assertIsNotNone(r.plan, r.problems)
        self.assertEqual([l for b in beat_of(r.plan) for l in b["layers"] if l["type"] == "stat"], [])

    def test_every_map_layer_is_tied_to_the_beats_own_words_and_validates(self):
        for r, words in ((KoreaCache.get(), WORDS),):
            rep = check_plan(r.plan, words)
            self.assertEqual([p for p in rep.problems if "file not found" not in p and "not a readable" not in p and "clip 1:" not in p], [])   # board clips are not encoded in these tests
            self.assertEqual(r.report["hybrid_validate"].get("errors"), [])

    def test_the_plan_compiles_through_the_applications_own_compiler(self):
        from hybrid.compile import compile_plan
        from hybrid.plan import HybridPlan
        r = KoreaCache.get()
        c = compile_plan(HybridPlan.from_dict(json.loads(json.dumps(r.plan))), base_dir=str(ROOT), validate=False)
        self.assertEqual(c.report.errors, [])
        kinds = {e["type"] for e in c.spec["events"]}
        self.assertTrue({"fill", "label"} & kinds or "zone_label" in kinds or "zone" in " ".join(kinds), kinds)


class Preserved(unittest.TestCase):
    def test_imagery_is_chosen_by_the_renderer_not_baked_into_the_plan(self):
        r = KoreaCache.get()
        text = json.dumps(r.plan)
        for key in ("imagery", "flat_only", "tiles", "cache"):
            self.assertNotIn(f'"{key}"', text)

    def test_the_pakmap_cache_folder_is_the_one_the_application_uses(self):
        import os
        from pakmap import engine_runner
        os.environ["VIDEOGEN_PAKMAP_CACHE"] = "/tmp/_p4_cache_probe"
        try:
            self.assertEqual(str(engine_runner.cache_dir()), "/tmp/_p4_cache_probe")
        finally:
            os.environ.pop("VIDEOGEN_PAKMAP_CACHE", None)
            try:
                Path("/tmp/_p4_cache_probe").rmdir()
            except OSError:
                pass

    def test_planning_is_deterministic(self):
        a = run(WORDS, SCRIPT, DUR)
        b = run(WORDS, SCRIPT, DUR)
        self.assertEqual(json.dumps(a.plan, sort_keys=True), json.dumps(b.plan, sort_keys=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
