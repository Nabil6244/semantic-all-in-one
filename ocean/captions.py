"""Ocean captions (docs/ocean/PATTERNS.md section 4, plan step 3): not subtitles. Each spoken clause may get one short
phrase on screen: up to two small white lead words and one KEY span in bold capitals, orange (numbers, superlatives,
quantities, emphasis) or red (danger words). e.g. "only A FEW", "THE BIGGEST", "12 MILLION YEARS", "WIPING OUT", "too BIG?".

    words_from_text(text, start, end)                -> [(word, t0, t1)]   even spread when no word timings exist
    plan(words, chapters=(), every_s=5.0)            -> [caption dict]      which clause gets which phrase, and when
    lay_captions(t, dur, {"items": plan(...)})       -> RGBA W x H          the layer (pop in, hold, fade out)

The key is picked by the shape of the clause, never by topic: a number (+ its unit) beats a superlative, which beats a
danger word, a quantity or an emphasis word; a clause with none of these only gets a caption (its last content words)
when nothing has been on screen for `every_s` seconds. The first caption of a chapter sits at the top, the rest at the
bottom. A caption never overlaps the next one and holds 1.0-3.2 s.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter

from . import look as L

W, H = L.W, L.H
Word = Tuple[str, float, float]

MIN_HOLD, MAX_HOLD, GAP = 1.0, 3.2, 0.05
POP_S, FADE_S = 0.18, 0.2

NUM_WORDS = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "fifteen",
             "twenty", "thirty", "forty", "fifty", "hundred", "hundreds", "thousand", "thousands", "million", "millions",
             "billion", "billions", "dozen", "dozens", "half"}
SCALE_WORDS = {"hundred", "hundreds", "thousand", "thousands", "million", "millions", "billion", "billions", "percent",
               "times", "x"}
UNITS = {"m", "km", "cm", "mm", "kg", "tons", "tonnes", "ton", "tonne", "meters", "metres", "meter", "metre", "feet", "ft",
         "miles", "mph", "km/h", "years", "year", "days", "hours", "minutes", "seconds", "teeth", "times", "percent",
         "degrees", "lb", "lbs", "pounds", "calories", "sharks", "whales", "orcas", "seals", "less", "more", "bigger",
         "longer", "heavier", "faster", "deeper", "older", "km", "attacks", "kills", "people"}
QUANTITY = {"few", "many", "most", "all", "none", "zero", "every", "half", "nobody", "nothing", "no", "only"}
EMPHASIS = {"except", "never", "nothing", "nobody", "always", "same", "real", "myth", "twin", "first", "last", "alone",
            "everything", "anything", "itself", "free", "fight", "back", "bigger", "smaller", "slower", "faster",
            "colder", "deeper", "darker", "patient", "hidden", "invisible", "secret", "wrong", "awkward", "scary"}
DANGER = {"kill", "kills", "killed", "killing", "killer", "dead", "die", "dies", "died", "death", "deadly", "deadliest", "gone",
          "vanish", "vanished", "vanishes", "flee", "fled", "flees", "fleeing", "attack", "attacks", "attacked", "bite", "bit",
          "bitten", "bites", "extinct", "extinction", "blood", "bleeding", "terrified", "terrifying", "afraid", "scared",
          "nightmare", "nightmares", "panic", "wiping", "wiped", "destroy", "destroyed", "torn", "ripped", "crushed",
          "eaten", "hunted", "ambush", "fear", "feared", "run", "ran", "flee", "escape", "escaped", "target", "hot"}
NOT_SUPERLATIVE = {"interest", "forest", "honest", "west", "rest", "test", "nest", "chest", "harvest", "guest", "request",
                   "suggest", "protest", "contest", "invest", "arrest", "modest", "digest", "manifest", "quest", "pest",
                   "best"}  # "best" is a superlative but a weak one; kept out so "the best way" does not shout
STOP = {"a", "an", "the", "and", "or", "but", "so", "of", "to", "in", "on", "at", "for", "with", "by", "from", "as", "is", "are",
        "was", "were", "be", "been", "it", "its", "it's", "this", "that", "these", "those", "they", "them", "their", "you",
        "your", "we", "our", "he", "she", "his", "her", "i", "me", "my", "just", "really", "very", "about", "like", "into",
        "than", "then", "there", "here", "what", "which", "who", "when", "where", "why", "how", "do", "does", "did", "can",
        "could", "would", "should", "will", "has", "have", "had", "not", "if", "up", "out", "even", "also", "some", "any",
        "one", "get", "got", "around", "over", "under", "because", "while"}
CLAUSE_BREAK = {"and", "but", "so", "because", "which", "who", "when", "while", "until", "except"}
LEAD_KEEP = {"only", "up", "to", "about", "around", "too", "almost", "nearly", "over", "under", "than", "no", "not", "even",
             "just", "never", "so", "very", "really", "every", "all", "one"}
SCORE = {"number": 5, "superlative": 4, "danger": 4, "quantity": 3, "emphasis": 2, "last": 1}


# ------------------------------------------------------------------------------------------------------------------ words

def _norm(w: str) -> str:
    return re.sub(r"[^\w%/+.\-']", "", w.lower()).strip(".'-")


def words_from_text(text: str, start: float, end: float) -> List[Word]:
    """Even spread of words over [start, end] by character length (used when no word timings exist)."""
    toks = text.split()
    if not toks:
        return []
    total = sum(len(t) + 1 for t in toks)
    out, t = [], float(start)
    span = max(0.01, float(end) - float(start))
    for tok in toks:
        d = span * (len(tok) + 1) / total
        out.append((tok, t, t + d))
        t += d
    return out


def as_words(words: Iterable[Any]) -> List[Word]:
    """Accept (word, start, end) tuples or {"word"/"text", "start", "end"} dicts."""
    out: List[Word] = []
    for w in words:
        if isinstance(w, dict):
            out.append((str(w.get("word") or w.get("text") or ""), float(w.get("start", 0)), float(w.get("end", 0))))
        else:
            out.append((str(w[0]), float(w[1]), float(w[2])))
    return [w for w in out if w[0].strip()]


def clauses(words: Sequence[Word], max_words: int = 12) -> List[List[Word]]:
    out: List[List[Word]] = []
    cur: List[Word] = []
    for w in words:
        lw = _norm(w[0])
        if cur and lw in CLAUSE_BREAK and len(cur) >= 4:
            out.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.,;:?!]$", w[0].strip()) or len(cur) >= max_words:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


# ------------------------------------------------------------------------------------------------------------------ keys

def _is_num(lw: str) -> bool:
    return bool(re.match(r"^~?\d", lw)) or lw in NUM_WORDS


def _is_super(lw: str) -> bool:
    return (len(lw) > 4 and lw.endswith("est") and lw not in NOT_SUPERLATIVE) or lw in ("most", "least")


def key_span(clause: Sequence[Word]) -> Optional[Tuple[int, int, str, int]]:
    """(first index, last index exclusive, kind, score) of the clause's key words, or None for an empty clause."""
    ws = [_norm(w[0]) for w in clause]
    cands: List[Tuple[int, int, int, str]] = []          # (score, i, j, kind)
    i = 0
    while i < len(ws):
        lw = ws[i]
        if _is_num(lw) and lw != "one":
            j = i + 1
            if i > 0 and ws[i - 1] in ("few", "several", "many", "tens", "hundreds") and lw in SCALE_WORDS:
                i -= 1                                                   # "a FEW HUNDRED METERS"
                if i > 0 and ws[i - 1] == "a":
                    i -= 1
            while j < len(ws) and j - i < 4 and (ws[j] in SCALE_WORDS or ws[j] in UNITS or _is_num(ws[j])
                                                 or (ws[j] in ("to", "and", "or") and j + 1 < len(ws) and _is_num(ws[j + 1]))):
                j += 1                                                   # "300 teeth", "12 million years", "3 to 4 m"
            spelled = all(not re.match(r"^~?\d", x) for x in ws[i:j]) and not any(x in SCALE_WORDS for x in ws[i:j])
            if spelled:
                cands.append((SCORE["number"] - 2, i, j, "number"))      # "two orcas" is weaker than "300 teeth" or a danger word
            else:
                cands.append((SCORE["number"], i, j, "number"))
            i = j
            continue
        if lw in ("most", "least") and not (i > 0 and ws[i - 1] == "the"):
            pass                                                         # "most people" is not "the most feared"
        elif _is_super(lw):
            j = i + 1
            if lw in ("most", "least") and j < len(ws) and ws[j] not in STOP:
                j += 1                                                   # "most FEARED"
            a = i - 1 if i > 0 and ws[i - 1] == "the" else i
            cands.append((SCORE["superlative"], a, j, "superlative"))
        elif lw in DANGER:
            j = i + 1
            if j < len(ws) and ws[j] in ("out", "away", "off"):
                j += 1
            cands.append((SCORE["danger"], i, j, "danger"))
        elif lw in QUANTITY and lw not in ("only", "no", "every", "all"):
            a = i - 1 if i > 0 and ws[i - 1] in ("a", "the") else i
            cands.append((SCORE["quantity"], a, i + 1, "quantity"))
        elif lw in EMPHASIS:
            cands.append((SCORE["emphasis"], i, i + 1, "emphasis"))
        elif i > 0 and lw not in STOP and clause[i][0][:1].isupper():
            j = i + 1                                                    # a name said mid-clause: "FARALLON ISLANDS", "CALIFORNIA"
            while j < len(ws) and j - i < 3 and clause[j][0][:1].isupper():
                j += 1
            cands.append((SCORE["emphasis"], i, j, "name"))
            i = j
            continue
        i += 1
    if not cands:
        content = [k for k, lw in enumerate(ws) if lw and lw not in STOP and not lw.isdigit()]
        if not content:
            return None
        j = content[-1] + 1
        a = content[-2] if len(content) > 1 and content[-2] == content[-1] - 1 else content[-1]
        return a, j, "last", SCORE["last"]
    sc, a, b, kind = max(cands, key=lambda c: (c[0], c[1]))
    return a, b, kind, sc


