"""python -m map_scene "Florida > Florida Panhandle" -o panhandle.mp4 [--duration 10]"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .places import PlaceNotFound
from .render import DEFAULT_DURATION_S, MapRenderError, render_map
from .spec import MapPromptError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m map_scene", description="Render a map scene to MP4.")
    parser.add_argument("prompt", help='e.g. "Florida > Florida Panhandle | camera: zoom_in"')
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION_S)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--size", default="1920x1080")
    parser.add_argument("--ai", action="store_true", help="Ask Gemini for places not in the bundled data")
    args = parser.parse_args(argv)
    width, height = (int(v) for v in args.size.lower().split("x"))
    ai = None
    if args.ai:
        from .ai_places import gemini_place_resolver

        ai = gemini_place_resolver()
    start = time.monotonic()
    try:
        result = render_map(args.prompt, Path(args.output), duration=args.duration, fps=args.fps,
                            width=width, height=height, ai=ai,
                            progress=lambda f, n: print(f"\r  frame {f}/{n}", end="", flush=True))
    except (MapPromptError, PlaceNotFound, MapRenderError) as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1
    print(f"\n{result.output} — {result.frames} frames in {time.monotonic() - start:.1f}s — {result.places}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
