"""story_align -- put every picture on screen WHEN ITS WORDS ARE SPOKEN (Hindi / English / mixed).

Drop-in, more accurate replacement for ``video_generator.align_rows``:

    aligned, audio_end, report = align_story(rows, whisper_words)

``rows``          list of dicts with ``scene_number`` and ``script_segment`` (any other keys are kept).
``whisper_words`` list of (word, start, end) -- Whisper spells Hindi phonetically and drops speech.
``aligned``       one dict per row: ``dict(row)`` + ``start_time``, ``end_time``, ``confidence`` (same keys as align_rows; the scenes tile
                  the audio: first starts at 0, each starts where the previous one ends, last ends at ``audio_end``).
``report``        dict (see below) listing the scenes whose evidence is weak.

How it works
 1. Every script word gets a coarse PHONETIC KEY (consonant skeleton: matras, nasal marks, nukta, aspiration, voicing, dental/retroflex and the
    v/b/p family are ignored; Latin words are mapped to the same alphabet so "Amazon" ~ "अमेज़न" ~ Whisper's "आमजोन"; Whisper's garbage like
    "होगगगगग" collapses to its consonants).
 2. Every plausible (script word, Whisper word) pair in a time band is a candidate (1-1, plus 1-2 / 2-1 merges because Whisper splits and joins
    words). The result is the heaviest monotonic CHAIN of candidates in which every consecutive pair is physically possible (the script words
    between two matches cannot be spoken faster than the clock allows). Words Whisper dropped simply stay unmatched.
 3. A word matched far ahead of where its neighbours' syllables say it can be (a scene's last words matched onto the next scene's first
    words) can therefore never join the chain.
 4. Unmatched words are placed between their heard neighbours by SYLLABLES (plus a pause weight at punctuation) with a speaking-rate prior,
    not by word count.
 5. A scene starts at its first word minus a small lead-in (0.2 s) and ends where the next starts.
 6. Per-scene confidence + a report of weak scenes; optional fallback to the app's own result when the DP result is implausible.

``applied(vg)`` is a context manager that swaps ``vg.align_rows`` for a wrapper (falls back to the original on any exception).
``compare(app_aligned, new_aligned)`` -> per-scene shifts.  Deterministic, numpy-free, stdlib only.
"""
from __future__ import annotations

import bisect
import contextlib
import math
import re
import statistics
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

__all__ = ["align_story", "compare", "applied", "phon_key", "syllables", "tokenize", "speech_window_check", "format_table"]

LEAD_IN = 0.2            # a picture appears this long before its first word
DEFAULT_RATE = 0.2       # seconds per syllable when nothing better is known
SIM_MIN = 0.62           # a pair of keys at least this similar may match
SIM_STRONG = 0.8
MATCH_BASE = 1.1
MAX_PER_TOKEN = 30
FAST = 0.45             # words between two matches cannot be spoken faster than 1/FAST of the median rate
FAST_SLACK = 0.6
MERGE_PENALTY = 0.25     # 1-2 / 2-1 matches are a bit less trusted than 1-1

# ---------------------------------------------------------------------------------------------------------------------------------------------
# phonetic key
# ---------------------------------------------------------------------------------------------------------------------------------------------

_DEV_CONS: Dict[str, str] = {}
for _chars, _k in (("कखगघ", "K"), ("चछजझ", "C"), ("टठडढतथदध", "T"), ("णनमङञ", "N"), ("पफबभव", "P"), ("य", "Y"), ("रऱ", "R"), ("लळ", "L"),
                   ("शषस", "S"), ("ह", "H")):
    for _c in _chars:
        _DEV_CONS[_c] = _k
_DEV_INDEP_VOWELS = set("अआइईउऊऋएऐओऔऑऍ")
_DEV_MATRAS = set("ािीुूृॄेैोौॅॉॆॊ")
_VIRAMA = "्"
_NUKTA = "़"
_NASAL_MARKS = set("ंँः")
_LAT_DIGRAPH = (("sh", "S"), ("ch", "C"), ("th", "T"), ("dh", "T"), ("ph", "P"), ("bh", "P"), ("kh", "K"), ("gh", "K"), ("ck", "K"), ("qu", "K"),
                ("ng", "NK"), ("ee", "i"), ("oo", "u"), ("ou", "u"))
