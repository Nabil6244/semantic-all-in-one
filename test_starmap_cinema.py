"""StarMap Cinema (the StarMap tab's Cinema option): What If's documentary grammar on top of StarMap, and Classic untouched."""

import json
import unittest

from starmap import Catalog, compile_plan, read_plan
from starmap.cinema import flags, pause_cut
from test_starmap_actions import csv_of


def beat(bid, start, text, date, *rows, place="sun", frame="heliosphere"):
    return [dict(beat=bid, row="beat", start=str(start), mode="map", place=place, frame=frame, date=date, text=text),
            dict(beat=bid, row="layer", t=str(start + 0.3), type="craft", id="voyager1.voyager1"), *rows]


def spec_of(rows, length, cinema):
    plan = read_plan(csv_of([dict(beat="plan", row="plan", date="2026-10-15")] + rows), [], length)
    return compile_plan(plan, Catalog(), media=None, resolve_media=False, cinema=cinema).spec


HELIOPAUSE = beat("b1", 0, "Voyager 1 crossed the heliopause, the edge of the Sun's bubble, and entered interstellar space.", "2012-08-25T00:00:00Z")
SIGNAL = beat("b1", 0, "Today a radio signal takes almost a full day to reach Voyager 1 as it races away.", "2026-10-15T00:00:00Z")
HARDWARE = beat("b1", 0, "Voyager 1 is now twenty five billion kilometres from Earth, and its plutonium power is fading as its "
                         "instruments switch off one by one, the dish still pointed home.", "2026-10-15T00:00:00Z",
                dict(beat="b1", row="layer", t="6", type="stat", value_to="25", format="0 BILLION KM", sub="FROM EARTH", anchor="bl"))


class Cinema(unittest.TestCase):
    def test_off_means_classic_starmap(self):
        self.assertIsNone(flags(None))
        self.assertIsNone(flags({"enabled": False, "plates": True}))
        spec = spec_of(HARDWARE, 24.0, None)
        self.assertNotIn("cinema", spec)
        self.assertFalse([L for L in spec["layers"] if str(L["type"]).startswith(("tm_", "cinema_"))])
        self.assertEqual(json.dumps(spec, sort_keys=True), json.dumps(spec_of(HARDWARE, 24.0, None), sort_keys=True))

    def test_a_named_boundary_gets_a_cross_section_plate(self):
        spec = spec_of(HELIOPAUSE, 14.0, True)
        types = [L["type"] for L in spec["layers"]]
        self.assertIn("cinema_plate", types)
        sec = next(L for L in spec["layers"] if L["type"] == "tm_section")
        self.assertEqual(sec["unit"], "AU")
        self.assertTrue(any("HELIOPAUSE" in m["label"] for m in sec["marks"]))

    def test_a_travelling_signal_gets_a_light_time_axis(self):
        spec = spec_of(SIGNAL, 14.0, True)
        ax = next(L for L in spec["layers"] if L["type"] == "tm_logaxis")
        craft = ax["marks"][-1]
        self.assertIn("VOYAGER", craft["label"])
        self.assertTrue(20 * 3600 < craft["v"] < 26 * 3600, "about a light-day in 2026")

    def test_numbers_become_type_moments_and_every_shot_is_cited(self):
        spec = spec_of(HARDWARE, 24.0, True)
        types = [L["type"] for L in spec["layers"]]
        self.assertNotIn("big_number", types, "no dark full-screen scrim")
        self.assertIn("tm_metric", types)
        cite = next(L for L in spec["layers"] if L["type"] == "tm_cite")
        self.assertAlmostEqual(cite["segments"][-1]["t1"], spec["duration"], places=2)

    def test_the_craft_is_nasas_model_and_a_beat_about_its_hardware_cuts_to_it(self):
        spec = spec_of(HARDWARE, 24.0, True)
        craft = next(L for L in spec["layers"] if L["type"] == "spacecraft")
        self.assertEqual(craft["model"], "wi:voyager.glb")
        self.assertTrue(any("follow" in m["to"] for m in spec["camera"]["moves"]), "a hero close-up of the craft")

    def test_a_cut_lands_in_a_pause_when_one_is_near(self):
        words = [("one", 0.0, 0.4), ("two", 0.45, 0.9), ("three", 1.6, 2.0), ("four", 2.05, 2.4)]
        self.assertAlmostEqual(pause_cut(words, 1.0, 0.0, 3.0), 1.25)
        self.assertIsNone(pause_cut(words, 1.0, 1.5, 3.0), "outside the allowed span")


