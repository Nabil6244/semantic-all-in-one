"""Flow-made aircraft stickers for the sticker stage (docs/aviation/MASTER_PLAN.md section 5, F1; step 10), made ONCE per airline x era x
type into the shared library and reused by every later film. Flow images are free; nothing here makes a video.

    needs(bible, story_airlines=None) -> [{airline, era, type, year, prompt}]   the stickers a film's stage shows that the library lacks
    prompt(airline, era, type, year) -> str                                     side view, nose right, livery words, era look, on flat
                                                                                bright green (cut out in code); no letters / logos
    cut_out(png) -> RGBA | None                                                 chroma-key the green away, despill the edge, crop;
                                                                                None when it does not look like one aircraft on green
    generate(items, log=print, mode=None, account_ids=None) -> [{..., status, path?, error?}]
                                                                                one Flow image per item (the app's FlowProvider, the
                                                                                engine and accounts it already uses), cut out, filed in
                                                                                the library as an approved 'sticker' (tag 'flow')
    lookup(airline, era, type) -> path | None                                   what the stage uses before any code-drawn aircraft
Guard rails: never a real named event or person (an aircraft in a livery only); the AI ILLUSTRATION chip stays the stage's job.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from PIL import Image, ImageFilter

from . import catalog as C

GREEN = "#00FF00"
ERA_LOOK = {"pre1960": "a late-1940s / 1950s airliner as it looked then",
            "1960s": "as it looked in the 1960s", "1970s": "as it looked in the 1970s", "1980s": "as it looked in the 1980s",
            "1990s": "as it looked in the 1990s", "modern": "in its current livery"}


def _livery_words(airline: str, era: str) -> str:
    from . import bible as BB
    al = C.get_airline(airline) or {}
    words = BB.color_words(al.get("colors") or [])
    notes = al.get("livery_notes") or ""
    return f"{al.get('name', airline)} livery, {notes or ('painted ' + words) if (notes or words) else 'its airline livery'}"


def prompt(airline: str, era: str, typ: str, year: int = 0) -> str:
    from . import bible as BB
    ac = BB.aircraft_entry(typ) or {}
    name = ac.get("name") or typ
    return (f"Detailed side-view illustration of a {name} airliner in {_livery_words(airline, era)}, {ERA_LOOK.get(era, '')}. "
            "Exactly one aircraft, seen exactly from the side, nose pointing to the right, landing gear down, the whole aircraft "
            "inside the frame with a little space around it. Clean illustrated look with crisp outlines, accurate proportions, "
            "windows, doors, engines and tail drawn in fine detail. "
            f"Plain flat solid bright green background ({GREEN}) filling the whole picture, no ground, no shadow, no sky, no other "
            "objects. No text, no letters, no logos, no watermark.")


def needs(bible: Any, story_airlines: Optional[Sequence[str]] = None, lib: Any = None) -> List[Dict[str, Any]]:
    """The film's hero aircraft (bible fleet per airline x era) that the stage shows, minus what the library already has.
    Guessed types ('assumed') are kept only for airlines the stage shows (story_airlines), never for news-only airlines."""
    from . import flow_prompts as FP
    out = []
    for h in FP.hero_list(bible):
        al, era, typ = h["airline"], h["era"], h.get("aircraft") or ""
        if not typ:
            continue
        if h.get("assumed") and story_airlines is not None and al not in story_airlines:
            continue
        if lookup(al, era, typ, lib=lib):
            continue
        out.append({"airline": al, "era": era, "type": typ, "year": h.get("year") or 0, "prompt": prompt(al, era, typ, h.get("year") or 0)})
    return out


def cut_out(path: Any) -> Optional[Image.Image]:
    try:
        im = Image.open(path).convert("RGB")
    except Exception:
        return None
    if max(im.size) > 1400:
        im.thumbnail((1400, 1400), Image.LANCZOS)
    px = im.load()
    w, h = im.size
    a = Image.new("L", (w, h), 255)
    ap = a.load()
    rgb = im.copy()
    rp = rgb.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if g > 90 and g > 1.35 * max(r, b):          # the green screen
                ap[x, y] = 0
            elif g > max(r, b) + 12:                      # green spill on the aircraft's edge: neutralise it
                rp[x, y] = (r, max(r, b), b)
    a = a.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    box = a.point(lambda v: 255 if v > 128 else 0).getbbox()
    if not box:
        return None
    bw, bh = box[2] - box[0], box[3] - box[1]
    cover = sum(1 for v in a.crop(box).getdata() if v > 128) / max(1, bw * bh)
    edge_green = sum(1 for x in range(w) for y in (0, h - 1) if ap[x, y] == 0) / (2 * w)
    if bw < w * 0.45 or bh > bw * 0.8 or cover < 0.12 or edge_green < 0.6:
        return None                                        # not one wide aircraft on a green field: never used
    out = rgb.convert("RGBA")
    out.putalpha(a)
    return out.crop(box)


def lookup(airline: str, era: str, typ: str, lib: Any = None) -> Optional[str]:
    from . import library as LIB
    hits = [e for e in LIB.find("sticker", airline=airline, subject=typ, lib=lib)
            if e.get("airline") == airline and "flow" in (e.get("tags") or [])]
    exact = [e for e in hits if e.get("era") == era and e.get("subject") == typ]
    pick = (exact or [e for e in hits if e.get("subject") == typ])
    if not pick:
        return None
    p = LIB.path_of(pick[0], lib=lib)
    return str(p) if Path(p).is_file() else None


def generate(items: Sequence[Dict[str, Any]], log=print, mode: Optional[str] = None, account_ids=None, lib: Any = None,
             settings: Optional[dict] = None) -> List[Dict[str, Any]]:
    if not items:
        return []
    from providers.base import SceneRow
    from providers.flow.engine_manager import FlowEngineManager
    from providers.flow.provider import FlowProvider
    from . import library as LIB
    mgr = FlowEngineManager(log=log)
    fs = {"model": "GEM_PIX_2", "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE"}
    if mode:
        fs["generationMode"] = mode
    fs.update(settings or {})
    prov = FlowProvider(mgr, media_kind="image", account_ids=account_ids, flow_settings=fs)
    tmp = Path(tempfile.mkdtemp(prefix="av_sticker_"))
    rows = [SceneRow(scene_number=str(i + 1), script_segment=f"{it['airline']} {it['type']} {it['era']}", asset_type="image",
                     prompt=it["prompt"]) for i, it in enumerate(items)]
    log(f"[AVIATION] Flow: {len(rows)} sticker image(s) (free), one per airline x era x aircraft")
    res = prov.resolve_batch(rows, tmp, log=log)
    out = []
    for i, it in enumerate(items):
        r = res.get(str(i + 1))
        src = getattr(r, "path", None) if r is not None else None
        if not (src and Path(src).is_file()):
            out.append(dict(it, status="failed", error=str(getattr(r, "error", None) or "no image returned")))
            continue
        st = cut_out(src)
        if st is None:
            out.append(dict(it, status="rejected", error="not one aircraft on a clean green background", raw=str(src)))
            continue
        png = tmp / f"sticker_{it['airline']}_{it['era']}_{it['type']}.png"
        st.save(png)
        ent = LIB.add("sticker", str(png), airline=it["airline"], era=it["era"], subject=it["type"], source="flow",
                      credit="AI illustration (Flow)", ai=True, tags=("flow", f"made {time.strftime('%Y-%m-%d')}"), approved=True,
                      lib=lib)
        out.append(dict(it, status="made", path=str(LIB.path_of(ent, lib=lib)), raw=str(src)))
    return out


def aircraft_image(typ: str, airline: str = "", width: int = 560, era: str = "") -> Image.Image:
    """The aircraft picture every stage element uses: the library's Flow sticker for this airline x type (nearest era) when one
    was made, else the code-drawn sticker kit's. Same width either way; the stage adds the white die-cut edge."""
    try:
        p = lookup(airline, era, typ) if airline and typ else None
    except Exception:
        p = None
    if p:
        try:
            im = Image.open(p).convert("RGBA")
            return im.resize((int(width), max(1, int(im.height * width / im.width))), Image.LANCZOS)
        except Exception:
            pass
    from . import stickers as SK
    return SK.aircraft(typ, airline, int(width))


