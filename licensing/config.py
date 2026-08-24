"""Resolve Supabase URL + anon key (env overrides embedded build constants)."""

from __future__ import annotations

import os
from typing import Tuple

from . import embedded


def supabase_credentials() -> Tuple[str, str]:
    url = (os.environ.get("SUPABASE_URL") or embedded.SUPABASE_URL or "").strip().rstrip("/")
    key = (os.environ.get("SUPABASE_ANON_KEY") or embedded.SUPABASE_ANON_KEY or "").strip()
    return url, key


def is_configured() -> bool:
    url, key = supabase_credentials()
    return bool(url and key)
