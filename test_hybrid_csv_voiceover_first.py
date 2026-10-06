#!/usr/bin/env python3
"""Hybrid Map: picking the CSV before the voiceover never makes the user pick the CSV again. The app offers to choose the
voiceover there and then loads the same CSV; declined, the CSV waits and loads as soon as a voiceover is set."""

from __future__ import annotations

import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


class TestHybridCsvBeforeVoiceover(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")
        cls.app = _app

    def _fake(self, voiceover=None):
        App = self.app.VideoGeneratorApp
        state = {"voice": voiceover, "imported": []}
        fake = types.SimpleNamespace(_hybrid_pending_csv=None, status=None)
        fake._current_voiceover_path = lambda: state["voice"]
        fake._hybrid_status_var = types.SimpleNamespace(set=lambda v: setattr(fake, "status", v))
        fake.after = lambda _ms, fn: fn()
        fake._hybrid_import_csv_file = types.MethodType(App._hybrid_import_csv_file, fake)
        return fake, state

    def test_choosing_the_voiceover_then_loads_the_same_csv(self):
        fake, state = self._fake()
        csv = Path(tempfile.mkdtemp()) / "plan.csv"
        csv.write_text("a,b\n", encoding="utf-8")

        def browse(stay=False):
            self.assertTrue(stay, "the user stays on the Hybrid screen")
            state["voice"] = Path("/tmp/voice.wav")
            return True

        fake._browse_audio = browse
        reads = []
        with mock.patch.object(self.app.messagebox, "askyesno", return_value=True), \
             mock.patch.object(self.app.Path, "read_text", side_effect=lambda *a, **k: reads.append(1) or (_ for _ in ()).throw(OSError("stop here"))), \
             mock.patch.object(self.app.messagebox, "showerror"):
            fake._hybrid_import_csv_file(str(csv))
        self.assertEqual(reads, [1], "the same CSV is read straight after the voiceover is chosen")
        self.assertIsNone(fake._hybrid_pending_csv)

    def test_declined_the_csv_waits_and_loads_when_a_voiceover_is_set(self):
        fake, state = self._fake()
        with mock.patch.object(self.app.messagebox, "askyesno", return_value=False):
            fake._hybrid_import_csv_file("/tmp/plan.csv")
        self.assertEqual(fake._hybrid_pending_csv, "/tmp/plan.csv")
        self.assertIn("waiting for the voiceover", fake.status)

        App = self.app.VideoGeneratorApp
        voice = Path(tempfile.mkdtemp()) / "voice.wav"
        voice.write_bytes(b"RIFF")
        loaded = []
        fake.audio_var = types.SimpleNamespace(set=lambda v: None)
        fake._workspace = None
        fake._refresh_voiceover_active_label = lambda: None
        fake._bind_voice_player_to = lambda p: None
        fake._sync_primary_cta = lambda: None
        fake._hybrid_import_csv_file = lambda p: loaded.append(p)
        with mock.patch.object(self.app.Path, "is_file", return_value=True):
            App._set_active_voiceover(fake, voice, source="imported")
        self.assertEqual(loaded, ["/tmp/plan.csv"])
        self.assertIsNone(fake._hybrid_pending_csv)


if __name__ == "__main__":
    unittest.main()
