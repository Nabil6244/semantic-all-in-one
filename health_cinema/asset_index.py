"""The Health Cinema asset index: every model / anchors / illustration-library file is read once and remembered by its size and modification time, and
which 3D templates can render is kept in a small persistent index, so planning a video never re-reads or re-checks the same files.

Incremental: an entry is reused only while every file it came from is unchanged (same size and mtime); a changed or new file is read again on its
next use. Nothing is scanned up front. HEALTH_CINEMA_ASSET_INDEX moves the index file (tests)."""
from __future__ import annotations
import json, os, threading
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

INDEX = Path(os.environ.get("HEALTH_CINEMA_ASSET_INDEX", str(Path.home() / ".semantic_yt_studio" / "health_cinema" / "asset_index.json")))
_LOCK = threading.Lock()
_JSON: Dict[str, Tuple[tuple, object]] = {}
STATS = {"json_hits": 0, "json_reads": 0, "ready_hits": 0, "ready_checks": 0}
_ready: Optional[dict] = None


def _stat(path) -> tuple:
    try:
        st = os.stat(path); return (str(path), st.st_mtime_ns, st.st_size)
    except OSError:
        return (str(path), None, None)


def load_json(path) -> object:
    """A JSON file, read once while it is unchanged."""
    k = _stat(path)
    with _LOCK:
        hit = _JSON.get(str(path))
        if hit and hit[0] == k: STATS["json_hits"] += 1; return hit[1]
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    with _LOCK:
        _JSON[str(path)] = (k, data); STATS["json_reads"] += 1
    return data


def _load_ready() -> dict:
    global _ready
    if _ready is None:
        try: _ready = json.loads(INDEX.read_text(encoding="utf-8")).get("templates", {})
        except (OSError, ValueError): _ready = {}
    return _ready


def _save_ready() -> None:
    try:
        for t in [t for t, e in _ready.items() if not all(os.path.exists(f[0]) for f in e.get("files", []))]: del _ready[t]      # files gone (a test's temp folder): forget them
        INDEX.parent.mkdir(parents=True, exist_ok=True); tmp = INDEX.with_suffix(".tmp")
        tmp.write_text(json.dumps({"templates": _ready}, separators=(",", ":")), encoding="utf-8"); os.replace(tmp, INDEX)
    except OSError:
        pass      # a read-only home only loses the memory between runs


def template_ready(template: str, files: Tuple[str, ...], check: Callable[[], bool]) -> bool:
    """Whether `template` can render, from the index while its files are unchanged; otherwise `check()` decides and the answer is stored."""
    key = [list(_stat(f)) for f in files]
    with _LOCK:
        ready = _load_ready(); hit = ready.get(template)
        if hit is not None and hit.get("files") == key: STATS["ready_hits"] += 1; return bool(hit["ready"])
    ok = bool(check())
    with _LOCK:
        STATS["ready_checks"] += 1; _load_ready()[template] = {"files": key, "ready": ok}; _save_ready()
    return ok
