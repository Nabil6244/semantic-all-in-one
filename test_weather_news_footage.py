"""Event footage for Weather News: search answers (NASA recorded; Commons and YouTube hand-made in the real answers' shape),
relevance and licence rules, approval storage in <project>/weather/clips.json, and the hand-off to Hybrid clip rows and
footage_credit rows. No network, no YouTube, no download (ffmpeg is faked)."""

import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from weather.news import approval, footage_pool as fp, sources
from weather.sidecar import parse_sidecar

DATA = Path(__file__).resolve().parent / "weather" / "testdata" / "news"
IAN = fp.Event(name="Hurricane Ian", start="2022-09-23", end="2022-10-01", places=["Fort Myers", "Florida", "Cayo Costa"], keywords=["Ian"])
YT = json.loads((DATA / "youtube_info_SYNTHETIC.json").read_text())
ISS = "nasa:jsc2022m000251_Expedition_67_Space_Station_Flyover_of_Hurricane_Ian_220928"


def get_text(url):
    if "images-api.nasa.gov" in url:
        return (DATA / "nasa_ian.json").read_text()
    if "commons.wikimedia.org" in url:
        return (DATA / "commons_search_SYNTHETIC.json").read_text()
    raise AssertionError(f"unexpected fetch {url}")


def yt_extract(vid):
    return next(v for v in YT.values() if v["id"] == vid)


def pool():
    clips, problems = fp.search(IAN, get_text, youtube_ids=["AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC"], yt_extract=yt_extract)
    assert problems == [], problems
    return {c.id: c for c in clips}


class Sources(unittest.TestCase):
    def test_nasa(self):
        clips = sources.nasa_clips((DATA / "nasa_ian.json").read_text())
        self.assertEqual(len(clips), 5)
        c = [c for c in clips if c["id"] == ISS][0]
        self.assertEqual((c["date"], c["author"], c["licence"]), ("2022-09-28", "NASA/JSC", "public domain (NASA)"))
        self.assertIn("collection.json", c["assets_url"])

    def test_pick_rendition(self):
        assets = json.loads('["http://x/a~orig.mp4", "http://x/a~small.mp4", "http://x/a~medium.mp4", "http://x/a.srt"]')
        self.assertEqual(sources.nasa_pick_rendition(assets), "https://x/a~medium.mp4")
        self.assertEqual(sources.nasa_pick_rendition(["http://x/a.srt"]), "")

    def test_commons(self):
        c = {x["source_id"]: x for x in sources.commons_clips((DATA / "commons_search_SYNTHETIC.json").read_text())}
        surge = c["File:Hurricane Ian storm surge Fort Myers Beach.webm"]
        self.assertEqual((surge["licence"], surge["author"], surge["date"]), ("CC BY 4.0", "Jane Example", "2022-09-28"))

    def test_youtube_by_id_only(self):
        c = sources.youtube_clip("AAAAAAAAAAA", yt_extract("AAAAAAAAAAA"))
        self.assertEqual((c["date"], c["author"]), ("2022-09-29", "Example Weather Lab"))
        with self.assertRaisesRegex(ValueError, "not a YouTube video id"):
            sources.youtube_info("https://youtu.be/x", extract=yt_extract)


class Rules(unittest.TestCase):
    def test_pool_decisions(self):
        p = pool()
        self.assertEqual(p[ISS].status, "proposed")
        self.assertEqual(p[ISS].credit, "Video: NASA")
        # Artemis rollback "ahead of Hurricane Ian": in the window and names Ian -> proposed (the user decides)
        self.assertEqual(p["nasa:KSC-20220927-MH-CSH01_0001-Artemis_I_Rollback-3314998"].status, "proposed")
        self.assertEqual(p["commons:File:Hurricane Ian storm surge Fort Myers Beach.webm"].credit, "CC BY 4.0 — Jane Example")
        self.assertEqual(p["commons:File:FEMA Hurricane Ian Sanibel causeway.webm"].credit, "Video: FEMA (public domain)")
        nc = p["commons:File:Ian aftermath news clip.webm"]
        self.assertEqual(nc.status, "rejected")
        self.assertIn("CC BY-NC 4.0 is not allowed", nc.reasons[0])
        irma = p["commons:File:Hurricane Irma Florida 2017.webm"]
        self.assertEqual(irma.status, "rejected")
        self.assertTrue(any("outside the event window" in r for r in irma.reasons))
        self.assertEqual(p["youtube:AAAAAAAAAAA"].credit, "CC BY — Example Weather Lab (YouTube)")
        self.assertEqual(p["youtube:BBBBBBBBBBB"].status, "rejected")
        self.assertIn("news and storm-chaser clips are off", p["youtube:BBBBBBBBBBB"].reasons[0])
        gov = p["youtube:CCCCCCCCCCC"]
        self.assertEqual((gov.status, gov.credit), ("proposed", "Video: NOAA Satellites (public domain)"))
        self.assertIn("third-party", gov.reasons[0])

    def test_relevance_needs_a_name(self):
        c = fp.Clip(id="nasa:x", source="nasa", source_id="x", title="Space station views", description="Clouds over the ocean", date="2022-09-28")
        self.assertEqual(fp.relevance(c, IAN), ["neither the title nor the description names Hurricane Ian, Ian, Fort Myers, Florida, Cayo Costa"])
        c.description = "Ian over the Gulf"
        self.assertEqual(fp.relevance(c, IAN), [])
        c.title, c.description = "Ianthe", ""   # a word, not a substring
        self.assertTrue(fp.relevance(c, IAN))

    def test_no_date_is_not_relevant(self):
        c = fp.Clip(id="nasa:x", source="nasa", source_id="x", title="Hurricane Ian")
        self.assertIn("no date", fp.relevance(c, IAN)[0])

    def test_nasa_third_party_flagged(self):
        clips = sources.nasa_clips(json.dumps({"collection": {"items": [{"data": [{"nasa_id": "a", "media_type": "video", "title": "Ian",
                                                                                     "description": "Hurricane Ian. Credit: Some TV Station", "date_created": "2022-09-28T00:00:00Z"}]}]}}))
        self.assertIn("check the rights", clips[0]["notes"][0])


