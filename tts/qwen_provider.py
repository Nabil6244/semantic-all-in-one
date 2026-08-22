"""In-process Qwen3-TTS 1.7B Base voice cloning. Loaded only inside the isolated worker."""

from __future__ import annotations

import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from tts.base import CLONE_MODEL_ID, DEFAULT_LANGUAGE, PROFILE_FORMAT_VERSION, TTSResult
from tts.device import detect_device, torch_load_kwargs
from tts.errors import (
    CLONE_MODEL_LOAD_FAILED,
    REFERENCE_TEXT_REQUIRED,
    TTSError,
    VOICE_PROFILE_NEEDS_REBUILD,
    map_exception,
    model_missing_message,
    package_missing_message,
)
from tts.model_cache import find_local_model
from tts.narration import narration_chunk_chars_for_device, split_narration_chunks, validate_text
from tts.reference import convert_reference_to_wav, validate_reference

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def _write_audio(path: Path, wav, sr: int) -> None:
    import soundfile as sf

    sf.write(str(path), wav, int(sr))


def _probe_audio(path: Path) -> tuple[float, int]:
    try:
        import soundfile as sf

        info = sf.info(str(path))
        duration = float(info.frames) / float(info.samplerate or 1)
        return duration, int(info.samplerate)
    except Exception as exc:
        raise TTSError(
            f"Generated narration file is not valid audio: {path} ({exc})",
            "invalid_audio",
        ) from exc


def _prompt_items_to_payload(items) -> dict:
    return {
        "format_version": PROFILE_FORMAT_VERSION,
        "model": CLONE_MODEL_ID,
        "items": [asdict(it) for it in items],
    }


def _load_prompt_items(path: Path):
    import torch
    from qwen_tts import VoiceClonePromptItem

    try:
        payload = torch.load(str(path), map_location="cpu", weights_only=False)
    except TypeError:
        payload = torch.load(str(path), map_location="cpu")
    if not isinstance(payload, dict) or "items" not in payload:
        raise TTSError(VOICE_PROFILE_NEEDS_REBUILD, "VOICE_PROFILE_NEEDS_REBUILD")
    if payload.get("model") and payload.get("model") != CLONE_MODEL_ID:
        raise TTSError(VOICE_PROFILE_NEEDS_REBUILD, "VOICE_PROFILE_NEEDS_REBUILD")
    if payload.get("format_version") not in (None, PROFILE_FORMAT_VERSION):
        raise TTSError(VOICE_PROFILE_NEEDS_REBUILD, "VOICE_PROFILE_NEEDS_REBUILD")
    items_raw = payload["items"]
    if not isinstance(items_raw, list) or not items_raw:
        raise TTSError(VOICE_PROFILE_NEEDS_REBUILD, "VOICE_PROFILE_NEEDS_REBUILD")
    items: List[VoiceClonePromptItem] = []
    for d in items_raw:
        if not isinstance(d, dict):
            raise TTSError(VOICE_PROFILE_NEEDS_REBUILD, "VOICE_PROFILE_NEEDS_REBUILD")
        ref_code = d.get("ref_code")
        if ref_code is not None and not torch.is_tensor(ref_code):
            ref_code = torch.tensor(ref_code)
        ref_spk = d.get("ref_spk_embedding")
        if ref_spk is None:
            raise TTSError(VOICE_PROFILE_NEEDS_REBUILD, "VOICE_PROFILE_NEEDS_REBUILD")
        if not torch.is_tensor(ref_spk):
            ref_spk = torch.tensor(ref_spk)
        items.append(
            VoiceClonePromptItem(
                ref_code=ref_code,
                ref_spk_embedding=ref_spk,
                x_vector_only_mode=bool(d.get("x_vector_only_mode", False)),
                icl_mode=bool(d.get("icl_mode", not bool(d.get("x_vector_only_mode", False)))),
                ref_text=d.get("ref_text"),
            )
        )
    return items


