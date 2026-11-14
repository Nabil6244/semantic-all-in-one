"""Real clips for Ocean Predators (docs/ocean/PATTERNS.md section 3, plan step 6): about one shot in six is a short real
clip (3-6 s), graded into the blue world (less colour, cooler, vignette) with a small credit line bottom-left, used for the
"this is real" moments. Everything is fetched through the app's own stock sources into the Visuals tab (visual_bridge
owner "ocean"), so the user reviews, retries or swaps clips there before Render; Render uses exactly what the tab holds.

    choose(scenes, layers, total)      -> [slot]   slot = {"scene_no", "start", "end", "query", "text", "why"}
    query_for(features, set_name)      -> str      a stock search from the animals the sentence names (+ the set's place)
    visual_scenes(slots)               -> [scene]  rows for fetch_csv_footage / the Visuals tab (asset_type stock_video)
    credit(meta)                       -> str      "Footage: <author> / <provider>" from the clip's own record
    grade(src, dst, seek, seconds)     -> dst      ffmpeg: fit 1280 x 720, desaturate, cool, vignette, no audio
    apply(plan, found, black, work)    -> (shots, layers)   the timeline with clip shots cut in and the stage hidden there

Slot rules (by sentence shape, never topic): a sentence that names an animal the kit knows is a candidate; "filmed /
footage / camera / drone / spotted / photographed / real / first time / caught" make it a strong one; a sentence with a
full-screen or text card is never used (the card is the point there); slots keep CLIP_GAP_S apart and number about one per
CLIP_EVERY_S of film. A slot whose clip is missing or failed simply keeps the drawn stage: a clip never leaves a hole.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import reader as R

CLIP_MIN_S, CLIP_MAX_S = 3.0, 5.5
CLIP_GAP_S = 30.0
CLIP_EVERY_S = 40.0
REAL = re.compile(r"\b(film(ed|ing|s)?|footage|camera|cameras|drones?|spotted|photograph(ed|s)?|caught|real|really|actually|"
                  r"first time|first ever|for the first|seen|recorded|observed|witness(ed)?|video)\b", re.I)
QUERY = {
    "great_white": "great white shark underwater", "shark": "shark swimming underwater", "megalodon": "great white shark underwater",
    "orca": "orca killer whale swimming", "humpback": "humpback whale underwater", "sperm_whale": "sperm whale underwater",
    "dolphin": "dolphins swimming underwater", "seal": "sea lion seal underwater", "squid": "squid deep sea",
    "colossal_squid": "giant squid deep sea", "diver": "scuba diver underwater", "boat": "boat ocean aerial",
}
PLACE = {"surface": "surface", "seafloor": "sea floor", "abyss": "deep sea dark", "kelp": "kelp forest", "depth_column": "deep"}
SKIP_ANIMALS = ("cage", "tooth")
GRADE = ("eq=saturation=0.58:contrast=1.06:brightness=-0.035,"
         "colorbalance=rs=-0.06:gs=-0.01:bs=0.10:rm=-0.04:bm=0.06:rh=-0.02:bh=0.03,vignette=PI/4.6")


# ---------------------------------------------------------------------------------------------------------------- choose

def query_for(f: R.Features, set_name: str = "") -> str:
    names = [a for a in f.animals if a[0] not in SKIP_ANIMALS]
    if not names:
        return ""
    a = names[0]
    q = QUERY.get(a[0], a[4] + " underwater")
    if a[2].get("color") and not a[2].get("generic"):        # a named variant: "blue whale", "tiger shark", "vampire squid"
        word = re.sub(r"(?<!s)s$", "", a[4].lower().strip())
        q = f"{word} {'deep sea' if 'squid' in word else 'underwater'}"
    if a[1] and a[0] in ("orca", "dolphin", "seal"):
        q += " group"
    place = PLACE.get(set_name)
    if a[0] == "boat":
        return q
    if place == "surface":
        q = q.replace(" underwater", "").replace(" swimming", "") + " ocean surface"
    elif place and not any(w in q for w in place.split()):
        q += " " + place
    return re.sub(r"\s+", " ", q).strip()


def _busy(layers: Sequence[Dict[str, Any]]) -> List[Tuple[float, float]]:
    """Absolute windows where a full-screen or text card is up (no clip there)."""
    from .planner import FULL, TEXT_CARDS

    out = []
    for ly in layers:
        if ly.get("name") != "ocean.lay_ocean":
            continue
        s0 = float(ly["start"])
        for e in (ly.get("params") or {}).get("elements") or []:
            k = e.get("kind", "")
            if k.startswith("ocean_") and (k[6:] in FULL or k[6:] in TEXT_CARDS):
                t1 = e.get("t1")
                out.append((s0 + float(e["t0"]), s0 + float(t1 if t1 is not None else float(ly["end"]) - s0)))
    return out


def _shot_at(layers: Sequence[Dict[str, Any]], t: float) -> Optional[Dict[str, Any]]:
    for ly in layers:
        if ly.get("name") == "ocean.lay_ocean" and float(ly["start"]) <= t < float(ly["end"]):
            return ly
    return None


def choose(scenes: Sequence[Dict[str, Any]], layers: Sequence[Dict[str, Any]], total: float,
           shots: Sequence[Dict[str, Any]] = ()) -> List[Dict[str, Any]]:
    busy = _busy(layers)
    want = max(1, int(round(total / CLIP_EVERY_S))) if total >= 20 else 0
    cands: List[Tuple[float, Dict[str, Any]]] = []
    set_at = {round(float(s["start"]), 3): s.get("set", "") for s in shots}
    for i, sc in enumerate(scenes):
        a, b = float(sc["start"]), float(sc["end"])
        if b - a < CLIP_MIN_S - 0.6 or a < 4.0 or b > total - 6.0:
            continue
        f = R.read(str(sc.get("text", "")))
        ly = _shot_at(layers, a + 0.05)
        set_name = next((v for k, v in sorted(set_at.items()) if k <= a + 0.05), "") if set_at else ""
        q = query_for(f, set_name)
        if not q or ly is None:
            continue
        start = a + 0.15
        end = min(b, start + CLIP_MAX_S, float(ly["end"]))
        if end - start < CLIP_MIN_S:
            if i + 1 < len(scenes) and float(ly["end"]) - start >= CLIP_MIN_S:
                end = min(start + CLIP_MIN_S + 0.5, float(ly["end"]))      # a short line runs on into the next one
            else:
                continue
        if any(min(end, y) - max(start, x) > 0 for x, y in busy):
            continue
        score = (2.0 if REAL.search(f.text) else 0.0) + 1.0 + (0.5 if f.group else 0.0) + (0.3 if set_name == "surface" else 0.0)
        cands.append((score, {"scene_no": str(sc.get("scene_no", i + 1)), "start": round(start, 3), "end": round(end, 3),
                              "query": q, "text": str(sc.get("text", "")), "why": "real" if score >= 3 else "animal"}))
    cands.sort(key=lambda c: (-c[0], c[1]["start"]))
    picked: List[Dict[str, Any]] = []
    used_q: Dict[str, int] = {}
    for score, s in cands:
        if len(picked) >= want:
            break
        if any(abs(s["start"] - p["start"]) < CLIP_GAP_S for p in picked):
            continue
        if used_q.get(s["query"], 0) >= 2 and score < 3:
            continue                                  # the same search at most twice unless the line says it is real footage
        picked.append(s)
        used_q[s["query"]] = used_q.get(s["query"], 0) + 1
    return sorted(picked, key=lambda s: s["start"])


def visual_scenes(slots: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{"scene_no": s["scene_no"], "text": s["text"], "asset_type": "stock_video", "prompt": s["query"],
             "stock": s["query"], "start": s["start"], "end": s["end"]} for s in slots]


# ---------------------------------------------------------------------------------------------------------------- render

def credit(meta: Optional[Dict[str, Any]]) -> str:
    m = meta or {}
    if m.get("user_supplied") and not m.get("author"):
        return ""
    who = str(m.get("author") or m.get("channel") or "").strip()
    src = str(m.get("provider") or m.get("source") or "").strip()
    src = {"pexels": "Pexels", "pixabay": "Pixabay", "youtube": "YouTube", "nasa": "NASA", "noaa": "NOAA", "coverr": "Coverr",
           "videvo": "Videvo", "mixkit": "Mixkit"}.get(src.lower(), src.title() if src.islower() else src)
    lic = str(m.get("license") or "").strip()
    if not who and not src:
        return ""
    text = "Footage: " + " / ".join(x for x in (who, src) if x)
    if lic and re.search(r"cc|creative|public", lic, re.I):
        text += f" ({lic})"
    return text[:90]


def _duration(path: str) -> float:
    try:
        return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                             timeout=30).strip())
    except Exception:  # noqa: BLE001
        return 0.0


def grade(src: str, dst: str, seek: float, seconds: float) -> str:
    from cinematic_explainer.render import H, W

    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, seek):.3f}", "-t", f"{seconds + 0.6:.3f}", "-i", src, "-an",
                    "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30,setsar=1,{GRADE}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", dst], check=True, timeout=600)
    return dst


def apply(plan: Dict[str, Any], found: Dict[str, Dict[str, Any]], black: str, work: str,
          log=lambda m: None) -> Tuple[List[Any], List[Any], List[Dict[str, Any]]]:
    """(shots, layers, used) with every slot whose clip was found cut in; `found` = {scene_no: {"path", "meta"}}."""
    from cinematic_explainer.render import Layer, Shot

    total = float(plan["total"])
    used: List[Dict[str, Any]] = []
    wd = Path(work)
    for s in plan.get("clips") or []:
        f = found.get(str(s["scene_no"]))
        if not f or not f.get("path") or not Path(f["path"]).is_file():
            continue
        a, b = float(s["start"]), float(s["end"])
        src_len = _duration(f["path"])
        if src_len < 1.0:
            continue
        b = min(b, a + max(1.0, src_len - 0.2))
        seek = 0.0 if src_len < (b - a) + 2.0 else min(1.5, src_len - (b - a) - 0.5)
        dst = wd / f"clip_{s['scene_no']}.mp4"
        try:
            grade(f["path"], str(dst), seek, b - a)
        except Exception as ex:  # noqa: BLE001 - a clip that cannot be graded keeps the drawn stage
            log(f"clip for scene {s['scene_no']} skipped ({ex})")
            continue
        used.append({**s, "start": a, "end": b, "path": str(dst), "credit": credit(f.get("meta"))})
    used.sort(key=lambda u: u["start"])
    shots: List[Any] = []
    t = 0.0
    for u in used:
        if u["start"] > t + 1e-3:
            shots.append(Shot(black, t, u["start"], t))
        shots.append(Shot(u["path"], u["start"], u["end"], 0.0))
        t = u["end"]
    if t < total - 1e-3 or not shots:
        shots.append(Shot(black, t, total, t))
    layers: List[Any] = []
    for ly in plan.get("layers") or []:
        p = dict(ly.get("params") or {})
        a, b = float(ly["start"]), float(ly["end"])
        if ly.get("name") == "ocean.lay_ocean":
            holes = [[u["start"] - a, u["end"] - a, u["credit"]] for u in used if u["end"] > a and u["start"] < b]
            if holes:
                p["holes"] = holes
        layers.append(Layer(ly["name"], a, b, p))
    return shots, layers, used
