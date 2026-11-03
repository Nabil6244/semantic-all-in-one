"""Screen bugs seen in an Explainer render (2026-11-03), each as a general rule: a region made of parts draws one outline; a map card points at the place the map shows;
a phrase is never cut by a time window or before a word that finishes it; an icon has no bare-verb label; CSV names are capitalised in a lowercase transcript;
a narration graphic is not laid where a board shows the words; the same places are not mapped twice in a row."""
import json
import tempfile
import unittest
from pathlib import Path


def timed(text, step=0.3):
    return [(w, i * step, i * step + 0.25) for i, w in enumerate(text.split())]


class RegionOutline(unittest.TestCase):
    def test_parts_merge_into_one_outline(self):
        from map_scene.places import _dissolve
        sq = lambda x0, y0: [[[x0, y0], [x0 + 1, y0], [x0 + 1, y0 + 1], [x0, y0 + 1], [x0, y0]]]  # noqa: E731
        out = _dissolve([sq(0, 0), sq(1, 0), sq(0, 1), sq(1, 1), sq(0, 0)])       # four parts in a 2x2 block, one listed twice
        self.assertEqual(len(out), 1)
        ring = out[0][0]
        self.assertEqual(ring[0], ring[-1])
        self.assertFalse(any(p == [1, 1] for p in ring))                            # the centre, where only inner borders meet, is not on the outline

    def test_separate_parts_stay_separate(self):
        from map_scene.places import _dissolve
        sq = lambda x0: [[[x0, 0], [x0 + 1, 0], [x0 + 1, 1], [x0, 1], [x0, 0]]]  # noqa: E731
        self.assertEqual(len(_dissolve([sq(0), sq(5)])), 2)

    def test_england_is_one_coast(self):
        from pakmap import geo
        self.assertLess(len(geo.resolve("England").polys), 20)                    # was 155 council outlines, each filled and stroked


class CardPoint(unittest.TestCase):
    def test_york_card_points_at_york_england(self):
        from explainer.director.plan import _place_point
        lat, lon = (float(v) for v in _place_point("York").split(","))
        self.assertAlmostEqual(lat, 54.0, delta=1.0)
        self.assertAlmostEqual(lon, -1.1, delta=1.0)


class Phrases(unittest.TestCase):
    def test_window_edge_is_not_a_clause_end(self):
        from explainer.director.compose import best_phrases
        w = timed("how did viking warriors from scandinavia come so close to conquering all of england")
        got = best_phrases(list(range(2, 7)), w, {}, {}, set(), k=1, max_words=6, min_score=0.0, min_words=2, strict_edges=True)
        self.assertFalse(any(p.text.endswith("come") for p in got))

    def test_never_before_to_or_of(self):
        from explainer.director.compose import best_phrases
        w = timed("unlike earlier raiders these warriors intended to stay")
        got = best_phrases(list(range(len(w))), w, {}, {}, {len(w) - 1}, k=2, max_words=6, min_score=0.0, min_words=2, strict_edges=True)
        self.assertFalse(any(p.text.endswith("intended") for p in got))

    def test_bare_verb_label(self):
        from explainer.director.compose_ref import bare_verb
        self.assertTrue(bare_verb("ruled", {}))
        self.assertTrue(bare_verb("controlled", {}))
        self.assertFalse(bare_verb("crown", {}))


class Casing(unittest.TestCase):
    def test_csv_names_capitalise_the_transcript(self):
        from explainer.director.segment import vocab_casing
        got = vocab_casing(timed("viking raiders from scandinavia reached mercia near eddington in the north"),
                           ["Mercia", "place: Scandinavian fjord shore; region: North Sea; looks: Viking warriors", "Edington"])
        self.assertEqual(got.get("mercia"), "Mercia")
        self.assertEqual(got.get("scandinavia"), "Scandinavia")
        self.assertEqual(got.get("viking"), "Viking")
        self.assertEqual(got.get("eddington"), "Edington")                         # misheard by one letter: the CSV's spelling
        self.assertNotIn("north", got)


class NoDoubleWords(unittest.TestCase):
    def test_auto_graphic_over_a_board_is_left_out(self):
        from explainer.integration import clear_under_boards
        work = Path(tempfile.mkdtemp())
        (work / "explainer").mkdir()
        (work / "explainer" / "render_report.json").write_text(json.dumps({"report": {"beat_details": {"e3": {"board_overlay": {"mov": "x.mov", "start": 10.0, "end": 13.0}}}}}))
        spec = {"events": [{"id": "auto_quote_card_2", "type": "map_template", "t_in": 10.5, "t_out": 16.0},
                           {"id": "auto_tag_headline_1", "type": "map_template", "t_in": 30.0, "t_out": 33.0},
                           {"id": "e6_c1", "type": "media_full", "media": "/a/explainer/board_ab.mp4", "t_in": 40.0, "t_out": 44.0},
                           {"id": "auto_subtitle_gold_3", "type": "map_template", "t_in": 41.0, "t_out": 43.0},
                           {"id": "e10_cap1", "type": "map_template", "t_in": 11.0, "t_out": 12.0}]}
        self.assertEqual(clear_under_boards(spec, work), 2)
        self.assertEqual([e["id"] for e in spec["events"]], ["auto_tag_headline_1", "e6_c1", "e10_cap1"])


class NoRepeatMap(unittest.TestCase):
    def test_same_place_twice_in_a_row_is_one_map(self):
        from explainer.director import DirectorOptions, direct
        text = ("vikings sailed to england in the ninth century . england was divided into several competing kingdoms at that time . "
                "the kings argued and fought for many long years over the land .")
        w = timed(text, 0.35)
        opt = DirectorOptions(work_dir=tempfile.mkdtemp())
        opt.max_map_share = 1.0                                                    # the map budget is not what stops the second map
        r = direct(w, None, opt, duration=w[-1][2] + 0.3)
        maps = [b for b in (r.plan or {}).get("beats", []) if b.get("mode") in ("map", "map_footage")]
        places = [b.get("purpose") for b in maps]
        self.assertTrue(places)
        self.assertFalse(any(a == b_ for a, b_ in zip(places, places[1:])), places)


if __name__ == "__main__":
    unittest.main()
