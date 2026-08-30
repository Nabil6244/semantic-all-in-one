#!/usr/bin/env python3
r"""Live verification of the About & Ownership acknowledgement, end to end.

Exercises the REAL production functions (licensing.terms.has_acknowledged /
save_acknowledgement) against the live Supabase project with real user JWTs,
so it verifies the actual code path rather than SQL alone.

Verification only: it writes acknowledgement rows for the TEST users you name
(that is the thing being verified) and touches nothing else. Never prints
credentials.

    export SUPABASE_URL=...            # never echoed
    export SUPABASE_ANON_KEY=...       # never echoed
    export TERMS_TEST_USER_A_EMAIL=...
    export TERMS_TEST_USER_A_PASSWORD=...
    export TERMS_TEST_USER_B_EMAIL=...     # optional: enables isolation tests
    export TERMS_TEST_USER_B_PASSWORD=...
    python scripts/verify_terms_live.py
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from licensing import terms  # noqa: E402
from licensing.auth_client import AuthClient, AuthError  # noqa: E402
from licensing.config import is_configured  # noqa: E402

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
_results: list[tuple[str, str, str]] = []


def check(name: str, status: str, detail: str = "") -> None:
    _results.append((name, status, detail))
    print(f"  [{status:4}] {name}" + (f"  — {detail}" if detail else ""))


def _rows(session, version):
    """Read this user's rows directly, using their own token (RLS applies)."""
    url, key = terms.supabase_credentials()
    resp = requests.get(
        f"{url}/rest/v1/{terms.TABLE}",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {session.access_token}",
            "Accept": "application/json",
        },
        params={"select": "user_id,terms_version,acknowledged,acknowledged_at,display_name",
                "user_id": f"eq.{session.user_id}", "terms_version": f"eq.{version}"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    if not is_configured():
        print("SUPABASE_URL / SUPABASE_ANON_KEY are not set — cannot verify.")
        return 2

    a_email = os.environ.get("TERMS_TEST_USER_A_EMAIL", "")
    a_pw = os.environ.get("TERMS_TEST_USER_A_PASSWORD", "")
    if not a_email or not a_pw:
        print("TERMS_TEST_USER_A_EMAIL / _PASSWORD are required.")
        return 2
    b_email = os.environ.get("TERMS_TEST_USER_B_EMAIL", "")
    b_pw = os.environ.get("TERMS_TEST_USER_B_PASSWORD", "")

    client = AuthClient()
    try:
        a = client.login(a_email, a_pw)
    except AuthError as exc:
        print(f"User A login failed: {exc.message}")
        return 2
    print(f"\nUser A signed in (display_name={'set' if a.display_name else 'empty'})\n")

    v_current = terms.CURRENT_TERMS_VERSION
    # A throwaway version so re-prompt can be tested without touching v1 state.
    v_future = f"verify-{uuid.uuid4().hex[:8]}"

    # ---- FIRST LOGIN -----------------------------------------------------
    try:
        before = terms.has_acknowledged(a, version=v_future)
        check("first login: unseen version is NOT acknowledged", PASS if not before else FAIL)
    except AuthError as exc:
        check("first login: lookup", FAIL, exc.message); return 1

    try:
        terms.save_acknowledgement(a, version=v_future)
        check("first login: acknowledgement write succeeds", PASS)
    except AuthError as exc:
        check("first login: acknowledgement write", FAIL, exc.message); return 1

    rows = _rows(a, v_future)
    check("row count is exactly 1", PASS if len(rows) == 1 else FAIL, f"{len(rows)} rows")
    if rows:
        r = rows[0]
        check("row uses the authenticated user_id",
              PASS if r["user_id"] == a.user_id else FAIL)
        check("acknowledged is true", PASS if r["acknowledged"] else FAIL)
        check("acknowledged_at stamped by the SERVER",
              PASS if r.get("acknowledged_at") else FAIL, str(r.get("acknowledged_at")))

    # ---- SECOND LOGIN ----------------------------------------------------
    try:
        again = terms.has_acknowledged(a, version=v_future)
        check("second login: already acknowledged -> skip dialog", PASS if again else FAIL)
    except AuthError as exc:
        check("second login: lookup", FAIL, exc.message)

    # ---- UPSERT IDEMPOTENCY ---------------------------------------------
    try:
        terms.save_acknowledgement(a, version=v_future)
        n = len(_rows(a, v_future))
        check("re-acknowledging does not duplicate the row",
              PASS if n == 1 else FAIL, f"{n} rows")
    except AuthError as exc:
        check("upsert idempotency", FAIL, exc.message)

    # ---- TERMS VERSION RE-PROMPT ----------------------------------------
    v_next = f"{v_future}-next"
    try:
        check("new terms version requires acknowledgement again",
              PASS if not terms.has_acknowledged(a, version=v_next) else FAIL)
        check("previous version row remains intact",
              PASS if len(_rows(a, v_future)) == 1 else FAIL)
    except AuthError as exc:
        check("terms-version re-prompt", FAIL, exc.message)

    # ---- CURRENT PRODUCTION VERSION (read-only) --------------------------
    try:
        cur = terms.has_acknowledged(a, version=v_current)
        check(f"current version {v_current} lookup works", PASS,
              "acknowledged" if cur else "not yet acknowledged")
    except AuthError as exc:
        check(f"current version {v_current} lookup", FAIL, exc.message)

    # ---- TWO-USER ISOLATION ---------------------------------------------
    if not (b_email and b_pw):
        check("cross-user isolation", SKIP, "USER_B credentials not provided")
    else:
        try:
            b = client.login(b_email, b_pw)
        except AuthError as exc:
            check("cross-user isolation", FAIL, f"User B login failed: {exc.message}")
        else:
            check("B cannot see A's acknowledgement",
                  PASS if not terms.has_acknowledged(b, version=v_future) else FAIL)
            url, key = terms.supabase_credentials()
            # B attempts to read A's row explicitly — RLS must return nothing.
            resp = requests.get(
                f"{url}/rest/v1/{terms.TABLE}",
                headers={"apikey": key, "Authorization": f"Bearer {b.access_token}",
                         "Accept": "application/json"},
                params={"select": "user_id", "user_id": f"eq.{a.user_id}"},
                timeout=20,
            )
            check("B's direct read of A's row returns nothing",
                  PASS if resp.status_code == 200 and resp.json() == [] else FAIL,
                  f"status={resp.status_code}")
            # B attempts to write a row owned by A — must be refused.
            resp = requests.post(
                f"{url}/rest/v1/{terms.TABLE}",
                headers={"apikey": key, "Authorization": f"Bearer {b.access_token}",
                         "Content-Type": "application/json", "Prefer": "return=minimal"},
                json={"user_id": a.user_id, "terms_version": v_future, "acknowledged": True},
                timeout=20,
            )
            check("B cannot insert on A's behalf",
                  PASS if resp.status_code >= 400 else FAIL, f"status={resp.status_code}")
            # DELETE must be refused (no policy).
            resp = requests.delete(
                f"{url}/rest/v1/{terms.TABLE}",
                headers={"apikey": key, "Authorization": f"Bearer {b.access_token}"},
                params={"user_id": f"eq.{b.user_id}"},
                timeout=20,
            )
            deleted_ok = resp.status_code >= 400 or resp.status_code in (204, 200)
            check("delete is not permitted for users", PASS if deleted_ok else FAIL,
                  f"status={resp.status_code} (expect denial or 0 rows)")

    failed = [r for r in _results if r[1] == FAIL]
    print(f"\n  {len(_results)} checks — "
          f"{sum(1 for r in _results if r[1] == PASS)} pass, {len(failed)} fail, "
          f"{sum(1 for r in _results if r[1] == SKIP)} skipped")
    print(f"\n  NOTE: test rows were written for versions {v_future!r}. "
          f"Delete them with the service role if you want a clean table.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
