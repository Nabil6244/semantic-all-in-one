"""Friend-only login gate (Supabase Auth + profiles.active)."""

from .auth_client import (
    AuthError,
    AuthSession,
    AuthClient,
    get_auth_client,
    verify_access,
)
from .session_store import clear_session, load_session, save_session

__all__ = [
    "AuthError",
    "AuthSession",
    "AuthClient",
    "get_auth_client",
    "verify_access",
    "clear_session",
    "load_session",
    "save_session",
]
