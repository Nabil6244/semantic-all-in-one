"""Doc Style: any video's graphics drawn in the News Doc look (the app-wide "Doc Style" switch in Audio & Effects > Smart editing).

    render_doc_style(spec, out_path, width, height) -> PNG path, or None when the spec has no Doc Style look
                                                       (the caller then draws it the usual way)

The looks themselves are News Doc's own, copied to graphics/doc_looks.py (Weather is protected and never imported), each
drawn at its settled frame. The pipeline adds the overlay's fade/slide as for any graphic. Preview of every look:
docs/weather/newsdoc_style_sheet.png (assets/doc_style_preview.jpg in the app).

  STATISTIC / DATA     big white number + spaced label (a percent: the cyan ring); Book of Enoch's big number centred
  dataviz charts       comparison/ranking -> navy bars (3+ long labels: horizontal bars), change/timeline -> navy line
  NAME / LOWER_THIRD   orange name bar + role
  LOCATION / LABEL     black place box or orange place pin + sub
  extras (doc_plan)    checklist, rings, forecast, polaroids, panel, quote card, framed, dossier, glitch, watermark
  CALLOUT / EMPHASIS   yellow tag (short) or the typed caption (long)
  QUOTE                serif pull quote with its speaker, or the boxed quote card
  TITLE / CHAPTER      chapter words (a year: the huge year), longer titles as a headline
  anything else        the typed caption
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

SETTING_KEY = "doc_style"
LOOK = "doc"


def _num(text: str) -> Tuple[Optional[float], str]:
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", text or "")
    if not m:
        return None, ""
    try:
        return float(m.group(0).replace(",", "")), m.group(0)
    except ValueError:
        return None, ""


def _words(text: str) -> int:
    return len(str(text or "").split())


def pick_look(spec: Any) -> Optional[Tuple[str, Dict[str, Any]]]:
    """(News Doc look, its params) for a GraphicSpec; None when Doc Style has nothing for it."""
    payload = dict(getattr(spec, "payload", None) or {})
    template = str(payload.get("template") or "")
    if template.startswith("countdown") or template == "keyword_callout":
        return None   # a style's own reference look (countdown videos) stays as it is
    text = getattr(spec, "text", None)
    main = str(getattr(text, "text", "") or payload.get("text") or "").strip()
    sub = str(getattr(text, "secondary_text", "") or "").strip()
    meta = dict(getattr(text, "metadata", None) or {}) if text is not None else {}
    role = str(getattr(spec, "role", "") or "").upper()
    decision = str(getattr(spec, "decision", "") or "").upper()

    if template.startswith("dataviz_") and payload.get("dataviz"):
        dv = payload["dataviz"]
        pts = [p for p in (dv.get("points") or []) if isinstance(p, dict)][:5]
        if len(pts) >= 2:
            p = {"title": str(dv.get("title") or main or ""), "values": [float(x.get("value") or 0) for x in pts],
                 "shown": [str(x.get("display") or x.get("value")) for x in pts], "labels": [str(x.get("label") or "") for x in pts],
                 "unit": str(dv.get("unit") or "")}
            kind = str(dv.get("kind") or "")
            if kind in ("change", "timeline"):
                return "line", p
            long_labels = any(len(x) > 12 for x in p["labels"])
            return ("hbars" if len(pts) >= 3 and long_labels else "chart"), p
        if len(pts) == 1 and str(pts[0].get("display") or "").endswith("%"):
            return "ring", {"value": float(pts[0].get("value") or 0), "label": str(dv.get("title") or "")}
    if not main:
        return None

    if role in ("STATISTIC", "DATA", "DATA_LABEL") or decision == "STATISTIC":
        value, shown = _num(main)
        if main.endswith("%") and value is not None and 0 <= value <= 100 and _words(main) == 1:
            return "ring", {"value": value, "label": sub}
        if value is not None and _words(main) <= 2:
            shown_text = main if re.fullmatch(r"[\d,.%]+", main) else main.upper()
            return "number", {"value": value, "shown": shown_text, "label": sub.upper(), "corner": not meta.get("big_number")}
        return "ytag", {"text": main.upper()}
    if role in ("NAME", "LOWER_THIRD", "PERSON") or decision == "LOWER_THIRD":
        return "nametag", {"name": main.upper(), "role": sub.upper()}
    if role in ("LOCATION", "LABEL", "MAP"):
        # News Doc has two place tags: the black box and the orange pin; the place's own name picks one, so it never flips
        look = "orange_place" if sum(map(ord, main)) % 2 else "place"
        return look, {"name": main.upper(), "sub": sub.upper()}
    if role in ("QUOTE", "EVIDENCE"):
        if sub:
            return "pullquote", {"text": main.strip("\"“”"), "who": sub}
        return "quote", {"text": main, "red": ""}
    if role in ("TITLE", "CHAPTER", "REVEAL"):
        if re.fullmatch(r"(1[0-9]|20)\d\d", main):
            return "year", {"text": main}
        if _words(main) <= 3:
            return "chapter", {"text": main}
        return "headline", {"title": main, "sub": sub}
    if role in ("CALLOUT", "EMPHASIS", "HIGHLIGHT", "DATE") or decision == "CALLOUT":
        if _words(main) <= 4:
            return "ytag", {"text": main.upper()}
        return "caption", {"text": main}
    return "caption", {"text": main}


def render_doc_style(spec: Any, out_path: "Path | str", width: int, height: int) -> Optional[Path]:
    """The spec drawn in the News Doc look to a transparent full-frame PNG. None: no look for it, or a frame that isn't 16:9."""
    if width <= 0 or height <= 0 or abs(width / height - 16 / 9) > 0.02:
        return None   # the looks are laid out for 16:9; other shapes keep the usual graphics
    payload = dict(getattr(spec, "payload", None) or {})
    if payload.get("doc_look"):   # an extra placed by graphics/doc_plan.py: its look is already chosen
        picked = (str(payload["doc_look"]), dict(payload.get("doc_params") or {}))
    else:
        picked = pick_look(spec)
    if picked is None:
        return None
    look, params = picked
    try:
        from . import doc_looks as nd

        fn = nd.LOOKS.get(look)
        if fn is None:
            return None
        if look == "glitch":
            t, d = 0.2, 0.42   # the white/cyan flash (the pipeline fades it out)
        else:   # the settled frame: every word shown, every tick made, numbers counted up, before the exit fade
            d = max(3.0, float(getattr(spec, "end", 0.0) or 0.0) - float(getattr(spec, "start", 0.0) or 0.0))
            t = d - 0.35
        img = fn(t, d, params)
        if img.size != (width, height):
            from PIL import Image

            img = img.resize((width, height), Image.LANCZOS)
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out, format="PNG")
        return out
    except Exception as exc:
        print(f"[GRAPHICS] Doc Style look skipped ({exc})")
        return None
