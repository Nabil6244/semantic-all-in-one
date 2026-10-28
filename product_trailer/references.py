"""Reference renders of a phone for AI scene generation (Flow takes up to three reference images per request).

One call renders five clean pictures of the code-built phone from the What If engine, in a plain bright room, with no wordmark, so a scene
generator keeps the same design: a fan of backs, a row of fronts, a row of backs, one phone at three quarters, and a camera macro.

    python -m product_trailer.references "galaxy s27 ultra" --out out/refs

Pure parts (the spec, the file names, the colour pick) are plain functions and tested; the engine run is one subprocess.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

DEFAULT_COLOURS = ["Black", "Sky Blue", "Pink", "White"]
DEFAULT_ROOM = "gallery"
SHOT_S = 2.0

# name, extra shot fields. Times of the stills are the middle of each shot.
SHOTS: List[tuple] = [
    ("fan_backs", {"pose": "fan", "push": [5.9, 5.9], "cam_y": -0.1, "look_y": 0.0, "spacing": 1.3}),
    ("row_fronts", {"pose": "front", "push": [6.0, 6.0], "cam_y": -0.1, "look_y": 0.0}),
    ("row_backs", {"pose": "back", "push": [6.0, 6.0], "cam_y": -0.1, "look_y": 0.0}),
    ("one_three_quarter", {"pose": "back", "one": True, "push": [4.6, 4.6], "cam_x": [1.5, 1.5], "cam_y": -0.2, "look_y": -0.05}),
    ("camera_macro", {"pose": "back", "one": True, "push": [1.9, 1.9], "cam_x": [0.55, 0.55], "cam_y": 0.7, "look_y": 0.7, "focus": 0.002}),
]
NAMES = [n for n, _ in SHOTS]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def _catalog(path: Optional[Path] = None) -> list:
    p = path or Path(__file__).resolve().parents[1] / "whatif-engine" / "data" / "phones.json"
    try:
        return json.loads(Path(p).read_text(encoding="utf-8")).get("phones", [])
    except Exception:  # noqa: BLE001 -- a missing catalog only means the default colours
        return []


def preset_colours(phone: str, catalog: Optional[list] = None) -> List[str]:
    """Up to four colour names from the phone's preset (the preset's own order), else the defaults."""
    key = _norm(phone)
    for p in (catalog if catalog is not None else _catalog()):
        names = {_norm(p.get("id", "")), _norm(p.get("name", ""))} | {_norm(a) for a in p.get("aliases", [])}
        if key and key in names:
            cols = [c.get("name") for c in p.get("colors", []) if c.get("name")]
            if len(cols) >= 2:
                return cols[:4]
    return list(DEFAULT_COLOURS)


def reference_files(out_dir: Path) -> List[Path]:
    """The five file names, in the order a scene prompt expects them."""
    return [Path(out_dir) / f"ref{i + 1}_{n}.jpg" for i, n in enumerate(NAMES)]


def build_reference_spec(phone: str, *, colours: Optional[Sequence[str]] = None, room: str = DEFAULT_ROOM, width: int = 2560, height: int = 1440,
                         wordmark: str = "") -> tuple:
    """-> (engine spec, stills times). Five 2 s lineup shots; the still of shot i is taken at its middle."""
    cols = list(colours) if colours else preset_colours(phone)
    one = cols[1] if len(cols) > 1 else cols[0]
    shots, times = [], []
    for i, (name, extra) in enumerate(SHOTS):
        t0 = i * SHOT_S
        shot = {"id": name, "start": t0, "end": t0 + SHOT_S, "kind": "product", "object": "lineup", "room": room, "phone": phone, "wordmark": wordmark, "seed": 21}
        extra = dict(extra)
        shot["colors"] = [one] if extra.pop("one", False) else cols
        shot.update(extra)
        shots.append(shot)
        times.append(t0 + SHOT_S / 2)
    spec = {"width": width, "height": height, "fps": 30, "duration": SHOT_S * len(SHOTS),
            "look": {"saturate": 0.97, "contrast": 1.03, "lift": "#000000", "vignette": 0.12, "grain": 0.0}, "shots": shots, "layers": []}
    return spec, times


def _run_engine_stills(spec: dict, times: Sequence[float], work: Path, log: Callable[[str], None]) -> List[Path]:
    """Render the stills with the What If engine (WHATIF_STILLS); one JPEG per time, named <base>.t<time>.jpg."""
    from map_scene.render import _browser_channel, _ensure_browser, _ffmpeg, _node
    from whatif.engine_runner import WhatifRenderError, engine_dir

    engine = engine_dir()
    try:
        from providers.flow.engine_manager import _find_flow_engine_dir

        playwright_dir = str(_find_flow_engine_dir())
    except Exception:  # noqa: BLE001
        playwright_dir = None
    try:
        _ensure_browser()
        node, ffmpeg = _node(), _ffmpeg()
    except Exception as exc:  # noqa: BLE001
        raise WhatifRenderError(str(exc)) from exc
    job = dict(spec, ffmpeg=ffmpeg, playwright_dir=playwright_dir, browser_channel=_browser_channel())
    spec_path, base = work / "spec.json", work / "refs.mp4"
    spec_path.write_text(json.dumps(job), encoding="utf-8")
    env = dict(os.environ, WHATIF_STILLS=",".join(f"{t:g}" for t in times))
    proc = subprocess.run([node, str(engine / "render.mjs"), str(spec_path), str(base)], cwd=str(engine), env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=900)
    for line in (proc.stdout or "").splitlines():
        if '"event":"warning"' in line or '"event":"error"' in line:
            log(line[:300])
    if proc.returncode != 0:
        raise WhatifRenderError(f"the reference render failed: {(proc.stderr or proc.stdout)[-400:]}")
    out = [work / f"refs.mp4.t{t:g}.jpg" for t in times]
    missing = [p.name for p in out if not p.is_file()]
    if missing:
        raise WhatifRenderError(f"the reference render made no picture for: {', '.join(missing)}")
    return out


def render_references(phone: str, out_dir, *, colours: Optional[Sequence[str]] = None, room: str = DEFAULT_ROOM, width: int = 2560, height: int = 1440,
                      wordmark: str = "", log: Callable[[str], None] = print, runner: Optional[Callable] = None) -> Dict[str, object]:
    """Render the five references into out_dir. Returns {"files": [five Paths], "colours": [...], "room": room}. `runner` is for tests."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    spec, times = build_reference_spec(phone, colours=colours, room=room, width=width, height=height, wordmark=wordmark)
    with tempfile.TemporaryDirectory(prefix="product_refs_") as tmp:
        stills = (runner or _run_engine_stills)(spec, times, Path(tmp), log)
        targets = reference_files(out_dir)
        for src, dst in zip(stills, targets):
            Path(src).replace(dst) if Path(src).parent == dst.parent else dst.write_bytes(Path(src).read_bytes())
    cols = list(colours) if colours else preset_colours(phone)
    log(f"reference images for {phone!r} ({', '.join(cols)}): {out_dir}")
    return {"files": targets, "colours": cols, "room": room}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m product_trailer.references", description="Render five reference pictures of a phone for AI scene generation.")
    ap.add_argument("phone", help='a preset name, e.g. "galaxy s27 ultra"')
    ap.add_argument("--out", required=True, help="folder for ref1..ref5 JPEGs")
    ap.add_argument("--colours", help="comma-separated colour names (default: the preset's first four)")
    ap.add_argument("--room", default=DEFAULT_ROOM, choices=["loft", "gallery", "studio", "terrace"])
    ap.add_argument("--size", default="2560x1440", help="WxH (default 2560x1440)")
    ap.add_argument("--wordmark", default="", help="text printed on the back (default none)")
    a = ap.parse_args(argv)
    w, h = (int(x) for x in a.size.lower().split("x"))
    cols = [c.strip() for c in a.colours.split(",") if c.strip()] if a.colours else None
    res = render_references(a.phone, a.out, colours=cols, room=a.room, width=w, height=h, wordmark=a.wordmark)
    for f in res["files"]:
        print(f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