class Qwen3TTSProvider:
    def __init__(self, model_id: str = CLONE_MODEL_ID, log=print):
        self.model_id = model_id
        self._log = log
        self._model = None
        self._device = ""
        self._model_path: Optional[Path] = None
        self._load_time = 0.0

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _emit(self, message: str) -> None:
        self._log(message)

    def _unload(self) -> None:
        self._model = None
        try:
            import torch

            if self._device == "mps" and hasattr(torch, "mps"):
                torch.mps.empty_cache()
            if self._device == "cuda" and torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            import torch  # noqa: F401
            from qwen_tts import Qwen3TTSModel
        except ImportError as exc:
            raise TTSError(package_missing_message(), "package_missing") from exc

        try:
            model_path = find_local_model(CLONE_MODEL_ID)
        except TTSError as exc:
            raise TTSError(model_missing_message(), "VOICE_CLONE_MODEL_UNAVAILABLE") from exc

        info = detect_device()
        self._device = info.name
        if info.name == "cpu":
            self._emit(f"[TTS] {info.detail}")
        self._emit("[TTS] Loading Qwen 1.7B Base voice clone model...")
        t0 = time.perf_counter()
        kwargs = torch_load_kwargs(info.name)
        kwargs["local_files_only"] = True
        try:
            self._model = Qwen3TTSModel.from_pretrained(str(model_path), **kwargs)
        except Exception as exc:
            mapped = map_exception(exc)
            if mapped.code in ("generation_failure", "VOICE_CLONE_GENERATION_FAILED") and info.name == "mps":
                self._emit("[TTS] MPS load failed; retrying on CPU (slower).")
                kwargs = torch_load_kwargs("cpu")
                kwargs["local_files_only"] = True
                try:
                    self._model = Qwen3TTSModel.from_pretrained(str(model_path), **kwargs)
                    self._device = "cpu"
                except Exception as retry_exc:
                    raise TTSError(CLONE_MODEL_LOAD_FAILED, "VOICE_CLONE_MODEL_LOAD_FAILED") from retry_exc
            else:
                if mapped.code not in (
                    "TTS_OUT_OF_MEMORY",
                    "TTS_TIMEOUT",
                    "package_missing",
                    "VOICE_CLONE_MODEL_UNAVAILABLE",
                ):
                    raise TTSError(CLONE_MODEL_LOAD_FAILED, "VOICE_CLONE_MODEL_LOAD_FAILED") from exc
                raise mapped from exc
        self._model_path = model_path
        self._load_time = time.perf_counter() - t0
        self._emit("[TTS] Model ready")
        self._emit(f"[TTS] Device: {self._device}")
        self._emit(f"[TTS] Model: {CLONE_MODEL_ID}")

    def _wav_for_model(self, ref_audio: Path) -> tuple[Path, Optional[Path]]:
        if ref_audio.suffix.lower() == ".wav":
            return ref_audio, None
        import tempfile

        handle, tmp_name = tempfile.mkstemp(prefix="qwen_ref_", suffix=".wav")
        os.close(handle)
        tmp_wav = Path(tmp_name)
        return convert_reference_to_wav(ref_audio, tmp_wav), tmp_wav

    def create_voice_clone_prompt_items(self, ref_audio: Path, ref_text: str):
        transcript = (ref_text or "").strip()
        if not transcript:
            raise TTSError(REFERENCE_TEXT_REQUIRED, "REFERENCE_TEXT_REQUIRED")
        self.ensure_loaded()
        tmp_wav = None
        try:
            wav_for_model, tmp_wav = self._wav_for_model(ref_audio)
            return self._model.create_voice_clone_prompt(
                ref_audio=str(wav_for_model.resolve()),
                ref_text=transcript,
                x_vector_only_mode=False,
            )
        except TTSError:
            raise
        except Exception as exc:
            mapped = map_exception(exc)
            if mapped.code in ("generation_failure", "VOICE_CLONE_GENERATION_FAILED"):
                raise TTSError(
                    "Reference audio could not be processed.\n\n"
                    "Check that the recording is clear speech in a supported format.",
                    "VOICE_CLONE_GENERATION_FAILED",
                ) from exc
            raise mapped from exc
        finally:
            if tmp_wav is not None:
                try:
                    tmp_wav.unlink(missing_ok=True)
                except OSError:
                    pass

    def save_voice_prompt(self, items, prompt_path: Path) -> None:
        import torch

        prompt_path = Path(prompt_path)
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(_prompt_items_to_payload(items), str(prompt_path))

    def load_voice_prompt(self, prompt_path: Path):
        return _load_prompt_items(Path(prompt_path))

    def build_voice_prompt(self, ref_audio: Path | str, ref_text: str, prompt_path: Path) -> None:
        info = validate_reference(ref_audio)
        transcript = (ref_text or "").strip()
        if not transcript:
            raise TTSError(REFERENCE_TEXT_REQUIRED, "REFERENCE_TEXT_REQUIRED")
        self._emit("[TTS] Creating reusable voice profile...")
        items = self.create_voice_clone_prompt_items(info.path, transcript)
        self.save_voice_prompt(items, prompt_path)
        self._emit("[TTS] Voice profile saved")

    def generate_clone(
        self,
        text: str,
        output_path: Path,
        *,
        ref_audio: Optional[Path | str] = None,
        ref_text: Optional[str] = None,
        voice_prompt_path: Optional[Path | str] = None,
        language: str = DEFAULT_LANGUAGE,
    ) -> TTSResult:
        spoken = validate_text(text)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            self.ensure_loaded()
        except TTSError:
            raise
        except Exception as exc:
            raise TTSError(CLONE_MODEL_LOAD_FAILED, "VOICE_CLONE_MODEL_LOAD_FAILED") from exc

        if voice_prompt_path:
            prompt = self.load_voice_prompt(Path(voice_prompt_path))
            x_vector_only = False
        else:
            if ref_audio is None:
                raise TTSError(
                    "No saved voice profile was provided for narration.",
                    "VOICE_PROFILE_MISSING",
                )
            info = validate_reference(ref_audio)
            transcript = (ref_text or "").strip()
            if not transcript:
                raise TTSError(REFERENCE_TEXT_REQUIRED, "REFERENCE_TEXT_REQUIRED")
            prompt = self.create_voice_clone_prompt_items(info.path, transcript)
            x_vector_only = False

        self._emit("[TTS] Generating narration...")
        t0 = time.perf_counter()
        chunk_chars = narration_chunk_chars_for_device(self._device)
        chunks = split_narration_chunks(spoken, max_chars=chunk_chars)
        n_chunks = max(1, len(chunks))
        self._emit(
            f"[TTS] Chunk size {chunk_chars} chars on {self._device or 'unknown'} "
            f"→ {n_chunks} part(s)"
        )
        self._emit(f"[TTS] Progress 0% (0/{n_chunks})")
        try:
            import numpy as np

            pieces = []
            sr = 24000
            for idx, chunk in enumerate(chunks, start=1):
                self._emit(f"[TTS] Generating part {idx}/{n_chunks}…")
                wavs, sr = self._model.generate_voice_clone(
                    text=chunk,
                    language=language or DEFAULT_LANGUAGE,
                    voice_clone_prompt=prompt,
                    x_vector_only_mode=x_vector_only,
                )
                if wavs is None or len(wavs) == 0:
                    raise TTSError(
                        "Voice cloning failed.\n\nThe Qwen 1.7B Base model returned no audio.",
                        "VOICE_CLONE_GENERATION_FAILED",
                    )
                pieces.append(np.asarray(wavs[0], dtype=np.float32).reshape(-1))
                pct = int(round(100.0 * idx / float(n_chunks)))
                self._emit(f"[TTS] Progress {pct}% ({idx}/{n_chunks})")
            combined = pieces[0] if len(pieces) == 1 else np.concatenate(pieces)
        except TTSError:
            raise
        except Exception as exc:
            mapped = map_exception(exc)
            if mapped.code in ("generation_failure", "VOICE_CLONE_GENERATION_FAILED"):
                raise TTSError(
                    "Voice cloning failed.\n\nThe Qwen 1.7B Base model could not generate audio.",
                    "VOICE_CLONE_GENERATION_FAILED",
                ) from exc
            raise mapped from exc
        gen_s = time.perf_counter() - t0

        try:
            _write_audio(output_path, combined, int(sr))
        except TTSError:
            raise
        except Exception as exc:
            raise TTSError(
                f"Qwen3-TTS could not write the narration file: {exc}",
                "VOICE_CLONE_GENERATION_FAILED",
            ) from exc

        if not output_path.is_file() or output_path.stat().st_size < 64:
            raise TTSError(
                "Qwen3-TTS finished but the output audio file is missing or empty.",
                "output_missing",
            )

        duration, sample_rate = _probe_audio(output_path)
        if duration <= 0.05:
            raise TTSError(
                "Qwen3-TTS wrote an audio file that is too short to be valid narration.",
                "invalid_audio",
            )

        self._emit("[TTS] Generated audio")
        mm, ss = divmod(int(round(duration)), 60)
        hh, mm = divmod(mm, 60)
        self._emit(f"[TTS] Duration: {hh:02d}:{mm:02d}:{ss:02d}")
        self._emit(f"[TTS] Saved: {output_path}")

        return TTSResult(
            path=output_path,
            duration_seconds=duration,
            sample_rate=sample_rate,
            format=output_path.suffix.lstrip(".").lower() or "wav",
            provider="qwen3-tts",
            voice=str(voice_prompt_path or ref_audio or "clone"),
            generation_time_seconds=gen_s,
            load_time_seconds=self._load_time,
            device=self._device,
            model=CLONE_MODEL_ID,
            local=True,
        )

    def shutdown(self) -> None:
        self._unload()
