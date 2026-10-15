"""Weather never stops on a broken plan: the dry run (weather/preflight.py), the last repair (weather/guard.py), stale data
(weather.resolve.prune_stale) and a small stress test of broken plans (weather/stress.py's mutations on a fixture project).

The big stress test runs on real projects: python -m weather.stress ~/Downloads/VideoGenerator/<project> --mutants 300.
No network (the NWS answers are fixtures), no rendering."""

from __future__ import annotations

import random
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from hybrid.plan import Beat, CameraStep, Clip, HybridPlan, Layer, validate_plan
from weather import generate as wgen
from weather.cache import HttpCache
from weather.nws import NwsClient

from test_weather_autofix import BEATS, LAYERS, WORDS
from test_weather_data import DALLAS_ROUTES, FakeNet, fixture
from test_weather_render import NOW

from weather import stress


def plan_of(*beats, duration=None):
    return HybridPlan(duration=duration or beats[-1].end, beats=list(beats))


class TheGuardAnswersEveryHybridCheck(unittest.TestCase):
    def fixed(self, plan):
        from weather.guard import make_safe

        notes = []
        make_safe(plan, notes)
        self.assertEqual(validate_plan(plan), [], notes)
        return notes

    def test_footage_beat_with_no_clip_gets_stock_or_the_map(self):
        plan = plan_of(Beat(id="b1", mode="map", start=0, end=5, camera=[CameraStep("start", "Texas", "region")]),
                       Beat(id="b2", mode="footage", start=5, end=10, narration="Floodwater filled the streets of Houston."))
        self.fixed(plan)
        self.assertTrue(plan.beats[1].mode == "map" or plan.beats[1].clips[0].asset.startswith("stock_video:"))

    def test_map_beat_with_clips_and_footage_beat_with_layers(self):
        plan = plan_of(Beat(id="b1", mode="map", start=0, end=5, camera=[CameraStep("start", "Texas", "region")],
                            clips=[Clip("stock_video:rain")], layers=[Layer("t1", "hud_title", 0.5, label="RAIN")]),
                       Beat(id="b2", mode="footage", start=5, end=10, clips=[Clip("stock_video:rain")],
                            layers=[Layer("t2", "hud_title", 5.5, label="X")]))
        self.fixed(plan)
        self.assertEqual(plan.beats[0].clips, [])
        self.assertEqual(plan.beats[1].layers, [])

    def test_no_start_several_starts_and_unknown_moves(self):
        plan = plan_of(Beat(id="b1", mode="map", start=0, end=6, camera=[CameraStep("zoom", "Texas", "city", t=1, dur=2)]),
                       Beat(id="b2", mode="map", start=6, end=12, camera=[CameraStep("start", "Texas", "region", t=6),
                                                                         CameraStep("start", "Ohio", "national", t=7)]))
        self.fixed(plan)
        self.assertEqual(sum(c.action == "start" for b in plan.beats for c in b.camera), 1)
        self.assertTrue(all(c.frame in ("", "globe", "continental", "country", "region", "local") for b in plan.beats for c in b.camera))

    def test_duplicate_ids_gaps_bad_layers_and_overlapping_titles(self):
        plan = plan_of(Beat(id="b1", mode="map", start=0, end=5, camera=[CameraStep("start", "Texas", "region")],
                            layers=[Layer("t", "hud_title", 0.5, label="ONE", until="end"), Layer("t", "hud_title", 2.0, label="TWO"),
                                    Layer("x", "bolt", 1.0), Layer("s", "stat", 9.0), Layer("u", "caption", 1, text="hi", until="forever")]),
                       Beat(id="b1", mode="mapp", start=7, end=6, transition="wipe"),
                       Beat(id="b3", mode="map", start=6, end=12), duration=12)
        notes = self.fixed(plan)
        self.assertEqual(len({b.id for b in plan.beats}), len(plan.beats))
        self.assertTrue(any("title" in n for n in notes))

    def test_a_plan_that_was_already_fine_is_not_touched(self):
        plan = plan_of(Beat(id="b1", mode="map", start=0, end=5, camera=[CameraStep("start", "Texas", "region")],
                            layers=[Layer("t1", "hud_title", 0.5, label="RAIN")]),
                       Beat(id="b2", mode="footage", start=5, end=10, clips=[Clip("stock_video:rain")]))
        before = plan.to_dict()
        self.assertEqual(self.fixed(plan), [])
        self.assertEqual(plan.to_dict(), before)


