"""Deterministic QA result cache."""

from __future__ import annotations

import atexit
import hashlib
import itertools
import json
import os
import threading
import time
from pathlib import Path
from typing import Optional

from .models import QA_ENGINE_VERSION, VisualQAResult

CACHE_FILE = ".visual_qa_cache.json"

# Stores are coalesced: the first store writes at once, later ones within this
# many seconds of the previous write are written together by a short timer
# (and at interpreter exit / flush_cache()). The file on disk is therefore at
# most this stale, and is always a complete JSON document (atomic replace).
FLUSH_INTERVAL_S = 0.5


def _file_identity(asset_path: Path) -> str:
    """Cheap content identity: size + nanosecond mtime.

    The cache key used to be the PATH alone, but a retry regenerates a
    DIFFERENT image to the SAME path (001.png), so the re-evaluation after a
    retry was served the previous image's verdict. Both stat fields change
    when a file is rewritten, so a regenerated asset misses the cache and is
    scored fresh. Returns "" when the file is unreadable, which simply falls
    back to the old path-only behaviour rather than raising."""
    try:
        st = Path(asset_path).stat()
    except OSError:
        return ""
    return f"{st.st_size}:{st.st_mtime_ns}"


def _fingerprint(
    asset_path: str,
    scene_number: str,
    style_id: str = "",
    coverage_version: str = "",
    file_identity: str = "",
) -> str:
    raw = (
        f"{QA_ENGINE_VERSION}|{asset_path}|{file_identity}"
        f"|{scene_number}|{style_id}|{coverage_version}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def load_cache(images_dir: Path) -> dict:
    path = Path(images_dir) / CACHE_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


_tmp_counter = itertools.count()

# Windows refuses os.replace() onto a file another handle has open (another process reading the cache,
# antivirus, the search indexer): PermissionError. Those handles last milliseconds, so retry; if the
# target stays locked, write in place as the code did before atomic writes (never worse than before).
_REPLACE_RETRIES = 40
_REPLACE_BACKOFF_S = 0.025


def _replace_with_retry(tmp: Path, path: Path, text: str) -> None:
    for attempt in range(_REPLACE_RETRIES):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(_REPLACE_BACKOFF_S * min(attempt + 1, 4))
    path.write_text(text, encoding="utf-8")  # the pre-atomic behaviour
    try:
        tmp.unlink()
    except OSError:
        pass


def _atomic_write_json(path: Path, cache: dict) -> None:
    """Write next to the target, then os.replace(): a reader (another
    process, starmap.media) or a crash mid-write never sees a half file.
    os.open with 0o666 keeps the umask-derived mode write_text produced."""
    text = json.dumps(cache, indent=2)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{next(_tmp_counter)}.tmp")
    try:
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        _replace_with_retry(tmp, path, text)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def save_cache(images_dir: Path, cache: dict) -> None:
    path = Path(images_dir) / CACHE_FILE
    with _LOCK:
        _atomic_write_json(path, cache)
        st = _STATES.get(_state_key(path))
        if st is not None:
            # An explicit save replaces the file wholesale, exactly as before.
            st.data = json.loads(json.dumps(cache))
            st.dirty.clear()
            st.sig = _disk_sig(path)
            st.last_flush = time.monotonic()


# ---------------------------------------------------------------------------
# In-memory view of each cache file for the run.
#
# Before: every get_cached() parsed the whole JSON and every store_cached()
# parsed + rewrote it, O(n^2) for an n-scene run (1200 rows: ~5 s). Now each
# file is parsed once and kept in memory; it is re-read only when its on-disk
# signature (mtime_ns, size, inode) changes, i.e. someone else wrote it, so a
# second process or a direct writer is still seen. Writes are coalesced (see
# FLUSH_INTERVAL_S) and atomic. When the file changed underneath us, a flush
# re-reads it and re-applies only our pending entries on top (the old
# read-modify-write merge); when it was deleted, our view is dropped, as the
# deletion would have dropped those entries before.
# ---------------------------------------------------------------------------

_LOCK = threading.RLock()


class _FileState:
    __slots__ = ("path", "data", "sig", "dirty", "last_flush", "timer")

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict = {}
        self.sig = False  # never synced
        self.dirty: dict = {}
        self.last_flush = float("-inf")
        self.timer: Optional[threading.Timer] = None


_STATES: dict = {}


def _state_key(path: Path) -> str:
    return os.path.abspath(str(path))


def _disk_sig(path: Path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size, st.st_ino)


def _state_for(path: Path) -> _FileState:
    key = _state_key(path)
    st = _STATES.get(key)
    if st is None:
        st = _STATES[key] = _FileState(path)
    return st


def _read_existing(path: Path) -> Optional[dict]:
    """The file's contents, or None when it exists but can't be read right now.
    On Windows a reader gets PermissionError for the instant another process
    replaces the file; reading that as "empty" made the next flush drop every
    entry already written."""
    for attempt in range(_REPLACE_RETRIES):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            return {}  # a genuinely broken file is rebuilt, as before
        except OSError:
            time.sleep(_REPLACE_BACKOFF_S * min(attempt + 1, 4))
    return None


def _sync(st: _FileState) -> None:
    """Bring st.data in line with the disk (call with _LOCK held)."""
    cur = _disk_sig(st.path)
    if cur == st.sig:
        return
    if cur is None:
        if st.sig not in (False, None):
            st.dirty.clear()  # file deleted since we last saw it
        data = {}
    else:
        data = _read_existing(st.path)
        if data is None:
            return  # still locked: keep our view and try again next time
    st.data = data
    st.data.update(st.dirty)
    st.sig = cur


def _flush_state(st: _FileState) -> None:
    """Write pending entries (call with _LOCK held). Raises on I/O error,
    leaving the entries pending."""
    if st.timer is not None:
        st.timer.cancel()
        st.timer = None
    if not st.dirty:
        return
    _sync(st)
    _atomic_write_json(st.path, st.data)
    st.sig = _disk_sig(st.path)
    st.dirty.clear()
    st.last_flush = time.monotonic()


def _timer_flush(st: _FileState) -> None:
    with _LOCK:
        st.timer = None
        try:
            _flush_state(st)
        except Exception:
            pass  # retried on the next store / flush_cache() / exit


def flush_cache(images_dir: Optional[Path] = None) -> None:
    """Write pending cache entries now (one folder, or all). Errors are
    swallowed for the all-folders form (used at exit)."""
    with _LOCK:
        if images_dir is not None:
            st = _STATES.get(_state_key(Path(images_dir) / CACHE_FILE))
            if st is not None:
                _flush_state(st)
            return
        for st in list(_STATES.values()):
            try:
                _flush_state(st)
            except Exception:
                pass


atexit.register(flush_cache)


def get_cached(
    images_dir: Path,
    asset_path: Path,
    scene_number: str,
    *,
    style_id: str = "",
) -> Optional[VisualQAResult]:
    fp = _fingerprint(
        str(asset_path.resolve()), scene_number, style_id,
        file_identity=_file_identity(asset_path),
    )
    with _LOCK:
        st = _state_for(Path(images_dir) / CACHE_FILE)
        _sync(st)
        raw = st.data.get(fp)
    if not isinstance(raw, dict):
        return None
    return VisualQAResult.from_dict(raw)


def store_cached(
    images_dir: Path,
    asset_path: Path,
    scene_number: str,
    result: VisualQAResult,
    *,
    style_id: str = "",
) -> None:
    fp = _fingerprint(
        str(Path(asset_path).resolve()), scene_number, style_id,
        file_identity=_file_identity(Path(asset_path)),
    )
    # JSON round trip: the in-memory entry is exactly what a re-read of the
    # file would give (and a non-serialisable value fails here, as before).
    entry = json.loads(json.dumps(result.to_dict()))
    with _LOCK:
        st = _state_for(Path(images_dir) / CACHE_FILE)
        _sync(st)
        st.data[fp] = entry
        st.dirty[fp] = entry
        wait = st.last_flush + FLUSH_INTERVAL_S - time.monotonic()
        if wait <= 0:
            _flush_state(st)
        elif st.timer is None:
            st.timer = threading.Timer(wait, _timer_flush, args=(st,))
            st.timer.daemon = True
            st.timer.start()