_LAT = {"k": "K", "c": "K", "q": "K", "g": "K", "j": "C", "z": "C", "t": "T", "d": "T", "n": "N", "m": "N", "p": "P", "f": "P", "b": "P",
        "v": "P", "w": "P", "y": "Y", "r": "R", "l": "L", "s": "S", "x": "KS", "h": "H"}


def _is_dev(s: str) -> bool:
    return any("ऀ" <= c <= "ॿ" for c in s)


def _collapse(chars: Sequence[str]) -> str:
    out: List[str] = []
    for c in chars:
        if not out or out[-1] != c:
            out.append(c)
    return "".join(out)


def _lat_key(s: str) -> List[str]:
    s = re.sub(r"[^a-z]", "", s.lower())
    for dg, k in _LAT_DIGRAPH:
        s = s.replace(dg, "\x01" + k + "\x02")
    out: List[str] = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\x01":
            j = s.index("\x02", i)
            out.extend(s[i + 1:j].upper() if s[i + 1:j].isupper() else [])
            i = j + 1
            continue
        if c == "c" and i + 1 < len(s) and s[i + 1] in "eiy":
            out.append("S")
        elif c in _LAT:
            out.extend(_LAT[c])
        elif c in "aeiou" and not out:
            out.append("A")
        i += 1
    return out


def phon_key(word: str) -> str:
    """Coarse consonant skeleton of a Hindi / English word ('' for pure digits / punctuation)."""
    s = unicodedata.normalize("NFC", str(word or "")).lower()
    out: List[str] = []
    if _is_dev(s):
        s = s.replace(_NUKTA, "")
        latin = ""
        for c in s + " ":
            if "a" <= c <= "z":
                latin += c
                continue
            if latin:
                out.extend(_lat_key(latin))
                latin = ""
            if c in _DEV_CONS:
                out.append(_DEV_CONS[c])
            elif c in _DEV_INDEP_VOWELS and not out:
                out.append("A")
    else:
        out = _lat_key(s)
    return _collapse(out)


def syllables(word: str) -> float:
    """Estimated spoken syllables of a token (Devanagari, Latin or digits)."""
    w = unicodedata.normalize("NFC", str(word or ""))
    digits = re.sub(r"\D", "", w)
    if digits and not re.search(r"[^\W\d_]", w):
        return float({1: 2, 2: 3, 3: 6, 4: 8}.get(len(digits), 2 * len(digits)))
    if _is_dev(w):
        w = w.replace(_NUKTA, "")
        n, pending = 0, False
        last_cons = False
        for c in w:
            if c in _DEV_INDEP_VOWELS:
                n += 1
                pending = False
                last_cons = False
            elif c in _DEV_CONS:
                if pending:
                    n += 1
                pending = True
                last_cons = True
            elif c in _DEV_MATRAS:
                n += 1
                pending = False
                last_cons = False
            elif c == _VIRAMA:
                pending = False
            elif c in _NASAL_MARKS:
                pass
        if pending:
            n += 1 if n < 2 else 0       # final inherent schwa is silent in words of 2+ syllables
        return float(max(1, n))
    groups = re.findall(r"[aeiouy]+", w.lower())
    n = len(groups)
    if n > 1 and w.lower().endswith("e") and not w.lower().endswith(("le", "ee")):
        n -= 1
    return float(max(1, n))


def _key_sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if len(a) <= 1 or len(b) <= 1:
        return 1.0 if a == b else 0.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


# ---------------------------------------------------------------------------------------------------------------------------------------------
# tokens
# ---------------------------------------------------------------------------------------------------------------------------------------------

_SENT_END = "।.?!…|"
_CLAUSE_END = ",;:–—"


class _Tok:
    __slots__ = ("raw", "scene", "key", "syl", "weight", "pause", "t0", "t1", "match", "sim")

    def __init__(self, raw, scene, key, syl, weight, pause):
        self.raw, self.scene, self.key, self.syl, self.weight, self.pause = raw, scene, key, syl, weight, pause
        self.t0 = self.t1 = None
        self.match = False
        self.sim = 0.0


