"""Unit tests for local Qwen3-TTS integration. No real model download."""

from __future__ import annotations

import csv
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tts.base import CLONE_MODEL_ID, DEFAULT_VOICE, TTSResult
from tts.device import DeviceInfo, detect_device, is_apple_silicon
from tts.errors import TTSError, map_exception
from tts.model_cache import find_local_model, model_is_installed
from tts.narration import collect_narration, narration_from_csv, validate_text
from tts.qwen_provider import Qwen3TTSProvider


def _write_wav(path: Path, frames: int = 24000, sr: int = 24000) -> None:
    import wave

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(b"\x00\x00" * frames)


class TestProviderInitAndMissing(unittest.TestCase):
    def test_provider_starts_unloaded(self):
        provider = Qwen3TTSProvider()
        self.assertFalse(provider.loaded)
        self.assertEqual(provider.model_id, CLONE_MODEL_ID)

    def test_missing_qwen_package(self):
        provider = Qwen3TTSProvider()
        real_import = __import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "qwen_tts" or name.startswith("qwen_tts"):
                raise ImportError("No module named 'qwen_tts'")
            return real_import(name, globals, locals, fromlist, level)

        with patch("tts.qwen_provider.find_local_model", return_value=Path("/tmp/model")):
            with patch("builtins.__import__", side_effect=fake_import):
                with self.assertRaises(TTSError) as ctx:
                    provider.ensure_loaded()
        self.assertEqual(ctx.exception.code, "package_missing")
        self.assertIn("not installed", ctx.exception.message.lower())

    def test_missing_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("tts.model_cache.candidate_model_dirs", return_value=[Path(tmp) / "nope"]):
                with self.assertRaises(TTSError) as ctx:
                    find_local_model()
        self.assertEqual(ctx.exception.code, "VOICE_CLONE_MODEL_UNAVAILABLE")
        self.assertIn("1.7B Base", ctx.exception.message)

    def test_model_is_installed_false_without_cache(self):
        with patch("tts.model_cache.candidate_model_dirs", return_value=[]):
            self.assertFalse(model_is_installed())


class TestTextValidation(unittest.TestCase):
    def test_empty_text(self):
        with self.assertRaises(TTSError) as ctx:
            validate_text("   ")
        self.assertEqual(ctx.exception.code, "invalid_text")

    def test_placeholder_rejected(self):
        with self.assertRaises(TTSError):
            validate_text("Paste your narration script here...")

    def test_valid_text(self):
        self.assertIn("city", validate_text("The city never sleeps."))


class TestSuccessfulGeneration(unittest.TestCase):
    def test_generate_clone_writes_wav_and_metadata(self):
        provider = Qwen3TTSProvider()
        fake_model = MagicMock()
        fake_model.create_voice_clone_prompt.return_value = ["prompt"]
        fake_model.generate_voice_clone.return_value = ([[0.0] * 48000], 24000)
        provider._model = fake_model
        provider._device = "cpu"
        provider._load_time = 1.5

        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp) / "ref.wav"
            _write_wav(ref, frames=48000, sr=24000)
            out = Path(tmp) / "narration.wav"
            with patch(
                "tts.qwen_provider._write_audio",
                side_effect=lambda p, w, sr: _write_wav(Path(p), frames=48000, sr=sr),
            ):
                with patch("tts.qwen_provider._probe_audio", return_value=(2.0, 24000)):
                    result = provider.generate_clone(
                        "Imagine standing in the middle of a city that never sleeps.",
                        out,
                        ref_audio=ref,
                        ref_text="Reference transcript for the sample audio.",
                    )
            self.assertIsInstance(result, TTSResult)
            self.assertEqual(result.duration_seconds, 2.0)
            self.assertEqual(result.sample_rate, 24000)
            self.assertEqual(result.format, "wav")
            self.assertEqual(result.provider, "qwen3-tts")
            self.assertTrue(result.local)
            fake_model.generate_voice_clone.assert_called_once()
            kwargs = fake_model.generate_voice_clone.call_args.kwargs
            self.assertEqual(kwargs["language"], "English")
            self.assertFalse(kwargs["x_vector_only_mode"])
            self.assertTrue(out.is_file())

    def test_missing_output_file(self):
        provider = Qwen3TTSProvider()
        fake_model = MagicMock()
        fake_model.create_voice_clone_prompt.return_value = ["prompt"]
        fake_model.generate_voice_clone.return_value = ([[0.0] * 100], 24000)
        provider._model = fake_model
        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp) / "ref.wav"
            _write_wav(ref, frames=120000, sr=24000)
            out = Path(tmp) / "missing.wav"
            with patch("tts.qwen_provider._write_audio"):
                with self.assertRaises(TTSError) as ctx:
                    provider.generate_clone(
                        "A complete speakable narration sentence.",
                        out,
                        ref_audio=ref,
                        ref_text="Reference transcript.",
                    )
        self.assertEqual(ctx.exception.code, "output_missing")

    def test_model_reuse(self):
        provider = Qwen3TTSProvider()
        fake_model = MagicMock()
        fake_model.create_voice_clone_prompt.return_value = ["prompt"]
        fake_model.generate_voice_clone.return_value = ([[0.1] * 24000], 24000)
        provider._model = fake_model
        provider._load_time = 12.0
        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp) / "ref.wav"
            _write_wav(ref, frames=120000, sr=24000)
            with patch(
                "tts.qwen_provider._write_audio",
                side_effect=lambda p, w, sr: _write_wav(Path(p), frames=24000, sr=sr),
            ):
                with patch("tts.qwen_provider._probe_audio", return_value=(1.0, 24000)):
                    a = provider.generate_clone(
                        "First complete narration sentence here.",
                        Path(tmp) / "a.wav",
                        ref_audio=ref,
                        ref_text="Reference transcript.",
                    )
                    b = provider.generate_clone(
                        "Second complete narration sentence here.",
                        Path(tmp) / "b.wav",
                        ref_audio=ref,
                        ref_text="Reference transcript.",
                    )
        self.assertEqual(fake_model.create_voice_clone_prompt.call_count, 2)
        self.assertEqual(fake_model.generate_voice_clone.call_count, 2)
        self.assertIs(provider._model, fake_model)
        self.assertEqual(a.load_time_seconds, b.load_time_seconds)


