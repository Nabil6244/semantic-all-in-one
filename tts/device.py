"""Local device detection for Qwen3-TTS. Never assumes CUDA."""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceInfo:
    name: str  # cuda | mps | cpu
    detail: str
    apple_silicon: bool = False


def is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() in ("arm64", "aarch64")


def detect_device() -> DeviceInfo:
    apple = is_apple_silicon()
    try:
        import torch
    except ImportError:
        extra = " Apple Silicon is present;" if apple else ""
        return DeviceInfo(
            "cpu",
            f"PyTorch is not available in this process.{extra} "
            "install qwen-tts in .venv-qwen to use the local model.",
            apple_silicon=apple,
        )

    if torch.cuda.is_available():
        return DeviceInfo("cuda", "NVIDIA CUDA is available.", apple_silicon=apple)

    mps_ok = bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
    if mps_ok:
        return DeviceInfo(
            "mps",
            "Apple Metal (MPS) is available.",
            apple_silicon=apple,
        )
    if apple:
        return DeviceInfo(
            "cpu",
            MPS_CPU_FALLBACK,
            apple_silicon=True,
        )
    return DeviceInfo("cpu", "Using CPU. Generation may be slower.", apple_silicon=False)


MPS_CPU_FALLBACK = (
    "Apple Silicon was detected but MPS is not available in this PyTorch build. "
    "Falling back to CPU — generation may be slower."
)


def torch_load_kwargs(device: str) -> dict:
    """HuggingFace from_pretrained kwargs. No flash-attn (unsupported on this Mac)."""
    import torch

    if device == "cuda":
        return {"device_map": "cuda:0", "dtype": torch.bfloat16}
    if device == "mps":
        return {"device_map": "mps", "dtype": torch.float16}
    return {"device_map": "cpu", "dtype": torch.float32}
