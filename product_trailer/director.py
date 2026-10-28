"""Auto scene-writer for Review films: reads each narrated sentence and writes the scene that shows what it says, the way the reference explainers do
(checked on four of them: How's This Possible, This Was NEVER Expected, S26 NEW CHANGES, iPhone 17 THE TRUTH). One sentence, one claim, one picture:

    a certification / database / listing  -> an evidence document with the matching row highlighted
    "according to a tipster / leaker X"    -> a quote card naming the source
    two numbers with the same unit         -> two phones, each with its figure, and a +delta badge
    one number with a unit (60W, 5700 mAh) -> a phone with that figure beside it (battery cutaway for mAh / charging)
    a list of colours                      -> phones in those colours, labelled
    a list of models (S27, S27 Plus, ...)  -> phones in a row, labelled
    "three / four cameras"                 -> a phone with that many lenses
    inside / chip / hinge / camera / screen -> the matching 3D shot
    anything else                          -> nothing: the scene before it stays on screen (the references hold a scene across sentences)

    auto_direct(parsed, phone) -> parsed (the same chapters with directive items inserted)

Footage-style references (hands, events, people) are not drawn here: such a sentence keeps the previous scene, and `footage_hint()` returns the search
words a footage library or Flow picture should be asked for.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional

NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(%|W\b|watts?|mAh|milliamp\w*(?:\s+hours?)?|MP|megapixels?|Hz|GB|TB|nits?|mm|fps|ms\b|milliseconds?|hours?|hrs?\b|mbps|points|pts\b|x\b)", re.I)
UNIT = {"watt": "W", "watts": "W", "w": "W", "nit": " nits", "nits": " nits", "megapixel": "MP", "megapixels": "MP", "mp": "MP"}
COLOURS = {"black": "#2b2b2e", "blue": "#3f6fb5", "sky blue": "#8fc3ea", "light pink": "#e9b4c4", "pink": "#e49ab0", "white": "#ecebea", "silver": "#c8ccd2", "grey": "#8a8f98",
           "gray": "#8a8f98", "green": "#4f8a63", "purple": "#6b5aa8", "gold": "#d3b26b", "red": "#b3363f", "orange": "#e08a3a", "navy": "#26325c", "titanium": "#9a9a96"}
NUMBER_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "2": 2, "3": 3, "4": 4, "5": 5}
PURPLE, DARK = "#5b5a86", "#2b2b2e"


def _unit(u: str) -> str:
    u = u.lower().strip()
    if u.startswith("milliamp") or u == "mah":
        return "mAh"
    if u in ("milliseconds", "millisecond", "ms"):
        return "ms"
    if u in ("hour", "hours", "hr", "hrs"):
        return "h"
    if u in ("points", "pts"):
        return "pts"
    if u == "mbps":
        return "Mbps"
    return UNIT.get(u, u if u in ("%", "W") else u.upper() if u in ("hz", "gb", "tb", "mm", "fps") else u)


def _numbers(text: str) -> List[Dict[str, Any]]:
    out = []
    for m in NUM.finditer(text):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        out.append({"v": v, "unit": _unit(m.group(2)), "raw": m.group(1)})
    return out


def _fmt(v: float, unit: str) -> str:
    return f"{v:,.0f}{unit}" if abs(v - round(v)) < 1e-9 else f"{v:,.1f}{unit}"


def _has(t: str, *words: str) -> bool:
    return any(re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", t) for w in words)


def _scene(**layer: Any) -> Dict[str, Any]:
    return {"kind": "scene", "layer": layer}


def footage_hint(text: str) -> Optional[str]:
    """Search words for a sentence about the real world (an event, a person, a hands-on moment), or None."""
    t = text.lower()
    if _has(t, "launch", "unveil", "announce", "event", "stage", "presentation"):
        return "smartphone launch event stage presentation"
    if _has(t, "hold", "hand", "feel", "grip", "use", "daily"):
        return "hand holding smartphone close up"
    if _has(t, "store", "buy", "shop", "price"):
        return "smartphone store display"
    return None


def scene_for(text: str, phone: str = "Galaxy S27 Ultra") -> Optional[Dict[str, Any]]:
    t = text.lower()
    nums = _numbers(text)
    if not nums and _has(t, "geekbench", "score", "scores", "benchmark"):                   # "scores 4,719 against 3,832": bare figures are points
        bare = [float(x.replace(",", "")) for x in re.findall(r"\b\d[\d,]{2,}(?:\.\d+)?\b", text)]
        nums = [{"v": v, "unit": "pts", "raw": f"{v:,.0f}"} for v in bare[:3]]
    name = re.sub(r"\bIphone\b", "iPhone", phone.title()) if phone else "Galaxy S27 Ultra"
    # 1. certification / database evidence
    if _has(t, "certification", "certified", "certifies", "bis", "fcc", "3c", "regulatory", "database", "listing", "listed", "geekbench") and len(nums) < 2:
        chip = next((c for c in ("BIS", "FCC", "3C", "TENAA", "Geekbench") if re.search(r"(?<![a-z])" + c.lower() + r"(?![a-z])", t)), "CERTIFICATION")
        return _scene(type="pt_doc", title="Regulatory listing" if chip != "Geekbench" else "Benchmark listing", chip=(chip.upper() + " CERTIFICATION") if chip not in ("Geekbench", "CERTIFICATION") else chip.upper(),
                      rows=7, highlight=3, stamp="5G" if _has(t, "5g") else "")
    # 2. a named source
    if _has(t, "tipster", "leaker", "according to", "rumor", "rumour", "sources say"):
        who = re.search(r"(?:tipster|leaker|source)\s+([A-Z][\w]*(?:\s+[A-Z][\w]*)?)", text)
        hl = nums and re.search(re.escape(nums[0]["raw"]) + r"[^,.]*", text)
        return {"kind": "tweet", "author": who.group(1) if who else "As reported", "handle": "", "text": text, "highlight": hl.group(0).strip() if hl else ""}
    # 3. colours
    cols = [c for c in sorted(COLOURS, key=len, reverse=True) if re.search(r"(?<![a-z])" + c + r"(?![a-z])", t)]
    seen: List[str] = []
    for c in cols:
        if not any(c in s or s in c for s in seen):
            seen.append(c)
    if len(seen) >= 3 and _has(t, "colour", "colours", "color", "colors", "shades", "options"):
        order = sorted(seen, key=lambda c: t.index(c))
        return _scene(phones=[{"label": c.title(), "color": COLOURS[c], "cams": 3} for c in order[:4]], title="Colour options")
    # 4. model lineup
    models = re.findall(r"(?:Galaxy )?S\d{2}(?: (?:Plus|Pro|Edge|Ultra|FE))?|iPhone \d+(?: (?:Pro Max|Pro|Plus|Air))?", text)
    models = [m if m.startswith(("Galaxy", "iPhone")) else "Galaxy " + m for m in models]
    uniq = list(dict.fromkeys(models))
    if len(uniq) >= 3 or (len(uniq) >= 2 and _has(t, "lineup", "models", "series")):
        pal = [PURPLE, DARK, "#7a2f45", "#cfc9de"]
        return _scene(phones=[{"label": m, "color": pal[i % 4], "cams": 2 + i % 3} for i, m in enumerate(uniq[:4])], title="The lineup")
    if len(uniq) == 2 and not _numbers(text) and _has(t, "than", "compared", "versus", "vs", "over", "unlike", "while", "against"):
        return _scene(phones=[{"label": uniq[0], "color": PURPLE, "cams": 4}, {"label": uniq[1], "color": DARK, "cams": 3}], title="Side by side")
    # 5. camera count
    cm = re.search(r"(two|three|four|five|[2-5])\s+(?:rear\s+)?cameras?", t)
    if cm:
        n = NUMBER_WORDS[cm.group(1)]
        return _scene(phones=[{"label": name, "color": DARK, "cams": min(4, n), "text": f"{n} cameras"}], title="Camera module")
    # 6. numbers
    rng = re.search(r"(?:from\s+)?(\d{1,3})\s*%?\s+to\s+(\d{1,3})\s*%", t)
    if rng and int(rng.group(1)) < int(rng.group(2)) <= 100:                       # "charging from 0 to 50%": a charge range on one phone
        a, b = int(rng.group(1)), int(rng.group(2))
        return _scene(phones=[{"label": name, "color": DARK, "cams": 3, "cable": True, "fill_from": a / 100, "fill": b / 100, "side": {"text": f"{a}-{b}%", "size": 90}}], title="Charge range")
    battery = _has(t, "battery", "mah", "milliampere", "charging", "charge", "watt")
    measured = _has(t, "benchmark", "score", "scores", "geekbench", "latency", "speed", "faster", "slower", "battery life", "frame rate", "fps", "test", "tested", "measured", "lasts", "mbps")
    if len(nums) >= 2 and nums[0]["unit"] == nums[1]["unit"] and nums[0]["v"] != nums[1]["v"] and nums[0]["unit"] not in ("%",) and (measured or nums[0]["unit"] in ("ms", "h", "pts", "Mbps", "fps")):
        a, b = nums[0], nums[1]
        other = next((m for m in uniq if m.lower() != name.lower()), "Previous")
        lab = uniq[:2] if len(uniq) >= 2 else ([name, other] if _has(t, "against", "vs", "versus", "compared", "than") else [other, name])
        head = next((w.upper() for w in ("latency", "geekbench", "battery life", "frame rate", "speed", "score", "benchmark") if w in t), "MEASURED")
        return {"kind": "bench", "heading": head, "items": [{"label": lab[0], "value": a["v"], "unit": a["unit"]}, {"label": lab[1], "value": b["v"], "unit": b["unit"]}]}
    if len(nums) >= 2 and nums[0]["unit"] == nums[1]["unit"] and nums[0]["v"] != nums[1]["v"]:
        a, b = nums[0], nums[1]
        lo, hi = (a, b) if a["v"] < b["v"] else (b, a)
        phones = [{"label": "Before", "color": PURPLE, "cams": 4, "text": _fmt(lo["v"], lo["unit"]), **({"cutaway": True, "cell": 0.5, "cell_from": 0.5} if battery and lo["unit"] == "mAh" else {})},
                  {"label": "Now", "color": DARK, "cams": 3, "text": _fmt(hi["v"], hi["unit"]), "badge": "+" + _fmt(hi["v"] - lo["v"], hi["unit"]),
                   **({"cutaway": True, "cell": 0.8, "cell_from": 0.8} if battery and hi["unit"] == "mAh" else {})}]
        for p in phones:
            if p.get("cutaway"):
                p.pop("text", None)
                p["top"] = p["label"] + ""
        return _scene(phones=phones, title="Before and now")
    if len(nums) == 1 and _has(t, "bigger", "larger", "more", "faster", "higher", "extra", "upgrade", "boost", "increase"):
        n = nums[0]                                                                # "a 700mAh bigger battery": the old phone and the new one with a +delta badge
        cut = battery and n["unit"] == "mAh"
        return _scene(phones=[{"label": "Before", "color": PURPLE, "cams": 4, **({"cutaway": True, "cell": 0.55, "cell_from": 0.55} if cut else {})},
                              {"label": name, "color": DARK, "cams": 3, "badge": "+" + _fmt(n["v"], n["unit"]), **({"cutaway": True, "cell": 0.9, "cell_from": 0.9} if cut else {})}], title="Before and now")
    if len(nums) == 1:
        n = nums[0]
        fig = _fmt(n["v"], n["unit"])
        if battery and n["unit"] == "mAh":
            return _scene(phones=[{"label": name, "color": DARK, "cams": 3, "cutaway": True, "cell_from": 0.2, "cell": 0.9, "side": {"text": fig, "size": 84}}], title="Battery")
        if battery and n["unit"] == "W" and _has(t, "same", "unchanged", "remain", "remains", "stays", "still", "stay"):
            return _scene(phones=[{"label": "Before", "color": PURPLE, "cams": 4, "text": fig, "cable": True}, {"label": name, "color": DARK, "cams": 3, "text": fig, "cable": True}], title="Same charging speed")
        if battery and n["unit"] in ("W", "%"):
            return _scene(phones=[{"label": name, "color": DARK, "cams": 3, "cable": True, "side": {"text": fig, "size": 96}}], title="Charging")
        return _scene(phones=[{"label": name, "color": DARK, "cams": 3, "side": {"text": fig, "size": 96}}])
    # 7. 3D shots
    if _has(t, "inside", "teardown", "internal", "silicon-carbon", "silicon carbon", "cell"):
        return {"kind": "xray", "text": "Inside the phone"}
    if _has(t, "hinge", "fold", "folds", "crease"):
        return {"kind": "fold", "text": "The hinge"}
    if _has(t, "chip", "processor", "exynos", "snapdragon", "benchmark"):
        return {"kind": "chip", "label": "CHIP", "text": "Performance"}
    if _has(t, "camera", "cameras", "lens", "zoom", "sensor"):
        return {"kind": "macro", "text": "Camera", "move": "island"}
    if _has(t, "display", "screen", "bright", "refresh", "brightness"):
        return {"kind": "macro", "text": "Display", "move": "screen"}
    if _has(t, "frame", "slim", "titanium", "button", "port", "usb"):
        return {"kind": "macro", "text": "Design", "move": "edge"}
    return None


def auto_direct(parsed: Dict[str, Any], phone: str = "") -> Dict[str, Any]:
    """A copy of `parsed` where each line without a directive of the author's gets the scene its words call for (see the module text). A line that
    calls for nothing keeps the previous scene; two identical scenes in a row are not repeated."""
    out = copy.deepcopy(parsed)
    last_key = None
    for ch in out["chapters"]:
        items: List[Dict[str, Any]] = []
        placed = False                              # a directive written by the author sits right before the line it belongs to
        for it in ch["items"]:
            if it["kind"] != "line":
                items.append(it)
                placed = True
                continue
            pick = None if placed else scene_for(it["text"], phone)
            if pick:
                key = repr(pick)
                if key != last_key:
                    items.append(pick)
                    last_key = key
            items.append(it)
            placed = False
        ch["items"] = items
    return out
