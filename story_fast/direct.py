"""Story Motion visual director: decides per shot HOW it looks and moves (genre, energy, camera treatment, ambient layer, transition, continuity,
optional AI-video flag). Pure python, deterministic for a seed, no inputs mutated. Works on Hindi (Devanagari / romanised) and English text.

    direct(shots, settings, seed) -> {"shots": [...], "stats": {...}, "bible": {...}}
    continuity_suffix(bible, shot) -> str       (anchor appended to Flow prompts of NEW pictures)
    csv_hint(prompt) -> dict                    (optional 'MOTION: tracking-right | energy 4 | needs-real-movement' tag)
"""
from __future__ import annotations

import copy
import math
import random
import re
import time
from collections import Counter
from typing import Any, Dict, List, Optional

TREATMENTS = ("push_in", "pull_out", "pan_left", "pan_right", "tilt_up", "tilt_down", "parallax_left", "parallax_right",
              "dolly_through", "arc", "reveal_up", "track_lateral", "handheld", "hold_alive")
TRANSITIONS = ("cut", "dissolve", "fade", "soft", "flash", "zoom_blur")
ENVS = ("dust", "fog", "embers", "rain", "snow", "light_sweep", "shimmer")
GENRES = ("history", "travel", "emotional", "action", "documentary")
MAX_SHARE = 0.22
DISSOLVE_MAX = 0.14            # in this app every dissolve/soft/fade is a dip through black, so a film-like cut stays the norm:
DIP_MAX = 0.30                 # dissolve + soft + fade together (hard cuts and motion-led cuts carry the rest)
FADE_MAX = 0.08
MAX_RUN = 3
MAX_CUT_RUN = 10 ** 6          # plain cuts are what films mostly use and carry no 'repeat' penalty; the variety comes from the camera treatment and the shot


# ------------------------------------------------------------------ lexicons (English stems / romanised Hindi / Devanagari substrings)
def _lex(en: str, dev: str = "") -> re.Pattern:
    """en: space separated stems matched at a word start; dev: space separated Devanagari substrings."""
    parts = []
    if en.strip():
        parts.append(r"\b(?:" + "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in en.split()) + ")")
    if dev.strip():
        parts.append("(?:" + "|".join(re.escape(w) for w in dev.split()) + ")")
    return re.compile("|".join(parts), re.I)


_GENRE = {
    "history": _lex("war battle army armies soldier sword spear king queen emperor empire dynasty fort castle palace ancient century centuries kingdom "
                    "siege conquest throne temple ruins medieval banner knight warrior crown sultan raja rani qila kila mahal sena yuddh yudh badshah samrat "
                    "revolution colonial era historic",
                    "युद्ध लड़ाई राजा रानी सम्राट साम्राज्य किला किले महल सेना सैनिक तलवार इतिहास सदी सदियों बादशाह राज्य सिंहासन योद्धा मुगल अंग्रेज़ अंग्रेज क्रांति"),
    "travel": _lex("journey travel traveler traveller road path trek mountain valley river ocean sea coast desert horizon landscape caravan voyage sail "
                   "highway train wander trail expedition safar yatra rasta pahad nadi samudra sagar jungle",
                   "सफ़र सफर यात्रा यात्री रास्ता राह रास्ते पहाड़ घाटी नदी समुद्र सागर रेगिस्तान मंज़िल मंजिल जंगल मुसाफ़िर मुसाफिर"),
    "emotional": _lex("cry crying tears farewell goodbye love grief loss mother father death dying alone lonely hug heartbreak memory miss sorrow sad "
                      "mourn weep pyaar pyar maut dard dukh judai ro",
                      "प्यार प्रेम मोहब्बत आँसू आंसू रोया रोती रोने रो रहा रो रही मौत मृत्यु अलविदा जुदाई माँ पिता याद दर्द दुख अकेला अकेली तन्हा गले बिछड़ बिछुड़ विदा आख़िरी आखिरी"),
    "action": _lex("fight chase run running ran escape attack explosion gallop charge ride riding race jump flee crash rush clash duel ambush "
                   "bhaag bhaga daud ghoda ghode dhamaka",
                   "भाग भागा भागता दौड़ पीछा हमला टूट पड़ घुड़सवार घोड़े घोड़ा भिड़ कूद धमाका छलांग वार"),
    "documentary": _lex("data statistic statistics year population scientist study studied discovered discovery research museum archive map evidence "
                        "record according report survey experiment analysis percent",
                        "शोध अध्ययन वैज्ञानिक आँकड़े आंकड़े दस्तावेज खोज संग्रहालय अभिलेख प्रमाण सबूत अनुसार रिपोर्ट सर्वे प्रतिशत"),
}
_GENRE_ORDER = ("emotional", "history", "action", "travel", "documentary")

