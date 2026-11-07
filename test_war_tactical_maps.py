"""Tactical / political explainer maps: deterministic, inside the frame, never blank, never inventing a place."""
import tempfile
import unittest
from unittest import mock
import hashlib

from PIL import Image, ImageChops

from cinematic_explainer.war import maps_tactical as MT
from cinematic_explainer.war import registry

P = {"theme": "tactical", "places": ["Kharkiv", "Kyiv", {"name": "Kupiansk", "kind": "ring"}, "Atlantis"],
     "routes": [{"from": "Kharkiv", "to": "Kupiansk", "style": "dashed_blue", "label": "Supply line"}],
     "glyphs": [{"place": "Kupiansk", "kind": "explosion"}, {"place": "Nowhere", "kind": "drone"}],
     "focus": [["Kharkiv", "Kupiansk"], ["Kyiv"]], "chips": [{"title": "Note", "sub": "approximate", "variant": "red"}]}


def _md5(im):
    return hashlib.md5(im.tobytes()).hexdigest()


_UP = {"places": [{"name": "Odesa"}, {"name": "Mykolaiv", "kind": "ring"}], "regions": [{"name": "Ukraine", "role": "blue"}],
       "glyphs": [{"place": "Odesa", "kind": "sticker", "name": "drone", "start": 1.0}]}


class WarTacticalMapsTests(unittest.TestCase):
    def tmp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        return Path(d.name)

    def patch(self, obj, name, value):
        p = mock.patch.object(obj, name, value)
        p.start()
        self.addCleanup(p.stop)

    def test_registered_in_all_cards(self):
        cards = registry.all_cards()
        assert "tac_map" in cards and "tac_route" in cards

    def test_deterministic_and_full_frame(self):
        a = MT.tac_map(2.0, 8.0, dict(P))
        b = MT.tac_map(2.0, 8.0, dict(P))
        assert a.size == (1280, 720) and a.mode == "RGBA" and _md5(a) == _md5(b)
        assert a.getchannel("A").getextrema() == (255, 255)          # opaque full frame

    def test_never_blank_even_with_nothing_resolvable(self):
        for params in ({}, {"places": ["Atlantis"]}, {"theme": "political"}):
            im = MT.tac_map(0.5, 4.0, params).convert("L")
            lo, hi = im.getextrema()
            assert hi - lo > 20                                         # grid and outlines are always there

    def test_unknown_place_skipped_not_fabricated(self):
        p = dict(P)
        info = MT.render_info(p, 3.0, 8.0)
        assert any("Atlantis" in s for s in info["skipped"]) and any("Nowhere" in s for s in info["skipped"])
        names = [n for n, _r in info["labels"]]
        assert "ATLANTIS" not in names and "KHARKIV" in names
        assert MT.resolve_place("Atlantis")[0] is None
        assert MT.resolve_place("Ukraine")[0] is None                   # an area is not a point
        assert MT.resolve_place({"name": "Mine", "lat": 50.0, "lon": 36.0})[0]["lat"] == 50.0

    def test_labels_inside_frame_and_do_not_overlap(self):
        info = MT.render_info({"places": ["Kyiv", "Kharkiv", "Odesa", "Dnipro", "Zaporizhzhia", "Donetsk", "Kherson", "Poltava", "Sumy"], "frame": "ukraine"}, 6.0, 8.0)
        rects = [r for _n, r in info["labels"] if r]
        assert rects
        for r in rects:
            assert 0 <= r[0] and r[2] <= 1280 and 0 <= r[1] and r[3] <= 720
        for i, a in enumerate(rects):
            for b in rects[i + 1:]:
                assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]

    def test_camera_moves_between_focus_steps_and_markers_animate(self):
        v0 = MT.render_info(P, 0.2, 8.0)["view"]
        v1 = MT.render_info(P, 7.5, 8.0)["view"]
        assert v0 != v1
        early, late = MT.tac_map(0.6, 8.0, dict(P)), MT.tac_map(3.0, 8.0, dict(P))
        assert ImageChops.difference(early.convert("RGB"), late.convert("RGB")).getbbox() is not None

    def test_route_label_always_illustrative_and_route_card(self):
        im = MT.tac_route(3.0, 6.0, {"from": "Odesa", "to": "Moscow"})
        assert im.size == (1280, 720)
        sk = MT.tac_route(3.0, 6.0, {"from": "Odesa", "to": "Atlantis"})
        assert sk.size == (1280, 720)                                    # an unresolvable end draws no route, still a map

    def test_political_theme_fills_ukraine_blue_russia_red(self):
        im = MT.tac_map(3.0, 6.0, {"theme": "political", "frame": "ukraine_russia"}).convert("RGB")
        cols = {im.getpixel((x, y)) for x in (200, 900) for y in (300,)}
        assert len(cols) == 2

    def test_looks_differ_and_are_deterministic(self):
        a = MT.tac_map(4.0, 7.0, dict(_UP, look="night"))
        b = MT.tac_map(4.0, 7.0, dict(_UP, look="table"))
        assert a.size == (1280, 720)
        assert a.tobytes() != b.tobytes()
        assert a.tobytes() == MT.tac_map(4.0, 7.0, dict(_UP, look="night")).tobytes()

    def test_camera_opens_wide_then_settles(self):
        assert MT.render_info(dict(_UP), 0.0, 7.0)["view"][2] > MT.render_info(dict(_UP), 3.0, 7.0)["view"][2]

    def test_unknown_region_is_skipped_not_guessed(self):
        p = dict(_UP, regions=[{"name": "Atlantis"}])
        MT.tac_map(3.0, 7.0, p)
        assert any("Atlantis" in x for x in p["_skipped"])