if __name__ == "__main__":
    unittest.main()


class CinemaAll(unittest.TestCase):
    """Every What If technique reachable from Cinema: CSV plates and instruments, titles, fades, lockups, comparisons, rhythm."""

    BARS = dict(beat="b1", row="layer", t="2", type="plate", id="bars", label="TEN LANDINGS",
                extra='{"rows": [{"label": "VENERA 13", "value": 127, "text": "127 MIN", "highlight": true}], "max": 140}')

    def test_a_csv_plate_is_drawn_on_a_slate_in_cinema_and_left_out_in_classic(self):
        rows = beat("b1", 0, "Ten probes landed and one lasted two hours.", "2026-10-15T00:00:00Z", self.BARS)
        on = spec_of(rows, 12.0, True)
        types = [L["type"] for L in on["layers"]]
        self.assertIn("tm_bars", types)
        self.assertLess(types.index("cinema_plate"), types.index("tm_bars"), "the slate draws underneath")
        self.assertEqual(next(L for L in on["layers"] if L["type"] == "tm_bars")["title"], "TEN LANDINGS")
        off = spec_of(rows, 12.0, None)
        self.assertNotIn("tm_bars", [L["type"] for L in off["layers"]])

    def test_a_hero_scene_is_cited_as_an_illustration_and_instruments_stay_over_it(self):
        rows = beat("b1", 0, "In 1982 Venera 13 touched down on the surface of Venus.", "1982-03-01T00:00:00Z",
                    dict(beat="b1", row="layer", t="1", type="plate", id="hero", extra='{"scene": "venera_ground"}'),
                    dict(beat="b1", row="layer", t="0.5", type="instrument", id="survival", until="end",
                         extra='{"chips": ["AIR"], "states": [{"t": 1, "verdict": "SECONDS", "lethal": ["AIR"]}]}'), place="venus", frame="body")
        spec = spec_of(rows, 12.0, True)
        cite = next(L for L in spec["layers"] if L["type"] == "tm_cite")
        self.assertTrue(any(s["kind"] == "ILLUSTRATION" and "VENERA GROUND" in s["text"] for s in cite["segments"]))
        surv = next(L for L in spec["layers"] if L["type"] == "tm_survival")
        self.assertGreater(surv["z"], 0, "drawn over the hero scene")

    def test_titles_fades_lockups_and_comparisons(self):
        rows = beat("b1", 0, "Jupiter is eleven times wider than Earth.", "1979-03-05T00:00:00Z",
                    dict(beat="b1", row="layer", t="0.5", type="title", label="THE JOURNEY OF VOYAGER ONE", sub="FROM EARTH"),
                    place="jupiter", frame="body") + \
            beat("b2", 70, "Then in 1982 the lander went silent after two hours on the surface.", "1982-03-01T00:00:00Z")
        spec = spec_of(rows, 90.0, True)
        types = [L["type"] for L in spec["layers"]]
        self.assertIn("tm_title", types)
        self.assertNotIn("title", types)
        self.assertIn("tm_fade", types)
        cmp_ = next(L for L in spec["layers"] if L["type"] == "tm_compare")
        self.assertEqual((cmp_["left"]["amount"], cmp_["right"]["label"]), (11.0, "EARTH"))

    def test_a_hero_close_up_has_the_name_and_date_centred_under_it(self):
        spec = spec_of(HARDWARE, 24.0, True)
        cap = [L for L in spec["layers"] if L["type"] == "tm_caption" and L.get("anchor") == "bc"]
        self.assertTrue(cap and "VOYAGER" in cap[0]["text"] and "2026" in cap[0]["sub"])

    def test_the_rhythm_is_a_shot_about_every_eight_seconds(self):
        long = beat("b1", 0, "Voyager 1 coasts on. " * 20, "2026-10-15T00:00:00Z", place="jupiter", frame="body")
        cuts = [m for m in spec_of(long, 48.0, True)["camera"]["moves"] if m["dur"] == 0]
        self.assertGreaterEqual(len(cuts), 4)


