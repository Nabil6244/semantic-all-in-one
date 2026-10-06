"""Automatic failure recovery: what a failure MEANS, whether retrying can help, and a project-level recovery scan.

Classification is deterministic (error text and exception type only — no AI). It decides:
  * retryable failures (a dropped connection, a timeout, a 5xx, a rate limit) — retried with backoff by the caller,
  * permanent failures (no search results, a bad key, a missing place, a full disk) — never retried blindly; the scene
    goes to Needs action with a plain explanation,
  * stops (cancelled, interrupted) — never retried automatically.

Flow is deliberately NOT retried from here: Flow keeps its own frozen retry rules (one same-source retry, paid-video
guard, anti-abuse hold detection) in AssetManager / flow-engine. ``classify_failure`` still labels Flow failures so
analytics and the job ledger can report them, but ``should_auto_retry`` refuses Flow sources.

The recovery scan (``scan_project`` / ``apply``) repairs what a crash or a closed laptop leaves behind:
  * half-written downloads (``*.part``, ``*_part.mp4``) in the scene media folder -> deleted (never a finished file),
  * render-cache entries whose clip is missing or empty -> dropped from the index (the scene simply re-renders),
  * manifest records that say "complete" but whose file is gone -> reported (Generate re-resolves them),
  * jobs that were running when the app closed -> already marked interrupted by the job ledger; reported here.
It never deletes a finished asset, a CSV, narration, or a final render.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, List, Optional

FLOW_SOURCES = frozenset({"flow_image", "flow_video", "image", "video", "flow"})


@dataclass(frozen=True)
class FailureClass:
    kind: str  # network | timeout | rate_limit | busy | not_found | invalid_input | auth | disk | too_large | slow | cancelled
    #            | interrupted | corrupt_output | flow_hold | unknown
    retryable: bool
    backoff_s: float = 0.0
    advice: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# Order matters: the first matching rule wins (stops before transient before permanent).
_RULES: List[tuple] = [
    ("cancelled", False, 0.0, r"\bcancel+ed\b|stopped by (?:the )?user|download cancelled", "Stopped on request."),
    ("interrupted", False, 0.0, r"interrupted", "The app or the batch stopped while this ran. Retry it."),
    ("flow_hold", False, 0.0, r"PUBLIC_ERROR_UNUSUAL_ACTIVITY|unusual activity",
     "Google paused this Flow account. Wait before retrying, or change the scene's source."),
    ("disk", False, 0.0, r"no space left|disk (?:is )?full|GB free on the disk|errno 28|not enough space",
     "The disk is nearly full. Free some space, then Retry."),
    ("too_large", False, 0.0, r"exceeded \d+\s*MB|too large", "The file was bigger than the size cap. Try another clip."),
    ("auth", False, 0.0, r"\b401\b|\b403\b|unauthori[sz]ed|forbidden|api key (?:is )?(?:required|not valid|invalid)|rejected the api key",
     "The service refused the key. Check it in Settings."),
    ("slow", False, 0.0, r"took longer than", "The download was far too slow. Try another clip or source."),
    ("rate_limit", True, 20.0, r"\b429\b|rate limit|quota|too many requests|resource_exhausted", "The service asked us to slow down."),
    ("timeout", True, 4.0, r"timed? ?out|timeout|read timeout", "The network was too slow."),
    ("network", True, 3.0,
     r"connection (?:reset|aborted|refused|error)|remote end closed|broken pipe|name or service not known|"
     r"temporary failure in name resolution|getaddrinfo|max retries exceeded|ssl|eof occurred|network is unreachable|"
     r"chunkedencodingerror|incompleteread|connectionerror|failed to establish a new connection|httpsconnectionpool|"
     r"request failed",
     "The connection dropped."),
    ("busy", True, 6.0, r"\b50[0234]\b|service unavailable|bad gateway|internal server error|overloaded|high demand",
     "The service was busy."),
    ("corrupt_output", True, 1.0, r"moov atom not found|invalid data found|corrupt|truncated",
     "The downloaded file was broken."),
    ("not_found", False, 0.0,
     r"no (?:suitable|alternative|usable) .*result|candidates exhausted|search exhausted|no results|not found|"
     r"no research media|place .* not found|no unused",
     "Nothing usable was found. Try other search words or another source."),
    ("invalid_input", False, 0.0, r"no (?:stock keywords|search query|place) given|validation|is empty|unknown (?:camera|style|map option)",
     "The scene's instruction is incomplete. Edit the row."),
]
_COMPILED = [(k, r, b, re.compile(p, re.IGNORECASE), a) for k, r, b, p, a in _RULES]

UNKNOWN = FailureClass("unknown", False, 0.0, "Unexpected failure. See the Activity log.")


def classify_failure(error: Any, source: str = "") -> FailureClass:
    """Classify an error message or exception. Deterministic; never raises."""
    try:
        if isinstance(error, BaseException):
            text = f"{type(error).__name__}: {error}"
        else:
            text = str(error or "")
        if not text.strip():
            return UNKNOWN
        for kind, retryable, backoff, rx, advice in _COMPILED:
            if rx.search(text):
                return FailureClass(kind, retryable, backoff, advice)
        return UNKNOWN
    except Exception:
        return UNKNOWN


def is_flow_source(source: str) -> bool:
    return str(source or "").strip().lower() in FLOW_SOURCES


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3  # the first attempt included
    base_delay_s: float = 2.0
    max_delay_s: float = 45.0

    def delay(self, attempt: int, failure: Optional[FailureClass] = None) -> float:
        """Seconds to wait before attempt number ``attempt + 1`` (attempt counts from 1)."""
        base = max(self.base_delay_s, failure.backoff_s if failure else 0.0)
        return float(min(self.max_delay_s, base * (2 ** max(0, attempt - 1))))


# Per job type. Asset sources other than Flow get two automatic retries for transient failures.
POLICIES = {
    "asset": RetryPolicy(max_attempts=3, base_delay_s=2.0, max_delay_s=45.0),
    "align": RetryPolicy(max_attempts=1),
    "editorial": RetryPolicy(max_attempts=1),
    "render": RetryPolicy(max_attempts=2, base_delay_s=1.0, max_delay_s=5.0),
    "map": RetryPolicy(max_attempts=2, base_delay_s=1.0, max_delay_s=5.0),
    "ai": RetryPolicy(max_attempts=1),
}


def policy_for(job_type: str) -> RetryPolicy:
    return POLICIES.get(str(job_type or ""), RetryPolicy(max_attempts=1))


def should_auto_retry(failure: FailureClass, *, source: str = "", attempt: int = 1, policy: Optional[RetryPolicy] = None) -> bool:
    """True when the caller should try again by itself. Flow is never auto-retried from here (its rules are frozen)."""
    if is_flow_source(source):
        return False
    policy = policy or POLICIES["asset"]
    return bool(failure.retryable) and attempt < policy.max_attempts


# --------------------------------------------------------------------------- project recovery scan

_PARTIAL_PATTERNS = ("*.part", "*_part.mp4")


@dataclass
class RecoveryAction:
    action: str  # delete_partial | drop_render_cache_entry | reresolve_asset | retry_job
    target: str
    detail: str = ""
    scene: str = ""
    applied: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RecoveryReport:
    actions: List[RecoveryAction] = field(default_factory=list)

    @property
    def needs_attention(self) -> bool:
        return bool(self.actions)

    def by_action(self, action: str) -> List[RecoveryAction]:
        return [a for a in self.actions if a.action == action]

    def summary(self) -> str:
        if not self.actions:
            return "Nothing to recover."
        parts = []
        for action, label in (("delete_partial", "half-finished download(s) cleaned"),
                              ("drop_render_cache_entry", "broken render-cache entr(ies) dropped"),
                              ("reresolve_asset", "scene file(s) missing — Generate will fetch them again"),
                              ("retry_job", "job(s) interrupted when the app closed")):
            n = len(self.by_action(action))
            if n:
                parts.append(f"{n} {label}")
        return "; ".join(parts) + "."

    def to_dict(self) -> dict:
        return {"actions": [a.to_dict() for a in self.actions], "summary": self.summary()}


def _media_dirs(workspace: Any) -> List[Path]:
    dirs = []
    for attr in ("assets_dir", "stock_dir", "youtube_dir", "flow_dir"):
        d = getattr(workspace, attr, None)
        if d is not None and Path(d).is_dir():
            dirs.append(Path(d))
    return dirs


def scan_project(workspace: Any, *, images_dir: Optional[Path] = None, ledger: Any = None) -> RecoveryReport:
    """Find what an interrupted session left behind. Read-only."""
    report = RecoveryReport()
    seen: set = set()
    folders = ([Path(images_dir)] if images_dir else []) + _media_dirs(workspace)
    for folder in folders:
        for pattern in _PARTIAL_PATTERNS:
            for p in folder.glob(pattern):  # top level only: scene media lives flat in these folders
                if p.is_file() and p not in seen:
                    seen.add(p)
                    report.actions.append(RecoveryAction("delete_partial", str(p), "half-written download"))

    state_dir = getattr(workspace, "state_dir", None)
    if state_dir is not None:
        report.actions.extend(_broken_render_cache_entries(Path(state_dir)))

    manifest_dir = Path(images_dir) if images_dir else getattr(workspace, "assets_dir", None)
    if manifest_dir is not None:
        report.actions.extend(_missing_manifest_files(Path(manifest_dir)))

    if ledger is not None:
        for job in ledger.interrupted():
            report.actions.append(RecoveryAction("retry_job", job.id, f"{job.type} was running when the app closed",
                                                 scene=job.scene or ""))
    return report


def _broken_render_cache_entries(state_dir: Path) -> List[RecoveryAction]:
    try:
        from render_cache import cache_clips_dir, cache_index_path

        index = json.loads(cache_index_path(state_dir).read_text(encoding="utf-8"))
        entries = index.get("entries") or {}
        clips = cache_clips_dir(state_dir)
    except (OSError, ValueError, AttributeError, ImportError):
        return []
    out = []
    for scene, entry in entries.items():
        name = (entry or {}).get("clip_file") if isinstance(entry, dict) else None
        clip = clips / name if name else None
        try:
            ok = clip is not None and clip.is_file() and clip.stat().st_size > 0
        except OSError:
            ok = False
        if not ok:
            out.append(RecoveryAction("drop_render_cache_entry", str(scene), "cached clip missing or empty", scene=str(scene)))
    return out


def _missing_manifest_files(images_dir: Path) -> List[RecoveryAction]:
    try:
        from asset_manager import MANIFEST_NAME

        data = json.loads((images_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError, ImportError):
        return []
    out = []
    for scene, rec in (data or {}).items():
        if not isinstance(rec, dict) or rec.get("status") != "complete":
            continue
        local = rec.get("local_path")
        if local and Path(local).is_file():
            continue
        try:
            import video_generator as vg

            if vg.find_image_for_scene(images_dir, str(scene)) is not None:
                continue
        except Exception:
            pass
        out.append(RecoveryAction("reresolve_asset", str(scene), "manifest says complete but the file is gone", scene=str(scene)))
    return out


def apply(report: RecoveryReport, workspace: Any) -> RecoveryReport:
    """Carry out the safe actions: delete partial downloads, drop broken render-cache entries. Missing assets and
    interrupted jobs are left for Generate / Retry (they need the providers). Never raises."""
    state_dir = getattr(workspace, "state_dir", None)
    drop = [a for a in report.actions if a.action == "drop_render_cache_entry"]
    for a in report.actions:
        if a.action == "delete_partial":
            try:
                p = Path(a.target)
                if p.is_file() and (p.name.endswith(".part") or p.name.endswith("_part.mp4")):
                    p.unlink()
                    a.applied = True
            except OSError:
                pass
    if drop and state_dir is not None:
        try:
            from render_cache import cache_index_path

            path = cache_index_path(Path(state_dir))
            index = json.loads(path.read_text(encoding="utf-8"))
            entries = index.get("entries") or {}
            for a in drop:
                if entries.pop(a.target, None) is not None:
                    a.applied = True
            index["entries"] = entries
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(index, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except (OSError, ValueError, ImportError):
            pass
    try:
        from production import events

        for a in report.actions:
            events.emit("recovery", action=a.action, scene=a.scene or None, detail=a.detail, applied=a.applied)
    except Exception:
        pass
    return report


def describe(error: Any, source: str = "") -> str:
    """One plain sentence for the UI: what happened and what to do."""
    fc = classify_failure(error, source)
    return fc.advice or "Unexpected failure."