if __name__ == "__main__":
    unittest.main()



class MapsFollowTheNarration(unittest.TestCase):
    """The owner (2026-11-07): map upgrades: highlights, colouring, zoom in, movements, country flags, follow the narration."""

    def narrate(self, text):
        from cinematic_explainer.war import direction as D, semantics as S

        from cinematic_explainer.war.planner import _default_catalog

        A = S.analyze_scene(text, _default_catalog(), None, 0.0, 7.0)
        sent = A.sentences[0]
        pl, co = D._places(sent), D._countries(sent)
        p = D._tac_params(sent, pl, co, False) if pl else D._tac_params(sent, [], co, True)
        return D._narrate_map(p, text, A, 0.0, D._countries_in(A)), A

    def test_pins_and_movement_appear_when_their_words_are_spoken(self):
        p, A = self.narrate("Russian columns advanced from Belgorod toward Kharkiv in February 2022.")
        starts = {x["name"]: x["start"] for x in p["places"]}
        self.assertLess(starts["Belgorod"], starts["Kharkiv"])
        r = p["routes"][0]
        self.assertEqual((r["style"], r["colour"]), ("advance", "red"))
        self.assertAlmostEqual(r["start"], round(A.time_at(p and "Russian columns advanced".find("advanced")), 2), places=1)
        self.assertEqual(p["focus"][0], ["Belgorod"])                              # opens on the origin, widens as it moves

    def test_strike_from_and_retreat_get_their_own_styles(self):
        p, _A = self.narrate("Russia struck Odesa from Sevastopol with cruise missiles.")
        self.assertEqual((p["routes"][0]["from"], p["routes"][0]["to"], p["routes"][0]["style"]), ("Sevastopol", "Odesa", "strike"))
        q, _A = self.narrate("Ukrainian troops withdrew from Avdiivka to Pokrovsk.")
        self.assertEqual((q["routes"][0]["style"], q["routes"][0]["colour"]), ("retreat", "blue"))

    def test_countries_colour_in_and_regions_light_up_when_named_and_one_town_gets_a_close_up(self):
        p, A = self.narrate("Fighting raged in the Donetsk region as Poland and Lithuania watched.")
        self.assertEqual([(f["iso3"], f["role"]) for f in p["fills"]], [("POL", "gold"), ("LTU", "teal")])
        self.assertLess(p["fills"][0]["start"], p["fills"][1]["start"])
        reg = p["regions"][0]
        self.assertEqual(reg["label"], "Donetsk")
        self.assertGreater(reg["start"], 1.0)                                      # on the word, not at the card's start
        self.assertEqual(p["close_steps"], [False, True])

    def test_every_movement_style_draws_and_moves(self):
        from cinematic_explainer.war.maps_tactical import tac_map

        for style in ("advance", "strike", "retreat"):
            p = {"places": ["Belgorod", "Kharkiv"], "routes": [{"from": "Belgorod", "to": "Kharkiv", "style": style, "start": 0.5, "length": 1.4}]}
            a, b = tac_map(1.0, 6.0, dict(p)), tac_map(3.5, 6.0, dict(p))
            self.assertIsNotNone(a)
            self.assertNotEqual(a.tobytes(), b.tobytes())

    def test_crimea_is_never_coloured_or_flagged_as_russia(self):
        from cinematic_explainer.war import maps_tactical as TM
        from cinematic_explainer.war import maps as MP

        p = {"places": ["Simferopol"], "fills": [{"iso3": "RUS", "role": "red", "start": 0.4}], "focus": [["Simferopol"]]}
        im = TM.tac_map(4.0, 6.0, dict(p)).convert("RGB")
        view = TM._render(dict(p), 4.0, 6.0)[1]["view"]
        r, g, b = im.getpixel((640, 420))                                         # Crimea, south of Simferopol's pin
        self.assertFalse(r > 120 and r > g + 60 and r > b + 60, "Crimea drawn in Russia's red")
        rus = TM.G.find_country("RUS")
        crimea_only = MP.View(TM.math.radians(34.1), TM.G.merc(45.0), TM.math.radians(1.2), 1280, 720)
        self.assertIsNone(TM._flag_anchor(rus, crimea_only))

    def test_flags_are_exact_stripe_flags_only(self):
        from cinematic_explainer.war.maps_tactical import _flag_tile

        self.assertIsNotNone(_flag_tile("UKR"))
        self.assertIsNone(_flag_tile("USA"))                                       # not a stripe flag: never drawn approximately

    def test_a_countries_only_map_frames_and_colours_the_countries_named(self):
        p, _A = self.narrate("Poland and Lithuania closed their borders with Belarus and Russia.")
        self.assertEqual([f["iso3"] for f in p["fills"]], ["POL", "LTU", "BLR", "RUS"])
        self.assertEqual([f["role"] for f in p["fills"]], ["gold", "teal", "brown", "red"])
        self.assertEqual(sorted(f["start"] for f in p["fills"]), [f["start"] for f in p["fills"]])   # in spoken order
        self.assertNotIn("frame", p)                                               # not the fixed Ukraine frame
        self.assertEqual(len(p["focus"][0]), 4)
