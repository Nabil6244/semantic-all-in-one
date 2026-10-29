"""Story director for the paper-cutout puppet: one protagonist who FOLLOWS THE NARRATION and LINKS neighbouring pictures like a journey.

plan_story(scenes, words, settings, log) -> {"protagonist": {...}, "scenes": {scene_no: {...}}, "links": [(a, b), ...], "info": {...}}

  scenes   [{scene_no, start, end, script_segment, prompt, still?}]   (seconds on the final timeline; "text" is accepted instead of script_segment)
  words    Whisper words: [[word, start, end], ...] or [{"word", "start", "end"}]   (timeline seconds; missing -> spread evenly over each scene)
  settings {"intensity": low|medium|high, "character": "auto"|name, "seed": int?, "rows": [csv rows with character_action/character/character_ground]?}

Each planned scene = {"character", "action", "direction", "beats": [{t0, t1, action, x0, x1, params}], "enter", "exit", "y", "char_h", "prop", "why": [phrase per beat],
"journey": id|None}. Beat times are seconds from the start of that scene's clip. A journey is a run of 2-4 consecutive scenes: the figure leaves scene N through one
side at walking speed and enters scene N+1 from the opposite side at the same speed, height, row and direction, so the cut reads as one walk.
Everything is deterministic for a seed, and any exception gives an empty plan: a story problem never stops a render.
"""
from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

STORY_VERSION = "1"
INTENSITY = {"low": {"rate": 0.6, "journeys": 1}, "medium": {"rate": 1.3, "journeys": 2}, "high": {"rate": 2.0, "journeys": 3}}   # appearances per minute / journeys per 4.5 min
MIN_SCENE_S = 3.0
MIN_SINGLE_S = 3.5
OFF_L, OFF_R = -0.14, 1.14            # just outside the frame
WALK_SPEED = 0.15                     # frame widths per second
MAX_WALK, MAX_RUN = 0.3, 0.5
PRESENCE = 9.0          # a figure that has to walk in and out of a long picture appears only for the last stretch of it
PRESENCE_HOLD = 4.0     # seconds a figure stays after arriving when it is not tied to a cut
JOURNEY_Y, CHAR_H = 0.86, 0.42
ACTION_LEN = {"look_around": 2.0, "point": 1.7, "pick_up": 1.7, "put_down": 1.6, "wave": 1.6, "turn": 1.0, "stop": 0.9}


# ---- text helpers ---------------------------------------------------------------------------------------------------------------------------

def norm(w: str) -> str:
    """Lower-case, no punctuation, Devanagari without nukta / chandrabindu / anusvara (so पहुँचता == पहुचता, चढ़ता == चढता)."""
    s = unicodedata.normalize("NFD", str(w or "")).lower()
    s = "".join(c for c in s if c not in "़ँं")
    s = unicodedata.normalize("NFC", s)
    return "".join(c for c in s if unicodedata.category(c)[0] in "LMN")


def _set(*ws: str) -> frozenset:
    return frozenset(norm(w) for w in ws)


def _pre(*ws: str) -> Tuple[str, ...]:
    return tuple(norm(w) for w in ws)


# kind -> (exact words, prefixes). First kind that matches a word wins (checked in this order).
MOVE_EXACT = _set("जाता", "जाती", "जाते", "जाना", "जाए", "जाएगा", "जाएगी", "जाएंगे", "जाएँगे", "जाऊँगा", "आता", "आती", "आते", "आना", "आया", "आई", "आए", "आएगा",
                  "go", "goes", "going", "went", "come", "comes", "came", "coming", "gone")
MOVE_PRE = _pre("पहुँच", "निकल", "चलता", "चलती", "चलते", "चलना", "चढ़", "उतर", "लौट", "घुस", "रेंग", "बढ़ता", "बढ़ती", "भाग", "दौड़", "गुज़र", "टहल",
                "सफ़र", "यात्रा", "walk", "run", "enter", "arriv", "reach", "leav", "travel", "climb", "head", "move", "cross", "return", "wander", "step", "drive", "board", "exit")
WEAK_EXACT = _set("गया", "गई", "गए", "गयी")        # "हो गई" is only an auxiliary: counts for half
ARRIVE_PRE = _pre("पहुँच", "arriv", "reach", "लौट", "return")
PICK_PRE = _pre("उठा", "पकड़", "थाम", "pick", "lift", "carr", "grab", "लेकर", "ले जा")
PUT_PRE = _pre("रख", "छोड़", "डिलीवर", "deliver", "drop", "place", "बाँट", "सौंप")
PUT_EXACT = _set("पहुँचा", "पहुँचाता", "पहुँचाती", "पहुँचाएगा", "पहुँचाने")
LOOK_PRE = _pre("देखिए", "देखिये", "देखें", "देखो", "देखत", "ध्यान", "notice", "look", "watch", "see", "साफ़ दिख", "खोजत", "ढूँढ़", "तलाश", "सोच")
POINT_PRE = _pre("दिखाई", "दिखेग", "दिखत", "दिखा", "show", "यहाँ", "वहाँ", "here", "there", "इधर", "उधर")
WAVE_PRE = _pre("नमस्ते", "नमस्कार", "स्वागत", "अलविदा", "hello", "welcome", "goodbye", "bye", "hi")
STOP_PRE = _pre("रुक", "ठहर", "थम", "stop", "halt", "pause")
TURN_PRE = _pre("मुड़", "पलट", "turn", "spin")
BACK_PRE = _pre("लौट", "वापस", "पहले", "back", "return", "पीछे")        # the story goes back in time / returns -> the figure walks left

PROXY_PRE = _pre("बिंदु", "dot", "पार्सल", "parcel", "package", "ऑर्डर", "order", "सामान", "डिब्बा", "डिब्बे", "कूरियर", "courier", "वैन", "van", "ट्रक", "delivery", "डिलीवरी")

# the picture (English prompt)
HARD_PLAIN = re.compile(r"\b(crowds?|endless|rows of|map|maps|chart|charts|graph|diagram|infographic|skyline|aerial|clock|pocket watch|coins?|ledger|timeline|stacks? of coins|"
                        r"server racks?|bar chart|line chart|world map|football|pitches|skyscrapers?|cityscape|globe|netw?ork|data|equation|formula|portrait|photograph)\b", re.I)
SOFT_SKY = re.compile(r"\b(sky|clouds?|underwater|ocean|sea|space|stars?|moon|plane)\b", re.I)
FLOOR = re.compile(r"\b(floor|ground|street|streets|road|doorstep|door|doors|corridor|hallway|garage|yard|ranch|desert|interior|inside|pavement|sidewalk|path|stairs|staircase|"
                   r"warehouse|shop|store|storefront|counter|porch|alley|lane|field|platform|dock|room|house|city|town|landscape|workshop|office|bookshop|market|gate)\b", re.I)
PERSON_PIC = re.compile(r"\b(silhouettes?|figures?|man|men|woman|women|worker|workers|person|people|child|boy|girl|mother|father|teenager|lawyer|reporter|customers?|crowd|"
                        r"couple|family|clerk|driver)\b", re.I)
