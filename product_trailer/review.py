"""Review mode: a long, voice-over-driven film (the iPhone Duo review style) from a script, with no presenter and no real footage.

Script markup (plain text):

    # Title of the review                    (optional)
    ## Design                                a chapter: a section card, then its lines
    The frame is flat and the back is matte. The hinge feels firm.
    [bars: Geekbench 6.5 multi-core | Exynos 2700=13000 | Snapdragon=11000]     a chart slot (big readable bars)
    [stat: 1h40min | Full charge, as tested]                                    a stat callout over a 3D shot

    parse_script(text)                       -> chapters
    plan_review_scenes(parsed, phone, cols)  -> a scene pack (product_trailer.scenepack) for the AI shots of the film
    plan_review(parsed, pack, results)       -> What If spec: chapter cards, AI stills (slow push) or 3D, charts, stat callouts, subtitles

Subtitles are 6 to 9 words at a time, split evenly over each line's spoken time (2.7 words per second); in the app the voice-over alignment
replaces these times. A line whose AI picture is missing or failed becomes a 3D shot, so the film never stops on Flow.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .scenepack import DESIGN, NO_BRAND, estimate

WORDS_PER_S = 2.7
PAUSE_S = 0.25
MIN_SHOT_S, MAX_SHOT_S = 2.5, 7.0
CHAPTER_S = 2.6
MIN_CHART_S = 3.5
MAX_HOLD_S = 5.0
HOLD_STEP_S = 4.5
MAX_SCENE_S = 9.0          # a scene stays on screen for the sentences that follow it for at most this long, then the film moves on to other pictures
CHUNK_WORDS = 7
FLAT_LOOK = {"saturate": 1.0, "contrast": 1.0, "vignette": 0.0, "grain": 0.0}
LOOK = {"saturate": 0.97, "contrast": 1.05, "lift": "#05070B", "vignette": 0.25, "grain": 0.025}

# line keywords -> an AI scene type for a review (hands-on and lab looks), or None to stay 3D
REVIEW_TYPES: Dict[str, Dict[str, Any]] = {
    "hands_desk": {"words": ("hold", "hand", "grip", "use", "daily", "feel", "comfortable", "one hand", "carry", "pocket"),
                   "refs": ["ref1_fan_backs", "ref4_one_three_quarter"],
                   "prompt": "Photorealistic photo. A hand holding one {one_colour} smartphone over a tidy workshop desk with tools softly out of focus. {design}; {nobrand}. "
                             "Natural light, shallow depth of field, 35mm lens, realistic skin, 16:9."},
    "lab_rig": {"words": ("test", "scratch", "fold", "hinge", "durab", "bend", "force", "stress", "drop", "tough", "crease"),
                "refs": ["ref4_one_three_quarter", "ref5_camera_macro"],
                "prompt": "Photorealistic photo. One {one_colour} smartphone clamped in a metal test rig on a workshop bench with a force gauge and a dial indicator, "
                          "back toward the camera, nothing readable on any gauge. {design}; {nobrand}. Cool workshop light, shallow depth of field, 50mm lens, 16:9."},
    "charging_cable": {"words": ("charge", "charging", "plug", "cable", "watt", "charger", "power", "battery"),
                      "refs": ["ref4_one_three_quarter", "ref5_camera_macro"],
                      "prompt": "Photorealistic photo. A hand plugging a USB-C cable into the bottom edge of a {one_colour} smartphone lying on a warm wooden desk, a plain white charger "
                                "brick and cable in view, nothing readable on the screen. {design}; {nobrand}. Soft window light, shallow depth of field, 35mm lens, 16:9."},
    "charging_desk": {"words": ("charge", "charging", "battery", "power", "fills", "percent"),
                      "refs": ["ref4_one_three_quarter", "ref2_row_fronts"],
                      "prompt": "Photorealistic photo. A {one_colour} smartphone lying flat on a tidy desk beside a laptop, a thin charging cable attached, the screen softly glowing "
                                "with an abstract ripple wallpaper and no readable text. {design}; {nobrand}. Natural light, shallow depth of field, 50mm lens, 16:9."},
    "macro_edge": {"words": ("edge", "frame", "metal", "thin", "slim", "button", "port", "speaker", "camera", "lens"),
                   "refs": ["ref5_camera_macro", "ref4_one_three_quarter"],
                   "prompt": "Photorealistic macro photo of the edge and camera module of a {one_colour} smartphone on a clean grey bench. {design}; {nobrand}. "
                             "Very shallow depth of field, soft window light, 85mm macro look, 16:9."},
    "desk_row": {"words": ("compare", "versus", "color", "colour", "lineup", "display", "screen", "bright", "wallpaper"),
                 "refs": ["ref2_row_fronts", "ref3_row_backs"],
                 "prompt": "Photorealistic photo. Four smartphones standing upright side by side on a desk in a workshop, screens glowing with ripple wallpapers ({colours}). "
                           "{design}; {nobrand}. Soft light, shallow depth of field, 35mm lens at desk height, 16:9."},
}
THREE_D_WORDS = ("chip", "processor", "benchmark", "score", "geekbench", "inside", "teardown", "x-ray", "mah", "silicon")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


ROOMS = ["loft", "gallery", "studio", "terrace", "desk"]
POSES = ["back", "front", "mixed", "fan"]
MACRO_MOVES = ["island", "edge", "port", "buttons", "screen", "monolith"]
DIRECTIVE_SECONDS = {"bars": 7.0, "curve": 8.0, "compare": 7.0, "stat": 4.0, "xray": 5.0, "fold": 5.0, "lineup": 5.0, "chip": 5.0, "macro": 4.0,
                     "bigtype": 3.5, "intro": 5.0, "outro": 5.0, "flat": 5.0, "gauge": 5.5, "tweet": 6.0, "thermal": 5.5, "cost": 6.0, "scene": 4.0, "bench": 5.5}
PAPER_SHOT = {"kind": "black"}
STYLES = ("mixed", "cinematic", "infographic", "follow")


def _paper(layers_fn):
    """Wrap a layer maker so the flat paper sheet is drawn first (the shot under it is black and never seen)."""
    return lambda a, b: [{"type": "pt_paper", "start": a, "end": b, "fade_in": 0, "fade_out": 0}] + layers_fn(a, b)


BENCH_TINTS = ["teal", "green", "blue"]


def bench_visual(it: Dict[str, Any], phone: str, k: int):
    """The review-lab set: phones on stands showing a chart / figure each, with frosted glass cards over the scene for the compared figures."""
    its = it["items"][:3]
    n = len(its)
    types = ["chart", "number", "bars"]
    screens = [{"type": types[i % 3], "title": it.get("heading", ""), "label": x["label"], "value": x["value"], "unit": x["unit"],
                "values": [x["value"], x["value"] * 0.86] if types[i % 3] == "chart" else [x["value"], x["value"] * 0.7, x["value"] * 0.5]} for i, x in enumerate(its)]
    shot = {"kind": "product", "object": "bench", "phone": phone, "screens": screens, "palette": ["blue", "teal", "amber"][k % 3], "seed": 13 + k}
    xs = {2: [0.27, 0.73], 3: [0.19, 0.5, 0.81]}[max(2, n)]
    cards = [{"title": x["label"], "value": x["value"], "unit": x["unit"], "tint": BENCH_TINTS[i % 3], "x": xs[i], "y": 0.2, "w": 0.24 if n == 2 else 0.2} for i, x in enumerate(its)]
    return shot, lambda a, b: [{"type": "pt_glass", "heading": it.get("heading", ""), "cards": cards, "start": a + 0.3, "end": b - 0.1}], 5.5


def infographic_visual(it: Dict[str, Any], phone: str, cols: Sequence[str], k: int):
    """The flat-paper look of the explainer reviews for one directive, or None when the directive has no flat form (it stays 3D)."""
    kind = it["kind"]
    sec = DIRECTIVE_SECONDS.get(kind, 5.0)
    swatch = ["#5b5a86", "#2b2b2e", "#7a2f45", "#cfc9de"]
    if kind == "flat":
        phs = [{"cams": 3 + (i % 2), "color": swatch[i % 4], **p} for i, p in enumerate(it["phones"])]
        return PAPER_SHOT, _paper(lambda a, b: [{"type": "pt_flatphones", "title": it["title"], "phones": phs, "start": a + 0.1, "end": b - 0.05}]), sec
    if kind == "stat":
        ph = [{"label": phone.title(), "text": str(it["value"]), "color": swatch[1], "cams": 3}]
        return PAPER_SHOT, _paper(lambda a, b: [{"type": "pt_flatphones", "title": it["label"], "phones": ph, "start": a + 0.1, "end": b - 0.05}]), 4.0
    if kind == "scene":
        lay = dict(it["layer"])
        lay.setdefault("type", "pt_flatphones")
        return PAPER_SHOT, _paper(lambda a, b: [{**lay, "start": a + 0.05, "end": b - 0.03}]), sec
    if kind == "thermal":
        return PAPER_SHOT, lambda a, b: [{"type": "pt_thermal", "title": it["title"], "phones": it["phones"], "start": a + 0.1, "end": b - 0.05}], sec
    if kind == "cost":
        return PAPER_SHOT, lambda a, b: [{"type": "pt_coststack", "title": it["title"], "rows": it["rows"], "total": it["total"], "start": a + 0.1, "end": b - 0.05}], sec
    if kind == "gauge":
        return PAPER_SHOT, _paper(lambda a, b: [{"type": "pt_gauge", "title": it["title"], "unit": it["unit"], "max": it["max"], "gauges": it["gauges"], "start": a + 0.1, "end": b - 0.05}]), sec
    if kind == "tweet":
        return PAPER_SHOT, _paper(lambda a, b: [{"type": "pt_tweet", **{x: it[x] for x in ("author", "handle", "text", "highlight")}, "start": a + 0.1, "end": b - 0.05}]), sec
    if kind == "curve":
        return PAPER_SHOT, _paper(lambda a, b: [{"type": "pt_curve", "title": it["title"], "x_label": it["x_label"], "y_label": it["y_label"], "points": it["points"],
                                                 "marks": it["marks"], "level": {"y": max(p[1] for p in it["points"]), "text": ""}, "start": a + 0.2, "end": b - 0.1}]), sec
    if kind == "compare":
        return PAPER_SHOT, _paper(lambda a, b: [{"type": "pt_compare3", "title": it["title"], "unit": it["unit"], "cols": it["cols"], "start": a + 0.2, "end": b - 0.1}]), sec
    if kind == "bars":
        return PAPER_SHOT, _paper(lambda a, b: [{"type": "pt_bench", "title": it["title"], "rows": it["rows"], "start": a + 0.2, "end": b - 0.1}]), sec
    return None


def line_visual(phone: str, cols: Sequence[str], k: int):
    """A narrated line in the infographic style: a row of flat phones on the paper, drifting slightly (never a still screen)."""
    swatch = ["#5b5a86", "#2b2b2e", "#7a2f45", "#cfc9de"]
    n = 1 + k % 3
    ph = [{"cams": 3 + (i % 2), "color": swatch[(i + k) % 4], "label": phone.title() if i == 0 else ""} for i in range(n)]
    return PAPER_SHOT, _paper(lambda a, b: [{"type": "pt_flatphones", "phones": ph, "start": a, "end": b}])


def directive_visual(it: Dict[str, Any], phone: str, cols: Sequence[str], k: int, product: Optional[Dict[str, Any]] = None, style: str = "cinematic"):
    """The shot and layers of one non-spoken item (chart, stat, X-ray, fold, lineup, chip, macro, big word, intro, outro): (shot fields, make(a, b) -> layers, seconds)."""
    kind = it["kind"]
    if kind == "bench":
        return bench_visual(it, phone, k)
    if style in ("infographic", "follow") or kind in ("flat", "gauge", "tweet", "thermal", "cost", "scene"):
        flat = infographic_visual(it, phone, cols, k)
        if flat:
            return flat
    cap = lambda text, a, b: [{"type": "pt_caption", "text": text, "y": 0.13, "size": 0.075, "start": round(a + 0.4, 3), "end": round(b - 0.2, 3)}] if text else []
    sec = DIRECTIVE_SECONDS.get(kind, 5.0)
    if kind == "bars":
        return {"kind": "plate", "tint": "blue"}, lambda a, b: [{"type": "pt_bench", "title": it["title"], "rows": it["rows"], "start": a + 0.2, "end": b - 0.1}], sec
    if kind == "curve":
        return {"kind": "plate", "tint": "blue"}, lambda a, b: [{"type": "pt_curve", "title": it["title"], "x_label": it["x_label"], "y_label": it["y_label"], "points": it["points"],
                                                                  "marks": it["marks"], "level": {"y": max(p[1] for p in it["points"]), "text": ""}, "start": a + 0.2, "end": b - 0.1}], sec
    if kind == "compare":
        return {"kind": "plate", "tint": "cool"}, lambda a, b: [{"type": "pt_compare3", "title": it["title"], "unit": it["unit"], "cols": it["cols"], "start": a + 0.2, "end": b - 0.1}], sec
    if kind == "stat":
        return ({"kind": "product", "object": "lineup", "phone": phone, "colors": list(cols), "room": "studio", "pose": "front", "seed": 5 + k},
                lambda a, b: [{"type": "tm_metric", "value": it["value"], "unit": "", "sub": it["label"].upper(), "size": "large", "anchor": "center", "start": a + 0.2, "end": b - 0.1}], sec)
    if kind in ("xray", "fold"):
        shot = {"kind": "product", "object": kind, "seed": 21 + k, **({"explode": [0, 1]} if kind == "xray" else {"angle": [180, 15]})}
        return shot, lambda a, b: cap(it.get("text"), a, b), sec
    if kind == "lineup":
        shot = {"kind": "product", "object": "lineup", "phone": phone, "colors": list(cols), "room": it.get("room") or ROOMS[k % len(ROOMS)], "pose": it.get("pose") or POSES[k % 4], "seed": 11 + k}
        return shot, lambda a, b: cap(it.get("text"), a, b), sec
    if kind == "chip":
        shot = {"kind": "product", "object": "chip", "move": "chip", "label": str(it.get("label") or "Chip").upper(), "sublabel": "Reported", "glow": "#3ac8ff", "heat": [0.0, 0.4], "seed": 31 + k}
        return shot, lambda a, b: cap(it.get("text"), a, b), sec
    if kind == "macro":
        move = it.get("move") if it.get("move") in MACRO_MOVES else MACRO_MOVES[k % len(MACRO_MOVES)]
        shot = {"kind": "product", "object": "phone", "phone": phone, "move": move, "backdrop": "charcoal", "seed": 41 + k}
        return shot, lambda a, b: cap(it.get("text"), a, b), sec
    if kind == "bigtype":
        shot = {"kind": "product", "object": "phone", "phone": phone, "move": "monolith", "backdrop": "charcoal", "seed": 51 + k}
        return shot, lambda a, b: [{"type": "pt_bigtype", "text": str(it.get("text") or ""), "y": 0.22, "start": a + 0.2, "end": b - 0.1}], sec
    if kind == "intro":
        shot = {"kind": "product", "object": "lineup", "phone": phone, "colors": list(cols), "room": "gallery", "pose": "back", "turn": [0.45, 0.8], "seed": 3}
        return shot, lambda a, b: cap(it.get("text") or (product or {}).get("name") or phone.title(), a, b), sec
    if kind == "outro":
        shot = {"kind": "product", "object": "lineup", "phone": phone, "colors": list(cols), "room": "loft", "pose": "front", "frame_side": "right", "seed": 4}
        return shot, lambda a, b: [{"type": "pt_reveal", "kicker": (product or {}).get("intro", "Introducing"), "name": it.get("text") or (product or {}).get("name") or phone.title(),
                                    "side": "left", "start": a + 0.3, "end": b - 0.1}], sec
    raise ValueError(f"unknown item kind {kind!r}")


TEXT_COLS = ("text", "line", "narration", "script_segment", "script", "sentence", "voiceover", "voice")
VISUAL_COLS = ("visual", "directive", "graphic", "shot")


def csv_to_script(text: str) -> str:
    """A review CSV as the script markup. Columns (any order, case-insensitive): the narration (text, line, narration or script_segment), an optional
    visual ("xray: Inside the hinge", "bars: ...", "lineup: ..."; brackets optional) and an optional chapter. No header: each row's first cell is a line."""
    import csv as _csv
    import io

    rows = [r for r in _csv.reader(io.StringIO(text.lstrip("\ufeff"))) if any(c.strip() for c in r)]
    if not rows:
        return ""
    head = [c.strip().lower() for c in rows[0]]
    t_i = next((head.index(c) for c in TEXT_COLS if c in head), None)
    v_i = next((head.index(c) for c in VISUAL_COLS if c in head), None)
    c_i = head.index("chapter") if "chapter" in head else None
    body = rows[1:] if (t_i is not None or v_i is not None) else rows
    if t_i is None:
        t_i = 0 if v_i != 0 else None
    out, chapter = [], None
    for r in body:
        cell = lambda i: _clean(r[i]) if i is not None and i < len(r) else ""
        if c_i is not None and cell(c_i) and cell(c_i) != chapter:
            chapter = cell(c_i)
            out.append(f"## {chapter}")
        v = cell(v_i)
        if v:
            out.append(v if v.startswith("[") else f"[{v}]")
        if cell(t_i):
            out.append(cell(t_i))
    return "\n".join(out)


