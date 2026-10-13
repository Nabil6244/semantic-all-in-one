"""Phase 2: the whole prep on recorded answers (weather/testdata/automation/prep_recording.json.gz: every NWS and GIBS answer of a
real prep, no network): every file written at once, the render path loads it, and a failed fetch writes nothing."""

import gzip
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from weather.automation.fetch import PrepDataError
from weather.automation.prep import FILES, PrepError, prep, script_edited
from weather.cache import HttpCache, Response
from weather.nws import NwsClient
from weather.resolve import Snapshot

REC_PATH = Path(__file__).resolve().parent / "weather" / "testdata" / "automation" / "prep_recording.json.gz"
REC = json.loads(gzip.decompress(REC_PATH.read_bytes())) if REC_PATH.exists() else {"now": "2026-10-13T12:00:00+00:00", "responses": {}}
NOW = datetime.fromisoformat(REC["now"])


class Recorded:
    def __init__(self, broken=()):
        self.broken, self.calls = tuple(broken), []

    def __call__(self, url, headers):
        self.calls.append(url)
        if any(b in url for b in self.broken):
            return Response(500, b'{"detail": "test outage"}', {}, NOW)
        status, body = REC["responses"].get(url, [404, '{"detail": "not recorded"}'])
        return Response(status, body.encode("utf-8"), {"cache-control": "max-age=600"}, NOW)

    def gibs(self, url):
        return REC["responses"][url][1]


def run(project, broken=(), now=NOW, **kw):
    net = Recorded(broken)
    client = NwsClient("https://example.invalid", cache=HttpCache(Path(tempfile.mkdtemp())), fetch=net, sleep=lambda s: None)
    return prep(project, now=now, client=client, gibs_get=net.gibs, **kw), net


def files(project):
    return {p.name: p.read_bytes() for p in Path(project).iterdir()}


@unittest.skipUnless(REC_PATH.exists(), "no recording yet: python -m weather.automation.record (5:30 AM-9 PM Central)")
class Prep(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp()) / "today"

    def test_every_file_is_written_and_the_render_path_loads_it(self):
        from pakmap.words import estimate_words
        from weather.automation.spoken import strip_hints
        from weather.generate import WeatherProject, plan_layers

        res, net = run(self.dir)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), sorted(FILES))
        meta = json.loads((self.dir / "prep.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["story"]["kind"], res.story.kind)
        self.assertTrue(meta["why"])
        self.assertEqual(len(meta["lines"]), sum(len(s.sentences) for s in res.script.sections))
        self.assertFalse(script_edited(self.dir))
        cov = Snapshot.from_json((self.dir / "coverage.json").read_text(encoding="utf-8"))
        rsv = Snapshot.from_json((self.dir / "resolved.json").read_text(encoding="utf-8"))
        for k, f in rsv.forecasts.items():
            self.assertEqual(f, cov.forecasts[k])   # the screen shows the answers the script was written from
        self.assertTrue(rsv.satellite)
        words = estimate_words(strip_hints((self.dir / "script.txt").read_text(encoding="utf-8")))
        plan, rows, snap, payload = plan_layers(WeatherProject(self.dir), words, words[-1][2] + 1, now=NOW + timedelta(minutes=1))
        self.assertGreater(len(payload.report.lines), 20)
        self.assertTrue(any(e["type"] == "temp_trend" for e in payload.events))
        self.assertFalse([u for u in net.calls if "example" in u])

    def test_running_again_gives_the_same_files(self):
        run(self.dir)
        first = files(self.dir)
        run(self.dir)
        self.assertEqual(files(self.dir), first)

    def test_a_failed_fetch_leaves_the_folder_as_it_was(self):
        run(self.dir)
        before = files(self.dir)
        for broken in ("/alerts/active?status=actual", "gridpoints/", "/alerts/active?status=actual&area="):
            with self.assertRaises((PrepDataError, RuntimeError)):
                run(self.dir, broken=(broken,), force=True)
            self.assertEqual(files(self.dir), before, broken)

    def test_a_failed_first_prep_writes_nothing(self):
        with self.assertRaises(PrepDataError) as cm:
            run(self.dir, broken=("/alerts/active",))
        self.assertIn("Nothing was written", str(cm.exception))
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_forecasts_too_old_leave_cities_out_and_too_many_stop_the_prep(self):
        with self.assertRaises(PrepDataError) as cm:
            run(self.dir, now=NOW + timedelta(hours=12))
        self.assertIn("NWS forecast is", str(cm.exception))
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_an_edited_script_is_not_replaced_unless_asked(self):
        run(self.dir)
        (self.dir / "script.txt").write_text("My own words.\n", encoding="utf-8")
        with self.assertRaises(PrepError):
            run(self.dir)
        self.assertEqual((self.dir / "script.txt").read_text(encoding="utf-8"), "My own words.\n")
        run(self.dir, force=True)
        self.assertFalse(script_edited(self.dir))


if __name__ == "__main__":
    unittest.main()