STAT_RE = re.compile(r"(%|प्रतिशत|ट्रिलियन|अरब|करोड़|लाख|हज़ार|डॉलर|million|billion|trillion|percent)", re.I)
THEMES = (("worker", re.compile(r"(गोदाम|warehouse|delivery|डिलीवरी|पार्सल|parcel|ऑर्डर|order|कर्मचारी|worker|courier|कूरियर|factory|फ़ैक्टरी|shipping|logistics)", re.I)),
          ("woman", re.compile(r"(माँ|माता|महिला|woman|mother|she\b|her\b|लड़की)", re.I)),
          ("child", re.compile(r"(बच्चा|बच्चे|child|kid|बालक)", re.I)),
          ("suit_man", re.compile(r"(कंपनी|company|ceo|business|startup|निवेश|shares?|शेयर|bank|बैंक|office|ऑफ़िस|founder|संस्थापक)", re.I)))


def _get(o: Any, k: str, d: Any = None) -> Any:
    return o.get(k, d) if isinstance(o, dict) else getattr(o, k, d)


def _rand(seed: int, *parts: Any) -> float:
    h = hashlib.sha256(("%s|" % seed + "|".join(str(p) for p in parts)).encode()).digest()
    return int.from_bytes(h[:6], "big") / float(1 << 48)


def _starts(tok: str, pres: Sequence[str]) -> bool:
    return any(tok.startswith(p) for p in pres if p)


POSTPOS = _set("में", "तक", "से", "को", "पर", "के", "की", "का", "ओर", "तरफ़", "फिर", "और", "भी", "वहाँ", "यहाँ", "अब", "वह", "वो", "यह", "ये", "कभी", "सीधे", "धीरे")
NEGATE = _set("नहीं", "न", "ना", "मत", "never", "not")
AUX_MOVE = _set("जाता", "जाती", "जाते", "जाना", "जाए", "जाएगा", "जाएगी", "जाएंगे", "जाएँगे", "गया", "गई", "गए", "गयी", "गई।")


def _passive_or_negated(toks: List[str], i: int) -> bool:
    """"समझा जाता" (passive), "हो गई" (auxiliary), "कभी नहीं जाएँगे" (negation) are not somebody walking."""
    tok = toks[i]
    if any(t in NEGATE for t in toks[max(0, i - 2):i]) or (i + 1 < len(toks) and toks[i + 1] in NEGATE):
        return True
    if tok in AUX_MOVE and i > 0:
        prev = toks[i - 1]
        if prev in POSTPOS:
            return False
        if len(prev) > 2 and prev[-1] in "ाेीो" or prev in _set("हो", "बन", "कर", "ढह", "बढ़", "खत्म", "टिक", "टूट", "गिर", "जारी"):
            return True
    return False


def _is_move(tok: str) -> bool:
    return tok in MOVE_EXACT or _starts(tok, MOVE_PRE)


def normalize_words(words: Any) -> List[Tuple[str, float, float]]:
    out = []
    for w in words or []:
        try:
            if isinstance(w, dict):
                txt, a, b = w.get("word", w.get("text", "")), w.get("start"), w.get("end")
            else:
                txt, a, b = w[0], w[1], w[2]
            if a is None:
                continue
            out.append((str(txt).strip(), float(a), float(b if b is not None else a)))
        except Exception:      # noqa: BLE001
            continue
    out.sort(key=lambda x: x[1])
    return out


def even_words(text: str, start: float, end: float) -> List[Tuple[str, float, float]]:
    toks = str(text or "").split()
    if not toks:
        return []
    step = (end - start) / len(toks)
    return [(t, start + i * step, start + (i + 1) * step) for i, t in enumerate(toks)]


def scene_words(sc: dict, all_words: List[Tuple[str, float, float]]) -> List[Tuple[str, float, float]]:
    """The scene's script words with times. The script (CSV) text is the truth about WHAT is said (Whisper spells Hindi phonetically and drops words), Whisper says
    WHEN: tokens are spread over the span the scene's Whisper words cover (by letters), then snapped to a Whisper word that sounds the same (+-2.5 s)."""
    a, b = sc["start"], sc["end"]
    own = [w for w in all_words if a - 0.02 <= w[1] < b - 0.02]
    toks = str(sc["text"] or "").split()
    if not toks:
        return own
    lo, hi = a, b
    if len(own) >= 3 and 0.5 <= len(own) / len(toks) <= 2.0:
        lo, hi = max(a, own[0][1]), min(b, max(own[-1][2], own[0][1] + 0.5))
    weights = [max(1, len(norm(t))) for t in toks]
    total, acc, out = float(sum(weights)), 0.0, []
    for t, wgt in zip(toks, weights):
        t0 = lo + (hi - lo) * acc / total
        acc += wgt
        t1 = lo + (hi - lo) * acc / total
        best, bd = None, 9.0
        nt = norm(t)
        if own and len(nt) >= 3:
            for w in own:
                if abs(w[1] - t0) <= 2.5 and abs(w[1] - t0) < bd and SequenceMatcher(None, nt, norm(w[0])).ratio() >= 0.74:
                    best, bd = w, abs(w[1] - t0)
        out.append((t, best[1], best[2]) if best else (t, t0, t1))
    out.sort(key=lambda x: x[1])
    return out


# ---- re-alignment: when is each scene's script really spoken? --------------------------------------------------------------------------------
# The app cuts clips at its own scene boundaries, but Whisper spells Hindi phonetically so the app's aligner interpolates many boundaries. Here every script word is
# matched (monotonic DP) onto the Whisper words by the SOUND of its consonants, which survives Whisper's spelling (अमेजन ~ Amazon, पहुंचता ~ पहुँचता).

_DEV_CONS = {}
for _chars, _k in (("कख", "K"), ("गघ", "G"), ("चछ", "C"), ("जझ", "J"), ("टठतथ", "T"), ("डढदध", "D"), ("णन", "N"), ("पफ", "P"), ("बभ", "B"), ("म", "M"), ("य", "Y"),
                   ("रऱ", "R"), ("लळ", "L"), ("व", "V"), ("शषस", "S"), ("ह", "H"), ("ङञ", "N")):
    for _c in _chars:
        _DEV_CONS[_c] = _k
_DEV_CONS.update({"ड़": "D", "ढ़": "D", "क़": "K", "ख़": "K", "ग़": "G", "ज़": "J", "फ़": "P"})
_DEV_VOWELS = set("अआइईउऊऋएऐओऔऑ")
_LAT_DIGRAPH = (("sh", "S"), ("ch", "C"), ("th", "T"), ("dh", "D"), ("ph", "P"), ("bh", "B"), ("kh", "K"), ("gh", "G"), ("ck", "K"), ("ee", ""), ("oo", ""))
_LAT = {"k": "K", "c": "K", "q": "K", "g": "G", "j": "J", "z": "J", "t": "T", "d": "D", "n": "N", "p": "P", "f": "P", "b": "B", "m": "M", "y": "Y", "r": "R", "l": "L",
        "v": "V", "w": "V", "s": "S", "x": "KS", "h": "H"}


def phon_key(word: str) -> str:
    """Coarse consonant skeleton of a Hindi / English word: matras, nasal marks, nukta, aspiration and dental-vs-retroflex differences are ignored."""
    s = unicodedata.normalize("NFC", str(word or "")).lower()
    out: List[str] = []
    if any("ऀ" <= c <= "ॿ" for c in s):
        s = s.replace("़", "")
        for i, c in enumerate(s):
            if c in _DEV_CONS:
                out.append(_DEV_CONS[c])
            elif c in _DEV_VOWELS and not out:
                out.append("A")
            elif "a" <= c <= "z":
                out.extend(_lat_key(c))
        return "".join(out)
    return "".join(_lat_key(s))


