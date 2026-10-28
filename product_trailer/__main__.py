"""python -m product_trailer features.csv [--music track.mp3] [--out out.mp4] [--spec-only] [--seed N] [--size 1920x1080] [--fps 30]"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import build_spec, render


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="product_trailer", description="Feature CSV + music -> product trailer")
    ap.add_argument("csv")
    ap.add_argument("--music")
    ap.add_argument("--out", default=None, help="output mp4 (default: <csv>.mp4)")
    ap.add_argument("--work", default=None, help="folder for the spec (default: next to the output)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--spec-only", action="store_true")
    a = ap.parse_args(argv)
    w, h = (int(x) for x in a.size.lower().split("x"))
    out = Path(a.out or Path(a.csv).with_suffix(".mp4"))
    spec = build_spec(a.csv, a.music, Path(a.work or out.parent), width=w, height=h, fps=a.fps, seed=a.seed)
    print(f"spec: {spec}")
    if not a.spec_only:
        def show(f, t):
            print("\r%d/%d" % (f, t), end="", flush=True)

        print("\nvideo:", render(spec, out, progress=show))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