def caption_for(clause: Sequence[Word]) -> Optional[Dict[str, Any]]:
    ks = key_span(clause)
    if ks is None:
        return None
    a, b, kind, score = ks
    raw = [w[0] for w in clause]
    lead_i = max(0, a - 2)
    lead = [re.sub(r"[^\w'%\-]", "", x).lower() for x in raw[lead_i:a]]
    lead = [x for x in lead if x]
    while lead and _norm(lead[0]) in (STOP | CLAUSE_BREAK) and _norm(lead[0]) not in LEAD_KEEP:
        lead = lead[1:]                                                  # "is a 5-METER" -> "5-METER"; "about" stays
    key_raw = " ".join(raw[a:b])
    q = "?" if raw[b - 1].rstrip().endswith("?") or (b == len(raw) and raw[-1].rstrip().endswith("?")) else ""
    key = re.sub(r"[^\w%~+.\-/' ]", "", key_raw).strip(" .-'").upper() + q
    if not key.strip("?"):
        return None
    return {"t0": clause[a][1], "lead": " ".join(lead), "key": key, "kind": kind, "score": score,
            "color": "red" if kind == "danger" else "orange", "clause_end": clause[-1][2], "clause_start": clause[0][1]}


# ------------------------------------------------------------------------------------------------------------------ plan