def tokenize(text: str) -> List[Tuple[str, float]]:
    """script text -> [(token, pause_syllables)] (hyphenated words split, punctuation removed, pause after sentence / clause ends)."""
    out: List[Tuple[str, float]] = []
    for chunk in str(text or "").replace("‍", "").replace("‌", "").split():
        trail = chunk.rstrip(")]}\"'”’»")
        pause = 2.5 if trail and trail[-1] in _SENT_END else (0.9 if trail and trail[-1] in _CLAUSE_END else 0.0)
        parts = [p for p in re.split(r"[-–—/]", chunk) if p]
        for k, p in enumerate(parts):
            clean = "".join(c for c in p if c.isalnum() or c in "़्ंँःािीुूृेैोौॅॉ" or ("ऀ" <= c <= "ॿ" and c not in "।॥") or c in ".,'")
            clean = clean.strip(".,'")
            if not re.search(r"\w", clean):
                continue
            out.append((clean, pause if k == len(parts) - 1 else 0.0))
    return out


# ---------------------------------------------------------------------------------------------------------------------------------------------
# DP
# ---------------------------------------------------------------------------------------------------------------------------------------------

def _norm_words(whisper_words) -> List[Tuple[str, float, float]]:
    out = []
    for w in whisper_words or []:
        try:
            if isinstance(w, dict):
                txt, a, b = w.get("word") or w.get("text") or "", w.get("start"), w.get("end")
            else:
                txt, a, b = w[0], w[1], w[2]
            a, b = float(a), float(b)
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        if b < a:
            b = a
        out.append((str(txt), a, b))
    out.sort(key=lambda x: (x[1], x[2]))
    return out


def _record_rate(toks: List[_Tok], recs, words) -> float:
    cs = [0.0]
    for t in toks:
        cs.append(cs[-1] + t.syl + t.pause)
    good = [r for r in recs if r[4] >= SIM_STRONG]
    rates = []
    for a, b in zip(good, good[1:]):
        syl = cs[b[0]] - cs[a[0]]
        dt = words[b[2]][1] - words[a[2]][1]
        if 4 <= syl <= 40 and dt > 0:
            rates.append(dt / syl)
    if len(rates) < 3:
        return DEFAULT_RATE
    return min(0.5, max(0.1, statistics.median(rates)))


def _candidates(toks: List[_Tok], words, audio_end: float):
    """Every plausible (script token, Whisper word) pair: records (i0, i1, j0, j1, sim)."""
    n, m = len(toks), len(words)
    wk = [phon_key(w[0]) for w in words]
    wstart = [w[1] for w in words]
    cum = [0.0]
    for t in toks:
        cum.append(cum[-1] + t.syl + t.pause)
    total = cum[-1] or 1.0
    band = max(45.0, min(120.0, 0.18 * audio_end))
    cache: Dict[Tuple[str, str], float] = {}

    def sim(a: str, b: str) -> float:
        k = (a, b)
        v = cache.get(k)
        if v is None:
            v = cache[k] = _key_sim(a, b)
        return v

    out = []
    for i, t in enumerate(toks):
        if t.weight <= 0:
            continue
        mark = len(out)
        t_exp = audio_end * ((cum[i] + cum[i + 1]) / 2 / total)
        lo = bisect.bisect_left(wstart, t_exp - band)
        hi = min(m, bisect.bisect_right(wstart, t_exp + band))
        for j in range(lo, hi):
            if not wk[j]:
                continue
            sm = sim(t.key, wk[j])
            if sm >= SIM_MIN:
                out.append((i, i, j, j, sm))
            if j + 1 < m and t.weight >= 3 and wk[j + 1]:
                sm2 = sim(t.key, wk[j] + wk[j + 1])
                if sm2 >= SIM_MIN + 0.1 and sm2 > sm + 0.05:
                    out.append((i, i, j, j + 1, sm2))
            if i + 1 < n and toks[i + 1].weight > 0:
                sm3 = sim(t.key + toks[i + 1].key, wk[j])
                if sm3 >= SIM_MIN + 0.1 and sm3 > sm + 0.05:
                    out.append((i, i + 1, j, j, sm3))
        if len(out) - mark > MAX_PER_TOKEN:          # keep the best few readings of a word (the chain picks by the clock among them)
            mine = sorted(out[mark:], key=lambda r: (-r[4], r[2]))[:MAX_PER_TOKEN]
            del out[mark:]
            out.extend(mine)
    return out


