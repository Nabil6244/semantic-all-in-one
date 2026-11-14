"""Painted animal library for Ocean Predators: realistic documentary-illustration animals made ONCE with Flow (free images),
cut off a green screen in code and kept in assets/ocean/art/. Every film reuses them; the code drawings in ocean/animals.py
stay only as the backup for an animal or pose the library lacks. Same pattern as aviation/sticker_flow.py.

    ITEMS                               [(name, pose)]  what the library holds (pose: side | jaw | top)
    prompt(name, pose) -> str           exactly one animal, side view facing right (top: seen from above, nose right),
                                        semi-realistic painting, on flat bright green; no text
    cut_out(png, pose) -> RGBA | None   key the green away, despill the edge, crop; None when it is not one animal on green
    path(name, pose) -> Path | None     the library picture, if made
    missing() -> [(name, pose)]         what still has to be made
    generate(items=None, log=print)     one Flow image per item (the app's FlowProvider, engine and accounts), cut out, saved

    python -m ocean.art_flow            make whatever is missing (prints a line per picture)
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageFilter

ART_DIR = Path(__file__).resolve().parent.parent / "assets" / "ocean" / "art"
GREEN = "#00FF00"

from . import species as SP  # noqa: E402

SUBJECT = {**{k: v.desc for k, v in SP.SPECIES.items()}, **SP.PROP_DESC}
BASE_SET = ("great_white", "shark", "megalodon", "orca", "humpback", "sperm_whale", "dolphin", "seal", "squid",
            "colossal_squid", "diver", "boat", "tooth", "car", "bus")
JAW = ("great_white", "shark", "megalodon", "orca")
TOP = ("great_white", "shark", "orca", "dolphin", "seal")
ITEMS: List[Tuple[str, str]] = ([(n, "side") for n in BASE_SET] + [(n, "jaw") for n in JAW] + [(n, "top") for n in TOP])
TOP_FAMILIES = ("shark", "whale", "dolphin", "seal", "fish", "ray", "turtle", "reptile", "bird", "squid")


def needs_for_plan(plan: Optional[Dict[str, Any]]) -> List[Tuple[str, str]]:
    """The pictures a planned film shows that the library lacks: every animal on stage (side), predators that attack or
    open their jaws (jaw), animals on a top-down island map (top). Nothing for names the catalogue does not know."""
    if not plan:
        return []
    want: List[Tuple[str, str]] = []

    def add(n: str, pose: str) -> None:
        if n in SUBJECT and (n, pose) not in want:
            want.append((n, pose))
    for ly in plan.get("layers") or []:
        for e in (ly.get("params") or {}).get("elements") or []:
            a = e.get("args") or {}
            k = str(e.get("kind", ""))
            if k == "animal" and a.get("name"):
                add(str(a["name"]), "side")
                sp = SP.get(str(a["name"]))
                if a.get("jaw") or (sp and sp.jaw):
                    add(str(a["name"]), "jaw")
            elif k == "ocean_island_map" and a.get("animal"):
                sp = SP.get(str(a["animal"]))
                add(str(a["animal"]), "side")
                if sp is None or sp.family in TOP_FAMILIES:
                    add(str(a["animal"]), "top")
            elif k == "ocean_size_compare":
                if a.get("animal"):
                    add(str(a["animal"]), "side")
                if a.get("ref") in ("car", "bus"):
                    add(str(a["ref"]), "side")
            elif isinstance(a.get("animal"), str) and a.get("animal"):
                add(str(a["animal"]), "side")
    return [(n, p) for n, p in want if path(n, p) is None]


STYLE = ("Semi-realistic digital painting for a nature documentary: accurate anatomy and proportions, detailed skin texture, "
         "soft light from above, subtle shading and depth, painterly but realistic. Not a cartoon, no thick outlines, "
         "no cute face.")
BACKGROUND = (f"Plain flat solid bright green background ({GREEN}) filling the whole picture, no water, no bubbles, no ground, "
              "no shadow, no other objects. No text, no letters, no logos, no watermark.")


def prompt(name: str, pose: str = "side") -> str:
    what = SUBJECT.get(name, name.replace("_", " "))
    sp = SP.get(name)
    if pose == "side" and sp is not None and sp.family == "ray":
        pose = "top"                                  # a ray reads from above: its 'side' picture is the top view
    if pose == "top":
        view = ("Bird's-eye view looking straight down on its back from directly above, like a map icon: the body is a "
                "straight horizontal line with the head pointing to the right, both side fins / flippers spread "
                "symmetrically up and down, the tail at the left; no side view, no belly visible, "
                "whole animal inside the frame with space around it.")
    elif pose == "jaw":
        view = ("Seen exactly from the side, facing right, mouth wide open showing rows of teeth, attacking pose, "
                "whole animal inside the frame with space around it.")
    elif name == "tooth":
        view = "Seen from the front, point up, centred, the whole tooth inside the frame with space around it."
    else:
        view = ("Seen exactly from the side, facing right, swimming straight, mouth closed, "
                "whole animal inside the frame with space around it.")
    return f"{STYLE} Exactly one {what}. {view} {BACKGROUND}"


def cut_out(src: Any, pose: str = "side") -> Optional[Image.Image]:
    """Chroma-key the green away (aviation/sticker_flow.py's keying), crop; None when it is not one subject on green."""
    try:
        im = Image.open(src).convert("RGB")
    except Exception:  # noqa: BLE001
        return None
    if max(im.size) > 1600:
        im.thumbnail((1600, 1600), Image.LANCZOS)
    px = im.load()
    w, h = im.size
    a = Image.new("L", (w, h), 255)
    ap = a.load()
    rgb = im.copy()
    rp = rgb.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if g > 90 and g > 1.35 * max(r, b):
                ap[x, y] = 0
            elif g > max(r, b) + 10:                      # green spill on the edge: neutralise it
                rp[x, y] = (r, max(r, b), b)
    a = a.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.9))
    box = a.point(lambda v: 255 if v > 128 else 0).getbbox()
    if not box:
        return None
    bw, bh = box[2] - box[0], box[3] - box[1]
    cover = sum(1 for v in a.crop(box).getdata() if v > 128) / max(1, bw * bh)
    edge_green = sum(1 for x in range(w) for y in (0, h - 1) if ap[x, y] == 0) / (2 * w)
    tall_ok = pose == "side" and bh <= bw * 3.0          # the tooth stands up; animals lie along the frame
    if edge_green < 0.6 or cover < 0.10 or (bw < w * 0.25 and bh < h * 0.25) or (bh > bw * 0.9 and not tall_ok):
        return None
    out = rgb.convert("RGBA")
    out.putalpha(a)
    return out.crop(box)