# ---------------------------------------------------------------------------------------------------------------- era plates

def plate_needs(bible: Any, story_airlines: Optional[Sequence[str]] = None, lib: Any = None) -> List[Dict[str, Any]]:
    """Full-screen Flow era pictures (F2) the stage can cut to when no real photo exists: one per airline x era it shows, from the
    bible's era-plate prompt of that chapter's first line (era look, livery, place, mood; people invented and seen from behind).
    Already in the library -> left out."""
    from . import flow_prompts as FP
    out, seen = [], set()
    for h in FP.hero_list(bible):
        al, era = h["airline"], h["era"]
        if (al, era) in seen or (story_airlines is not None and al not in story_airlines):
            continue
        seen.add((al, era))
        if plate(al, era, lib=lib):
            continue
        line = (h.get("lines") or [0])[0]
        pr = FP.image_prompt(bible, line, "era_plate")
        if pr and pr.get("prompt"):
            out.append({"airline": al, "era": era, "line": line, "prompt": pr["prompt"]})
    return out


def plate(airline: str, era: str, lib: Any = None) -> Optional[str]:
    from . import library as LIB
    for e in LIB.find("flow_image", airline=airline, era=era, subject="era_plate", lib=lib):
        if e.get("airline") == airline and e.get("era") == era and "flow" in (e.get("tags") or []):
            p = LIB.path_of(e, lib=lib)
            if Path(p).is_file():
                return str(p)
    return None


def make_plates(items: Sequence[Dict[str, Any]], log=print, mode: Optional[str] = "ui", lib: Any = None) -> List[Dict[str, Any]]:
    if not items:
        return []
    from providers.base import SceneRow
    from providers.flow.engine_manager import FlowEngineManager
    from providers.flow.provider import FlowProvider
    from . import library as LIB
    fs = {"model": "GEM_PIX_2", "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE"}
    if mode:
        fs["generationMode"] = mode
    prov = FlowProvider(FlowEngineManager(log=log), media_kind="image", flow_settings=fs)
    tmp = Path(tempfile.mkdtemp(prefix="av_plate_"))
    rows = [SceneRow(scene_number=str(i + 1), script_segment=f"{it['airline']} {it['era']} era plate", asset_type="image",
                     prompt=it["prompt"]) for i, it in enumerate(items)]
    log(f"[AVIATION] Flow: {len(rows)} era picture(s) (free), one per airline x era")
    res = prov.resolve_batch(rows, tmp, log=log)
    out = []
    for i, it in enumerate(items):
        r = res.get(str(i + 1))
        src = getattr(r, "path", None) if r is not None else None
        if not (src and Path(src).is_file()):
            out.append(dict(it, status="failed", error=str(getattr(r, "error", None) or "no image returned")))
            continue
        ent = LIB.add("flow_image", str(src), airline=it["airline"], era=it["era"], subject="era_plate", source="flow",
                      credit="AI illustration (Flow)", ai=True, tags=("flow", "era_plate"), approved=True, lib=lib)
        out.append(dict(it, status="made", path=str(LIB.path_of(ent, lib=lib))))
    return out