def _lat_key(s: str) -> List[str]:
    s = re.sub(r"[^a-z]", "", s)
    for dg, k in _LAT_DIGRAPH:
        s = s.replace(dg, k.lower() if k else "")
    out: List[str] = []
    for c in s:
        if c.isupper():
            out.append(c)
        elif c in _LAT:
            out.append(_LAT[c])
        elif c in "aeiou" and not out:
            out.append("A")
    return out


def _key_sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if len(a) <= 2 or len(b) <= 2:
        return 1.0 if a == b else (0.55 if (a in b or b in a) and min(len(a), len(b)) >= 2 else 0.0)
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


ALIGN_BAND = 60.0          # seconds around the app's own scene window in which a script word may be found
MATCH_BASE = 1.1           # a match is worth wt * (2 * sim - MATCH_BASE)
SKIP_SCRIPT = 0.35         # per weight: a script word nobody said (Whisper dropped it)
SKIP_WHISPER = 0.04        # a Whisper word with no script word (noise, a repeat)


def realign(sc: List[dict], allw: List[Tuple[str, float, float]]) -> Optional[Dict[Any, dict]]:
    """-> {scene_no: {words: [(tok, t0, t1, matched)], speech_start, speech_end, cov, in_frac, foreign, timing_ok, reason}} or None (no Whisper words).
    A scene's real speech is where ITS script words are spoken; in_frac is the share of them (by letters) inside the app's clip window; foreign is the share of the
    window covered by Whisper words that belong to other scenes."""
    import bisect
    if not allw or not sc:
        return None
    import numpy as np
    toks: List[Tuple[int, str, str, int]] = []         # (scene idx, raw, key, weight)
    for s in sc:
        for raw in str(s["text"] or "").split():
            k = phon_key(raw)
            has_digit = any(c.isdigit() for c in raw)
            toks.append((s["idx"], raw, k, 0 if (has_digit or not k) else min(4, max(1, len(k)))))
    n, m = len(toks), len(allw)
    if n == 0:
        return None
    wkeys = [phon_key(w[0]) for w in allw]
    wstart = [w[1] for w in allw]
    NEG = -1e9
    H = np.full((n + 1, m + 1), NEG)
    H[0, :] = 0.0
    BT = np.zeros((n + 1, m + 1), dtype=np.int8)       # 1 diag, 2 up (script word skipped), 3 left (whisper word skipped)
    lo_prev = 0
    scene_by_idx = {s["idx"]: s for s in sc}
    sim_cache: Dict[Tuple[str, str], float] = {}
    for i in range(1, n + 1):
        si, raw, key, wt = toks[i - 1]
        s = scene_by_idx[si]
        jlo = max(lo_prev, bisect.bisect_left(wstart, s["start"] - ALIGN_BAND))
        jhi = bisect.bisect_right(wstart, s["end"] + ALIGN_BAND)
        lo_prev = jlo
        if jhi <= jlo:
            jhi = min(m, jlo + 1)
        gs = SKIP_SCRIPT * wt
        for j in range(jlo, jhi + 1):
            best, how = NEG, 0
            up = H[i - 1, j]
            if up > NEG / 2:
                best, how = up - gs, 2
            if j > 0:
                d = H[i - 1, j - 1]
                if d > NEG / 2 and wt > 0 and j - 1 >= jlo - 1:
                    ck = (key, wkeys[j - 1])
                    sim = sim_cache.get(ck)
                    if sim is None:
                        sim = sim_cache[ck] = _key_sim(*ck)
                    v = d + wt * (2.0 * sim - MATCH_BASE)
                    if sim >= 0.6 and v > best:
                        best, how = v, 1
                lf = H[i, j - 1]
                if lf > NEG / 2 and lf - SKIP_WHISPER > best:
                    best, how = lf - SKIP_WHISPER, 3
            H[i, j], BT[i, j] = best, how
    j = int(np.argmax(H[n]))
    i = n
    match: Dict[int, Tuple[int, float]] = {}
    while i > 0 and j >= 0:
        how = BT[i, j]
        if how == 1:
            match[i - 1] = (j - 1, _key_sim(toks[i - 1][2], wkeys[j - 1]))
            i, j = i - 1, j - 1
        elif how == 2:
            i -= 1
        elif how == 3:
            j -= 1
        else:
            break
    # times: matched words take the Whisper word's time, the rest are spread between their matched neighbours by letters
    t0s: List[Optional[float]] = [None] * n
    t1s: List[Optional[float]] = [None] * n
    for k, (jw, _) in match.items():
        t0s[k], t1s[k] = allw[jw][1], allw[jw][2]
    known = [k for k in range(n) if t0s[k] is not None]
    wlet = [max(1, len(norm(t[1]))) for t in toks]
    if not known:
        return {s["scene_no"]: _empty_timing(s, "no script word could be found in the speech") for s in sc}
    for a_, b_ in zip([-1] + known, known + [n]):
        gap = list(range(a_ + 1, b_))
        if not gap:
            continue
        left = t1s[a_] if a_ >= 0 else (t0s[b_] - 0.3 * sum(wlet[g] for g in gap) / 3.0 if b_ < n else 0.0)
        right = t0s[b_] if b_ < n else left + 0.3 * sum(wlet[g] for g in gap) / 3.0
        right = max(right, left)
        tot, acc = float(sum(wlet[g] for g in gap)), 0.0
        for g in gap:
            t0s[g] = left + (right - left) * acc / tot
            acc += wlet[g]
            t1s[g] = left + (right - left) * acc / tot
    result: Dict[Any, dict] = {}
    for s in sc:
        idxs = [k for k in range(n) if toks[k][0] == s["idx"]]
        if not idxs:
            result[s["scene_no"]] = _empty_timing(s, "no script text")
            continue
        words = [(toks[k][1], float(t0s[k]), float(t1s[k]), k in match and match[k][1] >= 0.62) for k in idxs]
        tot = float(sum(wlet[k] for k in idxs))
        mw = float(sum(wlet[k] for k in idxs if k in match and match[k][1] >= 0.62))
        cov = mw / tot
        a, b = s["start"], s["end"]
        if cov < 0.35:
            lo_k = max([k for k in match if toks[k][0] < s["idx"]] or [-1])
            hi_k = min([k for k in match if toks[k][0] > s["idx"]] or [n])
            left = float(allw[match[lo_k][0]][2]) if lo_k >= 0 else a
            right = float(allw[match[hi_k][0]][1]) if hi_k < n else b
            if right - left > 1.0:           # spread over the stretch between the heard neighbours (not by one stray match inside it)
                acc, new_words = 0.0, []
                for k, w in zip(idxs, words):
                    t_a = left + (right - left) * acc / tot
                    acc += wlet[k]
                    new_words.append((w[0], t_a, left + (right - left) * acc / tot, False))
                words = new_words
        inw = float(sum(wlet[k] for k, w in zip(idxs, words) if a - 0.15 <= (w[1] + w[2]) / 2 <= b + 0.15))
        in_frac = inw / tot
        conf = [w for w in words if w[3]]
        sp0 = min((w[1] for w in conf), default=None)
        sp1 = max((w[2] for w in conf), default=None)
        foreign = 0.0
        if b > a:
            cover = 0.0
            owner = {jw: toks[k][0] for k, (jw, _) in match.items()}
            for jw in range(bisect.bisect_left(wstart, a), min(m, bisect.bisect_right(wstart, b))):
                if owner.get(jw, s["idx"]) != s["idx"]:
                    cover += max(0.0, min(allw[jw][2], b) - max(allw[jw][1], a))
            foreign = min(1.0, cover / (b - a))
        reason = ""
        ok = True
        trust = "heard"
        disp = max(0.0, a - sp0, sp1 - b, 0.0) if sp0 is not None else 0.0
        if cov < 0.35:
            # Whisper often drops a long stretch of speech. Its words are then placed between the neighbours that WERE heard; that is only believable when the stretch fits
            # the clip and the speed of speech is human.
            span = words[-1][2] - words[0][1]
            expected = tot / 11.0
            if in_frac >= 0.9 and foreign <= 0.35 and 0.5 <= span / max(0.5, expected) <= 2.0:
                trust, reason = "inferred", "speech not heard by Whisper; placed between its heard neighbours"
                sp0, sp1 = words[0][1], words[-1][2]
            else:
                ok, reason = False, f"only {cov:.0%} of its words could be found in the speech"
        elif not (in_frac >= 0.9 or (in_frac >= 0.7 and disp <= 2.0)):
            ok = False
            reason = (f"its speech is at {sp0:.1f}-{sp1:.1f}s but the clip is {a:.1f}-{b:.1f}s ({in_frac:.0%} of the words inside)" if sp0 is not None
                      else f"{in_frac:.0%} of the words inside the clip")
        if ok and foreign > 0.5:
            ok, reason = False, f"{foreign:.0%} of the clip plays other scenes' speech"
        result[s["scene_no"]] = {"words": words, "speech_start": sp0, "speech_end": sp1, "cov": round(cov, 3), "in_frac": round(in_frac, 3), "foreign": round(foreign, 3),
                                 "timing_ok": ok, "trust": trust, "reason": reason, "app_start": a, "app_end": b}
    return result


