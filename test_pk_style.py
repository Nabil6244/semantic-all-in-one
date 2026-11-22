"""PK style (ui/pk_section.py) and loudness levelling (audio_level.py)."""

import json
import subprocess
from types import SimpleNamespace

import audio_level
import make_video
from autorun import job as J
from smart_editing import SmartEditingSettings
from ui import pk_section as pk
from ui import style_pages, style_registry


class _WS:
    def __init__(self, path):
        self.path = path

    def read_meta(self):
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def _write_meta(self, data):
        self.path.write_text(json.dumps(data))


def test_pk_card_sits_next_to_normal_video():
    general = dict(style_registry.GROUPS)["General"]
    assert general[:2] == ("Normal video", "PK")
    assert style_registry.BUILT_ON["PK"] == "Normal video"
    assert "PK" in style_registry.EXTRA_BLURBS and "PK" in style_registry.EXTRA_CARDS


def test_pick_saves_pk_in_the_project_and_other_picks_clear_it(tmp_path):
    app = SimpleNamespace(_workspace=_WS(tmp_path / "project.json"), _settings={}, generation_mode="normal")
    assert style_pages.pick_variant(app, "PK") == ("Normal video", False)
    assert pk.is_active(app) and app._workspace.read_meta()["pk_style"] is True
    assert style_pages.active_variant(app, "normal") == "PK"
    style_pages.pick_variant(app, "Modern Tech News")
    assert not pk.is_active(app) and "pk_style" not in app._workspace.read_meta()


def test_recipe_only_for_pk_projects(tmp_path):
    app = SimpleNamespace(_workspace=_WS(tmp_path / "project.json"), _settings={"music_boost_db": None, "doc_style": False})
    assert pk.setting(app, "doc_style") is False and pk.setting(app, "music_boost_db") is None
    pk.remember(app, True)
    assert pk.setting(app, "doc_style") is True and pk.setting(app, "normal_hybrid_style") is True
    assert pk.setting(app, "music_boost_db") == pk.RECIPE["music_boost_db"]
    s = pk.smart_settings(SmartEditingSettings(text_effects=True, sound_effects=False))
    assert s.text_effects is False and s.sound_effects is True and s.sound_effects_intensity == "high"


def test_pk_in_batch_tables():
    assert J.STYLES["pk"]["pick"] == "PK" and make_video.STYLES["pk"][3] == "PK"


def _tone(path, db):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=220:duration=4", "-af", f"volume={db}dB",
                    str(path)], check=True)


def test_hot_voice_is_levelled_to_standard_same_length(tmp_path):
    src = tmp_path / "hot.wav"
    _tone(src, 0)   # a loud full-scale tone, far above -16 LUFS
    before = audio_level.integrated_lufs(src)
    out = audio_level.level_narration(src, tmp_path)
    assert out != str(src)
    assert abs(audio_level.integrated_lufs(out) - audio_level.NARRATION_LUFS) < 1.0 < abs(before - audio_level.NARRATION_LUFS)
    dur = lambda f: float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
                                         capture_output=True, text=True).stdout)
    assert abs(dur(out) - dur(src)) < 0.01
    assert audio_level.level_narration(src, tmp_path) == out   # cached


def test_level_voice_left_alone_and_bad_file_passes_through(tmp_path):
    assert audio_level.gain_for(-16.4, -16.0) == 0.0 and audio_level.gain_for(None, -16.0) == 0.0
    missing = tmp_path / "nope.wav"
    assert audio_level.level_narration(missing, tmp_path) == str(missing)
