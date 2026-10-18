"""Normal Video + gfx-core templates (normal_gfx/, gfx-overlay-engine/): the allowlist, the narration planner, the cached batch renderer, the composite layer."""

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import gfx_templates as G
from normal_gfx import composite, planner, runner


def _browser_ok() -> bool:
    try:
        from map_scene.render import _browser_channel, _node
        from providers.playwright_chromium import is_playwright_chromium_installed, system_chrome_available

        _node()
        return is_playwright_chromium_installed() or system_chrome_available()
    except Exception:
        return False


def _words(text, per=0.3, t0=0.0):
    out, t = [], t0
    for tok in text.split():
        out.append((tok, t, t + per - 0.02))
        t += per
    return out


class Allowlist(unittest.TestCase):
    def test_every_template_has_one_valid_mode(self):
        data = planner.allowlist()
        lib = G.load_library()
        self.assertEqual(set(data["templates"]), set(lib))
        self.assertTrue(all(v["mode"] in ("auto", "doc", "manual", "full_frame", "excluded") for v in data["templates"].values()))

    def test_map_templates_are_excluded(self):
        data = planner.allowlist()
        for tid, t in G.load_library().items():
            if any(s.get("from") in ("geo", "geo_area") for s in (t.get("slots") or {}).values()) or any(i.get("follow") for i in t["items"]):
                self.assertEqual(data["templates"][tid]["mode"], "excluded", tid)

    def test_full_frame_cards_are_off_by_default(self):
        data = planner.allowlist()
        self.assertFalse(data["full_frame_enabled"])
        for tid in planner.allowed("auto", data):
            self.assertNotEqual(data["templates"][tid]["mode"], "full_frame")

    def test_auto_and_doc_ids_exist_and_doc_looks_map_to_them(self):
        data = planner.allowlist()
        for look, tid in data["doc_looks"].items():
            self.assertIn(data["templates"][tid]["mode"], ("doc", "auto", "full_frame"), look)
        own = {"end_question", "chapter_words"} | {t for v in data["variants"].values() for t in v}
        for tid in planner.allowed("auto", data):
            self.assertIn(tid, {a[0] for a in G.AUTO} | own)


class Planner(unittest.TestCase):
    SCRIPT = ("The observatory sits high in the desert, far from any town, road or light, and almost nothing grows there at all. Maria Lopez, a geologist at the observatory, has worked on the mountain for years. "
              "In 1998 the first light reached the mirror and the room fell silent. They chose the sharper image because the data would be "
              "studied for decades. The rest of the night was quiet and clear for the telescopes.")

    def _plan(self, existing=()):
        words = _words(self.SCRIPT)
        total = words[-1][2] + 1
        rows = [{"scene_number": "1", "script_segment": self.SCRIPT, "start_time": 0.0}]
        return planner.plan_graphics(words, total, rows, [(0.0, total)], list(existing)), total

    def test_graphics_come_only_from_the_narration_and_never_from_a_map(self):
        plan, _ = self._plan()
        ids = {e["template"]["id"] for e in plan.events}
        self.assertIn("name_bar", ids)
        data = planner.allowlist()
        for e in plan.events:
            self.assertIn(data["templates"][e["template"]["id"]]["mode"], ("auto", "doc"))
            self.assertTrue(e.get("over_footage"))
        name = next(e for e in plan.events if e["template"]["id"] == "name_bar")
        self.assertEqual(name["slots"]["label"], "MARIA LOPEZ")
        self.assertIn("GEOLOGIST", name["slots"]["sub"])

    def test_a_year_is_drawn_from_the_sentence(self):
        script = "The observatory sits high in the desert, far from any town, road or light, and almost nothing grows there at all. In 1998 the first light reached the mirror."
        words = _words(script)
        total = words[-1][2] + 1
        plan = planner.plan_graphics(words, total, [{"scene_number": "1", "script_segment": script, "start_time": 0.0}], [(0.0, total)], [])
        self.assertEqual([e["slots"]["text"] for e in plan.events if e["template"]["id"] == "year_wipe"], ["1998"])

    def test_never_two_at_once_and_pacing(self):
        plan, _ = self._plan()
        ev = sorted(plan.events, key=lambda e: e["t_in"])
        for a, b in zip(ev, ev[1:]):
            self.assertLessEqual(a["t_out"], b["t_in"])
        self.assertTrue(all(e["t_in"] >= 4.0 for e in ev))

    def test_a_graphic_already_planned_reserves_its_window(self):
        plan, total = self._plan()
        first = plan.events[0]
        spec = SimpleNamespace(start=first["t_in"] - 0.2, end=first["t_out"] + 0.2, role="NAME", decision="TEXT", graphic_id="x", text=None, payload={})
        again, _ = self._plan([spec])
        for e in again.events:
            self.assertTrue(e["t_out"] <= spec.start or e["t_in"] >= spec.end, e["id"])

    def test_a_template_number_replaces_the_plain_stat_with_the_same_number(self):
        script = "The first line is only a quiet opening for the story. About 60 percent of the planet is covered by oceans and seas today."
        words = _words(script)
        total = words[-1][2] + 1
        t0 = next(a for w, a, b in words if w.startswith("60"))
        stat = SimpleNamespace(graphic_id="stat1", role="STATISTIC", decision="STATISTIC", start=t0, end=t0 + 3, text=SimpleNamespace(text="60%", secondary_text="of the planet"), payload={})
        plan = planner.plan_graphics(words, total, [{"scene_number": "1", "script_segment": script, "start_time": 0.0}], [(0.0, total)], [stat])
        got = [e for e in plan.events if e["template"]["id"] in ("ring_percent", "big_number")]
        if got:      # the extractor decides whether the sentence states a share; when it does the stat is replaced, never doubled
            self.assertEqual(got[0].get("replaces"), ["stat1"])
            self.assertEqual(plan.replaced_graphic_ids, ["stat1"])

    def test_quote_with_attribution_is_not_cut_into_a_pull_quote(self):
        script = 'Silence filled the room for a while after the news. "Nobody had ever seen the galaxy in this much detail before," said Dr. Lopez in her first interview.'
        words = _words(script)
        total = words[-1][2] + 1
        plan = planner.plan_graphics(words, total, [{"scene_number": "1", "script_segment": script, "start_time": 0.0}], [(0.0, total)], [])
        for e in plan.events:
            self.assertFalse(e["slots"].get("text", "").endswith("SAID DR."), e)


