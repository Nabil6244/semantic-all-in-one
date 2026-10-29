"""Shot director: turns scenes (script + timings) into a shot list.

Offline, deterministic (per seed), no network. See docs/story/shot_director.md
for the schema and the honest limits.

    plan = plan_shots(scenes, words=None, settings=None, log=print)
    rows = to_csv_rows(plan);  plan2 = from_csv_rows(rows)
"""
from __future__ import annotations

import hashlib
import math
import random
import re
import unicodedata

DEFAULTS = {
    "seed": 0,
    "target_len": 3.2,          # preferred shot length (s)
    "min_len": 1.8,
    "max_len": 5.0,
    "max_new_ratio": 1.8,       # new pictures <= ratio * number of scenes (soft: max_same_pic may add more)
    "max_same_pic": 6.0,        # one picture may stay on screen at most this long (s); the shot that would cross it gets a new picture
    "ai_video_ratio": 0.22,     # share of shots that may be ai_video
    "link_ratio": 0.20,         # share of shots that may start a link
    "graphic_ratio": 0.12,
    "allow_puppet": False,
    "puppet_ratio": 0.05,
    "close_gaps": True,         # split inter-scene silences between neighbours
    "max_gap_close": 4.0,
    "protagonist": None,        # dict(name, look) to force one
    "refine": None,             # optional callable(plan)->plan (e.g. an LLM); off by default
}

STYLE_EN = ("engraved sepia paper-collage illustration, halftone shading, white cut-out "
            "outline, torn cream parchment background, muted sepia and terracotta palette")
NO_TEXT = "no text, no letters, no logos"

CAMERAS = ("push_in", "pull_out", "drift_l", "drift_r", "diag", "hold_alive")
TRANSITIONS = ("cut", "match_cut", "torn_wipe", "doorway_push", "dissolve", "whip")


# ----------------------------------------------------------------- text utils
def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    s = s.replace("़", "").replace("ँ", "ं")
    return unicodedata.normalize("NFC", s).lower()


def _stem_re(stems):
    return re.compile(r"(?<![ऀ-ॿa-z0-9])(?:" + "|".join(re.escape(norm(x)) for x in stems) + ")")


_DEV = "ऀ-ॿ"

# (key, stems, visual_en, kind, scale)   kind: place|object|person|vehicle|abstract
_LEX_RAW = [
    ("warehouse", ("गोदाम", "warehouse", "fulfilment", "fulfillment"), "a vast windowless warehouse with towering shelves and loading dock doors", "place", "wide"),
    ("plane", ("विमान", "हवाई जहाज", "जहाज", "plane", "cargo jet", "flight"), "a cargo plane on a night runway", "vehicle", "wide"),
    ("van", ("वैन", "van "), "a delivery van turning into a quiet street", "vehicle", "wide"),
    ("truck", ("ट्रक", "truck", "लॉरी"), "a freight truck on a highway", "vehicle", "wide"),
    ("parcel", ("पार्सल", "डिब्बा", "डिब्बे", "डिब्बों", "पैकेज", "parcel", "package", "carton"), "a plain cardboard parcel", "object", "close"),
    ("shelf", ("शेल्फ", "शेल्फ़", "रैक", "shelf", "shelves"), "a tall shelf of boxes", "object", "mid"),
    ("robot", ("रोबोट", "robot"), "a low flat warehouse robot lifting a shelf", "object", "mid"),
    ("scanner", ("स्कैन", "scanner"), "a handheld barcode scanner", "object", "close"),
    ("worker", ("कर्मचारी", "मज़दूर", "मजदूर", "कामगार", "worker", "employee"), "a worker", "person", "mid"),
    ("person", ("आदमी", "इंसान", "व्यक्ति", "क्लर्क", "clerk", "वकील", "पत्रकार", "लड़का", "लड़की", "बच्चा", "बच्चे", "माँ ", "महिला", "ग्राहक", "courier", "driver"), "a person", "person", "mid"),
    ("shop", ("दुकान", "स्टोर", "shop", "store", "बुकस्टोर", "bookstore"), "a small old storefront", "place", "mid"),
    ("book", ("किताब", "पुस्तक", "book"), "a stack of old books", "object", "close"),
    ("garage", ("गैरेज", "garage"), "a cluttered suburban garage with a workbench", "place", "mid"),
    ("map", ("नक्शे", "नक्शा", "नक्श", "map"), "a torn parchment map with a dashed route", "object", "mid"),
    ("dot", ("बिंदु", "dot"), "a single glowing red dot on a dashed route", "object", "close"),
    ("building", ("इमारत", "building", "टावर", "मुख्यालय", "headquarters"), "an enormous flat-roofed building", "place", "wide"),
    ("football", ("फ़ुटबॉल", "फुटबॉल", "football"), "small football pitches outlined beside it for scale", "object", "wide"),
    ("clock", ("घड़ी", "घंटे", "घंटा", "clock", "hour"), "an engraved round wall clock", "object", "close"),
    ("bell", ("घंटी", "bell"), "a brass bell", "object", "close"),
    ("napkin", ("नैपकिन", "napkin"), "a paper napkin with a pencil sketch", "object", "close"),
    ("stock", ("शेयर", "बाज़ार", "बाजार", "stock", "market", "बॉन्ड", "bond"), "a vintage stock-exchange board silhouette and ticker tape", "place", "mid"),
    ("money", ("डॉलर", "कमाई", "मुनाफ़ा", "मुनाफा", "घाटे", "घाटा", "पैसे", "क़ीमत", "कीमत", "dollar", "profit", "revenue"), "gold coins pouring into an overflowing wooden chest", "object", "close"),
    ("company", ("कंपनी", "company"), "a row of identical brick office fronts", "place", "wide"),
    ("catalog", ("कैटलॉग", "catalog", "catalogue"), "a thick mail-order catalogue", "object", "close"),
    ("home", ("घरों", "घर ", "गली", "दरवाज़े", "दरवाजे", "दरवाज़ा", "doorstep", "door"), "a front door on a quiet street at night", "place", "mid"),
    ("phone", ("मोबाइल", "फ़ोन", "फोन", "ट्रैकिंग", "ट्रेकिंग", "ऑर्डर", "phone", "tracking", "order"), "a hand holding a phone showing a tracking page", "object", "close"),
    ("army", ("सेना", "army", "सैनिक"), "ranks of identical soldier silhouettes", "place", "wide"),
    ("ranch", ("रैंच", "मवेशी", "ranch", "cattle"), "a dusty cattle ranch under a wide sky", "place", "wide"),
    ("car", ("गाड़ी", "कार ", "car "), "an old car on a dirt road", "vehicle", "mid"),
    ("bicycle", ("साइकिल", "bicycle", "bike"), "an old bicycle leaning on a wall", "object", "mid"),
    ("wedding", ("शादी", "wedding", "विवाह"), "a modest wedding portrait frame", "object", "close"),
    ("court", ("अदालत", "court"), "a courtroom bench", "place", "mid"),
    ("newspaper", ("अख़बार", "अखबार", "newspaper"), "a folded newspaper", "object", "close"),
    ("computer", ("कंप्यूटर", "वेबसाइट", "इंटरनेट", "website", "internet", "computer"), "an early beige computer on a desk", "object", "mid"),
    ("hospital", ("अस्पताल", "hospital"), "a hospital corridor", "place", "mid"),
    ("rocket", ("रॉकेट", "rocket"), "a rocket on a launch pad", "vehicle", "wide"),
    ("city", ("शहर", "city", "सड़क", "street"), "a dense city street seen from above", "place", "wide"),
    ("night", ("रात", "night"), "a night sky", "abstract", "mid"),
]
LEX = [(k, _stem_re(st), vis, kind, scale) for (k, st, vis, kind, scale) in _LEX_RAW]
LEX_BY_KEY = {k: (vis, kind, scale) for (k, _r, vis, kind, scale) in LEX}

