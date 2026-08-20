"""Tests for persistent Qwen voice profiles."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tts.base import CLONE_MODEL_ID, PROFILE_FORMAT_VERSION
from tts.errors import TTSError
from tts.reference import validate_reference
from tts.voice_library import (
    PROFILE_NAME,
    PROMPT_NAME,
    REFERENCE_NAME,
    VoiceProfile,
    create_voice_profile,
    delete_voice,
    get_default_voice,
    get_voice,
    list_voices,
    refresh_profile_status,
    replace_voice_reference,
    set_default_voice,
)


def _write_wav(path: Path, seconds: float = 8.0, sr: int = 24000) -> Path:
    import wave

    path.parent.mkdir(parents=True, exist_ok=True)
    frames = max(1, int(seconds * sr))
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(b"\x00\x00" * frames)
    return path


class TestVoiceLibrary(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name) / "voices"
        self._patch = patch("tts.voice_library.VOICES_ROOT", self.root)
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()
        self._tmpdir.cleanup()

    def test_create_and_list_profile(self) -> None:
        ref = _write_wav(Path(self._tmpdir.name) / "ref.wav")
        profile = create_voice_profile("Nabil", ref, "Welcome to today's video.")
        self.assertEqual(profile.name, "Nabil")
        self.assertEqual(profile.id, "nabil")
        self.assertEqual(profile.model, CLONE_MODEL_ID)
        self.assertTrue(profile.is_default)
        self.assertTrue(profile.reference_path.is_file())
        data = json.loads((profile.dir / PROFILE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(data["reference_text"], "Welcome to today's video.")
        voices = list_voices()
        self.assertEqual(len(voices), 1)
        self.assertEqual(voices[0].id, "nabil")

    def test_ready_requires_prompt(self) -> None:
        ref = _write_wav(Path(self._tmpdir.name) / "ref.wav")
        profile = create_voice_profile("Nabil", ref, "Exact transcript here.")
        profile.prompt_path.write_bytes(b"fake")
        profile.status = "ready"
        refreshed = refresh_profile_status(profile)
        self.assertEqual(refreshed.status, "ready")

    def test_needs_rebuild_without_prompt(self) -> None:
        ref = _write_wav(Path(self._tmpdir.name) / "ref.wav")
        profile = create_voice_profile("Nabil", ref, "Exact transcript here.")
        refreshed = refresh_profile_status(profile)
        self.assertEqual(refreshed.status, "needs_rebuild")

    def test_persistence_after_reload(self) -> None:
        ref = _write_wav(Path(self._tmpdir.name) / "ref.wav")
        created = create_voice_profile("Nabil", ref, "Spoken words.")
        created.prompt_path.write_bytes(b"prompt")
        created.status = "ready"
        from tts.voice_library import _save_profile

        _save_profile(created)
        loaded = get_voice(created.id)
        assert loaded is not None
        self.assertEqual(loaded.name, "Nabil")
        self.assertEqual(loaded.reference_text, "Spoken words.")
        self.assertTrue(loaded.reference_path.is_file())

    def test_default_voice(self) -> None:
        ref = _write_wav(Path(self._tmpdir.name) / "ref.wav")
        a = create_voice_profile("Alpha", ref, "Alpha transcript long enough.")
        ref2 = _write_wav(Path(self._tmpdir.name) / "ref2.wav")
        b = create_voice_profile("Beta", ref2, "Beta transcript long enough.")
        b.prompt_path.write_bytes(b"p")
        b.status = "ready"
        from tts.voice_library import _save_profile

        _save_profile(b)
        set_default_voice(b.id)
        default = get_default_voice()
        assert default is not None
        self.assertEqual(default.id, b.id)
        self.assertFalse(get_voice(a.id).is_default)

    def test_replace_clears_prompt(self) -> None:
        ref = _write_wav(Path(self._tmpdir.name) / "ref.wav")
        profile = create_voice_profile("Nabil", ref, "Old transcript here.")
        profile.prompt_path.write_bytes(b"old-prompt")
        new_ref = _write_wav(Path(self._tmpdir.name) / "new.wav", seconds=9)
        updated = replace_voice_reference(profile.id, new_ref, "New transcript here.")
        self.assertEqual(updated.status, "building")
        self.assertFalse(updated.prompt_path.is_file())
        self.assertTrue(updated.reference_path.is_file())

    def test_delete_voice(self) -> None:
        ref = _write_wav(Path(self._tmpdir.name) / "ref.wav")
        profile = create_voice_profile("Nabil", ref, "Delete me transcript.")
        delete_voice(profile.id)
        self.assertFalse(profile.dir.exists())
        self.assertEqual(list_voices(), [])

    def test_transcript_required(self) -> None:
        ref = _write_wav(Path(self._tmpdir.name) / "ref.wav")
        with self.assertRaises(TTSError) as ctx:
            create_voice_profile("Nabil", ref, "   ")
        self.assertEqual(ctx.exception.code, "REFERENCE_TEXT_REQUIRED")

    def test_incompatible_format_version(self) -> None:
        ref = _write_wav(Path(self._tmpdir.name) / "ref.wav")
        profile = create_voice_profile("Nabil", ref, "Transcript text.")
        profile.prompt_path.write_bytes(b"prompt")
        profile.profile_format_version = PROFILE_FORMAT_VERSION + 1
        from tts.voice_library import _save_profile

        _save_profile(profile)
        loaded = get_voice(profile.id)
        assert loaded is not None
        self.assertEqual(refresh_profile_status(loaded).status, "needs_rebuild")


class TestReferenceValidationIntegration(unittest.TestCase):
    def test_valid_reference_for_library(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_wav(Path(tmp) / "ok.wav", seconds=8.0)
            info = validate_reference(path)
            self.assertEqual(info.suffix, ".wav")


if __name__ == "__main__":
    unittest.main()
