"""Voiceover page: switching project clears the old project's voiceover, script and messages; same project keeps them."""
import tempfile
import types
import unittest
from pathlib import Path

from ui import voiceover_view as vv


class Box:
    def __init__(self): self.text = ""
    def get(self, *_a): return self.text
    def delete(self, *_a): self.text = ""
    def insert(self, _i, t): self.text = t


class Var:
    def __init__(self, v=""): self.v = v
    def set(self, v): self.v = v
    def get(self): return self.v


class Widget:
    def __init__(self): self.state = None; self.value = None
    def configure(self, **kw): self.state = kw.get("state", self.state)
    def set(self, v): self.value = v


def ws(root, pid):
    audio = Path(root) / pid / "audio"
    audio.mkdir(parents=True)
    return types.SimpleNamespace(project_id=pid, folder_name=pid, audio_dir=audio)


class SwitchTests(unittest.TestCase):
    def test_switch_clears_old_voiceover_and_shows_the_new_one(self):
        with tempfile.TemporaryDirectory() as root:
            a, b = ws(root, "A"), ws(root, "B")
            (a.audio_dir / "A_voiceover.mp3").write_bytes(b"x")
            app = types.SimpleNamespace(_workspace=a)
            view = types.SimpleNamespace(_vo_busy=False, _vo_play_proc=None, _vo_last=None, _vo_play_btn=Widget(), _vo_download_btn=Widget(),
                                         _vo_stopplay_btn=Widget(), _vo_play_var=Var(), _vo_status_var=Var("old"), _vo_progress=Widget(),
                                         _vo_text=Box(), _vo_count_var=Var(), _vo_project_key=vv._project_key(app))
            view._vo_text.text = "old script"
            vv._set_last(view, a.audio_dir / "A_voiceover.mp3", "Last voiceover in this project")
            vv.sync_project(view, app)                       # same project: nothing changes
            self.assertEqual(view._vo_text.text, "old script")
            self.assertIsNotNone(view._vo_last)
            app._workspace = b                               # switch to a project with no voiceover
            vv.sync_project(view, app)
            self.assertIsNone(view._vo_last)
            self.assertEqual(view._vo_text.text, "")
            self.assertEqual(view._vo_status_var.get(), "")
            self.assertEqual(view._vo_play_btn.state, "disabled")
            (b.audio_dir / "B_voiceover.mp3").write_bytes(b"x")   # a project that has its own voiceover
            app._workspace = a
            vv.sync_project(view, app)
            self.assertEqual(view._vo_last.name, "A_voiceover.mp3")
            app._workspace = b
            vv.sync_project(view, app)
            self.assertEqual(view._vo_last.name, "B_voiceover.mp3")

    def test_a_running_generation_is_left_alone(self):
        app = types.SimpleNamespace(_workspace=types.SimpleNamespace(project_id="X"))
        view = types.SimpleNamespace(_vo_busy=True, _vo_project_key="other")
        vv.sync_project(view, app)
        self.assertEqual(view._vo_project_key, "other")


if __name__ == "__main__":
    unittest.main()
