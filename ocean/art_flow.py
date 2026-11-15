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


def vector_needs_for_plan(plan: Optional[Dict[str, Any]]) -> List[Tuple[str, str]]:
    """Beat mode: the flat vector pictures (pose "vector") a planned film draws that the library lacks: every animal that
    acts on the knee rig (plan["drawn"]), every flat stage animal and every animal a card draws."""
    if not plan:
        return []
    names: List[str] = []

    def add(n: Any) -> None:
        n = str(n or "")
        if n and n in SUBJECT and n not in names and n not in ("diver", "boat", "cage", "tooth", "car", "bus"):
            names.append(n)
    for d in plan.get("drawn") or []:
        for n in d.get("names") or []:
            add(n)
    for ly in plan.get("layers") or []:
        for e in (ly.get("params") or {}).get("elements") or []:
            a = e.get("args") or {}
            if e.get("kind") == "animal" and a.get("flat"):
                add(a.get("name"))
            elif a.get("flat_art"):
                add(a.get("animal"))
                for x in a.get("animals") or []:
                    add(x)
    return [(n, "vector") for n in names if path(n, "vector") is None]


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
            elif k == "ocean_stomach":                       # the eater and everything shown inside it
                for n in [a.get("predator")] + list(a.get("prey") or []):
                    if n:
                        add(str(n), "side")
            elif k == "ocean_above_below":
                for n in (a.get("top"), a.get("bottom")):
                    if n:
                        add(str(n), "side")
            elif isinstance(a.get("animal"), str) and a.get("animal"):
                add(str(a["animal"]), "side")
    land = any(SP.family(n) in ("land",) for n, _p in want)
    if land:
        add("hiker", "side")                          # the thumbnail's figure for scale in a land story
    return [(n, p) for n, p in want if path(n, p) is None]


STYLE = ("Semi-realistic digital painting for a nature documentary: accurate anatomy and proportions, detailed skin texture, "
         "soft light from above, subtle shading and depth, painterly but realistic. Not a cartoon, no thick outlines, "
         "no cute face.")
BACKGROUND = (f"Plain flat solid bright green background ({GREEN}) filling the whole picture, no water, no bubbles, no ground, "
              "no shadow, no other objects. No text, no letters, no logos, no watermark.")


VECTOR_STYLE = ("Flat 2D vector illustration in the style of a modern animated YouTube explainer: clean flat colour shapes "
                "with soft subtle gradients, crisp smooth edges, simple stylised but accurate anatomy, bold readable "
                "silhouette, markings (stripes, spots, mane, patches) drawn as clean tapered shapes, a lighter belly, "
                "small clean face details. No outlines, no texture, no fur strands, no painterly brush work, no 3D render.")
VECTOR_VIEW = ("Seen exactly from the side, facing right, walking slowly, head level, mid-stride: the near front leg "
               "reaching forward and the far front leg back, the near hind leg back and the far hind leg forward, so all "
               "FOUR paws stand apart on the ground with empty space between every leg and under the belly; no leg "
               "hides another. The two far-side legs a slightly darker shade than the near-side legs. The tail fully "
               "visible, held out behind, not touching the legs. Whole animal inside the frame with space around it.")


def prompt(name: str, pose: str = "side") -> str:
    what = SUBJECT.get(name, name.replace("_", " "))
    if pose == "vector":                              # the reference channel's flat puppet look (ocean/rig.py animates it)
        sp = SP.get(name)
        fam = sp.family if sp is not None else ""
        if name in ("cobra", "puff_adder", "black_mamba") or "snake" in name or "adder" in name or "mamba" in name:
            view = ("Seen exactly from the side, facing right, the body in a loose S-curve along the ground, head raised"
                    + (" with the hood spread" if "cobra" in name else "") + ", the whole snake inside the frame.")
        elif fam == "bird" or name in ("bee", "wasp", "hornet"):
            view = "Seen exactly from the side, facing right, flying with wings spread, the whole animal inside the frame."
        elif fam == "ray":
            view = ("Seen from directly above like a map icon, nose pointing right, fins spread symmetrically, the whole "
                    "animal inside the frame.")
        elif fam in ("shark", "whale", "dolphin", "fish", "seal", "squid", "turtle"):
            view = "Seen exactly from the side, facing right, swimming straight, mouth closed, the whole animal inside the frame."
        elif name == "tiger" or fam in ("land", "bear", ""):
            view = VECTOR_VIEW + (" The tail curves up and back, high above the ground, well away from the hind legs."
                                  if name in ("tiger", "leopard", "cheetah", "lion", "lioness") else "")
        else:
            view = VECTOR_VIEW
        return f"{VECTOR_STYLE} Exactly one {what}. {view} {BACKGROUND}"
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
    elif name == "hiker":
        view = "Seen exactly from the side, facing right, walking, the whole person inside the frame with space around it."
    elif name == "tooth":
        view = "Seen from the front, point up, centred, the whole tooth inside the frame with space around it."
    elif sp is not None and sp.family == "bird":
        view = ("Seen exactly from the side, facing right, flying with wings spread, "
                "whole animal inside the frame with space around it.")
    elif sp is not None and sp.key in ("cobra", "puff_adder", "black_mamba"):
        view = ("Seen exactly from the side, facing right, the whole snake inside the frame with space around it.")
    elif sp is not None and sp.family in ("land", "bear") and name != "polar_bear" or name == "polar_bear_land":
        view = ("Seen exactly from the side, facing right, standing on all four legs, "
                "whole animal inside the frame with space around it.")
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
    tall_ok = pose in ("side", "vector") and bh <= bw * 3.0          # the tooth stands up; animals lie along the frame
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
