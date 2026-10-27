"""Health Cinema UI: Classic/High-end switch and Music option reach engine.run_health_cinema correctly (engine mocked, no rendering)."""
from __future__ import annotations

import types, unittest
from unittest import mock

from health_cinema import app_section as S


class _Var:
    def __init__(self, v): self.v = v
    def get(self): return self.v
    def set(self, v): self.v = v


def _app(edit="Classic", music=True):
    return types.SimpleNamespace(_health_edit_var=_Var(edit), _health_music_var=_Var(music), _health_music_cb=mock.Mock())


class EditSwitchTests(unittest.TestCase):
    def test_default_is_classic_music_on_no_extra_kwargs(self):
        a = _app()
        self.assertEqual(a._health_edit_var.get(), "Classic"); self.assertTrue(a._health_music_var.get())
        self.assertEqual(S.edit_kwargs(a), {})

    def test_high_end_passes_edit_and_music(self):
        self.assertEqual(S.edit_kwargs(_app("High-end", True)), {"edit": "high_end", "music": True})
        self.assertEqual(S.edit_kwargs(_app("High-end", False)), {"edit": "high_end", "music": False})

    def test_music_checkbox_disabled_for_classic(self):
        a = _app("Classic"); S.sync_edit_options(a); a._health_music_cb.configure.assert_called_with(state="disabled")
        a = _app("High-end"); S.sync_edit_options(a); a._health_music_cb.configure.assert_called_with(state="normal")

    def test_run_call_receives_kwargs(self):
        with mock.patch("health_cinema.engine.run_health_cinema") as run:
            run("p", [], "v", "o", profile="x", **S.edit_kwargs(_app("High-end", False)))
            self.assertEqual(run.call_args.kwargs["edit"], "high_end"); self.assertFalse(run.call_args.kwargs["music"])
            run("p", [], "v", "o", profile="x", **S.edit_kwargs(_app()))
            self.assertNotIn("edit", run.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