class Coverage(unittest.TestCase):
    """Which templates a narration can really place automatically (not merely allow-listed)."""

    def test_automatic_count_and_every_automatic_template_has_a_way_in(self):
        from normal_gfx import rules

        data = planner.allowlist()
        automatic = set(planner.allowed("auto", data)) | set(planner.allowed("doc", data))
        self.assertEqual(len(automatic), 31)                               # was 17 before the variants and rules (the 4 full-frame cards of those 17 are now off)
        full = {t for t, v in data["templates"].items() if v["mode"] == "full_frame" and t in data["doc_looks"].values()}
        self.assertEqual(full, {"day_cards", "dossier_card", "quote_card_black", "three_rings"})
        reachable = {a[0] for a in G.AUTO} | (set(data["doc_looks"].values()) - full) | {"end_question", "chapter_words"}
        for variants in data["variants"].values():
            reachable |= set(variants)
        self.assertEqual(automatic - reachable, set())          # every automatic template has a mechanism that can place it
        excluded = {t for t, v in data["templates"].items() if v["mode"] == "excluded"}
        self.assertEqual(automatic & excluded, set())            # and no map-bound template is among them

    def _ev(self, tid, slots, eid="ngfx_x_1"):
        return {"id": eid, "type": "map_template", "template": G._public(G.get(tid)), "slots": slots, "t_in": 10.0, "t_out": 14.0, "over_footage": True}

    def test_variants_rotate_through_every_look_of_a_fact_with_the_same_content(self):
        from normal_gfx import rules

        rot = rules.Rotation()
        seen = []
        for _ in range(3):
            e = rules.adapt(self._ev("big_number", {"value": 8, "unit": "METRES", "label": "THE MAIN MIRROR", "sub": ""}), rot)
            seen.append(e["template"]["id"])
            self.assertEqual(e["slots"]["value"], 8)
            self.assertIn("METRES", str(e["slots"]))
        self.assertEqual(set(seen), {"big_number", "stat_countup", "counter_corner"})
        rot = rules.Rotation()
        self.assertEqual({rules.adapt(self._ev("ring_percent", {"title": "SHARE", "value": 60, "label": "OF THE PLANET"}), rot)["template"]["id"] for _ in range(2)},
                         {"ring_percent", "gold_stat"})
        rot = rules.Rotation()
        got = {rules.adapt(self._ev("name_bar", {"label": "MARIA LOPEZ", "sub": "GEOLOGIST"}), rot)["template"]["id"] for _ in range(2)}
        self.assertEqual(got, {"name_bar", "lower_kicker"})
        rot = rules.Rotation()
        text = {rules.adapt(self._ev("quote_boxed", {"text": "NOBODY HAD EVER SEEN IT"}, "ngfx_doc_quote_1"), rot)["template"]["id"] for _ in range(13)}
        self.assertEqual(text, {"quote_boxed"} | set(rules.TEXT_STYLES))

    def test_a_long_strong_line_and_a_percentage_over_100_keep_their_original_look(self):
        from normal_gfx import rules

        rot = rules.Rotation()
        long_line = self._ev("quote_boxed", {"text": "NOBODY HAD EVER SEEN THE GALAXY IN THIS MUCH DETAIL BEFORE TODAY"}, "ngfx_doc_quote_1")
        for _ in range(3):
            self.assertEqual(rules.adapt(long_line, rot)["template"]["id"], "quote_boxed")

    def test_a_question_and_a_part_title_are_placed_verbatim_only(self):
        fill = "The long road ran on past the quiet fields and the old farms while the light slowly faded over the hills and nobody said a word."
        text = f"{fill} {fill} Why does the water in this lake never freeze in winter? {fill} {fill} Part two begins at the old harbour town. {fill}"
        words = _words(text)
        total = words[-1][2] + 2
        plan = planner.plan_graphics(words, total, [{"scene_number": "1", "script_segment": text, "start_time": 0.0}], [(0.0, total)], [])
        got = {e["template"]["id"]: e["slots"] for e in plan.events}
        self.assertEqual(got["end_question"]["text"], "WHY DOES THE WATER IN THIS LAKE NEVER FREEZE IN WINTER?")
        self.assertEqual(got["chapter_words"]["text"], "PART TWO")


