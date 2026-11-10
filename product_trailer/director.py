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

NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(%|W\b|watts?|mAh|milliamp\w*(?:\s+hours?)?|MP|megapixels?|Hz|GB|TB|nits?|mm|fps|ms\b|milliseconds?|hours?|hrs?\b|mbps|points|pts\b|percent\b|x\b)", re.I)
UNIT = {"percent": "%", "watt": "W", "watts": "W", "w": "W", "nit": " nits", "nits": " nits", "megapixel": "MP", "megapixels": "MP", "mp": "MP"}
COLOURS = {"black": "#2b2b2e", "blue": "#3f6fb5", "sky blue": "#8fc3ea", "light pink": "#e9b4c4", "pink": "#e49ab0", "white": "#ecebea", "silver": "#c8ccd2", "grey": "#8a8f98",
           "gray": "#8a8f98", "green": "#4f8a63", "purple": "#6b5aa8", "gold": "#d3b26b", "red": "#b3363f", "orange": "#e08a3a", "navy": "#26325c", "titanium": "#9a9a96",
           "violet": "#b98ce0", "lavender": "#c9b6e8", "mint": "#9fd6c0", "cream": "#efe6d2", "yellow": "#f0d24a", "coral": "#e88a7a"}
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


PRICE_WORDS = re.compile(r"\$|\bprice[sd]?\b|\bdollars?\b|\bamazon\b|\bdeal\b|\bcosts?\b|\bmsrp\b|\bsale\b|\bretail\b|\bdropped to\b", re.I)


def spoken_numbers(text: str) -> str:
    """Whisper writes 5,534 as "5 534" and $919.99 as "919 99": join the digit groups back (cents only in a sentence about a price)."""
    out = text
    while True:
        nxt = re.sub(r"(?<![\d.,])(\d{1,3}) (\d{3})(?![\d])", r"\1,\2", out)
        if nxt == out:
            break
        out = nxt
    if re.search(r"\bdollars?\b", out, re.I):         # a script written for the ear: "1,999 dollars", "up to 2,199, 2,599, and 3,199 dollars"
        out = re.sub(r"(?<![\d$,.])(\d[\d,]*(?:\.\d+)?)\s+dollars?\b", r"$\1", out, flags=re.I)
        out = re.sub(r"(?<![\w$,.])(\d{1,3}(?:,\d{3})+)(?=,\s+(?:and\s+)?\$?\d)", r"$\1", out)
    if PRICE_WORDS.search(out):
        out = re.sub(r"(?<![\d.,$])\$?(\d[\d,]*) (\d{2})(?![\d,]|\s*(?:%|mah|w\b|mp\b|hz\b))", r"$\1.\2", out, flags=re.I)
    return out


TOPICS = (("battery", ("battery", "mah", "milliamp", "charging", "charge", "watts")), ("camera", ("camera", "cameras", "zoom", "telephoto", "megapixel", "lens", "sensor")),
          ("display", ("display", "screen", "brightness", "privacy")), ("chip", ("chip", "snapdragon", "exynos", "processor")),
          ("price", ("price", "prices", "amazon", "black friday", "deal", "buy")), ("design", ("design", "dummy", "dummies", "size", "bigger", "case", "layout", "millimeters")))
NOT_NAMES = {"Samsung", "Apple", "Google", "The", "This", "That", "So", "And", "But", "If", "It", "A", "An", "Today", "First", "Second", "Third", "Here", "US", "I", "One", "Two"}
STATUS = (("certification", "CERTIFIED"), ("certified", "CERTIFIED"), ("leak", "LEAK"), ("rumor", "RUMOR"), ("rumour", "RUMOR"))


def topic_of(text: str) -> Optional[str]:
    """The subject a sentence is about (battery, camera, display, chip, price, design), or None."""
    t = text.lower()
    return next((name for name, words in TOPICS if _has(t, *words)), None)


def _callout(kicker: str, value: str, sub: str = "", topic: Optional[str] = None) -> Dict[str, Any]:
    """A short spoken claim as big readable type beside the 3D phone of its subject (review.feature_visual draws it)."""
    return {"kind": "callout", "kicker": kicker.upper()[:34], "value": value[:28], "sub": sub[:40], "feature": topic or "", "look": "", "_own": True}   # the point itself: the variety pass never swaps it


MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")
DATE_LABELS = (("launch", "LAUNCH"), ("announce", "ANNOUNCED"), ("pencil", "PENCIL"), ("update", "UPDATE"), ("respon", "RESPONSE"), ("memo", "MEMO"), ("release", "RELEASE"), ("recall", "RECALL"),
               ("teardown", "TEARDOWN"), ("report", "REPORT"), ("guide", "GUIDE"))


def _doy(e: Dict[str, Any]) -> int:
    import datetime as _dt
    return _dt.date(2001, int(e["month"]), int(e["day"])).timetuple().tm_yday


def _span_days(evs: List[Dict[str, Any]]) -> int:
    d = [_doy(e) for e in evs]
    return max(d) - min(d)


_VERBS = r"published|acknowledged|sent|announced|released|confirmed|launched|issued|opened|posted|said|told|responded|updated|reported|quoted|quoting|arrived|started"


