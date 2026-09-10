"""Platform-aware resource governor for Semantic YT Studio.

Central policy for concurrency across downloads, FFmpeg, Flow/Chrome,
Whisper, and processing. Subsystems should request capacity here instead
of hardcoding unlimited fan-out.

This module is intentionally dependency-light (stdlib only) so it works
in packaged builds without psutil.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


def _env_int(name: str, default: int, *, lo: int, hi: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return max(lo, min(hi, default))
    try:
        return max(lo, min(hi, int(raw)))
    except ValueError:
        return max(lo, min(hi, default))


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class PlatformProfile:
    """Static host facts (platform ≠ architecture)."""

    system: str  # Darwin | Windows | Linux
    architecture: str  # arm64 | x86_64 | AMD64 | …
    cpu_count: int
    ram_total_bytes: int
    ram_available_bytes: int
    ffmpeg_path: str
    hwaccels: tuple[str, ...] = ()
    encoders: tuple[str, ...] = ()
    is_apple_silicon: bool = False
    is_windows: bool = False
    is_macos: bool = False


@dataclass
class ConcurrencyBudget:
    """Resolved worker caps for the current host pressure."""

    download: int = 4
    ffmpeg: int = 2
    flow_accounts: int = 10
    whisper: int = 1
    processing: int = 4
    reason: str = ""


@dataclass
class ResourceSnapshot:
    platform: PlatformProfile
    budget: ConcurrencyBudget
    active: Dict[str, int] = field(default_factory=dict)
    bottleneck: str = "none"
    notes: list[str] = field(default_factory=list)


class ResourceGovernor:
    """Singleton-ish governor. Thread-safe lease tracking."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._leases: Dict[str, int] = {
            "download": 0,
            "ffmpeg": 0,
            "flow": 0,
            "whisper": 0,
            "processing": 0,
        }
        self._profile: Optional[PlatformProfile] = None
        self._ffmpeg_probed = False
        self._hwaccels: tuple[str, ...] = ()
        self._encoders: tuple[str, ...] = ()

    # ------------------------------------------------------------------ profile
    def refresh_profile(self, *, ffmpeg_path: Optional[str] = None) -> PlatformProfile:
        system = platform.system()
        arch = platform.machine() or ""
        cpu = os.cpu_count() or 2
        total, avail = _ram_bytes()
        ff = ffmpeg_path or _find_ffmpeg()
        if not self._ffmpeg_probed and ff:
            self._hwaccels, self._encoders = _probe_ffmpeg_caps(ff)
            self._ffmpeg_probed = True
        profile = PlatformProfile(
            system=system,
            architecture=arch,
            cpu_count=max(1, cpu),
            ram_total_bytes=total,
            ram_available_bytes=avail,
            ffmpeg_path=ff,
            hwaccels=self._hwaccels,
            encoders=self._encoders,
            is_apple_silicon=system == "Darwin" and arch.lower() in ("arm64", "aarch64"),
            is_windows=system == "Windows",
            is_macos=system == "Darwin",
        )
        with self._lock:
            self._profile = profile
        return profile

    def profile(self) -> PlatformProfile:
        with self._lock:
            if self._profile is None:
                return self.refresh_profile()
            return self._profile

    # ------------------------------------------------------------------ budget
    def budget(self, *, long_form: bool = False) -> ConcurrencyBudget:
        """Compute adaptive caps from host + current leases + memory pressure."""
        p = self.profile()
        # Refresh available RAM cheaply each call.
        _, avail = _ram_bytes()
        total = max(p.ram_total_bytes, 1)
        avail_ratio = avail / total if total else 0.5
        mem_gb = total / (1024**3)
        pressure = avail_ratio < 0.18 or avail < 1.5 * (1024**3)

        # Base defaults — platform-aware, never unbounded.
        if p.is_windows:
            download = 3 if mem_gb < 12 else 4
            ffmpeg = 1 if mem_gb < 12 or pressure else 2
            flow = 8 if mem_gb < 16 or pressure else 10
            processing = 3 if pressure else min(4, max(2, p.cpu_count // 2))
        elif p.is_apple_silicon:
            download = 4 if not pressure else 3
            ffmpeg = 2 if not pressure else 1
            flow = 10 if not pressure else 8
            processing = min(4, max(2, p.cpu_count // 2))
        else:  # Intel macOS / Linux
            download = 3 if pressure else 4
            ffmpeg = 1 if pressure else 2
            flow = 8 if pressure else 10
            processing = min(4, max(2, p.cpu_count // 2))

        if long_form or mem_gb < 8:
            # Prioritize sustained throughput / stability for ~40min docs.
            download = min(download, 3)
            ffmpeg = min(ffmpeg, 1)
            flow = min(flow, 8)
            processing = min(processing, 3)

        # Env overrides (ops / benchmarks).
        download = _env_int("VIDEOGEN_DOWNLOAD_WORKERS", download, lo=1, hi=8)
        ffmpeg = _env_int("VIDEOGEN_FFMPEG_WORKERS", ffmpeg, lo=1, hi=4)
        flow = _env_int("FLOW_MAX_PARALLEL_ACCOUNTS", flow, lo=1, hi=10)
        processing = _env_int("VIDEOGEN_PROCESS_WORKERS", processing, lo=1, hi=8)
        whisper = _env_int("VIDEOGEN_WHISPER_WORKERS", 1, lo=1, hi=2)

        reason_parts = [
            f"{p.system}/{p.architecture}",
            f"cpu={p.cpu_count}",
            f"ram={mem_gb:.0f}G",
            f"avail_ratio={avail_ratio:.2f}",
        ]
        if pressure:
            reason_parts.append("memory_pressure")
        if long_form:
            reason_parts.append("long_form")

        return ConcurrencyBudget(
            download=download,
            ffmpeg=ffmpeg,
            flow_accounts=flow,
            whisper=whisper,
            processing=processing,
            reason=", ".join(reason_parts),
        )

    def recommend_download_workers(self, *, long_form: bool = False) -> int:
        return self.budget(long_form=long_form).download

    def recommend_ffmpeg_workers(self, *, long_form: bool = False) -> int:
        return self.budget(long_form=long_form).ffmpeg

    def recommend_flow_workers(self, *, long_form: bool = False) -> int:
        return self.budget(long_form=long_form).flow_accounts

    def recommend_processing_workers(self, *, long_form: bool = False) -> int:
        return self.budget(long_form=long_form).processing

    # ------------------------------------------------------------------ leases
    def try_acquire(self, kind: str, n: int = 1) -> bool:
        kind = _norm_kind(kind)
        with self._lock:
            budget = self.budget()
            cap = _cap_for(budget, kind)
            if self._leases.get(kind, 0) + n > cap:
                return False
            self._leases[kind] = self._leases.get(kind, 0) + n
            return True

    def acquire(self, kind: str, n: int = 1, *, block: bool = False, timeout: float = 30.0) -> bool:
        """Non-blocking by default; optional short wait for a free slot."""
        if self.try_acquire(kind, n):
            return True
        if not block:
            return False
        import time

        deadline = time.monotonic() + max(0.0, timeout)
        while time.monotonic() < deadline:
            if self.try_acquire(kind, n):
                return True
            time.sleep(0.05)
        return False

    def release(self, kind: str, n: int = 1) -> None:
        kind = _norm_kind(kind)
        with self._lock:
            self._leases[kind] = max(0, self._leases.get(kind, 0) - n)

    def active_counts(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._leases)

    def snapshot(self, *, long_form: bool = False) -> ResourceSnapshot:
        p = self.profile()
        # Refresh RAM
        total, avail = _ram_bytes()
        p = PlatformProfile(
            system=p.system,
            architecture=p.architecture,
            cpu_count=p.cpu_count,
            ram_total_bytes=total,
            ram_available_bytes=avail,
            ffmpeg_path=p.ffmpeg_path,
            hwaccels=p.hwaccels,
            encoders=p.encoders,
            is_apple_silicon=p.is_apple_silicon,
            is_windows=p.is_windows,
            is_macos=p.is_macos,
        )
        budget = self.budget(long_form=long_form)
        active = self.active_counts()
        bottleneck = "none"
        for kind, count in active.items():
            cap = _cap_for(budget, kind)
            if cap > 0 and count >= cap:
                bottleneck = kind
                break
        if avail < 1.2 * (1024**3):
            bottleneck = "memory"
        notes: list[str] = []
        if "videotoolbox" in p.hwaccels:
            notes.append("VideoToolbox decode available")
        if "h264_videotoolbox" in p.encoders:
            notes.append("h264_videotoolbox encoder present (quality path still libx264 by default)")
        if any("nvenc" in e for e in p.encoders):
            notes.append("NVENC encoder present")
        if any("qsv" in e for e in p.encoders):
            notes.append("QSV encoder present")
        return ResourceSnapshot(
            platform=p,
            budget=budget,
            active=active,
            bottleneck=bottleneck,
            notes=notes,
        )

    def encode_argv(self, *, quality: str = "documentary") -> list[str]:
        """Return FFmpeg video encode args.

        Default preserves documentary quality (libx264 CRF). Hardware encoders
        are detected for diagnostics and optional opt-in via VIDEOGEN_HW_ENCODE=1,
        because GPU encode is not always faster/better for filter-heavy pipelines.
        """
        prefer_hw = os.environ.get("VIDEOGEN_HW_ENCODE", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        p = self.profile()
        if prefer_hw:
            if p.is_macos and "h264_videotoolbox" in p.encoders:
                # Bitrate-ish VT path — only when explicitly opted in.
                return [
                    "-c:v",
                    "h264_videotoolbox",
                    "-b:v",
                    "8M",
                    "-allow_sw",
                    "1",
                ]
            if p.is_windows and any("h264_nvenc" in e for e in p.encoders):
                return ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20", "-b:v", "0"]
        # Quality-preserving software path (current production default).
        if quality == "preview":
            return ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23"]
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]

    def to_dict(self) -> Dict[str, Any]:
        snap = self.snapshot()
        p = snap.platform
        return {
            "platform": p.system,
            "os_version": platform.platform(),
            "architecture": p.architecture,
            "cpu_count": p.cpu_count,
            "ram_total_mb": round(p.ram_total_bytes / (1024**2)),
            "ram_available_mb": round(p.ram_available_bytes / (1024**2)),
            "ffmpeg_path": p.ffmpeg_path,
            "hwaccels": list(p.hwaccels),
            "encoders": [e for e in p.encoders if any(k in e for k in ("videotoolbox", "nvenc", "qsv", "amf", "libx264"))],
            "budget": {
                "download": snap.budget.download,
                "ffmpeg": snap.budget.ffmpeg,
                "flow_accounts": snap.budget.flow_accounts,
                "whisper": snap.budget.whisper,
                "processing": snap.budget.processing,
                "reason": snap.budget.reason,
            },
            "active": snap.active,
            "bottleneck": snap.bottleneck,
            "notes": snap.notes,
        }


_GOVERNOR: Optional[ResourceGovernor] = None
_GOV_LOCK = threading.Lock()


def get_governor() -> ResourceGovernor:
    global _GOVERNOR
    with _GOV_LOCK:
        if _GOVERNOR is None:
            _GOVERNOR = ResourceGovernor()
            _GOVERNOR.refresh_profile()
        return _GOVERNOR


def reset_governor_for_tests() -> ResourceGovernor:
    """Test helper — clear singleton state."""
    global _GOVERNOR
    with _GOV_LOCK:
        _GOVERNOR = ResourceGovernor()
        _GOVERNOR.refresh_profile()
        return _GOVERNOR


# ------------------------------------------------------------------ helpers
def _norm_kind(kind: str) -> str:
    k = (kind or "").strip().lower()
    aliases = {
        "downloads": "download",
        "asset": "download",
        "assets": "download",
        "render": "ffmpeg",
        "encode": "ffmpeg",
        "chrome": "flow",
        "flow_accounts": "flow",
        "process": "processing",
        "visual": "processing",
    }
    return aliases.get(k, k)


def _cap_for(budget: ConcurrencyBudget, kind: str) -> int:
    return {
        "download": budget.download,
        "ffmpeg": budget.ffmpeg,
        "flow": budget.flow_accounts,
        "whisper": budget.whisper,
        "processing": budget.processing,
    }.get(kind, 1)


def _find_ffmpeg() -> str:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("ffmpeg.exe", "ffmpeg"):
        cand = os.path.join(here, "bin", name)
        if os.path.isfile(cand):
            return cand
    return shutil.which("ffmpeg") or "ffmpeg"


def _ram_bytes() -> tuple[int, int]:
    """Return (total, available). Best-effort without psutil."""
    try:
        import psutil  # type: ignore

        m = psutil.virtual_memory()
        return int(m.total), int(m.available)
    except Exception:
        pass
    system = platform.system()
    if system == "Darwin":
        try:
            total = int(
                subprocess.check_output(
                    ["sysctl", "-n", "hw.memsize"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
            )
        except Exception:
            total = 8 * (1024**3)
        # pages free + speculative + inactive as rough available
        avail = total // 3
        try:
            out = subprocess.check_output(
                ["vm_stat"], text=True, stderr=subprocess.DEVNULL
            )
            page = 4096
            for line in out.splitlines():
                if "page size of" in line:
                    parts = line.split()
                    for tok in parts:
                        if tok.isdigit():
                            page = int(tok)
                            break
                if line.startswith("Pages free:"):
                    free = int(line.split(":")[1].strip().rstrip(".")) * page
                    avail = max(avail, free)
                if line.startswith("Pages inactive:"):
                    inactive = int(line.split(":")[1].strip().rstrip(".")) * page
                    avail = max(avail, avail + inactive // 2)
        except Exception:
            pass
        return total, min(total, avail)
    if system == "Windows":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return int(stat.ullTotalPhys), int(stat.ullAvailPhys)
        except Exception:
            return 8 * (1024**3), 4 * (1024**3)
    # Linux
    try:
        total = avail = 0
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1]) * 1024
                elif line.startswith("MemAvailable:"):
                    avail = int(line.split()[1]) * 1024
        if total:
            return total, avail or total // 3
    except Exception:
        pass
    return 8 * (1024**3), 4 * (1024**3)


def _probe_ffmpeg_caps(ffmpeg: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    hw: list[str] = []
    enc: list[str] = []
    try:
        from providers import hidden_subprocess as hs

        r = hs.run(
            [ffmpeg, "-hide_banner", "-hwaccels"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        lines = (r.stdout or "").splitlines()
        for line in lines[1:]:
            tok = line.strip().lower()
            if tok:
                hw.append(tok)
    except Exception:
        pass
    try:
        from providers import hidden_subprocess as hs

        r = hs.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=12,
        )
        for line in (r.stdout or "").splitlines():
            low = line.lower()
            for key in (
                "libx264",
                "h264_videotoolbox",
                "hevc_videotoolbox",
                "h264_nvenc",
                "hevc_nvenc",
                "h264_qsv",
                "h264_amf",
            ):
                if key in low:
                    enc.append(key)
    except Exception:
        pass
    return tuple(dict.fromkeys(hw)), tuple(dict.fromkeys(enc))