_ENV = {
    "embers": _lex("fire flame flames smoke burning ember embers torch bonfire blaze ash smoulder smolder aag dhuan",
                   "आग लपट धुआँ धुआं जल रहा जलते मशाल अंगारे राख"),
    "rain": _lex("storm rain rainy thunder lightning monsoon downpour drizzle barish toofan",
                 "तूफ़ान तूफान बारिश बरसात बिजली आँधी आंधी मूसलाधार"),
    "snow": _lex("snow snowy cold winter blizzard frozen ice icy glacier frost barf", "बर्फ़ बर्फ सर्दी ठंड ठंडी हिमालय हिम"),
    "dust": _lex("desert dust dusty sand sandstorm caravan arid ruins parched dry dhool", "धूल रेगिस्तान रेत मिट्टी सूखा सूखे खंडहर कारवाँ कारवां"),
    "fog": _lex("mist misty fog foggy dawn haze hazy twilight morning cloud clouds kohra", "धुंध कोहरा सुबह भोर बादल धुँध"),
    "light_sweep": _lex("sacred sunrise sunset divine holy temple prayer glow golden rays beam heaven blessing worship",
                        "पवित्र सूर्योदय सूर्यास्त दिव्य पूजा प्रार्थना मंदिर रोशनी किरण आशीर्वाद"),
    "shimmer": _lex("water river lake sea ocean waves wave reflection shimmering stream pond harbor harbour nadi samudra",
                    "पानी नदी झील समुद्र सागर लहर तालाब झरना"),
}

_SHAPE_CLOSE = _lex("close-up closeup close up portrait face eyes hands hand detail macro over-the-shoulder over the shoulder tears expression")
_SHAPE_WIDE = _lex("wide establishing aerial landscape panorama panoramic vista horizon skyline drone expanse sweeping")
_SHAPE_BUILD = _lex("castle fort fortress palace temple tower cathedral mosque building architecture minaret gate skyscraper ruins pillar monument "
                    "dome facade", "किला महल मंदिर मीनार इमारत गुंबद")
_SHAPE_LOW = _lex("low angle low-angle looking up towering")
_SHAPE_HIGH = _lex("high angle high-angle top-down overhead bird's-eye birds-eye from above")
_TIME_JUMP = _lex("years later next day next morning centuries decades flashback long ago once upon later that meanwhile weeks later months later",
                  "सालों बाद साल बाद सदियों कई साल अगले दिन बहुत पहले दशकों कुछ दिन बाद")
_MEMORY = _lex("flashback memory remember remembered dream recalled", "याद यादों सपना सपने")
_CLIMAX = _lex("explosion lightning suddenly flash blast thunder", "धमाका बिजली अचानक")
_REAL_MOVE = _lex("fight fights fighting duel run runs running ran chase chased ride rides riding gallop charge dance dancing speak speaks speaking "
                  "speech ceremony march marching swing sword wield climb jump swim walk walking", "भाग दौड़ लड़ ")
_REAL_MOVE_DEV = _lex("", "भागता दौड़ता लड़ता लड़ रहा घुड़सवारी नाच नृत्य भाषण समारोह कूद चढ़ तैर")
_PERSON = _lex("man woman boy girl king queen knight soldier warrior prince princess child mother father monk merchant traveler rider people crowd army "
               "figure hero rider horseman", "आदमी औरत राजा रानी सैनिक योद्धा बच्चा माँ पिता साधु व्यापारी यात्री लड़की लड़का घुड़सवार")
_ENERGY_UP = _lex("fast rush charge explosion chase battle storm frantic urgent furious violent gallop crash", "तेज़ तेज भागा धमाका तूफ़ान तूफान भीषण")
_ENERGY_DOWN = _lex("quiet silent still calm peaceful slow gentle soft sleeping rest lonely sorrow", "शांत चुप धीरे सन्नाटा खामोश")

_LOCS = [
    ("forest", "forest jungle woods woodland grove", "जंगल वन"),
    ("desert", "desert dunes sahara wasteland", "रेगिस्तान"),
    ("mountain", "mountain mountains peak cliff himalaya pass canyon", "पहाड़ पर्वत हिमालय चोटी"),
    ("river", "river lake stream waterfall pond riverbank", "नदी झील झरना तालाब"),
    ("sea", "sea ocean beach shore coast harbor harbour waves", "समुद्र सागर तट बंदरगाह"),
    ("ship", "ship boat deck vessel galleon", "जहाज़ जहाज नाव"),
    ("village", "village hut farm field fields countryside", "गाँव गांव खेत झोपड़ी"),
    ("city", "city town street streets alley skyline", "शहर नगर गली सड़क"),
    ("market", "market bazaar bazar souk", "बाज़ार बाजार मंडी"),
    ("castle", "castle fort fortress rampart ramparts citadel walls", "किला किले दुर्ग"),
    ("palace", "palace court throne hall durbar", "महल दरबार सिंहासन"),
    ("temple", "temple shrine mosque cathedral church monastery", "मंदिर मस्जिद गुरुद्वारा मठ"),
    ("battlefield", "battlefield battleground warfield", "रणभूमि युद्धभूमि रणक्षेत्र मैदान"),
    ("room", "room house home interior chamber kitchen study library", "घर कमरा कक्ष"),
    ("cave", "cave cavern tunnel", "गुफा गुफ़ा सुरंग"),
    ("road", "road highway path trail bridge", "रास्ता रास्ते पुल"),
    ("sky", "sky clouds above", "आसमान आकाश"),
]
_LOC_RE = [(k, _lex(en, dv)) for k, en, dv in _LOCS]

