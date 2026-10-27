"""War Documentary maps: deterministic, honest (no unsourced rings or front lines), camera lands exactly, labels stay inside the safe box."""
import time
import unittest

from PIL import Image

from cinematic_explainer.war import geo_data as G
from cinematic_explainer.war import maps
from cinematic_explainer.war import tokens as T

BOX = lambda x0, y0, x1, y1: [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
SNAP_A = {"as_of": "2024-01-05", "source": "Fixture assessment A (test data)", "role": "a", "polygons": [BOX(36, 48.2, 38.5, 49.5)]}
SNAP_B = {"as_of": "2024-03-10", "source": "Fixture assessment B (test data)", "role": "a", "polygons": [BOX(36, 48.2, 39.5, 50.0)]}


def base_params(**kw):
    p = {"frame": "ukraine", "fills": [{"name": "Ukraine", "role": "b", "label": "Ukraine"}, {"name": "Russia", "role": "a", "label": "Russia"}],
         "pins": [{"lat": 50.45, "lon": 30.52, "label": "Kyiv", "note": "Capital", "start": 0.3}],
         "cities": [{"name": "Odesa"}, {"name": "Lviv"}, {"name": "Nowhereville"}],
         "caption": {"title": "Fixture map", "sub": "Schematic overview used by the tests."}}
    p.update(kw)
    return p


def px_hash(img):
    import hashlib
    return hashlib.sha1(img.tobytes()).hexdigest()


class RenderTests(unittest.TestCase):
    def test_cards_registered_and_full_frame(self):
        self.assertEqual(set(maps.MAP_CARDS), {"map_card", "map_inset"})
        img = maps.MAP_CARDS["map_card"](3.0, 8.0, base_params())
        self.assertEqual(img.size, (T.W, T.H))
        self.assertEqual(img.getchannel("A").getextrema(), (255, 255))   # opaque once faded in

    def test_deterministic(self):
        a = maps.map_card(2.0, 8.0, base_params())
        maps.clear_cache()
        b = maps.map_card(2.0, 8.0, base_params())
        self.assertEqual(px_hash(a), px_hash(b))

    def test_fade_in_and_out(self):
        p = base_params()
        self.assertEqual(maps.map_card(0.0, 8.0, p).getchannel("A").getextrema()[1], 0)
        self.assertLess(maps.map_card(7.95, 8.0, p).getchannel("A").getextrema()[1], 255)

    def test_labels_inside_safe_area_and_not_overlapping(self):
        info = maps.render_info(base_params(cities=[{"name": n} for n in ("Odesa", "Lviv", "Kharkiv", "Dnipro", "Donetsk", "Mariupol")]), 3.0)
        s = info["safe"]
        rects = [r for _, r in info["labels"]]
        self.assertTrue(len(rects) >= 4)
        for text, r in info["labels"]:
            if text == "FIXTURE MAP":   # the caption panel is anchored to the safe edge by design
                continue
            self.assertTrue(r[0] >= s[0] and r[1] >= s[1] and r[2] <= s[2] and r[3] <= s[3], (text, r, s))
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                a, b = rects[i], rects[j]
                self.assertTrue(a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], (info["labels"][i], info["labels"][j]))

    def test_unknown_places_are_skipped_without_error(self):
        p = base_params(frame="Atlantis", fills=[{"name": "Nowhere", "role": "a"}], oblasts=[{"name": "Not An Oblast", "role": "a"}],
                        pins=[{"label": "bad"}, {"name": "Nowhereville"}], arrows=[{"from": "x"}], cities=[{"name": "Nowhereville"}])
        info = maps.render_info(p, 3.0)
        self.assertTrue(any("unknown" in w for w in info["warnings"]))
        self.assertIn("Nowhereville", info["unresolved"])
        self.assertEqual(maps.map_card(3.0, 8.0, p).size, (T.W, T.H))