# (stems, english action, journey?, strong action?)
_VERB_RAW = [
    (("स्कैन",), "scanning a parcel with a handheld scanner", False, True),
    (("उठा",), "lifting a box", False, True),
    (("चढ़", "चढ"), "climbing aboard", True, True),
    (("निकल",), "walking out through the doors", True, True),
    (("पहुँच", "पहुंच", "पहुंचत"), "arriving at a doorstep", True, True),
    (("मुड़", "मुड"), "turning a corner", True, True),
    (("रेंग",), "creeping along a route", True, True),
    (("चल ", "चलत", "चलता", "चलती", "चले"), "walking steadily", True, True),
    (("जात", "जाता", "जाती"), "heading off", True, True),
    (("भाग", "दौड़"), "running", True, True),
    (("उड़",), "flying", True, True),
    (("खोल",), "opening it", False, True),
    (("सोच",), "standing and thinking", False, False),
    (("देख", "दिखाई"), "looking at it", False, False),
    (("बेच",), "selling", False, True),
    (("बना", "बनाए"), "building something by hand", False, True),
    (("लिख",), "writing", False, True),
    (("काम कर", "काम करत"), "working", False, True),
    (("पकड़",), "holding it", False, True),
    (("रख", "डाल"), "putting a box down", False, True),
    (("शुरू", "शुरुआत"), "setting out", False, False),
]
VERBS = [(_stem_re(st), act, jn, strong) for (st, act, jn, strong) in _VERB_RAW]

_NUM_RE = re.compile(r"\d|%|प्रतिशत|ट्रिलियन|बिलियन|मिलियन|अरब|करोड़|करोड|लाख|हज़ार|हजार|trillion|billion|million|percent")
_YEAR_RE = re.compile(r"\b(1[5-9]\d\d|20\d\d)\b")
_WHIP_CUES = _stem_re(("फिर", "अचानक", "तभी", "तुरंत", "then", "suddenly"))
_TIME_CUES = _stem_re(("साल", "वर्ष", "दशक", "बाद", "पहले", "तब", "जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून",
                       "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर", "कुछ ही", "आज", "later", "years"))

_STRONG_CONN = {norm(x) for x in ("और", "लेकिन", "परंतु", "मगर", "जब", "फिर", "क्योंकि", "तब", "इसलिए", "जबकि",
                                  "ताकि", "तो", "अब", "but", "and", "when", "then", "because")}
_MID_CONN = {norm(x) for x in ("जो", "जहाँ", "जहां", "कि", "जिसमें", "जिसने", "जिसके", "जिसकी", "जिस", "जिन",
                               "या", "while", "which", "where")}
_SENT_END = "।.?!…"
_COMMA = ",;:،—–"


def _strip_punct(t):
    return t.strip("\"'“”‘’()[]{}«».,;:!?।…—–-،")


def _tokens(text):
    return str(text or "").split()


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "x"


def _suffix(k):
    out = ""
    k += 1
    while k:
        k, r = divmod(k - 1, 26)
        out = chr(97 + r) + out
    return out