def _chain(toks: List[_Tok], recs, words, rate: float):
    """Heaviest chain of matches in which every consecutive pair is physically possible: the words between them (by syllables) cannot be
    spoken faster than ~2x the median rate in the time the transcript gives. A candidate that jumped ahead of the clock (a scene's last words
    matched onto the NEXT scene's first words) is therefore never in the chain together with the true matches."""
    if not recs:
        return []
    recs = sorted(recs, key=lambda r: (r[0], r[2], r[1]))
    cs = [0.0]
    for t in toks:
        cs.append(cs[-1] + t.syl + t.pause)
    C = len(recs)
    val, ts, te, c0, c1, i0s, i1s, j0s, j1s = [], [], [], [], [], [], [], [], []
    for (i0, i1, j0, j1, sm) in recs:
        w = sum(toks[k].weight for k in range(i0, i1 + 1))
        val.append(max(0.15, w * (2.0 * sm - MATCH_BASE) - (MERGE_PENALTY if (i1 > i0 or j1 > j0) else 0.0)))
        ts.append(words[j0][1])
        te.append(words[j1][2])
        c0.append(cs[i0])
        c1.append(cs[i1 + 1])
        i0s.append(i0)
        i1s.append(i1)
        j0s.append(j0)
        j1s.append(j1)
    best = list(val)
    prev = [-1] * C
    LOOK_TOK = 45
    for b in range(C):
        ib, jb, tb, cb = i0s[b], j0s[b], ts[b], c0[b]
        bb = best[b]
        for a in range(b - 1, -1, -1):
            if i0s[a] < ib - LOOK_TOK:
                break
            if i1s[a] >= ib or j1s[a] >= jb:
                continue
            if tb - ts[a] < FAST * max(0.0, cb - c0[a]) * rate - FAST_SLACK:
                continue
            v = best[a] + val[b]
            if v > bb:
                bb, prev[b] = v, a
        best[b] = bb
    k = max(range(C), key=lambda x: (best[x], -x))
    keep = []
    while k >= 0:
        keep.append(k)
        k = prev[k]
    keep.reverse()
    return [recs[k] for k in keep]


def _match_tokens(toks: List[_Tok], words, audio_end: float, min_sim: float = 0.0) -> Tuple[float, int, int]:
    """Candidate pairs + feasibility chain; sets token.match / sim / t0 / t1. -> (rate, candidates, rejected)."""
    cands = _candidates(toks, words, audio_end)
    n_dp = len(cands)
    rate = DEFAULT_RATE
    kept = _chain(toks, cands, words, rate)
    for _ in range(2):                              # learn the speaking rate from the first chain, then chain again with it
        rate2 = _record_rate(toks, kept, words)
        if abs(rate2 - rate) <= 0.01:
            break
        rate = rate2
        kept = _chain(toks, cands, words, rate)
    rate = _record_rate(toks, kept, words)
    for (i0, i1, j0, j1, sm) in kept:
        if sm < min_sim:
            continue
        if i0 == i1:
            t = toks[i0]
            t.match, t.sim = True, sm
            t.t0, t.t1 = words[j0][1], words[j1][2]
        else:                                    # two script words, one Whisper word: split its span
            a, b = toks[i0], toks[i1]
            w0, w1 = words[j0][1], words[j0][2]
            tot = (a.syl + b.syl) or 1.0
            mid = w0 + (w1 - w0) * a.syl / tot
            a.match, b.match, a.sim, b.sim = True, True, sm, sm
            a.t0, a.t1, b.t0, b.t1 = w0, mid, mid, w1
    return rate, n_dp, len(kept)


def _place_gap(toks: List[_Tok], a: int, b: int, left: float, right: float, rate: float) -> None:
    """Give times to the unmatched tokens a..b-1 (inclusive a, exclusive b) inside [left, right]."""
    gap = toks[a:b]
    if not gap:
        return
    right = max(right, left)
    speech = [t.syl for t in gap]
    pauses = [t.pause for t in gap]
    nat = (sum(speech) + sum(pauses)) * rate
    avail = right - left
    if nat <= 0:
        nat = 0.01
    if avail <= 1.8 * nat:
        scale = avail / nat                  # stretch / squeeze evenly
        slack_to_pauses = 0.0
    else:
        scale = 1.8
        slack_to_pauses = avail - 1.8 * nat   # real silence: park it on sentence ends
    pw = sum(pauses)
    sp_total = sum(speech) or 1e-9
    cur = left
    for t in gap:
        t.t0 = cur
        t.t1 = cur + t.syl * rate * scale
        cur = t.t1 + t.pause * rate * scale
        if slack_to_pauses > 0:
            cur += slack_to_pauses * ((t.pause / pw) if pw > 0 else (t.syl / sp_total))
    # rescale if rounding left us outside the gap
    if gap[-1].t1 > right + 1e-6 or gap[0].t0 < left - 1e-6:
        span = max(gap[-1].t1 - left, 1e-9)
        f = avail / span
        for t in gap:
            t.t0 = left + (t.t0 - left) * f
            t.t1 = left + (t.t1 - left) * f


