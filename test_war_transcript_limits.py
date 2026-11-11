"""War Footage Director: transcript fetches under YouTube rate limits (live run: 7 x 429 for 3 videos, each retried within seconds and then
refused as 'a programme without a transcript'). No network: Searcher gets fake info / captions callables."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from cinematic_explainer.war import director_moment as M
from cinematic_explainer.war import director_search as S

VID = "abcDEF12345"
JSON3 = json.dumps({"events": [{"tStartMs": 600000, "dDurationMs": 4000, "segs": [{"utf8": "drones hit a refinery near St Petersburg"}]}]})


def _info(calls, chapters=None, url="https://captions/en.json3"):
    def info(vid):
        calls.append(vid)
        return {"duration": 900, "upload_date": "20261109", "title": "News hour",
                "automatic_captions": {"en": [{"ext": "vtt", "url": url + ".vtt"}, {"ext": "json3", "url": url}]},
                "subtitles": {}, "chapters": chapters or []}
    return info


class _HTTPError(Exception):
    def __init__(self, code):
        super().__init__(f"{code} Client Error")
        self.response = SimpleNamespace(status_code=code)


def _captions(script):
    """Each call pops the next outcome: an int is an HTTP error code, else the caption text."""
    seen = []

    def fetch(url, ext):
        seen.append(url)
        out = script.pop(0) if script else JSON3
        if isinstance(out, int):
            raise _HTTPError(out)
        return out
    return fetch, seen


def _searcher(td, info, captions):
    s = S.Searcher(Path(td), info=info, captions=captions, pause=0)
    s.backoff = (0, 0)
    return s


class TranscriptLimits(unittest.TestCase):
    def test_429_then_success_after_backoff(self):
        with tempfile.TemporaryDirectory() as td:
            calls = []
            fetch, seen = _captions([429, JSON3])
            s = _searcher(td, _info(calls), fetch)
            segs = s.transcript(VID)
            self.assertEqual(segs[0]["start"], 600.0)
            self.assertEqual(len(seen), 2)
            self.assertEqual(s.transcript_status[VID], "ok")
            self.assertEqual(s.calls["transcript_rate_limited"], 0)
            self.assertTrue((Path(td) / f"t_{VID}.json").exists())

    def test_persistent_429_is_rate_limited_not_cached_and_not_retried_at_once(self):
        with tempfile.TemporaryDirectory() as td:
            calls = []
            fetch, seen = _captions([429, 429, 429, 429, 429])
            s = _searcher(td, _info(calls), fetch)
            self.assertIsNone(s.transcript(VID))
            self.assertEqual(len(seen), 3)                       # first try + two backoff retries
            self.assertEqual(s.transcript_status[VID], "rate_limited")
            self.assertEqual(s.calls["transcript_rate_limited"], 1)
            self.assertFalse((Path(td) / f"t_{VID}.json").exists())
            n_info = len(calls)
            segs, status, chapters = s.transcript_info(VID)   # within the cooldown: no request at all
            self.assertIsNone(segs)
            self.assertEqual(status, "rate_limited")
            self.assertEqual(len(seen), 3)
            self.assertEqual(len(calls), n_info)

    def test_a_429_from_the_metadata_call_counts_too(self):
        with tempfile.TemporaryDirectory() as td:
            def info(vid):
                raise Exception("ERROR: Unable to download webpage: HTTP Error 429: Too Many Requests")
            s = _searcher(td, info, _captions([])[0])
            self.assertIsNone(s.transcript(VID))
            self.assertEqual(s.transcript_status[VID], "rate_limited")

    def test_caption_track_comes_from_the_details_cache(self):
        with tempfile.TemporaryDirectory() as td:
            calls = []
            fetch, seen = _captions([JSON3])
            s = _searcher(td, _info(calls, chapters=[{"start_time": 0, "title": "Intro"}]), fetch)
            d = s.details(S.Candidate(video_id=VID))
            self.assertEqual(d["captions"], {"ext": "json3", "url": "https://captions/en.json3"})
            self.assertEqual(d["chapters"], [{"start": 0.0, "title": "Intro"}])
            self.assertTrue(s.transcript(VID))
            self.assertEqual(len(calls), 1)                      # details() fetched info once; transcript() did not again
            # a fresh Searcher reads the details from disk and still makes no metadata call
            s2 = _searcher(td, _info(calls), fetch)
            (Path(td) / f"t_{VID}.json").unlink()
            self.assertTrue(s2.transcript(VID))
            self.assertEqual(len(calls), 1)

    def test_an_expired_caption_url_refetches_info_once(self):
        with tempfile.TemporaryDirectory() as td:
            calls = []
            fetch, seen = _captions([403, JSON3])
            s = _searcher(td, _info(calls), fetch)
            s.details(S.Candidate(video_id=VID))
            self.assertTrue(s.transcript(VID))
            self.assertEqual(len(calls), 2)

    def test_chapters_give_the_hint_without_a_transcript(self):
        with tempfile.TemporaryDirectory() as td:
            calls = []
            chapters = [{"start_time": 0, "title": "Headlines"}, {"start_time": 590, "title": "Drones over St Petersburg"},
                        {"start_time": 840, "title": "Satellites"}]
            s = _searcher(td, _info(calls, chapters=chapters), _captions([429, 429, 429])[0])
            s.details(S.Candidate(video_id=VID))
            segs, status, ch = s.transcript_info(VID)
            self.assertEqual(status, "rate_limited")
            reading = SimpleNamespace(section_terms=["St Petersburg"], key_terms=["St Petersburg"])
            self.assertEqual(M.check(900.0, segs, reading, status=status, chapters=ch), (True, 590.0, ""))

    def test_rate_limited_wording_says_unverified(self):
        reading = SimpleNamespace(section_terms=["St Petersburg"], key_terms=[])
        ok, hint, why = M.check(900.0, None, reading, status="rate_limited")
        self.assertFalse(ok)
        self.assertIsNone(hint)
        self.assertIn("rate-limited", why)
        self.assertIn("cannot be verified", why)
        self.assertNotIn("without a transcript", why)
        _ok, _h, plain = M.check(900.0, None, reading)
        self.assertIn("without a transcript", plain)


if __name__ == "__main__":
    unittest.main()