def _f(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


# --------------------------------------------------------------- scene input
def _scene_no(s, i):
    for k in ("scene_no", "scene_number", "scene"):
        if s.get(k) not in (None, ""):
            try:
                return int(s[k])
            except (TypeError, ValueError):
                pass
    return i + 1


def _normalise_scenes(scenes, words):
    out = []
    t = 0.0
    for i, s in enumerate(scenes or []):
        text = str(s.get("script_segment") or s.get("text") or "")
        st, en = s.get("start"), s.get("end")
        try:
            st = float(st)
        except (TypeError, ValueError):
            st = None
        try:
            en = float(en)
        except (TypeError, ValueError):
            en = None
        if st is None:
            st = t
        if en is None or en <= st:
            dur = _f(s.get("duration"), 0.0) or max(1.8, len(_tokens(text)) * 0.42)
            en = st + dur
        t = en
        out.append({"no": _scene_no(s, i), "text": text, "prompt": str(s.get("prompt") or s.get("prompt_en") or ""),
                    "start": st, "end": en, "o_start": st, "o_end": en})
    return out


def _close_gaps(sc, words, cfg):
    if not cfg["close_gaps"] or not sc:
        return
    for a, b in zip(sc, sc[1:]):
        gap = b["start"] - a["end"]
        if 0 < gap <= cfg["max_gap_close"]:
            mid = a["end"] + gap / 2
            a["end"] = b["start"] = mid
    if words:
        try:
            if words[0][1] < sc[0]["start"] and sc[0]["start"] - words[0][1] <= 6.0:
                sc[0]["start"] = max(0.0, float(words[0][1]))
        except (TypeError, ValueError, IndexError):
            pass


def _token_times(sc, words):
    """Per token (start, end). Words only guide timing by character-proportion,
    so spelling differences between script and transcript do not matter."""
    toks = _tokens(sc["text"])
    n = len(toks)
    if n == 0:
        return toks, []
    lo, hi = sc["o_start"] - 0.3, sc["o_end"] + 0.3
    win = []
    for w in words or []:
        try:
            ws, we = float(w[1]), float(w[2])
        except (TypeError, ValueError, IndexError):
            continue
        if lo <= (ws + we) / 2 <= hi:
            win.append((str(w[0]), ws, we))
    clen = [max(1, len(_strip_punct(t))) for t in toks]
    tot = float(sum(clen))
    if len(win) >= max(3, 0.4 * n):
        wlen = [max(1, len(w[0])) for w in win]
        wt = float(sum(wlen))
        # cumulative char fraction at the *end* of each window word -> its end time
        xs, ys = [0.0], [win[0][1]]
        acc = 0
        for (w, ws, we), l in zip(win, wlen):
            acc += l
            xs.append(acc / wt)
            ys.append(we)

        def at(f):
            f = min(max(f, 0.0), 1.0)
            for k in range(1, len(xs)):
                if f <= xs[k]:
                    span = xs[k] - xs[k - 1] or 1e-9
                    return ys[k - 1] + (ys[k] - ys[k - 1]) * (f - xs[k - 1]) / span
            return ys[-1]
    else:
        a, b = sc["o_start"], sc["o_end"]

        def at(f):
            return a + (b - a) * min(max(f, 0.0), 1.0)
    out = []
    acc = 0.0
    for l in clen:
        out.append((at(acc / tot), at((acc + l) / tot)))
        acc += l
    return toks, out


# ---------------------------------------------------------- phrase splitting
def _boundary_strength(toks):
    """strength[p] for a cut placed before token p (1..n-1)."""
    n = len(toks)
    s = [0.0] * (n + 1)
    for p in range(1, n):
        prev, cur = toks[p - 1], toks[p]
        st = 0.0
        if prev and prev[-1] in _SENT_END:
            st = 3.0
        elif prev and prev[-1] in _COMMA:
            st = 2.0
        c = norm(_strip_punct(cur))
        if c in _STRONG_CONN:
            st = max(st, 1.5)
        elif c in _MID_CONN:
            st = max(st, 1.0)
        s[p] = st
    return s


def split_scene(sc, words, cfg):
    """Return [(tok_a, tok_b, t0, t1)] covering the scene."""
    toks, tt = _token_times(sc, words)
    n = len(toks)
    a0, b0 = sc["start"], sc["end"]
    if n == 0:
        return toks, [(0, 0, a0, b0)]
    dur = b0 - a0
    if dur < 2 * cfg["min_len"] or n < 2:
        return toks, [(0, n, a0, b0)]
    T = [a0] * (n + 1)
    T[n] = b0
    for p in range(1, n):
        lo, hi = tt[p - 1][1], tt[p][0]
        T[p] = min(max((lo + hi) / 2 if hi >= lo else hi, a0), b0)
    for p in range(1, n + 1):  # monotone
        T[p] = max(T[p], T[p - 1])
    st = _boundary_strength(toks)
    tgt, mn, mx = cfg["target_len"], cfg["min_len"], cfg["max_len"]

    def cost(a, b):
        d = T[b] - T[a]
        if d < mn:
            c = 40 * (mn - d) ** 2 + 5
        elif d > mx:
            c = 20 * (d - mx) ** 2 + 5
        else:
            c = 6 * ((d - tgt) / tgt) ** 2
        if b - a < 3 and n >= 6:
            c += 2.5 * (3 - (b - a))   # avoid one/two-word fragments
        return c + 0.6 - (2.5 * st[b] if b < n else 0.0)

    INF = float("inf")
    best = [INF] * (n + 1)
    prev = [-1] * (n + 1)
    best[0] = 0.0
    for b in range(1, n + 1):
        for a in range(b):
            if best[a] == INF or T[b] - T[a] > 2.5 * mx:
                continue
            c = best[a] + cost(a, b)
            if c < best[b]:
                best[b], prev[b] = c, a
    if best[n] == INF:
        return toks, [(0, n, a0, b0)]
    cuts = []
    b = n
    while b > 0:
        cuts.append((prev[b], b))
        b = prev[b]
    cuts.reverse()
    return toks, [(a, b, T[a], T[b]) for a, b in cuts]


# ----------------------------------------------------------------- analysis
def concepts_in(text):
    """Distinct lexicon keys in order of appearance."""
    t = norm(text) + " "
    hits = []
    for key, rx, vis, kind, scale in LEX:
        m = rx.search(t)
        if m:
            hits.append((m.start(), key))
    hits.sort()
    seen, out = set(), []
    for _p, k in hits:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def _verb_in(text):
    t = norm(text) + " "
    best = None
    for rx, act, jn, strong in VERBS:
        m = rx.search(t)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), act, jn, strong)
    return best[1:] if best else (None, False, False)


