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

import copy
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
SWATCH_MAX_S = 20.0        # colour cards stay up while the narration keeps talking colours (each sentence adds a card, a "?" or an older colour)
COLOUR_TALK = re.compile(r"\b(colou?rs?|shades?|finish(?:es)?|exclusive|variant|online only)\b", re.I)


def _colour_talk(text: str) -> bool:
    from .director import COLOURS
    t = text.lower()
    return bool(COLOUR_TALK.search(t)) or any(re.search(r"(?<![a-z])" + c + r"(?![a-z])", t) for c in COLOURS)


def _canvas_talk():
    from .lenses import is_camera_talk
    return {"pt_swatches": _colour_talk, "pt_lenses": is_camera_talk}


MAX_CARD_S = 6.0           # a flat card (paper, phones, document, quote) stays at most this long, then the film cuts to moving 3D: never a frozen screen
FLAT_LOOK = {"saturate": 1.0, "contrast": 1.0, "vignette": 0.0, "grain": 0.0}
LOOK = {"saturate": 0.97, "contrast": 1.05, "lift": "#05070B", "vignette": 0.25, "grain": 0.025}
NEWS_LOOK = {"saturate": 1.0, "contrast": 1.02, "vignette": 0.08, "grain": 0.0}    # real footage keeps its own colour

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


ROOMS = ["gallery", "loft", "terrace", "gallery", "loft"]          # the bright rooms (the dark studio and the orange desk read as a toy set in a review)
POSES = ["back", "fan", "mixed", "back"]
ALL_ROOMS = ("loft", "gallery", "studio", "terrace", "desk")      # every room an author may name in [lineup: ...]                             # backs first: the camera bar is what the narration talks about
MACRO_MOVES = ["island", "edge", "port", "buttons", "screen", "monolith"]
DIRECTIVE_SECONDS = {"bars": 7.0, "curve": 8.0, "compare": 7.0, "stat": 4.0, "xray": 5.0, "fold": 5.0, "lineup": 5.0, "chip": 5.0, "macro": 4.0,
                     "bigtype": 3.5, "intro": 5.0, "outro": 5.0, "flat": 5.0, "gauge": 5.5, "tweet": 6.0, "thermal": 5.5, "cost": 6.0, "scene": 4.0, "bench": 5.5, "feature": 4.5, "callout": 4.0, "sides": 4.5,
                     "ui": 6.0, "icon": 5.0, "wall": 5.0}
PAPER_SHOT = {"kind": "black"}
STYLES = ("mixed", "cinematic", "infographic", "follow", "news")


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


def paper_form(it: Dict[str, Any], phone: str, cols: Sequence[str], k: int):
    """The paper version of a scene that is otherwise 3D, for the one-look infographic film: a spoken point or a CSV row as a phone with its figure
    beside it, a lineup as coloured phones, the chip as its badge, the inside as a battery cutaway. None for a kind with no paper form."""
    kind = it["kind"]
    sec = DIRECTIVE_SECONDS.get(kind, 4.5)
    swatch = ["#2b2b2e", "#5b5a86", "#7a2f45", "#cfc9de"]
    name = phone.title() if phone else ""
    if kind in ("feature", "callout"):
        value = str(it.get("value") or it.get("feature", "")).strip()
        title = " · ".join(x for x in (it.get("kicker"), it.get("sub")) if x)
        size = 96 if len(value) <= 9 else 72 if len(value) <= 14 else 54
        ph = [{"label": name, "color": swatch[k % 2], "cams": 3, "side": {"text": value, "size": size}}]
        return PAPER_SHOT, _paper(lambda a, b: [{"type": "pt_flatphones", "title": title.upper(), "phones": ph, "start": a + 0.05, "end": b - 0.05}]), sec
    if kind == "lineup":
        ph = [{"label": c, "color": COLOUR_HEX.get(c.lower(), swatch[i % 4]), "cams": 3} for i, c in enumerate(list(cols)[:4])]
        return PAPER_SHOT, _paper(lambda a, b: [{"type": "pt_flatphones", "title": str(it.get("text") or "").upper(), "phones": ph, "start": a + 0.05, "end": b - 0.05}]), sec
    if kind == "chip":
        return PAPER_SHOT, _paper(lambda a, b: [{"type": "pt_badge", "title": str(it.get("label") or "CHIP"), "subtitle": str(it.get("text") or ""), "color": "#d4a017",
                                                 "start": a + 0.05, "end": b - 0.05}]), sec
    if kind in ("xray", "macro", "fold"):
        ph = [{"label": name, "color": swatch[0], "cams": 3, **({"cutaway": True, "cell_from": 0.3, "cell": 0.85} if kind == "xray" else {})}]
        return PAPER_SHOT, _paper(lambda a, b: [{"type": "pt_flatphones", "title": str(it.get("text") or "").upper(), "phones": ph, "start": a + 0.05, "end": b - 0.05}]), sec
    return None


