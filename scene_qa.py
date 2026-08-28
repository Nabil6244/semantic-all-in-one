"""QA / error-management layer over existing scene results.

Single source of truth for the production header, Issues list, error navigation,
bulk-recovery targeting, and stale worker-callback tokens.

This module does not acquire assets, parse Activity Log text, or invent fallback
strategies — it reads current AssetResult / busy / skipped state and the scene's
existing SceneRecoveryTracker.next_alternative() paths.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from providers.base import AssetResult, AssetSource, SceneRow, SceneStatus
from providers.router import SceneAssetRouter
from scene_recovery import SceneRecoveryTracker, scene_key, summarize_assets

QA_FILE = ".scene_qa.json"

PROCESSING = frozenset({
    "retrying", "using_alternative", "generating", "searching",
    "downloading", "extracting", "cancelling", "matching", "adding_local",
})
QUEUED = frozenset({"waiting", "queued"})
UNRESOLVED = frozenset({
    "needs_action", "failed", "timeout", "cancelled",
})
READY = frozenset({"ready", "success"})

PROVIDER_LABELS = {
    "youtube_video": "YouTube Video",
    "youtube": "YouTube Video",
    AssetSource.YOUTUBE_VIDEO: "YouTube Video",
    "archive_video": "Internet Archive",
    "archive": "Internet Archive",
    AssetSource.ARCHIVE_VIDEO: "Internet Archive",
    "nasa_video": "NASA Media",
    "nasa": "NASA Media",
    AssetSource.NASA_VIDEO: "NASA Media",
    "commons_video": "Stock Video",
    "commons": "Stock Video",
    AssetSource.COMMONS_VIDEO: "Stock Video",
    "commons_image": "Stock Image",
    AssetSource.COMMONS_IMAGE: "Stock Image",
    "stock_video": "Stock Video",
    "stock": "Stock Video",
    AssetSource.STOCK_VIDEO: "Stock Video",
    AssetSource.STOCK: "Stock",
    "stock_image": "Stock Image",
    AssetSource.STOCK_IMAGE: "Stock Image",
    "flow_video": "Flow Video",
    "video": "Flow Video",
    AssetSource.FLOW_VIDEO: "Flow Video",
    "flow_image": "Flow Image",
    "image": "Flow Image",
    AssetSource.FLOW_IMAGE: "Flow Image",
    "manual": "Manual",
    AssetSource.MANUAL: "Manual",
    "local": "Local",
    AssetSource.LOCAL: "Local",
}

STATUS_LABELS = {
    "ready": "READY",
    "success": "READY",
    "needs_action": "NEEDS ACTION",
    "failed": "NEEDS ACTION",
    "timeout": "NEEDS ACTION",
    "cancelled": "CANCELLED",
    "skipped": "SKIPPED",
    "retrying": "RETRYING",
    "using_alternative": "USING ALTERNATIVE",
    "adding_local": "ADDING LOCAL CLIP",
    "generating": "GENERATING",
    "searching": "SEARCHING",
    "downloading": "DOWNLOADING",
    "waiting": "WAITING",
}


def provider_label(source) -> str:
    if source is None:
        return "Unknown"
    if isinstance(source, AssetSource):
        return PROVIDER_LABELS.get(source, source.value.replace("_", " ").title())
    key = str(source).strip().lower()
    return PROVIDER_LABELS.get(key, key.replace("_", " ").title())


def short_error(error: Optional[str], limit: int = 96) -> str:
    text = " ".join(str(error or "Needs action").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def classify_severity(error: Optional[str]) -> str:
    """Coarse bucket for UI chrome — not a new taxonomy of acquisition failures."""
    text = (error or "").lower()
    if any(token in text for token in ("missing required", "invalid project", "cannot render", "no ffmpeg")):
        return "blocking"
    if any(token in text for token in ("fallback", "quality", "duration adjusted")):
        return "warning"
    return "recoverable"


def alternative_label(action: dict) -> str:
    kind = action.get("kind")
    if kind == "youtube_query":
        return "YouTube (next query)"
    if kind == "provider":
        return provider_label(action.get("provider"))
    if kind == "regenerate_exclude":
        return "Same provider (new result)"
    return "No unused alternative"


@dataclass
class QAIssue:
    key: str
    scene_number: str
    provider: str
    error: str
    severity: str = "recoverable"


@dataclass
class QASnapshot:
    total: int = 0
    ready: int = 0
    needs_action: int = 0
    processing: int = 0
    skipped: int = 0
    waiting: int = 0
    unresolved_keys: List[str] = field(default_factory=list)
    issues: List[QAIssue] = field(default_factory=list)
    statuses: Dict[str, str] = field(default_factory=dict)
    header: str = ""
    health: str = "idle"
    health_label: str = ""
    error_counter: str = "0 NEEDS ACTION"
    allow_render: bool = False
    progress: float = 0.0
    go_to_error_label: str = "GO TO ERROR"
    visual_pass: int = 0
    visual_weak: int = 0
    visual_fail: int = 0
    visual_issues: List[QAIssue] = field(default_factory=list)
    visual_summary: str = ""

    @property
    def resolved(self) -> int:
        return self.ready + self.skipped


def format_header(snap: QASnapshot) -> str:
    if snap.total == 0:
        return "Choose a script CSV or analyze an AI Script"
    if snap.needs_action == 0 and snap.processing == 0 and snap.waiting == 0:
        return f"✓ {snap.ready} / {snap.total} READY"
    parts = [f"{snap.ready} / {snap.total} READY"]
    if snap.needs_action:
        parts.append(f"{snap.needs_action} NEEDS ACTION")
    if snap.processing:
        parts.append(f"{snap.processing} PROCESSING")
    if snap.waiting:
        parts.append(f"{snap.waiting} QUEUED")
    return " · ".join(parts)


def format_health(snap: QASnapshot) -> Tuple[str, str]:
    if snap.total == 0:
        return "idle", "Choose a script"
    if snap.needs_action and any(i.severity == "blocking" for i in snap.issues) and snap.processing == 0:
        return "blocking", "⛔ PIPELINE BLOCKED"
    if snap.processing:
        return "processing", "⟳ GENERATION IN PROGRESS"
    if snap.needs_action:
        noun = "SCENE" if snap.needs_action == 1 else "SCENES"
        return "partial", f"⚠ {snap.needs_action} {noun} NEED ATTENTION"
    return "healthy", "✓ PIPELINE HEALTHY"


class SceneQAState:
    """Current QA truth. Activity Log is never consulted."""

    def __init__(self) -> None:
        self.job_tokens: Dict[str, int] = {}
        self.busy: Dict[str, str] = {}
        self.attempts: Dict[str, int] = {}
        self.selected_failed: Set[str] = set()
        self.focused_key: Optional[str] = None
        self.filter_query: str = ""

    def begin_job(self, scene_number, kind: str) -> int:
        key = scene_key(scene_number)
        token = self.job_tokens.get(key, 0) + 1
        self.job_tokens[key] = token
        self.busy[key] = kind
        self.attempts[key] = self.attempts.get(key, 0) + 1
        return token

    def is_current(self, scene_number, token: int) -> bool:
        return self.job_tokens.get(scene_key(scene_number)) == token

    def apply_result(self, scene_number, token: int) -> bool:
        """Accept a worker result only if it belongs to the latest job for this scene."""
        if not self.is_current(scene_number, token):
            return False
        self.busy.pop(scene_key(scene_number), None)
        return True

    def clear_focus_if_resolved(self, unresolved: Sequence[str]) -> None:
        if self.focused_key and self.focused_key not in unresolved:
            self.focused_key = unresolved[0] if unresolved else None

    def row_status(
        self,
        scene: SceneRow,
        results: Dict[str, AssetResult],
        skipped: Set[str],
    ) -> str:
        key = scene_key(scene.scene_number)
        if key in self.busy:
            return self.busy[key]
        if key in skipped:
            return "skipped"
        result = results.get(key)
        if result is not None and getattr(result, "ok", False):
            return "ready"
        if result is not None:
            status = getattr(result.status, "value", result.status)
            if status == SceneStatus.SKIPPED or status == "skipped":
                return "skipped"
            if status == SceneStatus.CANCELLED or status == "cancelled":
                return "cancelled"
            if status in (SceneStatus.NEEDS_ACTION, SceneStatus.FAILED, SceneStatus.TIMEOUT) or status in UNRESOLVED:
                return "needs_action"
        if SceneAssetRouter.classify(scene) is None:
            return "waiting"
        if result is None:
            return "waiting"
        return "needs_action"

    def snapshot(
        self,
        scenes: Sequence[SceneRow],
        results: Dict[str, AssetResult],
        skipped: Optional[Set[str]] = None,
    ) -> QASnapshot:
        skipped = set(skipped or ())
        statuses: Dict[str, str] = {}
        issues: List[QAIssue] = []
        unresolved: List[str] = []
        ready = needs = processing = skipped_n = waiting = 0
        for scene in scenes:
            key = scene_key(scene.scene_number)
            status = self.row_status(scene, results, skipped)
            statuses[key] = status
            if status in PROCESSING:
                processing += 1
            elif status == "skipped":
                skipped_n += 1
            elif status in READY:
                ready += 1
            elif status in UNRESOLVED:
                needs += 1
                unresolved.append(key)
                result = results.get(key)
                source = getattr(result, "source", None) or SceneAssetRouter.classify(scene)
                err = getattr(result, "error", None) if result is not None else None
                issues.append(QAIssue(
                    key=key,
                    scene_number=str(scene.scene_number),
                    provider=provider_label(source),
                    error=short_error(err),
                    severity=classify_severity(err),
                ))
            elif status in QUEUED:
                waiting += 1
            else:
                waiting += 1
        snap = QASnapshot(
            total=len(scenes),
            ready=ready,
            needs_action=needs,
            processing=processing,
            skipped=skipped_n,
            waiting=waiting,
            unresolved_keys=unresolved,
            issues=issues,
            statuses=statuses,
        )
        stats = summarize_assets(
            [s.scene_number for s in scenes],
            results,
            skipped,
        )
        snap.allow_render = bool(stats["allow_render"]) and processing == 0
        snap.header = format_header(snap)
        snap.health, snap.health_label = format_health(snap)
        snap.error_counter = f"{snap.needs_action} NEEDS ACTION"
        if snap.total:
            if snap.needs_action == 0 and snap.processing == 0 and snap.waiting == 0:
                snap.progress = 1.0
            else:
                snap.progress = snap.ready / snap.total
        if unresolved:
            idx = unresolved.index(self.focused_key) + 1 if self.focused_key in unresolved else 1
            snap.go_to_error_label = f"GO TO ERROR {idx}/{len(unresolved)}"
        else:
            snap.go_to_error_label = "GO TO ERROR"
        self._append_visual_qa(snap, scenes, results)
        return snap

    def _append_visual_qa(
        self,
        snap: QASnapshot,
        scenes: Sequence[SceneRow],
        results: Dict[str, AssetResult],
    ) -> None:
        from visual_qa.models import VisualQAStatus

        for scene in scenes:
            key = scene_key(scene.scene_number)
            result = results.get(key)
            if result is None or not getattr(result, "ok", False):
                continue
            meta = getattr(result, "metadata", None) or {}
            raw = meta.get("visual_qa")
            if not isinstance(raw, dict):
                continue
            try:
                status = VisualQAStatus(str(raw.get("status") or ""))
            except ValueError:
                continue
            if status == VisualQAStatus.PASS:
                snap.visual_pass += 1
            elif status == VisualQAStatus.WEAK:
                snap.visual_weak += 1
                snap.visual_issues.append(QAIssue(
                    key=key,
                    scene_number=str(scene.scene_number),
                    provider=provider_label(getattr(result, "source", None)),
                    error=f"Visual QA: {raw.get('warnings', ['weak'])[0] if raw.get('warnings') else 'weak match'}",
                    severity="warning",
                ))
            elif status == VisualQAStatus.FAIL:
                snap.visual_fail += 1
                reasons = raw.get("failure_reasons") or raw.get("warnings") or ["visual QA failed"]
                snap.visual_issues.append(QAIssue(
                    key=key,
                    scene_number=str(scene.scene_number),
                    provider=provider_label(getattr(result, "source", None)),
                    error=f"Visual QA: {reasons[0]}",
                    severity="warning",
                ))
        if snap.visual_pass or snap.visual_weak or snap.visual_fail:
            total_v = snap.visual_pass + snap.visual_weak + snap.visual_fail
            snap.visual_summary = (
                f"VQA ✓{snap.visual_pass} ⚠{snap.visual_weak} ✕{snap.visual_fail} / {total_v}"
            )

    def go_to_error(self, unresolved: Sequence[str]) -> Optional[str]:
        if not unresolved:
            self.focused_key = None
            return None
        if self.focused_key not in unresolved:
            self.focused_key = unresolved[0]
        else:
            i = unresolved.index(self.focused_key)
            self.focused_key = unresolved[(i + 1) % len(unresolved)]
        return self.focused_key

    def next_error(self, unresolved: Sequence[str]) -> Optional[str]:
        return self.go_to_error(unresolved)

    def prev_error(self, unresolved: Sequence[str]) -> Optional[str]:
        if not unresolved:
            self.focused_key = None
            return None
        if self.focused_key not in unresolved:
            self.focused_key = unresolved[-1]
        else:
            i = unresolved.index(self.focused_key)
            self.focused_key = unresolved[(i - 1) % len(unresolved)]
        return self.focused_key

    def error_position(self, unresolved: Sequence[str]) -> str:
        if not unresolved:
            return "0 / 0"
        if self.focused_key in unresolved:
            return f"{unresolved.index(self.focused_key) + 1} / {len(unresolved)}"
        return f"1 / {len(unresolved)}"

    def prune_selection(self, alive_keys: Sequence[str]) -> None:
        """Keep selection only for scenes that still exist (any status)."""
        alive = set(alive_keys)
        self.selected_failed &= alive

    def select_all_failed(self, unresolved: Sequence[str]) -> None:
        self.selected_failed = set(unresolved)

    def clear_selection(self) -> None:
        self.selected_failed.clear()

    def targets(self, unresolved: Sequence[str], selected_only: bool) -> List[str]:
        if selected_only:
            return [k for k in unresolved if k in self.selected_failed]
        return list(unresolved)

    def scene_matches(self, scene: SceneRow, status: str, result: Optional[AssetResult]) -> bool:
        q = (self.filter_query or "").strip().lower()
        if not q:
            return True
        if q.isdigit():
            try:
                return int(str(scene.scene_number).strip()) == int(q)
            except ValueError:
                return str(scene.scene_number).strip() == q
        hay = [
            str(scene.scene_number),
            scene.script_segment or "",
            status,
            status.replace("_", " "),
            STATUS_LABELS.get(status, status),
            getattr(result, "error", None) or "",
            provider_label(getattr(result, "source", None) or SceneAssetRouter.classify(scene)),
        ]
        if q in {"failed", "fail", "error", "unresolved"} and status in UNRESOLVED:
            return True
        if q in {"ready", "success"} and status in READY:
            return True
        blob = " ".join(hay).lower()
        return q in blob or q in str(scene.scene_number)

    def details(
        self,
        scene: SceneRow,
        result: Optional[AssetResult],
        status: str,
        tracker: Optional[SceneRecoveryTracker] = None,
    ) -> dict:
        source = getattr(result, "source", None) or SceneAssetRouter.classify(scene)
        search = (scene.prompt or scene.stock or "").strip()
        fallback = ""
        if tracker is not None:
            action = tracker.next_alternative(scene)
            fallback = alternative_label(action)
        elif scene.fallbacks:
            fallback = provider_label(scene.fallbacks[0])
        duration = ""
        meta = getattr(result, "metadata", None) or {}
        if meta.get("duration") is not None:
            try:
                duration = f"{float(meta['duration']):.1f}s"
            except (TypeError, ValueError):
                duration = str(meta.get("duration"))
        attempt = self.attempts.get(scene_key(scene.scene_number), 0)
        if status in PROCESSING:
            actions = ["cancel"]
        elif status == "skipped":
            actions = ["retry", "local_clip", "change_source"]
        elif status in UNRESOLVED:
            actions = ["retry", "alternative", "local_clip", "skip", "change_source"]
        elif status in READY:
            actions = ["retry", "alternative", "local_clip", "change_source", "open"]
        else:
            actions = ["retry", "alternative", "local_clip", "change_source"]
        return {
            "title": f"Scene {scene.scene_number}",
            "status": STATUS_LABELS.get(status, status.replace("_", " ").upper()),
            "provider": provider_label(source),
            "search": search,
            "error": (getattr(result, "error", None) or "") if status in UNRESOLVED else "",
            "attempt": str(attempt) if attempt else "—",
            "duration": duration,
            "fallback": fallback,
            "actions": actions,
        }


def preview_alternatives(
    scenes: Sequence[SceneRow],
    tracker: SceneRecoveryTracker,
) -> List[Tuple[SceneRow, dict]]:
    """One existing next_alternative() per scene — no new acquisition strategy."""
    return [(scene, tracker.next_alternative(scene)) for scene in scenes]


def summarize_alternative_preview(previews: Sequence[Tuple[SceneRow, dict]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for _scene, action in previews:
        label = alternative_label(action)
        counts[label] = counts.get(label, 0) + 1
    return counts


def load_qa_file(images_dir: Path) -> dict:
    path = Path(images_dir) / QA_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_qa_file(images_dir: Path, attempts: Dict[str, int], skipped: Iterable[str]) -> None:
    path = Path(images_dir) / QA_FILE
    payload = {
        "attempts": {k: int(v) for k, v in attempts.items() if v},
        "skipped": sorted({scene_key(s) for s in skipped}),
    }
    try:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass
