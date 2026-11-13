"""Sticker skin of the gfx_air graphics (aviation/gfx_sticker.py): kinds, animation, final figures, gfx_frame, SKIN, add_graphic."""

import tempfile
import time
import unittest

from PIL import Image, ImageChops

from aviation import gfx_air as A
from aviation import gfx_sticker as X
from aviation import stage as G
from test_aviation_map import fake_tile

FLEET = {"count": 277, "label": "AIRCRAFT", "type": "a380", "airline": "emirates"}
CASH = {"value": 3.1e9, "currency": "USD", "label": "PROFIT"}
CABIN = {"now": 72.0, "before": 79.5, "label": "SEATS FILLED"}
CHANGE = {"before": 3.1e9, "after": 1.0e9, "currency": "USD", "label": "PROFIT"}
BIG = {"value": 52.0, "unit": "%", "sign": "+", "label": "CARGO REVENUE", "icon": "freighter", "airline": "emirates", "type": "b777f"}

SAMPLES = {
    "lay_fleet": {"count": 277, "label": "AIRCRAFT"},
    "lay_network": {"hub": "DXB", "count": 150, "label": "DESTINATIONS"},
    "lay_seats": {"now": 72.0, "before": 79.5, "label": "SEATS FILLED"},
    "lay_change": {"before": 3.1e9, "after": 1.0e9, "currency": "USD", "label": "PROFIT"},
    "lay_big_number": {"value": 52.0, "unit": "%", "sign": "+", "label": "CARGO REVENUE", "icon": "freighter"},
    "lay_timeline": {"from_year": 1985, "to_year": 2026, "label": "EMIRATES"},
    "lay_crew": {"name": "", "role": "CAPTAIN", "age": 52, "hours": 11000, "on_type": None},
    "lay_gauge": {"value": 540, "max": 5000, "unit": "KG", "label": "FUEL"},
    "lay_runway": {"runway": "34", "length_m": 3330, "airport": "ATQ"},
    "lay_approach": {"from_ft": 2600, "to_ft": 200, "lines": [450, 200]},
    "lay_descent": {"speed_kt": 285, "fpm": -3284},
    "lay_title": {"title": "VISTARA 611", "sub": "4 JULY 2019"},
}


def diff(a, b):
    a, b = a.convert("RGBA"), b.convert("RGBA")
    w, h = max(a.width, b.width), max(a.height, b.height)
    ca, cb = Image.new("RGBA", (w, h)), Image.new("RGBA", (w, h))
    ca.alpha_composite(a)
    cb.alpha_composite(b)
    return sum(ImageChops.difference(ca, cb).convert("L").histogram()[12:])


class KindTests(unittest.TestCase):
    def kind(self, name, args):
        a = G._FACTORIES[name](dict(args, _k=0.2))
        b = G._FACTORIES[name](dict(args, _k=1.0))
        self.assertEqual(a.mode, "RGBA")
        self.assertEqual(b.mode, "RGBA")
        self.assertGreater(diff(a, b), 2000, name)
        return b

    def test_fleet(self):
        self.kind("sticker_fleet", FLEET)
        self.assertEqual(X.fleet_layout(12), (12, 1))
        icons, per = X.fleet_layout(277)
        self.assertLessEqual(icons, X.ICON_CAP)
        self.assertGreater(per, 1)
        self.assertGreaterEqual(icons * per, 277)
        self.assertEqual(X.shown_count(277, 1.0), 277)           # the badge ends on the real number
        self.assertLess(X.shown_count(277, 0.2), 277)
        self.assertGreater(X.shown_count(277, 0.5), X.shown_count(277, 0.2))
        self.kind("sticker_fleet", {"count": 6, "airline": "msa", "type": "b707"})     # small fleet: one sticker each

    def test_cash(self):
        self.kind("cash_pile", CASH)
        self.assertGreater(X.cash_stacks(3.1e9), X.cash_stacks(4e6))
        self.assertGreater(X.cash_stacks(4e6), X.cash_stacks(5e3))
        self.assertEqual(X.cash_stacks(0), 1)

    def test_cabin(self):
        self.kind("sticker_cabin", CABIN)
        self.assertEqual(X.cabin_filled(72.0, 1.0), A.seats_filled(72.0, X.CABIN_SEATS))
        self.assertLess(X.cabin_filled(72.0, 0.2), X.cabin_filled(72.0, 1.0))

    def test_change(self):
        self.kind("sticker_change", CHANGE)
        self.kind("sticker_change", {"before": 40.0, "after": 52.0, "label": "LOAD"})   # a rise: green tag, no currency

    def test_big_number(self):
        self.kind("sticker_big_number", BIG)
        self.assertEqual(X.big_number_text(52.0, "%", "+", 1.0), "+52%")
        self.assertEqual(X.big_number_text(3.1e9, "USD", "", 1.0), "$3.1B")
        self.assertNotEqual(X.big_number_text(52.0, "%", "+", 0.3), "+52%")

    def test_bad_params_do_not_crash_the_stage(self):
        st = G.Stage()
        st.add("sticker_change", 0.0, {"_flat": True}, pos=(640, 390), anim=1.0)     # no values -> placeholder card, not a crash
        self.assertIsNotNone(G.lay_stage(2.0, 4.0, st.params()))