def review_source(script: Optional[str], csv_path: Optional[str]) -> str:
    """The pasted script when there is one, else the review CSV converted to a script, else ''."""
    if (script or "").strip():
        return script
    if csv_path and Path(csv_path).is_file():
        return csv_to_script(Path(csv_path).read_text(encoding="utf-8-sig"))
    return ""


def parse_script(text: str) -> Dict[str, Any]:
    title, chapters = "", []
    cur: Optional[Dict[str, Any]] = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## "):
            cur = {"title": _clean(line[3:]), "items": []}
            chapters.append(cur)
        elif line.startswith("# "):
            title = _clean(line[2:])
        elif line.startswith("[") and line.endswith("]"):
            cur = cur or chapters.append({"title": "", "items": []}) or chapters[-1]
            m = re.match(r"\[(bars|stat|curve|compare|xray|fold|lineup|chip|macro|bigtype|intro|outro|flat|gauge|tweet|thermal|cost|scene|bench)\s*:\s*(.*)\]$", line, re.I)
            if not m:
                continue
            parts = [p.strip() for p in m.group(2).split("|")]
            kind = m.group(1).lower()
            if kind == "scene":        # [scene: {"title": ..., "phones": [...]}]  any flat-phone scene as JSON (see layers/pt_flatphones.mjs)
                try:
                    import json as _json

                    layer = _json.loads(m.group(2))
                    if isinstance(layer, dict) and layer.get("phones"):
                        cur["items"].append({"kind": "scene", "layer": layer})
                except ValueError:
                    pass
                continue
            if kind in ("xray", "fold", "bigtype", "intro", "outro"):
                cur["items"].append({"kind": kind, "text": parts[0] if parts and parts[0] else ""})
            elif kind == "lineup":     # [lineup: caption | room | pose]
                cur["items"].append({"kind": "lineup", "text": parts[0] if parts else "", "room": (parts[1] if len(parts) > 1 and parts[1] in ROOMS else None),
                                     "pose": (parts[2] if len(parts) > 2 and parts[2] in POSES else None)})
            elif kind == "chip":       # [chip: LABEL | caption]
                cur["items"].append({"kind": "chip", "label": parts[0] if parts else "", "text": parts[1] if len(parts) > 1 else ""})
            elif kind == "macro":      # [macro: caption | move]
                cur["items"].append({"kind": "macro", "text": parts[0] if parts else "", "move": parts[1] if len(parts) > 1 else None})
            elif kind == "curve" and len(parts) >= 4:
                pts = []
                for p in parts[3].replace(";", ",").split(","):
                    x, _, y = p.strip().partition(":")
                    try:
                        pts.append([float(x), float(y)])
                    except ValueError:
                        continue
                marks = []
                for p in parts[4:]:
                    x, _, text = p.partition("=")
                    try:
                        marks.append({"x": float(x), "text": text.strip()})
                    except ValueError:
                        continue
                if len(pts) >= 2:
                    cur["items"].append({"kind": "curve", "title": parts[0], "x_label": parts[1], "y_label": parts[2], "points": pts, "marks": marks})
            elif kind == "compare" and len(parts) >= 4:
                cols = []
                for p in parts[2:]:
                    label, _, val = p.partition("=")
                    try:
                        cols.append({"label": label.strip(), "value": float(val.replace(",", ""))})
                    except ValueError:
                        continue
                if len(cols) >= 2:
                    cols[0]["highlight"] = True
                    cur["items"].append({"kind": "compare", "title": parts[0], "unit": parts[1], "cols": cols})
            elif kind == "bars" and len(parts) >= 3:
                rows = []
                for p in parts[1:]:
                    label, _, val = p.partition("=")
                    try:
                        rows.append({"label": label.strip(), "value": float(val.replace(",", "")), "text": f"{float(val.replace(',', '')):,.0f}"})
                    except ValueError:
                        continue
                if rows:
                    rows[0]["highlight"] = True
                    cur["items"].append({"kind": "bars", "title": parts[0], "rows": rows})
            elif kind == "flat" and len(parts) >= 2:   # [flat: TITLE | Name=60W@95 | Name=45W@80 ...]  (@ = battery fill percent)
                phones = []
                for p in parts[1:]:
                    label, _, rest = p.partition("=")
                    text, _, fill = rest.partition("@")
                    ph = {"label": label.strip(), "text": text.strip()}
                    try:
                        ph["fill"] = float(fill) / 100.0 if fill.strip() else None
                    except ValueError:
                        ph["fill"] = None
                    if ph["fill"] is None:
                        del ph["fill"]
                    phones.append(ph)
                if phones:
                    cur["items"].append({"kind": "flat", "title": parts[0], "phones": phones})
            elif kind == "gauge" and len(parts) >= 4:  # [gauge: TITLE | unit | max | A=30.12 | B=127.51]
                gs = []
                for p in parts[3:]:
                    label, _, val = p.partition("=")
                    try:
                        gs.append({"label": label.strip(), "value": float(val.replace(",", ""))})
                    except ValueError:
                        continue
                try:
                    mx = float(parts[2])
                except ValueError:
                    mx = 0.0
                if gs:
                    max(gs, key=lambda x: x["value"])["highlight"] = True
                    cur["items"].append({"kind": "gauge", "title": parts[0], "unit": parts[1], "max": mx, "gauges": gs})
            elif kind == "tweet" and len(parts) >= 3:  # [tweet: Author @handle | text | phrase to highlight]
                who = parts[0].split("@", 1)
                cur["items"].append({"kind": "tweet", "author": who[0].strip() or "Source", "handle": ("@" + who[1].strip()) if len(who) > 1 else "",
                                     "text": parts[1], "highlight": parts[2]})
            elif kind == "bench" and len(parts) >= 3:     # [bench: HEADING | iPhone 18 Pro=1.2 ms | iPhone 17 Pro=59.2 ms]  (a lab set: phones on stands, glass cards)
                its = []
                for p in parts[1:4]:
                    label, _, rest = p.partition("=")
                    mm = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*(.*)$", rest)
                    if mm:
                        its.append({"label": label.strip(), "value": float(mm.group(1)), "unit": mm.group(2).strip()})
                if len(its) >= 2:
                    cur["items"].append({"kind": "bench", "heading": parts[0], "items": its})
            elif kind == "thermal" and len(parts) >= 3:   # [thermal: TITLE | Name=41.2 | Name=46.8]  (the hottest one is highlighted)
                ps = []
                for p in parts[1:]:
                    label, _, val = p.partition("=")
                    try:
                        ps.append({"label": label.strip(), "temp": float(val)})
                    except ValueError:
                        continue
                if len(ps) >= 2:
                    max(ps, key=lambda x: x["temp"])["highlight"] = True
                    cur["items"].append({"kind": "thermal", "title": parts[0], "phones": ps})
            elif kind == "cost" and len(parts) >= 3:      # [cost: TITLE | Display=90 | Camera=120 | Processor=160]  (total is summed)
                rs = []
                for p in parts[1:]:
                    label, _, val = p.partition("=")
                    try:
                        rs.append({"label": label.strip(), "value": float(val.replace(",", ""))})
                    except ValueError:
                        continue
                if len(rs) >= 2:
                    cur["items"].append({"kind": "cost", "title": parts[0], "rows": rs, "total": "$" + f"{sum(r['value'] for r in rs):,.0f}"})
            elif kind == "stat" and len(parts) >= 2:
                cur["items"].append({"kind": "stat", "value": parts[0], "label": parts[1]})
        else:
            cur = cur or chapters.append({"title": "", "items": []}) or chapters[-1]
            for s in re.split(r"(?<=[.!?])\s+", line):
                if s.strip():
                    cur["items"].append({"kind": "line", "text": _clean(s)})
    return {"title": title, "chapters": chapters}