_ROLES = {
    "king": ("king", "राजा"), "queen": ("queen", "रानी"), "emperor": ("emperor sultan", "सम्राट बादशाह"), "knight": ("knight", ""),
    "soldier": ("soldier soldiers", "सैनिक सिपाही"), "warrior": ("warrior", "योद्धा"), "prince": ("prince", "राजकुमार"), "princess": ("princess", "राजकुमारी"),
    "child": ("child boy", "बच्चा लड़का बालक"), "girl": ("girl", "लड़की बच्ची"), "mother": ("mother", "माँ माता"), "father": ("father", "पिता"),
    "monk": ("monk sage priest", "साधु संत ऋषि"), "merchant": ("merchant trader", "व्यापारी"), "traveler": ("traveler traveller wanderer", "यात्री मुसाफ़िर मुसाफिर"),
    "woman": ("woman", "औरत महिला स्त्री"), "man": ("man", "आदमी पुरुष"), "elder": ("elder", "बुज़ुर्ग बुजुर्ग"), "farmer": ("farmer", "किसान"),
    "general": ("general commander", "सेनापति"), "hero": ("hero", "नायक"),
}
_ROLE_RE = {k: _lex(en, dv) for k, (en, dv) in _ROLES.items()}
_ROLE_EN = re.compile(r"\b(?:a|an|the)\s+((?:[A-Za-z\-]+\s+){0,6}?(" + "|".join(sorted({w for k, (en, dv) in _ROLES.items() for w in en.split()}, key=len, reverse=True))
                      + r"))\b(?:\s+(?:with|in|wearing|dressed in|holding|carrying)\s+[^,.;:|]{3,60})?", re.I)
_LOC_EN_WORDS = {k: en.split() for k, en, dv in _LOCS}


# ------------------------------------------------------------------ MOTION tag
_MOTION_RE = re.compile(r"MOTION\s*[:=]\s*([^\n]*)", re.I)
_HINT_MAP = {
    "push-in": ("push_in", None), "pushin": ("push_in", None), "push": ("push_in", None), "dolly-in": ("push_in", None),
    "pull-out": ("pull_out", None), "pull-back": ("pull_out", None), "pullback": ("pull_out", None), "dolly-out": ("pull_out", None),
    "pan-left": ("pan_left", "l"), "pan-right": ("pan_right", "r"), "pan": ("pan_left", None),
    "tilt-up": ("tilt_up", "up"), "tilt-down": ("tilt_down", "down"),
    "parallax-left": ("parallax_left", "l"), "parallax-right": ("parallax_right", "r"), "parallax": ("parallax_left", None),
    "dolly": ("dolly_through", None), "dolly-through": ("dolly_through", None), "push-through": ("dolly_through", None),
    "arc": ("arc", None), "orbit": ("arc", None), "arc-left": ("arc", "l"), "arc-right": ("arc", "r"),
    "reveal": ("reveal_up", "up"), "reveal-up": ("reveal_up", "up"), "crane-up": ("reveal_up", "up"),
    "tracking-left": ("track_lateral", "l"), "tracking-right": ("track_lateral", "r"), "track-left": ("track_lateral", "l"),
    "track-right": ("track_lateral", "r"), "tracking": ("track_lateral", None), "track": ("track_lateral", None),
    "handheld": ("handheld", None), "hold": ("hold_alive", None), "hold-alive": ("hold_alive", None), "static": ("hold_alive", None),
}


def strip_motion(prompt: str) -> str:
    return _MOTION_RE.sub("", prompt or "").strip(" \t|;")


