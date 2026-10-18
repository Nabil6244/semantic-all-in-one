"""Versioned, style-scoped knowledge packages: strict validation, hash check, local cache, pin and rollback.

A package is DATA only (short plain-text advisory rules). Nothing in it is ever executed, formatted or evaluated, and it is
only ever used for the exact ``style_scope`` it names. Packages are published by a trusted off-device process (see
docs/learning/README.md); this module can validate and install them, and build one for that publisher.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SUPPORTED_SCHEMA = 1
KEEP_VERSIONS = 3
MAX_RULES = 12
MAX_RULE_TEXT = 240
MAX_BYTES = 16 * 1024
RULE_KINDS = ("note", "asset_type_failure", "tag_pattern", "pacing_target", "variety_run")
PARAM_RANGES = {"pacing_target": (12, 120), "variety_run": (1, 5)}    # integer ``param`` the generator can apply deterministically
_ID = re.compile(r"^[a-z0-9_.\-]{1,48}$")
_SCOPE = re.compile(r"^[a-z0-9_.+\-]{1,60}/[a-z0-9_.+\-]{1,60}(\+[a-z0-9_.+\-]{1,60})?$")
_ASSET = re.compile(r"^[a-z0-9_.\-]{1,40}$")
_TEXT_BAD = re.compile(r"[\x00-\x1f\x7f`<>{}$\\]")


@dataclass
class Result:
    ok: bool
    reason: str = ""
    version: int = 0


def canonical_hash(pkg: Dict[str, Any]) -> str:
    body = {k: v for k, v in pkg.items() if k != "content_sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def validate(pkg: Any, expected_scope: Optional[str] = None) -> Result:
    try:
        if not isinstance(pkg, dict):
            return Result(False, "not_an_object")
        if len(json.dumps(pkg)) > MAX_BYTES:
            return Result(False, "too_large")
        if pkg.get("schema") != SUPPORTED_SCHEMA:
            return Result(False, "unsupported_schema")
        if int(pkg.get("min_app_schema", 1)) > SUPPORTED_SCHEMA:
            return Result(False, "incompatible_app_schema")
        scope = pkg.get("style_scope")
        if not isinstance(scope, str) or not _SCOPE.match(scope):
            return Result(False, "bad_scope")
        if expected_scope is not None and scope != expected_scope:
            return Result(False, "scope_mismatch")
        v = pkg.get("version")
        if isinstance(v, bool) or not isinstance(v, int) or v < 1:
            return Result(False, "bad_version")
        prev = pkg.get("previous_version")
        if prev is not None and (isinstance(prev, bool) or not isinstance(prev, int) or not 0 < prev < v):
            return Result(False, "bad_previous_version")
        if not isinstance(pkg.get("created_at"), str):
            return Result(False, "bad_created_at")
        rules = pkg.get("rules")
        if not isinstance(rules, list) or len(rules) > MAX_RULES:
            return Result(False, "bad_rules")
        seen = set()
        for r in rules:
            if not isinstance(r, dict) or r.get("status") != "approved":
                return Result(False, "rule_not_approved")
            if not _ID.match(str(r.get("id", ""))) or r["id"] in seen:
                return Result(False, "bad_rule_id")
            seen.add(r["id"])
            if r.get("kind") not in RULE_KINDS:
                return Result(False, "bad_rule_kind")
            t = r.get("text")
            if not isinstance(t, str) or not 1 <= len(t) <= MAX_RULE_TEXT or _TEXT_BAD.search(t):
                return Result(False, "bad_rule_text")
            c, n = r.get("confidence"), r.get("evidence_count")
            if isinstance(c, bool) or not isinstance(c, (int, float)) or not 0 <= c <= 1:
                return Result(False, "bad_confidence")
            if isinstance(n, bool) or not isinstance(n, int) or n < 0:
                return Result(False, "bad_evidence_count")
            if r["kind"] == "asset_type_failure" and not _ASSET.match(str(r.get("asset_type", ""))):
                return Result(False, "bad_asset_type")
            if r["kind"] in PARAM_RANGES:
                lo, hi = PARAM_RANGES[r["kind"]]
                pv = r.get("param")
                if isinstance(pv, bool) or not isinstance(pv, int) or not lo <= pv <= hi:
                    return Result(False, "bad_param")
            if r.get("expires_at") is not None:
                try:
                    datetime.fromisoformat(str(r["expires_at"]))
                except ValueError:
                    return Result(False, "bad_expires_at")
        if pkg.get("content_sha256") != canonical_hash(pkg):
            return Result(False, "hash_mismatch")
        return Result(True, "", v)
    except Exception:
        return Result(False, "invalid")


def build_package(scope: str, rules: List[Dict[str, Any]], *, version: int, previous_version: Optional[int] = None,
                  created_at: Optional[str] = None) -> Dict[str, Any]:
    """For the trusted publisher / tests: stamp the hash. Rules must already carry status='approved' (human approval)."""
    pkg = {"schema": SUPPORTED_SCHEMA, "min_app_schema": 1, "style_scope": scope, "version": version,
           "previous_version": previous_version, "created_at": created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "rules": rules}
    pkg["content_sha256"] = canonical_hash(pkg)
    return pkg


# ---- local cache ----------------------------------------------------------------------------------------------------
def _root(root: Optional[Path]) -> Path:
    if root is not None:
        return Path(root)
    from licensing.session_store import store_dir
    return store_dir() / "knowledge"


def _dir(scope: str, root: Optional[Path]) -> Path:
    return _root(root) / scope.replace("/", "__").replace("+", "--")


def _state(d: Path) -> Dict[str, Any]:
    try:
        return json.loads((d / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(d: Path, st: Dict[str, Any]) -> None:
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "state.json.tmp"
    tmp.write_text(json.dumps(st), encoding="utf-8")
    tmp.replace(d / "state.json")


def _versions(d: Path) -> List[int]:
    return sorted(int(p.stem[1:]) for p in d.glob("v*.json") if p.stem[1:].isdigit()) if d.is_dir() else []


def _load(d: Path, version: int, scope: str) -> Optional[Dict[str, Any]]:
    try:
        pkg = json.loads((d / f"v{version:06d}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return pkg if validate(pkg, scope).ok else None


def install(pkg: Any, *, expected_scope: Optional[str] = None, root: Optional[Path] = None, activate: bool = True) -> Result:
    """Validate and cache a package. Older versions are refused (ordering); the same version is accepted only if identical.
    Never raises."""
    try:
        res = validate(pkg, expected_scope)
        if not res.ok:
            return res
        scope, v = pkg["style_scope"], pkg["version"]
        d = _dir(scope, root)
        have = _versions(d)
        if have and v < have[-1]:
            return Result(False, "older_than_installed", v)
        target = d / f"v{v:06d}.json"
        if target.exists():
            if _load(d, v, scope) != pkg:
                return Result(False, "conflicting_same_version", v)
        else:
            d.mkdir(parents=True, exist_ok=True)
            tmp = d / f"v{v:06d}.tmp"
            tmp.write_text(json.dumps(pkg, sort_keys=True), encoding="utf-8")
            tmp.replace(target)
        st = _state(d)
        if activate and not st.get("pinned"):
            st["active"] = v
            st.pop("rolled_back", None)
        _save_state(d, st)
        for old in _versions(d)[:-KEEP_VERSIONS]:
            if old not in (st.get("active"), st.get("pinned")):
                (d / f"v{old:06d}.json").unlink(missing_ok=True)
        return Result(True, "", v)
    except Exception:
        return Result(False, "install_failed")


def latest_version(scope: str, root: Optional[Path] = None) -> int:
    v = _versions(_dir(scope, root))
    return v[-1] if v else 0


def known_scopes(root: Optional[Path] = None) -> List[str]:
    out = []
    base = _root(root)
    for d in sorted(base.iterdir()) if base.is_dir() else []:
        for v in reversed(_versions(d)):
            try:
                sc = json.loads((d / f"v{v:06d}.json").read_text(encoding="utf-8")).get("style_scope")
            except (OSError, ValueError):
                continue
            if isinstance(sc, str) and _SCOPE.match(sc):
                out.append(sc)
                break
    return out


def active_package(scope: str, root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """The package in force for exactly this scope: pinned > active, re-validated on every read; if the file went bad it
    falls back to the newest older valid version. None when nothing valid exists."""
    try:
        d = _dir(scope, root)
        st = _state(d)
        first = st.get("pinned") or st.get("active")
        order = ([first] if first else []) + [v for v in reversed(_versions(d)) if v != first and not st.get("pinned") and (not first or v < first)]
        for v in order:
            pkg = _load(d, int(v), scope)
            if pkg:
                return pkg
    except Exception:
        pass
    return None


def rollback(scope: str, root: Optional[Path] = None) -> Result:
    """Make the previous cached version active (the project and its CSV are untouched)."""
    try:
        d = _dir(scope, root)
        st = _state(d)
        cur = st.get("active")
        older = [v for v in _versions(d) if cur is not None and v < cur and _load(d, v, scope)]
        if not older:
            return Result(False, "no_previous_version")
        st["active"], st["rolled_back"] = older[-1], cur
        st.pop("pinned", None)
        _save_state(d, st)
        return Result(True, "", older[-1])
    except Exception:
        return Result(False, "rollback_failed")


def pin(scope: str, version: Optional[int], root: Optional[Path] = None) -> Result:
    """Pin a cached version (keeps it in force even if a newer one downloads); version=None unpins."""
    try:
        d = _dir(scope, root)
        st = _state(d)
        if version is None:
            st.pop("pinned", None)
        elif not _load(d, version, scope):
            return Result(False, "version_not_cached")
        else:
            st["pinned"] = version
        _save_state(d, st)
        return Result(True, "", version or 0)
    except Exception:
        return Result(False, "pin_failed")
