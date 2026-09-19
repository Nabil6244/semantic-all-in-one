"""Project-scoped scene render cache (Semantic YT Studio 2.0 — Batch 1).

Conservative-by-design: the cache key is built from every material input
that `video_generator._render_scene_clip()` actually receives (source asset
identity, timing, overlays, transitions, edit decision, encoder args), plus
a schema version this module controls. Any uncertainty — a stat() failure,
a missing cached clip file, a corrupt/empty cached clip, an unparsable
cache-metadata file — is treated as a cache MISS, never a stale hit. See
PHASE 4/5 of the Batch 1 plan: "If there is uncertainty, treat it as CACHE
MISS... Correctness is more important than hit rate."

Storage layout (mirrors editorial/persistence.py's convention):
  <project>/state/render_cache.json          — {scene_key: {cache_key, clip_file, ...}}
  <project>/state/render_cache/clips/        — the actual cached scene-clip files

Both are project-scoped (under the project's own state_dir) — no global
mutable cache exists, so two different projects can never share an entry
even if scene numbers/filenames coincide (PHASE 6).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Optional

RENDER_CACHE_SCHEMA_VERSION = 1
CACHE_INDEX_NAME = "render_cache.json"
CACHE_CLIPS_DIRNAME = "render_cache"


def cache_index_path(state_dir: Path) -> Path:
    return Path(state_dir) / CACHE_INDEX_NAME


def cache_clips_dir(state_dir: Path) -> Path:
    return Path(state_dir) / CACHE_CLIPS_DIRNAME


def _file_identity(path: Any) -> Optional[list]:
    """[resolved_path_str, size, mtime_ns] for a real file, or None if the
    path is falsy. Never raises — an unreadable file just yields a
    (path, None, None) tuple, which simply can never match a future stat()
    that succeeds, i.e. it behaves as "always miss" for that input, which is
    the safe direction (see module docstring)."""
    if not path:
        return None
    try:
        p = Path(path)
        st = p.stat()
        return [str(p.resolve()), st.st_size, st.st_mtime_ns]
    except OSError:
        return [str(path), None, None]


def build_scene_cache_key(
    *,
    scene_number: Any,
    img_path: Any,
    duration: float,
    width: int,
    height: int,
    fps: int,
    zoom: bool,
    zoom_in: bool,
    zoom_amount: float,
    caption_overlay: Any = None,
    text_effect_filters: str = "",
    timed_overlays: Optional[list] = None,
    fade_in: float = 0.0,
    fade_out: float = 0.0,
    fade_color: str = "black",
    camera_style: Optional[str] = None,
    avoid_blind_loop: bool = False,
    edit_decision: Optional[dict] = None,
    encode_args: Optional[list] = None,
) -> str:
    """Deterministic sha256 key over every material input to one scene's
    render. Same inputs -> same key, always; any single differing input
    (source asset content, timing, transitions, graphics/text state,
    EditDecision/ShotSpec, encoder settings) -> a different key, i.e. a miss.
    """
    overlays_sig = []
    for item in timed_overlays or []:
        png = item[0] if len(item) > 0 else None
        t0 = item[1] if len(item) > 1 else None
        t1 = item[2] if len(item) > 2 else None
        anim = item[3] if len(item) > 3 else None
        center = item[4] if len(item) > 4 else None
        overlays_sig.append(
            [
                _file_identity(png),
                round(float(t0), 4) if t0 is not None else None,
                round(float(t1), 4) if t1 is not None else None,
                anim,
                list(center) if center else None,
            ]
        )

    edit_decision_sources = []
    if isinstance(edit_decision, dict):
        for shot in edit_decision.get("shots") or []:
            if isinstance(shot, dict) and shot.get("source_path"):
                edit_decision_sources.append(_file_identity(shot.get("source_path")))

    payload = {
        "schema_version": RENDER_CACHE_SCHEMA_VERSION,
        "scene_number": str(scene_number),
        "source": _file_identity(img_path),
        "duration": round(float(duration), 4),
        "width": int(width),
        "height": int(height),
        "fps": int(fps),
        "zoom": bool(zoom),
        "zoom_in": bool(zoom_in),
        "zoom_amount": round(float(zoom_amount), 4),
        "caption_overlay": _file_identity(caption_overlay),
        "text_effect_filters": text_effect_filters or "",
        "timed_overlays": overlays_sig,
        "fade_in": round(float(fade_in), 4),
        "fade_out": round(float(fade_out), 4),
        "fade_color": fade_color or "black",
        "camera_style": camera_style,
        "avoid_blind_loop": bool(avoid_blind_loop),
        "edit_decision": edit_decision,
        "edit_decision_sources": edit_decision_sources,
        "encode_args": list(encode_args) if encode_args else [],
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RenderCache:
    """One instance per render run, scoped to one project's state_dir.

    Not a global/shared cache — each instance only ever reads/writes its
    own project's render_cache.json and render_cache/clips/ directory, so
    two projects opened in the same process can never cross-contaminate
    (PHASE 6). Old projects with no render_cache.json at all simply behave
    as 100% cache-miss (PHASE 15) — nothing about loading requires the file
    to pre-exist.
    """

    def __init__(self, state_dir: Path):
        self.state_dir = Path(state_dir)
        self._index_path = cache_index_path(self.state_dir)
        self._clips_dir = cache_clips_dir(self.state_dir)
        self._entries: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        try:
            if not self._index_path.is_file():
                return
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            if int(data.get("schema_version") or 0) != RENDER_CACHE_SCHEMA_VERSION:
                # A schema bump invalidates the whole cache outright, same
                # convention as editorial/persistence.py's exact-match gate.
                return
            entries = data.get("entries")
            if isinstance(entries, dict):
                self._entries = entries
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            # Any corruption/unreadability -> start with an empty cache
            # (every scene misses), never crash the pipeline over this.
            self._entries = {}

    def _save(self) -> None:
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            payload = {"schema_version": RENDER_CACHE_SCHEMA_VERSION, "entries": self._entries}
            self._index_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            # Persisting the cache is best-effort — losing it just means the
            # next run starts cold, never a pipeline failure.
            pass

    def get(self, scene_key: str, cache_key: str) -> Optional[Path]:
        """Returns a Path to a valid, reusable cached clip, or None (miss).

        A hit requires: an index entry exists for this scene, its stored
        cache_key matches exactly, AND the referenced clip file actually
        exists on disk and is non-empty. Any single failing condition is a
        miss — scene number matching or filename matching alone is never
        sufficient (PHASE 4's explicit requirement).
        """
        entry = self._entries.get(str(scene_key))
        if not isinstance(entry, dict):
            return None
        if entry.get("cache_key") != cache_key:
            return None
        clip_name = entry.get("clip_file")
        if not clip_name:
            return None
        clip_path = self._clips_dir / clip_name
        try:
            if not clip_path.is_file() or clip_path.stat().st_size <= 0:
                return None
        except OSError:
            return None
        return clip_path

    def put(self, scene_key: str, cache_key: str, rendered_clip: Path) -> None:
        """Copy a freshly-rendered clip into the persistent cache and record
        its key. Best-effort: a failure here never raises — it just means
        this scene won't be cached this run (still renders fine now, will
        simply miss and re-render next time instead of reusing)."""
        try:
            if not Path(rendered_clip).is_file():
                return
            self._clips_dir.mkdir(parents=True, exist_ok=True)
            clip_name = f"scene_{str(scene_key)}_{cache_key[:16]}{Path(rendered_clip).suffix}"
            dest = self._clips_dir / clip_name
            shutil.copy2(rendered_clip, dest)
            self._entries[str(scene_key)] = {"cache_key": cache_key, "clip_file": clip_name}
            self._save()
        except (OSError, shutil.Error):
            pass

    def reuse(self, cached_clip: Path, out_path: Path) -> bool:
        """Copy a cache hit into the run's expected clip location. Returns
        False (never raises) if the copy fails for any reason — the caller
        must then fall back to a normal render, exactly as on a cache miss."""
        try:
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cached_clip, out_path)
            return Path(out_path).is_file() and Path(out_path).stat().st_size > 0
        except (OSError, shutil.Error):
            return False