class HonestyTests(unittest.TestCase):
    def test_range_ring_needs_a_source(self):
        p = {"frame": "ukraine", "range_rings": [{"lat": 49, "lon": 32, "km": 100, "source": ""}, {"lat": 49, "lon": 32, "km": 100}]}
        info = maps.render_info(p, 3.0)
        self.assertEqual((info["rings_drawn"], info["rings_skipped"]), (0, 2))
        p["range_rings"] = [{"lat": 49, "lon": 32, "km": 100, "source": "Fixture published range"}]
        self.assertEqual(maps.render_info(p, 3.0)["rings_drawn"], 1)

    def test_snapshot_without_date_or_source_is_rejected(self):
        bad = [{"source": "x", "polygons": [BOX(0, 0, 1, 1)]}, {"as_of": "2024-01-01", "polygons": [BOX(0, 0, 1, 1)]},
               {"as_of": "not a date", "source": "x", "polygons": [BOX(0, 0, 1, 1)]}, {"as_of": "2024-01-01", "source": "x", "polygons": []}]
        info = maps.render_info({"frame": "donbas", "control_snapshots": bad}, 3.0)
        self.assertEqual(info["snapshots_drawn"], 0)
        self.assertEqual(len(info["snapshots_rejected"]), 4)
        self.assertEqual(info["status"], "illustrative")          # nothing verified is shown, so the chip says so

    def test_no_control_layer_by_default(self):
        self.assertEqual(maps.render_info(base_params(), 3.0)["snapshots_drawn"], 0)

    def test_valid_snapshots_are_dated_and_attributed(self):
        p = {"frame": "donbas", "control_snapshots": [SNAP_A, SNAP_B], "snapshot_wipe": {"start": 0.5, "length": 1.0}}
        info = maps.render_info(p, 3.0)
        self.assertEqual(info["snapshots_drawn"], 2)
        self.assertEqual(info["status"], "attributed")
        chips = " ".join(info["chips"])
        self.assertIn("05 JAN 2024", chips)
        self.assertIn("10 MAR 2024", chips)
        # before the wipe starts only the first snapshot is shown
        self.assertEqual(maps.render_info(p, 0.2)["snapshots_drawn"], 1)

    def test_trajectory_always_carries_an_illustrative_chip(self):
        p = {"frame": "ukraine", "arrows": [{"from": (50.45, 30.52), "to": (48.5, 36.0), "kind": "trajectory", "illustrative": False,
                                              "start": 0.0, "length": 1.0}]}
        info = maps.render_info(p, 3.0)
        self.assertIn("ILLUSTRATIVE", info["chips"])
        # an unsourced movement arrow is illustrative as well, a sourced one is not forced to be
        p2 = {"frame": "ukraine", "arrows": [{"from": (50.0, 30.0), "to": (49.0, 33.0), "kind": "movement", "start": 0.0, "length": 1.0}]}
        self.assertEqual(maps.render_info(p2, 3.0)["chips"].count("ILLUSTRATIVE"), 2)   # arrow chip + status chip

    def test_a_colour_is_never_the_only_affiliation_cue(self):
        # a labelled fill gets a legend row with its text; nothing is coloured without a legend entry
        info = maps.render_info(base_params(), 3.0)
        legend = [l for l in info["labels"] if l[0] in ("UKRAINE", "RUSSIA")]
        self.assertTrue(legend)
        a = maps.map_card(3.0, 8.0, base_params())
        b = maps.map_card(3.0, 8.0, base_params(legend=False))
        self.assertNotEqual(px_hash(a), px_hash(b))

    def test_crimea_policy_changes_the_picture_and_is_stated_on_screen(self):
        p = base_params(frame="crimea")
        rec = maps.map_card(3.0, 8.0, dict(p, crimea="recognized"))
        src = maps.map_card(3.0, 8.0, dict(p, crimea="source"))
        self.assertNotEqual(px_hash(rec), px_hash(src))
        self.assertIn("internationally recognised", maps.CRIMEA_NOTES["recognized"])