def _assign_times(toks: List[_Tok], words, audio_end: float, rate: float) -> None:
    for t in toks:
        if not t.match:
            t.t0 = t.t1 = None
    # matched tokens carry their word times (set by the caller in t.t0/t.t1); fill the rest
    known = [k for k, t in enumerate(toks) if t.match]
    n = len(toks)
    if not known:
        _place_gap(toks, 0, n, 0.0, audio_end, rate)
        return
    # leading
    first = known[0]
    nat = sum(t.syl + t.pause for t in toks[:first]) * rate
    _place_gap(toks, 0, first, max(0.0, toks[first].t0 - max(nat * 1.25, 0.0)), toks[first].t0, rate)
    for a, b in zip(known, known[1:]):
        _place_gap(toks, a + 1, b, toks[a].t1, toks[b].t0, rate)
    last = known[-1]
    nat = sum(t.syl + t.pause for t in toks[last + 1:]) * rate
    _place_gap(toks, last + 1, n, toks[last].t1, min(audio_end, toks[last].t1 + nat * 1.25), rate)


def _empty(rows, audio_end, why, report_extra=None):
    n = len(rows)
    out = []
    for i, row in enumerate(rows):
        r = dict(row)
        r.update(start_time=audio_end * i / max(n, 1), end_time=audio_end * (i + 1) / max(n, 1), confidence=0.0)
        out.append(r)
    rep = {"method": "even", "fallback": False, "reason": why, "weak": [r.get("scene_number") for r in rows], "scenes": []}
    rep.update(report_extra or {})
    return out, audio_end, rep


