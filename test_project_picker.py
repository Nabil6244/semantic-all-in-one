#!/usr/bin/env python3
"""Project picker helper + optional dialog smoke (skipped without a display)."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from types import SimpleNamespace

from project_picker import (
    _display_order,
    project_dicts_from_workspaces,
)


class _SeqMethodStub:
    def __init__(self, project_id: str, title: str, seq: int) -> None:
        self.project_id = project_id
        self.title = title
        self._seq = seq

    def display_seq(self) -> str:
        return f"{int(self._seq):03d}"


class _SeqAttrStub:
    def __init__(self, project_id: str, title: str, display_seq) -> None:
        self.project_id = project_id
        self.title = title
        self.display_seq = display_seq


class TestProjectDictsFromWorkspaces(unittest.TestCase):
    def test_callable_display_seq_and_last_used(self):
        a = _SeqMethodStub("project_20260820_001", "Sleep Schedule", 1)
        b = _SeqMethodStub("project_20260820_003", "Focus", 3)
        out = project_dicts_from_workspaces([a, b], last_id="project_20260820_003")
        self.assertEqual(
            out,
            [
                {
                    "id": "project_20260820_001",
                    "title": "Sleep Schedule",
                    "display_seq": "001",
                    "last_used": False,
                },
                {
                    "id": "project_20260820_003",
                    "title": "Focus",
                    "display_seq": "003",
                    "last_used": True,
                },
            ],
        )

    def test_attribute_display_seq_keeps_int(self):
        ws = _SeqAttrStub("p2", "Two", 2)
        out = project_dicts_from_workspaces([ws], last_id="")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], "p2")
        self.assertEqual(out[0]["title"], "Two")
        self.assertEqual(out[0]["display_seq"], 2)
        self.assertFalse(out[0]["last_used"])

    def test_preserves_caller_order(self):
        items = [
            _SeqMethodStub("c", "C", 3),
            _SeqMethodStub("a", "A", 1),
            _SeqMethodStub("b", "B", 2),
        ]
        titles = [d["title"] for d in project_dicts_from_workspaces(items)]
        self.assertEqual(titles, ["C", "A", "B"])

    def test_empty_and_none_workspaces(self):
        self.assertEqual(project_dicts_from_workspaces([]), [])
        self.assertEqual(project_dicts_from_workspaces(None), [])

    def test_missing_display_seq_falls_back_to_seq(self):
        ws = SimpleNamespace(project_id="x", title="Untitled", seq=7)
        out = project_dicts_from_workspaces([ws], last_id="nope")
        self.assertEqual(out[0]["display_seq"], 7)
        self.assertFalse(out[0]["last_used"])

    def test_empty_last_id_marks_none(self):
        ws = _SeqMethodStub("same", "One", 1)
        out = project_dicts_from_workspaces([ws], last_id="")
        self.assertFalse(out[0]["last_used"])


class TestDisplayOrder(unittest.TestCase):
    def test_reverses_clearly_oldest_first(self):
        projects = [
            {"id": "a", "title": "A", "display_seq": "001", "last_used": False},
            {"id": "b", "title": "B", "display_seq": 2, "last_used": True},
            {"id": "c", "title": "C", "display_seq": "003", "last_used": False},
        ]
        ordered = _display_order(projects)
        self.assertEqual([p["id"] for p in ordered], ["c", "b", "a"])

    def test_keeps_newest_first_and_mixed(self):
        newest_first = [
            {"id": "c", "display_seq": 3},
            {"id": "b", "display_seq": 2},
            {"id": "a", "display_seq": 1},
        ]
        self.assertEqual([p["id"] for p in _display_order(newest_first)], ["c", "b", "a"])
        mixed = [
            {"id": "b", "display_seq": 2},
            {"id": "a", "display_seq": 1},
            {"id": "c", "display_seq": 3},
        ]
        self.assertEqual([p["id"] for p in _display_order(mixed)], ["b", "a", "c"])


def _tk_available() -> bool:
    """Probe Tk in a child process so a display crash cannot kill this suite."""
    if os.environ.get("PROJECT_PICKER_SKIP_GUI") == "1":
        return False
    probe = (
        "import tkinter as tk; r = tk.Tk(); r.withdraw(); "
        "r.update_idletasks(); r.destroy()"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", probe],
            timeout=8,
            capture_output=True,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


@unittest.skipUnless(_tk_available(), "no display / Tk unavailable")
class TestProjectPickerDialogSmoke(unittest.TestCase):
    def setUp(self):
        import customtkinter as ctk
        from project_picker import ProjectPickerDialog

        self.ctk = ctk
        self.ProjectPickerDialog = ProjectPickerDialog
        self.root = ctk.CTk()
        self.root.withdraw()
        self.addCleanup(self._cleanup_root)

    def _cleanup_root(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_constructs_with_projects_and_empty_list(self):
        events: list[str] = []
        projects = [
            {"id": "p1", "title": "Alpha", "display_seq": "001", "last_used": False},
            {"id": "p2", "title": "Beta", "display_seq": "002", "last_used": True},
        ]
        dlg = self.ProjectPickerDialog(
            self.root,
            projects=projects,
            on_create=lambda title: events.append(f"create:{title}"),
            on_select=lambda pid: events.append(f"select:{pid}"),
            on_open_folder=lambda: events.append("folder"),
            on_settings=lambda: events.append("settings"),
            on_dismiss=lambda: events.append("dismiss"),
        )
        self.addCleanup(lambda: dlg._safe_destroy())
        self.root.update_idletasks()
        self.assertEqual(dlg.title(), "Choose a project")
        self.assertTrue(dlg.winfo_exists())
        dlg._safe_destroy()

        empty = self.ProjectPickerDialog(
            self.root,
            projects=[],
            on_create=lambda _t: None,
            on_select=lambda _i: None,
            on_open_folder=lambda: None,
        )
        self.addCleanup(lambda: empty._safe_destroy())
        self.root.update_idletasks()
        self.assertTrue(empty.winfo_exists())
        empty._safe_destroy()
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