def _scene_subject(prompt):
    p = str(prompt or "")
    cut = re.split(r",\s*(?:engraved|halftone|torn|cut-out|aged|sepia|muted|white|tape|cream|vintage)\b", p, maxsplit=1,
                   flags=re.I)[0]
    cut = re.sub(r"^(?:vintage|engraved|aerial|torn-paper|collage|woodcut-style)[^a-z]*(?:paper-)?(?:collage )?"
                 r"(?:illustration|scene|woodcut-style collage)?\s*(?:of|inside)?\s*", "", cut, flags=re.I)
    return cut.strip(" ,.") or p[:80]


def _choose_protagonist(sc_all_text, forced):
    if forced and isinstance(forced, dict) and forced.get("name") and forced.get("look"):
        name, look = forced["name"], forced["look"]
    else:
        t = norm(sc_all_text)
        themes = [
            ("Night-shift warehouse worker", ("गोदाम", "पार्सल", "डिब्बे", "warehouse", "parcel", "delivery", "शेल्फ"),
             "a faceless sepia paper-collage silhouette of a lean night-shift warehouse worker in a flat cap, "
             "a high-collar work coat, rolled sleeves and heavy boots, a handheld scanner on his belt, white cut-out outline"),
            ("Doctor", ("अस्पताल", "डॉक्टर", "मरीज", "hospital", "patient"),
             "a faceless sepia paper-collage silhouette of a calm doctor in a long white coat with a stethoscope, white cut-out outline"),
            ("Farmer", ("खेत", "किसान", "फसल", "farm"),
             "a faceless sepia paper-collage silhouette of a farmer in a wide straw hat and patched overalls, white cut-out outline"),
            ("Soldier", ("सेना", "युद्ध", "सैनिक", "war", "army"),
             "a faceless sepia paper-collage silhouette of a soldier in a greatcoat and helmet, white cut-out outline"),
            ("Astronaut", ("अंतरिक्ष", "रॉकेट", "चाँद", "space", "rocket"),
             "a faceless sepia paper-collage silhouette of an astronaut in a bulky suit and round helmet, white cut-out outline"),
            ("Scientist", ("वैज्ञानिक", "प्रयोगशाला", "शोध", "scientist", "lab"),
             "a faceless sepia paper-collage silhouette of a scientist in a lab coat with round glasses, white cut-out outline"),
        ]
        best, bs = None, 0
        for name_, keys, look_ in themes:
            sc = sum(t.count(norm(k)) for k in keys)
            if sc > bs:
                best, bs = (name_, look_), sc
        if best:
            name, look = best
        else:
            name, look = ("Everyman", "a faceless sepia paper-collage silhouette of an ordinary adult in a long "
                                      "buttoned coat, flat cap and sturdy boots, white cut-out outline")
    ref = "protagonist_%s_%s" % (_slug(name), hashlib.sha1(look.encode("utf-8")).hexdigest()[:6])
    return {"name": name, "look": look, "reference_key": ref}


