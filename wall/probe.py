"""Stills of wall moments, for checks without a render.

    python -m wall.probe <plan.json> [--at 3,7.5,12 | --at 10%,50%,end] [--segment N] [--out DIR]

plan.json is a planner result ({"segments": [{"start", "end", "params"}]}) or one moment's params ({"items", "cam", "dur"}).
Times are seconds inside the moment, percentages of it, or 'start' / 'end'. Without --at: the hand-off in, the pull-back, five points
through the moment and the hand-off out. Writes seg<N>_<t>.jpg per still and one contact sheet per moment (sheet_<N>.jpg), and
prints the paths.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence

from PIL import Image, ImageDraw

from . import engine as E

DEFAULT = ["start", "0.6", "1.3", "20%", "35%", "50%", "65%", "80%", "92%", "end"]


def _times(spec: Sequence[str], dur: float) -> List[float]:
    out = []
    for s in spec:
        s = str(s).strip()
        if not s:
            continue
        if s == "start":
            t = 0.0
        elif s == "end":
            t = dur
        elif s.endswith("%"):
            t = dur * float(s[:-1]) / 100.0
        else:
            t = float(s)
        out.append(round(max(0.0, min(dur, t)), 3))
    return out


def stills(params: Dict[str, Any], times: Sequence[float], out_dir: Path, tag: str, label: str = "") -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    w = E.Wall(params)
    thumbs = []
    for t in times:
        im = w.render(t).convert("RGB")
        im.save(out_dir / f"{tag}_{t:06.2f}.jpg", quality=88)
        th = im.resize((480, 270))
        ImageDraw.Draw(th).text((8, 6), f"{label} t={t:.2f}", fill=(255, 255, 0))
        thumbs.append(th)
    cols = 3
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (480 * cols, 270 * rows), (0, 0, 0))
    for i, th in enumerate(thumbs):
        sheet.paste(th, ((i % cols) * 480, (i // cols) * 270))
    path = out_dir / f"sheet_{tag}.jpg"
    sheet.save(path, quality=85)
    return path


def main(argv: Sequence[str] = None) -> List[Path]:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("plan")
    ap.add_argument("--at", default=",".join(DEFAULT))
    ap.add_argument("--segment", type=int, default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    data = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    segs = data.get("segments") if isinstance(data, dict) and "segments" in data else [{"start": 0.0, "end": data.get("dur", 0), "params": data}]
    out = Path(a.out) if a.out else Path(a.plan).with_suffix("").with_name(Path(a.plan).stem + "_probe")
    sheets = []
    for i, s in enumerate(segs):
        if a.segment is not None and i != a.segment:
            continue
        p = s["params"]
        sheets.append(stills(p, _times(a.at.split(","), float(p.get("dur", 0))), out, f"seg{i:02d}",
                             f"#{i} {float(s.get('start', 0)):.1f}-{float(s.get('end', 0)):.1f}s"))
    for p in sheets:
        print(p)
    return sheets


if __name__ == "__main__":
    main()
