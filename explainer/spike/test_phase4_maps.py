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


ALLOWED_FILL_ROLES = ("compare", "green", "red", "featured", "accent", "orange")      # pakMap's own fill roles (blue, green, bright red, gold, purple, orange); never the dark "primary" brown


class CountryColours(unittest.TestCase):
    def fills(self, plan):
        return [(b["id"], l) for b in plan["beats"] if b["mode"] == "map" for l in b.get("layers", []) if l["type"] == "fill"]

    def test_every_filled_country_gets_its_own_colour_role(self):
        r = KoreaCache.get()
        fills = self.fills(r.plan)
        self.assertGreaterEqual(len(fills), 2)
        for bid, l in fills:
            self.assertIn(l.get("role"), ALLOWED_FILL_ROLES, f"{bid}: {l['place']} has role {l.get('role')!r}")
        roles = [l["role"] for _b, l in fills]
        self.assertEqual(len(set(roles)), len(roles), "two countries on one map must not share a colour")

    def test_a_country_keeps_its_colour_everywhere_in_the_video(self):
        s = ("The ancient empire of Egypt grew along a great river. Farmers planted wheat each year beside the water. Traders carried grain downstream to the cities. "
             "Priests recorded the harvest on papyrus. Far to the north the people of Greece built small harbour towns. Their ships crossed the sea to trade with Egypt again. "
             "Sailors told stories of the great river. Merchants from Greece sold olive oil in the markets of Egypt. The two lands grew rich together.")
        words, dur = synth(s)
        r = run(words, s, dur, max_map_share=0.9)
        self.assertIsNotNone(r.plan, r.problems)
        seen = {}
        for bid, l in self.fills(r.plan):
            seen.setdefault(l["place"], set()).add(l["role"])
        self.assertTrue(seen)
        for place, roles in seen.items():
            self.assertEqual(len(roles), 1, f"{place} changes colour between maps: {roles}")
        if len(seen) > 1:
            self.assertEqual(len({next(iter(v)) for v in seen.values()}), len(seen))

    def test_the_compiled_pakmap_spec_draws_the_fills_in_different_colours(self):
        from hybrid.compile import compile_plan
        from hybrid.plan import HybridPlan
        r = KoreaCache.get()
        c = compile_plan(HybridPlan.from_dict(json.loads(json.dumps(r.plan))), base_dir=str(ROOT), validate=False)
        roles = [e.get("role") for e in c.spec["events"] if e["type"] == "fill"]
        self.assertEqual(len(roles), 2)
        self.assertEqual(len(set(roles)), 2, roles)
        self.assertNotIn("primary", roles)

    def test_the_colours_do_not_change_the_other_gates(self):
        r = KoreaCache.get()
        self.assertEqual(r.report["hybrid_validate"].get("errors"), [])
        self.assertEqual([x for x in layer_frames(r.plan) if not x[3]], [])

    def test_colours_are_deterministic(self):
        a = run(WORDS, SCRIPT, DUR)
        b = run(WORDS, SCRIPT, DUR)
        self.assertEqual([l.get("role") for _x, l in self.fills(a.plan)], [l.get("role") for _x, l in self.fills(b.plan)])


WIDE_LIST = ("It ruled India and Canada, Australia and Egypt, Nigeria, Jamaica and Malaysia. At any hour of the day it was daytime somewhere in that empire. "
             "Farmers planted wheat each year beside the water and traders carried grain downstream to the cities. Priests recorded the harvest on papyrus. "
             "Every season the river rose and fell and the kings built storehouses to hold the grain. The two lands grew rich together.")
WIDE_NAMES = ("India", "Canada", "Australia", "Egypt", "Nigeria", "Jamaica", "Malaysia")


def map_hash(plan):
    import hashlib
    return hashlib.sha256(json.dumps([b for b in plan["beats"] if b["mode"] == "map"], sort_keys=True).encode()).hexdigest()[:16]