class Approval(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = approval.ClipStore(self.root)
        self.store.save_pool(IAN, list(pool().values()))

    def tearDown(self):
        self.tmp.cleanup()

    def test_storage_round_trip(self):
        self.assertTrue((self.root / "weather" / "clips.json").is_file())
        ev, clips = self.store.load()
        self.assertEqual(ev.name, "Hurricane Ian")
        self.assertEqual(len(clips), 12)   # 5 NASA + 4 Commons + 3 YouTube

    def test_rejected_licence_cannot_be_approved(self):
        with self.assertRaisesRegex(approval.ApprovalError, "cannot be approved.*CC BY-NC"):
            self.store.decide("commons:File:Ian aftermath news clip.webm", "approved")
        with self.assertRaisesRegex(approval.ApprovalError, "cannot be approved.*storm-chaser"):
            self.store.decide("youtube:BBBBBBBBBBB", "approved")

    def test_decisions_survive_a_new_search(self):
        self.store.decide(ISS, "approved", start_s=95, dur_s=8)
        self.store.decide("youtube:AAAAAAAAAAA", "rejected")
        merged = {c.id: c for c in self.store.save_pool(IAN, list(pool().values()))}
        self.assertEqual((merged[ISS].status, merged[ISS].start_s, merged[ISS].dur_s), ("approved", 95, 8))
        self.assertEqual(merged["youtube:AAAAAAAAAAA"].status, "rejected")
        with self.assertRaisesRegex(approval.ApprovalError, "a clip is proposed, approved, rejected"):
            self.store.decide(ISS, "maybe")

    def test_only_approved_downloaded_clips_reach_the_plan(self):
        with self.assertRaisesRegex(approval.ApprovalError, "not approved"):
            approval.download(self.store.get(ISS), self.root, get_text)
        self.store.decide(ISS, "approved", start_s=95, dur_s=8)
        with self.assertRaisesRegex(approval.ApprovalError, "approved but not downloaded"):
            self.store.clip_rows("b6")
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            Path(cmd[-1]).write_bytes(b"mp4")
            return type("R", (), {"returncode": 0, "stderr": ""})()

        assets = '["http://images-assets.nasa.gov/video/x/x~orig.mp4", "http://images-assets.nasa.gov/video/x/x~medium.mp4"]'
        out = approval.download(self.store.get(ISS), self.store.media_dir, lambda u: assets, run=fake_run)
        self.assertEqual(calls[0][:7], ["ffmpeg", "-v", "error", "-y", "-ss", "95", "-i"])
        self.assertEqual(calls[0][7], "https://images-assets.nasa.gov/video/x/x~medium.mp4")
        self.assertIn("-t", calls[0])
        self.store.set_local(ISS, out)
        rows = self.store.clip_rows("b6")
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0][0], rows[0][1], rows[0][19], rows[0][20]), ("b6", "clip", str(out), "8"))
        self.assertEqual(len(rows[0]), 22)   # the Hybrid beat CSV's columns
        credit = self.store.credit_rows("b6", "the space station")
        text = approval.rows_csv(credit)
        parsed = parse_sidecar("beat,vo_anchor,t,id,type,place,data_source,hold,until,extra\n" + text)
        self.assertEqual(parsed[0].extra["text"], "VIDEO: NASA · SEP 28, 2022")
        self.assertEqual(parsed[0].type, "footage_credit")

    def test_youtube_is_handed_to_the_app(self):
        self.store.decide("youtube:AAAAAAAAAAA", "approved")
        with self.assertRaisesRegex(approval.ApprovalError, "app's own code"):
            approval.download(self.store.get("youtube:AAAAAAAAAAA"), self.root, get_text)


if __name__ == "__main__":
    unittest.main()
