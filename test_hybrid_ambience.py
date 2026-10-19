"""Hybrid Map plays a quiet ambience bed under the whole video (it used to have none: 154 effects and 0 beds over 16 minutes). The bed follows what the
beats talk about (water, cold, wind, space, otherwise a calm default), changes rarely, never flaps, and the plan can switch it off."""

from __future__ import annotations

import unittest

from hybrid.compile import plan_to_rows
from hybrid.plan import Beat, CameraStep, Clip, HybridPlan, Support
from pakmap.audio_plan import plan_audio
from pakmap.sounds import AMBIENCE_IDS


def _beat(i, start, end, text="", mode="map"):
    b = Beat(id=f"b{i}", mode=mode, start=float(start), end=float(end), narration=text, purpose=text)
    if mode == "footage":
        b.clips = [Clip(asset="stock_video:x")]
        b.footage_intent = text
    else:
        b.geo_intent = text
        if i == 1:
            b.camera = [CameraStep(action="start", place="Victoria", frame="region", t=0.0)]
        if mode == "map_footage":
            b.support = Support(asset="stock_image:x", t=float(start) + 1.0, label="X", hold=3.0)
    return b


def _beds(plan):
    rows, _, _ = plan_to_rows(plan)
    return [(r.t_start, r.ambience) for r in rows if r.layer_type == "sound" and r.ambience]


class TestHybridAmbience(unittest.TestCase):
    def test_a_plan_with_no_topic_still_gets_a_calm_bed_from_the_start(self):
        beds = _beds(HybridPlan(duration=40, beats=[_beat(1, 0, 20, "flat farmland"), _beat(2, 20, 40, "stone fences", "footage")]))
        self.assertEqual(len(beds), 1)
        self.assertEqual(beds[0][0], 0.0)
        self.assertIn(beds[0][1], AMBIENCE_IDS)

    def test_the_bed_follows_the_topic_and_waits_before_changing(self):
        plan = HybridPlan(duration=90, beats=[_beat(1, 0, 30, "the lake and the river"), _beat(2, 30, 60, "ice across the glacier", "footage"),
                                              _beat(3, 60, 90, "dust and wind across the desert")])
        beds = _beds(plan)
        self.assertEqual([t for t, _ in beds], [0.0, 30.0, 60.0])
        self.assertEqual(len({b for _, b in beds}), 3)

    def test_a_topic_that_flips_back_within_the_minimum_stretch_does_not_flap(self):
        plan = HybridPlan(duration=60, beats=[_beat(1, 0, 10, "the lake"), _beat(2, 10, 20, "the glacier", "footage"), _beat(3, 20, 60, "the lake again")])
        self.assertEqual(len(_beds(plan)), 1)

    def test_the_same_topic_twice_is_one_bed(self):
        plan = HybridPlan(duration=60, beats=[_beat(1, 0, 30, "the lake"), _beat(2, 30, 60, "the river", "footage")])
        self.assertEqual(len(_beds(plan)), 1)

    def test_the_plan_can_switch_ambience_off(self):
        plan = HybridPlan(duration=40, beats=[_beat(1, 0, 40, "the lake")], settings={"ambience": False})
        self.assertEqual(_beds(plan), [])

    def test_the_beds_reach_the_sound_plan(self):
        plan = HybridPlan(duration=60, beats=[_beat(1, 0, 30, "the lake"), _beat(2, 30, 60, "snow and ice", "footage")])
        rows, _, _ = plan_to_rows(plan)
        hints = [{"t": r.t_start, "ambience": r.ambience} for r in rows if r.ambience]
        audio = plan_audio({"events": [], "duration": 60.0}, {"ambience": hints}, duration=60.0)
        self.assertEqual([round(b.start) for b in audio.beds], [0, 30])
        self.assertEqual(audio.beds[-1].end, 60.0)


if __name__ == "__main__":
    unittest.main()
