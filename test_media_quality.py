"""Regression tests for centralized media quality scoring."""

from __future__ import annotations

import unittest

from providers.media_quality.scoring import (
    effective_dimensions,
    is_preview_or_derivative_url,
    passes_quality_floor,
    selection_score,
)


class TestMediaQualityScoring(unittest.TestCase):
    def test_rejects_preview_urls(self):
        self.assertTrue(is_preview_or_derivative_url("https://cdn.example/img-thumbs/960w/foo.jpg"))
        ok, reason = passes_quality_floor(
            width=1920,
            height=1080,
            download_url="https://cdn.example/img-thumbs/960w/foo.jpg",
            provider="openverse",
        )
        self.assertFalse(ok)
        self.assertIn("preview", reason)

    def test_relevant_1080_beats_irrelevant_4k(self):
        query = "apollo 11 saturn v launch"
        good = selection_score(
            query=query,
            script_segment="Apollo 11 left Earth on a Saturn V rocket.",
            title="Apollo 11 Saturn V Launch",
            description="Saturn V liftoff from Kennedy Space Center",
            width=1920,
            height=1080,
            download_url="https://example.invalid/apollo_hd.mp4",
            provider="nasa",
            media_type="video",
            is_archival=True,
        )
        bad = selection_score(
            query=query,
            script_segment="Apollo 11 left Earth on a Saturn V rocket.",
            title="Random city skyline",
            description="Modern downtown at night",
            width=3840,
            height=2160,
            download_url="https://example.invalid/city_4k.mp4",
            provider="openverse",
            media_type="video",
        )
        self.assertGreater(good.total, bad.total)

    def test_archival_480p_can_pass(self):
        ok, _ = passes_quality_floor(
            width=640,
            height=480,
            download_url="https://archive.org/download/apollo11/apollo11.mpeg",
            provider="archive",
            media_type="video",
            is_archival=True,
        )
        self.assertTrue(ok)

    def test_pixabay_webformat_dims_capped(self):
        w, h = effective_dimensions(4000, 3000, "https://pixabay.com/get/webformatURL.jpg", "pixabay")
        self.assertLessEqual(w, 640)

    def test_openverse_low_res_rejected_for_stock(self):
        ok, reason = passes_quality_floor(
            width=640,
            height=360,
            download_url="https://example.invalid/photo.jpg",
            provider="openverse",
            media_type="image",
        )
        self.assertFalse(ok)
        self.assertIn("floor", reason)

    def test_provider_repetition_soft_penalty(self):
        a = selection_score(
            query="rocket launch",
            title="Launch",
            width=1920,
            height=1080,
            download_url="https://example.invalid/a.mp4",
            provider="openverse",
            provider_use_counts={"openverse": 5},
        )
        b = selection_score(
            query="rocket launch",
            title="Launch",
            width=1920,
            height=1080,
            download_url="https://example.invalid/b.mp4",
            provider="pexels",
            provider_use_counts={"openverse": 5},
        )
        self.assertGreater(b.total, a.total)

    def test_nasa_topic_boost_for_space_scene(self):
        from providers.media_quality.scoring import provider_topic_boost

        boost = provider_topic_boost(
            "nasa",
            "The Saturn V rocket lifted off toward the Moon.",
            "Apollo launch pad night",
            "space_documentary",
        )
        self.assertGreater(boost, 0.3)


if __name__ == "__main__":
    unittest.main()
