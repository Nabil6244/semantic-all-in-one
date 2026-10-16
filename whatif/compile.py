"""What If: ShotPlan (+ fetched files) -> the renderer's spec (whatif-engine/lib/shots.mjs). A shot whose picture could not be had
is never swapped for an unrelated one: a world with a texture becomes its globe, anything else a dark plate carrying the
sentence's key phrase (a meaningful typographic shot, like the references' title lines)."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import narration as nr
from .planner import PHOTO_WORLDS, Shot, ShotPlan, _world

WIDTH, HEIGHT, FPS = 1920, 1080, 30
LOOK = {"saturate": 0.82, "contrast": 1.04, "lift": "#080B10", "vignette": 0.34, "grain": 0.035}
DRIFT_FOCUS = ((0.5, 0.5), (0.45, 0.5), (0.55, 0.48), (0.5, 0.45), (0.5, 0.55))


def _fallback(s: Shot, notes: List[str]) -> None:
    """This shot has no picture: a meaningful alternative, in place."""
    w = _world(s.text)
    why = s.asset.split(":", 1)[0] if s.asset else "picture"
    if w and w[0] and not PHOTO_WORLDS.search(s.text):
        s.kind, s.texture, s.atmosphere, s.model, s.cite = "globe", w[0], w[2], "", ("ILLUSTRATION", "")
        notes.append(f"shot {s.id}: no {why} could be had, so it shows {w[1].title()} as a globe")
        return
    s.kind, s.tint, s.cite = "plate", "dark", ("ILLUSTRATION", "")
    s.extra["lockup"] = True
    notes.append(f"shot {s.id}: no {why} could be had, so it carries the sentence as a title shot")


def _lockup(s: Shot) -> Optional[Dict[str, Any]]:
    phrase = [re.sub(r"[^\w'°%.\-]", "", t).strip(".-") for t in s.text.split()]
    phrase = [p for p in phrase if p]
    while phrase and phrase[0].lower() in nr.FILLER:
        phrase.pop(0)
    cut = phrase[:7]
    while len(cut) > 2 and (cut[-1].lower() in nr.FILLER or cut[-1].lower() in nr.TAIL_WORDS):
        cut.pop()
    if len(cut) < 2:
        return None
    return {"type": "tm_caption", "text": " ".join(cut).upper(), "size": "large", "anchor": "ml", "start": round(s.start + 0.2, 3),
            "end": round(s.end - 0.2, 3), "fade_in": 0.1, "fade_out": 0.3, "z": 5}


def citation(shots: List[Shot]) -> Dict[str, Any]:
    segs = []
    for s in shots:
        kind, text = s.cite if s.cite[0] else (("ILLUSTRATION", ""))
        if s.kind in ("image", "video") and s.file and not s.asset.lower().startswith(("flow_",)):
            real = bool(s.credit and "nasa" in s.credit.lower() or s.asset.startswith(("nasa_", "commons_", "archive_")))
            # "REAL PHOTO · VENERA 14 · NASA/NSSDCA/COURTESY OF THE USSR": what it shows, then who made it
            kind = ("REAL PHOTO" if s.name else "REAL IMAGE") if real else "IMAGE"
            text = " · ".join(x for x in (s.name.upper() if s.name else "", _credit_text(s.credit) or text) if x)
        elif s.kind in ("image", "video") and s.asset.lower().startswith("flow_"):
            kind, text = "AI ILLUSTRATION", ""
        elif s.kind == "craft":
            kind, text = "ILLUSTRATION", "NASA 3D MODEL · NASA/JPL-CALTECH"
        elif s.kind == "globe":
            kind, text = "ILLUSTRATION", "NASA / SOLAR SYSTEM SCOPE TEXTURE"
        segs.append({"t0": round(s.start, 3), "t1": round(s.end, 3), "kind": kind, "text": text})
    return {"type": "tm_cite", "segments": segs, "z": 12}


def _credit_text(credit: str) -> str:
    return re.sub(r"^(photo|image|credit|footage)\s*:\s*", "", (credit or "").strip(), flags=re.I)[:90]


def _join_same_file(out: List[Dict[str, Any]], names: Dict[str, str], notes: List[str]) -> List[Dict[str, Any]]:
    """Two shots back to back that show the same file are one shot. A split shot (the opening's pace, the 6 s Flow clip rule, a split
    half given its twin's picture) whose halves got the same clip restarted it at frame 0 at the cut -- the probe jumped back and played
    its move again (project #013, 5:51) -- and a picture's slow push restarted, faster, on the shorter half. Joined, the clip plays on
    and the push runs once over the whole length."""
    import hashlib

    by_name = {v: k for k, v in names.items()}
    digest: Dict[str, str] = {}

    def same(name: str) -> str:
        if name not in digest:
            src = Path(by_name.get(name, name))
            try:
                h = hashlib.md5()
                with open(src, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        h.update(chunk)
                digest[name] = h.hexdigest()
            except OSError:
                digest[name] = name
        return digest[name]

    joined: List[Dict[str, Any]] = []
    merged = 0
    for d in out:
        p = joined[-1] if joined else None
        if (p is not None and d["kind"] == p["kind"] and d["kind"] in ("image", "video") and p.get("file") and d.get("file")
                and abs(p["end"] - d["start"]) < 0.05 and same(p["file"]) == same(d["file"])):
            p["end"] = d["end"]
            p["exit"] = d.get("exit", p.get("exit"))
            merged += 1
            continue
        joined.append(d)
    if merged:
        notes.append(f"{merged} cut(s) between two shots of the same picture or clip removed: it plays on instead of restarting")
    return joined


def compile_spec(plan: ShotPlan, *, width: int = WIDTH, height: int = HEIGHT, fps: int = FPS, media_dir: Optional[Path] = None,
                 title: str = "") -> Dict[str, Any]:
    """The spec for whatif-engine. Files are hard-linked into media_dir (one folder the renderer serves)."""
    notes: List[str] = list(plan.notes)
    shots = plan.shots
    layers: List[Dict[str, Any]] = [dict(L) for L in plan.layers]
    names: Dict[str, str] = {}

    def place(src: str) -> str:
        p = Path(src).resolve()
        if str(p) not in names:
            if media_dir is None:
                return str(p)
            Path(media_dir).mkdir(parents=True, exist_ok=True)
            name = f"{len(names) + 1:03d}_{p.name}"
            try:
                os.link(p, Path(media_dir) / name)
            except OSError:
                shutil.copy2(p, Path(media_dir) / name)
            names[str(p)] = name
        return names[str(p)]

    out_shots: List[Dict[str, Any]] = []
    for n, s in enumerate(shots):
        if s.kind in ("image", "video") and s.file and not Path(s.file).is_file():
            notes.append(f"shot {s.id}: its picture {Path(s.file).name} is no longer on disk (cache cleared or file moved)")
            s.file = ""
        if s.kind in ("image", "video") and not s.file:
            if s.asset.lower().startswith("file:") and Path(s.asset.split(":", 1)[1].strip()).is_file():
                s.file = s.asset.split(":", 1)[1].strip()
            else:
                _fallback(s, notes)
                if s.extra.get("lockup") and (L := _lockup(s)):
                    layers.append(L)
        d: Dict[str, Any] = {"id": s.id, "start": round(s.start, 3), "end": round(s.end, 3), "kind": s.kind, "exit": s.exit}
        if s.kind in ("image", "video"):
            d["file"] = place(s.file)
            if s.cite[0] == "REAL IMAGE" and s.kind == "image" and not s.extra.get("full_bleed"):
                d["compose"] = "letterbox"            # a real photograph: the whole picture over a blurred copy of itself (V1 6:40)
            fx, fy = DRIFT_FOCUS[n % len(DRIFT_FOCUS)]
            d["drift"] = {"from": 1.0, "to": 1.04, "fx": fx, "fy": fy}
            if s.kind == "video":
                d["in_s"], d["loop"] = float(s.extra.get("in_s", 0)), True
        elif s.kind == "plate":
            d["tint"], d["title"], d["sub"] = s.tint, s.title, s.sub
            d["lockup"] = bool(s.extra.get("lockup"))            # a typographic stand-in: the act's instruments stay on over it
        elif s.kind == "hero":
            d["scene"], d["cam"] = s.scene, s.cam
        elif s.kind == "craft":
            d["model"], d["cam"] = s.model, s.cam
            d["spin_deg_s"] = float(s.extra.get("spin_deg_s", 0))
        elif s.kind == "globe":
            d["texture"], d["cam"], d["atmosphere"] = s.texture, s.cam, s.atmosphere
        out_shots.append(d)
    out_shots = _join_same_file(out_shots, names, notes)
    # the photograph of a disc-map plate (V2 0:22): the plate shot's fetched file goes into its tm_discmap layer
    for s in shots:
        if s.kind == "plate" and s.file and Path(s.file).is_file():
            for L in layers:
                if L.get("type") == "tm_discmap" and s.start - 0.1 <= float(L["start"]) < s.end:
                    L["image"] = place(s.file)
                if L.get("type") == "tm_template" and L.get("image_slot") and s.start - 0.1 <= float(L["start"]) < s.end:
                    L.setdefault("slots", {})[L["image_slot"]] = place(s.file)     # the template's photo (eht_pair, map_overlay ...)
    for L in layers:                     # a template photo given as a local file: placed in the media folder like any other
        if L.get("type") == "tm_template" and L.get("image_slot"):
            v = str(L.get("slots", {}).get(L["image_slot"], ""))
            if v.lower().startswith("file:") and Path(v.split(":", 1)[1].strip()).is_file():
                L["slots"][L["image_slot"]] = place(v.split(":", 1)[1].strip())
    layers.append(citation(shots))
    spec = {"width": width, "height": height, "fps": fps, "duration": round(plan.duration, 3), "look": dict(LOOK), "shots": out_shots,
            "layers": layers, "whatif": {"title": title or plan.title, "notes": notes}}
    if media_dir is not None:
        spec["media_dir"] = str(media_dir)
    return spec