class Feedback(unittest.TestCase):
    SCRIPT = ("The observatory sits high in the desert, far from any town, road or light, and almost nothing grows there at all. Maria Lopez, a geologist at the "
              "observatory, has worked on the mountain for years.")

    def _prepare(self, fake_results):
        from normal_gfx import pipeline

        words = _words(self.SCRIPT)
        total = words[-1][2] + 1
        orig = pipeline._runner.render_overlays
        pipeline._runner.render_overlays = lambda jobs, *a, **k: {runner.job_key(j, 640, 360, 30): fake_results(j) for j in jobs}
        lines = []
        try:
            return pipeline.prepare(words, total, [{"scene_number": "1", "script_segment": self.SCRIPT, "start_time": 0.0}], [(0.0, total)], [],
                                    width=640, height=360, log=lines.append), lines
        finally:
            pipeline._runner.render_overlays = orig

    def test_no_browser_is_reported_as_a_fallback_with_a_way_to_retry(self):
        prep, lines = self._prepare(lambda j: runner.Result("k", error="graphics renderer unavailable: no browser"))
        self.assertEqual(prep.status, "unavailable")
        self.assertFalse(prep)
        text = "\n".join(lines)
        self.assertIn("WARNING", text)
        self.assertIn("Google Chrome", text)
        self.assertIn("render again", text.lower())
        self.assertIn("Doc Style", prep.final_line(False))
        self.assertNotIn("has 0 animated", prep.final_line(False))

    def test_every_skip_names_the_template_the_time_and_the_reason(self):
        prep, lines = self._prepare(lambda j: runner.Result("k", error="the template drew nothing"))
        self.assertEqual(prep.status, "all_skipped")
        row = prep.report[0]
        self.assertEqual(row["status"], "skipped")
        self.assertIn("drew nothing", row["reason"])
        self.assertTrue(any(f"skipped {row['template']} at {row['t_in']:.1f}s" in l for l in lines))

    def test_a_success_is_reported_as_one(self):
        from normal_gfx import pipeline

        prep = pipeline.Prepared(placed=[(1.0, runner.Result("k", Path("."), 3))], status="ok")
        self.assertIn("1 animated template graphic", prep.final_line(True))


@unittest.skipUnless(_browser_ok(), "needs Node and a browser (Chrome or Playwright's Chromium)")
class BrowserFailsToStart(unittest.TestCase):
    def test_a_browser_that_cannot_start_gives_an_unavailable_error_not_a_crash(self):
        import map_scene.render as MR

        orig = MR._browser_channel
        MR._browser_channel = lambda: "no-such-browser-channel"
        try:
            with tempfile.TemporaryDirectory() as d:
                j = runner.Job(G.get("name_bar"), {"label": "A"}, len=1.0)
                out = runner.render_overlays([j], 320, 180, 10, root=Path(d), log=lambda *_: None)
        finally:
            MR._browser_channel = orig
        (res,) = out.values()
        self.assertFalse(res.ok)
        self.assertIn("unavailable", res.error)