def align_story(rows, whisper_words, *, min_dur: float = 1.2, log: Callable[[str], Any] = print,
                fallback: Optional[Callable[[Any, Any], Any]] = None, lead_in: float = LEAD_IN):
    """See module docstring. ``fallback`` = the app's own align_rows (used only when the DP result is implausible)."""
    rows = list(rows)
    words = _norm_words(whisper_words)
    if not rows:
        return [], (words[-1][2] if words else 0.0), {"method": "none", "scenes": [], "weak": [], "fallback": False}
    if not words:
        raise ValueError("no Whisper words to align against")
    audio_end = words[-1][2]
    for w in words:
        audio_end = max(audio_end, w[2])

    toks: List[_Tok] = []
    scene_tokens: List[List[int]] = []
    for ri, row in enumerate(rows):
        idxs = []
        for raw, pause in tokenize(row.get("script_segment", "")):
            key = phon_key(raw)
            syl = syllables(raw)
            has_digit = any(c.isdigit() for c in raw)
            weight = 0 if (has_digit or not key) else min(4, max(1, len(key)))
            t = _Tok(raw, ri, key, syl, weight, pause)
            idxs.append(len(toks))
            toks.append(t)
        scene_tokens.append(idxs)
    if not toks:
        return _empty(rows, audio_end, "script has no words")

    rate, n_dp, dropped = _match_tokens(toks, words, audio_end)
    kept = {id(t): (t.t0, t.t1) for t in toks if t.match}
    _assign_times(toks, words, audio_end, rate)
    for t in toks:                                # matched tokens keep their Whisper times
        if id(t) in kept:
            t.t0, t.t1 = kept[id(t)]
    # ordering guard: times must not go backwards (monotone envelope)
    run = 0.0
    for t in toks:
        t.t0 = max(t.t0, run)
        t.t1 = max(t.t1, t.t0)
        run = t.t0

    n_scenes = len(rows)
    # --- boundaries
    bounds = [0.0] * (n_scenes + 1)
    bounds[n_scenes] = audio_end
    first_tok: List[Optional[int]] = [(idx[0] if idx else None) for idx in scene_tokens]
    for si in range(1, n_scenes):
        ft = first_tok[si]
        if ft is None:
            bounds[si] = bounds[si - 1]
            continue
        t_first = toks[ft].t0
        prev_idx = [k for k in range(si - 1, -1, -1) if scene_tokens[k]]
        lo = 0.0
        if prev_idx:
            lt = toks[scene_tokens[prev_idx[0]][-1]]
            lo = lt.t0 + 0.2
        b = min(t_first, max(t_first - lead_in, lo))
        bounds[si] = b
    # empty-script scenes share the neighbours' boundary; monotone + minimum duration
    for si in range(1, n_scenes + 1):
        bounds[si] = max(bounds[si], bounds[si - 1])
    if n_scenes * min_dur <= audio_end:
        for _ in range(4):
            for si in range(1, n_scenes):
                bounds[si] = max(bounds[si], bounds[si - 1] + min_dur)
            for si in range(n_scenes - 1, 0, -1):
                bounds[si] = min(bounds[si], bounds[si + 1] - min_dur)
            bounds[0] = 0.0
    else:
        bounds = [audio_end * k / n_scenes for k in range(n_scenes + 1)]

    # --- per-scene stats
    scenes_rep: List[dict] = []
    weak: List[Any] = []
    total_syl_by_scene = []
    for si, row in enumerate(rows):
        idx = scene_tokens[si]
        tsyl = sum(toks[k].syl for k in idx) or 1.0
        msyl = sum(toks[k].syl for k in idx if toks[k].match)
        cov = msyl / tsyl
        start, end = bounds[si], bounds[si + 1]
        dur = end - start
        # how near is the closest heard word to the scene's first / last word
        def nearest(k0, step):
            d = 0
            for k in (idx if step > 0 else idx[::-1]):
                if toks[k].match:
                    return d
                d += 1
            return d
        lead_gap = nearest(0, 1) if idx else 99
        first_heard = bool(idx) and (toks[idx[0]].match or lead_gap <= 1)
        r_scene = dur / tsyl if idx else 0.0
        conf = 0.15 + 0.55 * cov + (0.3 if first_heard else 0.0)
        reasons = []
        if not idx:
            conf, reasons = 0.0, ["empty script segment"]
        else:
            if cov < 0.35:
                reasons.append(f"only {cov:.0%} of its words were heard (inferred between neighbours)")
                conf = min(conf, 0.45)
            if not first_heard:
                reasons.append(f"its first {lead_gap} words were not heard, so the start is estimated")
                conf = min(conf, 0.6)
            if tsyl >= 5 and not (0.08 <= r_scene <= 0.9):
                reasons.append(f"implausible speaking rate {r_scene:.2f} s/syllable")
                conf = min(conf, 0.3)
        conf = round(max(0.0, min(1.0, conf)), 2)
        status = "heard" if (conf >= 0.8) else ("inferred" if conf >= 0.4 else "weak")
        if reasons:
            weak.append(row.get("scene_number"))
        total_syl_by_scene.append(tsyl)
        scenes_rep.append({"scene_number": row.get("scene_number"), "start": round(start, 3), "end": round(end, 3), "confidence": conf,
                           "status": status, "coverage": round(cov, 3), "sec_per_syllable": round(r_scene, 3), "reasons": reasons})

    aligned = []
    for si, row in enumerate(rows):
        r = dict(row)
        r["start_time"] = bounds[si]
        r["end_time"] = bounds[si + 1]
        r["confidence"] = scenes_rep[si]["confidence"]
        aligned.append(r)

    all_syl = sum(total_syl_by_scene) or 1.0
    matched_syl = sum(t.syl for t in toks if t.match)
    report = {"method": "story_align", "fallback": False, "reason": "", "tokens": len(toks), "matched_tokens": sum(1 for t in toks if t.match),
              "candidates": n_dp, "chain": dropped, "coverage": round(matched_syl / all_syl, 3), "rate_s_per_syllable": round(rate, 3),
              "weak": weak, "scenes": scenes_rep}

    # --- plausibility / fallback
    bad_rate = sum(1 for s in scenes_rep if any("implausible" in x for x in s["reasons"]))
    implausible = report["coverage"] < 0.25 or bad_rate > 0.4 * n_scenes
    if implausible:
        report["reason"] = f"coverage {report['coverage']:.0%}, {bad_rate} scenes with implausible rate"
        if fallback is not None:
            log(f"[story_align] result implausible ({report['reason']}); using the app's own aligner")
            res = fallback(rows, [(w[0], w[1], w[2]) for w in words])
            app_rows, app_end = res[0], res[1]
            report.update(method="fallback", fallback=True)
            return app_rows, app_end, report
        report["fallback_recommended"] = True
    log(f"[story_align] {report['matched_tokens']}/{report['tokens']} words matched ({report['coverage']:.0%} of syllables); "
        f"{len(weak)} scene(s) with weak evidence: {weak}")
    return aligned, audio_end, report


