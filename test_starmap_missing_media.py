"""StarMap pictures that NASA's library has no match for: a story with no mission tries the stock search instead (a mission
story keeps NASA's answer, so no stock photo stands in for the mission's own picture); a picture still left out is reported
to the Visual Plan table (NEEDS ACTION with the reason, not QUEUED); and a footage beat that lost a clip gives its time to the
clips it still has, so the map is not left frozen. No network: NASA and the download step are fakes."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from starmap.app_integration import share_missing_clip_time
from starmap.beat_csv import read_plan
from starmap.media import fetch_media

HEAD = "beat,row,vo_anchor,mode,type,id,place,frame,date,label,sub,text,value_from,value_to,format,anchor,until,hold,asset,dur,why,extra"
CSV = HEAD + """
plan,plan,,,,,,,,EUROPA,,,,,,,,,,,,
b1,beat,Europa is one of,map_footage,,,europa,body,,,,Europa is one of the moons of Jupiter.,,,,,,,,,meet Europa,
b1,card,Europa is one of,,,,,,,EUROPA,,,,,,tr,,,nasa_image:Europa full disk photographed by Galileo,,,
"""
WORDS = [(w, i * 0.4, i * 0.4 + 0.35) for i, w in enumerate("Europa is one of the moons of Jupiter.".split())]


class NoNasa:
    """NASA's image search answering, with nothing that fits."""

    def __call__(self, url, params=None, **kw):
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None, json=lambda: {"collection": {"items": []}})


def run(mission):
    sent, reported = [], []

    def fetch_scenes(table, images_dir, **kw):
        sent.extend(str(r.scene_number) for r in table)
        return SimpleNamespace(paths={}, skipped=set(), missing={}, credits={})

    out = fetch_media(read_plan(CSV, WORDS), Path(tempfile.mkdtemp()), nasa_get=NoNasa(), fetch_scenes=fetch_scenes,
                      mission=mission, on_scene_complete=lambda row, res: reported.append((row.scene_number, res.status.name, res.error)),
                      log=lambda *_: None)
    return out, sent, reported


class NasaMiss(unittest.TestCase):
    def test_a_story_with_no_mission_tries_the_stock_search(self):
        out, sent, reported = run("")
        self.assertEqual(sent, ["1"], "the NASA miss goes on to the stock search")
        self.assertEqual(reported, [])

    def test_a_mission_story_keeps_nasas_answer_and_reports_it(self):
        out, sent, reported = run("Apollo 11")
        self.assertEqual(sent, [], "no stock photo stands in for a mission's own picture")
        self.assertEqual(out.media.get("row:4"), {"file": ""}, "left out, as before")
        self.assertEqual([(n, s) for n, s, _ in reported], [("1", "FAILED")], "the table shows it, not QUEUED")
        self.assertIn("Left out", reported[0][2])

    def test_per_scene_missions(self):
        _, sent, _ = run({"1": ""})
        self.assertEqual(sent, ["1"])
        _, sent, _ = run({"1": "Apollo 11"})
        self.assertEqual(sent, [])


class ClipTime(unittest.TestCase):
    def test_a_beat_that_lost_a_clip_gives_its_time_to_the_rest(self):
        fs = [{"id": "b4_1", "start": 16.24, "end": 22.29}, {"id": "b4_2", "start": 22.29, "end": 28.34, "image": "x.jpg"}]
        self.assertEqual(share_missing_clip_time(fs), [{"id": "b4_2", "start": 16.24, "end": 28.34, "image": "x.jpg"}])

    def test_two_left_share_evenly_in_order(self):
        fs = [{"id": "b2_1", "start": 0.0, "end": 3.0, "file": "a"}, {"id": "b2_2", "start": 3.0, "end": 6.0},
              {"id": "b2_3", "start": 6.0, "end": 9.0, "file": "c"}]
        self.assertEqual([(f["id"], f["start"], f["end"]) for f in share_missing_clip_time(fs)], [("b2_1", 0.0, 4.5), ("b2_3", 4.5, 9.0)])

    def test_complete_and_empty_beats_are_unchanged(self):
        full = [{"id": "b8_1", "start": 1.0, "end": 2.0, "file": "a"}, {"id": "b8_2", "start": 2.0, "end": 3.0, "file": "b"}]
        self.assertEqual(share_missing_clip_time([dict(f) for f in full]), full)
        self.assertEqual(share_missing_clip_time([{"id": "b9_1", "start": 5.0, "end": 9.0}]), [], "no clip at all: the map, as before")


if __name__ == "__main__":
    unittest.main()