def line_visual(phone: str, cols: Sequence[str], k: int):
    """A narrated line in the infographic style: a row of flat phones on the paper, drifting slightly (never a still screen)."""
    swatch = ["#5b5a86", "#2b2b2e", "#7a2f45", "#cfc9de"]
    n = 1 + k % 3
    ph = [{"cams": 3 + (i % 2), "color": swatch[(i + k) % 4], "label": phone.title() if i == 0 else ""} for i in range(n)]
    return PAPER_SHOT, _paper(lambda a, b: [{"type": "pt_flatphones", "phones": ph, "start": a, "end": b}])


def ui_visual(it: Dict[str, Any], phone: str, cols: Sequence[str], k: int, product: Optional[Dict[str, Any]] = None, flat: bool = False):
    """A software sentence's scene (product_trailer/uifilm.py): "ui" a live interface on a 3D phone (a scripted demo, or its layers exploded in 3D),
    "icon" an app icon built on construction lines, "wall" floating lock-screen phones. The title types on word by word. The set alternates light /
    dark and the shot dissolves in with a blur, so the interface beats read as their own moments inside the review. flat: paper looks keep no 3D."""
    from .uifilm import ACCENTS, _script, ui_for_feature

    kind, prod = it["kind"], product or {}
    light = k % 2 == 0
    ink = "dark" if light else "light"
    title = it.get("title") or it.get("text") or {"icon": "New Icons", "wall": "Make It Yours"}.get(kind, "")
    words = lambda a, b: [{"type": "pt_words", "text": title, "start": round(a + 0.2, 3), "end": round(min(b - 0.2, a + 4.4), 3), "y": 0.12, "ink": ink}] if title else []
    if kind == "icon" or flat:
        glyph = it.get("icon") or "star"
        shot = {"kind": "plate", "tint": "paper" if light or flat else "ink", "dissolve_in": 0.5, "dissolve_style": "fade"}
        return shot, lambda a, b: words(a, b) + [{"type": "pt_iconbuild", "icon": glyph, "label": glyph.title(), "color": ACCENTS[k % len(ACCENTS)], "start": round(a + 0.2, 3),
                                                  "end": round(b - 0.15, 3), "ink": "dark" if light or flat else "light", "build": round(min(2.8, max(1.2, (b - a) * 0.55)), 2), "y": 0.56, "size": 0.34}], DIRECTIVE_SECONDS[kind]
    colour = cols[k % len(cols)] if cols else ""
    base = {"kind": "product", "object": "phone", "phone": phone, "color": colour, "move": "demo", "backdrop": "daylight" if light else "charcoal", "glow": not light,
            "seed": 61 + k, "dissolve_in": 0.5, "dissolve_style": "blur", "exit": "cut"}
    time, date = prod.get("time", "9:41"), prod.get("date", "Tuesday, October 21")
    if kind == "wall":
        ui = {"theme": "dark", "accent": ACCENTS[0], "components": [{"type": "clock", "time": time, "date": date}], "top": 150}
        shot = {**base, "screen": {"wallpaper": "wave", "clock": False, "ui": ui}, "wall": {"cols": 4, "rows": 3, "speed": 0.34, "seed": 7 + k},
                "cam": {"z0": 6.1, "z1": 5.2, "y0": -0.2, "y1": 0.08, "ay0": 0.3, "ay1": 0.4}}
        return shot, words, DIRECTIVE_SECONDS[kind]
    f = {"feature": title, "kicker": "", "value": title, "sub": ", ".join(it.get("rows") or []), "look": " ".join(x for x in (it.get("look"), f"rows:{'|'.join(r.replace(' ', '_') for r in it['rows'])}" if it.get("rows") else "") if x)}
    accent = ACCENTS[k % len(ACCENTS)]
    ui, cat = ui_for_feature(f, accent=accent, time=time, date=date)
    style = "exploded" if "style:exploded" in (it.get("look") or "") or ("style:demo" not in (it.get("look") or "") and cat in ("lock", "widgets", "home", "notif")) else "demo"
    shot = {**base, "screen": {"wallpaper": "wave", "tint": accent, "clock": False, "ui": ui}, "ui_style": style}
    if style == "exploded":
        shot.update({"layers3d": {"explode": [1, 0], "start": 0.4, "depth": 0.4, "fan": 0.42}, "cam": {"p0": 0.16, "p1": 0.03, "y0": -0.62, "y1": 0.05, "z0": 5.3, "z1": 3.0, "ay0": 0.22, "ay1": 0.4}})
    else:
        shot["cam"] = {"p0": 0.07, "p1": 0.02, "y0": -0.34, "y1": 0.1, "z0": 5.0, "z1": 2.4, "ay0": 0.3, "ay1": 0.62}

    def make(a: float, b: float) -> List[Dict[str, Any]]:
        if style == "exploded":
            shot["layers3d"]["dur"] = round(max(1.0, (b - a) * 0.78), 2)
        elif not ui.get("script"):
            ui["script"] = _script(ui, b - a)          # spread over the shot; a timed review moves them onto the spoken row names
        return words(a, b)
    return shot, make, DIRECTIVE_SECONDS[kind]


