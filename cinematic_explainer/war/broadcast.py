"""War Documentary broadcast overlays (reference study docs/war/REFERENCE_AIR_DEFENSE.md, templates T1-T4): the small, word-synced marks a
news documentary keeps on its footage. Transparent overlays; same card contract as cards.py (fn(t, dur, params) -> RGBA 1280x720 or None).

  bc_source   T1  yellow box top-right, "SOURCE: <channel / outlet>" from the clip's own metadata
  bc_label    T2  yellow box top-left, black caps: the noun or figure just spoken ("44 MISSILES", "ISKANDER-M"); optional second line
  bc_caption  T3  white box lower-centre, heavy black caps, 1-3 lines: quoted or reported words from the narration
  bc_bigword  T4  one word or figure, very large, centred over clean footage ("1 PERCENT", "2.1 BILLION DOLLARS"); `accent` red|yellow|white

apply(plan, rows, cfg, cat) places them (direction.apply calls it last, config key "broadcast", default on). Only ADDS layers, only over
footage, never over a full-frame card, never in a corner another card is using; everything shown is the narration's own words or the
clip's recorded source. Rates follow the reference: a keyword label about every 15 s, a caption box or a big word about every 25 s.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter

from . import motion as M
from . import semantics as S
from . import tokens as T
from .. import look as L
from ..render import Layer

W, H = T.W, T.H
YEL = (255, 196, 0, 255)
INK = (12, 12, 14, 255)
WHITE = (255, 255, 255, 255)
RED = (232, 40, 40, 255)
FPS = 25
LABEL_GAP_S, CAPTION_GAP_S, BIG_GAP_S = 14.0, 22.0, 25.0


def fr(x: float) -> float:
    return round(round(x * FPS) / FPS, 4)


def _canvas() -> Image.Image:
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def _env(t: float, dur: float, a: float = 0.18) -> float:
    return min(M.ease_out(M.ramp(t, 0.0, a)), 1.0 - M.ramp(t, dur - a, a)) if dur > 0 else 1.0


def _wrap(d: ImageDraw.ImageDraw, text: str, f, width: int, max_lines: int) -> List[str]:
    out, cur = [], ""
    for w in text.split():
        nxt = (cur + " " + w).strip()
        if d.textlength(nxt, font=f) <= width or not cur:
            cur = nxt
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    if len(out) > max_lines:
        out = out[:max_lines]
        out[-1] = out[-1].rstrip(",.;:") + "…"
    return out


def _box(img: Image.Image, x: int, y: int, lines: List[str], f, fg, bg, pad: Tuple[int, int] = (10, 5), right: bool = False, lh: Optional[int] = None) -> Tuple[int, int, int, int]:
    d = ImageDraw.Draw(img)
    lh = lh or int(f.size * 1.18)
    w = max(int(d.textlength(s, font=f)) for s in lines) + 2 * pad[0]
    h = lh * len(lines) + 2 * pad[1]
    x0 = x - w if right else x
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle([x0 + 3, y + 4, x0 + w + 3, y + h + 4], fill=(0, 0, 0, 110))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(4)))
    d.rectangle([x0, y, x0 + w, y + h], fill=bg)
    for i, s in enumerate(lines):
        d.text((x0 + pad[0], y + pad[1] + i * lh - 1), s, font=f, fill=fg)
    return (x0, y, x0 + w, y + h)


# ================================================================================================================ cards
def bc_source(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    text = str((p or {}).get("text") or "").strip()
    if not text:
        return None
    img = _canvas()
    f = T.font("bold", 17)
    s = text if text.lower().startswith("source") else f"SOURCE: {text}"
    _box(img, W - 22, 20, [s.upper() if p.get("caps", True) else s], f, INK, YEL, pad=(9, 4), right=True)
    return L.fade(img, _env(t, dur, 0.15))


def _typed(text: str, t: float, type_s: float) -> str:
    """The first characters of `text` at t: types on over type_s (letter by letter, as the reference's labels do)."""
    if type_s <= 0:
        return text
    n = int(math.ceil(len(text) * M.clamp01(t / type_s)))
    return text[:max(1, n)]


def bc_label(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    text = str((p or {}).get("text") or "").strip().upper()
    if not text:
        return None
    sub = str(p.get("sub") or "").strip().upper()
    type_s = float(p.get("type_s", min(0.6, 0.035 * len(text) + 0.12)))
    lines = [_typed(text, t, type_s)]
    if sub and t > type_s:
        lines.append(_typed(sub, t - type_s, min(0.5, 0.03 * len(sub) + 0.1)))
    img = _canvas()
    f = T.font("display", 34)
    pos = str(p.get("pos") or "tl")
    if pos == "center":                                  # on the subject: centred a little below the middle
        d = ImageDraw.Draw(img)
        w = max(int(d.textlength(s_, font=f)) for s_ in lines) + 24
        _box(img, (W - w) // 2, int(H * 0.56), lines, f, INK, YEL, pad=(12, 5))
    else:
        _box(img, 40, 40, lines, f, INK, YEL, pad=(12, 5))   # the box grows as the letters arrive
    return L.fade(img, 1.0 - M.ramp(t, dur - 0.18, 0.18))


def bc_caption(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """White box, heavy black caps. With `words_t` (one time per word, seconds from the card start) each word appears as it is spoken and
    the box grows with it; without, the line types on over the first 0.6 s."""
    text = str((p or {}).get("text") or "").strip().upper()
    if not text:
        return None
    img = _canvas()
    d = ImageDraw.Draw(img)
    f = T.font("display", 34)
    full = ("“" + text + "”") if p.get("quote") else text
    words = full.split()
    wt = [float(x) for x in (p.get("words_t") or [])]
    if len(wt) == len(words):
        shown = [w_ for w_, tt in zip(words, wt) if tt <= t] or words[:1]
    else:
        shown = words[:max(1, int(math.ceil(len(words) * M.clamp01(t / 0.6))))]
    lines = _wrap(d, " ".join(shown), f, 760, 3)
    full_lines = _wrap(d, full, f, 760, 3)
    lh = 40
    w = max(int(d.textlength(s_, font=f)) for s_ in lines) + 40
    h = lh * len(lines) + 18
    y_bottom = int(H * 0.80) + 18
    x0 = (W - max(int(d.textlength(s_, font=f)) for s_ in full_lines) - 40) // 2 if p.get("anchor_left") else (W - w) // 2
    y0 = y_bottom - h
    lay = _canvas()
    ld = ImageDraw.Draw(lay)
    sh = _canvas()
    ImageDraw.Draw(sh).rectangle([x0 + 4, y0 + 6, x0 + w + 4, y0 + h + 6], fill=(0, 0, 0, 120))
    lay.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6)))
    ld.rectangle([x0, y0, x0 + w, y0 + h], fill=WHITE)
    for i, s_ in enumerate(lines):
        tw = d.textlength(s_, font=f)
        ld.text((x0 + (w - tw) / 2, y0 + 8 + i * lh), s_, font=f, fill=INK)
    img.alpha_composite(lay)
    return L.fade(img, 1.0 - M.ramp(t, dur - 0.2, 0.2))


def bc_bigword(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    text = str((p or {}).get("text") or "").strip().upper()
    if not text:
        return None
    sub = str(p.get("sub") or "").strip().upper()
    acc = {"red": RED, "yellow": YEL, "white": WHITE}.get(str(p.get("accent") or "yellow"), YEL)
    img = _canvas()
    d = ImageDraw.Draw(img)
    size = 120 if len(text) <= 10 else 92 if len(text) <= 18 else 70
    f = T.font("display", size)
    while d.textlength(text, font=f) > W - 160 and size > 40:
        size -= 6
        f = T.font("display", size)
    k = M.ease_out(M.ramp(t, 0.0, 0.3))
    sc = 1.12 - 0.12 * k                                              # punches in, settles
    tw = d.textlength(text, font=f)
    lay = _canvas()
    ld = ImageDraw.Draw(lay)
    cy = H * 0.46
    ld.text(((W - tw) / 2 + 4, cy - size / 2 + 5), text, font=f, fill=(0, 0, 0, 170))
    ld.text(((W - tw) / 2, cy - size / 2), text, font=f, fill=acc)
    if sub:
        fs = T.font("display", max(30, size // 3))
        sw = d.textlength(sub, font=fs)
        ld.text(((W - sw) / 2 + 3, cy + size / 2 + 8 + 3), sub, font=fs, fill=(0, 0, 0, 170))
        ld.text(((W - sw) / 2, cy + size / 2 + 8), sub, font=fs, fill=WHITE)
    lay = lay.filter(ImageFilter.GaussianBlur(0))
    if abs(sc - 1.0) > 0.002:
        z = lay.resize((int(W * sc), int(H * sc)), Image.BILINEAR)
        lay = z.crop(((z.width - W) // 2, (z.height - H) // 2, (z.width - W) // 2 + W, (z.height - H) // 2 + H))
    img.alpha_composite(lay)
    return L.fade(img, min(k, 1.0 - M.ramp(t, dur - 0.22, 0.22)))


BROADCAST_CARDS = {"bc_source": bc_source, "bc_label": bc_label, "bc_caption": bc_caption, "bc_bigword": bc_bigword}


# ================================================================================================================ placement
_FULL = None
CORNER_TR = {"kit_speaker", "kit_stamp", "evidence_card", "figure_card", "kit_chips", "bc_source", "source_label"}
CORNER_TL = {"kit_tag", "lay_inset", "kit_ribbon", "bc_label", "kit_chapter"}     # kit_badge sits bottom-right
CENTRE = {"kit_sticker", "kit_scale", "kit_recap", "kit_bignum", "kit_versus", "kit_icons", "kit_flyover", "bc_caption", "bc_bigword",
          "shot_headline", "stat_number", "kit_quote", "kit_kinetic", "kit_title", "kit_datecard", "kit_keywords", "kit_radar", "kit_dossier"}
SOURCE_PROVIDERS = ("youtube", "archive", "commons", "nasa")


def _full_kinds() -> set:
    global _FULL
    if _FULL is None:
        from . import direction as D

        _FULL = set(D.FULL_KINDS)
    return _FULL


def _opaque(ly: Layer) -> bool:
    return ly.kind in _full_kinds() and not (ly.params or {}).get("over")


def _free(layers: Sequence[Layer], a: float, b: float, kinds: set) -> bool:
    """Nothing in the same place, nothing full-frame, and (the style's rule) no other graphic on screen: marks never stack on a card."""
    from .direction import _NOT_A_GRAPHIC

    return not any(ly.start < b and ly.end > a and (ly.kind in kinds or _opaque(ly) or (ly.kind not in _NOT_A_GRAPHIC and ly.kind != "bc_source"))
                   for ly in layers)


def _on_footage(plan: Any, a: float, b: float) -> bool:
    """Real footage under the whole span (long clips are split into 3-6 s pieces: their union counts)."""
    cov = sum(max(0.0, min(b, s.end) - max(a, s.start)) for s in plan.shots)
    return b > a and cov >= (b - a) - 0.08


def source_text(meta: Dict[str, Any]) -> str:
    """'CNN', 'X | @handle', 'Reuters' from what the provider recorded; '' for stock, AI, the user's own files or unknown sources."""
    if not meta or meta.get("ai_generated") or meta.get("user_supplied"):
        return ""
    prov = str(meta.get("provider") or meta.get("source") or "").lower()
    if not any(p in prov for p in SOURCE_PROVIDERS):
        return ""
    ch = str(meta.get("channel") or meta.get("publisher") or meta.get("author") or "").strip()
    if not ch:
        return ""
    if ch.startswith("@"):
        return f"X | {ch}"
    return ch[:34]


_KEY_UNITS = re.compile(r"^(missiles?|drones?|rockets?|interceptors?|launchers?|tanks?|soldiers?|troops|shells?|aircraft|jets?|ships?|"
                        r"kilometres?|kilometers?|km|miles|percent|%|billion|million|people|civilians|attacks?|strikes?|systems?|batteries)$",
                        re.IGNORECASE)


_THINGS = re.compile(r"\b(ballistic missiles?|cruise missiles?|kamikaze drones?|drones?|missiles?|interceptors?|air defen[cs]e|power grid|power plants?|"
                     r"power|heat|electricity|metro stations?|bridges?|refiner(?:y|ies)|depots?|airfields?|air bases?|ports?|tanks?|artillery|shells?|"
                     r"launchers?|warships?|fleet|counteroffensive|offensive|front ?line|trenches|sanctions|oil|gas|ammunition|troops|"
                     r"civilians|winter)\b", re.IGNORECASE)
_DATE_RX = re.compile(r"\b(?:(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday),?\s+)?(?:\d{1,2}\s+)?(?:january|february|march|april|may|"
                      r"june|july|august|september|october|november|december)(?:\s+\d{1,2})?,?\s+(?:19|20)\d{2}\b", re.IGNORECASE)


def _label_of(sent: Any, text: str) -> Optional[Tuple[str, int, str]]:
    """(label, char offset, second line) for the sentence's key noun, in the narration's own words:
    a figure with what it counts ('44 MISSILES') > a named system ('ISKANDER-M') > the places named ('IZIUM · KUPIANSK') > the things named
    ('MISSILES · DRONES'). A date the sentence states rides as the second line ('SEPTEMBER 2022')."""
    dm = _DATE_RX.search(sent.text)
    date = dm.group(0).upper() if dm else ""
    figs = []                                            # two figures set against each other: '35 USED · 12 DELIVERED' style contrast
    for n in sent.numbers:
        if n.is_year or not re.search(r"\d", n.raw):
            continue
        after = re.findall(r"[\w'’-]+", text[n.span[1]:n.span[1] + 30])[:2]
        unit = (n.unit.split()[-1] if n.unit and n.unit != "%" else "") or (after[0] if after and _KEY_UNITS.match(after[0]) else "")
        figs.append((n.raw.rstrip("%") + ("%" if n.unit == "%" else ""), unit, n.span[0]))
    if len(figs) >= 2 and re.search(r"\b(vs|versus|while|whereas|compared|than|but only|against|instead)\b", sent.text, re.IGNORECASE):
        a_, b_ = figs[0], figs[1]
        return f"{a_[0]} {a_[1]}".strip().upper() + "  VS  " + f"{b_[0]} {b_[1]}".strip().upper(), a_[2], date
    for n in sent.numbers:
        if n.is_year or not re.search(r"\d", n.raw):
            continue                                   # a written figure ('44'), not 'two full days'
        after = re.findall(r"[\w'’-]+", text[n.span[1]:n.span[1] + 40])[:2]
        cand = (n.unit.split()[-1] if n.unit and n.unit != "%" else "") or (after[0] if after else "")
        unit = cand if _KEY_UNITS.match(cand or "") else ""
        if n.unit == "%":
            unit = "PERCENT"
        if unit:
            return f"{n.raw.rstrip('%')} {unit}".upper(), n.span[0], date
    for e in sent.entities:
        if e.kind == "equipment" and e.specific and not e.ambiguous:
            return (text[e.span[0]:e.span[1]] or e.name).upper(), e.span[0], date
    places = [e for e in sent.entities if e.kind == "place" and not e.ambiguous and not S._is_possessive(text, e.span[1])]
    if places:
        names = []
        for e in places:
            nm = text[e.span[0]:e.span[1]] or e.name
            if nm.upper() not in names:
                names.append(nm.upper())
        if len(names) >= 2 or not places[0].country:
            return " · ".join(names[:3]), places[0].span[0], date
    things = []
    first = None
    for m in _THINGS.finditer(sent.text):
        w = m.group(0).upper()
        if w not in things:
            things.append(w)
            first = sent.span[0] + m.start() if first is None else first
    if things:
        return " · ".join(things[:2]), first, date
    if date:
        return date, sent.span[0] + dm.start(), ""
    return None


def _caption_of(sent: Any, text: str) -> Optional[str]:
    """Quoted words, or the reported clause after 'said / warned / admitted (that)', 4-16 words, as the narration has them."""
    q = getattr(sent, "quote", None)
    if q is not None and 3 <= len(q.text.split()) <= 18:
        return q.text.strip(" \"“”")
    m = re.search(r"\b(?:said|says|warned|admitted|told \w+|claimed|insisted|announced)\b,?\s+(?:that\s+)?(.+)$", sent.text)
    if m:
        c = m.group(1).strip().rstrip(".")
        if 4 <= len(c.split()) <= 16:
            return c
    return None


_KEYLINE = re.compile(r"\b(the problem|the answer|the truth|the question|here is|that is why|this is why|cannot|can't|only|never|no one|nobody|"
                      r"the one thing|the real|most|first time|for the first|and that|but that|is cracking|running (?:short|out))\b", re.IGNORECASE)


SPEAKER_QUOTE_GAP_S = 35.0
_REPORT = re.compile(r"\b(said|says|told \w+|wrote|warned|admitted|added|insisted|announced|claimed)\b,?\s+(?:that\s+)?", re.IGNORECASE)


def _speaker_quote_of(A: Any, sent: Any) -> Optional[Tuple[Dict[str, Any], float]]:
    """A catalogue person whose words the sentence reports, 5-26 words: (card params with portrait and per-word times, start time)."""
    fig = next((e for e in sent.entities if e.kind == "figure" and e.specific and not e.ambiguous and e.entry), None)
    if fig is None:
        return None
    q = getattr(sent, "quote", None)
    if q is not None and 4 <= len(q.text.split()) <= 26:
        words, k0 = q.text.strip(" \"“”"), sent.span[0] + max(0, sent.text.find(q.text[:10]))
    else:
        m = _REPORT.search(sent.text)
        if not m:
            return None
        words = sent.text[m.end():].strip().rstrip(".")
        k0 = sent.span[0] + m.end()
        if not 5 <= len(words.split()) <= 26:
            return None
    from . import portraits as PT

    pr = PT.portrait_for(fig.id or fig.name) or {}
    role = re.split(r"\s+(?:since|from|until)\s+|\s*\(", str(fig.entry.get("role") or ""))[0].strip()
    a = A.time_at(k0) - 0.6
    params = {"name": str(fig.entry.get("name") or fig.name), "role": role, "quote": words, "portrait": pr.get("path")}
    params["words_t"] = [max(0.0, x + 0.6) for x in _word_times(A, sent, ("“" + words + "”").replace("“", "").replace("”", ""), a + 0.6)]
    return params, a


_EVIDENCE = re.compile(r"^\W*(this is (?:the|what|how|where)|these are|here is how|here's how|watch)\b", re.IGNORECASE)


def _word_times(A: Any, sent: Any, cap: str, a: float) -> List[float]:
    """Seconds (from the card start a) at which each caption word is spoken, read from the narration's own word times."""
    low = A.text.lower()
    pos = sent.span[0]
    out: List[float] = []
    words = cap.split()
    for w in words:
        k = low.find(w.lower().strip("“”\"'.,"), pos)
        if k < 0:
            out.append(out[-1] + 0.3 if out else 0.0)
            continue
        out.append(round(max(0.0, A.time_at(k) - a), 3))
        pos = k + len(w)
    return out


_BIG = re.compile(r"(\d[\d,.]*)\s*(%|percent|billion|million|trillion)(\s+(?:dollars|euros?|pounds))?", re.IGNORECASE)


def _bigword_of(sent: Any) -> Optional[Tuple[str, str, int]]:
    m = _BIG.search(sent.text)
    if not m:
        return None
    unit = "PERCENT" if m.group(2) in ("%", "percent") else m.group(2).upper()
    money = (m.group(3) or "").strip().upper()
    return f"{m.group(1)} {unit}" + (f" {money}" if money else ""), "", sent.span[0] + m.start()


FOOTAGE_FIRST_KINDS = {"lay_stat_split", "stat_number", "kit_bignum", "lay_equipment_hero", "equipment_card"}
MIN_REL = 0.3


def _fits(meta: Dict[str, Any]) -> bool:
    """The clip is known to show what its sentence says: the CSV's own search picked it, or the matcher rated it relevant."""
    if not meta or meta.get("ai_generated") or meta.get("mismatch"):
        return False
    rel = meta.get("relevance")
    return bool(meta.get("csv_pick")) or (isinstance(rel, (int, float)) and rel >= MIN_REL)


def footage_first(plan: Any, rows: Sequence[Dict[str, Any]], cfg: Dict[str, Any]) -> int:
    """Over a clip that fits its sentence, a full-frame figure / equipment / kinetic panel gives the screen back to the clip; the sentence's
    figure or name is then typed onto the clip instead (reference: '1 WOMAN KILLED / 15 PEOPLE INJURED' and '280 DRONES' sit on the
    footage). Maps, documents, quote cards, charts, timelines and every graphic the CSV asked for are kept."""
    gone = 0
    for r in rows:
        if not r.get("footage") or not _fits(r.get("footage_meta") or {}):
            continue
        a, b = r["_start"] - 0.05, r["_end"] + 0.6
        drop = [ly for ly in plan.layers if ly.kind in FOOTAGE_FIRST_KINDS and a <= ly.start < b and not (ly.params or {}).get("csv_graphic")
                and _on_footage(plan, ly.start, ly.end)]
        for ly in drop:
            plan.layers.remove(ly)
            gone += 1
    return gone


def apply(plan: Any, rows: Sequence[Dict[str, Any]], cfg: Dict[str, Any], cat: Any) -> Dict[str, int]:
    out = {"source": 0, "label": 0, "caption": 0, "bigword": 0, "footage_first": 0}
    rows = sorted(rows, key=lambda r: r["_start"])
    if cfg.get("footage_first", True):
        out["footage_first"] = footage_first(plan, rows, cfg)
    added: List[Layer] = []
    layers = plan.layers

    def put(kind: str, a: float, b: float, params: Dict[str, Any], need: set, until: Optional[float] = None) -> bool:
        """At a..b, or (with `until`) at the first moment after a blocking card ends, keeping the same length, before `until`."""
        ln = b - a
        starts = [a]
        if until is not None:
            starts += sorted(ly.end + 0.15 for ly in layers + added if a < ly.end < until and (ly.kind in need or _opaque(ly)))
        for s0 in starts:
            s0, e0 = fr(s0), fr(min(s0 + ln, until if until is not None else s0 + ln))
            if e0 - s0 >= min(ln, 2.2) - 0.01 and _on_footage(plan, s0, e0) and _free(layers + added, s0, e0, need):
                added.append(Layer(kind, s0, e0, params, dim=False))
                return True
        return False

    # T1: the clip's own source, for as long as the clip is on screen (split around full-frame cards and the corner's other cards)
    if cfg.get("bc_source", True):
        for r in rows:
            src = source_text(r.get("footage_meta") or {})
            if not src or not r.get("footage"):
                continue
            for s in plan.shots:
                if s.path != r["footage"] or s.end <= r["_start"] or s.start >= r["_end"] + 0.5:
                    continue
                a, b = max(s.start, r["_start"]), min(s.end, r["_end"] + 0.5)
                blocks = sorted((ly.start, ly.end) for ly in layers + added if ly.start < b and ly.end > a and (_opaque(ly) or ly.kind in CORNER_TR))
                cur = a
                for x, y in blocks + [(b, b)]:
                    if x - cur >= 1.5 and put("bc_source", cur, x, {"text": src}, CORNER_TR):
                        out["source"] += 1
                    cur = max(cur, y)
    # One text element per spoken sentence over footage (the reference keeps text on the clip ~80 % of the time, changing every 2-4 s):
    # a figure -> label (money / percent -> big figure), quoted or reported words -> caption box, the paragraph's key line -> caption box,
    # a named system -> label. Each types on with the words; consecutive elements never repeat the same kind three times in a row.
    recent: List[str] = []
    last_sq = -1e9
    for r in rows:
        text = str(r.get("text") or "")
        if not text.strip():
            continue
        A = S.analyze_scene(text, cat, r.get("words"), r["_start"], r["_end"])
        sents = A.sentences
        for si, sent in enumerate(sents):
            s_end = A.time_at(sent.span[1] - 1) + 0.5 if sent.span[1] > sent.span[0] else r["_end"]
            s_end = min(max(s_end, A.time_at(sent.span[0]) + 2.6), r["_end"] + 0.4)
            opts: List[Tuple[str, Dict[str, Any], float, float]] = []
            sq = _speaker_quote_of(A, sent) if cfg.get("speaker_quotes", True) else None
            if sq and r["_start"] - last_sq >= SPEAKER_QUOTE_GAP_S:
                params, a = sq
                opts.append(("lay_speaker_quote", params, a, max(s_end, a + min(7.0, max(3.6, 0.42 * len(params["quote"].split()))))))
            bw = _bigword_of(sent) if cfg.get("bc_bigword", True) else None
            if bw:
                a = A.time_at(bw[2]) - 0.15
                opts.append(("bc_bigword", {"text": bw[0], "sub": bw[1], "accent": "yellow"}, a, a + 2.6))
            lab = _label_of(sent, text) if cfg.get("bc_label", True) else None
            cap = _caption_of(sent, text) if cfg.get("bc_caption", True) else None
            if _EVIDENCE.search(sent.text):
                continue                                                # "This is the bridge the next morning": the picture holds, nothing on top
            if cap is None and cfg.get("bc_caption", True) and (_KEYLINE.search(sent.text) or sent.text.rstrip().endswith("?")) \
                    and 3 <= len(sent.text.split()) <= 16:
                cap = sent.text.strip().rstrip(".")                     # the narration's own key line, as the reference boxes it
            if cap:
                a = A.time_at(sent.span[0] + max(0, sent.text.upper().find(cap.upper()[:12]))) - 0.05
                opts.append(("bc_caption", {"text": cap, "quote": sent.quote is not None,
                                            "words_t": _word_times(A, sent, cap, a)}, a, max(s_end, a + min(5.0, max(2.4, len(cap.split()) * 0.36)))))
            if lab:
                a = A.time_at(lab[1]) - 0.1
                opts.append(("bc_label", {"text": lab[0], "sub": lab[2]}, a, max(a + 2.6, min(s_end, a + 4.0))))
            for kind, params, a, b in opts:
                if recent[-2:] == [kind, kind]:
                    continue
                key = kind[3:]
                if put(kind, a, b, params, CORNER_TL if kind == "bc_label" else CENTRE, until=s_end + 0.4):
                    out[key] = out.get(key, 0) + 1
                    if kind == "lay_speaker_quote":
                        last_sq = r["_start"]
                    recent.append(kind)
                    break
    plan.layers.extend(added)
    for ch in plan.layers:          # the source now sits top-right: the status chip keeps its status word only, never the name twice
        if ch.kind != "status_chip" or " · " not in str((ch.params or {}).get("text") or ""):
            continue
        status, name = str(ch.params["text"]).split(" · ", 1)
        if any(s.kind == "bc_source" and s.start < ch.end and s.end > ch.start and name.strip().lower() in s.params["text"].lower() for s in added):
            ch.params = dict(ch.params, text=status)
            out["chips_trimmed"] = out.get("chips_trimmed", 0) + 1
    return out