BEAT_S = 3.0


def _beats(a: float, b: float, beat: float = BEAT_S):
    """One spoken stretch as cuts of about 3 s (the reference reviews cut every 2-3 s); never a piece under 1.4 s."""
    n = max(1, int(round((b - a) / beat)))
    n = min(n, max(1, int((b - a) // 1.4)))
    step = (b - a) / n
    return [(a + step * j, a + step * (j + 1)) for j in range(n)]


def _filler_shot(phone: str, cols: Sequence[str], k: int, moves: Sequence[str]) -> Dict[str, Any]:
    """The picture under a narrated line: a macro phone move, every third beat a lineup in a rotating room, so a long line never repeats one frame."""
    if k % 3 == 2:
        return {"kind": "product", "object": "lineup", "phone": phone, "colors": list(cols), "room": ROOMS[k % len(ROOMS)], "pose": POSES[(k + 1) % 4], "seed": 70 + k}
    return {"kind": "product", "object": "phone", "phone": phone, "move": moves[k % len(moves)], "backdrop": "charcoal", "seed": 9 + k}


def footage_shot(it: Dict[str, Any], media_dir: Optional[Path], k: int) -> Optional[Dict[str, Any]]:
    """A video shot for a resolved footage item (its clip copied into the film's media folder), or None when it has no clip."""
    path = it.get("path")
    if not path or not Path(path).is_file() or not media_dir:
        return None
    Path(media_dir).mkdir(parents=True, exist_ok=True)
    name = f"footage_{k:03d}{Path(path).suffix or '.mp4'}"
    shutil.copyfile(path, Path(media_dir) / name)
    return {"kind": "video", "file": name, "loop": True}


def _alt_shot(prev: Dict[str, Any], phone: str, cols: Sequence[str], k: int, moves: Sequence[str]) -> Dict[str, Any]:
    """The second angle after a 3D shot: never the same kind of picture twice running (a lineup after a lineup reads as a restart)."""
    if prev.get("object") == "lineup":
        return {"kind": "product", "object": "phone", "phone": phone, "move": moves[k % len(moves)], "backdrop": "charcoal", "seed": 90 + k}
    room = next(r for r in ROOMS[k % len(ROOMS):] + ROOMS if r != prev.get("room"))
    return {"kind": "product", "object": "lineup", "phone": phone, "colors": list(cols), "room": room, "pose": POSES[(k + 2) % 4], "seed": 80 + k}


def line_seconds(text: str) -> float:
    return len(text.split()) / WORDS_PER_S + PAUSE_S


def _type_for(text: str, used: Sequence[str]) -> Optional[str]:
    t = text.lower()
    if any(w in t for w in THREE_D_WORDS):
        return None
    hits = [k for k, d in REVIEW_TYPES.items() if any(w in t for w in d["words"])] or list(REVIEW_TYPES)
    last = used[-1] if used else None
    hits = [h for h in hits if h != last] or hits
    return min(hits, key=lambda h: (max((i for i, u in enumerate(used) if u == h), default=-1), list(REVIEW_TYPES).index(h)))


def plan_review_scenes(parsed: Dict[str, Any], phone: str, colours: Sequence[str], *, max_ai_share: float = 0.55) -> Dict[str, Any]:
    cols = list(colours) or ["Black", "Sky Blue", "Pink", "White"]
    one = cols[1] if len(cols) > 1 else cols[0]
    scenes, used, n_line = [], [], 0
    for ch_i, ch in enumerate(parsed["chapters"]):
        for it in ch["items"]:
            if it["kind"] != "line":
                continue
            n_line += 1
            stype = _type_for(it["text"], used)
            ai_so_far = sum(1 for s in scenes if s["source"] == "ai_still")
            if stype is not None and ai_so_far + 1 > max_ai_share * n_line + 1:
                stype = None
            sc = {"n": n_line, "feature": ch["title"].lower() or "other", "caption": it["text"][:60], "chapter": ch_i, "text": it["text"]}
            if stype is None:
                scenes.append({**sc, "source": "3d", "type": None})
                continue
            d = REVIEW_TYPES[stype]
            used.append(stype)
            scenes.append({**sc, "source": "ai_still", "type": stype, "refs": list(d["refs"]), "key": f"review-{n_line:03d}-{stype}",
                           "prompt": d["prompt"].format(one_colour=one.lower(), colours=", ".join(c.lower() for c in cols), design=DESIGN, nobrand=NO_BRAND)})
    return {"phone": phone, "colours": cols, "scenes": scenes, "estimate": estimate(scenes)}


def _chunks(text: str, start: float, end: float) -> List[Dict[str, Any]]:
    words = text.split()
    if not words:
        return []
    n = max(1, round(len(words) / CHUNK_WORDS))
    size = -(-len(words) // n)
    parts = [words[i:i + size] for i in range(0, len(words), size)]
    span = (end - start) / len(words)
    out, k = [], 0
    for p in parts:
        out.append({"start": round(start + k * span, 3), "end": round(start + (k + len(p)) * span, 3), "text": " ".join(p)})
        k += len(p)
    return out


def plan_review(parsed: Dict[str, Any], pack: Dict[str, Any], results: Optional[Dict[Any, Any]] = None, *, media_dir: Optional[Path] = None,
                width: int = 1920, height: int = 1080, fps: int = 30, product: Optional[Dict[str, Any]] = None, style: str = "cinematic") -> Dict[str, Any]:
    prod = product or {}
    phone, cols = pack["phone"], list(pack.get("colours") or [])
    results = results or {}
    by_n = {s["n"]: s for s in pack["scenes"]}
    shots: List[Dict[str, Any]] = []
    layers: List[Dict[str, Any]] = []
    chunks: List[Dict[str, Any]] = []
    notes: List[str] = []
    t, n_line, k3 = 0.0, 0, 0
    moves = ["island", "monolith", "edge", "screen", "port", "monolith", "buttons", "screen"]

    def add(shot: Dict[str, Any], length: float) -> Dict[str, Any]:
        nonlocal t
        s = {"id": f"s{len(shots) + 1:02d}", "start": round(t, 3), "end": round(t + length, 3), "exit": "cut", **shot}
        shots.append(s)
        t += length
        return s

    for ci, ch in enumerate(parsed["chapters"]):
        if ch["title"]:
            s = add({"kind": "plate", "tint": "cool"}, CHAPTER_S)
            layers.append({"type": "tm_title", "line1": f"CHAPTER {ci + 1}", "line2": ch["title"], "accent": "cyan", "start": s["start"] + 0.2, "end": s["end"] - 0.1})
        for it in ch["items"]:
            if it["kind"] != "line":
                fs = footage_shot(it, media_dir, k3) if it["kind"] == "footage" else None
                if it["kind"] == "footage":
                    if not fs:
                        notes.append(f"no footage for '{it.get('query', '')}': a 3D shot was used")
                    s = add(fs or _filler_shot(phone, cols, k3, moves), 4.0)
                    k3 += 1
                    continue
                shot, make, secs = directive_visual(it, phone, cols, k3, prod, style)
                s = add(shot, secs)
                layers.extend(make(s["start"], s["end"]))
                k3 += 1
                continue
            n_line += 1
            sc = by_n.get(n_line, {"source": "3d"})
            length = min(MAX_SHOT_S, max(MIN_SHOT_S, line_seconds(it["text"])))
            if style == "infographic":
                shot, make = line_visual(phone, cols, n_line)
                s = add(shot, length)
                layers.extend(make(s["start"], s["end"]))
                chunks += _chunks(it["text"], s["start"] + 0.1, s["end"] - 0.1)
                continue
            res = results.get(sc.get("n")) or {}
            pic = res.get("path") if res.get("status") == "done" else None
            clip = (results.get("clips") or {}).get(sc.get("n")) if isinstance(results.get("clips"), dict) else None
            if sc["source"] == "ai_still" and clip and Path(clip).is_file():     # a hero clip made in Flow plays instead of the still
                name = f"review_{n_line:03d}_clip{Path(clip).suffix or '.mp4'}"
                if media_dir:
                    Path(media_dir).mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(clip, Path(media_dir) / name)
                s = add({"kind": "video", "file": name, "loop": True}, length)
            elif sc["source"] == "ai_still" and pic and Path(pic).is_file():
                name = f"review_{n_line:03d}{Path(pic).suffix or '.png'}"
                if media_dir:
                    Path(media_dir).mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(pic, Path(media_dir) / name)
                drift = {"from": 1.0, "to": 1.07, "fx": 0.5, "fy": 0.5} if n_line % 2 else {"from": 1.07, "to": 1.0, "fx": 0.5, "fy": 0.5}
                s = add({"kind": "image", "file": name, "fit": "cover", "drift": drift}, length)
            else:
                if sc["source"] == "ai_still":
                    notes.append(f"line {n_line} had no AI picture: a 3D shot was used")
                s = add({"kind": "product", "object": "phone", "phone": phone, "move": moves[k3 % len(moves)], "backdrop": "charcoal", "seed": 9 + k3}, length)
                k3 += 1
            chunks += _chunks(it["text"], s["start"] + 0.1, s["end"] - 0.1)
    layers.append({"type": "pt_subtitle", "chunks": chunks, "box": True})
    card = [x for x in (prod.get("disclaimer"),) if x]
    if card:
        shots.append({"id": f"s{len(shots) + 1:02d}", "start": round(t, 3), "end": round(t + 4.0, 3), "kind": "black", "exit": "cut"})
        layers.append({"type": "pt_card", "lines": card, "start": round(t + 0.2, 3), "end": round(t + 4.0, 3)})
        t += 4.0
    spec = {"width": int(width), "height": int(height), "fps": int(fps), "duration": round(t, 3), "look": dict(FLAT_LOOK if style == "infographic" else LOOK), "shots": shots, "layers": layers,
            "whatif": {"title": parsed.get("title") or "Review", "notes": notes}, "product_trailer": {"pace": "review", "product": prod, "style": style}}
    if media_dir:
        spec["media_dir"] = str(media_dir)
    return spec


def plan_review_timed(parsed: Dict[str, Any], pack: Dict[str, Any], results: Optional[Dict[Any, Any]], voice: Dict[str, Any], words: Sequence[Any] = (), *,
                      media_dir: Optional[Path] = None, width: int = 1920, height: int = 1080, fps: int = 30, product: Optional[Dict[str, Any]] = None,
                      style: str = "cinematic") -> Dict[str, Any]:
    """The review timed to a voice-over: every spoken line owns its stretch of the film (shot cuts at the lines' starts), a chart, stat, X-ray or fold
    written before a line is shown while that line is spoken, a chapter card opens its chapter, and subtitles come from the narrator's word times.
    `voice` is voiceover.align_lines(): {"spans", "ranges", "ok", "duration"}."""
    from . import voiceover

    prod = product or {}
    phone, cols = pack["phone"], list(pack.get("colours") or [])
    results = results or {}
    by_n = {s["n"]: s for s in pack["scenes"]}
    spans, ranges, ok, D = voice["spans"], voice["ranges"], voice.get("ok", False), float(voice["duration"])
    shots: List[Dict[str, Any]] = []
    layers: List[Dict[str, Any]] = []
    chunks: List[Dict[str, Any]] = []
    notes: List[str] = []
    k3 = 0
    last_dir: Dict[str, Any] = {}
    moves = ["island", "monolith", "edge", "screen", "port", "monolith", "buttons", "screen"]

    def add(a: float, b: float, shot: Dict[str, Any]) -> Dict[str, Any]:
        s = {"id": f"s{len(shots) + 1:02d}", "start": round(a, 3), "end": round(b, 3), "exit": "cut", **shot}
        shots.append(s)
        return s

    def hold_copy(n0: float, n1: float, held: List[Dict[str, Any]]) -> None:
        """A settled copy of a flat scene's layers over n0..n1 as a new shot (no new entrance), so a scene that must stay on screen never freezes in one long shot."""
        ns = add(n0, n1, {"kind": "black"})
        first = len(layers)
        for L in held:
            c = dict(L)
            c.update({"start": round(n0, 3), "end": round(n1 if L["type"] == "pt_paper" else n1 - 0.03, 3)})
            if L["type"] == "pt_flatphones":
                c.update({"hold": True, "t0": L.get("t0", L["start"])})
            layers.append(c)
        last_dir.update({"shot": ns, "first": first, "last": len(layers), "t0": last_dir.get("t0", n0)})

    def directive(it: Dict[str, Any], a: float, b: float) -> None:
        nonlocal k3
        if it["kind"] == "footage":
            fs = footage_shot(it, media_dir, k3)
            last_dir.clear()
            if fs:
                add(a, b, fs)
            else:
                notes.append(f"no footage for '{it.get('query', '')}': a 3D shot was used")
                add(a, b, _filler_shot(phone, cols, k3, moves))
            k3 += 1
            return
        shot, make, _secs = directive_visual(it, phone, cols, k3, prod, style)
        split = it["kind"] in ("lineup", "macro", "intro", "bigtype", "stat") and shot.get("kind") == "product" and (b - a) > 3.8
        mid = a + (b - a) * 0.55 if split else b
        s = add(a, mid, shot)
        first = len(layers)
        layers.extend(make(s["start"], mid))
        last_dir.clear()
        if not split:
            last_dir.update({"shot": s, "first": first, "last": len(layers), "t0": a})
            held = layers[first:]
            if style == "follow" and (mid - a) > MAX_HOLD_S + 1.0 and all(L["type"] in ("pt_paper", "pt_flatphones") for L in held):
                cut = a + HOLD_STEP_S                    # a long line: the scene is cut into settled pieces of about 4.5 s, each a slow push
                s["end"] = round(cut, 3)
                for L in held:
                    L["end"] = round(cut if L["type"] == "pt_paper" else cut - 0.03, 3)
                held = list(held)
                while mid - cut > 0.4:
                    nxt = min(mid, cut + HOLD_STEP_S) if mid - cut - HOLD_STEP_S > 1.5 else mid
                    hold_copy(cut, nxt, held)
                    cut = nxt
        k3 += 1
        if split:                                  # the 3D beat is cut in two: a second angle follows the first (every 2-3 s something new)
            add(mid, b, _alt_shot(shot, phone, cols, k3, moves))
            k3 += 1

    flat = []                      # (chapter index, first line of chapter?, pending directives, line item)
    pend: List[Dict[str, Any]] = []
    for ci, ch in enumerate(parsed["chapters"]):
        first = True
        for it in ch["items"]:
            if it["kind"] == "line":
                flat.append({"ch": ci, "title": ch["title"] if first else "", "pending": pend, "line": it})
                pend, first = [], False
            else:
                pend.append(it)
    if pend and flat:
        flat[-1]["pending"] = flat[-1]["pending"] + pend      # directives after the last line share its stretch
    for i, f in enumerate(flat):
        a = 0.0 if i == 0 else spans[i][0]
        b = D if i + 1 >= len(flat) else spans[i + 1][0]
        b = max(b, a + 1.0)
        span = b - a
        units = list(f["pending"])
        card = min(CHAPTER_S, 0.4 * span) if f["title"] else 0.0
        cur = a
        if card:
            s = add(cur, cur + card, {"kind": "plate", "tint": "cool"})
            layers.append({"type": "tm_title", "line1": f"CHAPTER {f['ch'] + 1}", "line2": f["title"], "accent": "cyan", "start": s["start"] + 0.1, "end": s["end"] - 0.05})
            cur += card
        rest = b - cur
        share = rest / (len(units) + 1)
        if units and (share < MIN_CHART_S or style == "follow"):          # too short to read a chart and then a filler shot: the graphics own the whole line
            share = rest / len(units)
        for u in units:
            directive(u, cur, cur + share)
            cur += share
        if units and b - cur < 0.3:
            continue_line = True
        else:
            continue_line = False
        if style == "follow" and not units and last_dir and shots and shots[-1] is last_dir["shot"] and b - last_dir.get("t0", 0.0) <= MAX_SCENE_S:
            prev = shots[-1]                             # a line with no picture of its own keeps the scene before it on screen (as the references do)
            held = [L for L in layers[last_dir["first"]:last_dir["last"]]]
            if b - prev["start"] > MAX_HOLD_S and all(L["type"] in ("pt_paper", "pt_flatphones") for L in held):
                n0 = prev["end"]                         # a long hold continues as a settled copy of the same scene (a cut between identical frames is invisible)
                hold_copy(n0, b, held)
            else:
                grow = b - prev["end"]
                prev["end"] = round(b, 3)
                for L in held:
                    if "end" in L:
                        L["end"] = round(L["end"] + grow, 3)
            chunks += voiceover.chunks(f["line"]["text"], spans[i], words, ranges[i], ok)
            continue
        if continue_line:
            chunks += voiceover.chunks(f["line"]["text"], spans[i], words, ranges[i], ok)
            continue
        sc = by_n.get(i + 1, {"source": "3d"})
        if style == "infographic":
            for a2, b2 in _beats(cur, b, 4.0):        # a long line changes its flat-phone arrangement every ~4 s
                shot, make = line_visual(phone, cols, k3 + 1)
                s = add(a2, b2, shot)
                layers.extend(make(s["start"], s["end"]))
                k3 += 1
            chunks += voiceover.chunks(f["line"]["text"], spans[i], words, ranges[i], ok)
            continue
        res = results.get(sc.get("n")) or {}
        pic = res.get("path") if res.get("status") == "done" else None
        clip = (results.get("clips") or {}).get(sc.get("n")) if isinstance(results.get("clips"), dict) else None
        if sc["source"] == "ai_still" and clip and Path(clip).is_file():
            name = f"review_{i + 1:03d}_clip{Path(clip).suffix or '.mp4'}"
            if media_dir:
                Path(media_dir).mkdir(parents=True, exist_ok=True)
                shutil.copyfile(clip, Path(media_dir) / name)
            add(cur, b, {"kind": "video", "file": name, "loop": True})
        elif sc["source"] == "ai_still" and pic and Path(pic).is_file():
            name = f"review_{i + 1:03d}{Path(pic).suffix or '.png'}"
            if media_dir:
                Path(media_dir).mkdir(parents=True, exist_ok=True)
                shutil.copyfile(pic, Path(media_dir) / name)
            drift = {"from": 1.0, "to": 1.07, "fx": 0.5, "fy": 0.5} if i % 2 == 0 else {"from": 1.07, "to": 1.0, "fx": 0.5, "fy": 0.5}
            add(cur, b, {"kind": "image", "file": name, "fit": "cover", "drift": drift})
        else:
            if sc["source"] == "ai_still":
                notes.append(f"line {i + 1} had no AI picture: a 3D shot was used")
            for a2, b2 in _beats(cur, b):
                fs = _filler_shot(phone, cols, k3, moves)
                if shots and shots[-1].get("object") == "lineup" and fs.get("object") == "lineup":
                    fs = _alt_shot(shots[-1], phone, cols, k3, moves)
                add(a2, b2, fs)
                k3 += 1
        chunks += voiceover.chunks(f["line"]["text"], spans[i], words, ranges[i], ok)
    layers.append({"type": "pt_subtitle", "chunks": chunks, "box": True})
    t = D
    card_lines = [x for x in (prod.get("disclaimer"),) if x]
    if card_lines:
        shots.append({"id": f"s{len(shots) + 1:02d}", "start": round(t, 3), "end": round(t + 4.0, 3), "kind": "black", "exit": "cut"})
        layers.append({"type": "pt_card", "lines": card_lines, "start": round(t + 0.2, 3), "end": round(t + 4.0, 3)})
        t += 4.0
    if not ok:
        notes.append("the voice-over did not follow the script word for word: lines were spread evenly over its length")
    spec = {"width": int(width), "height": int(height), "fps": int(fps), "duration": round(t, 3), "look": dict(FLAT_LOOK if style == "infographic" else LOOK), "shots": shots, "layers": layers,
            "whatif": {"title": parsed.get("title") or "Review", "notes": notes},
            "product_trailer": {"pace": "review", "product": prod, "voiceover_timed": True, "voice_matched": bool(ok)}}
    if media_dir:
        spec["media_dir"] = str(media_dir)
    return spec