# ---------------------------------------------------------------------------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------------------------------------------------------------------------

def compare(app_aligned, new_aligned) -> List[dict]:
    """Per-scene shifts: [{scene_number, start_shift, end_shift, app: (s, e), new: (s, e)}] (positive = the new aligner is later)."""
    out = []
    for a, b in zip(app_aligned, new_aligned):
        s0, e0 = float(a["start_time"]), float(a["end_time"])
        s1, e1 = float(b["start_time"]), float(b["end_time"])
        out.append({"scene_number": b.get("scene_number", a.get("scene_number")), "start_shift": round(s1 - s0, 2), "end_shift": round(e1 - e0, 2),
                    "app": (round(s0, 2), round(e0, 2)), "new": (round(s1, 2), round(e1, 2))})
    return out


def speech_window_check(rows, whisper_words, windows: Sequence[Tuple[float, float]], *, tol: float = 0.15) -> List[dict]:
    """For each scene: the share of ITS heard words (script words matched to Whisper words by the DP) that lie inside its (start, end) window.
    ``windows`` should TILE (what the renderer shows). Used to compare any aligner's result against the speech evidence."""
    words = _norm_words(whisper_words)
    toks: List[_Tok] = []
    owner: List[int] = []
    for ri, row in enumerate(rows):
        for raw, pause in tokenize(row.get("script_segment", "")):
            key = phon_key(raw)
            toks.append(_Tok(raw, ri, key, syllables(raw), 0 if (any(c.isdigit() for c in raw) or not key) else min(4, max(1, len(key))), pause))
    audio_end = words[-1][2]
    _match_tokens(toks, words, audio_end, min_sim=SIM_STRONG)
    res = []
    for ri, row in enumerate(rows):
        mine = [t for t in toks if t.scene == ri and t.match]
        a, b = windows[ri]
        inside = [t for t in mine if a - tol <= (t.t0 + t.t1) / 2 <= b + tol]
        res.append({"scene_number": row.get("scene_number"), "heard": len(mine), "inside": len(inside),
                    "frac": (len(inside) / len(mine)) if mine else None,
                    "speech": (min(t.t0 for t in mine), max(t.t1 for t in mine)) if mine else None})
    return res


def format_table(rows, before: List[dict], after: List[dict]) -> str:
    lines = ["scene  speech(heard)      app window        in%   new window        in%   shift(start)"]
    for rw, b, a in zip(rows, before, after):
        sp = f"{b['speech'][0]:6.1f}-{b['speech'][1]:6.1f}" if b["speech"] else "      -      "
        fb = "  - " if b["frac"] is None else f"{b['frac'] * 100:3.0f}%"
        fa = "  - " if a["frac"] is None else f"{a['frac'] * 100:3.0f}%"
        lines.append(f"{str(rw.get('scene_number')):>5}  {sp}  {b['win'][0]:6.1f}-{b['win'][1]:6.1f}  {fb}  {a['win'][0]:6.1f}-{a['win'][1]:6.1f}  {fa}  {a['win'][0] - b['win'][0]:+6.1f}")
    return "\n".join(lines)


@contextlib.contextmanager
def applied(vg, *, log: Callable[[str], Any] = print):
    """Temporarily replace ``vg.align_rows`` (video_generator) with story_align; any exception falls back to the original and says why."""
    original = vg.align_rows

    def wrapper(rows, whisper_words):
        try:
            aligned, audio_end, report = align_story(rows, whisper_words, log=log, fallback=original)
            if report.get("fallback"):
                return aligned, audio_end
            if len(aligned) != len(rows):
                raise RuntimeError("row count changed")
            return aligned, audio_end
        except Exception as e:           # never let the new aligner stop a video
            log(f"[story_align] failed ({type(e).__name__}: {e}); using the app's own aligner")
            return original(rows, whisper_words)

    vg.align_rows = wrapper
    try:
        yield wrapper
    finally:
        vg.align_rows = original
