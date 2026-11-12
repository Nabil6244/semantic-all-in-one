"""War render: draw ONE piece in its own process (owner 2026-11-12: "make it ultra fast").

The War renderer draws every frame in Python. In threads, Python draws on about one core at a time, so a 25-min film used ~4 of 8 cores.
segments._render_piece_any starts `python -m cinematic_explainer.war.segment_worker <job.pkl>` per piece: each piece is drawn on its own
core and piped to its own ffmpeg, exactly as segments._render_piece does in a thread (same code, same frames).

Job (pickle): {"piece", "layers", "out", "codec", "cancel_flag"}. Result (json next to the job): {"ok", "errors", "stats", "kind", "msg"}.
"""

from __future__ import annotations

import json
import os
import pickle
import sys
import threading
import traceback
from pathlib import Path


def run(job_path: str) -> int:
    from . import segments as S

    job = pickle.loads(Path(job_path).read_bytes())
    res_path = Path(job_path).with_suffix(".result.json")
    flag = str(job.get("cancel_flag") or "")
    errors: list = []
    stats: dict = {}
    procs: set = set()
    lock = threading.Lock()
    out = {"ok": False, "errors": errors, "stats": stats, "kind": "", "msg": ""}
    try:
        S._render_piece(job["piece"], job["layers"], Path(job["out"]), job["codec"], job.get("cards") or S.all_cards(),
                        (lambda: bool(flag) and os.path.exists(flag)), errors, procs, lock, stats)
        out["ok"] = True
    except S.RenderCancelled:
        out["kind"] = "cancelled"
    except S.RenderError as exc:
        out["kind"], out["msg"] = "render", str(exc)[-1500:]
    except BaseException as exc:  # noqa: BLE001 - reported to the parent, which decides
        out["kind"], out["msg"] = "crash", (traceback.format_exc()[-1500:] or str(exc))
    res_path.write_text(json.dumps(out, default=str), encoding="utf-8")
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1]))
