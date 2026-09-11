"""Numbered local-asset matching for Local Assets production mode.

Maps scene N → files named like ``001.ext`` / ``002.ext`` inside a user-chosen
folder. Media kind is taken from the CSV (``local_video`` / ``local_image``).

This module only finds and (optionally) installs paths. Timing, editorial
coverage, and rendering stay in the existing pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

import video_generator as vg

# Match the extensions the rest of the pipeline already understands.
IMAGE_EXTS = frozenset(e.lower() for e in vg.IMAGE_EXTS)
VIDEO_EXTS = frozenset(e.lower() for e in vg.VIDEO_EXTS)

LOCAL_VIDEO_TYPES = frozenset({"local_video"})
LOCAL_IMAGE_TYPES = frozenset({"local_image"})
LOCAL_NUMBERED_TYPES = LOCAL_VIDEO_TYPES | LOCAL_IMAGE_TYPES


@dataclass(frozen=True)
class LocalAssetMatch:
    """Successful numbered match (exactly one file of the requested kind)."""

    path: Path
    media_kind: str  # "image" | "video"
    scene_number: str
    expected_stem: str


@dataclass(frozen=True)
class LocalAssetIssue:
    """Why a scene could not be resolved from the local folder."""

    scene_number: str
    media_kind: str
    expected_stem: str
    reason: str
    code: str  # missing | wrong_type | ambiguous | bad_scene


def expected_stem(scene_number: str) -> str:
    """Canonical zero-padded stem used in error messages (Scene 57 → ``057``)."""
    try:
        return f"{int(str(scene_number).strip()):03d}"
    except ValueError:
        return str(scene_number).strip()


def media_kind_for_asset_type(asset_type: str) -> Optional[str]:
    key = (asset_type or "").strip().lower()
    if key in LOCAL_VIDEO_TYPES:
        return "video"
    if key in LOCAL_IMAGE_TYPES:
        return "image"
    return None


def is_local_numbered_type(asset_type: str) -> bool:
    return (asset_type or "").strip().lower() in LOCAL_NUMBERED_TYPES


def _stem_candidates(scene_number: str) -> List[str]:
    try:
        n = int(str(scene_number).strip())
    except ValueError:
        raw = str(scene_number).strip()
        return [raw] if raw else []
    # Prefer 001-style; also accept unpadded / alternate padding without inventing
    # a second identity system.
    out: List[str] = []
    for c in (f"{n:03d}", f"{n}", f"{n:02d}", f"{n:04d}"):
        if c not in out:
            out.append(c)
    return out


def _index_folder(folder: Path) -> dict[str, List[Path]]:
    """stem → list of media files (non-recursive; ignores junk / subfolders)."""
    by_stem: dict[str, List[Path]] = {}
    try:
        entries = list(folder.iterdir())
    except OSError:
        return {}
    for p in entries:
        if not p.is_file() or p.name.startswith("."):
            continue
        ext = p.suffix.lower()
        if ext not in IMAGE_EXTS and ext not in VIDEO_EXTS:
            continue
        by_stem.setdefault(p.stem, []).append(p)
    return by_stem


def find_numbered_asset(
    folder: Path,
    scene_number: str,
    media_kind: str,
) -> tuple[Optional[LocalAssetMatch], Optional[LocalAssetIssue]]:
    """Resolve Scene N to exactly one file of the requested media kind.

    Extra files for other scene numbers are ignored. Wrong media type for this
    scene number is a typed error (never silently substituted). Multiple files
    of the same kind for the same numeric identity are ambiguous.
    """
    folder = Path(folder)
    stem = expected_stem(scene_number)
    kind = (media_kind or "").strip().lower()
    if kind not in ("image", "video"):
        return None, LocalAssetIssue(
            scene_number=str(scene_number),
            media_kind=kind or "unknown",
            expected_stem=stem,
            reason=f"Unsupported local media kind: {media_kind!r}",
            code="bad_scene",
        )
    try:
        int(str(scene_number).strip())
    except ValueError:
        return None, LocalAssetIssue(
            scene_number=str(scene_number),
            media_kind=kind,
            expected_stem=stem,
            reason=f"Invalid scene number: {scene_number!r}",
            code="bad_scene",
        )

    if not folder.is_dir():
        return None, LocalAssetIssue(
            scene_number=str(scene_number),
            media_kind=kind,
            expected_stem=stem,
            reason=f"Local assets folder not found: {folder}",
            code="missing",
        )

    allowed = VIDEO_EXTS if kind == "video" else IMAGE_EXTS
    other = IMAGE_EXTS if kind == "video" else VIDEO_EXTS
    by_stem = _index_folder(folder)

    same_kind: List[Path] = []
    other_kind: List[Path] = []
    seen: set[str] = set()
    for candidate_stem in _stem_candidates(scene_number):
        for path in by_stem.get(candidate_stem, []):
            key = str(path.resolve()) if path.exists() else str(path)
            if key in seen:
                continue
            seen.add(key)
            ext = path.suffix.lower()
            if ext in allowed:
                same_kind.append(path)
            elif ext in other:
                other_kind.append(path)

    if len(same_kind) == 1:
        return (
            LocalAssetMatch(
                path=same_kind[0],
                media_kind=kind,
                scene_number=str(scene_number),
                expected_stem=stem,
            ),
            None,
        )

    if len(same_kind) > 1:
        names = ", ".join(p.name for p in same_kind[:6])
        more = f" (+{len(same_kind) - 6} more)" if len(same_kind) > 6 else ""
        return None, LocalAssetIssue(
            scene_number=str(scene_number),
            media_kind=kind,
            expected_stem=stem,
            reason=(
                f"Ambiguous local {kind} for scene {scene_number}: "
                f"multiple matches for {stem}.* ({names}{more})"
            ),
            code="ambiguous",
        )

    if other_kind:
        found = other_kind[0].name
        expected_ext = "mp4" if kind == "video" else "jpg"
        return None, LocalAssetIssue(
            scene_number=str(scene_number),
            media_kind=kind,
            expected_stem=stem,
            reason=(
                f"Expected local {kind}: {stem}.{expected_ext} "
                f"(found wrong type: {found})"
            ),
            code="wrong_type",
        )

    expected_ext = "mp4" if kind == "video" else "jpg"
    return None, LocalAssetIssue(
        scene_number=str(scene_number),
        media_kind=kind,
        expected_stem=stem,
        reason=f"Local asset not found — expected local {kind}: {stem}.{expected_ext}",
        code="missing",
    )


@dataclass
class LocalAssetCheckRow:
    scene_number: str
    media_kind: str
    ok: bool
    label: str
    detail: str


def check_local_assets(
    folder: Path,
    scenes: Sequence,
) -> tuple[List[LocalAssetCheckRow], int, int]:
    """Lightweight folder vs CSV check for the Local Assets UI / Visual Plan prep.

    Returns (rows, ready_count, needs_action_count). Extra files in the folder
    are ignored.
    """
    rows: List[LocalAssetCheckRow] = []
    ready = 0
    needs = 0
    for scene in scenes:
        asset_type = getattr(scene, "asset_type", "") or ""
        kind = media_kind_for_asset_type(asset_type)
        if kind is None:
            # Non-local CSV rows in this mode still surface as needs-action so
            # the operator can fix the CSV rather than silently mixing providers.
            sn = str(getattr(scene, "scene_number", "") or "")
            rows.append(
                LocalAssetCheckRow(
                    scene_number=sn,
                    media_kind="unknown",
                    ok=False,
                    label=f"Scene {sn}",
                    detail=f"asset_type must be local_video or local_image (got {asset_type!r})",
                )
            )
            needs += 1
            continue
        match, issue = find_numbered_asset(folder, scene.scene_number, kind)
        stem = expected_stem(scene.scene_number)
        if match is not None:
            rows.append(
                LocalAssetCheckRow(
                    scene_number=str(scene.scene_number),
                    media_kind=kind,
                    ok=True,
                    label=f"✓ {match.path.name} → Scene {scene.scene_number}",
                    detail="",
                )
            )
            ready += 1
        else:
            assert issue is not None
            rows.append(
                LocalAssetCheckRow(
                    scene_number=str(scene.scene_number),
                    media_kind=kind,
                    ok=False,
                    label=f"⚠ {stem}.* → Scene {scene.scene_number} missing",
                    detail=issue.reason,
                )
            )
            needs += 1
    return rows, ready, needs
