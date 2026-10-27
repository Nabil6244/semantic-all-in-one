"""War Documentary cards: deterministic, inside the safe area, honest about status and identification, safe on missing input."""
import hashlib
import os
import tempfile
import unittest

from PIL import Image, ImageStat

from cinematic_explainer import demo
from cinematic_explainer.war import cards as C, icons as I, tokens as T

SPECS = [{"label": "Crew", "value": "3"}, {"label": "Tubes", "value": "4"}, {"label": "Range", "value": "fixture"}, {"label": "Year", "value": "fixture"}]
EQ = {"name": "Sample Mk-9", "role": "Self-propelled launcher", "icon": "rocket_artillery", "operator": "Fixture", "specs": SPECS,
      "source": "Fixture data sheet", "confidence": "stated", "status": "attributed"}
STAT = {"title": "Output", "items": [{"label": "Before", "value": 40, "shown": "40", "colour": "yellow"},
                                    {"label": "Now", "value": 200, "shown": "200", "colour": "red"}], "unit": "units", "status": "attributed"}
PARAMS = {
    "equipment_card": EQ, "stat_compare": STAT,
    "stat_number": {"value": 5, "prefix": "×", "label": "More than before", "sub": "fixture", "status": "attributed"},
    "figure_card": {"name": "Dorrin Vale", "role": "Minister of Fixtures", "statement": "We will not move the depot before the winter ends.",
                    "statement_date": "12 Oct", "venue": "Briefing", "source": "Fixture transcript"},
    "institution_card": {"name": "General Staff of Fenland", "subtitle": "Daily summary", "source": "Fixture"},
    "timeline": {"title": "Timeline", "events": [{"date": "Feb 2022", "label": "One", "status": "confirmed"}, {"date": "Sep 2022", "label": "Two"},
                                                  {"date": "Mar 2023", "label": "Three", "status": "disputed"}], "times": [0.5, 1.2, 1.9]},
    "split_compare": {"left": {"label": "A", "icon": "tank"}, "right": {"label": "B", "icon": "air_defense"}, "chip": "Same scale"},
    "evidence_card": {"outlet": "Example Source", "date": "12 October", "words": demo.SOURCE_WORDS, "times": demo.SOURCE_TIMES,
                      "mark": demo.SOURCE_MARK, "kind": "claim", "status": "disputed"},
    "status_chip": {"status": "illustrative", "chips": [{"status": "disputed", "text": "Disputed figure"}]},
    "source_label": {"text": "Fixture agency"}, "shot_headline": {"text": "A sample headline", "date_line": "12 October · Fixture"},
    "flag": {"code": "UA", "label": "Ukraine"},
}
LOWER = ("status_chip", "source_label", "shot_headline", "flag")


def h(im):
    return hashlib.sha1(im.tobytes()).hexdigest()


def asum(im):
    return ImageStat.Stat(im.getchannel("A")).sum[0]


def count_colour(im, colour, box=None):
    region = im.crop(box) if box else im
    return region.tobytes().count(bytes(colour))


class CardTests(unittest.TestCase):
    def test_every_card_is_deterministic(self):
        for kind, p in PARAMS.items():
            self.assertEqual(h(C.WAR_CARDS[kind](2.0, 6.0, p)), h(C.WAR_CARDS[kind](2.0, 6.0, p)), kind)

    def test_registry_is_complete(self):
        self.assertEqual(set(C.WAR_CARDS), set(PARAMS))

    def test_inside_safe_area_and_frame(self):
        x0, y0, x1, y1 = T.SAFE
        for kind, p in PARAMS.items():
            im = C.WAR_CARDS[kind](3.0, 6.0, p)
            self.assertEqual(im.size, (T.W, T.H), kind)
            box = im.getchannel("A").getbbox()
            self.assertIsNotNone(box, kind)
            if kind == "timeline":
                # the card's soft scrim may feather past the margin (it is background, not content); the content is the bright text and markers
                import numpy as np
                a = np.array(im)
                ys, xs = np.where((a[..., 3] > 200) & (a[..., :3].max(axis=2) > 150))
                box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
            self.assertTrue(box[0] >= x0 - 1 and box[1] >= y0 - 2 and box[2] <= x1 + 1 and box[3] <= y1 + 1, (kind, box))

    def test_cards_stay_above_the_chip_stack(self):
        two_chips_top = C.STACK_Y - (C.CHIP_H + 6)
        for kind, p in PARAMS.items():
            if kind in LOWER:
                continue
            for t in (1.0, 3.0, 5.0):
                box = C.WAR_CARDS[kind](t, 6.0, p).getchannel("A").getbbox()
                self.assertLessEqual(box[3], two_chips_top, (kind, t, box))

    def test_chips_are_bottom_left_above_the_lower_zone(self):
        box = C.status_chip(1.0, 6.0, PARAMS["status_chip"]).getchannel("A").getbbox()
        self.assertGreaterEqual(box[0], T.MARGIN_X)
        self.assertLess(box[2], T.W // 2)
        self.assertLessEqual(box[3], T.LOWER_ZONE_Y)

    def test_fade_in_and_out(self):
        for kind in ("equipment_card", "stat_number", "timeline"):
            p = PARAMS[kind]
            mid = C.WAR_CARDS[kind](3.0, 6.0, p).getchannel("A").getextrema()[1]
            start = C.WAR_CARDS[kind](0.0, 6.0, p).getchannel("A").getextrema()[1]
            end = C.WAR_CARDS[kind](5.99, 6.0, p).getchannel("A").getextrema()[1]
            self.assertLess(start, mid, kind)
            self.assertLess(end, mid, kind)

    def test_spec_rows_appear_in_order(self):
        sums = [asum(C.equipment_card(t, 8.0, EQ)) for t in (0.4, 0.8, 1.1, 1.4, 1.7, 3.0)]
        self.assertEqual(sums, sorted(sums))
        self.assertGreaterEqual(len(set(round(s) for s in sums)), 5)

    def test_visual_only_hides_name_and_specs(self):
        a = C.equipment_card(3.0, 8.0, {**EQ, "confidence": "visual_only"})
        b = C.equipment_card(3.0, 8.0, {**EQ, "confidence": "visual_only", "name": "A Different Name", "specs": [], "role": "other"})
        self.assertEqual(h(a), h(b))
        full = C.equipment_card(3.0, 8.0, EQ)
        self.assertNotEqual(h(a), h(full))
        self.assertGreater(asum(full), asum(a))

    def test_illustrative_chip_only_for_silhouette_fallback(self):
        g = C._equipment_layout(EQ)
        chip_box = (g["ix0"], g["iy0"] + g["ih"] - 44, g["ix0"] + 320, g["iy0"] + g["ih"])
        fallback = C.equipment_card(3.0, 8.0, EQ)
        self.assertGreater(count_colour(fallback, T.STATUS_COLOUR["illustrative"], chip_box), 20)
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "photo.png")
            Image.new("RGB", (400, 300), (20, 40, 60)).save(path)
            with_photo = C.equipment_card(3.0, 8.0, {**EQ, "image": path})
        self.assertEqual(count_colour(with_photo, T.STATUS_COLOUR["illustrative"], chip_box), 0)

    def test_equipment_panel_is_sized_to_its_content(self):
        none = C.equipment_card(3.0, 8.0, {**EQ, "specs": []}).getchannel("A").getbbox()
        full = C.equipment_card(3.0, 8.0, EQ).getchannel("A").getbbox()
        self.assertLessEqual(full[3], C.CARD_BOTTOM)
        self.assertLessEqual(none[3], C.CARD_BOTTOM)
        self.assertLess(none[3] - none[1], 480)                       # no specs: a compact panel, not a tall empty one
        self.assertGreaterEqual(full[2] - full[0], 440)                # and a large one

    def test_callouts_draw_on_only_for_a_photo_with_an_identified_model(self):
        co = [{"label": "Radar", "x": 0.5, "y": 0.4}]
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "photo.png")
            Image.new("RGB", (400, 300), (20, 40, 60)).save(path)
            early = C.equipment_card(0.4, 8.0, {**EQ, "image": path, "callouts": co})
            late = C.equipment_card(3.0, 8.0, {**EQ, "image": path, "callouts": co})
            none = C.equipment_card(3.0, 8.0, {**EQ, "image": path})
            vis = C.equipment_card(3.0, 8.0, {**EQ, "image": path, "callouts": co, "confidence": "visual_only"})
            vis0 = C.equipment_card(3.0, 8.0, {**EQ, "image": path, "confidence": "visual_only"})
        self.assertGreater(count_colour(late, T.AMBER), count_colour(early, T.AMBER))
        self.assertGreater(count_colour(late, T.AMBER), count_colour(none, T.AMBER))
        self.assertEqual(h(vis), h(vis0))

    def test_claim_text_and_chip(self):
        self.assertEqual(C._claim_text({"claimant": "the ministry", "status": "disputed"}), "CLAIMED BY THE MINISTRY")
        self.assertEqual(C._claim_text({"claimant": "the ministry", "status": "attributed"}), "REPORTED BY THE MINISTRY")
        self.assertEqual(C._claim_text({"status": "attributed"}), "REPORTED FIGURES")
        self.assertEqual(C._claim_text({"status": "disputed"}), "CLAIMED FIGURES")
        self.assertIsNone(C._claim_text({"status": "confirmed"}))
        with_claim = C.stat_compare(3.0, 8.0, {**STAT, "claimant": "the ministry"})
        without = C.stat_compare(3.0, 8.0, STAT)
        self.assertNotEqual(h(with_claim), h(without))

    def test_bars_start_at_zero_and_scale_with_values(self):
        im = C.stat_compare(4.0, 8.0, {**STAT, "status": "confirmed"})

        def extent(colour):
            region = im.crop((0, 150, 1000, 560))
            cols = [x for x in range(region.width) if count_colour(region, colour, (x, 0, x + 1, region.height)) >= 20]
            return min(cols), max(cols)

        ya, yb = extent(T.AMBER)
        ra, rb = extent(T.RED)
        self.assertEqual(ya, ra)                                 # same zero axis
        self.assertAlmostEqual((yb - ya) / (rb - ra), 40 / 200, delta=0.02)

    def test_bars_grow_over_time(self):
        a, b, c = (count_colour(C.stat_compare(t, 8.0, STAT), T.RED) for t in (0.8, 1.0, 4.0))
        self.assertTrue(a < b < c, (a, b, c))

    def test_stat_number_counts_then_holds(self):
        sums = [asum(C.stat_number(t, 8.0, PARAMS["stat_number"])) for t in (0.1, 0.3, 0.5, 1.2)]
        self.assertTrue(sums[0] < sums[1] < sums[3])
        self.assertEqual(h(C.stat_number(2.0, 8.0, PARAMS["stat_number"])), h(C.stat_number(3.0, 8.0, PARAMS["stat_number"])))
        self.assertIsNone(C.stat_number(2.0, 8.0, {"label": "no value"}))

    def test_timeline_events_appear_by_their_times(self):
        p = PARAMS["timeline"]
        sums = [asum(C.timeline(t, 8.0, p)) for t in (0.3, 0.9, 1.6, 2.5)]
        self.assertTrue(all(a < b for a, b in zip(sums, sums[1:])), sums)
        self.assertEqual(h(C.timeline(4.0, 8.0, p)), h(C.timeline(5.0, 8.0, p)))     # settled once every event is in
        self.assertIsNone(C.timeline(2.0, 8.0, {"title": "x", "events": []}))

    def test_figure_words_darken_in_order(self):
        p = {**PARAMS["figure_card"], "times": [0.5 + 0.4 * i for i in range(9)]}
        cream = lambda t: count_colour(C.figure_card(t, 8.0, p), T.CREAM)
        self.assertTrue(cream(0.3) < cream(1.5) < cream(3.5))
        self.assertIsNone(C.figure_card(1.0, 8.0, {"role": "no name"}))

    def test_figure_without_portrait_is_a_plain_name_plate(self):
        im = C.figure_card(3.0, 8.0, {"name": "Dorrin Vale", "role": "Minister"})
        self.assertIsNotNone(im)
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "face.png")
            Image.new("RGB", (300, 300), (120, 90, 70)).save(path)
            with_img = C.figure_card(3.0, 8.0, {"name": "Dorrin Vale", "role": "Minister", "image": path})
        self.assertNotEqual(h(im), h(with_img))
        self.assertEqual(count_colour(im, (120, 90, 70, 255)), 0)

    def test_evidence_card_needs_words_and_adds_chip(self):
        self.assertIsNone(C.evidence_card(2.0, 8.0, {"outlet": "x"}))
        claim = C.evidence_card(3.0, 8.0, PARAMS["evidence_card"])
        plain = C.evidence_card(3.0, 8.0, {**PARAMS["evidence_card"], "kind": "statement", "status": "attributed"})
        self.assertGreater(count_colour(claim, T.STATUS_COLOUR["disputed"]), 20)
        self.assertEqual(count_colour(plain, T.STATUS_COLOUR["disputed"]), 0)
        self.assertGreater(count_colour(plain, T.STATUS_COLOUR["attributed"]), 20)

    def test_stat_item_enters_as_one_unit_never_a_label_without_its_bar(self):
        top, pitch = 172, 96
        first = (0, top, T.W, top + pitch - 4)
        second = (0, top + pitch, T.W, top + 2 * pitch)
        self.assertIsNone(C.stat_compare(0.2, 8.0, STAT).crop(first).getchannel("A").getbbox())          # nothing before it enters
        mid = C.stat_compare(0.5, 8.0, STAT)
        self.assertIsNotNone(mid.crop(first).getchannel("A").getbbox())                                 # item 1 is in ...
        self.assertIsNone(mid.crop(second).getchannel("A").getbbox())                                   # ... item 2 is not drawn at all yet
        # a bar track is drawn with the label from the first visible frame of an item
        track = (34, 42, 54)
        row = mid.crop(first)
        self.assertGreater(row.tobytes().count(bytes(track)) + row.tobytes().count(bytes(T.AMBER[:3])), 100)

    def test_stat_compare_type_sizes(self):
        im = C.stat_compare(4.0, 8.0, STAT)
        box = im.crop((0, 172, T.W, C.CARD_BOTTOM)).getchannel("A").getbbox()
        self.assertGreaterEqual(box[2], int(T.W * 0.45))                                                  # fills the left part of the frame
        self.assertLessEqual(box[2], int(T.W * 0.7))

    def test_missing_files_never_raise(self):
        bad = "/no/such/file.png"
        C.equipment_card(2.0, 6.0, {**EQ, "image": bad, "callouts": [{"label": "x", "x": 2, "y": -1}]})
        C.figure_card(2.0, 6.0, {**PARAMS["figure_card"], "image": bad})
        C.institution_card(2.0, 6.0, {"name": "Ministry", "emblem": bad})
        C.split_compare(2.0, 6.0, {"left": {"label": "A", "image": bad}, "right": {"label": "B", "image": bad}})
        with tempfile.TemporaryDirectory() as td:
            junk = os.path.join(td, "junk.png")
            open(junk, "wb").write(b"not an image")
            C.equipment_card(2.0, 6.0, {**EQ, "image": junk})

    def test_garbage_params_do_not_raise(self):
        for kind, fn in C.WAR_CARDS.items():
            for p in ({}, {"status": 5}, {"items": "x", "events": None, "specs": "no"}):
                try:
                    fn(1.0, 6.0, p)
                except Exception as exc:  # noqa: BLE001
                    self.fail(f"{kind} raised {exc!r} for {p!r}")

    def test_unknown_or_missing_status_draws_as_unverified(self):
        a = C.equipment_card(3.0, 8.0, {**EQ, "status": "bogus"})
        b = C.equipment_card(3.0, 8.0, {**EQ, "status": "unverified"})
        c = C.equipment_card(3.0, 8.0, {k: v for k, v in EQ.items() if k != "status"})
        self.assertEqual(h(a), h(b))
        self.assertEqual(h(b), h(c))
        self.assertEqual(T.status_of({"status": "CONFIRMED"}), "confirmed")

    def test_shot_headline_types_in(self):
        p = PARAMS["shot_headline"]
        self.assertLess(asum(C.shot_headline(0.15, 6.0, p)), asum(C.shot_headline(1.0, 6.0, p)))
        self.assertIsNone(C.shot_headline(1.0, 6.0, {"text": ""}))

    def test_split_compare_needs_two_sides(self):
        self.assertIsNone(C.split_compare(1.0, 6.0, {"left": {"label": "A"}}))


