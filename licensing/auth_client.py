"""Supabase GoTrue login/refresh + profiles.active check via REST."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

from .config import is_configured, supabase_credentials
from . import session_store


class AuthError(Exception):
    """User-facing auth failure. ``code`` drives login / force-logout copy."""

    def __init__(self, message: str, *, code: str = "auth"):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class AuthSession:
    access_token: str
    refresh_token: str
    user_id: str
    email: str = ""
    display_name: str = ""

    def to_store(self) -> Dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "user_id": self.user_id,
            "email": self.email,
            "display_name": self.display_name,
        }

    @classmethod
    def from_store(cls, data: Dict[str, Any]) -> "AuthSession":
        return cls(
            access_token=str(data.get("access_token") or ""),
            refresh_token=str(data.get("refresh_token") or ""),
            user_id=str(data.get("user_id") or ""),
            email=str(data.get("email") or ""),
            display_name=str(data.get("display_name") or ""),
        )


_TIMEOUT = 20


class AuthClient:
    def __init__(self, url: Optional[str] = None, anon_key: Optional[str] = None):
        if url is None or anon_key is None:
            cfg_url, cfg_key = supabase_credentials()
            url = url if url is not None else cfg_url
            anon_key = anon_key if anon_key is not None else cfg_key
        self.url = (url or "").rstrip("/")
        self.anon_key = anon_key or ""

    @property
    def configured(self) -> bool:
        return bool(self.url and self.anon_key)

    def _headers(self, access_token: Optional[str] = None) -> Dict[str, str]:
        h = {
            "apikey": self.anon_key,
            "Content-Type": "application/json",
        }
        if access_token:
            h["Authorization"] = f"Bearer {access_token}"
        return h

    def login(self, email: str, password: str) -> AuthSession:
        if not self.configured:
            raise AuthError("App is not configured for login.", code="misconfigured")
        email = (email or "").strip()
        if not email or not password:
            raise AuthError("Invalid login", code="invalid")
        try:
            resp = requests.post(
                f"{self.url}/auth/v1/token?grant_type=password",
                headers=self._headers(),
                json={"email": email, "password": password},
                timeout=_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise AuthError(f"Could not reach login server: {exc}", code="network") from exc

        if resp.status_code in (400, 401):
            raise AuthError("Invalid login", code="invalid")
        if resp.status_code >= 400:
            raise AuthError("Invalid login", code="invalid")

        data = resp.json()
        access = data.get("access_token") or ""
        refresh = data.get("refresh_token") or ""
        user = data.get("user") or {}
        user_id = str(user.get("id") or "")
        user_email = str(user.get("email") or email)
        if not access or not refresh or not user_id:
            raise AuthError("Invalid login", code="invalid")

        session = AuthSession(
            access_token=access,
            refresh_token=refresh,
            user_id=user_id,
            email=user_email,
        )
        profile = self._fetch_profile(session)
        session.display_name = profile.get("display_name") or ""
        if not profile.get("active"):
            raise AuthError("Account disabled", code="disabled")
        session_store.save_session(session.to_store())
        self._upsert_device(session)
        return session

    def request_password_reset(self, email: str) -> None:
        """Ask Supabase to email a recovery link. Never reveals whether the
        address has an account.

        Supabase's /recover endpoint deliberately answers 200 for unknown
        addresses so callers cannot enumerate accounts, and this method keeps
        that property: it returns None on success and raises only for problems
        that are not about the address itself (not configured, unreachable,
        rate limited). The caller must therefore show the same neutral message
        either way.

        No redirect URL is sent, so Supabase uses the project's configured
        Site URL and the reset is completed in the browser — the desktop app
        never handles the new password.
        """
        if not self.configured:
            raise AuthError("App is not configured for login.", code="misconfigured")
        email = (email or "").strip()
        if not email or "@" not in email:
            raise AuthError("Enter the email address for your account.", code="invalid")
        try:
            resp = requests.post(
                f"{self.url}/auth/v1/recover",
                headers=self._headers(),
                json={"email": email},
                timeout=_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise AuthError(f"Could not reach login server: {exc}", code="network") from exc

        if resp.status_code == 429:
            raise AuthError(
                "Too many reset requests. Wait a few minutes and try again.",
                code="rate_limited",
            )
        if resp.status_code >= 500:
            raise AuthError("Login server is unavailable. Try again shortly.", code="server")
        # 4xx other than 429 is treated as success on purpose: a malformed or
        # unknown address must not be distinguishable from a valid one.
        return None

    def refresh(self, refresh_token: str) -> AuthSession:
        if not self.configured:
            raise AuthError("App is not configured for login.", code="misconfigured")
        if not refresh_token:
            raise AuthError("Access revoked — contact the owner.", code="revoked")
        try:
            resp = requests.post(
                f"{self.url}/auth/v1/token?grant_type=refresh_token",
                headers=self._headers(),
                json={"refresh_token": refresh_token},
                timeout=_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise AuthError(f"Could not reach login server: {exc}", code="network") from exc

        if resp.status_code in (400, 401, 403):
            raise AuthError(
                "Access revoked or password changed",
                code="revoked",
            )
        if resp.status_code >= 400:
            raise AuthError(
                "Access revoked or password changed",
                code="revoked",
            )

        data = resp.json()
        access = data.get("access_token") or ""
        new_refresh = data.get("refresh_token") or refresh_token
        user = data.get("user") or {}
        user_id = str(user.get("id") or "")
        email = str(user.get("email") or "")
        if not access or not user_id:
            # Some responses omit user — fall back to getUser.
            session = AuthSession(
                access_token=access,
                refresh_token=new_refresh,
                user_id="",
                email=email,
            )
            user_info = self._get_user(access)
            session.user_id = user_info["id"]
            session.email = user_info.get("email") or email
        else:
            session = AuthSession(
                access_token=access,
                refresh_token=new_refresh,
                user_id=user_id,
                email=email,
            )
        return session

    def _get_user(self, access_token: str) -> Dict[str, str]:
        try:
            resp = requests.get(
                f"{self.url}/auth/v1/user",
                headers=self._headers(access_token),
                timeout=_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise AuthError(f"Could not reach login server: {exc}", code="network") from exc
        if resp.status_code in (401, 403):
            raise AuthError("Access revoked or password changed", code="revoked")
        if resp.status_code >= 400:
            raise AuthError("Access revoked or password changed", code="revoked")
        user = resp.json()
        uid = str(user.get("id") or "")
        if not uid:
            raise AuthError("Access revoked or password changed", code="revoked")
        return {"id": uid, "email": str(user.get("email") or "")}

    def _fetch_profile(self, session: AuthSession) -> Dict[str, Any]:
        try:
            resp = requests.get(
                f"{self.url}/rest/v1/profiles",
                headers={
                    **self._headers(session.access_token),
                    "Accept": "application/json",
                },
                params={"select": "active,display_name", "id": f"eq.{session.user_id}"},
                timeout=_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise AuthError(f"Could not reach login server: {exc}", code="network") from exc

        if resp.status_code in (401, 403):
            raise AuthError("Access revoked or password changed", code="revoked")
        if resp.status_code >= 400:
            raise AuthError("Access revoked — contact the owner.", code="revoked")

        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            # Missing profile row = deny (treat as inactive).
            return {"active": False, "display_name": ""}
        row = rows[0] if isinstance(rows[0], dict) else {}
        return {
            "active": bool(row.get("active")),
            "display_name": str(row.get("display_name") or ""),
        }

    def verify_stored_session(self) -> AuthSession:
        """Refresh tokens + re-check profiles.active. Raises AuthError on deny."""
        if not self.configured:
            raise AuthError("App is not configured for login.", code="misconfigured")
        stored = session_store.load_session()
        if not stored:
            raise AuthError("Not signed in", code="unsigned")
        session = self.refresh(str(stored.get("refresh_token") or ""))
        if not session.email:
            session.email = str(stored.get("email") or "")
        profile = self._fetch_profile(session)
        session.display_name = profile.get("display_name") or session.display_name
        if not profile.get("active"):
            session_store.clear_session()
            raise AuthError("Account disabled", code="disabled")
        session_store.save_session(session.to_store())
        self._upsert_device(session)
        return session

    def _upsert_device(self, session: AuthSession) -> None:
        """One user → many devices. Never blocks login if tracking fails."""
        try:
            from .device import collect_device_info

            info = collect_device_info()
            payload = {
                "user_id": session.user_id,
                "device_id": info["device_id"],
                "hostname": info.get("hostname") or "",
                "os_name": info.get("os_name") or "",
                "os_version": info.get("os_version") or "",
                "arch": info.get("arch") or "",
                "last_seen_at": info.get("last_seen_at"),
            }
            requests.post(
                f"{self.url}/rest/v1/devices?on_conflict=user_id,device_id",
                headers={
                    **self._headers(session.access_token),
                    "Prefer": "resolution=merge-duplicates,return=minimal",
                },
                json=payload,
                timeout=_TIMEOUT,
            )
        except Exception:
            pass


_client: Optional[AuthClient] = None


def get_auth_client() -> AuthClient:
    global _client
    if _client is None:
        _client = AuthClient()
    return _client


def verify_access() -> AuthSession:
    """Public entry: refresh + active check using the shared client."""
    return get_auth_client().verify_stored_session()
