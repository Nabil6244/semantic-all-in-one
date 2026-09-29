"""Render a map prompt to an MP4 with the map-engine (Node + hidden Chromium).

Kept apart from Flow: map-engine is its own process with its own throwaway
browser; it never uses the Flow engine's port or Chrome account profiles.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .places import AiResolver, Place, PlaceNotFound, find_place, sea_polygon
from .spec import MapSpec, parse_map_prompt

CREDIT = "Imagery: NASA Blue Marble"
DEFAULT_DURATION_S = 12.0


class MapRenderError(RuntimeError):
    pass


class MapRenderCancelled(MapRenderError):
    pass


@dataclass
class MapRenderResult:
    output: Path
    frames: int
    places: dict
    notes: list = field(default_factory=list)  # fallbacks taken, e.g. an unknown spot left out


def _roots() -> list[Path]:
    from providers.flow.engine_manager import _candidate_roots

    return _candidate_roots()


def _find(rel: str) -> Optional[Path]:
    for root in _roots():
        candidate = root / rel
        if candidate.exists():
            return candidate
    return None


def map_engine_dir() -> Path:
    found = _find("map-engine/render.mjs")
    if found is None:
        raise MapRenderError("Map renderer (map-engine/render.mjs) is missing from this install.")
    return found.parent


def _ffmpeg() -> str:
    name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    found = _find(f"bin/{name}")
    if found is not None:
        return str(found)
    which = shutil.which("ffmpeg")
    if not which:
        raise MapRenderError("ffmpeg was not found.")
    return which


def _node() -> str:
    from providers.flow.engine_manager import _find_node_binary

    node = _find_node_binary()
    if not node:
        raise MapRenderError("Node.js runtime was not found (bin/node).")
    return node


def cache_dir() -> Path:
    """Per-user cache for satellite tiles and AI place answers."""
    override = os.environ.get("VIDEOGEN_MAP_CACHE")
    if override:
        base = Path(override)
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches" / "SemanticYTStudio" / "maps"
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "SemanticYTStudio" / "Cache" / "maps"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "semantic-yt-studio" / "maps"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _browser_channel() -> Optional[str]:
    """Playwright's own Chromium when installed, else the system Chrome."""
    try:
        from providers.playwright_chromium import is_playwright_chromium_installed, system_chrome_available

        if is_playwright_chromium_installed():
            return None
        if system_chrome_available():
            return "chrome"
    except Exception:
        pass
    return None


def _ensure_browser() -> None:
    """A fresh install may have neither Chrome nor Playwright's Chromium yet:
    download Chromium once, exactly as Flow and YouTube capture do."""
    try:
        from providers.playwright_chromium import ensure_playwright_chromium, is_playwright_chromium_installed, system_chrome_available

        if is_playwright_chromium_installed() or system_chrome_available():
            return
        from providers.flow.engine_manager import _find_flow_engine_dir

        ensure_playwright_chromium(engine_dir=_find_flow_engine_dir(), node_bin=_node())
    except MapRenderError:
        raise
    except Exception as exc:
        raise MapRenderError(f"No browser available to draw the map: {exc}") from exc


def resolve_places(spec: MapSpec, ai: Optional[AiResolver] = None, notes: Optional[list] = None) -> dict:
    """Find each level of the prompt. A level that can't be found degrades
    the map instead of failing it, as long as something real is left: an
    unknown inner spot is dropped (the focus area still shows), and an
    unknown focus falls back to its parent area. Each fallback is added to
    ``notes``. Only when nothing at all can be found does it raise."""
    notes = notes if notes is not None else []
    parent = None
    if spec.parent:
        try:
            parent = find_place(spec.parent, ai=ai)
        except PlaceNotFound as exc:
            notes.append(f"wider area left out: {exc}")
    try:
        focus = find_place(spec.focus, parent=parent, ai=ai)
    except PlaceNotFound as exc:
        if parent is None:
            raise
        notes.append(f"showing {parent.name} instead: {exc}")
        focus, parent = parent, None
        spec.label = focus.name  # a custom label named the missing place, not this wider area
        spec.inner = None
    inner = None
    if spec.inner:
        try:
            inner = find_place(spec.inner, parent=focus, ai=ai)
        except PlaceNotFound as exc:
            notes.append(f"exact spot left out, showing {focus.name}: {exc}")
    return {k: v for k, v in (("parent", parent), ("focus", focus), ("inner", inner)) if v is not None}


def _area(role: str, place: Place) -> dict:
    area = {"role": role, "name": place.name, "bbox": list(place.bbox()), "anchor": list(place.anchor())}
    if place.is_point:
        area.update(point=list(place.point), radius_km=place.radius_km)
    else:
        area.update(fill=place.geojson(), outline=place.outline())
    return area