class OldDataIsLeftOutNotAStop(unittest.TestCase):
    def test_ended_alerts_and_old_forecasts_are_pruned(self):
        from weather.resolve import Snapshot, check_fresh, prune_stale

        snap = Snapshot(prepared=NOW.isoformat(), forecasts={"Dallas, TX": {"issued": (NOW - timedelta(hours=9)).isoformat()}},
                        alerts={"TX": {"areas": [{"event": "Heat Advisory", "ends": (NOW - timedelta(hours=1)).isoformat()},
                                                 {"event": "Flood Watch", "ends": (NOW + timedelta(hours=5)).isoformat()}]}})
        notes = []
        self.assertEqual(prune_stale(snap, NOW, notes), 2)
        check_fresh(snap, NOW)   # what is left is fresh
        self.assertEqual([a["event"] for a in snap.alerts["TX"]["areas"]], ["Flood Watch"])
        self.assertIn("left out", notes[0])


class BrokenPlansOnAFixtureProject(unittest.TestCase):
    """A small stress test in the suite: the fixture project broken 60 ways never stops before the render."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        cls.project = wgen.WeatherProject(d / "proj")
        cls.project.root.mkdir()
        cls.project.beats_csv.write_text(BEATS, encoding="utf-8")
        cls.project.layers_csv.write_text(LAYERS, encoding="utf-8")
        client = NwsClient("me@example.com", cache=HttpCache(d / "cache", now=lambda: NOW), fetch=FakeNet(DALLAS_ROUTES))
        wgen.fetch(cls.project, "me@example.com", now=NOW, client=client, gibs_get=lambda u: fixture("gibs_geocolor_domain.xml").decode())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_fixture_itself_passes_the_dry_run_with_the_engine_checks(self):
        from weather.preflight import preflight

        rep = preflight(self.project, WORDS, 10.0, now=NOW)
        self.assertTrue(rep.ok, rep.to_text())

    def test_sixty_broken_versions(self):
        from weather.preflight import preflight

        rng = random.Random(5)
        stopped = []
        for k in range(60):
            beats, layers, words, dur, now, applied = stress.mutate(BEATS, LAYERS, list(WORDS), 10.0, rng)
            if now is not None:
                continue   # stale data is covered above (the fixture's own data would all be pruned)
            self.project.beats_csv.write_text(beats, encoding="utf-8")
            if layers is None:
                self.project.layers_csv.unlink(missing_ok=True)
            else:
                self.project.layers_csv.write_text(layers, encoding="utf-8")
            rep = preflight(self.project, words, dur, now=NOW, engine=False, edit_style=rng.choice(["classic", "teamplate"]))
            if not rep.ok:
                stopped.append((applied, rep.stops[:2]))
        self.project.beats_csv.write_text(BEATS, encoding="utf-8")
        self.project.layers_csv.write_text(LAYERS, encoding="utf-8")
        self.assertEqual(stopped, [])


class AClipThatCannotBeFoundIsLeftOut(unittest.TestCase):
    """One stock search with no result used to stop the whole video ("Open the Visual Plan tab to Retry ..."): now the video is made
    without that clip (weather.guard.drop_unfound, then the generator runs again with the clips it found)."""

    def test_unfound_clips_leave_the_plan_and_it_still_passes(self):
        from hybrid.compile import plan_to_rows, rows_to_csv
        from weather.guard import drop_unfound, make_safe

        plan = plan_of(Beat(id="b1", mode="map", start=0, end=5, camera=[CameraStep("start", "Texas", "region")]),
                       Beat(id="b2", mode="footage", start=5, end=10, clips=[Clip("stock_video:a dam"), Clip("stock_video:no such thing")]),
                       Beat(id="b3", mode="footage", start=10, end=15, clips=[Clip("stock_video:no such thing at all")]))
        with tempfile.TemporaryDirectory() as d:
            script = Path(d) / "hybrid_script.csv"
            script.write_text(rows_to_csv(plan_to_rows(plan)[0]), encoding="utf-8")
            notes = []
            self.assertEqual(drop_unfound(plan, script, ["2", "3"], notes), 2)
        make_safe(plan, notes, new_requests=False)
        self.assertEqual(validate_plan(plan), [])
        self.assertEqual([c.asset for b in plan.beats for c in b.clips], ["stock_video:a dam"])
        self.assertEqual(plan.beats[-1].mode, "map")   # no new search: the beat whose only clip was not found stays on the map


if __name__ == "__main__":
    unittest.main()