class FrameTests(unittest.TestCase):
    def test_every_gfx_air_layer(self):
        names = sorted(n for n in dir(A) if n.startswith("lay_"))
        self.assertEqual(len(names), 12)
        with tempfile.TemporaryDirectory() as d:
            for n in names:
                p = dict(SAMPLES[n])
                if n == "lay_network":
                    p.update(fetch_tile=fake_tile, cache=d)
                a = G._FACTORIES["gfx_frame"]({"fn": n, "params": p, "dur": 4.0, "_k": 0.3})
                b = G._FACTORIES["gfx_frame"]({"fn": n, "params": p, "dur": 4.0, "_k": 1.0})
                self.assertEqual(b.mode, "RGBA", n)
                self.assertLess(b.width, 1280, n)                        # a card, not a full frame
                self.assertGreater(b.getchannel("A").getbbox()[2], 300, n)
                self.assertGreater(diff(a, b), 500, n)                   # it plays

    def test_nothing_to_show_raises_into_the_placeholder(self):
        with self.assertRaises(ValueError):
            G._FACTORIES["gfx_frame"]({"fn": "lay_runway", "params": {}, "dur": 3.0, "_k": 1.0})
        with self.assertRaises(KeyError):
            G._FACTORIES["gfx_frame"]({"fn": "os.system", "params": {}, "dur": 3.0})


class SkinTests(unittest.TestCase):
    def test_skin_covers_all_twelve(self):
        names = {"gfx_air." + n for n in dir(A) if n.startswith("lay_")}
        self.assertEqual(names, set(X.SKIN))
        self.assertEqual(X.SKIN["gfx_air.lay_fleet"], "sticker_fleet")
        self.assertEqual(X.SKIN["gfx_air.lay_seats"], "sticker_cabin")
        self.assertEqual(X.skin_kind("lay_runway"), "gfx_frame")
        self.assertEqual(X.skin_kind("gfx_air.unknown"), "gfx_frame")
        for kind in set(X.SKIN.values()):
            self.assertIn(kind, G._FACTORIES)

    def test_add_graphic_adds_an_element(self):
        st = G.Stage()
        e1 = X.add_graphic(st, 0.5, "gfx_air.lay_fleet", dict(FLEET), 4.0)
        e2 = X.add_graphic(st, 1.0, "gfx_air.lay_runway", SAMPLES["lay_runway"], 4.0)
        els = {e["id"]: e for e in st.params()["elements"]}
        self.assertEqual(els[e1]["kind"], "sticker_fleet")
        self.assertEqual(els[e2]["kind"], "gfx_frame")
        self.assertEqual(els[e2]["args"]["fn"], "lay_runway")
        self.assertGreater(els[e1]["anim"], 0)

    def test_full_stage_frame_renders(self):
        st = G.Stage()
        X.add_graphic(st, 0.2, "gfx_air.lay_fleet", dict(FLEET), 4.0)
        st.year(0.2, 2026)
        p = st.params()
        early, late = G.lay_stage(0.9, 6.0, p), G.lay_stage(4.5, 6.0, p)
        self.assertEqual(early.size, (1280, 720))
        self.assertGreater(diff(early, late), 5000)
        for name, params in SAMPLES.items():
            if name == "lay_network":
                continue
            s2 = G.Stage()
            X.add_graphic(s2, 0.0, "gfx_air." + name, params, 3.0)
            self.assertEqual(G.lay_stage(2.0, 4.0, s2.params()).size, (1280, 720), name)

    def test_speed_of_an_animating_fleet(self):
        st = G.Stage()
        X.add_graphic(st, 0.0, "gfx_air.lay_fleet", dict(FLEET), 4.0)
        p = st.params()
        G.lay_stage(1.0, 6.0, p)                                          # warm the cache of the first steps
        ts = [0.5 + i * 0.04 for i in range(60)]
        t0 = time.time()
        for t in ts:
            G.lay_stage(t, 6.0, p)
        ms = (time.time() - t0) / len(ts) * 1000
        print(f"\nsticker_fleet stage: {ms:.1f} ms/frame (60 frames over the build-up, cold sprites included)")
        self.assertLess(ms, 400)


if __name__ == "__main__":
    unittest.main()