# --------------------------------------------------------------- main planner
def plan_shots(scenes, words=None, settings=None, log=print):
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in (settings or {}).items() if v is not None or k in ("refine", "protagonist")})
    rng = random.Random(int(cfg["seed"]))
    sc = _normalise_scenes(scenes, words)
    if not sc:
        return {"protagonist": _choose_protagonist("", cfg["protagonist"]), "shots": [], "stats": _stats([], 0, cfg)}
    _close_gaps(sc, words, cfg)
    prot = _choose_protagonist(" ".join(s["text"] + " " + s["prompt"] for s in sc), cfg["protagonist"])

    shots = []
    for si, s in enumerate(sc):
        toks, parts = split_scene(s, words, cfg)
        nxt = sc[si + 1]["start"] if si + 1 < len(sc) else None
        if parts and nxt is not None and parts[-1][3] < nxt - 0.01:       # a pause (longer than close_gaps closes) between this scene's last word and the next scene's first: the last shot runs on, so shots tile the audio
            a_, b_, t0_, _ = parts[-1]; parts[-1] = (a_, b_, t0_, nxt)
        # a shot that is mostly silence (a pause / closed gap after its last word) would hold one picture for ages: cut it into even pieces, the words stay on the first
        fixed = []
        for (a, b, t0, t1) in parts:
            n_cut = int(math.ceil((t1 - t0) / (cfg["max_len"] + 0.5))) if cfg["max_len"] else 1
            if n_cut <= 1: fixed.append((a, b, t0, t1)); continue
            step = (t1 - t0) / n_cut
            for q in range(n_cut): fixed.append((a, b, t0 + q * step, t1 if q == n_cut - 1 else t0 + (q + 1) * step) if q == 0 else (b, b, t0 + q * step, t1 if q == n_cut - 1 else t0 + (q + 1) * step))
        parts = fixed
        for k, (a, b, t0, t1) in enumerate(parts):
            text = " ".join(toks[a:b]) if toks else s["text"]
            shots.append({
                "shot_id": "%03d%s" % (s["no"], _suffix(k)), "scene_no": s["no"],
                "start": round(t0, 3), "end": round(t1, 3), "text": text,
                "_k": k, "_nk": len(parts), "_toks": (a, b), "_scene": s, "_all_toks": toks,
            })
    N = len(shots)
    scene_dur = {s["no"]: s["end"] - s["start"] for s in sc}

    # --- analysis per shot
    prev_side = "right"
    for i, sh in enumerate(shots):
        s = sh["_scene"]
        phrase = sh["text"]
        cons = concepts_in(phrase)
        scene_cons = concepts_in(s["prompt"])
        verb, journey, strong = _verb_in(phrase)
        person = any(LEX_BY_KEY[c][1] == "person" for c in cons)
        stat = bool(_NUM_RE.search(norm(phrase))) or bool(_YEAR_RE.search(phrase))
        sh["_cons"] = cons
        sh["_scene_cons"] = scene_cons
        sh["_verb"] = (verb, journey, strong)
        sh["_person"] = person
        sh["_stat"] = stat
        sh["_dur"] = sh["end"] - sh["start"]
        concrete = [c for c in cons if LEX_BY_KEY[c][1] != "abstract"]
        sh["_concrete"] = concrete
        if concrete:
            sh["subject"] = ", ".join(c.replace("_", " ") for c in concrete[:2])
        else:
            sh["subject"] = "detail of: " + (_scene_subject(s["prompt"])[:50] or "scene")
        sh["character"] = bool(person)
        side = "left" if prev_side == "right" else "right"
        if i and shots[i - 1]["_scene"] is s and set(concrete) & set(shots[i - 1]["_concrete"]):
            side = shots[i - 1].get("side", side)  # shared object: keep side for a clean match cut
        sh["side"] = side
        prev_side = side

    # --- graphics (stats only)
    gcap = max(1, int(round(cfg["graphic_ratio"] * N))) if cfg["graphic_ratio"] > 0 else 0
    gc = sorted([i for i, sh in enumerate(shots) if sh["_stat"] and sh["_dur"] >= 2.2],
                key=lambda i: (-(shots[i]["_dur"]), i))[:gcap]
    graphic = set(gc)

    # --- which shots get a new picture
    cap_new = max(0, int(round(cfg["max_new_ratio"] * len(sc))))
    new_count_scene = {}
    chosen = set()
    cand = [i for i, sh in enumerate(shots) if sh["_k"] > 0 and i not in graphic and len(sh["text"].split()) >= 2]   # one-word / empty fragments reuse a picture (the repair pass below may still promote them)
    last_change_t = {}

    def base_score(i):
        sh = shots[i]
        c = min(len(sh["_concrete"]), 2) * 1.0
        c += 0.8 if (set(sh["_concrete"]) - set(sh["_scene_cons"])) else 0.0
        c += 0.4 * min(sh["_dur"], 5.0)
        c += 0.08 * min(scene_dur[sh["scene_no"]], 30)
        c += 0.7 if sh["_verb"][2] else 0.0
        c += 0.5 if sh["_person"] else 0.0
        return c

    while len(chosen) < cap_new and cand:
        def adj(i):
            sh = shots[i]
            sc_new = new_count_scene.get(sh["scene_no"], 0)
            sc = base_score(i) - 1.2 * sc_new
            # reward breaking a long run on the same picture
            run = 0.0
            j = i - 1
            while j >= 0 and j not in chosen and shots[j]["scene_no"] == sh["scene_no"]:
                run += shots[j]["_dur"]
                j -= 1
            if run + sh["_dur"] > 6.0:
                sc += 1.5
            if i - 1 in chosen:
                sc -= 0.6  # prefer to spread
            return sc + rng.random() * 1e-6
        best = max(cand, key=lambda i: (adj(i), -i))
        if adj(best) <= 0.8 and len(chosen) >= len(sc):
            break
        chosen.add(best)
        cand.remove(best)
        new_count_scene[shots[best]["scene_no"]] = new_count_scene.get(shots[best]["scene_no"], 0) + 1

    # --- repair: no picture stays on screen longer than max_same_pic (Flow images are free; a longer hold reads as a still)
    lim = float(cfg.get("max_same_pic") or 0)
    if lim > 0:
        run, cur_scene = 0.0, None
        for i, sh in enumerate(shots):
            if i in graphic: run, cur_scene = 0.0, None; continue
            if sh["scene_no"] != cur_scene and sh["_k"] == 0: run = 0.0           # a scene's first shot starts its own picture
            cur_scene = sh["scene_no"]
            if i in chosen: run = 0.0
            run += sh["_dur"]
            if run > lim and sh["_k"] > 0 and i not in chosen:
                chosen.add(i); run = sh["_dur"]

    _seen = {}
    for i, sh in enumerate(shots):
        if i in chosen:                      # k-th new picture of this scene, and how often the same subject was already drawn in it: used to vary the framing
            key = (sh["scene_no"], tuple(sh["_concrete"][:2]))
            sh["_vi"] = _seen.get(("n", sh["scene_no"]), 0) + _seen.get(key, 0)
            _seen[("n", sh["scene_no"])] = _seen.get(("n", sh["scene_no"]), 0) + 1; _seen[key] = _seen.get(key, 0) + 1
    for i, sh in enumerate(shots):
        sh["picture"] = "new" if i in chosen else "existing"
        sh["_pic"] = sh["shot_id"] if i in chosen else "S%d" % sh["scene_no"]

    # --- motion tiers
    for sh in shots:
        sh["motion_tier"] = "still_motion"
        sh["link_to_next"] = None
    for i in graphic:
        shots[i]["motion_tier"] = "graphic"
    ai_cap = int(cfg["ai_video_ratio"] * N)
    ai_c = []
    for i, sh in enumerate(shots):
        if i in graphic or sh["_dur"] < 2.4:
            continue
        verb, journey, strong = sh["_verb"]
        if not (strong and (sh["character"] or journey)):
            continue
        sc_ = (3.0 if sh["character"] and strong else 0) + (2.0 if journey else 0) + len(sh["_concrete"]) * 0.5
        sc_ += 0.5 if sh["picture"] == "new" else 0
        ai_c.append((-sc_, i))
    ai_c.sort()
    ai = set()
    for _s, i in ai_c:
        if len(ai) >= ai_cap:
            break
        if (i - 1) in ai or (i + 1) in ai:
            continue
        ai.add(i)
        shots[i]["motion_tier"] = "ai_video"
    if cfg["allow_puppet"]:
        pc = int(cfg["puppet_ratio"] * N)
        walkers = [i for i, sh in enumerate(shots) if sh["character"] and sh["_verb"][1] and
                   sh["motion_tier"] == "still_motion"]
        for i in walkers[:pc]:
            shots[i]["motion_tier"] = "puppet"

    # --- links
    link_cap = int(cfg["link_ratio"] * N)
    lc = []
    for i in range(N - 1):
        a, b = shots[i], shots[i + 1]
        if a["motion_tier"] != "still_motion" or b["motion_tier"] in ("graphic",):
            continue
        if a["_pic"] == b["_pic"]:
            continue
        if b["start"] - a["end"] > 1.5:
            continue
        shared = set(a["_concrete"]) & set(b["_concrete"])
        place_a = {c for c in a["_concrete"] + a["_scene_cons"] if LEX_BY_KEY[c][1] in ("place", "vehicle")}
        place_b = {c for c in b["_concrete"] + b["_scene_cons"] if LEX_BY_KEY[c][1] in ("place", "vehicle")}
        place_change = bool(place_a and place_b and not (place_a & place_b))
        journey = a["_verb"][1]
        sc_ = (3.0 if journey else 0) + (2.0 if shared else 0) + (1.0 if place_change else 0)
        if sc_ < 2.0:
            continue
        if journey:
            kind = "walk_through" if a["character"] else "push_through"
            note = "movement carries over: %s" % (a["_verb"][0] or "journey")
        elif shared:
            kind = "match_cut"
            note = "shared object: %s" % ", ".join(sorted(shared)[:2])
        else:
            kind = "torn_wipe"
            note = "place change: %s -> %s" % (",".join(sorted(place_a)) or "?", ",".join(sorted(place_b)) or "?")
        lc.append((-sc_, i, kind, note))
    lc.sort()
    nl = 0
    for _s, i, kind, note in lc:
        if nl >= link_cap:
            break
        if shots[i]["motion_tier"] != "still_motion" or (i > 0 and shots[i - 1]["link_to_next"]):
            continue
        if shots[i + 1]["link_to_next"] and False:
            continue
        shots[i]["motion_tier"] = "link"
        shots[i]["link_to_next"] = {"kind": kind, "note": note}
        nl += 1

    # --- transitions
    locked = [False] * N
    alt_pool = ["dissolve", "cut", "whip", "match_cut", "torn_wipe", "doorway_push"]
    for i, sh in enumerate(shots):
        if i == 0:
            sh["transition_in"], sh["_tr_why"] = "cut", "opening shot"
            continue
        p = shots[i - 1]
        lk = p["link_to_next"]
        phrase = sh["text"]
        if lk:
            m = {"match_cut": "match_cut", "torn_wipe": "torn_wipe", "walk_through": "doorway_push",
                 "push_through": "doorway_push"}
            sh["transition_in"], sh["_tr_why"] = m[lk["kind"]], "link: " + lk["note"]
            locked[i] = True
            continue
        norm_phrase = norm(phrase)
        gap = sh["start"] - p["end"]
        if _WHIP_CUES.search(norm_phrase[:24] + " "):
            sh["transition_in"], sh["_tr_why"] = "whip", "time jump cue at phrase start"
        elif sh["scene_no"] != p["scene_no"] and (_TIME_CUES.search(norm_phrase[:30] + " ") or _YEAR_RE.search(phrase)):
            sh["transition_in"], sh["_tr_why"] = "dissolve", "time shift in new scene"
        elif sh["_pic"] == p["_pic"]:
            sh["transition_in"], sh["_tr_why"] = "cut", "same picture, new camera"
        elif set(sh["_concrete"]) & set(p["_concrete"]):
            sh["transition_in"], sh["_tr_why"] = "match_cut", "same object, new view"
        else:
            pa = {c for c in p["_concrete"] + p["_scene_cons"] if LEX_BY_KEY[c][1] in ("place", "vehicle")}
            pb = {c for c in sh["_concrete"] + sh["_scene_cons"] if LEX_BY_KEY[c][1] in ("place", "vehicle")}
            if pa and pb and not (pa & pb):
                sh["transition_in"] = "torn_wipe" if (i % 2 == 0 or rng.random() < 0.4) else "doorway_push"
                sh["_tr_why"] = "place change"
            elif sh["scene_no"] != p["scene_no"]:
                sh["transition_in"], sh["_tr_why"] = "dissolve", "new scene, same world"
            else:
                sh["transition_in"] = "dissolve" if rng.random() < 0.5 else "cut"
                sh["_tr_why"] = "new view in same place, no shared object"
    for i in range(2, N):
        if shots[i]["transition_in"] == shots[i - 1]["transition_in"] == shots[i - 2]["transition_in"]:
            cur = shots[i]["transition_in"]
            for j in (i, i - 1):
                if not locked[j]:
                    opts = [t for t in alt_pool if t != cur]
                    pick = opts[(i + int(cfg["seed"])) % len(opts)]
                    # do not create a new triple with the following shot
                    shots[j]["transition_in"] = pick
                    shots[j]["_tr_why"] += " (varied: no 3 in a row)"
                    break
            else:
                shots[i - 1]["link_to_next"] = None
                if shots[i - 1]["motion_tier"] == "link":
                    shots[i - 1]["motion_tier"] = "still_motion"
                shots[i]["transition_in"] = "dissolve"
                shots[i]["_tr_why"] += " (link dropped: no 3 in a row)"
                locked[i] = False

    # --- camera
    last = None
    for i, sh in enumerate(shots):
        scale = None
        for c in sh["_concrete"] or sh["_scene_cons"]:
            scale = LEX_BY_KEY[c][2]
            break
        journey = sh["_verb"][1]
        if sh["motion_tier"] == "graphic":
            pref = ["hold_alive"]
        elif journey:
            pref = ["drift_r" if sh["side"] == "left" else "drift_l", "diag"]
        elif sh["_k"] == 0 and scale == "wide":
            pref = ["pull_out", "push_in"]
        elif scale == "close" or sh["character"]:
            pref = ["push_in", "diag"]
        elif scale == "wide":
            pref = ["pull_out", "drift_l" if sh["side"] == "right" else "drift_r"]
        else:
            pref = ["push_in", "drift_r" if sh["side"] == "left" else "drift_l", "pull_out"]
        if i and shots[i - 1]["_pic"] == sh["_pic"]:
            pref = [c for c in ("pull_out", "diag", "drift_l", "drift_r", "push_in") if c not in (last,)] [:3] + pref
            pref = [c for c in pref if c != last]
            pref = pref[::-1][:1] + pref  # contrast first
        cam = next((c for c in pref if c != last), None)
        if cam is None:
            cam = next(c for c in CAMERAS if c != last and c != "hold_alive")
        sh["camera"] = cam
        last = cam

    # --- prompts, beats, why
    for i, sh in enumerate(shots):
        s = sh["_scene"]
        if sh["picture"] == "existing":
            sh["prompt_en"] = s["prompt"]
        else:
            sh["prompt_en"] = _compose_prompt(sh, s, prot)
        toks = sh["_all_toks"]
        a, b = sh["_toks"]
        _t, tt = _token_times(s, words)
        beats = []
        for ti in range(a, min(b, len(tt))):
            if concepts_in(toks[ti]):
                beats.append({"t0": round(tt[ti][0], 3), "t1": round(tt[ti][1], 3), "word_idx": ti})
        if not beats:
            beats = [{"t0": sh["start"], "t1": round(min(sh["end"], sh["start"] + 0.6), 3), "word_idx": a}]
        sh["beats"] = beats
        sh["why"] = _why(sh)

    # --- optional refine hook (e.g. an LLM); never required
    out_shots = []
    keep = ("shot_id", "scene_no", "start", "end", "text", "subject", "prompt_en", "picture", "character",
            "motion_tier", "camera", "transition_in", "link_to_next", "beats", "why", "side")
    for sh in shots:
        d = {k: sh[k] for k in keep}
        if sh["motion_tier"] == "graphic":
            d["graphic"] = {"kind": "stat", "value": " ".join(re.findall(r"\S*(?:\d|%|लाख|ट्रिलियन|करोड़|अरब|प्रतिशत)\S*", sh["text"]))[:60]}
        out_shots.append(d)
    plan = {"protagonist": prot, "shots": out_shots, "stats": _stats(out_shots, len(sc), cfg)}
    if callable(cfg.get("refine")):
        try:
            p2 = cfg["refine"](plan)
            if isinstance(p2, dict) and p2.get("shots"):
                plan = p2
                plan["stats"] = _stats(plan["shots"], len(sc), cfg)
        except Exception as e:  # noqa: BLE001
            log("[shot_director] refine hook failed, kept heuristic plan: %s" % e)
    st = plan["stats"]
    log("[shot_director] %d scenes -> %d shots (avg %.1fs), %d new pictures" %
        (len(sc), st["shots"], st["avg_len"], st["new_pictures"]))
    return plan


