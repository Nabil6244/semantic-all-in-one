"""Diagnostic performance report for support / hidden debug panel."""

from __future__ import annotations

import json
import platform
import sys
from typing import Any, Dict

from .governor import get_governor
from .process_registry import get_registry


def build_diagnostics_report() -> Dict[str, Any]:
    gov = get_governor()
    snap = gov.to_dict()
    procs = get_registry().to_list()
    return {
        "app": "Semantic YT Studio",
        "python_version": sys.version.split()[0],
        "platform": snap.get("platform"),
        "os_version": snap.get("os_version") or platform.platform(),
        "architecture": snap.get("architecture"),
        "cpu_count": snap.get("cpu_count"),
        "ram_total_mb": snap.get("ram_total_mb"),
        "ram_available_mb": snap.get("ram_available_mb"),
        "ffmpeg_path": snap.get("ffmpeg_path"),
        "hwaccels": snap.get("hwaccels"),
        "encoders": snap.get("encoders"),
        "budget": snap.get("budget"),
        "active_workers": snap.get("active"),
        "bottleneck": snap.get("bottleneck"),
        "notes": snap.get("notes"),
        "owned_processes": procs,
        "owned_process_count": len(procs),
    }


def format_diagnostics_text(report: Dict[str, Any] | None = None) -> str:
    data = report or build_diagnostics_report()
    lines = [
        "=== Semantic YT Studio diagnostics ===",
        f"PLATFORM     {data.get('platform')} {data.get('os_version')}",
        f"ARCH         {data.get('architecture')}",
        f"CPU          {data.get('cpu_count')} cores",
        f"RAM          {data.get('ram_available_mb')} / {data.get('ram_total_mb')} MB available",
        f"FFMPEG       {data.get('ffmpeg_path')}",
        f"HWACCELS     {', '.join(data.get('hwaccels') or []) or 'none'}",
        f"ENCODERS     {', '.join(data.get('encoders') or []) or 'n/a'}",
        f"BOTTLENECK   {data.get('bottleneck')}",
        f"ACTIVE       {json.dumps(data.get('active_workers') or {})}",
        f"BUDGET       {json.dumps(data.get('budget') or {})}",
        f"OWNED PROCS  {data.get('owned_process_count')}",
    ]
    for note in data.get("notes") or []:
        lines.append(f"NOTE         {note}")
    return "\n".join(lines)