class WideCountryList(unittest.TestCase):
    """A sentence that names many far-apart countries is one wide map: every country filled and labelled on its own word."""

    @classmethod
    def setUpClass(cls):
        cls.words, cls.dur = synth(WIDE_LIST)
        cls.r = run(cls.words, WIDE_LIST, cls.dur, max_map_share=0.9)

    def fills(self):
        return {l["place"]: (b["id"], l) for b in self.r.plan["beats"] if b["mode"] == "map" for l in b.get("layers", []) if l["type"] == "fill"}

    def test_every_spoken_country_is_filled(self):
        self.assertIsNotNone(self.r.plan, self.r.problems)
        self.assertEqual(sorted(set(WIDE_NAMES) - set(self.fills())), [], f"filled: {sorted(self.fills())}")

    def test_all_of_them_are_inside_the_compiled_camera_view_when_they_appear(self):
        bad = [x for x in layer_frames(self.r.plan) if not x[3]]
        self.assertEqual(bad, [])

    def test_each_has_its_own_colour_and_a_label_or_a_recorded_reason(self):
        f = self.fills()
        roles = [l["role"] for _b, l in f.values()]
        self.assertEqual(len(set(roles)), len(roles), roles)
        labelled = {l["place"] for b in self.r.plan["beats"] if b["mode"] == "map" for l in b.get("layers", []) if l["type"] == "zone_label"}
        skipped = {d["place"] for d in self.r.report["selection"].get("map_labels_skipped", []) if d.get("reason", "").strip()}
        for name in f:
            self.assertTrue(name in labelled or name in skipped, f"{name}: no label and no recorded reason")

    def test_each_fill_appears_on_its_own_spoken_word(self):
        from explainer.beats.relevance import find_phrase
        for name, (bid, l) in self.fills().items():
            b = next(x for x in self.r.plan["beats"] if x["id"] == bid)
            m = find_phrase(beat_tokens(self.words, b["start"], b["end"]), name)
            self.assertIsNotNone(m, name)
            self.assertTrue(-0.2 - 1e-6 <= l["t"] - m["start"] <= 0.6 + 1e-6, f"{name}: layer at {l['t']} but spoken at {m['start']}")
        ts = sorted(l["t"] for _b, l in self.fills().values())
        self.assertGreater(len(set(ts)), 4, "the fills arrive one by one as the countries are named")

    def test_the_plan_still_passes_the_relevance_and_editorial_gates(self):
        rep = check_plan(self.r.plan, self.words)
        self.assertEqual([p for p in rep.problems if "file not found" not in p and "clip 1:" not in p], [])
        self.assertEqual(self.r.report["hybrid_validate"].get("errors"), [])

    def test_two_and_three_place_beats_are_unchanged(self):
        words, dur = synth(TWO_KOREAS)
        r = run(words, TWO_KOREAS, dur, max_map_share=0.6)
        self.assertEqual(map_hash(r.plan), "9dd4957c7a045b64")
        self.assertEqual(map_hash(KoreaCache.get().plan), "3025bc75875ae4ad")

    def test_deterministic(self):
        again = run(self.words, WIDE_LIST, self.dur, max_map_share=0.9)
        self.assertEqual(json.dumps(self.r.plan, sort_keys=True), json.dumps(again.plan, sort_keys=True))


REAL_PROJECT = Path.home() / "Downloads" / "VideoGenerator" / "Video_2026-10-23_032_explainer"


def compile_with_standins(plan, work):
    """The application's own compiler with validate=True (the engine's rules included). Board and footage clips that were never encoded (materialize=False) get a tiny local stand-in file."""
    import copy
    import subprocess
    from hybrid.compile import compile_plan
    from hybrid.plan import HybridPlan
    standin = Path(work) / "standin.mp4"
    if not standin.exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=320x180:r=30:d=3", "-pix_fmt", "yuv420p", str(standin)], check=True)
    p = copy.deepcopy(plan)
    for b in p["beats"]:
        if b["mode"] == "footage":
            for c in b["footage"]["clips"]:
                c["asset"] = str(standin)
    return compile_plan(HybridPlan.from_dict(json.loads(json.dumps(p))), base_dir=str(ROOT), validate=True)