class IconTests(unittest.TestCase):
    def test_every_class_draws_and_is_deterministic(self):
        for cid in I.CLASS_LABEL:
            a = I.draw_icon(cid, 96, T.CREAM)
            self.assertEqual(a.size, (96, 96))
            self.assertIsNotNone(a.getchannel("A").getbbox(), cid)
            self.assertEqual(h(a), h(I.draw_icon(cid, 96, T.CREAM)), cid)
        self.assertEqual(h(I.draw_icon("not_a_class", 64, T.CREAM)), h(I.draw_icon("generic", 64, T.CREAM)))

    def test_flags(self):
        ua = I.draw_flag("ua", 90)
        self.assertEqual(ua.size, (90, 60))
        self.assertIsNone(I.draw_flag("TR"))
        self.assertIsNone(I.draw_flag("XX"))
        self.assertIsNone(I.draw_flag(""))
        card = C.flag(1.0, 6.0, {"code": "XX"})
        self.assertIsNotNone(card)                                 # unknown code: a neutral plate with the letters
        self.assertIsNone(C.flag(1.0, 6.0, {}))

    def test_overlay_helpers_draw_and_stay_inside(self):
        im = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
        I.draw_arrow(im, (20, 20), (200, 120), T.AMBER, 4, 16, progress=0.4)
        part = asum(im)
        I.draw_arrow(im, (20, 20), (200, 120), T.AMBER, 4, 16, progress=1.0)
        self.assertGreater(asum(im), part)
        I.draw_bracket(im, (10, 10, 120, 80), T.RED)
        I.draw_circle_marker(im, (250, 150), 20, T.CREAM)
        I.draw_pin(im, (150, 180), T.RED, 40)
        I.draw_pin(im, (2, 2), T.RED, 40)                           # partly outside: clipped, never raises
        self.assertEqual(im.size, (300, 200))


if __name__ == "__main__":
    unittest.main()