def event_label(text: str, month: int, day: int) -> str:
    """A short label for what happened on a date, from the sentence's own words: 'On October 26, it acknowledged an inner display issue affecting...' -> 'ACKNOWLEDGED INNER DISPLAY ISSUE'."""
    t = re.sub(r"\s+", " ", text)
    m = re.search(r"\b(?:" + MONTHS[month - 1] + r")\s+" + str(day) + r"(?:st|nd|rd|th)?\b[,]?\s*(?:\d{4}[,]?\s*)?(.*)", t, re.I)
    rest = (m.group(1) if m else "").strip(" .")
    v = re.search(r"\b(reportedly\s+)?(" + _VERBS + r")\b\s*(.*)", rest, re.I)
    if not v:
        return ""
    noun = re.split(r"\b(?:affecting|and|to|for|that|which|with|in|on|at|of)\b|[,.;]", v.group(3), maxsplit=1)[0]
    words = [w for w in noun.split() if w.lower() not in ("a", "an", "the", "its", "it", "some", "their")][:4]
    lab = " ".join(([v.group(1).strip()] if v.group(1) else []) + [v.group(2)] + words)
    return lab.upper()


def _dates_in(text: str) -> List[Dict[str, Any]]:
    """Each "October 23" in a sentence with a short label for what happened that day (from the sentence's own words: launch, update, response...)."""
    out = []
    t = text.lower()
    for m in re.finditer(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b", t):
        near = t[max(0, m.start() - 90):m.end() + 40]
        hit = [lab for key, lab in DATE_LABELS if key in near][:2]
        mo, dy = MONTHS.index(m.group(1)) + 1, int(m.group(2))
        lab = event_label(text, mo, dy) if not re.search(r"launch", t[max(0, m.start() - 30):m.end() + 30]) else ""     # what the sentence says happened that day; launch day keeps LAUNCH
        out.append({"month": mo, "day": dy, "label": lab or " ".join(hit[::-1] if len(hit) == 2 and hit[0] == "UPDATE" else hit)})
    return out


def talk_scene(text: str, phone: str = "", ctx: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """The scenes of an explainer's spoken structure, which carry no spec figure: section labels ("Second, the cameras."), how reliable a claim is
    ("This one is a leak."), dates, verdicts ("If your phone works, wait."), a choice put to the viewer, a contradiction, a fit warning."""
    ctx = ctx if ctx is not None else {}
    t = text.lower().strip()
    words = len(t.split())
    name = re.sub(r"\bIphone\b", "iPhone", phone.title()) if phone else "The new phone"
    m = re.match(r"(first|second|third|fourth|fifth|finally|next|lastly)[, ]+(?:the\s+)?([a-z][a-z ]{2,24}?)[.!]?$", t)
    if m and words <= 5:
        return _callout(m.group(1), m.group(2).title(), "", topic_of(m.group(2)))
    m = re.match(r"(two|three|four|a few) more things for ([a-z ]{2,24}?)[.!]?$", t)
    if m:
        return _callout(f"{m.group(1)} more things", "For " + text.strip(" .!")[-len(m.group(2)):], "", ctx.get("topic"))
    m = re.match(r"(?:so )?here['’]s (my take|what doesn['’]t add up)[.!:]?$", t)
    if m:
        v = m.group(1).replace("’", "'")
        return _callout("", v[0].upper() + v[1:], "", ctx.get("topic"))
    m = re.match(r"this (?:one )?is (?:a |the )?(most reliable )?(leak|rumou?r|certification)", t)
    if m and words <= 12:
        tag = "CERTIFIED" if m.group(2) == "certification" or m.group(1) else ("RUMOR" if m.group(2).startswith("rumo") else "LEAK")
        return _callout("This one is", tag.title(), "most reliable" if m.group(1) else "", ctx.get("topic"))
    if re.search(r"\b(?:medium|low|high) reliability\b", t):
        lvl = re.search(r"\b(medium|low|high) reliability\b", t).group(1)
        return _callout("Reliability", lvl.title(), "", ctx.get("topic"))
    if re.search(r"(?:that['’]s|it['’]s) (?:a|just a) (tipster|leaker|rumou?r)[, ]+not (\w+)", t):
        m = re.search(r"(?:that['’]s|it['’]s) (?:a|just a) (tipster|leaker|rumou?r)[, ]+not (\w+)", t)
        return _callout(m.group(1), "Unconfirmed", f"not {m.group(2).title()}", ctx.get("topic"))
    tags = [tag for _, word, tag in sorted((t.find(w), w, tg) for w, tg in STATUS if _has(t, w))]
    if len(dict.fromkeys(tags)) >= 3:                                   # "a leak, a rumor, or a certification listing"
        return _callout("Every claim is a", " · ".join(dict.fromkeys(tags)).title(), "", ctx.get("topic"))
    m = re.search(r"\b(early|late|mid)[- ](20\d\d)\b", t)
    if m and _has(t, "expected", "launch", "announce", "announced", "arrive", "release", "coming"):
        return _callout("Expected", f"{m.group(1).title()} {m.group(2)}", "not announced yet" if re.search(r"(hasn['’]t|has not|not yet) announced", t) else "", ctx.get("topic"))
    m = re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december) (\d{1,2})(?:st|nd|rd|th)?\b", t)
    if m and words <= 16 and not re.search(r"\$\d", text):
        event = "Black Friday" if "black friday" in t else ("Prime Day" if "prime day" in t else "")
        return _callout(event or "Date", f"{m.group(1)[:3].title()} {m.group(2)}", "", "price")
    if re.search(r"(?:don['’]t|do not|no) (?:have )?confirmed .*prices?", t) or re.search(r"prices? (?:aren['’]t|are not|isn['’]t) (?:confirmed|known)", t):
        return _callout("Black Friday prices" if "black friday" in t else "Prices", "Not confirmed", "check closer to the date" if "closer" in t else "", "price")
    m = re.search(r"((?:galaxy )?s\d{2}(?: ultra| plus| pro)?|iphone \d{2}(?: pro max| pro)?) case (?:probably |likely )?won['’]t fit", t)
    if m:
        return _callout(m.group(1).upper().replace("GALAXY ", "") + " case", "Won't fit", "", "design")
    m = re.match(r"if (.{4,40}?),\s*(wait|buy|upgrade|skip it|hold off)\b", t)
    if m:
        return _callout("If " + m.group(1), m.group(2).title(), "", ctx.get("topic"))
    m = re.search(r"the (\w+) (?:looks like|is|seems like) the real upgrade.*the (\w+)(?: change)? is the risk", t)
    if m:
        return _callout("The real upgrade", m.group(1).title(), f"the risk: {m.group(2)}", m.group(1))
    looks = re.findall(r"\b([A-Za-z]+)-(?:inspired|like|style)\b", text)
    if len(looks) >= 2 and _has(t, "first", "earlier", "before", "now", "contradict"):
        return _scene(title="Conflicting leaks", phones=[{"label": "Earlier leak", "color": PURPLE, "cams": 3, "top": f"{looks[0]}-like"},
                                                          {"label": "Latest leak", "color": DARK, "cams": 3, "top": f"{looks[1]}-like", "badge": "Conflicting"}])
    m = re.search(r"wait for (?:this|the new) phone or buy (?:the )?((?:galaxy )?s\d{2}(?: ultra| plus| pro)?|iphone \d{2}(?: pro max| pro)?)", t)
    if m:
        old = "Galaxy " + m.group(1).upper().replace("GALAXY ", "").replace("ULTRA", "Ultra").replace("PLUS", "Plus").replace("PRO", "Pro") if m.group(1).startswith(("s", "galaxy")) else m.group(1).title()
        return _scene(title="Wait or buy?", phones=[{"label": name, "color": DARK, "cams": 3, "text": "WAIT?"}, {"label": old, "color": PURPLE, "cams": 4, "text": "BUY?"}])
    m = re.search(r"(?:the )?([a-z0-9 ]{3,24}?),? or (?:keeping |getting )?(?:the )?([a-z0-9 ]{3,24}?)\?$", t)
    if m and text.strip().endswith("?") and words <= 18:
        a, b = m.group(1).split(":")[-1].strip(), m.group(2).strip()
        a = re.sub(r"^(?:which matters more to you|the)\s*", "", a).strip()
        if a and b:
            cap = lambda x: x[0].upper() + x[1:]
            return _scene(title="Which matters more?", phones=[{"label": "", "color": DARK, "cams": 3, "top": cap(a)}, {"label": "", "color": PURPLE, "cams": 4, "top": cap(b)}])
    return None


def scene_for(text: str, phone: str = "Galaxy S27 Ultra", ctx: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """The scene a sentence calls for. `ctx` carries what the sentences before it were about ({"unit", "topic"}), so "the S26 Ultra has 5,000"
    after a battery sentence is read as mAh."""
    text = spoken_numbers(text)
    prior_dates = list(ctx.get("dates", [])) if ctx is not None else []
    if ctx is not None:                                                  # the dates the script has given so far, with what happened on each (a later date draws a timeline)
        for d in _dates_in(text):
            ctx.setdefault("dates", []).append(d)
    lens_open = bool(ctx.pop("lens_open", False)) if ctx is not None else False   # the sentence before drew lens callouts (gap 4)
    new_dates = [d for d in _dates_in(text) if d not in prior_dates]
    if new_dates and prior_dates and len(text.split()) <= 24 and not re.search(r"\$\d", text):
        evs = [d for d in prior_dates if d["month"] != new_dates[0]["month"] or d["day"] != new_dates[0]["day"]][-2:] + new_dates[:1]
        if len({(e["month"], e["day"]) for e in evs}) >= 2 and _span_days(evs) <= 45:      # a short run of dates on one axis
            return {"kind": "timeline", "events": evs[-3:]}
    talk = talk_scene(text, phone, ctx)
    if talk:
        return talk
    t = text.lower()
    nums = _numbers(text)
    unit = (ctx or {}).get("unit")
    if unit and not [n for n in nums if n["unit"] != "%"]:            # bare figures in a sentence that continues a battery / camera point
        bare = [float(x.replace(",", "")) for x in re.findall(r"(?<![\d.$])(\d[\d,]{2,})(?![\d.]|\s*(?:%|percent))", text) if not re.fullmatch(r"(?:19[89]\d|20[0-3]\d)", x)]   # a bare year ("a 2027 flagship") is not a figure
        nums = [{"v": v, "unit": unit, "raw": f"{v:,.0f}"} for v in bare] + nums
    if not nums and _has(t, "geekbench", "score", "scores", "benchmark"):                   # "scores 4,719 against 3,832": bare figures are points
        bare = [float(x.replace(",", "")) for x in re.findall(r"\b\d[\d,]{2,}(?:\.\d+)?\b", text)]
        nums = [{"v": v, "unit": "pts", "raw": f"{v:,.0f}"} for v in bare[:3]]
    name = re.sub(r"\bIphone\b", "iPhone", phone.title()) if phone else "Galaxy S27 Ultra"
    # 1. certification / database evidence
    chip = next((c for c in ("BIS", "FCC", "3C", "TENAA", "Geekbench") if re.search(r"(?<![a-z])" + c.lower() + r"(?![a-z])", t)), "CERTIFICATION")
    named = chip != "CERTIFICATION" or _has(t, "database", "regulatory")
    if _has(t, "certification", "certified", "certifies", "bis", "fcc", "3c", "regulatory", "database", "listing", "listed", "geekbench") and len(nums) < 2 and (named or not nums):
        return _scene(type="pt_doc", title="Regulatory listing" if chip != "Geekbench" else "Benchmark listing", chip=(chip.upper() + " CERTIFICATION") if chip not in ("Geekbench", "CERTIFICATION") else chip.upper(),
                      rows=7, highlight=3, stamp=_fmt(nums[0]["v"], nums[0]["unit"]) if nums else ("5G" if _has(t, "5g") else ""))
    # 2. a named source (unless the sentence itself calls for a graphic: lens callouts, colour cards, two chips; those draw the claim, the source stays in the voice)
    from . import lenses as _lenses0
    _cols0 = {c for c in COLOURS if re.search(r"(?<![a-z])" + c + r"(?![a-z])", t)}
    graphic_first = bool(_lenses0.layer_for(text, name) or _lenses0.ring_for(text) or (len(_cols0) >= 3 and _has(t, "colour", "colours", "color", "colors", "shades", "options")) or len(_chips_in(text)) >= 2)
    who = re.search(r"(?i:tipster|leaker|source)\s+([A-Z][\w]*(?:\s+[A-Z][\w]*)?)", text)
    pub = re.match(r"([A-Z][\w]+(?:\s+[A-Z][\w]+){0,2})\s+(?:says|said|reports|reported|built|claims|shared|posted|leaked)\b", text.strip())
    if pub and pub.group(1).split()[0] not in NOT_NAMES and not who and not graphic_first:     # "Android Headlines built dummy units ...": the source named on its card
        rest = text.strip()[pub.end():].strip(" .")
        return {"kind": "tweet", "author": pub.group(1), "handle": "", "text": text.strip(), "highlight": " ".join(rest.split()[:4])}
    if not graphic_first and _has(t, "tipster", "leaker", "according to", "rumor", "rumour", "sources say") and (who or _has(t, "tipster", "leaker") or not nums) and len(text.split()) >= 6:   # a bare "rumor" with figures shows the figures
        hl = nums and re.search(re.escape(nums[0]["raw"]) + r"[^,.]*", text)
        return {"kind": "tweet", "author": who.group(1) if who else "As reported", "handle": "", "text": text, "highlight": hl.group(0).strip() if hl else ""}
    bf = body_figure(text, name)
    if bf:
        return bf
    chips2 = _chips_in(text)
    if len(chips2) >= 2:                         # "a standard Snapdragon 8 Elite Gen 6 and a higher-end ... Extreme Gen 6": one phone per chip, the chip badge on each
        return _scene(phones=[{"label": ("Extreme" if "Extreme" in c else "Standard" if i == 0 else "Other"), "color": [PURPLE, DARK][i % 2], "cams": 3, "badge": c} for i, c in enumerate(chips2[:3])], title="Chips")
    # 2b. lens callouts (REVIEW_REFERENCE_4 gap 4): a camera sentence after one keeps that scene and adds to it; two lenses named, or one asked
    #     about, draw the callouts; every other such sentence keeps the older camera scenes below
    from . import lenses as _lenses
    if lens_open and _lenses.is_camera_talk(text):
        ctx["lens_open"] = True
        return None
    lens_layer = _lenses.layer_for(text, name)
    if lens_layer and ctx is not None:
        ctx["lens_n"] = ctx.get("lens_n", 0) + 1
        if ctx["lens_n"] % 2 == 1:
            ctx["lens_open"] = True
            return _scene(**lens_layer)
    ring = _lenses.ring_for(text)
    if ring:                                     # gap 5: how one lens looks -> a lens macro with a ring drawn round that lens
        return {"kind": "macro", "text": ring.pop("label"), "move": "island", "ring": ring}
    # 3. colours
    cols = [c for c in sorted(COLOURS, key=len, reverse=True) if re.search(r"(?<![a-z])" + c + r"(?![a-z])", t)]
    seen: List[str] = []
    for c in cols:
        if not any(c in s or s in c for s in seen):
            seen.append(c)
    if len(seen) >= 3 and _has(t, "colour", "colours", "color", "colors", "shades", "options"):
        order = sorted(seen, key=lambda c: t.index(c))
        if ctx is not None:
            ctx["colour_n"] = ctx.get("colour_n", 0) + 1
        if ctx is not None and ctx["colour_n"] % 2 == 1:   # colour cards (REVIEW_REFERENCE_4 gap 3); every other colour sentence keeps the colour phones
            from .swatches import cards_for
            return _scene(**cards_for(text, order, name))
        return _scene(phones=[{"label": c.title(), "color": COLOURS[c], "cams": 3} for c in order[:4]], title="Colour options")
    # 4. model lineup
    models = re.findall(r"(?:Galaxy )?S\d{2}(?: (?:Plus|Pro|Edge|Ultra|FE))?|iPhone \d+(?: (?:Pro Max|Pro|Plus|Air))?", text)
    models = [m if m.startswith(("Galaxy", "iPhone")) else "Galaxy " + m for m in models]
    uniq = list(dict.fromkeys(models))
    split = re.search(r"\b(?:while|but|whereas)\b", t)
    if len(uniq) >= 3 and split and re.search(r"won['’]t|will not|don['’]t|not get|miss out", t[split.start():]):   # "Pro and Ultra get it, while S27 and Plus won't"
        cut = split.start()
        at = {}
        for x in re.finditer(r"(?:Galaxy )?S\d{2}(?: (?:Plus|Pro|Edge|Ultra|FE))?|iPhone \d+(?: (?:Pro Max|Pro|Plus|Air))?", text):
            at.setdefault(x.group(0) if x.group(0).startswith(("Galaxy", "iPhone")) else "Galaxy " + x.group(0), x.start())
        got = [m for m in uniq if at.get(m, len(t)) < cut]
        pal = [PURPLE, DARK, "#7a2f45", "#cfc9de"]
        title = next((x.group(0).title() for x in [re.search(r"privacy display|[a-z]+ display|[a-z]+ chip|[a-z]+ camera", t)] if x), "Who gets it")
        return _scene(phones=[{"label": m, "color": pal[i % 4], "cams": 3, "badge": "Yes" if m in got else "No"} for i, m in enumerate(uniq[:4])], title=title)
    if len(uniq) >= 3 or (len(uniq) >= 2 and _has(t, "lineup", "models", "series")):
        pal = [PURPLE, DARK, "#7a2f45", "#cfc9de"]
        return _scene(phones=[{"label": m, "color": pal[i % 4], "cams": 2 + i % 3} for i, m in enumerate(uniq[:4])], title="The lineup")
    if len(uniq) == 2 and not _numbers(text) and _has(t, "than", "compared", "versus", "vs", "over", "unlike", "while", "against"):
        return _scene(phones=[{"label": uniq[0], "color": PURPLE, "cams": 4}, {"label": uniq[1], "color": DARK, "cams": 3}], title="Side by side")
    # 5. the camera module itself, a lost camera, a dropped zoom
    if _has(t, "camera bar", "camera island") and not nums and not re.search(r"\d\s*(?:x|by)\s*\d", t):
        return {"kind": "macro", "text": "Camera bar" if "bar" in t else "Camera island", "move": "island"}
    if re.search(r"\b(?:lost|lose|loses|drop|drops|one less|one fewer)\s+(?:a |one )?(?:rear\s+)?camera\b", t):
        before = next((NUMBER_WORDS[w] for w in ("four", "five", "three") if _has(t, w)), 4)
        return _scene(title="Rear cameras", phones=[{"label": "Before", "color": PURPLE, "cams": min(4, before), "text": str(before)},
                                                     {"label": name, "color": DARK, "cams": min(4, before - 1), "text": str(before - 1), "badge": "-1 camera"}])
    zm = re.search(r"\b(\d+(?:\.\d)?)x (?:telephoto|zoom)\b.*\b(dropped|removed|gone|cut|lost)\b", t)
    if zm:
        return _scene(title="Telephoto", phones=[{"label": name, "color": DARK, "cams": 3, "text": f"{zm.group(1)}x", "badge": zm.group(2).title()}])
    # 5b. camera count
    cm = re.search(r"(two|three|four|five|[2-5])\s+(?:rear\s+)?cameras?", t)
    if cm:
        n = NUMBER_WORDS[cm.group(1)]
        return _scene(phones=[{"label": name, "color": DARK, "cams": min(4, n), "text": f"{n} cameras"}], title="Camera module")
    # 6. dimensions ("163.76 x 78.25 x 7.97 mm", which Whisper writes as "163 76x78 25x7 97mm"): the size, not a before/after of two mm figures
    if re.search(r"\d\s*(?:x|by)\s*\d", t) and _has(t, "mm", "millimeters", "millimetres", "inches", "bigger", "size", "dimensions", "compared"):
        sizes = re.findall(r"(\d+(?:\.\d+)?)\s*(?:x|by|×)\s*(\d+(?:\.\d+)?)\s*(?:x|by|×)\s*(\d+(?:\.\d+)?)", t)
        if len(sizes) >= 2:                          # "163.76 by 78.25 by 7.97 millimeters, compared to 163.6 by 78.1 by 7.9": the two phones with their sizes
            other = next((m for m in uniq if m.lower() != name.lower()), "Before")
            dh = float(sizes[0][0]) - float(sizes[1][0])
            return _scene(title="Size (mm)", phones=[{"label": other, "color": PURPLE, "cams": 4, "top": " x ".join(sizes[1])},
                                                     {"label": name, "color": DARK, "cams": 3, "top": " x ".join(sizes[0]), **({"badge": f"{dh:+.2f} mm"} if dh else {})}])
        return {"kind": "macro", "text": "Dimensions", "move": "edge"}
    # 5c. battery life in hours for two screens: the battery cutaway on each phone, filled in proportion (a battery sentence is drawn as a battery)
    hrs = [n for n in nums if n["unit"] == "h"]
    if len(hrs) == 2 and _has(t, "battery", "batteries") and _has(t, "outer", "inner", "cover", "main", "front") and hrs[0]["v"] != hrs[1]["v"]:
        top = max(h["v"] for h in hrs)
        labs = ["Outer screen" if _has(t, "outer") else "Cover screen", "Inner screen" if _has(t, "inner") else "Main screen"]
        return _scene(title="Battery life", phones=[{"label": labs[i], "color": DARK, "cams": 3, "cutaway": True, "cell_from": 0.15, "cell": round(0.9 * h["v"] / top, 2),
                                                      "side": {"text": f"{h['v']:.0f} hrs", "size": 84, "sub": labs[i]}} for i, h in enumerate(hrs)])
    # 5d. "up to 35 percent better sustained performance than the iPhone 17 Pro": the claim as two bars, the old one as the baseline
    pc = re.search(r"up to (\d{1,3}) ?(?:%|percent) (better|faster|more|longer|higher|lower|less|quicker) ([a-z ]{3,34}?) than (?:the |last year['’]s )?([A-Za-z0-9 ]{3,26}?)(?:[.,;]|$)", text, re.I)
    if pc:
        n, word, what, other = int(pc.group(1)), pc.group(2).lower(), pc.group(3).strip(), pc.group(4).strip()
        sign = -1 if word in ("lower", "less") else 1
        by = re.search(r"\b(Apple|Samsung|Google|[A-Z][a-z]+) (?:says|said|claims|rates)\b", text)
        return {"kind": "bars", "title": what.upper(), "note": (f"{by.group(1).upper()}'S CLAIM, UP TO" if by else "UP TO"),
                "rows": [{"label": name.upper(), "value": 100 + sign * n, "text": f"{'+' if sign > 0 else '-'}{n}%", "highlight": True}, {"label": other.upper(), "value": 100, "text": "BASELINE"}],
                "delta": {"text": f"{'+' if sign > 0 else '-'}{n}%", "sub": "UP TO"}}
    # 5e. a score out of a maximum ("a repairability score of 5 out of 10"): the dial
    sc = re.search(r"(?:(?:a|an|the)\s+)?((?:[a-z]+\s+){0,3}?(?:score|rating))\s+of\s+(\d+(?:\.\d+)?)\s+out of\s+(\d+)", t)
    if sc and float(sc.group(3)) >= float(sc.group(2)) > 0:
        by = re.search(r"\b(iFixit|Apple|Samsung|Google|DXOMARK|[A-Z][a-z]+)\b(?= gave| rated| scored| awarded)", text)
        name_ = re.sub(r"\b(provisional)\b", "", sc.group(1)).strip().upper() or "SCORE"
        prov = " (PROVISIONAL)" if "provisional" in t else ""
        return {"kind": "gauge", "title": (name_ + prov), "unit": f"/{int(float(sc.group(3)))}", "max": float(sc.group(3)),
                "gauges": [{"label": (by.group(1).upper() if by else name), "value": float(sc.group(2)), "highlight": True}]}
    # 6a. two figures of one kind either side of the phone (REVIEW_REFERENCE_5 gap 17); every other such sentence keeps the flat scenes below
    from .sides import sides_for
    two = sides_for(text, name)
    from .sides import MODEL as _MODEL
    labelled = two and any(x["sub"] for x in two["items"]) and not any(x["value"].endswith("MP") for x in two["items"]) and not any(_MODEL.search(x["sub"]) or re.search(r"Launch|Leaked", x["sub"]) for x in two["items"])
    if two and labelled:                         # "outer screen / inner screen", "with / without AppleCare": no older scene says that (they read Previous / Now)
        return {"kind": "sides", **two}
    if two and ctx is not None:                  # without a running context (a one-off check) the older scenes below answer
        ctx["sides_n"] = ctx.get("sides_n", 0) + 1
        if ctx["sides_n"] % 2 == 1:
            return {"kind": "sides", **two}
    # 6b. prices ("dropped to $919.99 ... a $1,299.99 list price")
    prices = [x.rstrip(",") for x in re.findall(r"\$(\d[\d,]*(?:\.\d{2})?)", text)]
    if prices:
        said = re.search(r"\b(?:galaxy\s+)?s(\d{2})(?:\s+(plus|pro|edge|ultra|fe)\b)?|\biphone\s+(\d{2})(?:\s+(pro max|pro|plus|air)\b)?", t)
        lab = uniq[0] if uniq else ((f"Galaxy S{said.group(1)}" + (f" {said.group(2).title()}" if said.group(2) else "")) if said and said.group(1)
                                    else (f"iPhone {said.group(3)}" + (f" {said.group(4).title()}" if said.group(4) else "")) if said else name)
        if len(prices) >= 3:                         # a price ladder ("starts at 1,999, then 2,199, 2,599 and 3,199"): the tiers as rising bars, a storage size only where the sentence names one
            vals = [int(float(x.replace(",", ""))) if float(x.replace(",", "")).is_integer() else float(x.replace(",", "")) for x in prices[:4]]
            sto = [(m.start(), f"{m.group(1)} {'TB' if m.group(2).lower().startswith(('t')) else 'GB'}") for m in re.finditer(r"(\d+)\s*(gigabytes?|gb|terabytes?|tb)\b", t)]
            labs = [""] * len(vals)                  # a storage size only where the sentence names one: nothing is inferred for the tiers in between
            if sto:
                labs[0] = sto[0][1]
                if len(sto) > 1:
                    labs[-1] = sto[-1][1]
            return {"kind": "compare", "title": "PRICE", "unit": "$", "cols": [{"label": labs[i], "value": v, **({"highlight": True} if i == 0 else {})} for i, v in enumerate(vals)]}
        if len(prices) >= 2:
            return _scene(phones=[{"label": lab, "color": DARK, "cams": 3, "top": "Now", "text": "$" + prices[0]},          # one phone, two prices: the same body twice
                                  {"label": lab, "color": DARK, "cams": 3, "top": "List price", "text": "$" + prices[1]}], title="Price")
        return _scene(phones=[{"label": lab, "color": DARK, "cams": 3, "side": {"text": "$" + prices[0], "size": 90}}], title="Price")
    # 7. a camera list ("a 200 megapixel main camera, a 50 megapixel ultra wide"): one phone, its lenses, the headline figure
    mp = [n for n in nums if n["unit"] == "MP"]
    if len(mp) >= 2 and _has(t, "camera", "cameras", "main", "telephoto", "ultra wide", "ultrawide", "lens"):
        top = max(mp, key=lambda n: n["v"])
        return _scene(phones=[{"label": name, "color": DARK, "cams": min(4, max(3, len(mp))), "side": {"text": _fmt(top["v"], "MP"), "size": 96}}], title="Cameras")
    # 8. numbers
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
    same = [n for n in nums if n["unit"] == nums[0]["unit"]] if nums else []
    if len(same) >= 2 and _has(t, "more", "extra", "bigger", "larger") and min(same[0]["v"], same[1]["v"]) < 0.35 * max(same[0]["v"], same[1]["v"]):
        base, delta = max(same[0], same[1], key=lambda n: n["v"]), min(same[0], same[1], key=lambda n: n["v"])     # "has 5,000, so that's about 700 more"
        pct = next((n for n in nums if n["unit"] == "%"), None)
        old = next((m for m in uniq if m.lower() != name.lower()), "Before")
        cut = battery or base["unit"] == "mAh"
        badge = "+" + _fmt(delta["v"], delta["unit"]) + (f" · +{pct['v']:.0f}%" if pct else "")
        return _scene(title="Battery" if cut else "Before and now",
                      phones=[{"label": old, "color": PURPLE, "cams": 4, "top": _fmt(base["v"], base["unit"]), **({"cutaway": True, "cell": 0.7, "cell_from": 0.7} if cut else {})},
                              {"label": name, "color": DARK, "cams": 3, "top": _fmt(base["v"] + delta["v"], base["unit"]), "badge": badge, **({"cutaway": True, "cell": 0.85, "cell_from": 0.85} if cut else {})}])
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
    if len(nums) == 1 and nums[0]["unit"] != "x" and _has(t, "bigger", "larger", "more", "faster", "higher", "extra", "upgrade", "boost", "increase"):
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
        title = {"x": "Zoom", "MP": "Camera", "Hz": "Display", "W": "Charging", "mAh": "Battery", "GB": "Memory", "TB": "Storage", " nits": "Brightness"}.get(n["unit"], "")
        return _scene(phones=[{"label": name, "color": DARK, "cams": 3, "side": {"text": fig, "size": 96}}], **({"title": title} if title else {}))
    return ui_for(text) or three_d_for(text)


UI_PHRASES = [  # (phrases in the sentence, title, look tokens) -- a sentence about software gets a live interface on the phone (product_trailer/uifilm.py)
    (("control center", "control centre", "quick settings", "quick controls", "quick toggles", "toggles"), "Control Center", "ui:settings"),
    (("lock screen", "lockscreen", "always-on display", "always on display"), "Lock Screen", "ui:lock"),
    (("home screen", "homescreen", "app drawer", "app library", "dock"), "Home Screen", "ui:home"),
    (("widget", "widgets"), "Widgets", "ui:widgets"),
    (("notification", "notifications"), "Notifications", "ui:notif"),
    (("settings", "privacy controls", "focus mode", "battery saver", "power saving"), "Settings", "ui:settings"),
    (("one ui", "ios", "android", "hyperos", "oxygenos", "software update", "the software", "new interface", "redesigned interface"), "The Software", "ui:list"),
]


def ui_for(text: str) -> Optional[Dict[str, Any]]:
    """The interface scene a sentence about software calls for ({"kind": "ui" | "icon" | "wall", ...}), or None. Rows come from a spoken list
    ("Wi-Fi, Bluetooth and Focus") when there is one."""
    t = " " + re.sub(r"[^a-z0-9\- ]+", " ", text.lower()) + " "
    if _has(t, "icon", "icons") and _has(t, "app", "apps", "redesigned", "new"):
        return {"kind": "icon", "icon": "camera" if "camera" in t else "gear" if "setting" in t else "message" if "message" in t else "star", "text": "New Icons"}
    if _has(t, "wallpaper", "wallpapers", "customise", "customize", "customisation", "customization", "themes"):
        return {"kind": "wall", "text": "Make It Yours"}
    for keys, title, look in UI_PHRASES:
        if any(f" {k} " in t for k in keys):
            parts = []
            for p in re.split(r",|\band\b", text):
                p = re.split(r"\b(?:has|have|with|like|including|include|includes|adds|gets)\b", p.strip(" ."))[-1].strip(" .:")      # "the control center has Wi-Fi" -> "Wi-Fi"
                p = re.sub(r"\s+(?:toggles?|switches|controls|buttons)$", "", p, flags=re.I).strip()
                if 0 < len(p.split()) <= 3:
                    parts.append(p)
            rows = [p[0].upper() + p[1:] for p in parts][:5] if len(parts) >= 2 else []
            return {"kind": "ui", "title": title, "rows": rows, "look": look}
    return None


CHIP_NAME = re.compile(r"(Snapdragon 8 Elite(?: Extreme)?(?: Gen \d)?|Exynos \d{4}|Dimensity \d{4}|Tensor G\d|A\d{2} Pro|A\d{2})")
_NUMWORD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def _chips_in(text: str) -> List[str]:
    """The distinct chip names in a sentence, in spoken order (the longest form of each: 'Snapdragon 8 Elite Extreme Gen 6' over 'Snapdragon 8 Elite')."""
    found: List[str] = []
    for m in CHIP_NAME.finditer(text):
        n = m.group(1)
        if not any(n in f or f in n for f in found):
            found.append(n)
        else:
            found = [n if (f in n) else f for f in found]
    return list(dict.fromkeys(found))


def body_figure(text: str, name: str) -> Optional[Dict[str, Any]]:
    """A sentence that states one body measure ("the thickness should stay at 7.9 millimetres", "four grams heavier than the S26 Ultra"): the figure large
    beside the phone, with what it measures under it. Only what the sentence says."""
    t = text.lower()
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:millimet(?:re|er)s?|mm)\b", t)
    if m and _has(t, "thick", "thin", "thickness"):
        return _scene(phones=[{"label": name, "color": DARK, "cams": 3, "side": {"text": f"{m.group(1)}mm", "size": 96, "sub": "Thickness"}}], title="Thickness")
    g = re.search(r"\b(\d+(?:\.\d+)?|" + "|".join(_NUMWORD) + r")\s+grams?\s+(heavier|lighter)\b", t)
    if g:
        v = g.group(1)
        n = _NUMWORD.get(v) or float(v)
        sign = "+" if g.group(2) == "heavier" else "-"
        return _scene(phones=[{"label": name, "color": DARK, "cams": 3, "side": {"text": f"{sign}{n:g}g", "size": 96, "sub": g.group(2).title() + " than before"}}], title="Weight")
    return None


def three_d_for(text: str) -> Optional[Dict[str, Any]]:
    """The 3D shot a sentence about the phone's inside, hinge, chip, camera, display or frame calls for, or None."""
    t = text.lower()
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
    ctx: Dict[str, Any] = {"unit": None, "topic": None}      # what the sentences so far were about: a bare "5,000" after a mAh sentence is mAh
    for ch in out["chapters"]:
        items: List[Dict[str, Any]] = []
        placed = False                              # a directive written by the author sits right before the line it belongs to
        for it in ch["items"]:
            if it["kind"] != "line":
                items.append(it)
                placed = True
                continue
            said = spoken_numbers(it["text"])
            topic = topic_of(said)
            if topic and topic != ctx["topic"]:
                ctx["unit"] = None if ctx["topic"] else ctx["unit"]
                ctx["topic"] = topic
            pick = None if placed else scene_for(it["text"], phone, ctx)
            units = [n["unit"] for n in _numbers(said) if n["unit"] in ("mAh", "MP", "W", "Hz", "GB", "TB")]
            if units:
                ctx["unit"] = units[-1]
            if pick:
                key = repr(pick)
                if key != last_key:
                    items.append(pick)
                    last_key = key
            items.append(it)
            placed = False
        ch["items"] = items
    return out
