"""About & Ownership terms: version, content, and Supabase acknowledgement.

One module owns the version string and the agreement text so the first-login
dialog and the permanent page can never drift apart. Persistence reuses the
existing Supabase REST conventions from auth_client (same headers, same
timeout, same AuthError semantics).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import requests

from .auth_client import AuthError, AuthSession
from .config import supabase_credentials

# Bump this when the agreement materially changes: an existing user who
# acknowledged an older version is then asked again, and their old row is kept.
CURRENT_TERMS_VERSION = "2026-08-30-v1"

TABLE = "user_terms_acknowledgements"
_TIMEOUT = 20

TITLE = "About & Ownership"

INTRO = (
    "Before you continue, please review the About & Ownership information "
    "for this application."
)

# (heading, [paragraphs]) — rendered identically by the dialog and the page.
SECTIONS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "About the Application",
        (
            "This application is an internal YouTube content production and management "
            "platform designed to help our team research, plan, create, process, manage, "
            "and publish video content efficiently.",
            "The purpose of this application is to create a standardized workflow so that "
            "employees and partners can work on assigned YouTube channels and projects "
            "using the same production system.",
            "The application may include tools and workflows for research, scripting, "
            "visual planning, asset management, video generation, audio processing, "
            "quality assurance, and publishing.",
        ),
    ),
    (
        "How This App Was Created",
        (
            "This application was created from the idea of building a complete and "
            "organized system for managing YouTube content production at scale.",
            "Instead of relying on disconnected tools and manual processes, the goal was "
            "to create one workflow where content can move from:",
            "Research → Idea → Script → Visuals → Production → "
            "Quality Control → Publishing",
            "The application has been continuously developed and improved based on "
            "practical production requirements, workflow testing, automation needs, and "
            "the experience of operating YouTube content projects.",
        ),
    ),
    (
        "Development & Ownership",
        (
            "This application was developed by:",
            "Nabil & Yahya",
            "Nabil and Yahya are the developers and creators responsible for the design, "
            "development, architecture, implementation, and continued improvement of this "
            "application.",
            "The application's source code, software architecture, workflows, original "
            "systems, and other intellectual property are subject to the ownership and "
            "agreements established by the developers.",
            "Unauthorized copying, redistribution, resale, reverse engineering, or use of "
            "the application outside the authorized business/project environment is not "
            "permitted unless expressly authorized by the owners.",
        ),
    ),
    (
        "YouTube Channel Ownership & Revenue Agreement",
        (
            "This application is provided as part of an organized YouTube "
            "content-production operation.",
            "Where an employee, contractor, partner, or other authorized user creates, "
            "develops, manages, or operates a YouTube channel or content project through "
            "this business/workflow, the ownership and/or revenue rights associated with "
            "that channel or project are governed by the applicable agreement between the "
            "parties.",
            "Unless a separate written agreement states otherwise:",
            "Nabil retains a 50% ownership interest in each YouTube channel/project "
            "created or operated under this arrangement.",
            "The remaining ownership interest belongs to the other party or parties "
            "according to the applicable agreement.",
            "This ownership arrangement applies to channels/projects that are specifically "
            "created, assigned, or operated as part of this business arrangement. It does "
            "not automatically apply to unrelated personal channels or projects unless "
            "those channels/projects are expressly brought under the agreement.",
            "For clarity, ownership, revenue sharing, profit sharing, management rights, "
            "and control rights may be different concepts. The parties should rely on "
            "their applicable written agreement for the exact rights and obligations "
            "associated with each channel or project.",
        ),
    ),
)

# The line that must stand out visually without reading as a warning banner.
OWNERSHIP_HIGHLIGHT = (
    "Nabil retains a 50% ownership interest in each YouTube channel/project "
    "created or operated under this arrangement."
)

ACKNOWLEDGEMENT_POINTS: Tuple[str, ...] = (
    "I have read and understood the About & Ownership information.",
    "I understand that the application is part of an organized YouTube "
    "content-production operation.",
    "I understand that YouTube channels/projects assigned to me or created under "
    "this business arrangement may be subject to an ownership agreement.",
    "I understand that, unless a separate written agreement states otherwise, "
    "Nabil retains a 50% ownership interest in channels/projects covered by this "
    "arrangement.",
    "I agree to follow the applicable business, ownership, confidentiality, and "
    "operational agreements governing the project assigned to me.",
)

LEGAL_NOTE = (
    "Important: This acknowledgement should not be presented as replacing a "
    "separate legally binding contract where one is required."
)

CHECKBOX_LABEL = (
    "I have read and understood the About & Ownership information and agree to "
    "the applicable ownership and business terms."
)


def welcome_heading(display_name: str) -> str:
    """'Welcome, <name>' — falls back to a neutral form when no name is known."""
    name = (display_name or "").strip()
    return f"Welcome, {name}" if name else "Welcome"


def acknowledgement_lead(display_name: str) -> str:
    name = (display_name or "").strip()
    return f"{name}, I acknowledge that:" if name else "I acknowledge that:"


def _rest(url: str, key: str, token: str) -> Tuple[str, Dict[str, str]]:
    return (
        f"{url}/rest/v1/{TABLE}",
        {
            "apikey": key,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )


def has_acknowledged(
    session: AuthSession, *, version: str = CURRENT_TERMS_VERSION
) -> bool:
    """True only when THIS user has an acknowledged row for THIS version.

    Raises AuthError(code='network') when the answer cannot be determined —
    the caller must not treat an unreachable server as "already accepted".
    """
    if session is None or not getattr(session, "user_id", ""):
        return False
    url, key = supabase_credentials()
    if not url or not key:
        raise AuthError("App is not configured for login.", code="misconfigured")
    endpoint, headers = _rest(url, key, session.access_token)
    try:
        resp = requests.get(
            endpoint,
            headers=headers,
            params={
                "select": "acknowledged,terms_version",
                # RLS also restricts this to the caller, but filtering by the
                # session's own id keeps the query honest client-side too.
                "user_id": f"eq.{session.user_id}",
                "terms_version": f"eq.{version}",
                "acknowledged": "is.true",
                "limit": "1",
            },
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise AuthError(f"Could not reach login server: {exc}", code="network") from exc
    if resp.status_code in (401, 403):
        raise AuthError("Access revoked or password changed", code="revoked")
    if resp.status_code >= 400:
        raise AuthError(
            f"Could not check the ownership acknowledgement ({resp.status_code}).",
            code="network",
        )
    try:
        rows = resp.json()
    except ValueError as exc:
        raise AuthError("Unexpected response from login server.", code="network") from exc
    return isinstance(rows, list) and len(rows) > 0


def save_acknowledgement(
    session: AuthSession, *, version: str = CURRENT_TERMS_VERSION
) -> None:
    """Upsert this user's acknowledgement. Raises AuthError on any failure.

    user_id ALWAYS comes from the authenticated session — never from the UI —
    so the screen cannot acknowledge on behalf of another account.
    """
    if session is None or not getattr(session, "user_id", ""):
        raise AuthError("You must be signed in to continue.", code="unsigned")
    url, key = supabase_credentials()
    if not url or not key:
        raise AuthError("App is not configured for login.", code="misconfigured")
    endpoint, headers = _rest(url, key, session.access_token)
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
    # acknowledged_at is intentionally NOT sent: the database stamps it (see
    # set_updated_at in the migration), so the audit time cannot be skewed by a
    # wrong client clock, and we avoid sending a timestamp string at all.
    payload = {
        "user_id": session.user_id,
        "display_name": (session.display_name or "").strip() or None,
        "terms_version": version,
        "acknowledged": True,
    }
    try:
        resp = requests.post(
            endpoint,
            headers=headers,
            params={"on_conflict": "user_id,terms_version"},
            json=payload,
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise AuthError(f"Could not reach login server: {exc}", code="network") from exc
    if resp.status_code in (401, 403):
        raise AuthError("Access revoked or password changed", code="revoked")
    if resp.status_code >= 400:
        raise AuthError(
            f"Could not save the acknowledgement ({resp.status_code}). Please try again.",
            code="network",
        )