class WideBeatsThroughTheRealCompiler(unittest.TestCase):
    """The engine's own rules (no more than 5 text layers at once) and the plan check's framing warning, on the synthetic list and on the user's real project beat."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.tmp = tempfile.mkdtemp()
        cls.words, cls.dur = synth(WIDE_LIST)
        cls.r = run(cls.words, WIDE_LIST, cls.dur, max_map_share=0.9)
        cls.real = None
        wf = REAL_PROJECT / "state" / "narration_words.json"
        if wf.is_file():
            from hybrid.narration import build_sentences
            W = [tuple(w) for w in json.loads(wf.read_text())["words"]]
            script = (REAL_PROJECT / "script" / "narration.txt").read_text()
            last = build_sentences(W, script, W[-1][2] + 0.4)[3]
            words = [w for w in W if w[1] < last.end + 1e-6]
            text = script[: script.index(last.text) + len(last.text)]
            cls.real = (words, text, run(words, text, last.end + 0.4))

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _text_layers_on_screen(self, plan):
        worst = 0
        for b in plan["beats"]:
            if b["mode"] != "map":
                continue
            lay = [l for l in b.get("layers", []) if l["type"] in ("zone_label", "caption", "stat", "marker", "hud_title")]
            for l in lay:
                t = l["t"]
                alive = [x for x in lay if x["t"] <= t + 1e-9 and (x.get("until", "beat_end") == "beat_end" or isinstance(x.get("until"), (int, float)) and x["until"] > t)
                         and (x.get("hold") is None or x["t"] + x["hold"] > t)]
                worst = max(worst, len(alive))
        return worst

    def test_the_synthetic_list_compiles_with_zero_errors_and_at_most_five_text_layers(self):
        c = compile_with_standins(self.r.plan, self.tmp)
        self.assertEqual(c.report.errors, [])
        self.assertLessEqual(self._text_layers_on_screen(self.r.plan), 5)

    def test_every_country_of_the_list_is_still_filled_in_its_own_colour(self):
        fills = [l for b in self.r.plan["beats"] if b["mode"] == "map" for l in b.get("layers", []) if l["type"] == "fill"]
        self.assertEqual(sorted(l["place"] for l in fills), sorted(WIDE_NAMES))
        self.assertEqual(len({l["role"] for l in fills}), len(fills))

    def test_skipped_labels_are_recorded(self):
        labelled = {l["place"] for b in self.r.plan["beats"] if b["mode"] == "map" for l in b.get("layers", []) if l["type"] == "zone_label"}
        skipped = {d["place"] for d in self.r.report["selection"].get("map_labels_skipped", [])}
        for n in WIDE_NAMES:
            self.assertTrue(n in labelled or n in skipped, n)

    def test_the_plan_check_gives_no_off_screen_warning_for_the_wide_beat(self):
        rep = check_plan(self.r.plan, self.words)
        self.assertEqual([w for w in rep.warnings if "off screen" in w], [])

    def test_the_users_real_project_beat_compiles_with_zero_errors(self):
        if self.real is None:
            self.skipTest("the real project is not on this machine")
        words, text, r = self.real
        self.assertIsNotNone(r.plan, r.problems)
        c = compile_with_standins(r.plan, self.tmp)
        self.assertEqual(c.report.errors, [])
        self.assertLessEqual(self._text_layers_on_screen(r.plan), 5)
        fills = [l["place"] for b in r.plan["beats"] if b["mode"] == "map" for l in b.get("layers", []) if l["type"] == "fill"]
        self.assertGreaterEqual(len(set(fills)), 7)

    def test_the_users_real_project_beat_has_no_off_screen_warning(self):
        if self.real is None:
            self.skipTest("the real project is not on this machine")
        words, text, r = self.real
        rep = check_plan(r.plan, words)
        self.assertEqual([w for w in rep.warnings if "off screen" in w], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