def _empty_timing(s: dict, why: str) -> dict:
    return {"words": [], "speech_start": None, "speech_end": None, "cov": 0.0, "in_frac": 0.0, "foreign": 0.0, "timing_ok": False, "reason": why,
            "app_start": s["start"], "app_end": s["end"]}


def timing_report(scenes: Sequence[Any], words: Any) -> str:
    sc = _prep(scenes)
    tm = realign(sc, normalize_words(words)) or {}
    lines = ["scene  app window        real speech       cov  in  foreign  ok"]
    for s in sc:
        t = tm.get(s["scene_no"])
        if not t:
            continue
        real = f"{t['speech_start']:6.1f}-{t['speech_end']:6.1f}" if t["speech_start"] is not None else "      -      "
        lines.append(f"{str(s['scene_no']):>5}  {s['start']:6.1f}-{s['end']:6.1f}  {real}  {t['cov']:.2f} {t['in_frac']:.2f}  {t['foreign']:.2f}   {'ok' if t['timing_ok'] else 'MISALIGNED ' + t['reason']}")
    return "\n".join(lines)


# ---- narration -> triggers ------------------------------------------------------------------------------------------------------------------

def triggers(ws: List[Tuple[str, float, float]], t0: float) -> List[dict]:
    """Narration words of one scene -> [{t (scene-local sec), kind, w, phrase, back}] in time order. kind: move|arrive|pick|put|look|point|wave|stop|turn."""
    out: List[dict] = []
    toks = [norm(w[0]) for w in ws]
    for i, (raw, a, b) in enumerate(ws):
        tok = toks[i]
        if not tok:
            continue
        kinds: List[Tuple[str, float]] = []
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        deliver = tok in PUT_EXACT or (tok == norm("पहुँचा") and (nxt.startswith(norm("सक")) or nxt.startswith(norm("दे")) or nxt.startswith(norm("द"))))
        if deliver or _starts(tok, PUT_PRE):
            kinds.append(("put", 2.0))
        if _starts(tok, PICK_PRE):
            kinds.append(("pick", 2.0))
        if _starts(tok, ARRIVE_PRE) and not deliver:
            kinds.append(("arrive", 1.0))
        if (_is_move(tok) or tok in WEAK_EXACT) and not deliver and not _passive_or_negated(toks, i):
            kinds.append(("move", 0.7 if tok in WEAK_EXACT else 2.0))
        if _starts(tok, WAVE_PRE) and len(tok) > 2:
            kinds.append(("wave", 2.0))
        if _starts(tok, STOP_PRE):
            kinds.append(("stop", 0.5))
        if _starts(tok, TURN_PRE):
            kinds.append(("turn", 0.5))
        if _starts(tok, LOOK_PRE) and len(tok) > 2:
            kinds.append(("look", 0.5))
        if _starts(tok, POINT_PRE) and len(tok) > 2:
            kinds.append(("point", 0.5))
        for kind, wt in kinds:
            prev = ws[i - 1][0] if i else ""
            phrase = (prev + " " + raw).strip() if prev else raw
            out.append({"t": max(0.0, a - t0), "kind": kind, "w": wt, "phrase": phrase, "back": _starts(tok, BACK_PRE) or (i > 0 and _starts(toks[i - 1], BACK_PRE))})
    return out


def _sum(trs: List[dict], *kinds: str) -> float:
    return sum(t["w"] for t in trs if t["kind"] in kinds)


# ---- scene analysis -------------------------------------------------------------------------------------------------------------------------

def analyse(sc: dict, ws: List[Tuple[str, float, float]]) -> dict:
    trs = triggers(ws, sc["start"])
    prompt, text = sc.get("prompt", "") or "", sc.get("text", "") or ""
    dur = sc["end"] - sc["start"]
    hard = bool(HARD_PLAIN.search(prompt)) or bool(STAT_RE.search(text))
    floor = 1.0 if FLOOR.search(prompt) else 0.0
    sky = 1.0 if SOFT_SKY.search(prompt) else 0.0
    person = bool(PERSON_PIC.search(prompt))
    toks = [norm(w[0]) for w in ws]
    proxy = any(_starts(t, PROXY_PRE) for t in toks)
    move = min(4.0, _sum(trs, "move"))
    handle = min(4.0, _sum(trs, "pick", "put", "wave"))
    arrive = _sum(trs, "arrive")
    back = any(t["back"] for t in trs if t["kind"] in ("move", "arrive"))
    score = move + handle + 0.5 * arrive + floor - sky - (2.0 if person and move < 2 else 0.0) + (0.5 if proxy and move else 0.0)
    return {"dur": dur, "trs": trs, "hard": hard, "floor": floor, "sky": sky, "person": person, "move": move, "handle": handle, "arrive": arrive, "back": back,
            "score": score, "proxy": proxy}


def _relaxed_ok(a: dict) -> bool:
    return (not a["hard"] and a["dur"] >= MIN_SCENE_S and a.get("timing_ok", True) and a.get("lane_ok", True)
            and not (a["person"] and a["move"] < 1 and a["handle"] < 1 and not a["floor"]))


