"""
Central hardware capability detection for Semantic YT Studio.

GPU acceleration is OPTIONAL. Every path must fall back to the existing CPU
pipeline when drivers, CUDA, or hardware encoders are missing or fail.

Deferred (not in this layer yet — encode + Whisper first):
- GPU decode (NVDEC / QSV / VideoToolbox decode)
- GPU scaling filters (scale_cuda / scale_qsv)
Those need measurable wins without CPU↔GPU thrashing; keep CPU filters for now.
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from providers import hidden_subprocess as _hs

# auto | gpu | cpu — gpu still falls back when hardware is unusable
_VALID_MODES = frozenset({"auto", "gpu", "cpu"})
_mode_override: Optional[str] = None
_caps_lock = threading.Lock()
_caps_cache: dict[str, "HardwareCaps"] = {}

# Prefer quality close to libx264 -crf 20 / veryfast.
_CPU_ENCODE = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
_NVENC_ENCODE = [
    "-c:v", "h264_nvenc",
    "-preset", "p4",
    "-rc", "vbr",
    "-cq", "20",
    "-b:v", "0",
    "-maxrate", "12M",
    "-bufsize", "24M",
]
_AMF_ENCODE = [
    "-c:v", "h264_amf",
    "-quality", "balanced",
    "-rc", "cqp",
    "-qp_i", "20",
    "-qp_p", "22",
]
_QSV_ENCODE = [
    "-c:v", "h264_qsv",
    "-global_quality", "22",
    "-look_ahead", "1",
]
_VIDEOTOOLBOX_ENCODE = [
    "-c:v", "h264_videotoolbox",
    "-b:v", "8M",
    "-allow_sw", "1",
]


@dataclass
class HardwareCaps:
    performance_mode: str = "auto"
    gpu_vendor: str = ""
    gpu_name: str = ""
    gpu_available: bool = False
    cuda_available: bool = False
    nvenc_available: bool = False
    amf_available: bool = False
    qsv_available: bool = False
    videotoolbox_available: bool = False
    whisper_cuda_available: bool = False
    preferred_encoder: str = "libx264"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    notes: List[str] = field(default_factory=list)
    ffmpeg_path: str = "ffmpeg"

    @property
    def using_gpu_encode(self) -> bool:
        return self.preferred_encoder != "libx264"

    @property
    def using_gpu_whisper(self) -> bool:
        return self.whisper_device == "cuda"


def set_performance_mode_override(mode: Optional[str]) -> None:
    """Tests / one-shot CLI override. Pass None to clear."""
    global _mode_override
    if mode is None:
        _mode_override = None
        return
    m = str(mode).strip().lower()
    _mode_override = m if m in _VALID_MODES else "auto"
    clear_caps_cache()


def clear_caps_cache() -> None:
    with _caps_lock:
        _caps_cache.clear()


def get_performance_mode() -> str:
    if _mode_override in _VALID_MODES:
        return _mode_override  # type: ignore[return-value]
    env = (os.environ.get("SEMANTIC_PERF_MODE") or "").strip().lower()
    if env in _VALID_MODES:
        return env
    try:
        # Same settings file the GUI uses — avoid importing app.py (heavy).
        import json
        from pathlib import Path

        if getattr(sys, "frozen", False):
            base = Path.home() / ".videogen"
        else:
            base = Path(__file__).resolve().parent.parent
        path = base / "settings.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            m = str(data.get("performance_mode") or "auto").strip().lower()
            if m in _VALID_MODES:
                return m
    except Exception:
        pass
    return "auto"


def find_ffmpeg() -> str:
    which = shutil.which("ffmpeg")
    if which:
        return which
    name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    try:
        from pathlib import Path

        for candidate in (
            Path(__file__).resolve().parent.parent / "bin" / name,
            Path.cwd() / "bin" / name,
        ):
            if candidate.is_file():
                return str(candidate.resolve())
    except Exception:
        pass
    return name


def _run_ffmpeg(args: Sequence[str], *, timeout: float = 12.0) -> Tuple[int, str]:
    ffmpeg = find_ffmpeg()
    try:
        proc = _hs.run(
            [ffmpeg, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (proc.stderr or "") + (proc.stdout or "")
        return int(proc.returncode), out
    except Exception as exc:
        return 1, str(exc)


def _listed_encoders() -> set[str]:
    code, out = _run_ffmpeg(["-hide_banner", "-encoders"], timeout=15.0)
    if code != 0:
        return set()
    found: set[str] = set()
    for line in out.splitlines():
        # e.g. " V..... h264_nvenc           NVIDIA NVENC H.264 encoder"
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0].startswith("V"):
            found.add(parts[1])
        elif len(parts) >= 1 and parts[0] in (
            "h264_nvenc", "h264_amf", "h264_qsv", "h264_videotoolbox", "libx264",
        ):
            found.add(parts[0])
    return found


def _smoke_test_encoder(encoder: str, extra: Sequence[str]) -> Tuple[bool, str]:
    """Prove the encoder actually initializes (driver + ffmpeg), not just listed."""
    cmd = [
        "-hide_banner",
        "-loglevel", "error",
        "-f", "lavfi",
        "-i", "color=c=black:s=128x72:d=0.2",
        "-frames:v", "1",
        *extra,
        "-pix_fmt", "yuv420p",
        "-an",
        "-f", "null",
        "-",
    ]
    code, out = _run_ffmpeg(cmd, timeout=20.0)
    if code == 0:
        return True, ""
    tail = (out or "").strip().replace("\n", " ")[-240:]
    return False, tail or f"encoder {encoder} smoke test failed (exit {code})"


def _probe_cuda_whisper() -> Tuple[bool, str]:
    """Return (available, note) for the CTranslate2 CUDA BACKEND. Never raises.

    `available` must mean "Whisper can actually run on CUDA", not "an NVIDIA
    driver is installed". The old probe used get_cuda_device_count() alone,
    which only needs the driver's nvcuda.dll — so on a machine missing the CUDA
    math libraries it reported CUDA available, the UI showed CUDA, and
    transcription then silently fell back to CPU at model load.

    Three tiers, cheapest first; each is a strictly stronger claim:
      0. a CUDA device exists at all (driver)
      1. THIS CTranslate2 build has a CUDA backend with compute types
      2. a real allocation on the device succeeds (touches the CUDA runtime)

    Tier 2 still cannot prove cuBLAS/cuDNN load — those are resolved lazily at
    model construction — so a CUDA claim here remains provisional until the
    first successful CUDA Whisper load. The caller must not upgrade it.
    """
    try:
        from ctranslate2 import get_cuda_device_count  # type: ignore

        if int(get_cuda_device_count()) <= 0:
            return False, "no CUDA device visible to ctranslate2"
    except Exception as exc:
        return False, f"CUDA probe failed: {exc}"

    try:
        from ctranslate2 import get_supported_compute_types  # type: ignore

        types = set(get_supported_compute_types("cuda") or [])
        if not types:
            return False, "ctranslate2 has no CUDA compute types"
    except Exception as exc:
        return False, f"ctranslate2 CUDA backend unavailable: {exc}"

    try:
        import numpy as np  # ctranslate2 dependency — always present
        from ctranslate2 import Device, StorageView  # type: ignore

        StorageView.from_array(np.zeros((2, 2), dtype=np.float32)).to_device(Device.cuda)
    except Exception as exc:
        return False, f"CUDA runtime not usable: {str(exc)[:120]}"

    return True, f"CUDA backend responded; compute types: {sorted(types)[:6]}"


def _guess_gpu_label(encoders: set[str], cuda_ok: bool) -> Tuple[str, str, bool]:
    """Best-effort vendor/name without requiring nvidia-smi."""
    if "h264_nvenc" in encoders or cuda_ok:
        return "NVIDIA", "NVIDIA GPU (NVENC/CUDA probe)", True
    if "h264_amf" in encoders:
        return "AMD", "AMD GPU (AMF probe)", True
    if "h264_qsv" in encoders:
        return "Intel", "Intel GPU (QSV probe)", True
    if "h264_videotoolbox" in encoders and sys.platform == "darwin":
        return "Apple", "Apple Silicon / VideoToolbox", True
    return "", "unavailable", False


def get_capabilities(
    performance_mode: Optional[str] = None,
    *,
    force_refresh: bool = False,
) -> HardwareCaps:
    mode = (performance_mode or get_performance_mode()).strip().lower()
    if mode not in _VALID_MODES:
        mode = "auto"

    with _caps_lock:
        if not force_refresh and mode in _caps_cache:
            return _caps_cache[mode]

    caps = HardwareCaps(performance_mode=mode, ffmpeg_path=find_ffmpeg())
    notes: List[str] = []

    if mode == "cpu":
        notes.append("Performance mode=CPU — forcing libx264 + CPU Whisper")
        caps.notes = notes
        caps.preferred_encoder = "libx264"
        caps.whisper_device = "cpu"
        caps.whisper_compute_type = "int8"
        with _caps_lock:
            _caps_cache[mode] = caps
        return caps

    listed = _listed_encoders()
    if not listed:
        notes.append("Could not list ffmpeg encoders — using CPU encode")

    cuda_ok, cuda_note = _probe_cuda_whisper()
    caps.cuda_available = cuda_ok
    caps.whisper_cuda_available = cuda_ok
    notes.append(cuda_note)

    # Smoke-test each candidate only if listed (or on macOS try VT if listed).
    def try_encoder(name: str, argv: Sequence[str]) -> bool:
        if name not in listed and name != "libx264":
            notes.append(f"{name}: not present in bundled ffmpeg")
            return False
        ok, err = _smoke_test_encoder(name, argv)
        if ok:
            notes.append(f"{name}: smoke test OK")
            return True
        notes.append(f"{name}: unavailable ({err})")
        return False

    caps.nvenc_available = try_encoder("h264_nvenc", _NVENC_ENCODE)
    caps.amf_available = try_encoder("h264_amf", _AMF_ENCODE)
    caps.qsv_available = try_encoder("h264_qsv", _QSV_ENCODE)
    if sys.platform == "darwin":
        caps.videotoolbox_available = try_encoder(
            "h264_videotoolbox", _VIDEOTOOLBOX_ENCODE
        )
    else:
        caps.videotoolbox_available = False

    vendor, gname, gavail = _guess_gpu_label(listed, cuda_ok)
    # Prefer labels from successful smoke tests.
    if caps.nvenc_available:
        vendor, gname, gavail = "NVIDIA", "NVIDIA (NVENC verified)", True
    elif caps.amf_available:
        vendor, gname, gavail = "AMD", "AMD (AMF verified)", True
    elif caps.qsv_available:
        vendor, gname, gavail = "Intel", "Intel (QSV verified)", True
    elif caps.videotoolbox_available:
        vendor, gname, gavail = "Apple", "Apple VideoToolbox verified", True
    caps.gpu_vendor = vendor
    caps.gpu_name = gname
    caps.gpu_available = gavail

    # Encoder preference order.
    prefer_gpu = mode in ("auto", "gpu")
    encoder = "libx264"
    if prefer_gpu:
        if caps.nvenc_available:
            encoder = "h264_nvenc"
        elif caps.amf_available:
            encoder = "h264_amf"
        elif caps.qsv_available:
            encoder = "h264_qsv"
        elif caps.videotoolbox_available:
            encoder = "h264_videotoolbox"
        elif mode == "gpu":
            notes.append("GPU mode requested but no hardware encoder works — using libx264")
    caps.preferred_encoder = encoder

    # Whisper device.
    if prefer_gpu and cuda_ok:
        caps.whisper_device = "cuda"
        caps.whisper_compute_type = "float16"
    else:
        caps.whisper_device = "cpu"
        caps.whisper_compute_type = "int8"
        if mode == "gpu" and not cuda_ok:
            notes.append("GPU mode requested but CUDA unavailable — Whisper on CPU")

    caps.notes = notes
    with _caps_lock:
        _caps_cache[mode] = caps
    return caps


def video_encode_argv(
    performance_mode: Optional[str] = None,
    *,
    force_cpu: bool = False,
) -> List[str]:
    if force_cpu:
        return list(_CPU_ENCODE)
    caps = get_capabilities(performance_mode)
    enc = caps.preferred_encoder
    if enc == "h264_nvenc":
        return list(_NVENC_ENCODE)
    if enc == "h264_amf":
        return list(_AMF_ENCODE)
    if enc == "h264_qsv":
        return list(_QSV_ENCODE)
    if enc == "h264_videotoolbox":
        return list(_VIDEOTOOLBOX_ENCODE)
    return list(_CPU_ENCODE)


def whisper_device_and_compute(
    performance_mode: Optional[str] = None,
) -> Tuple[str, str, str]:
    """Return (device, compute_type, human_label)."""
    caps = get_capabilities(performance_mode)
    if caps.whisper_device == "cuda":
        return "cuda", caps.whisper_compute_type, "CUDA"
    return "cpu", "int8", "CPU"


_ENCODER_LABELS = {
    "h264_nvenc": "NVIDIA NVENC (GPU)",
    "h264_amf": "AMD AMF (GPU)",
    "h264_qsv": "Intel QuickSync (GPU)",
    "h264_videotoolbox": "Apple VideoToolbox (GPU)",
    "libx264": "CPU (libx264)",
}


# The ONLY place the real Whisper backend is known for certain. No cheap probe
# can reach it: CTranslate2's cuBLAS/cuDNN are resolved lazily at model load,
# and Encoder/Generator both require a model file, so nothing model-free forces
# them to load (verified against ctranslate2 4.8.1). The probe is therefore a
# PREDICTION; this records the OUTCOME so the UI never claims CUDA that the
# model did not actually achieve.
_verified_whisper_backend: Optional[Tuple[str, str]] = None


def record_whisper_backend(backend: str, compute_type: str = "") -> None:
    """Called by the transcription path after the model actually loaded."""
    global _verified_whisper_backend
    b = (backend or "").strip().upper()
    if b in ("CUDA", "CPU"):
        _verified_whisper_backend = (b, (compute_type or "").strip())


def verified_whisper_backend() -> Optional[Tuple[str, str]]:
    return _verified_whisper_backend


def video_encoder_label(caps: Optional["HardwareCaps"] = None) -> str:
    """What actually encodes video. Says nothing about Whisper."""
    caps = caps or get_capabilities()
    enc = caps.preferred_encoder or "libx264"
    return _ENCODER_LABELS.get(enc, enc)


def whisper_backend_label(caps: Optional["HardwareCaps"] = None) -> str:
    """What actually transcribes. Says nothing about video encoding.

    Only claims CUDA when the CUDA backend probe passed; otherwise it names CPU
    explicitly rather than leaving the user to infer it from a GPU line.
    """
    # Observed truth beats prediction. Once a real model load has happened this
    # is the ONLY thing reported, so a missing CUDA runtime can never surface
    # as "Whisper: CUDA" regardless of which DLL was absent.
    observed = verified_whisper_backend()
    if observed is not None:
        backend, ctype = observed
        if backend == "CUDA":
            return f"CUDA ({ctype})" if ctype else "CUDA"
        return f"CPU ({ctype})" if ctype else "CPU (int8)"

    caps = caps or get_capabilities()
    if caps.using_gpu_whisper and caps.cuda_available:
        # Not yet proven — say so rather than implying verified acceleration.
        return f"CUDA expected ({caps.whisper_compute_type}) — unverified until first transcription"
    return "CPU (int8)"


def format_accel_report(caps: Optional[HardwareCaps] = None) -> str:
    caps = caps or get_capabilities()
    lines = [
        "Hardware Acceleration",
        "---------------------",
        f"Performance Mode: {caps.performance_mode.upper()}",
        # Two INDEPENDENT capabilities. Video encoding and Whisper use entirely
        # different backends: a Mac has GPU video encode (VideoToolbox) with
        # CPU Whisper, and a CUDA box can have GPU Whisper with CPU encoding.
        # A single "GPU: available" line conflated them and let the app imply
        # GPU transcription that was not happening.
        f"Video Encoder: {video_encoder_label(caps)}",
        f"Whisper:       {whisper_backend_label(caps)}",
        "",
        f"Detected GPU (video): {caps.gpu_name or 'none'}",
        f"  CUDA backend (Whisper): {'available' if caps.cuda_available else 'unavailable'}",
        f"  NVENC: {'available' if caps.nvenc_available else 'unavailable'}",
        f"  AMF: {'available' if caps.amf_available else 'unavailable'}",
        f"  QSV: {'available' if caps.qsv_available else 'unavailable'}",
        f"  VideoToolbox: {'available' if caps.videotoolbox_available else 'unavailable'}",
        f"ffmpeg: {caps.ffmpeg_path}",
    ]
    if caps.notes:
        lines.append("Notes:")
        for n in caps.notes[:12]:
            lines.append(f"  - {n}")
    return "\n".join(lines)