class Captions(unittest.TestCase):
    W, H = 640, 360

    def _env(self, boxes):
        import numpy as np

        e = np.zeros((self.H, self.W), dtype=np.uint8)
        for (x0, y0, x1, y1, a) in boxes:
            e[y0:y1, x0:x1] = a
        return e

    def _res(self, env):
        from PIL import Image

        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        Image.fromarray(env).save(Path(d) / "envelope.png")
        return runner.Result("k", Path(d), frames=1)

    def _cap(self, y0, y1):
        import numpy as np
        from normal_gfx.captions import SceneCaption

        m = np.zeros((self.H, self.W), dtype=bool)
        m[y0:y1, 100:540] = True
        return SceneCaption(0.0, 10.0, m)

    def test_no_collision_keeps_it_as_drawn(self):
        from normal_gfx import captions as C

        f = C.fit(self._res(self._env([(50, 50, 300, 150, 255)])), 1, 4, [self._cap(290, 340)], self.W, self.H)
        self.assertTrue(f.ok and f.dy == 0)

    def test_a_graphic_over_the_caption_is_moved_up_just_enough(self):
        from normal_gfx import captions as C

        f = C.fit(self._res(self._env([(50, 240, 300, 300, 255)])), 1, 4, [self._cap(290, 340)], self.W, self.H)
        self.assertTrue(f.ok)
        self.assertLess(f.dy, 0)
        self.assertGreaterEqual(f.dy, -0.2)

    def test_a_faint_backing_over_a_caption_is_allowed_a_dense_one_is_not(self):
        from normal_gfx import captions as C

        faint = C.fit(self._res(self._env([(50, 250, 600, 345, 60)])), 1, 4, [self._cap(290, 340)], self.W, self.H)
        self.assertTrue(faint.ok and faint.dy == 0)
        dense = C.fit(self._res(self._env([(50, 250, 600, 345, 140)])), 1, 4, [self._cap(290, 340)], self.W, self.H)
        self.assertFalse(dense.ok and not dense.changed)           # never shown as it is: moved or scaled away from the caption, or skipped

    def test_skipped_only_when_no_move_clears_it_and_the_reason_says_so(self):
        from normal_gfx import captions as C

        tall = self._env([(10, 10, 600, 345, 255)])          # fills the frame: nothing to move or shrink away from the caption
        f = C.fit(self._res(tall), 1, 4, [self._cap(290, 340)], self.W, self.H)
        self.assertFalse(f.ok)
        self.assertIn("caption", f.reason)
        self.assertIn("scaling", f.reason)

    def test_a_tall_side_panel_is_scaled_down_about_its_top_corner(self):
        from normal_gfx import captions as C

        panel = self._env([(450, 0, 640, 360, 255)])         # a full-height panel on the right
        f = C.fit(self._res(panel), 1, 6, [self._cap(290, 340)], self.W, self.H)
        self.assertTrue(f.ok)
        self.assertEqual(f.anchor, (1.0, 0.0))
        self.assertLess(f.scale, 1.0)
        self.assertGreaterEqual(f.scale, 0.7)

    def test_a_sub_second_transition_is_left_as_designed(self):
        from normal_gfx import captions as C

        f = C.fit(self._res(self._env([(0, 0, 640, 360, 254)])), 5.0, 5.4, [self._cap(290, 340)], self.W, self.H)
        self.assertTrue(f.ok and not f.changed)
        self.assertIn("transition", f.reason)

    def test_a_caption_of_another_scene_does_not_matter(self):
        from normal_gfx import captions as C

        c = self._cap(290, 340)
        c.start, c.end = 20.0, 30.0
        f = C.fit(self._res(self._env([(50, 290, 300, 340, 255)])), 1, 4, [c], self.W, self.H)
        self.assertTrue(f.ok and f.dy == 0)

    def test_real_caption_pixels_come_from_the_renders_own_caption_function(self):
        from normal_gfx import captions as C

        caps = C.scene_masks([{"scene_number": "1", "script_segment": "A short caption for the test."}], [(0.0, 5.0)], 640, 360)
        self.assertEqual(len(caps), 1)
        ys = caps[0].mask.any(axis=1).nonzero()[0]
        self.assertGreater(ys.min(), 0.7 * 360)           # at the bottom
        self.assertLess(ys.max(), 360)