def _single_ok(a: dict) -> bool:
    return (not a["hard"] and a["dur"] >= MIN_SINGLE_S and a.get("timing_ok", True) and a.get("lane_ok", True)
            and (a["move"] + a["handle"]) >= 2.0 and a["score"] >= 2.5)


# ---- protagonist ----------------------------------------------------------------------------------------------------------------------------

def pick_protagonist(scenes: Sequence[dict], settings: dict, characters: Sequence[str]) -> dict:
    want = str(settings.get("character") or "auto").strip()
    chars = list(characters) or ["worker"]
    if want.lower() not in ("", "auto"):
        for c in chars:
            if c.lower() == want.lower():
                return {"character": c, "why": "set by the user"}
    blob = " ".join((s.get("text", "") + " " + s.get("prompt", "")) for s in scenes)
    scores = {name: len(rx.findall(blob)) for name, rx in THEMES}
    best = max(scores, key=lambda k: (scores[k], k == "worker"))
    if scores[best] == 0 or best not in chars:
        best = "worker" if "worker" in chars else chars[0]
    return {"character": best, "why": f"narration theme ({best}: {scores.get(best, 0)} cues)"}


# ---- walking lanes --------------------------------------------------------------------------------------------------------------------------
# health_cinema.puppet.lanes.lane_for(still, scene_no, overrides, project_dir) -> {x0, x1, y, h_hint, avoid: [[a, b], ...], conf, source} or None (no floor: never place a
# character). Imported lazily: without the module (or a settings["lane_fn"]) the story behaves as before.
LANE_MIN_W = 0.3
LANE_MIN_CONF = 0.25
LANE_EDGE = 0.04          # a lane that reaches within this of the frame edge is open: the figure may walk in from outside
JOIN_EDGE = 0.2           # a journey crosses a cut only where both lanes reach within this of the edge
JOIN_DY = 0.07            # ... and stand on (almost) the same floor line
AVOID_PAD = 0.04


def lane_source(st: dict) -> Optional[Callable[..., Any]]:
    fn = st.get("lane_fn")
    if callable(fn):
        return fn
    if fn is False:
        return None          # lanes switched off explicitly
    try:
        from health_cinema.puppet import lanes as _lanes
        f = getattr(_lanes, "lane_for", None)
        return f if callable(f) else None
    except Exception:       # noqa: BLE001 - module not there (yet)
        return None


def project_dir_for(still: Any, st: dict) -> Optional[str]:
    if st.get("project_dir"):
        return str(st["project_dir"])
    try:
        from pathlib import Path
        for par in list(Path(str(still)).resolve().parents)[:3]:
            if (par / "state").is_dir():
                return str(par)
    except Exception:       # noqa: BLE001
        pass
    return None


def fetch_lane(fn: Callable[..., Any], s: dict, st: dict) -> Optional[dict]:
    """The normalised lane of one scene's picture, or None (no usable floor)."""
    try:
        kw = dict(scene_no=s["scene_no"], overrides=st.get("lane_overrides"), project_dir=project_dir_for(s.get("still"), st))
        try:
            raw = fn(s.get("still"), **kw)
        except TypeError:
            raw = fn(s.get("still"))
        if not isinstance(raw, dict):
            return None
        x0, x1, y = float(raw["x0"]), float(raw["x1"]), float(raw["y"])
        x0, x1 = max(-0.2, min(x0, x1)), min(1.2, max(x0, x1))
        conf = 1.0 if raw.get("conf") is None else float(raw.get("conf"))
        if x1 - x0 < LANE_MIN_W or conf < LANE_MIN_CONF or not (0.3 <= y <= 1.05):
            return None
        av = sorted([min(float(a), float(b)), max(float(a), float(b))] for a, b in (raw.get("avoid") or []))
        return {"x0": round(x0, 4), "x1": round(x1, 4), "y": round(y, 4), "h_hint": float(raw.get("h_hint") or CHAR_H), "avoid": av, "conf": round(conf, 3),
                "source": str(raw.get("source", ""))}
    except Exception:       # noqa: BLE001 - a broken lane means "no lane", never a crash
        return None


def lane_u(lane: Optional[dict], s: int) -> Optional[dict]:
    """The lane in walking coordinates (mirrored when the figure walks left): lo/hi = floor span, in/out = where the figure enters / leaves."""
    if not lane:
        return None
    x0, x1, av = lane["x0"], lane["x1"], lane["avoid"]
    if s < 0:
        x0, x1, av = 1.0 - x1, 1.0 - x0, sorted([1.0 - b, 1.0 - a] for a, b in av)
    return {"lo": x0, "hi": x1, "avoid": av, "in": OFF_L if x0 <= LANE_EDGE else x0, "out": OFF_R if x1 >= 1.0 - LANE_EDGE else x1}


def pick_stand(lu: Optional[dict], seed: int, no: Any) -> Optional[float]:
    """Where the figure stands still: inside the lane, clear of every avoid span. None when no such place exists."""
    r = _rand(seed, "x", no)
    if lu is None:
        return 0.36 + 0.28 * r
    lo, hi = max(lu["lo"], 0.0), min(lu["hi"], 1.0)
    pad = 0.1 * (hi - lo)
    free = [(lo + pad, hi - pad)]
    for a, b in lu["avoid"]:
        nxt = []
        for f0, f1 in free:
            if b + AVOID_PAD <= f0 or a - AVOID_PAD >= f1:
                nxt.append((f0, f1))
                continue
            if a - AVOID_PAD > f0:
                nxt.append((f0, a - AVOID_PAD))
            if b + AVOID_PAD < f1:
                nxt.append((b + AVOID_PAD, f1))
        free = nxt
    free = [f for f in free if f[1] - f[0] >= 0.05]
    if not free:
        return None
    f0, f1 = max(free, key=lambda f: f[1] - f[0])
    return f0 + (f1 - f0) * (0.25 + 0.5 * r)


def pair_ok(a: dict, b: dict, side: int) -> bool:
    """May the figure leave picture a and arrive in picture b: both have a lane, the exit / entry edges are open, and the floor line matches."""
    if not a.get("lanes_on"):
        return True
    la, lb = a.get("lane"), b.get("lane")
    if not la or not lb or abs(la["y"] - lb["y"]) > JOIN_DY:
        return False
    if side > 0:
        return la["x1"] >= 1.0 - JOIN_EDGE and lb["x0"] <= JOIN_EDGE
    return la["x0"] <= JOIN_EDGE and lb["x1"] >= 1.0 - JOIN_EDGE


# ---- beats ----------------------------------------------------------------------------------------------------------------------------------

def _sx(x: float, s: int) -> float:
    return x if s > 0 else 1.0 - x


