"""Optional hardware acceleration (GPU) with mandatory CPU fallback."""

from .accel import (
    HardwareCaps,
    clear_caps_cache,
    format_accel_report,
    get_capabilities,
    get_performance_mode,
    set_performance_mode_override,
    video_encode_argv,
    whisper_device_and_compute,
)

__all__ = [
    "HardwareCaps",
    "clear_caps_cache",
    "format_accel_report",
    "get_capabilities",
    "get_performance_mode",
    "set_performance_mode_override",
    "video_encode_argv",
    "whisper_device_and_compute",
]