FRAMINGS = ("extreme close-up on one key object from",
            "low-angle view of",
            "top-down view of",
            "side view with a strong foreground object, showing",
            "wide establishing view with deep empty space around",
            "view through a doorway or window frame at",
            "tight crop on the hands and objects of",
            "dramatic silhouette against the light of")


def hash_stable(x) -> int:
    return int(hashlib.md5(str(x).encode()).hexdigest()[:6], 16)


def _compose_prompt(sh, s, prot):
    cons = sh["_concrete"][:2]
    vi = int(sh.get("_vi", 0))
    if cons:
        vis = [LEX_BY_KEY[c][0] for c in cons if LEX_BY_KEY[c][1] != "person"]
        scale = LEX_BY_KEY[cons[0]][2]
        frame = {"wide": "wide establishing view of", "mid": "medium view of", "close": "close-up of"}[scale]
        body = " with ".join(vis[:2]) if vis else "the scene"
    else:
        frame = "alternate view within the same scene:"
        body = _scene_subject(s["prompt"])
        if vi > 0 or sh.get("picture") == "new": frame = FRAMINGS[(vi + hash_stable(sh["shot_id"])) % len(FRAMINGS)]    # every new picture of a scene frames the subject differently
    if cons and vi > 0: frame = FRAMINGS[(vi + hash_stable(sh["shot_id"])) % len(FRAMINGS)]      # the same subject again in this scene: another framing
    parts = ["%s %s" % (frame, body)]
    if sh["character"]:
        act = sh["_verb"][0] or "standing alert"
        parts.append("%s, %s" % (prot["look"], act))
    side = sh.get("side", "left")
    parts.append("main subject placed on the %s third, open space on the %s" % (side, "right" if side == "left" else "left"))
    if sh["_verb"][1]:
        parts.append("clear empty floor strip along the bottom third for a walking figure")
    parts.append(STYLE_EN)
    parts.append(NO_TEXT)
    txt = "Collage illustration, " + ", ".join(parts) + "."
    return txt