def build_beats(a: dict, dur: float, role: str, s: int, seed: int, no: int, speed: float, exit_side: bool, early: bool = False, lane: Optional[dict] = None) -> Tuple[List[dict], List[str], Dict[str, Any]]:
    """role: single|first|mid|last. Returns (beats, why per beat, {'ok': bool}). Positions are mirrored for s=-1 (walking left).
    The figure is on screen only around the words that drive it (at most PRESENCE seconds): long scenes never hold a standing figure.
    first/mid leave through the far side exactly at the cut (the next picture continues the walk); last/mid arrive already walking at t=0."""
    IN, OUT = (lane["in"], lane["out"]) if lane else (OFF_L, OFF_R)
    beats: List[dict] = []
    why: List[str] = []
    trs = a["trs"]
    face = "right" if s > 0 else "left"
    run_act = lambda v: "run" if v > MAX_WALK else "walk"
    fp = {"facing": face}
    first_move = next((t for t in trs if t["kind"] in ("move", "arrive")), None)
    if role == "mid":
        need = (OUT - IN) / speed
        if need > dur + 0.01:
            return [], [], {"ok": False}
        beats.append({"t0": 0.0, "t1": round(need, 3), "action": run_act(speed), "x0": _sx(IN, s), "x1": _sx(OUT, s), "params": fp})
        why.append("walks on through the picture")
        return beats, why, {"ok": True}
    links_out = role == "first"                      # must leave exactly at the cut
    exits = exit_side or links_out or (role in ("single", "last") and dur > 5.5)
    x_stop = pick_stand(lane, seed, no)
    if x_stop is None:
        return [], [], {"ok": False, "why": "no standing place clear of the avoid zones"}
    enter_dur = (x_stop - IN) / speed
    exit_dur = (OUT - x_stop) / speed if exits else 0.0
    anchor = next((t for t in trs if t["kind"] in ("put", "pick")), None)
    acts = [t for t in trs if t["kind"] in ("pick", "put", "wave", "point", "look", "turn", "stop")]
    # when does the figure come in?
    if role == "last":
        t_in = 0.0
    elif role == "first" and dur > PRESENCE:
        t_in = dur - (enter_dur + 1.2 + exit_dur)           # long picture: appear just in time to walk out at the cut
    elif anchor is not None:
        t_in = max(0.2, anchor["t"] - enter_dur)           # arrive as the carrying / delivering word is spoken
    elif first_move is not None:
        t_in = max(0.2, first_move["t"] - 0.8)
    else:
        t_in = 0.3
    if early and role != "last":
        t_in = min(t_in, 0.2)
    t_in = max(0.0, t_in)
    min_hold = 0.6
    if links_out:
        travel = (OUT - IN) / speed                       # the whole crossing at the shared speed; the hold absorbs what is left
        if t_in + travel + min_hold > dur:
            t_in = max(0.0, dur - travel - min_hold)
        if t_in + travel + 0.3 > dur:
            return [], [], {"ok": False}
    elif t_in + enter_dur + min_hold + exit_dur > dur:
        exits = False
        exit_dur = 0.0
        if t_in + enter_dur + min_hold > dur:
            enter_dur = max(0.8, dur - t_in - min_hold)
            x_stop = min(x_stop, IN + enter_dur * speed)
    t_arr = t_in + enter_dur
    beats.append({"t0": round(t_in, 3), "t1": round(t_arr, 3), "action": run_act(speed), "x0": _sx(IN, s), "x1": _sx(x_stop, s), "params": fp})
    why.append(first_move["phrase"] if (first_move and role != "last") else ("arrives from the previous picture" if role == "last" else "enters the picture"))
    # the hold ends at the cut for linked exits, otherwise soon after the last gesture
    t_cut = dur
    t_end = dur - exit_dur if links_out else min(dur - exit_dur, t_arr + PRESENCE_HOLD) if exits else dur
    cur = t_arr
    used: List[str] = []
    for tr in acts:
        act = {"pick": "pick_up", "put": "put_down", "wave": "wave", "point": "point", "look": "look_around", "turn": "turn", "stop": "stop"}[tr["kind"]]
        if tr["kind"] in ("stop", "turn", "point") and len(acts) > 2 and tr["w"] < 1:
            continue
        if tr["t"] < t_arr - 1.0 and tr["kind"] in ("look", "point", "turn", "stop"):
            continue                                         # said before the figure is there: not a gesture it can make
        ln = min(ACTION_LEN.get(act, 1.5), max(0.0, t_end - cur - 0.02))
        t0 = max(cur, min(tr["t"], t_end - ln - 0.02))
        if ln < 0.8 or t0 + ln > t_end + 1e-6 or t0 < cur - 1e-6:
            continue
        if t0 - cur > 0.15:
            beats.append({"t0": round(cur, 3), "t1": round(t0, 3), "action": "stand_idle", "x0": _sx(x_stop, s), "x1": _sx(x_stop, s), "params": fp})
            why.append("waits for the words")
        beats.append({"t0": round(t0, 3), "t1": round(t0 + ln, 3), "action": act, "x0": _sx(x_stop, s), "x1": _sx(x_stop, s), "params": fp})
        why.append(tr["phrase"])
        cur = t0 + ln
        used.append(act)
        if len(used) >= 3:
            break
    if t_end - cur > 0.15:
        if t_end - cur > 2.6 and "look_around" not in used and role != "first":
            beats.append({"t0": round(cur, 3), "t1": round(cur + 2.0, 3), "action": "look_around", "x0": _sx(x_stop, s), "x1": _sx(x_stop, s), "params": fp})
            why.append("looks around (nothing in the narration to do)")
            cur += 2.0
        if t_end - cur > 0.15:
            beats.append({"t0": round(cur, 3), "t1": round(t_end, 3), "action": "stand_idle", "x0": _sx(x_stop, s), "x1": _sx(x_stop, s), "params": fp})
            why.append("stands")
        cur = t_end
    if exits:
        t_x0 = t_end if links_out else cur
        t_x1 = t_cut if links_out else min(t_cut, t_x0 + exit_dur)
        beats.append({"t0": round(t_x0, 3), "t1": round(t_x1, 3), "action": run_act((OUT - x_stop) / max(t_x1 - t_x0, 0.01)), "x0": _sx(x_stop, s), "x1": _sx(OUT, s), "params": fp})
        why.append("leaves toward the next picture" if links_out else "walks off")
    return beats, why, {"ok": True, "x_stop": x_stop, "exits": exits, "linked_exit": links_out}


# ---- the director ---------------------------------------------------------------------------------------------------------------------------

def _prep(scenes: Sequence[Any]) -> List[dict]:
    out = []
    for i, sc in enumerate(scenes):
        no = _get(sc, "scene_no", i + 1)
        text = _get(sc, "script_segment", None)
        if text is None:
            text = _get(sc, "text", "")
        out.append({"scene_no": no, "start": float(_get(sc, "start", 0.0)), "end": float(_get(sc, "end", 0.0)), "text": str(text or ""), "prompt": str(_get(sc, "prompt", "") or ""),
                    "still": _get(sc, "still", None), "idx": i})
    return out


def plan_story(scenes: Sequence[Any], words: Any = None, settings: Optional[dict] = None, log: Optional[Callable[[str], None]] = None, characters: Optional[Sequence[str]] = None) -> dict:
    say = log or (lambda m: None)
    empty = {"protagonist": {}, "scenes": {}, "links": [], "info": {}}
    try:
        return _plan(scenes, words, dict(settings or {}), say, characters) or empty
    except Exception as exc:       # noqa: BLE001 - never stop a render
        say(f"[STORY] planning failed ({exc}); no character is used")
        return empty