def csv_hint(prompt: str) -> dict:
    """Parse the optional 'MOTION: tracking-right | energy 4 | needs-real-movement' tag. Returns only the keys that were found:
    treatment, dir, energy (1-5), needs_real_movement (bool), transition."""
    out: Dict[str, Any] = {}
    m = _MOTION_RE.search(prompt or "")
    if not m:
        return out
    for tok in re.split(r"[|;]", m.group(1)):
        t = re.sub(r"[\s_]+", "-", tok.strip().lower())
        if not t:
            continue
        e = re.match(r"energy[-:=]*(\d)", t)
        if e:
            out["energy"] = max(1, min(5, int(e.group(1))))
        elif t in ("needs-real-movement", "real-movement", "needs-movement", "ai-video", "needs-real-motion"):
            out["needs_real_movement"] = True
        elif t.startswith("transition-") or t.startswith("trans-"):
            n = t.split("-", 1)[1]
            if n in ("hard-cut", "hardcut"):
                n = "cut"
            n = n.replace("-", "_")
            if n in TRANSITIONS:
                out["transition"] = n
        elif t in _HINT_MAP:
            name, d = _HINT_MAP[t]
            out["treatment"] = name
            if d:
                out["dir"] = d
    return out


# ------------------------------------------------------------------ helpers
def _f(x, d=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _count(rx: re.Pattern, text: str) -> int:
    return len(rx.findall(text)) if text else 0


def _texts(sh: dict):
    en = strip_motion(str(sh.get("prompt_en") or sh.get("prompt") or ""))
    hi = str(sh.get("text") or "")
    subj = str(sh.get("subject") or "")
    return en, hi, (en + " " + hi + " " + subj).lower()


def _genre(blob: str, hint_energy: Optional[int]):
    scores = {g: _count(rx, blob) for g, rx in _GENRE.items()}
    best, bs = "neutral", 0
    for g in _GENRE_ORDER:
        if scores[g] > bs:
            best, bs = g, scores[g]
    return best, scores


def _location(en: str, blob: str) -> Optional[str]:
    best, pos = None, 10 ** 9
    low = en.lower()
    for k, rx in _LOC_RE:
        m = rx.search(low)
        if m:
            # prefer a place introduced by a preposition ("in the forest")
            pre = re.search(r"\b(?:in|at|inside|on|near|through|across|outside|beyond|above|over|into|along)\s+(?:the|a|an)?\s*(?:[\w\-]+\s+){0,3}?" + re.escape(m.group(0)), low)
            p = (pre.start() - 1000) if pre else m.start()
            if p < pos:
                best, pos = k, p
    if best:
        return best
    for k, rx in _LOC_RE:
        if rx.search(blob):
            return k
    return None


def _roles(en: str, blob: str) -> List[str]:
    src = en.lower() if en else blob
    found = [k for k, rx in _ROLE_RE.items() if rx.search(src)]
    if not found and en:
        found = [k for k, rx in _ROLE_RE.items() if rx.search(blob)]
    # man/woman/child are generic: drop them when a specific role is present
    if len(found) > 1:
        found = [r for r in found if r not in ("man", "woman")] or found
    return found[:3]


# ------------------------------------------------------------------ bible
def _style_anchor(prompts: List[str]) -> str:
    cnt: Counter = Counter()
    for p in prompts:
        seen = set()
        for seg in re.split(r"[,.;|]", p):
            s = seg.strip().lower()
            if 2 <= len(s.split()) <= 10 and s not in seen:
                seen.add(s)
        cnt.update(seen)
    n = len(prompts)
    if n < 3:
        return ""
    best = [s for s, c in cnt.items() if c >= max(3, 0.3 * n)]
    if not best:
        return ""
    best.sort(key=lambda s: (-cnt[s], s))
    # keep the original casing of one occurrence, in the order they first appear
    out = []
    for s in best[:4]:
        for p in prompts:
            m = re.search(re.escape(s), p, re.I)
            if m:
                out.append(m.group(0))
                break
    return ", ".join(out)


def _build_bible(shots: List[dict], metas: List[dict]) -> dict:
    chars: Dict[str, dict] = {}
    locs: Dict[str, dict] = {}
    prompts = []
    for sh, mt in zip(shots, metas):
        en = mt["en"]
        prompts.append(en)
        for m in _ROLE_EN.finditer(en):
            role_word = m.group(2).lower()
            key = next((k for k, (e, d) in _ROLES.items() if role_word in e.split()), None)
            if not key:
                continue
            desc = re.sub(r"\s+", " ", m.group(0)).strip()
            words = desc.split()
            if len(words) > 16:
                desc = " ".join(words[:16])
            cur = chars.get(key)
            if cur is None or (not cur["long"] and len(words) > len(cur["desc"].split())):
                chars[key] = {"desc": desc, "first_shot": sh.get("shot_id"), "long": len(words) >= 5}
        lk = mt["loc"]
        if lk and lk not in locs:
            low = en
            best = None
            for w in _LOC_EN_WORDS.get(lk, []):
                m = re.search(r"\b(?:in|at|inside|on|near|through|across|outside|beyond|above|over|into|along)\s+((?:the|a|an)\s+(?:[\w\-]+\s+){0,5}?" + re.escape(w)
                              + r"\w*(?:\s+(?:of|with|under|at|beneath|against)\s+(?:[\w\-]+\s+){0,3}[\w\-]+)?)", low, re.I)
                if m:
                    best = m.group(1)
                    break
            locs[lk] = {"desc": re.sub(r"\s+", " ", best).strip() if best else lk, "first_shot": sh.get("shot_id")}
    for v in chars.values():
        v.pop("long", None)
    return {"characters": chars, "locations": locs, "style": _style_anchor(prompts)}


def continuity_suffix(bible: dict, shot: dict) -> str:
    """Short English anchor for a Flow image prompt of a NEW picture: the canonical description of the recurring character(s)/location + style anchor,
    skipping whatever the prompt already says."""
    if not bible:
        return ""
    en = strip_motion(str(shot.get("prompt_en") or shot.get("prompt") or "")).lower()
    c = shot.get("continuity") or {}
    bits = []
    for ck in (c.get("characters") or [])[:2]:
        d = ((bible.get("characters") or {}).get(ck) or {}).get("desc")
        if d and d.lower() not in en:
            bits.append("same %s as before: %s" % (ck, d))
    lk = c.get("location")
    d = ((bible.get("locations") or {}).get(lk) or {}).get("desc") if lk else None
    if d and d != lk and d.lower() not in en:
        bits.append("same setting: %s" % d)
    st = bible.get("style") or ""
    if st and st.lower() not in en:
        bits.append("consistent style: %s" % st)
    s = "; ".join(bits)
    return (s[:320].rsplit(" ", 1)[0] if len(s) > 320 else s)


# ------------------------------------------------------------------ treatment choice
# family weights per genre / shape (families: pan, parallax, track resolved to a direction)
_BASE = {
    "history": {"arc": 3, "pan": 2, "push_in": 2, "parallax": 2, "reveal_up": 2, "pull_out": 1.5, "tilt_up": 1, "hold_alive": 1, "track_lateral": 1},
    "travel": {"track_lateral": 3, "parallax": 3, "pan": 2, "pull_out": 1.5, "dolly_through": 1.5, "reveal_up": 1, "arc": 1, "tilt_down": 0.7},
    "emotional": {"push_in": 3, "hold_alive": 2.5, "handheld": 1.5, "reveal_up": 1, "pull_out": 1.5, "tilt_down": 0.7, "arc": 0.6},
    "action": {"dolly_through": 3, "handheld": 3, "pan": 2, "track_lateral": 2, "push_in": 1.5, "arc": 1, "parallax": 0.6},
    "documentary": {"push_in": 2, "pan": 2, "parallax": 2, "hold_alive": 1.5, "tilt_up": 1, "tilt_down": 1, "pull_out": 1.5, "track_lateral": 1, "arc": 1},
    "neutral": {"push_in": 2, "pan": 2, "parallax": 2, "pull_out": 1.5, "track_lateral": 1.5, "hold_alive": 1, "arc": 1, "reveal_up": 1, "tilt_up": 0.8,
                "tilt_down": 0.8, "handheld": 0.6, "dolly_through": 0.6},
}
_SHAPE_MUL = {
    "close": {"push_in": 2.2, "handheld": 1.8, "hold_alive": 2.0, "reveal_up": 1.4, "pan": 0.4, "parallax": 0.5, "track_lateral": 0.3, "arc": 0.7},
    "wide": {"track_lateral": 2.0, "parallax": 2.0, "pan": 1.6, "pull_out": 1.3, "hold_alive": 0.6, "handheld": 0.5},
    "build": {"tilt_up": 3.0, "tilt_down": 1.6, "reveal_up": 2.5, "arc": 2.0, "handheld": 0.4, "hold_alive": 0.5},
    "low": {"reveal_up": 2.0, "tilt_up": 1.6},
    "high": {"tilt_down": 2.0, "pull_out": 1.6},
}
_FAMILY_NAMES = {"pan": ("pan_left", "pan_right"), "parallax": ("parallax_left", "parallax_right")}
_DIRECTIONAL = {"pan_left": "l", "pan_right": "r", "parallax_left": "l", "parallax_right": "r"}


def _shape(en_low: str) -> str:
    sc = {"close": _count(_SHAPE_CLOSE, en_low), "wide": _count(_SHAPE_WIDE, en_low), "build": _count(_SHAPE_BUILD, en_low)}
    k = max(sc, key=lambda x: (sc[x], x == "close"))
    return k if sc[k] else ""


def _pick(rng: random.Random, weights: Dict[str, float]) -> str:
    tot = sum(weights.values())
    r = rng.random() * tot
    acc = 0.0
    last = None
    for k in sorted(weights):
        w = weights[k]
        if w <= 0:
            continue
        acc += w
        last = k
        if r <= acc:
            return k
    return last or "push_in"


def _choose_transition(rng, mt, prev_mt, i, st, n) -> str:
    """st: dict with counts/run state."""
    if i == 0:
        return "cut"
    g, pg = mt["genre"], prev_mt["genre"]
    hint = mt["hint"].get("transition")
    same = mt["same_loc"]
    opts: List[str]
    if hint:
        opts = [hint]
    elif mt["time_jump"]:
        opts = ["fade", "dissolve", "soft"]
    elif mt["memory"] or (g == "emotional") != (pg == "emotional"):
        opts = ["soft", "dissolve", "fade"]
    elif not same:
        opts = ["zoom_blur", "fade", "soft", "cut"] if (g == "action" and mt["energy"] >= 4) else ["fade", "soft", "dissolve", "cut"] if mt["energy"] <= 2 else ["soft", "fade", "zoom_blur", "dissolve", "cut"]
    elif g == "action":
        opts = ["cut", "zoom_blur"]
    else:
        opts = ["cut"]                  # same place, same story beat: a hard cut (the camera move carries the edit); dips are for jumps in time, place or mood
    if len(opts) > 1 and rng.random() < 0.28:
        opts = [opts[1], opts[0]] + opts[2:]
    if mt["climax"] and not hint and st["flash"] < max(1, int(0.03 * n)) and i - st["last_flash"] > 25:
        opts = ["flash"] + opts
    opts = list(dict.fromkeys(opts)) + [t for t in ("cut", "soft", "dissolve", "fade") if t not in opts]
    for t in opts:
        if st["run_t"] == t and st["run"] >= (MAX_CUT_RUN if t == "cut" else MAX_RUN):
            continue
        if t == "dissolve" and st["dissolve"] + 1 > DISSOLVE_MAX * (i + 1) + 1.5:
            continue
        if t in ("dissolve", "soft", "fade") and st.get("dips", 0) + 1 > DIP_MAX * (i + 1) + 1.5:
            continue
        if t == "fade" and st.get("fades", 0) + 1 > (FADE_MAX * 1.5 if mt["time_jump"] else FADE_MAX) * (i + 1) + 1.5:
            continue
        return t
    return "cut" if st["run_t"] != "cut" or st["run"] < MAX_CUT_RUN else "soft"


def direct(shots: List[dict], settings: Optional[dict] = None, seed: int = 0) -> dict:
    t0 = time.perf_counter()
    settings = settings or {}
    shots_in = copy.deepcopy(list(shots or []))
    n = len(shots_in)
    rng = random.Random(int(seed or 0) * 7919 + 17)
    metas: List[dict] = []
    for sh in shots_in:
        en, hi, blob = _texts(sh)
        hint = csv_hint(str(sh.get("prompt_en") or sh.get("prompt") or ""))
        genre, scores = _genre(blob, hint.get("energy"))
        dur = max(0.0, _f(sh.get("end")) - _f(sh.get("start")))
        e = {"neutral": 2.6, "documentary": 2.3, "history": 3.0, "travel": 2.8, "emotional": 1.9, "action": 4.2}[genre]
        e += min(1.5, 0.6 * _count(_ENERGY_UP, blob)) - min(1.0, 0.5 * _count(_ENERGY_DOWN, blob))
        if dur and dur < 2.5:
            e += 0.4
        elif dur > 6:
            e -= 0.4
        energy = hint["energy"] if "energy" in hint else int(max(1, min(5, round(e))))
        metas.append({"en": en, "blob": blob, "genre": genre, "scores": scores, "dur": dur, "energy": energy, "hint": hint,
                      "loc": _location(en, blob), "roles": _roles(en, blob), "shape": _shape(en.lower()),
                      "time_jump": bool(_TIME_JUMP.search(blob)), "memory": bool(_MEMORY.search(blob)), "climax": bool(_CLIMAX.search(blob)),
                      "low": bool(_SHAPE_LOW.search(en.lower())), "high": bool(_SHAPE_HIGH.search(en.lower()))})
    # location continuity: a shot with no location of its own continues the previous one
    cur_loc = None
    for i, (sh, mt) in enumerate(zip(shots_in, metas)):
        pic_same = i > 0 and sh.get("picture") and sh.get("picture") == shots_in[i - 1].get("picture")
        if mt["loc"] is None or pic_same:
            mt["loc"] = cur_loc if cur_loc else "unknown"
        mt["same_loc"] = i > 0 and mt["loc"] == metas[i - 1]["loc"]
        cur_loc = mt["loc"]
    bible = _build_bible(shots_in, metas)

    # stretches that keep showing one picture (one scene split into shots, or near-identical pictures in a row): each shot reframes on a different subject
    gkey = [str((sh.get("same_run") or {}).get("id") or ("scene%s" % sh.get("scene_no"))) for sh in shots_in]
    gpos: List[int] = []
    gsize: List[int] = []
    gdur: List[float] = []
    i0 = 0
    for i in range(n):
        if i and gkey[i] != gkey[i - 1]:
            i0 = i
        gpos.append(i - i0)
    for i in range(n):
        lo = i - gpos[i]
        hi = lo
        while hi + 1 < n and gkey[hi + 1] == gkey[lo]:
            hi += 1
        gsize.append(hi - lo + 1)
        gdur.append(sum(metas[k]["dur"] for k in range(lo, hi + 1)))

    cap = max(3, int(math.ceil(MAX_SHARE * n))) if n > 12 else n
    used: Counter = Counter()
    recent: List[str] = []
    prev_t = None
    last_dir: Optional[str] = None
    st = {"run_t": None, "run": 0, "dissolve": 0, "flash": 0, "last_flash": -99}
    trans_count: Counter = Counter()
    for i, (sh, mt) in enumerate(zip(shots_in, metas)):
        g, dur = mt["genre"], mt["dur"]
        hint = mt["hint"]
        fam = dict(_BASE[g])
        for sk in [mt["shape"]] + (["low"] if mt["low"] else []) + (["high"] if mt["high"] else []):
            mul = _SHAPE_MUL.get(sk, {})
            for k in list(fam):
                if k not in mul and sk in ("build", "close", "wide"):
                    fam[k] *= 0.45
            for k, m in mul.items():
                fam[k] = fam.get(k, 0.6) * m
        if dur > 5:                     # long: slow, large, calm moves
            for k in ("hold_alive", "push_in", "parallax", "arc", "pull_out", "track_lateral"):
                if k in fam:
                    fam[k] *= 1.5
            for k in ("handheld", "dolly_through"):
                if k in fam:
                    fam[k] *= 0.5
        elif 0 < dur < 2.5:             # short: decisive moves
            for k in ("dolly_through", "pan", "push_in", "handheld"):
                if k in fam:
                    fam[k] *= 1.6
            fam.pop("hold_alive", None)
            fam.pop("arc", None)
        # desired lateral direction: continue inside a location, flip at a location change
        if mt["same_loc"] and last_dir:
            want = last_dir
        else:
            want = "r" if last_dir == "l" else "l" if last_dir == "r" else ("l" if rng.random() < 0.5 else "r")
        if "dir" in hint and hint["dir"] in ("l", "r"):
            want = hint["dir"]
        weights: Dict[str, float] = {}
        for k, w in fam.items():
            names = _FAMILY_NAMES.get(k)
            if names:
                weights[names[0] if want == "l" else names[1]] = w
                weights[names[1] if want == "l" else names[0]] = w * 0.06
            else:
                weights[k] = w
        for k in list(weights):
            if k == prev_t or used[k] >= cap:
                weights.pop(k)
                continue
            weights[k] *= (0.35 ** sum(1 for r in recent[-5:] if r == k)) * max(0.12, 1 - used[k] / float(cap))
        if not weights:                 # relax the cap, still never the same twice
            weights = {k: 1.0 for k in TREATMENTS if k != prev_t}
        tname = None
        ht = hint.get("treatment")
        if ht in TREATMENTS and ht != prev_t and used[ht] < cap:
            tname = ht
        if tname is None:
            tname = _pick(rng, weights)
        # tparams
        d: Optional[str] = None
        if tname in _DIRECTIONAL:
            d = _DIRECTIONAL[tname]
        elif tname in ("track_lateral", "arc"):
            d = want
        elif tname == "tilt_up" or tname == "reveal_up":
            d = "up"
        elif tname == "tilt_down":
            d = "down"
        if d in ("l", "r"):
            last_dir = d
        amount = 0.28 + 0.09 * mt["energy"] + (0.14 if dur > 5 else 0.0) + (0.1 if 0 < dur < 2.5 else 0.0) + rng.uniform(-0.05, 0.05)
        if tname in ("hold_alive", "handheld"):
            amount *= 0.6
        amount = round(max(0.1, min(1.0, amount)), 2)
        if tname == "hold_alive":
            ease = "smooth"
        elif 0 < dur < 2.5:
            ease = "out"
        elif g == "action":
            ease = "in" if rng.random() < 0.4 else "linear"
        elif dur > 5 or g == "emotional":
            ease = "smooth"
        else:
            ease = rng.choice(("smooth", "linear", "smooth", "out"))
        tp = {"amount": amount, "ease": ease}
        if d:
            tp["dir"] = d
        reframe = gsize[i] >= 2 and gdur[i] >= 4.5      # long stay on one picture: a different subject and a different tightness every shot
        if reframe:
            tp["focus_rank"] = gpos[i]
            tp["amount"] = round(0.3 if gpos[i] % 2 == 0 else 0.62, 2)
        used[tname] += 1
        recent.append(tname)
        prev_t = tname
        # env
        env_sc = {k: _count(rx, mt["blob"]) for k, rx in _ENV.items()}
        env = [k for k, c in sorted(env_sc.items(), key=lambda kv: (-kv[1], kv[0])) if c >= 1][:2]
        # transition
        tr = "cut" if settings.get("story_cuts_only") else _choose_transition(rng, mt, metas[i - 1] if i else mt, i, st, n)
        if reframe and gpos[i] > 0 and not hint.get("transition") and not settings.get("story_cuts_only"):
            tr = "cut"                  # the same picture reframed: a jump cut
        if tr == st["run_t"]:
            st["run"] += 1
        else:
            st["run_t"], st["run"] = tr, 1
        if tr == "dissolve":
            st["dissolve"] += 1
        if tr in ("dissolve", "soft", "fade"):
            st["dips"] = st.get("dips", 0) + 1
        if tr == "fade":
            st["fades"] = st.get("fades", 0) + 1
        if tr == "flash":
            st["flash"] += 1
            st["last_flash"] = i
        trans_count[tr] += 1
        sh["genre"] = g
        sh["energy"] = mt["energy"]
        sh["treatment"] = tname
        sh["tparams"] = tp
        sh["env"] = env
        sh["transition_in"] = tr
        sh["continuity"] = {"location": mt["loc"], "characters": mt["roles"], "same_location_as_prev": bool(mt["same_loc"]),
                            "carry_dir": d if d in ("l", "r") else (last_dir if mt["same_loc"] else None)}
        sh["ai_video"] = None

    # ---- continuity: how each shot JOINS the one before it (follow / closeup-to-context / screen focus / match cut / real dissolve ...). Dips through black are
    # kept only for true scene breaks, and for transitions a CSV hint asked for; every other join is a hard cut whose camera ends match (compose.py / bridge.py).
    cont_stats = None
    if str(settings.get("story_continuity", True)).lower() not in ("false", "0", "off", "no", "none"):
        try:
            try:
                from story_fast import continuity as _C
            except ImportError:
                from . import continuity as _C
            before = [sh.get("transition_in") for sh in shots_in]
            edits = _C.plan_edits(shots_in, settings)
            _C.apply(shots_in, edits, settings)
            for sh, mt, b in zip(shots_in, metas, before):
                if mt["hint"].get("transition"):
                    sh["transition_in"] = b                    # an explicit MOTION/transition tag in the CSV is the author's call
            trans_count = Counter(sh["transition_in"] for sh in shots_in)
            cont_stats = _C.summary(edits)
        except Exception:       # noqa: BLE001  - the director's own transitions stay
            cont_stats = None

    # ---- AI video: only shots that truly need real movement, inside the budget
    budget = int(_f(settings.get("story_ai_video_max"), 0))
    cands = []
    for i, (sh, mt) in enumerate(zip(shots_in, metas)):
        real = bool(mt["hint"].get("needs_real_movement"))
        sc = 0.0
        if real:
            sc += 4.0
        person = bool(_PERSON.search(mt["blob"]))
        mv = _count(_REAL_MOVE, mt["en"].lower()) + _count(_REAL_MOVE_DEV, mt["blob"])
        if mv and person:
            sc += 1.5 + min(2.0, 0.7 * mv)
        elif mv:
            sc += 0.8
        if sc <= 0:
            continue
        sc += 0.4 * mt["energy"] + (0.6 if mt["genre"] == "action" else 0.0)
        cands.append((-sc, i, sc, real, mv))
    cands.sort()
    if budget > 0:
        for _, i, sc, real, mv in cands[:budget]:
            sh, mt = shots_in[i], metas[i]
            sh["ai_video"] = {"reason": "hint: needs-real-movement" if real else "real movement (%d cue%s)" % (mv, "" if mv == 1 else "s"),
                              "prompt": (mt["en"] + ". Natural, believable motion of the subject, steady cinematic camera.").strip(),
                              "seconds": round(max(2.0, min(5.0, mt["dur"] or 4.0)), 1), "priority": round(sc, 2)}

    shares = {k: round(v / float(max(1, n)), 3) for k, v in used.items()}
    stats = {"shots": n, "treatments": dict(used), "transitions": dict(trans_count),
             "genres": dict(Counter(m["genre"] for m in metas)), "max_treatment_share": max(shares.values()) if shares else 0.0,
             "ai_video": sum(1 for s in shots_in if s["ai_video"]), "ai_video_candidates": len(cands), "ai_video_budget": budget,
             "locations": len({m["loc"] for m in metas}), "continuity": cont_stats, "seconds": round(time.perf_counter() - t0, 4)}
    return {"shots": shots_in, "stats": stats, "bible": bible}
