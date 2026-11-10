"""Two-sided figures (docs/product_trailer/REVIEW_REFERENCE_5.md, gap 17).

The reference puts two figures of one kind either side of one phone, each with a small line under it, each landing on its word:
"5500mAh | 6000mAh", "$1299 / S26 Ultra Launch Price | $1499 / S27 Ultra Leaked Price", "25W / S27 | 45W / S27+", and for a downgrade
"LPDDR5 / Not LPDDR6 | UFS 4.0 / Not UFS 5.0". sides_for() finds that in a sentence (no Gemini); layers/pt_sides.mjs draws it.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

MODEL = re.compile(r"(?:Galaxy )?(S\d{2}(?: (?:Plus|Pro|Edge|Ultra|FE))?|iPhone \d+(?: (?:Pro Max|Pro|Plus|Air))?|Pixel \d+(?: Pro(?: XL)?)?)")
BOUNDARY = re.compile(r"[,;]|\b(?:while|whereas|but|and|compared|versus|vs)\b", re.I)
TECH = r"(LPDDR\d+X?|UFS \d(?:\.\d)?|Wi-?Fi \d+E?|Bluetooth \d(?:\.\d)?|USB \d(?:\.\d)?)"
NOT_PAIR = re.compile(TECH + r"(?:\s+[A-Za-z]+){0,2}?\s+(?:instead of|rather than|not)\s+(?:the\s+)?" + TECH, re.I)
PRICE = re.compile(r"\$(\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\d+(?:\.\d{2})?)")
UNITS = {"mah", "w", "gb", "tb", "mp", "hz", " nits", "mm", "x", "fps", "h"}
NUMBER = r"(\d{1,3}(?:,\d{3})+|\d+)"
WORD_PRICE = re.compile(NUMBER + r"(?:\.\d{2})?\s+dollars?\b", re.I)                       # "49 dollars", as a script is written to be read
BARE_PRICE = re.compile(r"\b(?:or|and|to|versus|vs)\s+" + NUMBER + r"\b(?!\s*(?:%|percent|hours?|inch|inches|gb|gigabytes?|tb|terabytes?|mah|watts?|w\b|nits|hz|hertz|mm|x\b|dollars?))", re.I)
INCH = re.compile(r"(\d+(?:\.\d+)?)[\s-]*(?:inch(?:es)?\b|″)", re.I)
STOP_RUN = {"we", "i", "you", "it", "they", "that", "which", "who", "is", "are", "was", "were", "has", "have", "had", "will", "would", "could", "can",
            "should", "may", "might", "be", "been", "said", "says", "heard", "about", "than", "then"}
LEAD = {"of", "on", "the", "a", "an", "for", "in", "at", "with", "to", "its", "their", "up"}


def _noun_after(after: str) -> str:
    """'of video on the outer screen' -> 'Outer Screen'; 'outer display' -> 'Outer Display': the last two words of the run after a figure."""
    run = []
    for w in re.findall(r"[A-Za-z][\w+\-]*", after):
        if w.lower() in STOP_RUN:
            break
        run.append(w)
    while run and run[0].lower() in LEAD:
        run.pop(0)
    run = [w for w in run if w.lower() not in LEAD][-2:]
    return " ".join(w[:1].upper() + w[1:] for w in run)


def _clause_sub(text: str, start: int, end: int, lo: int, hi: int, price: bool) -> str:
    """The small line under a figure at text[start:end]: the model named in its own clause (after it first, else before it), and for a
    price whether it is the launch or the leaked price. lo / hi: the neighbouring figures, which the clause never crosses."""
    after = text[end:hi]
    b = BOUNDARY.search(after)
    after = after[:b.start()] if b else after
    before = text[lo:start]
    bs = list(BOUNDARY.finditer(before))
    before = before[bs[-1].end():] if bs else before
    m = MODEL.search(after) or (list(MODEL.finditer(before)) or [None])[-1]
    model = m.group(1) if m else ""
    qual = ""
    w = re.match(r"\s*(with|without)\s+(it\b|[A-Za-z][\w+]*(?:\s+(?:Plus|\+|Care\+?|Pro|[A-Z][\w+]*))*)", after)
    if w:                                        # "49 dollars without AppleCare Plus, or 19 with it": the condition is the line
        return f"{w.group(1).title()} {w.group(2)}"
    if price:
        clause = (before + " " + after).lower()
        qual = "Launch Price" if "launch" in clause else "Leaked Price" if re.search(r"\bleak|rumou?r", clause) else ""
    if not model and not qual and not price:
        return _noun_after(after)
    return " ".join(x for x in (model, qual) if x)


def _canon(t: str) -> str:
    t = re.sub(r"\s+", " ", t.strip())
    return re.sub(r"(?i)^lpddr", "LPDDR", re.sub(r"(?i)^ufs", "UFS", re.sub(r"(?i)^wi-?fi", "Wi-Fi", t)))


def sides_for(text: str, phone: str) -> Optional[Dict[str, Any]]:
    """{"items": [{value, sub, side}, {value, sub, side}]} for a sentence with two figures of one kind, or two "X instead of Y"; else None."""
    mem = list(dict.fromkeys(_canon(m.group(0)) for m in re.finditer(r"(?i)\b(?:LPDDR\d+X?|UFS \d(?:\.\d)?)\b", text)))
    if len(mem) >= 2 and len({m[:3] for m in mem}) >= 2 and not NOT_PAIR.search(text):                      # a memory type and a storage type in one sentence: both figures, each with what the sentence says of it
        miss = re.search(r"(?i)miss(?:es|ing)? out|without|no longer|not getting|skips?", text)
        back = re.search(r"(?i)\b(?:is )?back\b|returns?|instead|newer|even faster", text)
        sub = "Possibly missing" if miss else "Newer report" if back else "Reported"
        return {"items": [{"value": mem[0], "sub": sub, "side": "left"}, {"value": mem[1], "sub": sub, "side": "right"}]}
    pairs = list(NOT_PAIR.finditer(text))
    if pairs:
        items = [{"value": _canon(m.group(1)), "sub": "Not " + _canon(m.group(2))} for m in pairs[:2]]
        if len(items) == 1:
            items[0]["side"] = "right"
        else:
            items[0]["side"], items[1]["side"] = "left", "right"
        return {"items": items}
    if "%" in text or re.search(r"\bpercent\b", text, re.I):
        return None
    prices = [(m.start(), m.end(), "$" + m.group(1)) for m in PRICE.finditer(text)] + [(m.start(), m.end(), "$" + m.group(1)) for m in WORD_PRICE.finditer(text)]
    if prices:                                   # "... or 19 with it": a bare figure joined to a price is a price too
        first = min(p[0] for p in prices)
        taken = [(a, b) for a, b, _v in prices]
        prices += [(m.start(1), m.end(1), "$" + m.group(1)) for m in BARE_PRICE.finditer(text) if m.start() > first and not any(a <= m.start(1) < b for a, b in taken)]
    inches = [(m.start(), m.end(), m.group(1) + '"') for m in INCH.finditer(text)]
    if prices:
        if len(prices) != 2:
            return None
        figs = sorted(prices)
        price = True
    elif len(inches) == 2:
        figs, price = inches, False
    else:
        from .director import NUM, _fmt, _unit
        found = []
        for m in NUM.finditer(text):
            u = _unit(m.group(2))
            if u.lower() in UNITS:
                found.append((m.start(), m.end(), _fmt(float(m.group(1).replace(",", "")), {"HZ": "Hz", "MM": "mm", "FPS": "fps", "h": " hrs"}.get(u, u)), u))
        units = {f[3] for f in found}
        if len(found) != 2 or len(units) != 1:
            return None
        figs = [(a, b, v) for a, b, v, _u in found]
        price = False
    items = []
    for i, (a, b, v) in enumerate(figs):
        lo = figs[i - 1][1] if i else 0
        hi = figs[i + 1][0] if i + 1 < len(figs) else len(text)
        items.append({"value": v, "sub": _clause_sub(text, a, b, lo, hi, price), "side": "left" if i == 0 else "right"})
    if items[0]["value"] == items[1]["value"] and items[0]["sub"] == items[1]["sub"]:
        return None
    subs = [x["sub"] for x in items]
    for i, s in enumerate(subs):                 # "or 19 with it": "it" is the thing the other figure names
        if s.endswith(" it") and subs[1 - i]:
            items[i]["sub"] = s[:-2] + subs[1 - i].split(" ", 1)[-1]
    if not price and sum(1 for x in items if x["sub"]) == 1 and not any(MODEL.search(x["sub"]) for x in items):
        for x in items:                          # one generic word under one side only reads as a mistake
            x["sub"] = ""
    return {"items": items}