def _plan(scenes: Sequence[Any], words: Any, st: dict, say: Callable[[str], None], characters: Optional[Sequence[str]]) -> dict:
    sc = _prep(scenes)
    if not sc:
        return {"protagonist": {}, "scenes": {}, "links": [], "info": {}}
    level = str(st.get("intensity") or "medium").lower()
    level = level if level in INTENSITY else "medium"
    cfg = INTENSITY[level]
    seed = st.get("seed")
    if seed is None:
        seed = int(hashlib.sha256("\n".join(s["text"] for s in sc).encode()).hexdigest()[:8], 16)
    if not isinstance(seed, int):
        seed = int(hashlib.sha256(str(seed).encode()).hexdigest()[:8], 16)
    if characters is None:
        try:
            from health_cinema import puppet as _p
            characters = list(_p.list_characters())
        except Exception:      # noqa: BLE001
            characters = ["worker", "suit_man", "woman", "child", "silhouette"]
    allw = normalize_words(words)
    prot = pick_protagonist(sc, st, characters)
    timing = None
    try:
        timing = realign(sc, allw) if allw else None
    except Exception as exc:       # noqa: BLE001 - old behaviour (even spread + snapping) when the aligner fails
        say(f"[STORY] re-alignment failed ({exc}); scene timing is used as the app has it")
    lane_fn = lane_source(st)
    lane_cache: Dict[Any, Optional[dict]] = {}
    an: Dict[Any, dict] = {}
    skipped: Dict[Any, str] = {}
    for s in sc:
        tm = (timing or {}).get(s["scene_no"])
        if tm is not None:
            lo_, hi_ = s["start"] - 0.05, s["end"] + 0.05       # a word spoken outside this clip cannot be acted on
            ws = [(w[0], w[1], w[2]) for w in tm["words"] if lo_ <= (w[1] + w[2]) / 2 <= hi_]
        else:
            ws = scene_words(s, allw)
        a = analyse(s, ws)
        a["timing"], a["timing_ok"] = tm, (tm["timing_ok"] if tm is not None else True)
        a["foreign"] = tm["foreign"] if tm is not None else 0.0
        if a["foreign"] > 0.3:
            a["score"] -= 1.0
        a["lanes_on"] = lane_fn is not None
        a["lane"], a["lane_ok"] = None, True
        if not a["hard"] and a["dur"] >= MIN_SCENE_S and not a["timing_ok"]:
            skipped[s["scene_no"]] = "timing: " + tm["reason"]
        elif lane_fn is not None and not a["hard"] and a["dur"] >= MIN_SCENE_S and s.get("still"):
            if s["scene_no"] not in lane_cache:
                lane_cache[s["scene_no"]] = fetch_lane(lane_fn, s, st)
            a["lane"] = lane_cache[s["scene_no"]]
            a["lane_ok"] = a["lane"] is not None
            if not a["lane_ok"] and a["move"] + a["handle"] >= 1:
                skipped[s["scene_no"]] = "no walking lane in the picture"
        elif lane_fn is not None:
            a["lane_ok"] = False
        an[s["scene_no"]] = a
    minutes = max(0.5, (sc[-1]["end"] - sc[0]["start"]) / 60.0)
    budget = max(1, int(round(minutes * cfg["rate"])))
    max_j = max(1, int(round(cfg["journeys"] * max(1.0, minutes / 4.5)))) if level != "low" or minutes > 2 else 1
    csv = _csv_rows(st.get("rows"), sc)

    chosen: Dict[int, dict] = {}       # idx -> {"role", "journey"}
    links: List[Tuple[Any, Any]] = []
    # CSV rows win
    for s in sc:
        o = csv.get(s["scene_no"])
        if o and o.get("none"):
            chosen[s["idx"]] = {"role": "block"}
        elif o and an[s["scene_no"]]["dur"] >= 2.5:
            if lane_fn is not None and not an[s["scene_no"]]["lane"] and s.get("still"):
                an[s["scene_no"]]["lane"] = lane_cache.get(s["scene_no"]) or fetch_lane(lane_fn, s, st)
            if lane_fn is None or an[s["scene_no"]]["lane"]:
                chosen[s["idx"]] = {"role": "single", "csv": o}
            else:
                skipped[s["scene_no"]] = "no walking lane in the picture (CSV row ignored)"
    used = len([1 for v in chosen.values() if v["role"] != "block"])

    # journeys: runs of 2-4 consecutive scenes
    runs = []
    for i, s in enumerate(sc):
        a = an[s["scene_no"]]
        if not _relaxed_ok(a) or a["move"] < 2 or chosen.get(i):
            continue
        run = [i]
        k = i + 1
        side0 = -1 if a["back"] else 1
        while k < len(sc) and len(run) < 4:
            b = an[sc[k]["scene_no"]]
            if not _relaxed_ok(b) or chosen.get(k) or not pair_ok(an[sc[run[-1]]["scene_no"]], b, side0) or not pair_ok(a, b, side0):
                break
            run.append(k)
            if b["move"] >= 2 and len(run) < 4 and k + 1 < len(sc) and _relaxed_ok(an[sc[k + 1]["scene_no"]]) and not (b["arrive"] >= 1 and b["move"] < 3):
                k += 1
                continue
            break
        if len(run) >= 2:
            val = sum(an[sc[j]["scene_no"]]["score"] for j in run) + 0.6 * len(run)
            runs.append((-val, i, run))
    runs.sort()
    n_j = 0
    taken: set = set()
    for _, i, run in runs:
        if n_j >= max_j or used + len(run) > budget + 1:
            continue
        if any(j in taken for j in run):
            continue
        chosen_run = _try_run(sc, an, run, seed)
        if not chosen_run:
            continue
        built = []
        for j, role in zip(run, chosen_run["roles"]):
            a = an[sc[j]["scene_no"]]
            side = chosen_run["side"]
            lu = lane_u(a["lane"], side)
            r = build_beats(a, a["dur"], role, side, seed, sc[j]["scene_no"], chosen_run["speed"], role in ("first", "mid"), lane=lu)
            if not r[2].get("ok"):
                r = build_beats(a, a["dur"], role, side, seed, sc[j]["scene_no"], chosen_run["speed"], role in ("first", "mid"), early=True, lane=lu)
            if not r[2].get("ok"):
                built = None
                break
            built.append(r)
        if not built:
            continue
        n_j += 1
        taken.update(run)
        used += len(run)
        for j, role, r in zip(run, chosen_run["roles"], built):
            chosen[j] = {"role": role, "journey": n_j, "speed": chosen_run["speed"], "side": chosen_run["side"], "built": r, "y": chosen_run.get("y"),
                         "char_h": chosen_run.get("char_h")}
        links.extend((sc[run[q]]["scene_no"], sc[run[q + 1]]["scene_no"]) for q in range(len(run) - 1))
    # singles
    singles = sorted(((-an[s["scene_no"]]["score"] - _rand(seed, "pick", s["scene_no"]) * 0.3, s["idx"]) for s in sc
                      if not chosen.get(s["idx"]) and _single_ok(an[s["scene_no"]])))
    for _, i in singles:
        if used >= budget:
            break
        chosen[i] = {"role": "single"}
        used += 1

    out: Dict[Any, dict] = {}
    for s in sc:
        c = chosen.get(s["idx"])
        if not c or c["role"] == "block":
            continue
        a = an[s["scene_no"]]
        no = s["scene_no"]
        role = c["role"]
        speed = c.get("speed", WALK_SPEED)
        side = c.get("side", -1 if a["back"] else 1)
        exits = role in ("first", "mid")
        lane = a.get("lane")
        lu = lane_u(lane, side)
        if c.get("built"):
            beats, why, info = c["built"]
        else:
            beats, why, info = build_beats(a, a["dur"], role, side, seed, no, speed, exits, lane=lu)
        if not info.get("ok") and role == "single":
            beats, why, info = build_beats(a, a["dur"], role, side, seed, no, speed, False, lane=lu)
        if not info.get("ok"):
            if info.get("why"):
                skipped[no] = info["why"]
            continue
        o = (c.get("csv") or {})
        char = o.get("character") or prot["character"]
        entry = {"character": char, "action": beats[0]["action"], "direction": "right" if side > 0 else "left", "beats": beats, "why": why,
                 "enter": "left" if side > 0 else "right", "exit": ("right" if side > 0 else "left") if info.get("exits", exits) or role == "mid" else "none",
                 "y": o.get("y") or c.get("y") or (lane["y"] if lane else (JOURNEY_Y if c.get("journey") else None)),
                 "char_h": c.get("char_h") or (lane["h_hint"] if lane else CHAR_H), "journey": c.get("journey"), "role": role, "source": "csv" if o else "auto"}
        if lane:
            entry["lane"] = dict(lane, y=entry["y"], h_hint=entry["char_h"])
        tm = a.get("timing")
        if tm:
            entry["timing"] = {"speech_start": tm["speech_start"], "speech_end": tm["speech_end"], "cov": tm["cov"], "in_frac": tm["in_frac"], "trust": tm.get("trust", "heard"),
                               "foreign": tm["foreign"]}
        prop = _prop(s, a)
        if prop:
            entry["prop"] = prop
        out[no] = entry
    # a journey whose scene failed to build loses its links
    links = [(x, y) for x, y in links if x in out and y in out]
    say(f"[STORY] protagonist {prot['character']} ({prot['why']}); {len(out)} appearances in {minutes:.1f} min ({level}), {len(links)} links")
    for no, why_ in skipped.items():
        if no not in out:
            say(f"[STORY] scene {no}: no character ({why_})")
    tinfo = {no: {k: v[k] for k in ("speech_start", "speech_end", "app_start", "app_end", "cov", "in_frac", "foreign", "timing_ok", "reason", "trust")} for no, v in (timing or {}).items()}
    return {"protagonist": prot, "scenes": out, "links": links, "info": {"seed": seed, "intensity": level, "budget": budget, "version": STORY_VERSION, "timing": tinfo,
                                                                         "skipped": {no: w for no, w in skipped.items() if no not in out}, "lanes": lane_fn is not None}}