def plan(words: Iterable[Any], chapters: Sequence[float] = (), every_s: float = 5.0, min_score: int = 2) -> List[Dict[str, Any]]:
    """Captions for a narration: [{t0, t1, lead, key, color, pos, kind}] in time order, never overlapping."""
    ws = as_words(words)
    chap = sorted(float(c) for c in chapters)
    items: List[Dict[str, Any]] = []
    last_end = 0.0                                  # a weak clause at the very start waits too ("Picture this.")
    for cl in clauses(ws):
        c = caption_for(cl)
        if c is None:
            continue
        lead_t = max(c["clause_start"], c["t0"] - 0.6) if c["lead"] else c["t0"]
        start = max(0.0, lead_t - 0.1)
        if c["score"] < min_score and start - last_end < every_s:
            continue
        if items and start < items[-1]["t0"] + MIN_HOLD + GAP:
            if c["score"] <= items[-1]["score"]:
                continue
            items.pop()                                             # a stronger key replaces a weak one right before it
        c["t0"] = start
        items.append(c)
        last_end = c["clause_end"]
    for k, c in enumerate(items):
        nxt = items[k + 1]["t0"] - GAP if k + 1 < len(items) else 1e9
        end = min(max(c["clause_end"] + 0.3, c["t0"] + MIN_HOLD), c["t0"] + MAX_HOLD, nxt)
        c["t1"] = round(max(c["t0"] + 0.3, end), 3)
        c["t0"] = round(c["t0"], 3)
        first_in_chapter = any(ch <= c["t0"] and (k == 0 or items[k - 1]["t0"] < ch) for ch in chap)
        c["pos"] = "top" if first_in_chapter and c["kind"] != "number" else "bottom"
        for x in ("clause_end", "clause_start"):
            c.pop(x, None)
    return items