def _view_bbox(places: dict) -> tuple:
    boxes = [p.bbox() for p in places.values()]
    minx, miny = min(b[0] for b in boxes), min(b[1] for b in boxes)
    maxx, maxy = max(b[2] for b in boxes), max(b[3] for b in boxes)
    pad_x, pad_y = max(2.0, (maxx - minx) * 2.5), max(2.0, (maxy - miny) * 2.5)
    return (minx - pad_x, miny - pad_y, maxx + pad_x, maxy + pad_y)


def _drawn_places(places: dict) -> dict:
    """A country as the PARENT of a state/region/county only says which one
    is meant ("United States of America > Georgia"): it isn't drawn — a whole
    country filled blue, from a camera that starts at Alaska, buries the
    place. A state or region parent (Florida > Florida Panhandle) is drawn."""
    parent, focus = places.get("parent"), places.get("focus")
    if parent is not None and parent.kind == "country" and focus is not None and focus.kind != "country":
        return {k: v for k, v in places.items() if k != "parent"}
    return places


def build_scene(spec: MapSpec, places: dict, *, duration: float, fps: int, width: int, height: int,
                imagery: bool = True) -> dict:
    places = _drawn_places(places)
    return {
        "imagery": imagery,
        "sea": sea_polygon(_view_bbox(places)) if spec.style == "dark" else None,
        "width": width, "height": height, "fps": fps, "duration": duration,
        "camera": spec.camera, "style": spec.style,
        "areas": [_area(role, place) for role, place in places.items()],
        "label": {"text": spec.label_text, "target": "focus"},
        "credit": CREDIT,
    }



def render_map(
    prompt: str,
    output: Path,
    *,
    duration: float = DEFAULT_DURATION_S,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
    ai: Optional[AiResolver] = None,
    progress: Optional[Callable[[int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    timeout_s: float = 900.0,
    imagery: bool = True,
) -> MapRenderResult:
    spec = parse_map_prompt(prompt)
    notes: list = []
    places = resolve_places(spec, ai=ai, notes=notes)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    font = _find("assets/fonts/Outfit-ExtraBold.ttf")
    if font is None:
        raise MapRenderError("Label font assets/fonts/Outfit-ExtraBold.ttf is missing.")
    engine = map_engine_dir()
    try:
        from providers.flow.engine_manager import _find_flow_engine_dir

        playwright_dir = str(_find_flow_engine_dir())
    except Exception:
        playwright_dir = None
    _ensure_browser()
    tmp_out = output.with_name(f".{output.stem}.rendering{output.suffix}")
    job = {
        "scene": build_scene(spec, places, duration=duration, fps=fps, width=width, height=height, imagery=imagery),
        "output": str(tmp_out), "ffmpeg": _ffmpeg(), "font_path": str(font),
        "cache_dir": str(cache_dir()), "playwright_dir": playwright_dir, "browser_channel": _browser_channel(),
    }
    with tempfile.TemporaryDirectory(prefix="map_scene_") as tmp:
        spec_path = Path(tmp) / "spec.json"
        spec_path.write_text(json.dumps(job), encoding="utf-8")
        from providers import hidden_subprocess as hs

        proc = hs.popen([_node(), str(engine / "render.mjs"), str(spec_path)], cwd=str(engine),
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        stderr_lines: list[str] = []
        threading.Thread(target=lambda: stderr_lines.extend(proc.stderr), daemon=True).start()
        done, error, frames = None, None, 0
        timer = threading.Timer(timeout_s, proc.kill)
        timer.start()
        try:
            for raw in proc.stdout:
                if cancel_check is not None and cancel_check():
                    proc.kill()
                    raise MapRenderCancelled("Map render cancelled.")
                try:
                    event = json.loads(raw)
                except ValueError:
                    continue
                kind = event.get("event")
                if kind == "progress" and progress is not None:
                    progress(int(event["frame"]), int(event["total"]))
                elif kind == "done":
                    done, frames = event, int(event.get("frames") or 0)
                elif kind == "error":
                    error = event.get("message")
            proc.wait()
        finally:
            timer.cancel()
            if proc.poll() is None:
                proc.kill()
    if done is None or proc.returncode != 0 or not tmp_out.is_file():
        tmp_out.unlink(missing_ok=True)
        detail = error or "".join(stderr_lines[-20:]).strip() or f"exit code {proc.returncode}"
        raise MapRenderError(f"Map render failed: {detail}")
    os.replace(tmp_out, output)
    return MapRenderResult(output=output, frames=frames,
                           places={role: (p.name, p.kind, p.source) for role, p in places.items()},
                           notes=notes)