def _try_run(sc: List[dict], an: Dict[Any, dict], run: List[int], seed: int) -> Optional[dict]:
    """A run is feasible when the shared walking speed fits every picture on it. Roles: first, mid..., last."""
    durs = [an[sc[j]["scene_no"]]["dur"] for j in run]
    side = -1 if (an[sc[run[0]]["scene_no"]]["back"]) else 1
    lanes = [an[sc[j]["scene_no"]].get("lane") for j in run]
    widths = []
    for ln in lanes:
        lu = lane_u(ln, side)
        widths.append((lu["out"] - lu["in"]) if lu else (OFF_R - OFF_L))
    ys = [ln["y"] for ln in lanes if ln]
    y_run = round(sum(ys) / len(ys), 4) if ys else None
    if ys and (max(ys) - min(ys)) > 2 * JOIN_DY:
        return None
    h_run = min((ln["h_hint"] for ln in lanes if ln), default=None)
    roles = ["first"] + ["mid"] * (len(run) - 2) + ["last"]
    # mid scenes need full-width travel in their own length; first/last need at least ~half of it plus 1 s of acting
    need = [None] * len(run)
    speed = WALK_SPEED
    for q, d in enumerate(durs):
        if roles[q] == "mid":
            speed = max(speed, widths[q] / d)
        else:
            speed = max(speed, widths[q] / max(1.0, d - 0.9) if roles[q] == "first" else widths[q] / max(1.0, d - 1.0) * 0.55)
    if speed > MAX_RUN:
        return None
    return {"roles": roles, "speed": round(speed, 3), "side": side, "y": y_run, "char_h": h_run}


def _prop(s: dict, a: dict) -> Optional[str]:
    p = s["prompt"].lower()
    if re.search(r"\b(parcel|package|box|boxes|cardboard)\b", p) and (a["handle"] > 0 or a["proxy"]):
        return "parcel"
    return None


def _csv_rows(rows: Any, sc: List[dict]) -> Dict[Any, dict]:
    out: Dict[Any, dict] = {}
    for r in rows or []:
        try:
            no = r.get("scene_number", r.get("scene_no"))
            act = str(r.get("character_action") or "").strip().lower()
            ch = str(r.get("character") or "").strip()
            gr = r.get("character_ground")
            if not (act or ch or gr):
                continue
            for s in sc:
                if str(s["scene_no"]).strip() == str(no).strip():
                    out[s["scene_no"]] = {"none": act in ("none", "off", "no", "plain", "skip"), "character": None if ch.lower() in ("", "auto") else ch,
                                          "y": float(gr) if gr not in (None, "") and re.match(r"^[0-9.]+$", str(gr)) else None}
        except Exception:       # noqa: BLE001
            continue
    return out


# ---- readable summary -----------------------------------------------------------------------------------------------------------------------

def explain(plan: dict, scenes: Optional[Sequence[Any]] = None) -> str:
    lines = []
    prot = plan.get("protagonist") or {}
    lines.append(f"protagonist: {prot.get('character', '-')} ({prot.get('why', '')})")
    text = {}
    for s in scenes or []:
        text[_get(s, "scene_no")] = str(_get(s, "script_segment", _get(s, "text", "")))[:70]
    for no, e in sorted((plan.get("scenes") or {}).items(), key=lambda kv: str(kv[0]).zfill(6)):
        tag = f"journey {e['journey']} ({e['role']})" if e.get("journey") else "single"
        head = f"scene {no} [{tag}] {e['character']} enter {e['enter']} exit {e['exit']}"
        if no in text:
            head += f"  \"{text[no]}\""
        lines.append(head)
        ln = e.get("lane")
        if ln:
            lines.append(f"    lane x {ln['x0']:.2f}-{ln['x1']:.2f} y {ln['y']:.2f} h {ln['h_hint']:.2f} avoid {ln['avoid']} ({ln.get('source', '')})")
        tm = e.get("timing")
        if tm and tm.get("speech_start") is not None:
            lines.append(f"    timing: speech {tm['speech_start']:.1f}-{tm['speech_end']:.1f}s, {tm['in_frac']:.0%} inside the clip, {tm['trust']}")
        for b, w in zip(e["beats"], e.get("why") or []):
            lines.append(f"    {b['t0']:5.1f}-{b['t1']:5.1f}s {b['action']:<11} x {b['x0']:.2f}->{b['x1']:.2f}   <- {w}")
    info = plan.get("info") or {}
    for no, why_ in sorted((info.get("skipped") or {}).items(), key=lambda kv: str(kv[0]).zfill(6)):
        lines.append(f"skipped scene {no}: {why_}")
    if plan.get("links"):
        lines.append("links: " + ", ".join(f"{a}->{b}" for a, b in plan["links"]))
    return "\n".join(lines)