def _why(sh):
    ph = " ".join(sh["text"].split()[:5])
    bits = ['phrase "%s..."' % ph]
    bits.append("%.1fs" % sh["_dur"])
    if sh["picture"] == "new":
        bits.append("new picture: concrete subject %s" % (",".join(sh["_concrete"]) or "scene detail"))
    elif sh["_k"] == 0:
        bits.append("first shot of the scene reuses its picture")
    else:
        bits.append("picture reused (budget/low concreteness)")
    if sh["motion_tier"] == "ai_video":
        bits.append("ai_video: action '%s'" % sh["_verb"][0])
    elif sh["motion_tier"] == "link":
        bits.append("link: %s" % sh["link_to_next"]["note"])
    elif sh["motion_tier"] == "graphic":
        bits.append("graphic: number/stat in phrase")
    elif sh["motion_tier"] == "puppet":
        bits.append("puppet: walking action allowed by settings")
    if sh["character"]:
        bits.append("person in phrase -> protagonist")
    bits.append("transition: " + sh.get("_tr_why", ""))
    return "; ".join(bits)


def _stats(shots, n_scenes, cfg):
    from collections import Counter
    d = [s["end"] - s["start"] for s in shots]
    tiers = Counter(s["motion_tier"] for s in shots)
    trans = Counter(s["transition_in"] for s in shots)
    # longest run on one picture
    longest, run, cur = 0.0, 0.0, None
    for s in shots:
        pic = s["shot_id"] if s["picture"] == "new" else "S%d" % s["scene_no"]
        if s.get("motion_tier") == "graphic": pic = "G" + s["shot_id"]     # a graphic is itself a visible change
        run = run + (s["end"] - s["start"]) if pic == cur else (s["end"] - s["start"])
        cur = pic
        longest = max(longest, run)
    return {
        "scenes": n_scenes, "shots": len(shots),
        "avg_len": round(sum(d) / len(d), 2) if d else 0.0,
        "min_len": round(min(d), 2) if d else 0.0, "max_len": round(max(d), 2) if d else 0.0,
        "shorter_than_min": sum(1 for x in d if x < cfg["min_len"] - 1e-6),
        "longer_than_max": sum(1 for x in d if x > cfg["max_len"] + 0.5),
        "new_pictures": sum(1 for s in shots if s["picture"] == "new"),
        "character_shots": sum(1 for s in shots if s["character"]),
        "tiers": dict(tiers), "transitions": dict(trans),
        "longest_same_picture_s": round(longest, 1),
    }