class CinemaBudgetAndNarration(unittest.TestCase):
    """The map at most half the screen time, and every shot moving the way its narration says."""

    def test_the_camera_moves_as_the_narration_says(self):
        from starmap.cinema import narrative_move

        w = lambda text: [(x, i * 0.4, i * 0.4 + 0.3) for i, x in enumerate(text.split())]   # noqa: E731
        self.assertEqual(narrative_move(w("it is now billions of kilometres away beyond the edge"), 0, 10), "out")
        self.assertEqual(narrative_move(w("look closer at the surface and its instruments"), 0, 10), "in")
        self.assertEqual(narrative_move(w("the moon goes around the planet in its orbit"), 0, 10), "orbit")
        self.assertIsNone(narrative_move(w("and so the story continues"), 0, 10))

    def test_spoken_numbers_are_read(self):
        from starmap.cinema import SPOKEN_NUMBER, spoken_number

        m = SPOKEN_NUMBER.search("about twenty-six billion kilometres away")
        self.assertEqual((spoken_number(m.group(1)), m.group(2)), ((26.0, "BILLION"), "kilometres"))

    def test_a_long_map_video_is_brought_to_half_map(self):
        from starmap.cinema import map_share

        rows = []
        for i in range(6):
            rows += beat(f"b{i + 1}", i * 20, "Voyager 1 is now twenty five billion kilometres from Earth and still going.",
                         "2026-10-15T00:00:00Z" if i == 0 else "")
        spec = spec_of(rows, 120.0, True)
        self.assertLessEqual(map_share(spec), 0.5 + 1e-6)
        self.assertTrue(any(L["type"] in ("cinema_craft", "tm_orbitmap", "tm_metric") for L in spec["layers"]))
        off = spec_of(rows, 120.0, {"enabled": True, "budget": False})
        self.assertGreater(map_share(off), 0.5, "without the budget the map keeps its share")


class CinemaPhotosAndMissingClips(unittest.TestCase):
    """Project #014: "footage cinema_photo_1 and b11_1 overlap (160.42 < 215.03)" stopped every render with Cinema on."""

    def test_cinema_photos_are_never_one_beat_spread_over_the_clips(self):
        from starmap.app_integration import share_missing_clip_time

        fo = [{"id": "cinema_photo_1", "start": 160.42, "end": 166.4, "image": "a.jpg"},
              {"id": "b11_1", "start": 166.4, "end": 200.0, "file": "x.mp4"},
              {"id": "cinema_photo_7", "start": 291.4, "end": 297.4, "image": "b.jpg"}]
        out = share_missing_clip_time(fo, [])
        self.assertEqual([(x["id"], x["start"], x["end"]) for x in out],
                         [("cinema_photo_1", 160.42, 166.4), ("b11_1", 166.4, 200.0), ("cinema_photo_7", 291.4, 297.4)])
        ends = sorted((x["start"], x["end"]) for x in out)
        self.assertTrue(all(b[0] >= a[1] - 1e-6 for a, b in zip(ends, ends[1:])), "no two footage entries overlap")

    def test_a_missing_clip_of_a_shown_beat_is_not_map_time(self):
        from starmap.cinema import _covered

        spec = {"duration": 60.0, "layers": [], "camera": {"moves": []},
                "footage": [{"id": "b3_1", "start": 10.0, "end": 20.0, "file": "x.mp4"}, {"id": "b3_2", "start": 20.0, "end": 30.0}]}
        self.assertEqual([tuple(x) for x in _covered(spec)], [(10.0, 30.0)], "the beat's clips will fill 10-30 s: no photo goes there")