def directive_visual(it: Dict[str, Any], phone: str, cols: Sequence[str], k: int, product: Optional[Dict[str, Any]] = None, style: str = "cinematic"):
    """The shot and layers of one non-spoken item (chart, stat, X-ray, fold, lineup, chip, macro, big word, intro, outro): (shot fields, make(a, b) -> layers, seconds)."""
    kind = it["kind"]
    if kind in ("ui", "icon", "wall"):
        return ui_visual(it, phone, cols, k, product, flat=style in ("infographic", "news"))
    if kind == "bench":
        return bench_visual(it, phone, k)
    if kind == "sides":                              # two figures either side of one phone, each on its word (REVIEW_REFERENCE_5 gap 17)
        items = [dict(x) for x in it.get("items") or []]
        sec = DIRECTIVE_SECONDS["sides"]
        if style in ("infographic", "news"):
            return PAPER_SHOT, _paper(lambda a, b: [{"type": "pt_flatphones", "phones": [{"label": phone.title(), "color": "#2b2b2e", "cams": 3}], "start": round(a + 0.05, 3), "end": round(b - 0.03, 3)},
                                                     {"type": "pt_sides", "items": [dict(x) for x in items], "ink": "dark", "start": round(a + 0.15, 3), "end": round(b - 0.05, 3)}]), sec
        shot = {"kind": "product", "object": "phone", "phone": phone, "move": "hero_back", "backdrop": REVIEW_SET, "seed": 61 + k}
        return shot, lambda a, b: [{"type": "pt_sides", "items": [dict(x) for x in items], "ink": "dark" if REVIEW_SET == "daylight" else "light",
                                    "start": round(a + 0.15, 3), "end": round(b - 0.05, 3)}], sec
    if kind in ("feature", "callout"):
        if style in ("infographic", "news"):
            return paper_form(it, phone, cols, k)
        return feature_visual(it, phone, k, product)
    if style in ("infographic", "follow", "news") or kind in ("flat", "gauge", "tweet", "thermal", "cost", "scene"):
        flat = infographic_visual(it, phone, cols, k)
        if flat:
            return flat
    if style == "infographic":                       # one look: the 3D kinds are drawn on the paper too
        flat = paper_form(it, phone, cols, k)
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
        shot = {"kind": "product", "object": "phone", "phone": phone, "move": move, "backdrop": REVIEW_SET, "seed": 41 + k}
        rg = it.get("ring")
        if rg:                                   # a ring round the named lens, tracked on the 3D phone (layers/pt_ring.mjs), drawn on its word
            return shot, lambda a, b: cap(it.get("text"), a, b) + [{"type": "pt_ring", "part": "lens", "index": int(rg.get("index", -1)), "phrase": str(rg.get("phrase") or ""),
                                                                    "x": 0.5, "y": 0.42, "r": 0.07, "start": round(a + 0.1, 3), "end": round(b - 0.05, 3)}], sec
        return shot, lambda a, b: cap(it.get("text"), a, b), sec
    if kind == "bigtype":
        shot = {"kind": "product", "object": "phone", "phone": phone, "move": "monolith", "backdrop": REVIEW_SET, "seed": 51 + k}
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


def is_feature_csv(text: str) -> bool:
    """True for a Trailer feature CSV (#product / #disclaimer lines, an order,feature,kicker,value,sub,look table) and no narration column:
    its rows are facts to show, never lines to speak."""
    import csv as _csv
    import io

    rows = [[c.strip().lower() for c in r] for r in _csv.reader(io.StringIO(text.lstrip("﻿"))) if any(c.strip() for c in r)]
    if any(c in TEXT_COLS for r in rows for c in r[:8]):
        return False
    tags = any(r and r[0].startswith(("#product", "#disclaimer", "#colors", "#colours", "#pace")) for r in rows)
    table = any("feature" in r and "value" in r for r in rows)
    return tags or table


