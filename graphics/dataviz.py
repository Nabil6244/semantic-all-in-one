"""Automatic data visualization — quantitative narration becomes a chart, through the EXISTING graphics pipeline.

Detection is deterministic and never fabricates data: every number on a chart was spoken in the narration line.
The only derived figure is the percent change of a "from A to B" line (plain arithmetic on the two spoken numbers).

    detect_dataviz(text) -> DataViz | None

  kind         when                                                          drawn as
  comparison   two named values of the same kind in one line                 two horizontal bars
               ("Texas pumps 5.6 million barrels a day, New Mexico 1.8 million")
  ranking      three or more named values of the same kind                   sorted horizontal bars
  change       a quantity going "from A (in 1990) to B (in 2020)"            before / after bars + change pill
  share        "70 percent of the world's cobalt ..."                        a filled share track
  timeline     three or more dated events in one line                        dots on a line, year above, event below

Trust checks (any failing -> no chart; the existing statistic card / text treatment applies as before):
  * every value parses, all values are the same kind (same currency / percent / magnitude-noun),
  * labels are named (capitalized) and distinct, values are positive, a share is 0-100%,
  * at most 6 bars and 5 timeline points (beyond that a chart is unreadable in a few seconds).

Rendering produces the same full-frame transparent PNG every other graphic produces (graphics/render.py), so it rides
the existing overlay / animation / render-cache path unchanged and scales with the frame (1080p and 4K alike).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

_MAG = {"thousand": 1e3, "k": 1e3, "million": 1e6, "m": 1e6, "mn": 1e6, "billion": 1e9, "bn": 1e9, "b": 1e9,
        "trillion": 1e12, "tn": 1e12}
_NUM = (r"(?P<cur>[$€£])?\s?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
        r"(?:\s?(?P<mag>thousand|million|billion|trillion|bn|mn|tn|k|m|b)\b)?"
        r"(?:\s?(?P<pct>%|percent\b|per cent\b))?")
_NUM_RE = re.compile(_NUM, re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(1[5-9]\d\d|20\d\d)\b")
_UNIT_NOUN_RE = re.compile(r"^\s*([a-z][a-z-]{2,}(?:\s+(?:of\s+)?[a-z][a-z-]{2,})?)", re.IGNORECASE)
_LABEL_RE = re.compile(r"((?:[A-Z][\w'’.-]*)(?:\s+(?:of|and|de|the|[A-Z][\w'’.-]*))*)(?:['’]s)?\s*[^.,;]{0,40}?$")
_STOP_LABELS = {"the", "a", "an", "in", "by", "it", "this", "that", "today", "then", "but", "and", "while", "of",
                "about", "nearly", "almost", "over", "under", "more", "less", "than", "some", "around", "roughly"}
_NON_UNIT_WORDS = {"in", "by", "and", "to", "from", "while", "compared", "versus", "vs", "at", "of", "a", "the", "per",
                   "each", "every", "is", "are", "was", "were", "with", "for", "on", "or", "than", "more", "less"}
_CHANGE_RE = re.compile(
    r"(?P<subject>[\w'’ -]{0,60}?)\b(?:rose|grew|jumped|climbed|increased|soared|surged|fell|dropped|declined|shrank|"
    r"plunged|went|moved|expanded|doubled|tripled|changed)?\s*from\s+" + _NUM.replace("?P<", "?P<a_")
    + r"(?:\s+(?!in\b|to\b)[a-z][a-z-]+){0,2}(?:\s+in\s+(?P<a_year>1[5-9]\d\d|20\d\d))?\s*(?:,\s*)?to\s+(?:about\s+|nearly\s+|almost\s+|over\s+)?"
    + _NUM.replace("?P<", "?P<b_") + r"(?:\s+(?!in\b|by\b)[a-z][a-z-]+){0,2}(?:\s+(?:in|by)\s+(?P<b_year>1[5-9]\d\d|20\d\d))?",
    re.IGNORECASE,
)
_SHARE_RE = re.compile(
    r"(?P<num>\d{1,3}(?:\.\d+)?)\s?(?:%|percent\b|per cent\b)\s+of\s+(?:the\s+|all\s+|its\s+|their\s+)?"
    r"(?P<what>[\w'’ -]{3,48}?)(?=[,.;:]|\s+(?:is|are|was|were|comes?|came|goes|went|lives?|lived|flows?|"
    r"passes|passed|is produced|was produced|come|depends?|relies)\b|$)",
    re.IGNORECASE,
)


@dataclass
class DataPoint:
    label: str
    value: float
    display: str


@dataclass
class DataViz:
    kind: str  # comparison | ranking | change | share | timeline
    title: str
    points: List[DataPoint] = field(default_factory=list)
    unit: str = ""
    note: str = ""  # e.g. "+350%" for a change (derived from the spoken numbers)
    confidence: float = 0.0
    source_text: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DataViz":
        pts = [DataPoint(**p) for p in (d or {}).get("points") or []]
        return cls(kind=str(d.get("kind") or ""), title=str(d.get("title") or ""), points=pts,
                   unit=str(d.get("unit") or ""), note=str(d.get("note") or ""),
                   confidence=float(d.get("confidence") or 0), source_text=str(d.get("source_text") or ""))


# --------------------------------------------------------------------------- parsing
def _value(m: re.Match, prefix: str = "") -> Tuple[float, str, str]:
    """(absolute value, kind, display) of a number match. kind groups values that can share an axis."""
    g = lambda name: m.group(prefix + name)  # noqa: E731
    raw = g("num").replace(",", "")
    v = float(raw)
    mag = (g("mag") or "").lower()
    cur = g("cur") or ""
    pct = bool(g("pct"))
    if mag:
        v *= _MAG.get(mag, 1.0)
    kind = "pct" if pct else (f"cur:{cur}" if cur else "n")
    return v, kind, _display(m.group(0).strip())


def _display(text: str) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    t = re.sub(r"\s?percent\b|\s?per cent\b", "%", t, flags=re.IGNORECASE)
    t = re.sub(r"\bthousand\b", "K", t, flags=re.IGNORECASE)
    t = re.sub(r"\bmillion\b", "M", t, flags=re.IGNORECASE)
    t = re.sub(r"\bbillion\b", "B", t, flags=re.IGNORECASE)
    t = re.sub(r"\btrillion\b", "T", t, flags=re.IGNORECASE)
    t = re.sub(r"(\d)\s+([KMBT])\b", r"\1\2", t)
    return t


def _unit_after(text: str, end: int) -> str:
    m = _UNIT_NOUN_RE.match(text[end:end + 40])
    if not m:
        return ""
    words = [w for w in m.group(1).split() if w.lower() not in _NON_UNIT_WORDS]
    return " ".join(words[:2]).lower()


def _label_before(text: str, start: int, floor: int) -> str:
    """The named thing a number belongs to: the closest capitalized phrase before it (same clause, after the previous
    number). "Texas produces 5.6 million" -> "Texas"; "China's 120 million" -> "China"."""
    window = text[floor:start]
    window = re.split(r"[;:]|\b(?:while|whereas|compared (?:to|with)|versus|vs\.?)\b", window)[-1]
    caps = list(re.finditer(r"(?:[A-Z][\w'’.-]*)(?:\s+(?:of|and|de|the|[A-Z][\w'’.-]*))*", window))
    for c in reversed(caps):
        name = re.sub(r"['’]s$", "", c.group(0)).strip(" .")
        words = [w for w in name.split() if w.lower() not in _STOP_LABELS]
        if not words:
            continue
        while words and words[-1].lower() in ("of", "and", "de", "the"):
            words.pop()
        name = " ".join(words)
        if name and not _YEAR_RE.fullmatch(name):
            return name
    return ""


def _numbers(text: str) -> List[Tuple[re.Match, float, str, str]]:
    out = []
    for m in _NUM_RE.finditer(text):
        if not m.group("num"):
            continue
        if _YEAR_RE.fullmatch(m.group("num")) and not (m.group("mag") or m.group("pct") or m.group("cur")):
            continue  # a bare year is a date, not a value
        v, kind, disp = _value(m)
        if v <= 0:
            continue
        out.append((m, v, kind, disp))
    return out


# --------------------------------------------------------------------------- detection
def _detect_change(text: str) -> Optional[DataViz]:
    m = _CHANGE_RE.search(text)
    if not m:
        return None
    a_num, b_num = m.group("a_num"), m.group("b_num")
    if not (a_num and b_num):
        return None
    a = float(a_num.replace(",", ""))
    b = float(b_num.replace(",", ""))
    a_mag, b_mag = (m.group("a_mag") or "").lower(), (m.group("b_mag") or "").lower()
    if a_mag and not b_mag and _MAG.get(a_mag, 1) > 1 and b >= a / 1000:
        b_mag = a_mag
    if b_mag and not a_mag:
        a_mag = b_mag  # "from 2 to 9 million": both are millions
    a *= _MAG.get(a_mag, 1.0)
    b *= _MAG.get(b_mag, 1.0)
    a_pct, b_pct = bool(m.group("a_pct")), bool(m.group("b_pct"))
    if a_pct != b_pct or (m.group("a_cur") or "") != (m.group("b_cur") or "") or a <= 0 or b <= 0 or a == b:
        return None
    if _YEAR_RE.fullmatch(a_num) and _YEAR_RE.fullmatch(b_num) and not (a_mag or b_mag or a_pct):
        return None  # "from 1990 to 2020" is a period, not a quantity
    cur = m.group("a_cur") or m.group("b_cur") or ""
    pct = "%" if a_pct else ""

    def disp(v_text: str, mag: str) -> str:
        return _display(f"{cur}{v_text}{(' ' + mag) if mag else ''}{pct}")

    a_label = m.group("a_year") or "Before"
    b_label = m.group("b_year") or "After"
    subject = _clean_subject(m.group("subject") or "")
    unit = _unit_after(text, m.end("b_num") if not m.group("b_mag") else m.end("b_mag"))
    change = (b - a) / a * 100.0
    note = (f"{'+' if change > 0 else '−'}{abs(change):.0f}%" if abs(change) < 1000 else f"×{b / a:.1f}")
    title = subject or (unit.upper() if unit else "CHANGE")
    return DataViz("change", title=title.upper(), unit=unit, note=note, confidence=0.8, source_text=text,
                   points=[DataPoint(a_label, a, disp(a_num, a_mag)), DataPoint(b_label, b, disp(b_num, b_mag))])


def _clean_subject(subject: str) -> str:
    words = [w for w in re.findall(r"[\w'’-]+", subject)][-5:]
    while words and words[0].lower() in _STOP_LABELS | {"its", "their", "his", "her", "has", "have", "had", "was"}:
        words.pop(0)
    while words and words[-1].lower() in {"has", "have", "had", "was", "were", "is", "are", "the", "its", "their"}:
        words.pop()
    return " ".join(words)


def _detect_share(text: str) -> Optional[DataViz]:
    m = _SHARE_RE.search(text)
    if not m:
        return None
    v = float(m.group("num"))
    if not 0 < v <= 100:
        return None
    what = re.sub(r"\s+", " ", m.group("what")).strip(" -")
    if len(what.split()) > 7 or not what:
        return None
    holder = _label_before(text, m.start(), 0)
    after = text[m.end():m.end() + 60]
    src = re.search(r"\b(?:comes?|came|is produced|was produced|lives?|lived|flows?|passes|passed)\s+(?:from|in|through)\s+"
                    r"((?:[A-Z][\w'’.-]*)(?:\s+(?:of|and|the|[A-Z][\w'’.-]*))*)", after)
    label = (src.group(1) if src else holder).strip(" .,;:")
    title = f"SHARE OF {what.upper()}"
    return DataViz("share", title=title, unit="%", confidence=0.75, source_text=text,
                   points=[DataPoint(label or what.title(), v, _display(f"{m.group('num')}%"))])


def _detect_named_values(text: str) -> Optional[DataViz]:
    nums = _numbers(text)
    if len(nums) < 2:
        return None
    points: List[DataPoint] = []
    kinds = set()
    floor = 0
    unit = ""
    last_mag = ""
    for m, v, kind, disp in nums:
        label = _label_before(text, m.start(), floor)
        floor = m.end()
        if not label:
            continue
        mag = (m.group("mag") or "").lower()
        if not mag and last_mag and not m.group("pct") and v < 1000:
            # "5.6 million barrels, New Mexico 1.8, and ..." — a list carries its magnitude forward
            v *= _MAG.get(last_mag, 1.0)
            disp = _display(f"{m.group(0).strip()} {last_mag}")
        last_mag = mag or last_mag
        unit = unit or _unit_after(text, m.end())
        kinds.add(kind)
        points.append(DataPoint(label, v, disp))
    labels = [p.label.lower() for p in points]
    if len(points) < 2 or len(kinds) != 1 or len(set(labels)) != len(labels) or len(points) > 6:
        return None
    kind = "ranking" if len(points) >= 3 else "comparison"
    if kind == "ranking":
        points.sort(key=lambda p: -p.value)
    title = unit.upper() if unit else ("SHARE" if "pct" in kinds else "COMPARISON")
    return DataViz(kind, title=title, unit=unit, confidence=0.7 if kind == "comparison" else 0.75,
                   source_text=text, points=points)


def _detect_timeline(text: str) -> Optional[DataViz]:
    years = list(_YEAR_RE.finditer(text))
    if len({y.group(1) for y in years}) < 3 or len(years) > 5:
        return None
    clauses = re.split(r",\s*(?:and\s+|then\s+)?|;\s*|\s+and\s+(?=(?:in|by)\s+\d{4})|\s+then\s+", text)
    points: List[DataPoint] = []
    for clause in clauses:
        y = _YEAR_RE.search(clause)
        if not y:
            continue
        rest = (clause[:y.start()] + clause[y.end():])
        rest = re.sub(r"\b(?:in|by|during|around|until|from|of)\s*$", "", rest.strip(" .,"), flags=re.IGNORECASE)
        rest = re.sub(r"\b(?:in|by|during|around)\b\s*(?=[,.]|$)", "", rest, flags=re.IGNORECASE)
        words = [w for w in re.findall(r"[\w'’-]+", rest) if w.lower() not in ("in", "by", "the", "and", "then", "it", "was")]
        if not words:
            continue
        points.append(DataPoint(" ".join(words[:4]), float(y.group(1)), y.group(1)))
    if len(points) < 3 or len({p.display for p in points}) != len(points):
        return None
    points.sort(key=lambda p: p.value)
    return DataViz("timeline", title="TIMELINE", confidence=0.7, source_text=text, points=points)


def detect_dataviz(text: str) -> Optional[DataViz]:
    """The chart this narration line supports, or None. Never invents a value."""
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text.split()) < 6:
        return None
    for detector in (_detect_change, _detect_share, _detect_named_values, _detect_timeline):
        try:
            viz = detector(text)
        except (ValueError, IndexError, re.error):
            viz = None
        if viz is not None and viz.points:
            return viz
    return None


DECISION_FOR_KIND = {"comparison": "COMPARISON", "ranking": "CHART", "change": "COMPARISON", "share": "PROGRESS",
                     "timeline": "TIMELINE"}


# --------------------------------------------------------------------------- rendering
def render_dataviz(viz: DataViz, out_path: Path | str, width: int, height: int, *, design=None) -> Optional[Path]:
    """Draw the chart as a full-frame transparent PNG (right side of the frame, inside the safe area)."""
    from PIL import Image, ImageDraw, ImageFilter

    from .design_system import get_design_system
    from .render import _load_font

    design = design or get_design_system()
    if not viz.points:
        return None
    k = height / 1080.0
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    panel_w = int(width * 0.36)
    pad = int(30 * k)
    x0 = int(width * (1 - design.margin_x_ratio)) - panel_w
    title_font = _load_font(design.font_ui, "SemiBold", max(12, int(26 * k)))
    label_font = _load_font(design.font_ui, "SemiBold", max(11, int(25 * k)))
    value_font = _load_font(design.font_data, "Bold", max(12, int(30 * k)))
    big_font = _load_font(design.font_data, "Bold", max(18, int(76 * k)))
    small_font = _load_font(design.font_ui, "Regular", max(10, int(21 * k)))
    draw = ImageDraw.Draw(img)

    def text_w(t, f):
        b = draw.textbbox((0, 0), t, font=f)
        return b[2] - b[0], b[3] - b[1]

    def fit(t, f, max_w):
        if text_w(t, f)[0] <= max_w:
            return t
        while t and text_w(t + "…", f)[0] > max_w:
            t = t[:-1]
        return t.rstrip() + "…"

    accent = design.accent
    track = (255, 255, 255, 46)
    body: List[tuple] = []  # (kind, args) drawn after the panel is sized
    inner_w = panel_w - 2 * pad
    title = fit(viz.title, title_font, inner_w)
    _, th = text_w(title or "X", title_font)
    y = pad + th + int(22 * k)

    if viz.kind in ("comparison", "ranking"):
        max_v = max(p.value for p in viz.points) or 1.0
        label_w = int(inner_w * 0.36)
        bar_h = int(30 * k)
        gap = int(20 * k)
        for p in viz.points:
            vw, _ = text_w(p.display, value_font)
            bar_room = inner_w - label_w - vw - int(16 * k)
            bw = max(int(6 * k), int(bar_room * (p.value / max_v)))
            body.append(("bar", fit(p.label, label_font, label_w - int(10 * k)), p.display, y, bar_h, bw, label_w))
            y += bar_h + gap
        y -= gap
    elif viz.kind == "change":
        a, b = viz.points[0], viz.points[1]
        max_v = max(a.value, b.value) or 1.0
        col_h = int(200 * k)
        col_w = int(inner_w * 0.24)
        top = y + int(46 * k)
        body.append(("cols", a, b, top, col_h, col_w, max_v))
        y = top + col_h + int(44 * k)
    elif viz.kind == "share":
        p = viz.points[0]
        _, bh = text_w(p.display, big_font)
        body.append(("share", p, y, bh))
        y += bh + int(28 * k) + int(18 * k) + int(40 * k)
    elif viz.kind == "timeline":
        body.append(("timeline", viz.points, y))
        y += int(150 * k)
    else:
        return None

    panel_h = y + pad
    y0 = int(height * 0.80) - panel_h
    y0 = max(int(height * design.safe_top_ratio), y0)
    # soft shadow + panel
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([x0 + 4, y0 + 8, x0 + panel_w + 4, y0 + panel_h + 8],
                                             radius=int(10 * k), fill=(0, 0, 0, 120))
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(radius=max(2, int(10 * k)))))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([x0, y0, x0 + panel_w, y0 + panel_h], radius=int(10 * k), fill=design.panel_fill_strong)
    draw.rectangle([x0, y0, x0 + max(2, int(5 * k)), y0 + panel_h], fill=accent)
    draw.text((x0 + pad, y0 + pad), title, font=title_font, fill=design.fill_muted)

    for item in body:
        kind = item[0]
        if kind == "bar":
            _, label, disp, by, bh, bw, label_w = item
            by += y0
            lx = x0 + pad
            _, lh = text_w(label, label_font)
            draw.text((lx, by + (bh - lh) // 2 - int(3 * k)), label, font=label_font, fill=design.fill)
            bx = lx + label_w
            draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=int(4 * k), fill=accent)
            _, vh = text_w(disp, value_font)
            draw.text((bx + bw + int(12 * k), by + (bh - vh) // 2 - int(4 * k)), disp, font=value_font, fill=design.fill)
        elif kind == "cols":
            _, a, b, top, col_h, col_w, max_v = item
            top += y0
            base = top + col_h
            centers = [x0 + pad + int(inner_w * 0.22), x0 + pad + int(inner_w * 0.62)]
            for cx, p, fill in ((centers[0], a, (255, 255, 255, 150)), (centers[1], b, accent)):
                h = max(int(6 * k), int(col_h * p.value / max_v))
                draw.rounded_rectangle([cx - col_w // 2, base - h, cx + col_w // 2, base], radius=int(4 * k), fill=fill)
                vw, vh = text_w(p.display, value_font)
                draw.text((cx - vw // 2, base - h - vh - int(14 * k)), p.display, font=value_font, fill=design.fill)
                lw, _ = text_w(p.label, small_font)
                draw.text((cx - lw // 2, base + int(10 * k)), p.label, font=small_font, fill=design.fill_muted)
            if viz.note:
                nw, nh = text_w(viz.note, value_font)
                nx = x0 + panel_w - pad - nw - int(16 * k)
                ny = top - int(40 * k)
                draw.rounded_rectangle([nx - int(14 * k), ny - int(6 * k), nx + nw + int(14 * k), ny + nh + int(14 * k)],
                                       radius=int(18 * k), fill=(accent[0], accent[1], accent[2], 60), outline=accent,
                                       width=max(1, int(2 * k)))
                draw.text((nx, ny), viz.note, font=value_font, fill=design.fill)
        elif kind == "share":
            _, p, sy, bh = item
            sy += y0
            draw.text((x0 + pad, sy - int(8 * k)), p.display, font=big_font, fill=design.fill)
            ty = sy + bh + int(28 * k)
            track_h = int(18 * k)
            draw.rounded_rectangle([x0 + pad, ty, x0 + pad + inner_w, ty + track_h], radius=track_h // 2, fill=track)
            fw = max(track_h, int(inner_w * min(1.0, p.value / 100.0)))
            draw.rounded_rectangle([x0 + pad, ty, x0 + pad + fw, ty + track_h], radius=track_h // 2, fill=accent)
            if p.label:
                draw.text((x0 + pad, ty + track_h + int(14 * k)), fit(p.label.upper(), small_font, inner_w),
                          font=small_font, fill=design.fill_muted)
        elif kind == "timeline":
            _, pts, ty = item
            ty += y0 + int(56 * k)
            lx0, lx1 = x0 + pad + int(20 * k), x0 + panel_w - pad - int(20 * k)
            draw.line([lx0, ty, lx1, ty], fill=(255, 255, 255, 140), width=max(1, int(3 * k)))
            n = len(pts)
            slot = (lx1 - lx0) / max(1, n - 1)
            r = int(9 * k)
            left, right = x0 + int(pad * 0.6), x0 + panel_w - int(pad * 0.6)

            def centered(cx, w):  # centred on the dot, but never outside the panel
                return int(min(max(cx - w // 2, left), right - w))

            for i, p in enumerate(pts):
                cx = int(lx0 + slot * i)
                draw.ellipse([cx - r, ty - r, cx + r, ty + r], fill=accent)
                yw, yh = text_w(p.display, value_font)
                draw.text((centered(cx, yw), ty - r - yh - int(16 * k)), p.display, font=value_font, fill=design.fill)
                words = p.label.split()
                lines = [" ".join(words[:2]), " ".join(words[2:4])] if len(words) > 2 else [p.label]
                ly = ty + r + int(10 * k)
                for line in lines:
                    line = fit(line, small_font, int(slot * 0.95) if n > 1 else inner_w)
                    lw, lh = text_w(line, small_font)
                    draw.text((centered(cx, lw), ly), line, font=small_font, fill=design.fill_muted)
                    ly += lh + int(6 * k)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, format="PNG")
    return out
