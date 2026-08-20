"""Unit tests for local Qwen voice cloning. No real model download."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tts.base import CLONE_MODEL_ID, DEFAULT_MODEL_ID, PREVIEW_TEXT, TTSResult
from tts.client import QwenTTSClient
from tts.device import DeviceInfo
from tts.errors import TTSError, map_exception
from tts.model_cache import find_local_model
from tts.qwen_provider import Qwen3TTSProvider
from tts.reference import REF_MAX_SECONDS, validate_reference
from tts.worker import _handle


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


def _clone_result(path: Path) -> TTSResult:
    return TTSResult(
        path=path,
        duration_seconds=2.0,
        sample_rate=24000,
        format="wav",
        provider="qwen3-tts",
        voice="clone",
        generation_time_seconds=1.0,
        load_time_seconds=0.5,
        device="cpu",
        model=CLONE_MODEL_ID,
        local=True,
    )


class TestCloneOnlyModel(unittest.TestCase):
    def test_single_clone_model(self) -> None:
        self.assertEqual(DEFAULT_MODEL_ID, CLONE_MODEL_ID)
        self.assertEqual(CLONE_MODEL_ID, "Qwen/Qwen3-TTS-12Hz-1.7B-Base")

    def test_client_build_voice_prompt_op(self) -> None:
        client = QwenTTSClient(python_bin=Path("/usr/bin/true"))
        captured = {}

        def fake_send(payload):
            captured["payload"] = payload
            return {"type": "ok"}

        client._send_raw = fake_send  # type: ignore[method-assign]
        client.build_voice_prompt("/tmp/ref.wav", "Exact transcript.", Path("/tmp/prompt.pt"))
        self.assertEqual(captured["payload"]["op"], "build_voice_prompt")
        self.assertEqual(captured["payload"]["ref_text"], "Exact transcript.")

    def test_client_generate_clone_uses_saved_prompt(self) -> None:
        client = QwenTTSClient(python_bin=Path("/usr/bin/true"))
        captured = {}

        def fake_send(payload):
            captured["payload"] = payload
            return {
                "type": "result",
                "path": "/tmp/out.wav",
                "duration_seconds": 2.0,
                "sample_rate": 24000,
            }

        client._send_raw = fake_send  # type: ignore[method-assign]
        client.generate_clone(
            "A complete speakable narration sentence.",
            Path("/tmp/out.wav"),
            voice_prompt_path="/tmp/voice_prompt.pt",
        )
        self.assertEqual(captured["payload"]["op"], "generate_clone")
        self.assertEqual(captured["payload"]["voice_prompt_path"], "/tmp/voice_prompt.pt")
        self.assertNotIn("ref_audio", captured["payload"])


class TestReferenceValidation(unittest.TestCase):
    def test_missing_file(self) -> None:
        with self.assertRaises(TTSError) as ctx:
            validate_reference("/tmp/does-not-exist-qwen-ref.wav")
        self.assertEqual(ctx.exception.code, "REFERENCE_AUDIO_NOT_FOUND")

    def test_too_short(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_wav(Path(tmp) / "short.wav", seconds=0.8)
            with self.assertRaises(TTSError) as ctx:
                validate_reference(path)
        self.assertEqual(ctx.exception.code, "REFERENCE_AUDIO_TOO_SHORT")

    def test_too_long(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_wav(Path(tmp) / "long.wav", seconds=REF_MAX_SECONDS + 2)
            with self.assertRaises(TTSError) as ctx:
                validate_reference(path)
        self.assertEqual(ctx.exception.code, "REFERENCE_AUDIO_TOO_LONG")

    def test_valid_wav(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_wav(Path(tmp) / "ok.wav", seconds=8.0)
            info = validate_reference(path)
        self.assertAlmostEqual(info.duration_seconds, 8.0, places=1)


class TestCloneConfigurationAndErrors(unittest.TestCase):
    def test_clone_model_unavailable(self) -> None:
        with patch("tts.model_cache.candidate_model_dirs", return_value=[]):
            with self.assertRaises(TTSError) as ctx:
                find_local_model(CLONE_MODEL_ID)
        self.assertEqual(ctx.exception.code, "VOICE_CLONE_MODEL_UNAVAILABLE")
        self.assertIn("1.7B", ctx.exception.message)

    def test_clone_model_load_failed(self) -> None:
        provider = Qwen3TTSProvider()
        qwen_mod = MagicMock()
        qwen_mod.Qwen3TTSModel.from_pretrained.side_effect = RuntimeError("cannot load weights")
        with patch("tts.qwen_provider.find_local_model", return_value=Path("/tmp/clone-model")):
            with patch("tts.qwen_provider.detect_device", return_value=DeviceInfo("cpu", "cpu")):
                with patch("tts.qwen_provider.torch_load_kwargs", return_value={}):
                    with patch.dict("sys.modules", {"qwen_tts": qwen_mod, "torch": MagicMock()}):
                        with self.assertRaises(TTSError) as ctx:
                            provider.ensure_loaded()
        self.assertEqual(ctx.exception.code, "VOICE_CLONE_MODEL_LOAD_FAILED")

    def test_successful_clone_with_reference_text(self) -> None:
        provider = Qwen3TTSProvider()
        fake = MagicMock()
        fake.create_voice_clone_prompt.return_value = ["prompt"]
        fake.generate_voice_clone.return_value = ([[0.0] * 48000], 24000)
        provider._model = fake
        provider._device = "mps"
        provider._load_time = 3.0
        with tempfile.TemporaryDirectory() as tmp:
            ref = _write_wav(Path(tmp) / "ref.wav", seconds=6)
            out = Path(tmp) / "voiceover_qwen.wav"
            with patch(
                "tts.qwen_provider._write_audio",
                side_effect=lambda p, w, sr: _write_wav(Path(p), seconds=2.0, sr=sr),
            ):
                with patch("tts.qwen_provider._probe_audio", return_value=(2.0, 24000)):
                    result = provider.generate_clone(
                        "This is a test of the local voice cloning system.",
                        out,
                        ref_audio=ref,
                        ref_text="Reference transcript for cloning.",
                    )
        self.assertEqual(result.model, CLONE_MODEL_ID)
        fake.create_voice_clone_prompt.assert_called_once()
        kwargs = fake.create_voice_clone_prompt.call_args.kwargs
        self.assertFalse(kwargs["x_vector_only_mode"])
        fake.generate_voice_clone.assert_called_once()
        gen_kwargs = fake.generate_voice_clone.call_args.kwargs
        self.assertFalse(gen_kwargs["x_vector_only_mode"])

    def test_reuses_saved_prompt_without_reprocessing_reference(self) -> None:
        provider = Qwen3TTSProvider()
        fake = MagicMock()
        fake.generate_voice_clone.return_value = ([[0.1] * 24000], 24000)
        provider._model = fake
        with tempfile.TemporaryDirectory() as tmp:
            prompt = Path(tmp) / "voice_prompt.pt"
            prompt.write_bytes(b"saved")
            with patch.object(provider, "load_voice_prompt", return_value=["saved-prompt"]):
                with patch(
                    "tts.qwen_provider._write_audio",
                    side_effect=lambda p, w, sr: _write_wav(Path(p), seconds=1.0, sr=sr),
                ):
                    with patch("tts.qwen_provider._probe_audio", return_value=(1.0, 24000)):
                        provider.generate_clone(
                            PREVIEW_TEXT,
                            Path(tmp) / "preview.wav",
                            voice_prompt_path=prompt,
                        )
        fake.create_voice_clone_prompt.assert_not_called()
        fake.generate_voice_clone.assert_called_once()


class TestWorkerCommunication(unittest.TestCase):
    def test_build_voice_prompt_op(self) -> None:
        fake = MagicMock()
        with patch("tts.worker._get_provider", return_value=fake):
            out = _handle(
                {
                    "op": "build_voice_prompt",
                    "ref_audio": "/tmp/ref.wav",
                    "ref_text": "Exact words.",
                    "prompt_path": "/tmp/prompt.pt",
                }
            )
        self.assertEqual(out["type"], "ok")
        fake.build_voice_prompt.assert_called_once()

    def test_clone_op_uses_saved_prompt(self) -> None:
        fake = MagicMock()
        fake.generate_clone.return_value = _clone_result(Path("/tmp/b.wav"))
        with patch("tts.worker._get_provider", return_value=fake):
            out = _handle(
                {
                    "op": "generate_clone",
                    "text": "A complete speakable narration sentence.",
                    "output_path": "/tmp/b.wav",
                    "voice_prompt_path": "/tmp/prompt.pt",
                }
            )
        self.assertEqual(out["type"], "result")
        fake.generate_clone.assert_called_once()
        kwargs = fake.generate_clone.call_args.kwargs
        self.assertEqual(str(kwargs["voice_prompt_path"]), "/tmp/prompt.pt")


class TestErrorCodes(unittest.TestCase):
    def test_timeout_mapping(self) -> None:
        mapped = map_exception(TimeoutError("timed out"))
        self.assertEqual(mapped.code, "TTS_TIMEOUT")


if __name__ == "__main__":
    unittest.main()