class Layer(unittest.TestCase):
    def test_concat_list_has_a_transparent_gap_then_each_frame_for_one_frame_time(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            res = runner.Result("k", d / "k", frames=3)
            lst = d / "l.ffconcat"
            n = composite.build_layer_list([(1.0, res)], 2.0, 30, d / "blank.png", lst)
            self.assertEqual(n, 33)
            lines = lst.read_text().splitlines()
            self.assertEqual(lines[1], f"file '{(d / 'blank.png').as_posix()}'")
            self.assertEqual(lines[2], f"duration {30 / 30:.6f}")
            self.assertIn("00001.png", lines[3])
            self.assertEqual(lines[4], f"duration {1 / 30:.6f}")

    def test_an_overlapping_second_graphic_is_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            a, b = runner.Result("a", d / "a", frames=30), runner.Result("b", d / "b", frames=30)
            n = composite.build_layer_list([(0.0, a), (0.5, b)], 5.0, 30, d / "blank.png", d / "l")
            self.assertEqual(n, 30)


class Packaging(unittest.TestCase):
    def test_everything_the_renderer_loads_ships(self):
        from normal_gfx.packaging import engine_data_files
        from pakmap.packaging import engine_data_files as pakmap_files

        root = Path(__file__).resolve().parent
        mine = {Path(src).name for src, _dest in engine_data_files(root)}
        self.assertTrue({"render.mjs", "page.html", "page.js", "allowlist.json"} <= mine)
        shipped = {Path(src).relative_to(root).as_posix() for src, _d in pakmap_files(root)}
        # what the renderer serves from gfx-core and pakmap-engine already ships with pakMap
        for need in ("gfx-core/lib/render.mjs", "gfx-core/fonts/CormorantGaramond-VF.ttf", "gfx-core/templates/news/name_bar.json",
                     "pakmap-engine/assets/fonts/Montserrat-VF.ttf"):
            self.assertIn(need, shipped)
        spec = (root / "VideoGenerator.spec").read_text(encoding="utf-8")
        self.assertIn("normal_gfx_data_files(ROOT)", spec)
        self.assertIn('"normal_gfx.pipeline"', spec)


class KeyAndCache(unittest.TestCase):
    def test_key_changes_with_every_input_and_not_otherwise(self):
        t = G.get("name_bar")
        j = runner.Job(t, {"label": "A"}, len=3.0)
        k = runner.job_key(j, 1280, 720, 30)
        self.assertEqual(k, runner.job_key(runner.Job(t, {"label": "A"}, len=3.0), 1280, 720, 30))
        for other in (runner.job_key(runner.Job(t, {"label": "B"}, len=3.0), 1280, 720, 30), runner.job_key(runner.Job(t, {"label": "A"}, len=3.5), 1280, 720, 30),
                      runner.job_key(j, 1920, 1080, 30), runner.job_key(j, 1280, 720, 25),
                      runner.job_key(runner.Job(G.get("year_wipe"), {"label": "A"}, len=3.0), 1280, 720, 30)):
            self.assertNotEqual(k, other)

    def test_the_cache_drops_the_least_recently_used_sequences_beyond_its_limit(self):
        import os
        import time

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for i, name in enumerate(("old", "mid", "new")):
                (root / name).mkdir()
                (root / name / "00001.png").write_bytes(b"x" * 1000)
                os.utime(root / name, (time.time() - 100 + i, time.time() - 100 + i))
            self.assertEqual(runner.prune(root, keep=["old"], max_bytes=2100), 1)
            self.assertTrue((root / "old").exists() and not (root / "mid").exists() and (root / "new").exists())

    def test_a_cache_hit_starts_no_browser(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            j = runner.Job(G.get("name_bar"), {"label": "A"}, len=1.0)
            key = runner.job_key(j, 320, 180, 10)
            (root / key).mkdir()
            for i in range(1, 11):
                (root / key / f"{i:05d}.png").write_bytes(b"x")
            (root / key / "meta.json").write_text(json.dumps({"frames": 10, "box": [1, 2, 3, 4], "ink": [1, 2, 3, 4], "band_max": 0}))
            out = runner.render_overlays([j], 320, 180, 10, root=root, log=lambda *_: None)
            self.assertTrue(out[key].ok and out[key].cached)
            self.assertEqual(out[key].box, [1, 2, 3, 4])

    def test_a_missing_browser_skips_the_graphic_and_never_raises(self):
        import normal_gfx.runner as R

        with tempfile.TemporaryDirectory() as d:
            orig = R._browser_job
            R._browser_job = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no browser"))
            try:
                j = runner.Job(G.get("name_bar"), {"label": "A"}, len=1.0)
                out = runner.render_overlays([j], 320, 180, 10, root=Path(d), log=lambda *_: None)
            finally:
                R._browser_job = orig
            (res,) = out.values()
            self.assertFalse(res.ok)
            self.assertIn("no browser", res.error)


@unittest.skipUnless(_browser_ok(), "needs Node and a browser (Chrome or Playwright's Chromium)")
class RealRender(unittest.TestCase):
    def test_animated_transparent_frames_are_deterministic_and_one_bad_template_does_not_stop_the_rest(self):
        from PIL import Image

        good = runner.Job(G.get("year_wipe"), {"text": "1998"}, len=2.0)
        bad = runner.Job({"id": "broken", "items": [{"p": "nope"}]}, {}, len=1.0)
        a, b = tempfile.mkdtemp(), tempfile.mkdtemp()
        try:
            ra = runner.render_overlays([bad, good], 480, 270, 15, root=Path(a), log=lambda *_: None)
            rb = runner.render_overlays([good], 480, 270, 15, root=Path(b), log=lambda *_: None)
            kg = runner.job_key(good, 480, 270, 15)
            self.assertTrue(ra[kg].ok and not ra[runner.job_key(bad, 480, 270, 15)].ok)
            self.assertEqual(ra[kg].frames, 30)
            first, last = Image.open(ra[kg].frame(0)).convert("RGBA"), Image.open(ra[kg].frame(29)).convert("RGBA")
            self.assertEqual(first.getpixel((2, 2))[3], 0)                       # real transparency
            self.assertNotEqual(first.tobytes(), last.tobytes())                 # and it moves (the year counts up)
            for i in (0, 10, 29):                                                # the same job in another cache draws the very same bytes
                self.assertEqual(hashlib.sha1(ra[kg].frame(i).read_bytes()).hexdigest(), hashlib.sha1(rb[kg].frame(i).read_bytes()).hexdigest())
            again = runner.render_overlays([good], 480, 270, 15, root=Path(a), log=lambda *_: None)
            self.assertTrue(again[kg].cached)
        finally:
            shutil.rmtree(a, ignore_errors=True)
            shutil.rmtree(b, ignore_errors=True)


@unittest.skipUnless(_browser_ok(), "needs Node and a browser (Chrome or Playwright's Chromium)")
class EveryAutomaticTemplateDraws(unittest.TestCase):
    def test_each_new_look_draws_with_the_slots_the_rules_give_it(self):
        from normal_gfx import rules

        ev = lambda tid, slots: {"id": "ngfx_doc_quote_1", "type": "map_template", "template": G._public(G.get(tid)), "slots": slots, "t_in": 5.0, "t_out": 8.0}
        jobs, names = [], []
        base = [("big_number", {"value": 8, "unit": "METRES", "label": "THE MAIN MIRROR", "sub": ""}), ("ring_percent", {"title": "SHARE", "value": 60, "label": "OF THE PLANET"}),
                ("name_bar", {"label": "MARIA LOPEZ", "sub": "GEOLOGIST"}), ("quote_boxed", {"text": "NOBODY HAD EVER SEEN IT"})]
        for tid, slots in base:
            rot = rules.Rotation()
            for _ in range(13 if tid == "quote_boxed" else 3):
                e = rules.adapt(ev(tid, slots), rot)
                jobs.append(runner.Job(e["template"], e["slots"], len=2.0))
                names.append(e["template"]["id"])
        for tid, slots in (("end_question", {"text": "WHY DOES THE WATER NEVER FREEZE?", "kicker": ""}), ("chapter_words", {"text": "PART TWO"})):
            jobs.append(runner.Job(rules._public(tid), slots, len=2.0))
            names.append(tid)
        with tempfile.TemporaryDirectory() as d:
            out = runner.render_overlays(jobs, 320, 180, 10, root=Path(d), log=lambda *_: None)
            bad = {n: r.error for n, j in zip(names, jobs) for r in [out[runner.job_key(j, 320, 180, 10)]] if not r.ok}
            self.assertEqual(bad, {})
        self.assertEqual(set(names), {"big_number", "stat_countup", "counter_corner", "ring_percent", "gold_stat", "name_bar", "lower_kicker", "quote_boxed", "end_question",
                                      "chapter_words"} | set(rules.TEXT_STYLES))


if __name__ == "__main__":
    unittest.main()