# ------------------------------------------------------------------- CSV I/O
CSV_COLUMNS = ["scene_number", "shot_id", "script_segment", "asset_type", "prompt", "character",
               "motion_tier", "camera", "transition_in", "link_to_next"]
CSV_EXTRA = ["start", "end", "picture", "subject", "why"]


def to_csv_rows(plan, extras=True):
    rows = []
    for s in plan.get("shots", []):
        lk = s.get("link_to_next")
        r = {
            "scene_number": s["scene_no"], "shot_id": s["shot_id"], "script_segment": s["text"],
            "asset_type": "image" if s.get("picture") == "new" else "reuse",
            "prompt": s.get("prompt_en", ""), "character": "true" if s.get("character") else "false",
            "motion_tier": s.get("motion_tier", "still_motion"), "camera": s.get("camera", ""),
            "transition_in": s.get("transition_in", "cut"),
            "link_to_next": ("%s: %s" % (lk["kind"], lk.get("note", ""))).rstrip(": ") if lk else "",
        }
        if extras:
            r.update({"start": s.get("start", ""), "end": s.get("end", ""), "picture": s.get("picture", ""),
                      "subject": s.get("subject", ""), "why": s.get("why", "")})
        rows.append(r)
    return rows


def _truthy(v):
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "t")


def from_csv_rows(rows, protagonist=None):
    """Inverse of to_csv_rows. Tolerant: old 4-column CSVs become one shot per
    scene (asset_type image/video => picture 'existing' for the first row of a
    scene, later rows of the same scene 'new')."""
    shots = []
    per_scene = {}
    for i, r in enumerate(rows or []):
        r = {str(k).strip().lower(): v for k, v in dict(r).items() if k is not None}
        try:
            sn = int(float(r.get("scene_number") or r.get("scene_no") or r.get("scene") or (i + 1)))
        except (TypeError, ValueError):
            sn = i + 1
        k = per_scene.get(sn, 0)
        per_scene[sn] = k + 1
        at = str(r.get("asset_type") or "image").strip().lower()
        pic = str(r.get("picture") or "").strip().lower()
        if pic not in ("existing", "new"):
            pic = "existing" if (at == "reuse" or k == 0) else "new"
        lk_raw = str(r.get("link_to_next") or "").strip()
        lk = None
        if lk_raw and lk_raw.lower() not in ("none", "null", "false"):
            kind, _sep, note = lk_raw.partition(":")
            lk = {"kind": kind.strip(), "note": note.strip()}
        tier = str(r.get("motion_tier") or "").strip() or "still_motion"
        st, en = r.get("start"), r.get("end")
        try:
            st = float(st)
        except (TypeError, ValueError):
            st = None
        try:
            en = float(en)
        except (TypeError, ValueError):
            en = None
        shots.append({
            "shot_id": str(r.get("shot_id") or "").strip() or "%03d%s" % (sn, _suffix(k)),
            "scene_no": sn, "start": st, "end": en,
            "text": str(r.get("script_segment") or r.get("text") or ""),
            "subject": str(r.get("subject") or ""), "prompt_en": str(r.get("prompt") or r.get("prompt_en") or ""),
            "picture": pic, "character": _truthy(r.get("character")), "motion_tier": tier,
            "camera": str(r.get("camera") or "").strip() or "push_in",
            "transition_in": str(r.get("transition_in") or "").strip() or "cut",
            "link_to_next": lk, "beats": [], "why": str(r.get("why") or ""),
        })
    cfg = dict(DEFAULTS)
    stats = _stats([s for s in shots if s["start"] is not None and s["end"] is not None], len(per_scene), cfg)
    return {"protagonist": protagonist or {"name": "", "look": "", "reference_key": ""},
            "shots": shots, "stats": stats}