class TestErrorMapping(unittest.TestCase):
    def test_oom(self):
        mapped = map_exception(RuntimeError("CUDA out of memory"))
        self.assertEqual(mapped.code, "TTS_OUT_OF_MEMORY")
        self.assertIn("memory", mapped.message.lower())

    def test_package_import(self):
        mapped = map_exception(ImportError("No module named 'qwen_tts'"))
        self.assertEqual(mapped.code, "package_missing")
        self.assertIn("isolated env", mapped.message.lower())

    def test_package_import_packaged_worker(self):
        with patch.dict("os.environ", {"VIDEOGEN_PACKAGED": "1"}, clear=False):
            mapped = map_exception(ImportError("No module named 'qwen_tts'"))
        self.assertEqual(mapped.code, "package_missing")
        self.assertIn("download", mapped.message.lower())
        self.assertNotIn("conda", mapped.message.lower())

    def test_runtime_corrupted_winerror(self):
        mapped = map_exception(
            OSError(
                "[WinError 1392] The file or directory is corrupted and unreadable: "
                "'C:\\\\Users\\\\Asus\\\\.videogen\\\\runtime\\\\qwen\\\\win-amd64\\\\Lib\\\\site-packages\\\\torch\\\\_higher_order_ops'"
            )
        )
        self.assertEqual(mapped.code, "runtime_corrupted")
        self.assertIn("corrupted", mapped.message.lower())
        self.assertIn(".videogen", mapped.message.lower())

    def test_passthrough_tts_error(self):
        err = TTSError("already mapped", "invalid_text")
        self.assertIs(map_exception(err), err)


class TestDeviceDetection(unittest.TestCase):
    def test_cpu_when_no_torch(self):
        real_import = __import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "torch":
                raise ImportError("No module named 'torch'")
            return real_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=fake_import):
            info = detect_device()
        self.assertEqual(info.name, "cpu")
        self.assertTrue(info.detail)

    def test_prefers_mps_on_apple(self):
        torch = MagicMock()
        torch.cuda.is_available.return_value = False
        torch.backends.mps.is_available.return_value = True
        with patch.dict("sys.modules", {"torch": torch}):
            info = detect_device()
        self.assertEqual(info.name, "mps")
        self.assertIn("Metal", info.detail)

    def test_apple_silicon_flag_matches_platform(self):
        self.assertIsInstance(is_apple_silicon(), bool)
        self.assertIsInstance(detect_device(), DeviceInfo)