# ------------------------------------------------------------------------------------------------------------------ render

def _colour(name: str) -> Tuple[int, ...]:
    return L.RED if name == "red" else L.ORANGE


@lru_cache(maxsize=128)
def _text_image(key_json: str) -> Image.Image:
    c = json.loads(key_json)
    sc = L.scale()
    fk = L.font("heavy", int(c.get("size") or 40))
    fl = L.font("regular", int(int(c.get("size") or 40) * 0.72))
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lead = c.get("lead", "")
    key = c.get("key", "")
    gap = 10 * sc if lead else 0
    wl = probe.textlength(lead, font=fl) if lead else 0
    wk = probe.textlength(key, font=fk)
    pad = int(18 * sc)
    w, h = int(wl + gap + wk + 2 * pad), int(fk.size * 1.5 + 2 * pad)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    txt = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(txt)
    base = pad + fk.size * 1.05                                 # shared baseline
    if lead:
        d.text((pad, base), lead, font=fl, fill=L.SOFT, anchor="ls")
    d.text((pad + wl + gap, base), key, font=fk, fill=_colour(c.get("color", "orange")), anchor="ls")
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow.putalpha(txt.getchannel("A").filter(ImageFilter.GaussianBlur(6 * sc)).point(lambda v: v * 150 // 255))
    img.alpha_composite(shadow, (0, int(2 * sc)))
    img.alpha_composite(txt)
    return img


def caption_image(item: Dict[str, Any]) -> Image.Image:
    return _text_image(json.dumps({k: item.get(k) for k in ("lead", "key", "color", "size")}, sort_keys=True))


def lay_captions(t: float, dur: float, p: Dict[str, Any]) -> Optional[Image.Image]:
    live = [c for c in p.get("items") or [] if float(c["t0"]) <= t < float(c["t1"])]
    if not live:
        return None
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sc = L.scale()
    for c in live:
        im = caption_image(c)
        k_in = (t - float(c["t0"])) / POP_S
        k_out = (float(c["t1"]) - t) / FADE_S
        alpha = max(0.0, min(1.0, k_in, k_out))
        s = 0.86 + 0.14 * min(1.0, max(0.0, k_in))
        if s < 0.999:
            im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.BILINEAR)
        if alpha < 0.999:
            im = im.copy()
            im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
        cy = (70 if c.get("pos") == "top" else 655) * sc
        canvas.alpha_composite(im, (int(W / 2 - im.width / 2), int(cy - im.height / 2)))
    return canvas


CARDS = {"ocean.lay_captions": lay_captions}