def path(name: str, pose: str = "side") -> Optional[Path]:
    p = ART_DIR / f"{name}_{pose}.png"
    return p if p.is_file() else None


def missing(items: Sequence[Tuple[str, str]] = ITEMS) -> List[Tuple[str, str]]:
    return [(n, p) for n, p in items if path(n, p) is None]


def generate(items: Optional[Sequence[Tuple[str, str]]] = None, log=print, mode: Optional[str] = None,
             account_ids=None, manager: Any = None, should_stop=None) -> List[Dict[str, Any]]:
    """manager: the app's shared Flow engine (app._get_flow_engine_manager()); None starts one (CLI)."""
    items = list(items if items is not None else missing())
    if not items:
        log("[OCEAN] art library complete: nothing to make")
        return []
    from providers.base import SceneRow
    from providers.flow.engine_manager import FlowEngineManager
    from providers.flow.provider import FlowProvider

    ART_DIR.mkdir(parents=True, exist_ok=True)
    mgr = manager or FlowEngineManager(log=log)
    fs: Dict[str, Any] = {"model": "GEM_PIX_2", "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE"}
    if mode:
        fs["generationMode"] = mode
    prov = FlowProvider(mgr, media_kind="image", account_ids=account_ids, flow_settings=fs)
    tmp = Path(tempfile.mkdtemp(prefix="ocean_art_"))
    rows = [SceneRow(scene_number=str(i + 1), script_segment=f"{n} {p}", asset_type="image", prompt=prompt(n, p))
            for i, (n, p) in enumerate(items)]
    log(f"[OCEAN] Flow: {len(rows)} animal picture(s) for the shared library (free images)")
    res = prov.resolve_batch(rows, tmp, log=log, should_stop=should_stop)
    out = []
    for i, (n, p) in enumerate(items):
        r = res.get(str(i + 1))
        src = getattr(r, "path", None) if r is not None else None
        if not (src and Path(src).is_file()):
            out.append({"name": n, "pose": p, "status": "failed", "error": str(getattr(r, "error", None) or "no image")})
            continue
        st = cut_out(src, p)
        if st is None:
            out.append({"name": n, "pose": p, "status": "rejected", "raw": str(src)})
            continue
        dst = ART_DIR / f"{n}_{p}.png"
        st.save(dst, optimize=True)
        out.append({"name": n, "pose": p, "status": "made", "path": str(dst)})
    for o in out:
        log(f"[OCEAN] {o['name']} {o['pose']}: {o['status']}" + (f" ({o.get('error') or o.get('raw')})" if o["status"] != "made" else ""))
    return out


if __name__ == "__main__":
    generate()
