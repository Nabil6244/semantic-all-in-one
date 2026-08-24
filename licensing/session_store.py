"""Persist Supabase tokens locally (cleared on force-logout / Sign out)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def _store_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path.home() / ".videogen"
    else:
        base = Path(__file__).resolve().parent.parent
    base.mkdir(parents=True, exist_ok=True)
    return base


def store_dir() -> Path:
    return _store_dir()


def session_path() -> Path:
    return _store_dir() / "auth_session.json"


def load_session() -> Optional[Dict[str, Any]]:
    path = session_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    if not data.get("access_token") or not data.get("refresh_token"):
        return None
    return data


def save_session(data: Dict[str, Any]) -> None:
    path = session_path()
    payload = {
        "access_token": data.get("access_token") or "",
        "refresh_token": data.get("refresh_token") or "",
        "user_id": data.get("user_id") or "",
        "email": data.get("email") or "",
        "display_name": data.get("display_name") or "",
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def clear_session() -> None:
    path = session_path()
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass
