"""Tests for documentary ambience profile taxonomy."""

from __future__ import annotations

import unittest

from sfx.ambience_profiles import (
    AMBIENCE_PROFILE_TARGETS,
    AMBIENCE_SHORTLIST_CAP,
    ambience_tags_for_text,
    infer_ambience_profile,
    smart_editing_profile_tags,
)
from sfx.curator import shortlist_ambience_by_profile, Candidate
from pathlib import Path


class TestAmbienceProfiles(unittest.TestCase):
    def test_infer_profiles_from_filenames(self) -> None:
        self.assertEqual(infer_ambience_profile("AMBIENCE_City_Street_Traffic"), "traffic")
        self.assertEqual(infer_ambience_profile("forest_birds_nature_loop"), "nature")
        self.assertEqual(infer_ambience_profile("heavy_rain_storm_thunder"), "rain")
        self.assertEqual(infer_ambience_profile("train_station_platform"), "transport")
        self.assertEqual(infer_ambience_profile("highway_traffic_distant"), "traffic")
        self.assertEqual(infer_ambience_profile("ocean_waves_shore"), "water")
        self.assertEqual(infer_ambience_profile("campfire_crackle"), "fire")
        self.assertEqual(infer_ambience_profile("dark_atmospheric_drone"), "atmospheric")

    def test_tags_include_primary_profile(self) -> None:
        tags = ambience_tags_for_text("office_roomtone_quiet")
        self.assertEqual(tags[0], "room")
        self.assertIn("indoor", tags)

    def test_shortlist_cap_matches_targets(self) -> None:
        self.assertEqual(AMBIENCE_SHORTLIST_CAP, sum(AMBIENCE_PROFILE_TARGETS.values()))

    def test_smart_editing_profile_map_covers_targets(self) -> None:
        mapping = smart_editing_profile_tags()
        for profile in AMBIENCE_PROFILE_TARGETS:
            self.assertIn(profile, mapping)
            self.assertIn(profile, mapping[profile])

    def test_shortlist_ambience_diverse_by_profile(self) -> None:
        samples = [
            ("city/city_traffic_a.wav", "city", 90.0),
            ("city/city_traffic_b.wav", "city", 85.0),
            ("rain/gentle_rain_a.wav", "rain", 88.0),
            ("nature/forest_wind_a.wav", "nature", 80.0),
        ]
        cands = [
            Candidate(
                path=Path(name),
                category="ambience",
                score=score,
                duration=4.0,
                tags=ambience_tags_for_text(name),
                intensity="medium",
                reasons=[],
            )
            for name, _prof, score in samples
        ]
        picks = shortlist_ambience_by_profile(cands)
        profiles = {infer_ambience_profile(str(p.path)) for p in picks}
        self.assertIn("traffic", profiles)
        self.assertIn("rain", profiles)


if __name__ == "__main__":
    unittest.main()