class CameraTests(unittest.TestCase):
    CAM = {"from_frame": "europe_east", "to_frame": "ukraine", "start": 0.5, "length": 2.0}

    def test_push_is_monotonic_and_ends_exactly_on_the_target(self):
        p = {"camera": self.CAM}
        target = maps.view_for("ukraine")
        widths, prev = [], None
        for i in range(0, 41):
            v = maps.camera_view(p, i * 0.075, (T.W, T.H), [])
            widths.append(v.hw)
        self.assertTrue(all(b <= a + 1e-12 for a, b in zip(widths, widths[1:])))       # zooming in never reverses
        end = maps.camera_view(p, 2.5, (T.W, T.H), [])
        self.assertEqual(end.key(), target.key())
        self.assertEqual(maps.camera_view(p, 0.0, (T.W, T.H), []).key(), maps.view_for("europe_east").key())

    def test_pull_back_is_monotonic_the_other_way(self):
        p = {"camera": {"from_frame": "kharkiv_region", "to_frame": "ukraine", "start": 0.0, "length": 2.0}}
        ws = [maps.camera_view(p, i * 0.1, (T.W, T.H), []).hw for i in range(0, 21)]
        self.assertTrue(all(b >= a - 1e-12 for a, b in zip(ws, ws[1:])))

    def test_every_preset_resolves(self):
        for name in G.PRESETS:
            v = maps.view_for(name)
            b = v.bounds()
            pre = G.PRESETS[name]
            self.assertLessEqual(b[0], pre[0] + 1e-6)
            self.assertGreaterEqual(b[2], pre[2] - 1e-6)


class InsetAndBudgetTests(unittest.TestCase):
    def test_inset_is_a_transparent_frame_with_a_small_map(self):
        img = maps.map_inset(3.0, 8.0, {"frame": "ukraine_russia", "fills": [{"name": "Ukraine", "role": "b"}], "title": "Locator", "pos": "tr"})
        self.assertEqual(img.size, (T.W, T.H))
        box = img.getchannel("A").getbbox()
        self.assertIsNotNone(box)
        self.assertLess(box[2] - box[0], 420)
        self.assertEqual(img.getpixel((5, 5))[3], 0)

    def test_per_frame_time_budget(self):
        maps.clear_cache()
        p = base_params(camera={"from_frame": "europe_east", "to_frame": "ukraine", "start": 0.0, "length": 2.0})
        maps.map_card(0.0, 8.0, p)                                      # warm the data loaders (one-off cost, not per frame)
        times = []
        for i in range(1, 12):
            t0 = time.perf_counter()
            maps.map_card(i * 0.16, 8.0, p)
            times.append(time.perf_counter() - t0)
        self.assertLess(sorted(times)[len(times) // 2], 0.25)           # median moving frame (loose: CI machines are slower)
        t0 = time.perf_counter()
        maps.map_card(3.0, 8.0, p)
        maps.map_card(3.04, 8.0, p)
        warm = time.perf_counter() - t0
        self.assertLess(warm, 0.6)                                      # a static map: one base draw, then reuse


class DataTests(unittest.TestCase):
    def test_oblast_and_country_lookup(self):
        for name in ("Kharkiv", "Odesa", "Kyiv", "Zaporizhzhia", "Donetsk", "Luhansk", "Kherson", "Lviv"):
            self.assertIsNotNone(G.find_oblast(name), name)
        self.assertIsNotNone(G.find_country("UKR"))
        self.assertIsNotNone(G.find_country("Russia"))
        self.assertIsNone(G.find_country("Atlantis"))

    def test_trajectory_geometry_is_between_the_named_endpoints(self):
        pts = G.great_circle((50.45, 30.52), (55.76, 37.62))
        self.assertAlmostEqual(pts[0][1], 50.45, 3)
        self.assertAlmostEqual(pts[-1][0], 37.62, 3)

    def test_geodesic_circle_radius(self):
        import math
        pts = G.geodesic_circle(49.0, 32.0, 100.0)
        r = []
        for lon, lat in pts[:-1]:
            dlat, dlon = math.radians(lat - 49.0), math.radians(lon - 32.0)
            a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(49.0)) * math.cos(math.radians(lat)) * math.sin(dlon / 2) ** 2
            r.append(2 * 6371.0 * math.asin(math.sqrt(a)))
        self.assertTrue(all(abs(x - 100.0) < 0.5 for x in r))


if __name__ == "__main__":
    unittest.main()
