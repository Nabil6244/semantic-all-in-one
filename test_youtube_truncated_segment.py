"""A YouTube cut that comes back far shorter than asked for is a failed extraction, not a clip: used as is, the video repeats
that one second again and again for the whole scene. The next candidate is tried instead."""

from __future__ import annotations

import unittest
from unittest import mock

from asset_manager import AssetManager
from providers.base import SceneRow
from providers.youtube.base import VideoCandidate, YouTubeProvider
from test_asset_pipeline import AssetPipelineTestCase, FakeYouTubeBackend


def candidate(vid):
    return VideoCandidate(video_id=vid, url=f"https://youtube.com/watch?v={vid}", title=f"Documentary {vid}", channel="C", duration=3000.0, has_captions=False)


class TestTruncatedYouTubeSegment(AssetPipelineTestCase):
    def scene(self):
        return SceneRow(scene_number="6", script_segment="x", asset_type="youtube_video", prompt="prehistoric sahara lakes")

    def manager(self, *cands):
        backend = FakeYouTubeBackend(list(cands))
        return AssetManager(self.images, youtube_provider=YouTubeProvider(backend, clip_duration=8.0), log=lambda *_: None), backend

    def test_a_one_second_cut_of_an_eight_second_request_is_rejected_and_the_next_candidate_is_used(self):
        mgr, backend = self.manager(candidate("short"), candidate("good"))
        with mock.patch("providers.youtube.base._downloaded_seconds", side_effect=lambda p: 1.019 if len(backend.download_calls) == 1 else 8.0):
            result = mgr.resolve_scene(self.scene())
        self.assertTrue(result.ok, result.error)
        self.assertEqual(len(backend.download_calls), 2)                                     # the first (truncated) cut was thrown away, the second candidate tried
        self.assertEqual(mgr.manifest.get("6")["provider_asset_id"], backend.download_calls[1][0])

    def test_when_every_candidate_is_truncated_the_scene_fails_instead_of_looping_one_second(self):
        mgr, _ = self.manager(candidate("a"), candidate("b"))
        with mock.patch("providers.youtube.base._downloaded_seconds", return_value=1.0):
            result = mgr.resolve_scene(self.scene())
        self.assertFalse(result.ok)
        self.assertIn("only 1.0s of the 8.0s", str(result.error))
        self.assertFalse((self.images / "006.mp4").exists())

    def test_a_clip_close_to_the_request_or_one_that_cannot_be_measured_is_kept(self):
        for measured in (7.2, 4.0, None):
            with self.subTest(measured=measured):
                mgr, _ = self.manager(candidate("ok"))
                with mock.patch("providers.youtube.base._downloaded_seconds", return_value=measured):
                    self.assertTrue(mgr.resolve_scene(self.scene()).ok)
                for f in self.images.glob("*"):
                    if f.is_file():
                        f.unlink()


if __name__ == "__main__":
    unittest.main()