def review_source(script: Optional[str], csv_path: Optional[str]) -> str:
    """The pasted script when there is one, else the review CSV converted to a script, else ''. A feature CSV gives no script (its rows are facts)."""
    if (script or "").strip():
        return script
    if csv_path and Path(csv_path).is_file():
        text = Path(csv_path).read_text(encoding="utf-8-sig")
        return "" if is_feature_csv(text) else csv_to_script(text)
    return ""


SPOKEN_UNITS = {"mp": ("mp", "megapixel", "megapixels"), "mah": ("mah", "milliamp", "milliamps"), "w": ("w", "watt", "watts"), "hz": ("hz", "hertz"),
                "x": ("x",), "gb": ("gb", "gigabytes"), "tb": ("tb", "terabyte"), "mm": ("mm", "millimeters", "millimetres"), "nits": ("nits", "nit")}
GENERIC_WORDS = {"the", "a", "an", "and", "but", "or", "of", "to", "new", "next", "gen", "more", "less", "than", "ever", "built", "in", "up", "with", "for", "top",
                 "phone", "ultra", "galaxy", "samsung", "iphone", "pro", "plus", "max", "big", "bigger", "fast", "steady", "longer", "range"}


def _figures(value: str) -> List[tuple]:
    """(number, unit) pairs of a CSV value: "50MP 5x" -> [("50", "mp"), ("5", "x")], "5700 mAh" -> [("5700", "mah")]."""
    return [(n.replace(",", ""), u.lower()) for n, u in re.findall(r"(\d[\d,]*(?:\.\d+)?)\s*([A-Za-z]*)", value or "")]


def _says_figure(line: str, num: str, unit: str) -> bool:
    """Does the spoken line say this figure? Whisper writes 5,700 as "5 700" and 60W as "60 watts"."""
    t = re.sub(r"(?<=\d)[ ,](?=\d{3}\b)", "", line.lower())
    forms = SPOKEN_UNITS.get(unit, (unit,)) if unit else ("",)
    for f in forms:
        if re.search(r"(?<![\d.])" + re.escape(num) + (r"\s*" + re.escape(f) if f else "") + r"(?![a-z\d])", t):
            return True
    if unit and len(num.split(".")[0]) < 3:
        return False                                 # "5x" or "50MP" only with its unit; a figure of 3+ digits ("around 5,700") is distinctive on its own
    return re.search(r"(?<![\d.])" + re.escape(num) + r"(?!\d|\.\d)", t) is not None


def _feature_words(f: Dict[str, Any]) -> List[str]:
    """The distinctive words of a feature with no figure ("Camera Island" -> camera, island; kicker "Snapdragon" when the value is "Ultra")."""
    for field in ("value", "kicker", "sub"):
        ws = [w for w in re.findall(r"[a-z0-9]+", str(f.get(field) or "").lower()) if w not in GENERIC_WORDS and len(w) >= 4]
        if ws:
            return ws
    return []


def feature_matches(f: Dict[str, Any], line: str) -> bool:
    figs = _figures(str(f.get("value") or ""))
    if figs:
        return all(_says_figure(line, n, u) for n, u in figs)
    ws = _feature_words(f)
    toks = set(re.findall(r"[a-z0-9]+", line.lower()))
    return bool(ws) and all(w in toks for w in ws)


FEATURE_TOPICS = {"battery": "battery", "charging": "battery", "camera": "camera", "display": "display", "screen": "display", "chip": "chip", "design": "design"}


def _row_topic(f: Dict[str, Any]) -> Optional[str]:
    return FEATURE_TOPICS.get(str(f.get("feature") or "").lower().split(" ")[0])


def _repeats(scene: Dict[str, Any], f: Dict[str, Any]) -> bool:
    """Does the director's scene only say again what the CSV row shows? A 3D shot (the row is itself a 3D shot with its text), or flat phones whose
    figures are all the row's own."""
    if scene.get("kind") in ("macro", "chip", "lineup", "xray"):
        return True
    phones = (scene.get("layer") or {}).get("phones") if scene.get("kind") == "scene" else None
    if not phones:
        return False
    figs = [str(p.get("text") or (p.get("side") or {}).get("text") or "") for p in phones]
    val = re.sub(r"\s+", "", str(f.get("value") or "")).lower()
    return all(x and re.sub(r"\s+", "", x).lower() in val for x in figs) and not any(p.get("badge") for p in phones)


