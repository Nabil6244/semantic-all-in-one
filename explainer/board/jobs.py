"""Board clips drawn after the plan: the director queues one job per board (cues + timing), and ensure_built() draws them all in parallel
just before the render. A job is skipped when its clip already exists, so a re-plan or a second render redraws nothing."""
from __future__ import annotations

import os
import pickle
from pathlib import Path
from typing import Callable, Dict, List, Sequence

PENDING = "pending_boards.pkl"
_WORDS: list = []


def queue(out_dir: "str | Path", words: Sequence, jobs: List[Dict]) -> None:
    """Write the jobs beside the clips (replacing an older queue); each job holds the build_board_clip arguments as a dict."""
    f = Path(out_dir) / PENDING
    if not jobs:
        f.unlink(missing_ok=True)
        return
    tmp = f.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps({"words": [tuple(w) for w in words], "jobs": jobs}))
    tmp.replace(f)


def _init(words) -> None:
    _WORDS[:] = [words]


def _draw(job: Dict) -> str:
    from .builder import build_board_clip
    build_board_clip(words=_WORDS[0], **job)
    return str(job["out_path"])


def ensure_built(out_dir: "str | Path", log: Callable[[str], None] = lambda m: None, max_workers: int = 0) -> int:
    """Draws every queued board that is not on disk yet. Returns how many could not be drawn (0 = all there). Never raises."""
    f = Path(out_dir) / PENDING
    try:
        data = pickle.loads(f.read_bytes())
    except (OSError, pickle.UnpicklingError, EOFError, ValueError, AttributeError, ImportError):
        return 0
    failed = run(data["words"], data["jobs"], log, max_workers)
    if not failed:
        f.unlink(missing_ok=True)
    return failed


def run(words, jobs, log: Callable[[str], None] = lambda m: None, max_workers: int = 0) -> int:
    """Draws the jobs whose clip is not on disk yet, in parallel when it can; returns how many failed."""
    todo = [j for j in jobs if not (Path(j["out_path"]).is_file() and Path(j["out_path"]).stat().st_size > 0)]
    failed: List[Dict] = []
    if todo:
        n = max_workers or max(1, min(8, (os.cpu_count() or 2) - 1, len(todo)))
        log(f"[Explainer] drawing {len(todo)} board clip(s) on {n} core(s)…")
        done = set()
        if n > 1 and len(todo) > 1:
            try:
                from concurrent.futures import ProcessPoolExecutor, as_completed
                with ProcessPoolExecutor(max_workers=n, initializer=_init, initargs=(words,)) as ex:
                    futs = {ex.submit(_draw, j): j for j in todo}
                    for fu in as_completed(futs):
                        try:
                            done.add(fu.result())
                        except Exception as exc:       # one bad board does not stop the rest; it is retried alone below
                            log(f"[Explainer] a board clip failed in parallel ({str(exc)[:120]}); retrying it alone")
            except Exception as exc:                   # no process pool here: draw them one after another
                log(f"[Explainer] the parallel drawing could not start ({str(exc)[:120]}); drawing one by one")
        _init(words)
        for j in todo:
            if str(j["out_path"]) in done:
                continue
            try:
                Path(j["out_path"]).unlink(missing_ok=True)
                _draw(j)
            except Exception as exc:
                failed.append(j)
                log(f"[Explainer] the board clip {Path(j['out_path']).name} could not be drawn ({str(exc)[:160]})")
    return len(failed)
