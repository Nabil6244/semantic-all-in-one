#!/usr/bin/env python3
"""Focused tests for ResearchView's folder/media-action buttons and the
reused-vs-new media breakdown in the result summary — exercised against a
real (hidden) Tk root, mirroring the pattern already validated for this view
in earlier sessions.

Run: python -m pytest test_research_view_ui.py -v
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import customtkinter as ctk

import ui.views as uv
from research.models import MediaCandidate, PropertySummary, ResearchResult


class FakeWorkspace:
    def __init__(self, research_dir: Path):
        self.research_dir = research_dir

    def read_meta(self):
        return {}

    def to_dict(self):
        return {"project_id": "p1"}

    def _write_meta(self, data):
        pass


class FakeApp:
    def __init__(self, research_dir: Path):
        self._workspace = FakeWorkspace(research_dir)
        self._settings = {}
        self._asset_manager = "sentinel"

    def _persist_global_settings(self):
        pass


class ResearchViewButtonStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.research_dir = self.tmp / "research"
        self.root = ctk.CTk()
        self.root.withdraw()
        self.app = FakeApp(self.research_dir)
        self.frame = uv.ResearchView(self.root, self.app)
        self.frame.pack()

    def tearDown(self):
        self.root.destroy()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_buttons_disabled_when_nothing_exists(self):
        self.frame.on_show()
        self.assertEqual(self.frame._open_research_btn.cget("state"), "disabled")
        self.assertEqual(self.frame._open_media_folder_btn.cget("state"), "disabled")
        self.assertEqual(self.frame._open_media_btn.cget("state"), "disabled")

    def test_research_folder_button_enabled_once_folder_exists(self):
        self.research_dir.mkdir(parents=True)
        self.frame.on_show()
        self.assertEqual(self.frame._open_research_btn.cget("state"), "normal")
        # media/ still doesn't exist
        self.assertEqual(self.frame._open_media_folder_btn.cget("state"), "disabled")
        self.assertEqual(self.frame._open_media_btn.cget("state"), "disabled")

    def test_media_button_enabled_and_picks_lowest_numbered_file(self):
        media_dir = self.research_dir / "media"
        media_dir.mkdir(parents=True)
        (media_dir / "002.jpg").write_bytes(b"b")
        (media_dir / "001.jpg").write_bytes(b"a")  # rank-1 (lowest number)
        self.frame.on_show()
        self.assertEqual(self.frame._open_media_folder_btn.cget("state"), "normal")
        self.assertEqual(self.frame._open_media_btn.cget("state"), "normal")
        self.assertEqual(self.frame._top_media_path, media_dir / "001.jpg")

    def test_refresh_from_fresh_result_prefers_first_usable_entry(self):
        media_dir = self.research_dir / "media"
        media_dir.mkdir(parents=True)
        real_file = media_dir / "007.jpg"
        real_file.write_bytes(b"x")
        result = ResearchResult(
            property=PropertySummary(name="Hunters Ridge"),
            media=[
                MediaCandidate(local_path=None, media_type="image", source_url="https://x.test/a.jpg"),  # not usable
                MediaCandidate(local_path=real_file, media_type="image", source_url="https://x.test/b.jpg"),
            ],
            sources=[],
            ok=True,
        )
        self.frame._refresh_folder_buttons(result)
        self.assertEqual(self.frame._top_media_path, real_file)
        self.assertEqual(self.frame._open_media_btn.cget("state"), "normal")

    def test_open_path_does_not_raise_on_missing_path(self):
        # must be a safe no-op, never crash the UI thread
        uv.ResearchView._open_path(None)
        uv.ResearchView._open_path(self.tmp / "does" / "not" / "exist")


class ResearchViewSummaryBreakdownTests(unittest.TestCase):
    """The reused/newly-downloaded breakdown must only ever be derived from
    download_note already present on the media — never invented."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.research_dir = self.tmp / "research"
        self.research_dir.mkdir(parents=True)
        self.root = ctk.CTk()
        self.root.withdraw()
        self.app = FakeApp(self.research_dir)
        self.frame = uv.ResearchView(self.root, self.app)
        self.frame.pack()

    def tearDown(self):
        self.root.destroy()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _media(self, n_new, n_reused):
        media_dir = self.research_dir / "media"
        media_dir.mkdir(exist_ok=True)
        items = []
        for i in range(n_new):
            p = media_dir / f"new_{i}.jpg"
            p.write_bytes(b"x")
            items.append(MediaCandidate(local_path=p, media_type="image", source_url=f"https://x.test/n{i}.jpg"))
        for i in range(n_reused):
            p = media_dir / f"reused_{i}.jpg"
            p.write_bytes(b"y")
            items.append(MediaCandidate(
                local_path=p, media_type="image", source_url=f"https://x.test/r{i}.jpg",
                download_note="duplicate_reused",
            ))
        return items

    def test_breakdown_shown_when_some_media_reused(self):
        result = ResearchResult(
            property=PropertySummary(name="X"), media=self._media(n_new=2, n_reused=13), sources=[], ok=True,
        )
        self.frame._on_research_complete(result)
        text = self.frame._status_label.cget("text")
        self.assertIn("13 reused", text)
        self.assertIn("2 newly downloaded", text)

    def test_no_breakdown_when_nothing_reused(self):
        result = ResearchResult(
            property=PropertySummary(name="X"), media=self._media(n_new=3, n_reused=0), sources=[], ok=True,
        )
        self.frame._on_research_complete(result)
        text = self.frame._status_label.cget("text")
        self.assertNotIn("reused", text)
        self.assertIn("3 usable media", text)

    def test_zero_usable_media_message_unchanged(self):
        result = ResearchResult(property=PropertySummary(), media=[], sources=[], ok=True)
        self.frame._on_research_complete(result)
        self.assertEqual(self.frame._status_pill.cget("text"), "No media found")


if __name__ == "__main__":
    unittest.main()
