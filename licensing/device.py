"""Stable local device id + OS info for login tracking."""

from __future__ import annotations

import json
import platform
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from .session_store import store_dir


def device_id_path() -> Path:
    return store_dir() / "device_id.json"


def get_or_create_device_id() -> str:
    """Same machine keeps the same id across logins (not cleared on sign-out)."""
    path = device_id_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            did = str((data or {}).get("device_id") or "").strip()
            if did:
                return did
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    did = str(uuid.uuid4())
    try:
        path.write_text(json.dumps({"device_id": did}, indent=2), encoding="utf-8")
        path.chmod(0o600)
    except OSError:
        pass
    return did


def collect_device_info() -> Dict[str, Any]:
    hostname = ""
    try:
        hostname = socket.gethostname() or ""
    except OSError:
        hostname = ""
    return {
        "device_id": get_or_create_device_id(),
        "hostname": hostname[:200],
        "os_name": (platform.system() or "")[:80],
        "os_version": (platform.release() or "")[:80],
        "arch": (platform.machine() or "")[:80],
        "last_seen_at": datetime.now(timezone.utc).isoformat(),
    }