class TestManualCsvAndAiScript(unittest.TestCase):
    def test_csv_uses_script_segment_not_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "script.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=["scene_number", "script_segment", "asset_type", "prompt"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "scene_number": "2",
                        "script_segment": "A rocket prepares for launch.",
                        "asset_type": "youtube_video",
                        "prompt": "falcon 9 rocket standing on launchpad night floodlights",
                    }
                )
                writer.writerow(
                    {
                        "scene_number": "1",
                        "script_segment": "The city never sleeps.",
                        "asset_type": "stock_video",
                        "prompt": "busy night traffic timelapse",
                    }
                )
            spoken = narration_from_csv(path)
        self.assertEqual(spoken, "The city never sleeps. A rocket prepares for launch.")
        self.assertNotIn("falcon 9", spoken)
        self.assertNotIn("timelapse", spoken)

    def test_ai_script_prefers_pasted_narration_not_visual_fields(self):
        from visual_director.schema import parse_visual_plan

        payload = {
            "topic": "City night",
            "scenes": [
                {
                    "scene_id": 1,
                    "narration": "Imagine standing in the middle of a city that never sleeps.",
                    "visual_goal": "establish city",
                    "visual_description": "wet streets neon reflections aerial",
                    "asset_type": "stock_video",
                    "provider_preference": "stock_video",
                    "search_queries": ["busy city night traffic wet roads"],
                    "timestamp_needed": False,
                    "duration": 2.5,
                    "importance": "high",
                    "fallbacks": ["flow_image"],
                    "visual_treatment": "cinematic",
                    "transition": "cut",
                },
                {
                    "scene_id": 2,
                    "narration": "Thousands of cars rush through the streets.",
                    "visual_goal": "show traffic",
                    "visual_description": "overhead freeway at night long exposure",
                    "asset_type": "stock_video",
                    "provider_preference": "stock_video",
                    "search_queries": ["night freeway traffic long exposure"],
                    "timestamp_needed": False,
                    "duration": 2.5,
                    "importance": "medium",
                    "fallbacks": ["flow_image"],
                    "visual_treatment": "cinematic",
                    "transition": "cut",
                },
            ],
        }
        plan = parse_visual_plan(payload)
        spoken = collect_narration(
            script_text="Imagine standing in the middle of a city that never sleeps.",
            visual_plan=plan,
        )
        self.assertIn("city that never sleeps", spoken)
        self.assertNotIn("neon reflections", spoken)
        self.assertNotIn("busy city night traffic", spoken)
        row = plan.scenes[0].to_scene_row()
        self.assertEqual(row.stock, "busy city night traffic wet roads")
        plan_spoken = collect_narration(csv_path=None, visual_plan=plan, script_text="")
        self.assertEqual(
            plan_spoken,
            "Imagine standing in the middle of a city that never sleeps. Thousands of cars rush through the streets.",
        )
        self.assertNotEqual(plan_spoken, row.stock)

    def test_collect_from_simple_plan_object(self):
        plan = SimpleNamespace(
            scenes=[
                SimpleNamespace(narration="Spoken line one."),
                SimpleNamespace(narration="Spoken line two."),
            ]
        )
        spoken = collect_narration(visual_plan=plan)
        self.assertEqual(spoken, "Spoken line one. Spoken line two.")


class TestClientPythonDiscovery(unittest.TestCase):
    def test_status_without_venv(self):
        from tts.client import qwen_runtime_status

        with patch("tts.client.find_qwen_python", return_value=None):
            ok, message = qwen_runtime_status()
        self.assertFalse(ok)
        self.assertIn("qwen", message.lower())

    def test_status_without_qwen_tts_package(self):
        from pathlib import Path

        from tts.client import qwen_runtime_status

        fake_py = Path("/tmp/fake-python")
        with patch("tts.client.find_qwen_python", return_value=fake_py):
            with patch("tts.client.qwen_tts_importable", return_value=False):
                with patch.object(sys, "frozen", True, create=True):
                    ok, message = qwen_runtime_status()
        self.assertFalse(ok)
        self.assertIn("download", message.lower())

    def test_frozen_ignores_qwen_tts_python_env(self):
        from pathlib import Path

        from tts.client import find_qwen_python

        provisioned = Path("/tmp/provisioned-python")
        env_python = Path("/tmp/env-python")
        with patch.object(sys, "frozen", True, create=True):
            with patch("tts.client._provisioned_qwen_python", return_value=provisioned):
                with patch.dict(os.environ, {"QWEN_TTS_PYTHON": str(env_python)}, clear=False):
                    self.assertEqual(find_qwen_python(), provisioned)


if __name__ == "__main__":
    unittest.main()
