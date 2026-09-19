"""In-process media-duration memoization (Semantic YT Studio 2.0 — Batch 1, PHASE 7).

The pipeline probes the same source files with ffprobe repeatedly across
different stages (editorial candidate-building, asset-duration annotation,
hold_tail rendering, post-mux QA — see investigation notes). This module
adds a conservative, process-local cache in front of
`media_duration.probe_media_duration` so the same unchanged file is only
ever probed once per run.

Cache identity is (resolved path, size, mtime_ns) — NOT trusted blindly:
if the file's size/mtime has changed since it was last probed, that is a
different cache key, so ffprobe runs again automatically. There is no
persistence across runs (process-local only) and no assumption that an
unprobed or unstat-able file is anything but a fresh probe.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

_lock = threading.Lock()
_cache: dict[tuple, Optional[float]] = {}


def _identity(path) -> Optional[tuple]:
    try:
        p = Path(path)
        st = p.stat()
        return (str(p.resolve()), st.st_size, st.st_mtime_ns)
    except OSError:
        return None


def cached_probe_duration(path, probe_fn: Callable[..., Optional[float]], *args, **kwargs) -> Optional[float]:
    """Call `probe_fn(path, *args, **kwargs)`, memoized by file identity.

    `probe_fn` is the real ffprobe-backed function to fall back to (e.g.
    `media_duration.probe_media_duration`) — ffprobe itself remains
    authoritative; this only avoids re-invoking it for a file whose
    (path, size, mtime) hasn't changed since the last call in this process.
    If the file can't be stat()'d, caching is skipped entirely and probe_fn
    is called directly every time (fail open to "always probe", never to a
    stale/wrong cached value).
    """
    key = _identity(path)
    if key is None:
        return probe_fn(path, *args, **kwargs)
    with _lock:
        if key in _cache:
            return _cache[key]
    # Probe outside the lock — ffprobe is a subprocess call, no need to
    # serialize unrelated files' probes behind one lock.
    result = probe_fn(path, *args, **kwargs)
    with _lock:
        _cache[key] = result
    return result


def clear() -> None:
    """Reset the in-process cache — used between test cases, and safe to
    call at the start of a fresh render run if a caller wants a clean slate
    (not required for correctness, since stale entries self-invalidate via
    the mtime/size key, but avoids unbounded growth across many runs in one
    long-lived process)."""
    with _lock:
        _cache.clear()


def size() -> int:
    with _lock:
        return len(_cache)
