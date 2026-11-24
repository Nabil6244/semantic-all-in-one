"""Whisper on the Apple GPU (mlx-whisper) when this Mac has an Apple chip and the package, else None so the caller
keeps its faster-whisper CPU path (Windows, Intel Macs, the exe without mlx).

    segs, info = whisper_backend.transcribe_gpu(audio, "small", initial_prompt=..., condition_on_previous_text=False)
    if segs is None: ... use faster-whisper as before

The segments look like faster-whisper's (seg.start, seg.end, seg.text, seg.words[i].word/.start/.end), so callers read
them the same way. VG_WHISPER=cpu turns the GPU path off.
"""
from __future__ import annotations

import os
import platform
import sys
import threading
from types import SimpleNamespace
from typing import Any, Optional, Tuple

# faster-whisper size -> the same model converted for mlx (mlx-community on Hugging Face, downloaded on first use)
MLX_REPOS = {
    "tiny": "mlx-community/whisper-tiny-mlx", "tiny.en": "mlx-community/whisper-tiny.en-mlx",
    "base": "mlx-community/whisper-base-mlx", "base.en": "mlx-community/whisper-base.en-mlx",
    "small": "mlx-community/whisper-small-mlx", "small.en": "mlx-community/whisper-small.en-mlx",
    "medium": "mlx-community/whisper-medium-mlx", "medium.en": "mlx-community/whisper-medium.en-mlx",
    "large-v2": "mlx-community/whisper-large-v2-mlx", "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large": "mlx-community/whisper-large-v3-mlx", "turbo": "mlx-community/whisper-large-v3-turbo",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}
_LOCK = threading.Lock()     # one GPU transcription at a time
_STATE = {"failed": False, "mod": None, "tried": False}


def _mlx():
    """mlx_whisper, imported once per process and kept here: importing mlx's native part a second time (after something
    dropped it from sys.modules, as unittest's patch.dict does) aborts Python outright."""
    if not _STATE["tried"]:
        _STATE["tried"] = True
        try:
            import mlx_whisper
            _STATE["mod"] = mlx_whisper
        except Exception:  # noqa: BLE001 - no mlx: the CPU path
            _STATE["mod"] = None
    return _STATE["mod"]


def gpu_available() -> bool:
    if _STATE["failed"] or os.environ.get("VG_WHISPER", "").lower() == "cpu":
        return False
    if sys.platform != "darwin" or platform.machine() != "arm64":
        return False
    return _mlx() is not None


def transcribe_gpu(audio: Any, model_size: str = "small", log=print, **opts) -> Tuple[Optional[list], Optional[Any]]:
    """(segments, info) from mlx-whisper, or (None, None) when the GPU path isn't there or fails (the caller then uses
    the CPU). opts: initial_prompt, condition_on_previous_text, language, hallucination_silence_threshold."""
    if not gpu_available() or model_size not in MLX_REPOS:
        return None, None
    try:
        mlx_whisper = _mlx()
        if isinstance(audio, (str, os.PathLike)):
            # decoded here (PyAV, as faster-whisper does): mlx's own reader needs an ffmpeg on PATH, which the app may not have
            from faster_whisper import decode_audio
            audio = decode_audio(str(audio), sampling_rate=16000)
        with _LOCK:
            out = mlx_whisper.transcribe(audio, path_or_hf_repo=MLX_REPOS[model_size], word_timestamps=True,
                                         verbose=None, **{k: v for k, v in opts.items() if v is not None})
    except Exception as exc:  # noqa: BLE001 - a bad install/download must not stop the video: CPU instead
        _STATE["failed"] = True
        log(f"Whisper on the GPU failed ({type(exc).__name__}: {exc}); using the CPU")
        return None, None
    segs = []
    for s in out.get("segments") or []:
        words = [SimpleNamespace(word=w.get("word", ""), start=float(w.get("start", 0.0)), end=float(w.get("end", 0.0)),
                                 probability=float(w.get("probability", 0.0))) for w in s.get("words") or []]
        segs.append(SimpleNamespace(start=float(s.get("start", 0.0)), end=float(s.get("end", 0.0)),
                                    text=s.get("text", ""), words=words))
    dur = len(audio) / 16000.0
    return segs, SimpleNamespace(duration=dur, language=out.get("language", ""))


_CPU: dict = {}


def transcribe(audio: Any, model_size: str = "small", *, device: str = "cpu", compute_type: str = "int8", log=print,
               **kw) -> Tuple[Any, Any]:
    """Drop-in for WhisperModel(model_size).transcribe(audio, **kw): the Apple GPU when it can, else faster-whisper on
    the CPU with exactly the options given (its model kept for the next call). Word timestamps are on by default."""
    kw.setdefault("word_timestamps", True)
    if kw["word_timestamps"]:
        gpu_kw = {k: kw[k] for k in ("language", "initial_prompt", "condition_on_previous_text") if k in kw}
        if kw.get("vad_filter"):
            gpu_kw["hallucination_silence_threshold"] = 2.0     # mlx has no VAD: skip what it "hears" in long silences
        segs, info = transcribe_gpu(audio, model_size, log=log, **gpu_kw)
        if segs is not None:
            return segs, info
    from faster_whisper import WhisperModel
    key = (model_size, device, compute_type)
    if key not in _CPU:
        _CPU.clear()
        _CPU[key] = WhisperModel(model_size, device=device, compute_type=compute_type)
    return _CPU[key].transcribe(audio if not isinstance(audio, os.PathLike) else str(audio), **kw)

