"""Loader for the "scenes v2" pack built by explainer/cartoon/build_scenes_v2.py (opt-in: DirectorOptions.scenes2). It only READS: every file is checked against its manifest.json (SHA-256 and
size) before it is used. A missing, edited or damaged file never stops a render: `problem()` answers with the reason (a cue problem, the beat falls back to its board or to the v1 kit) and
`available()` is False when the pack as a whole cannot be used. The v1 kit (assets/cartoon) and its manifest are never touched.

The v2 sets and props use names the v1 kit does not have (border_wall, vault, train ...). `install()` lets the existing renderer draw them through the same `visual` cues: it wraps
kit.problem / set_image / ground_y / prop_sprite so that a name missing from the v1 manifest is looked up here. Names the v1 kit knows are answered by the v1 functions exactly as before, so
with the flag off (or install() never called) nothing changes."""

from __future__ import annotations

import io
import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, Tuple

from PIL import Image

from . import kit as K

ASSET_DIR = Path(__file__).resolve().parents[1] / "assets" / "scenes_v2"
BUILD_HINT = "rebuild with: python3 -B explainer/cartoon/build_scenes_v2.py"
_INSTALLED = False


@lru_cache(maxsize=1)
def manifest() -> dict:
    p = ASSET_DIR / "manifest.json"
    if not p.is_file():
        raise K.AssetError(f"scenes v2 manifest.json is missing ({BUILD_HINT})")
    try:
        m = json.loads(p.read_bytes())
    except ValueError as e:
        raise K.AssetError(f"scenes v2 manifest.json is unreadable: {e}")
    if not isinstance(m, dict) or "sets" not in m or "props" not in m:
        raise K.AssetError("scenes v2 manifest.json has no sets/props")
    return m


def sets() -> Tuple[str, ...]:
    try:
        return tuple(sorted(manifest()["sets"]))
    except K.AssetError:
        return ()


def props() -> Tuple[str, ...]:
    try:
        return tuple(sorted(manifest()["props"]))
    except K.AssetError:
        return ()


def _raw(name: str, slot: dict) -> bytes:
    try:
        return K.check_file(ASSET_DIR / name, slot["sha256"], slot["bytes"])
    except K.AssetError as e:
        raise K.AssetError(str(e).replace("cartoon asset", "scenes v2 asset").replace(K.BUILD_HINT, BUILD_HINT))


@lru_cache(maxsize=128)
def _file_problem(name: str, sha: str, size: int) -> str:
    try:
        _raw(name, {"sha256": sha, "bytes": size})
        return ""
    except K.AssetError as e:
        return str(e)


def _slot_problem(slot: dict) -> str:
    return _file_problem(slot["file"], slot["sha256"], slot["bytes"])


def has_set(name: str, tod: str = "day") -> bool:
    return not problem("set", {"set": name, "tod": tod})


def has_prop(name: str) -> bool:
    return not problem("prop", {"prop": name})


def available() -> bool:
    """True when the manifest loads and every set and prop file is present and intact (checked once per process)."""
    try:
        m = manifest()
    except K.AssetError:
        return False
    for s in m["sets"].values():
        for slot in s["tod"].values():
            if _slot_problem(slot):
                return False
    return not any(_slot_problem(slot) for slot in m["props"].values())


def problem(style: str, params: Dict) -> str:
    """'' when a v2 set or prop named in the params can be drawn; otherwise why not."""
    try:
        m = manifest()
    except K.AssetError as e:
        return str(e)
    if style == "set":
        name, tod = params.get("set"), params.get("tod", "day")
        if name not in m["sets"]:
            return f"unknown v2 set {name!r} (available: {', '.join(sorted(m['sets']))})"
        if tod not in m["sets"][name]["tod"]:
            return f"unknown time of day {tod!r} (day or dusk)"
        return _slot_problem(m["sets"][name]["tod"][tod])
    if style == "prop":
        name = params.get("prop")
        if name not in m["props"]:
            return f"unknown v2 prop {name!r} (available: {', '.join(sorted(m['props']))})"
        return _slot_problem(m["props"][name])
    return f"v2 pack has no {style!r}"


def _img(name: str, slot: dict, mode: str) -> Image.Image:
    return Image.open(io.BytesIO(_raw(name, slot))).convert(mode)


@lru_cache(maxsize=16)
def set_image(name: str, tod: str = "day") -> Image.Image:
    return _img(f"set_{name}_{tod}.png", manifest()["sets"][name]["tod"][tod], "RGB")


def ground_y(name: str) -> int:
    return int(manifest()["sets"][name]["ground_y"])


@lru_cache(maxsize=32)
def prop_full(name: str) -> Image.Image:
    return _img(f"prop_{name}.png", manifest()["props"][name], "RGBA")


@lru_cache(maxsize=32)
def prop_sprite(name: str, height: int) -> Image.Image:
    im = prop_full(name)
    s = height / im.height
    return im.resize((max(2, round(im.width * s)), max(2, round(im.height * s))), Image.LANCZOS)


def _v1_has(kind: str, name) -> bool:
    try:
        return name in K.manifest()[kind]
    except K.AssetError:
        return False


def install() -> bool:
    """Idempotent. Wraps the v1 kit lookups so v2 names resolve here; returns whether the v2 pack is usable. Also registers the tile pictures (board.icons_v2)."""
    global _INSTALLED
    if not _INSTALLED:
        o_problem, o_set, o_ground, o_prop = K.problem, K.set_image, K.ground_y, K.prop_sprite

        def problem_(style, params):
            if style == "set" and not _v1_has("sets", params.get("set")) and params.get("set") in sets():
                return problem(style, params)
            if style == "prop" and not _v1_has("props", params.get("prop")) and params.get("prop") in props():
                return problem(style, params)
            return o_problem(style, params)

        def set_(name, tod="day"):
            return set_image(name, tod) if not _v1_has("sets", name) and name in sets() else o_set(name, tod)

        def ground_(name):
            return ground_y(name) if not _v1_has("sets", name) and name in sets() else o_ground(name)

        def prop_(name, height):
            return prop_sprite(name, height) if not _v1_has("props", name) and name in props() else o_prop(name, height)

        K.problem, K.set_image, K.ground_y, K.prop_sprite = problem_, set_, ground_, prop_
        _INSTALLED = True
    try:
        from . import characters
        characters.install()
    except Exception:
        pass
    try:
        from ..board import icons_v2
        icons_v2.register()
    except Exception:
        pass
    return available()
