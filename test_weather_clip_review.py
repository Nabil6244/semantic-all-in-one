"""Phase 5 event-footage screen logic (weather/clip_review.py): labels, why/rights lines, and approved clips placed under their beats
with their credit chips, replacing event clips placed before and never touching other clips."""

import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from weather.clip_review import rights_text, set_labels, use_in_beats, why_text
from weather.news.approval import ApprovalError, ClipStore, credit_text
from weather.news.footage_pool import Clip, Event

HEADER = "beat,row,vo_anchor,mode,type,id,place,frame,label,sub,text,asset,dur,why\n"
BEATS = HEADER + ("b1,beat,This is a look,map,,,Florida,region,,,This is a look back,,,\n"
                  "b2,beat,NASA cameras on,footage,,,,,,,NASA cameras on the station,,,\n"
                  "b2,clip,,,,,,,,,,stock_video:rain on a window,,mood\n"
                  "b3,beat,For the latest,map,,,Florida,region,,,For the latest on any storm,,,\n")


class ClipReview(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.store = ClipStore(self.root)
        ev = Event("Hurricane Ian", "2022-09-23", "2022-09-30", ["Florida"])
        c = Clip(id="nasa:1", source="nasa", source_id="1", title="Hurricane Ian from the ISS", date="2022-09-28", credit="NASA",
                 status="approved", decided=True, dur_s=8.0)
        self.store._write(ev, [c])
        self.store.media_dir.mkdir(parents=True)
        self.file = self.store.media_dir / "nasa_1.mp4"
        self.file.write_bytes(b"x")
        self.store.set_local("nasa:1", self.file)
        self.beats, self.layers = self.root / "beats.csv", self.root / "weather_layers.csv"
        self.beats.write_text(BEATS)
        self.layers.write_text("beat,vo_anchor,t,id,type,place,data_source,hold,until,extra\n")

    def test_labels_are_kept_and_shown_on_the_credit(self):
        c = set_labels(self.store, "nasa:1", use="historical", beat="b2")
        self.assertEqual((c.use, c.beat), ("historical", "b2"))
        self.assertEqual(credit_text(self.store.get("nasa:1")), "NASA · SEP 28, 2022 · ARCHIVE")
        with self.assertRaises(ApprovalError):
            set_labels(self.store, "nasa:1", use="current")

    def test_why_and_rights_never_claim_a_licence(self):
        c = self.store.get("nasa:1")
        self.assertIn("Picked", why_text(c))
        self.assertIn("not a licence", rights_text(c))
        self.assertIn("Not usable: licence NC", why_text(Clip(id="x", source="commons", source_id="x", title="t", status="rejected",
                                                              reasons=["licence NC"])))

    def test_approved_clips_go_under_their_beat_with_a_credit_and_replace_earlier_event_clips(self):
        set_labels(self.store, "nasa:1", beat="b2")
        use_in_beats(self.store, self.beats, self.layers)
        use_in_beats(self.store, self.beats, self.layers)   # twice: still one event clip
        rows = list(csv.DictReader(io.StringIO(self.beats.read_text())))
        self.assertEqual([(r["beat"], r["row"]) for r in rows], [("b1", "beat"), ("b2", "beat"), ("b2", "clip"), ("b2", "clip"), ("b3", "beat")])
        self.assertEqual(rows[2]["asset"], "stock_video:rain on a window")   # other clips are kept
        self.assertEqual(rows[3]["asset"], str(self.file))
        credits = list(csv.DictReader(io.StringIO(self.layers.read_text())))
        self.assertEqual(len(credits), 1)
        self.assertEqual((credits[0]["type"], credits[0]["vo_anchor"], json.loads(credits[0]["extra"])["text"]),
                         ("footage_credit", "NASA cameras on", "NASA · SEP 28, 2022"))

    def test_a_map_beat_or_a_missing_file_is_refused_and_nothing_is_written(self):
        set_labels(self.store, "nasa:1", beat="b1")
        with self.assertRaisesRegex(ApprovalError, "map beat"):
            use_in_beats(self.store, self.beats, self.layers)
        set_labels(self.store, "nasa:1", beat="b2")
        self.file.unlink()
        with self.assertRaisesRegex(ApprovalError, "not downloaded"):
            use_in_beats(self.store, self.beats, self.layers)
        self.assertEqual(self.beats.read_text(), BEATS)

    def test_no_beat_chosen_is_named(self):
        with self.assertRaisesRegex(ApprovalError, "pick the beat"):
            use_in_beats(self.store, self.beats, self.layers)


if __name__ == "__main__":
    unittest.main()