def place_features(parsed: Dict[str, Any], features: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """A copy of `parsed` with each feature-CSV row as a "feature" scene right before the first sentence that says it (the CSV's own words and look on
    the 3D phone). Rows the narrator never says go on sentences that call for no scene of their own, in CSV order, spread over the film."""
    from . import director

    out = copy.deepcopy(parsed)
    slots = [(ch["items"], i) for ch in out["chapters"] for i, it in enumerate(ch["items"]) if it["kind"] == "line"]
    has_scene = {j for j, (items, i) in enumerate(slots) if i and items[i - 1]["kind"] != "line"}
    taken: Dict[int, Dict[str, Any]] = {}
    left: List[Dict[str, Any]] = []
    for f in features:
        if not (f.get("value") or f.get("kicker")):
            continue
        j = next((j for j, (items, i) in enumerate(slots) if j not in taken and feature_matches(f, items[i]["text"])), None)
        if j is None:                                # a sentence that says two rows ("200MP main, ... 50MP 5x telephoto") shows the next one on the sentence after it
            j = next((j + 1 for j, (items, i) in enumerate(slots) if j + 1 < len(slots) and j + 1 not in taken and feature_matches(f, items[i]["text"])), None)
        if j is None:
            left.append(f)
        else:
            taken[j] = f
    plain = [j for j, (items, i) in enumerate(slots) if j not in taken and j not in has_scene and (has_scene or not director.scene_for(items[i]["text"]))]
    for f in list(left):                             # a row nobody says goes first on a plain sentence about its own subject ("design" -> a design sentence)
        want = _row_topic(f)
        j = next((j for j in plain if j not in taken and want and director.topic_of(slots[j][0][slots[j][1]]["text"]) == want), None)
        if j is not None:
            taken[j] = f
            left.remove(f)
    plain = plain[::-1]                              # the rest close the film, the way a trailer ends on its tagline
    for n, f in enumerate(left):
        if not plain:
            break
        j = plain[min(len(plain) - 1, n * len(plain) // len(left))]
        if j in taken:
            j = next((p for p in plain if p not in taken), None)
            if j is None:
                break
        taken[j] = f
    for j in sorted(taken, reverse=True):          # from the end, so the earlier indexes stay right
        items, i = slots[j]
        f = taken[j]
        while i and items[i - 1]["kind"] != "line":       # in front of the scene the director already gave this sentence: the CSV row, then that scene
            i -= 1
            if _repeats(items[i], f):                    # ...unless that scene only repeats the row (a 3D shot of the same part, the same figure again)
                items.pop(i)
        items.insert(i, {"kind": "feature", "_own": True, **{k: str(f.get(k) or "") for k in ("feature", "kicker", "value", "sub", "look")}})
    return out


NEWS_KEEP = ("scene", "sides", "tweet", "bench", "curve", "compare", "bars", "feature", "gauge", "thermal", "cost")
NEWS_BEAT_S = 2.6


def news_beats(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """The news-compilation form of a directed script (the leak channels: real footage, cut every 2-3 s, a data card only where a figure, a document
    or a quote is the point). Data scenes stay; spoken-point callouts and 3D shots go; every sentence without a data card gets footage beats of its
    subject, one per ~2.6 s; a long sentence with a card gets footage after it."""
    from . import director

    out = copy.deepcopy(parsed)
    topic = None
    for ch in out["chapters"]:
        items: List[Dict[str, Any]] = []
        pending: List[Dict[str, Any]] = []
        for it in ch["items"]:
            if it["kind"] != "line":
                if it["kind"] in NEWS_KEEP:
                    pending.append(it)
                continue
            topic = director.topic_of(director.spoken_numbers(it["text"])) or topic
            secs = line_seconds(it["text"])
            n = max(1, int(round(secs / NEWS_BEAT_S)))
            if pending:
                n = 1 if secs > 6.0 else 0
            beats = [{"kind": "footage", "query": "", "topic": topic, "text": ""} for _ in range(n)]
            items.extend(pending + beats + [it])
            pending = []
        ch["items"] = items + pending
    return out


def feature_visual(it: Dict[str, Any], phone: str, k: int, product: Optional[Dict[str, Any]] = None):
    """A feature-CSV row in the Trailer's own look (planner.classify: its moves, wash / horizon / stars backdrop, badge or big type), the text beside the phone."""
    from . import planner

    rule = planner.classify(it)
    prod = product or {}
    if it.get("kind") == "callout":                      # a spoken point: plain big type beside the phone of its subject, never a chip badge
        rule["extra"] = None
        rule["moves"] = [m for m in rule["moves"] if planner.FACE.get(m) != "chip"] or list(planner.TEXT_MOVES)
    text_side = "right" if k % 2 == 0 else "left"
    if rule["extra"] == "bigtype":
        rule["extra"] = None                             # a review's big word goes beside the phone (behind it, over a dark back, it cannot be read)
    if rule["extra"] == "badge":
        move = "chip"
    else:
        ok = list(TEXT_SAFE_MOVES)                       # the whole phone in frame beside its text (monolith / orbit crop it), mostly its back
        move = ok[k % len(ok)]
    backdrop = REVIEW_SET if rule["backdrop"] in ("stars", "horizon", "studio") else rule["backdrop"]   # a CSV wash stays; the night-sky looks become the bright set
    shot: Dict[str, Any] = {"kind": "product", "object": "chip" if move == "chip" else "phone", "phone": phone, "move": move, "backdrop": backdrop,
                            "frame_side": "left" if text_side == "right" else "right", "seed": 61 + k}
    ink = {"ink": "dark"} if backdrop == REVIEW_SET else {}
    if move == "chip":
        shot.update({"label": " ".join(x for x in (it.get("kicker"), it.get("value")) if x).upper()[:24] or "CHIP", "glow": "#ffb340"})
    if rule["backdrop"] == "wash":
        shot["wash"] = planner.WASH.get(rule["wash"] or "red", rule["wash"] or "#ff4a1f")
        shot["wash_style"] = rule["wash_style"] or "swoosh"
    elif rule["backdrop"] == "gradient":
        shot["wash"] = planner.WASH.get(rule["wash"] or "blue", rule["wash"] or "#2f6bff")
    elif rule["backdrop"] == "image":
        shot["backdrop"] = "stars"                      # a backdrop picture is a Trailer-only option (copied next to its CSV)
    if planner.FACE.get(move) == "front":
        shot["screen"] = {"time": prod.get("time", "09:41"), "date": prod.get("date", "Tue 27 Oct"), "tint": SCREEN_TINTS[k % len(SCREEN_TINTS)]}
        if rule["extra"] == "bigtype":
            shot["screen"]["clock"] = False
    value = it.get("value") or it.get("feature", "").title()

    def make(a: float, b: float) -> List[Dict[str, Any]]:
        a, b = a + 0.05, b - 0.05
        if rule["extra"] == "badge":
            return [{"type": "pt_badge", "title": value, "subtitle": it.get("sub") or it.get("kicker", ""), "color": "#ffb340", "start": a, "end": b}]
        if rule["extra"] == "bigtype":
            return [{"type": "pt_bigtype", "text": value, "y": 0.5, "start": a, "end": b}]
        if it.get("value") and not (it.get("kicker") or it.get("sub")) and len(it["value"]) <= 24:
            return [{"type": "pt_tagline", "text": it["value"], "side": text_side, "start": a, "end": b, **ink}]
        return [{"type": "pt_feature", "kicker": it.get("kicker", ""), "value": value, "sub": it.get("sub", ""), "side": text_side, "start": a, "end": b, **ink}]

    return shot, make, DIRECTIVE_SECONDS["feature"]


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
            m = re.match(r"\[(bars|stat|curve|compare|xray|fold|lineup|chip|macro|bigtype|intro|outro|flat|gauge|tweet|thermal|cost|scene|bench|ui|icon|wall)\s*:\s*(.*)\]$", line, re.I)
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
            elif kind == "ui":         # [ui: Title | row, row, row | demo or exploded]  a live interface on the phone
                rows = [r.strip() for r in parts[1].split(",") if r.strip()] if len(parts) > 1 else []
                style = parts[2].lower() if len(parts) > 2 and parts[2].lower() in ("demo", "exploded") else ""
                cur["items"].append({"kind": "ui", "title": parts[0] if parts else "", "rows": rows, "look": f"style:{style}" if style else ""})
            elif kind == "icon":       # [icon: glyph | Title]  an app icon built on construction lines
                cur["items"].append({"kind": "icon", "icon": parts[0].lower() if parts and parts[0] else "star", "text": parts[1] if len(parts) > 1 else ""})
            elif kind == "wall":       # [wall: Title]  a wall of floating lock-screen phones
                cur["items"].append({"kind": "wall", "text": parts[0] if parts else ""})
            elif kind == "lineup":     # [lineup: caption | room | pose]
                cur["items"].append({"kind": "lineup", "text": parts[0] if parts else "", "room": (parts[1] if len(parts) > 1 and parts[1] in ALL_ROOMS else None),
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


COLOUR_HEX = {"black": "#2b2b2e", "navy": "#26325c", "sky blue": "#8fc3ea", "pink": "#e49ab0", "white": "#ecebea", "silver": "#c8ccd2", "gray": "#8a8f98", "grey": "#8a8f98"}
REVIEW_SET = "daylight"      # the review's 3D phone sits in a bright seamless studio, as the reference channels' footage is bright; dark looks are for trailers
TEXT_SAFE_MOVES = ("hero_back", "hero", "hero_back", "flip")   # mostly the back: the camera bar is the star, as in the references
SCREEN_TINTS = ("#9cc3ff", "#f2b8c6", "#b9e3cf", "#e9d3a8", "#c9b8f2")
TOPIC_SHOTS = {"battery": ("xray", "rise", "orbit"), "camera": ("island", "monolith", "flip"), "display": ("screen", "hero", "orbit"),
               "chip": ("chip_macro", "chip", "edge"), "design": ("edge", "profile", "buttons", "monolith"), "price": ("lineup", "hero", "lineup")}


def _filler_shot(phone: str, cols: Sequence[str], k: int, moves: Sequence[str], topic: Optional[str] = None) -> Dict[str, Any]:
    """The picture under a narrated line: a macro phone move, every third beat a lineup in a rotating room, so a long line never repeats one frame.
    With the line's subject (`topic`) the shot shows that subject: battery -> the x-ray cutaway, camera -> the lens bar, chip -> the chip, and so on."""
    pick = TOPIC_SHOTS.get(topic or "")
    if pick:
        m = pick[k % len(pick)]
        if m == "xray":
            return {"kind": "product", "object": "xray", "seed": 100 + k, "explode": [0, 0.6]}
        if m == "lineup":
            return {"kind": "product", "object": "lineup", "phone": phone, "colors": list(cols), "room": ROOMS[k % len(ROOMS)], "pose": POSES[(k + 1) % 4], "seed": 70 + k}
        if m in ("chip", "chip_macro"):
            return {"kind": "product", "object": "chip", "move": m, "label": "CHIP", "glow": "#3ac8ff", "seed": 110 + k}
        return {"kind": "product", "object": "phone", "phone": phone, "move": m, "backdrop": REVIEW_SET, "seed": 9 + k}
    if k % 3 == 2:
        return {"kind": "product", "object": "lineup", "phone": phone, "colors": list(cols), "room": ROOMS[k % len(ROOMS)], "pose": POSES[(k + 1) % 4], "seed": 70 + k}
    return {"kind": "product", "object": "phone", "phone": phone, "move": moves[k % len(moves)], "backdrop": REVIEW_SET, "seed": 9 + k}


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
        return {"kind": "product", "object": "phone", "phone": phone, "move": moves[k % len(moves)], "backdrop": REVIEW_SET, "seed": 90 + k}
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
                s = add({"kind": "product", "object": "phone", "phone": phone, "move": moves[k3 % len(moves)], "backdrop": REVIEW_SET, "seed": 9 + k3}, length)
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
    cur_topic: List[Optional[str]] = [None]          # the subject the narration is on: filler shots show it

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
                add(a, b, _filler_shot(phone, cols, k3, moves, cur_topic[0]))
            k3 += 1
            return
        shot, make, _secs = directive_visual(it, phone, cols, k3, prod, style)
        split = it["kind"] in ("lineup", "macro", "intro", "bigtype", "stat", "feature", "callout") and shot.get("kind") == "product" and (b - a) > 3.8
        mid = a + (b - a) * 0.55 if split else b
        s = add(a, mid, shot)
        first = len(layers)
        layers.extend(make(s["start"], mid))
        ui = (s.get("screen") or {}).get("ui")
        if ui and s.get("ui_style") == "demo" and words:   # the cursor taps a row when the narrator names it
            from .uifilm import _cue_taps
            from .voiceover import _wtimes

            cues = _cue_taps(ui, _wtimes(words), a, mid)
            if cues:
                s["screen"] = {**s["screen"], "ui": {**ui, "script": cues}}
        last_dir.clear()
        if not split:
            last_dir.update({"shot": s, "first": first, "last": len(layers), "t0": a})
            held = layers[first:]
            most = MAX_CARD_S if s.get("kind") == "black" else MAX_SCENE_S
            if style in ("follow", "news") and (mid - a) > most + 1.0:
                cut = a + most                           # a long line: the scene has its read, then moving 3D shots carry the rest of the line
                s["end"] = round(cut, 3)
                for L in held:
                    L["end"] = round(min(L["end"], cut if L["type"] == "pt_paper" else cut - 0.03), 3)
                last_dir.clear()
                for a2, b2 in _beats(cut, mid):
                    fs = _filler_shot(phone, cols, k3, moves, cur_topic[0])
                    if shots and shots[-1].get("object") == "lineup" and fs.get("object") == "lineup":
                        fs = _alt_shot(shots[-1], phone, cols, k3, moves)
                    add(a2, b2, fs)
                    k3 += 1
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
    from . import director

    for i, f in enumerate(flat):
        cur_topic[0] = director.topic_of(director.spoken_numbers(f["line"]["text"])) or cur_topic[0]
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
        if units and (share < MIN_CHART_S or style in ("follow", "news")):          # too short to read a chart and then a filler shot: the graphics own the whole line
            share = rest / len(units)
        for u in units:
            directive(u, cur, cur + share)
            cur += share
        if units and b - cur < 0.3:
            continue_line = True
        else:
            continue_line = False
        held = [L for L in layers[last_dir["first"]:last_dir["last"]]] if last_dir else []
        limit = MAX_CARD_S if last_dir and last_dir["shot"].get("kind") == "black" else MAX_SCENE_S
        swatch_hold = (not units and bool(last_dir) and bool(shots) and shots[-1] is last_dir["shot"] and b - last_dir.get("t0", 0.0) <= SWATCH_MAX_S
                       and any(fn(f["line"]["text"]) for typ, fn in _canvas_talk().items() if any(L["type"] == typ for L in held)))   # colour cards / lens callouts keep building (gaps 3-4)
        if (style in ("follow", "news") and not units and last_dir and shots and shots[-1] is last_dir["shot"] and b - last_dir.get("t0", 0.0) <= limit) or swatch_hold:
            prev = shots[-1]                             # a line with no picture of its own keeps the scene before it on screen (as the references do)
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
                fs = _filler_shot(phone, cols, k3, moves, cur_topic[0])
                if shots and shots[-1].get("object") == "lineup" and fs.get("object") == "lineup":
                    fs = _alt_shot(shots[-1], phone, cols, k3, moves)
                add(a2, b2, fs)
                k3 += 1
        chunks += voiceover.chunks(f["line"]["text"], spans[i], words, ranges[i], ok)
    from .canvas import build as build_canvases
    if words and ok:
        from .swatches import follow as swatch_follow
        swatch_follow(layers, voiceover._wtimes(words))   # colour cards: an added colour, a "?" for unknown shades, an older model's colour (gap 3)
        from .lenses import follow as lens_follow, resolve_later
        lens_follow(layers, voiceover._wtimes(words))     # lens callouts: named on their words, "??" when asked, the answer when said (gap 4)
        resolve_later(shots, layers, voiceover._wtimes(words))
    build_canvases(shots, layers)                    # flat scenes of the same phones keep building on one canvas (REVIEW_REFERENCE_4 gap 2)
    if words and ok:                                 # each label, badge, bar and card lands on the word that names it (REVIEW_REFERENCE_4 gap 1)
        from .wordcue import cue_layers
        cue_layers(layers, voiceover._wtimes(words))
    layers.append({"type": "pt_subtitle", "chunks": chunks, "box": True})
    t = D
    card_lines = [x for x in (prod.get("disclaimer"),) if x]
    if card_lines:
        shots.append({"id": f"s{len(shots) + 1:02d}", "start": round(t, 3), "end": round(t + 4.0, 3), "kind": "black", "exit": "cut"})
        layers.append({"type": "pt_card", "lines": card_lines, "start": round(t + 0.2, 3), "end": round(t + 4.0, 3)})
        t += 4.0
    if not ok:
        notes.append("the voice-over did not follow the script word for word: lines were spread evenly over its length")
    spec = {"width": int(width), "height": int(height), "fps": int(fps), "duration": round(t, 3), "look": dict(FLAT_LOOK if style == "infographic" else NEWS_LOOK if style == "news" else LOOK), "shots": shots, "layers": layers,
            "whatif": {"title": parsed.get("title") or "Review", "notes": notes},
            "product_trailer": {"pace": "review", "product": prod, "voiceover_timed": True, "voice_matched": bool(ok)}}
    if media_dir:
        spec["media_dir"] = str(media_dir)
    return spec
