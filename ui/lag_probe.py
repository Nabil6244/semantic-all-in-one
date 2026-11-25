"""Freeze recorder: finds what makes the window lag, on the machine where it lags.

A 50 ms timer on the main (Tk) thread says "alive". A watcher thread notices when it has not for LAG_S, and while the
window stays frozen it samples the main thread's Python stack every 50 ms. When the freeze ends, the stack seen most
often is the code that froze the window. Every freeze is added to a report (worst code first): ~/SYT_lag_report.txt.

Costs nothing while the window is responsive (one timer tick, one thread asleep). Off switch: SYT_NO_LAG_PROBE=1.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import traceback
from collections import Counter
from pathlib import Path

LAG_S = 0.3          # a freeze shorter than this is not recorded
TICK_MS = 50
SAMPLE_S = 0.05
_HERE = str(Path(__file__).resolve().parent.parent)

_STATE: dict = {}


def report_path() -> Path:
    return Path.home() / "SYT_lag_report.txt"


def _where(frame) -> str:
    """The stack as text, newest call last; the app's own files only once the library frames are cut (plus the call into them)."""
    rows = traceback.extract_stack(frame)
    mine = [i for i, r in enumerate(rows) if r.filename.startswith(_HERE) and "site-packages" not in r.filename]
    if mine:   # from the app's outermost-but-useful frames to the deepest app frame, then one library frame it called
        last = mine[-1]
        rows = rows[max(0, last - 14): last + 2]
    else:
        rows = rows[-8:]
    out = []
    for r in rows:
        name = r.filename[len(_HERE) + 1:] if r.filename.startswith(_HERE) else Path(r.filename).name
        out.append(f"{name}:{r.lineno} {r.name}")
    return "\n    ".join(out)


def _write(stats: dict, recent: list) -> None:
    lines = [f"Semantic YT Studio freeze report ({time.strftime('%Y-%m-%d %H:%M')})",
             f"Window freezes longer than {LAG_S:.1f} s, grouped by the code that was running (most frozen time first).", ""]
    for stack, (n, total, worst) in sorted(stats.items(), key=lambda kv: -kv[1][1])[:25]:
        lines += [f"{total:7.1f} s frozen in {n} freeze(s), worst {worst:.1f} s:", "    " + stack, ""]
    lines += ["Last freezes:"] + [f"  {t}  {d:5.1f} s  {s.splitlines()[-1].strip() if s else '?'}" for t, d, s in recent[-30:]]
    try:
        tmp = report_path().with_suffix(".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(tmp, report_path())
    except OSError:
        pass


def start(root) -> bool:
    """Watch ``root``'s main loop. Call once after the window exists."""
    if os.environ.get("SYT_NO_LAG_PROBE") or _STATE.get("on"):
        return False
    main_id = threading.get_ident()
    alive = [time.monotonic()]
    _STATE.update(on=True, root=root)

    def tick():
        alive[0] = time.monotonic()
        try:
            root.after(TICK_MS, tick)
        except Exception:
            _STATE["on"] = False

    def watch():
        stats: dict = {}
        recent: list = []
        while _STATE.get("on"):
            time.sleep(SAMPLE_S)
            began = alive[0]
            if time.monotonic() - began < LAG_S:
                continue
            seen: Counter = Counter()
            while alive[0] == began and _STATE.get("on"):   # frozen: sample until the tick runs again
                frame = sys._current_frames().get(main_id)
                if frame is not None:
                    seen[_where(frame)] += 1
                del frame
                time.sleep(SAMPLE_S)
            took = time.monotonic() - began
            if not seen:
                continue
            stack = seen.most_common(1)[0][0]
            n, total, worst = stats.get(stack, (0, 0.0, 0.0))
            stats[stack] = (n + 1, total + took, max(worst, took))
            recent.append((time.strftime("%H:%M:%S"), took, stack))
            _write(stats, recent)

    try:
        root.after(TICK_MS, tick)
        threading.Thread(target=watch, name="lag-probe", daemon=True).start()
    except Exception:
        _STATE["on"] = False
        return False
    return True
