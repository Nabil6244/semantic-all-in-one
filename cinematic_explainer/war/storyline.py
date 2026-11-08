"""War Documentary storyline pass (reference study docs/war/REFERENCE_AIR_DEFENSE.md, section 7): the devices that make a long film
engaging, built from the narration's own structure. Only ADDS layers / re-cuts footage the plan already has; never invents a picture.

  roadmap      "Borrow, find and build. First, borrow ... Second, find ... Third, build." -> fx_roadmap: the three words on screen when the list
               is spoken, then again (current part lit) as each part opens
  callbacks    a later sentence that refers back to an earlier claim ("he had said", "promised", "called it", "claimed") -> the earlier
               scene's own picture returns for ~1.6 s (setup -> payoff)
  recap        "Here is the full account / to sum up / in short" -> the following sentences are cut over the film's own earlier shots of
               what each names (the whole story again in quick pictures)
  flashes      a section turn ("Then ...", "But ...", "So why ...?", "Meanwhile ...") over footage -> fx_flash: a 0.3 s white light flash
               on the cut (never on human-cost lines)
  pace         footage known to fit its sentence: strike / escalation sentences are cut into 1.4-2.4 s shots, explanation and human-cost
               sentences keep their longer shots (rhythm follows meaning)

Cards here: fx_flash, fx_roadmap (same contract as cards.py).
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw

from ..render import Layer, Shot
from . import motion as M
from . import semantics as S
from . import tokens as T
from .. import look as L

W, H = T.W, T.H
FPS = 25
YEL = (255, 196, 0, 255)
INK = (12, 12, 14, 255)


def fr(x: float) -> float:
    return round(round(x * FPS) / FPS, 4)


# ================================================================================================================ cards
def fx_flash(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """A light flash on a cut: white (or the reference's warm pink) rising and falling over the card."""
    col = (255, 236, 236) if str((p or {}).get("tone") or "") == "warm" else (255, 255, 255)
    k = math.sin(math.pi * M.clamp01(t / max(dur, 0.05)))
    return Image.new("RGBA", (W, H), col + (int(215 * k),))


def fx_roadmap(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """The roadmap words in a row (BORROW · FIND · BUILD); `current` index lit yellow, the rest white; types on word by word."""
    words = [str(w).upper() for w in (p or {}).get("words") or [] if str(w).strip()]
    if len(words) < 2:
        return None
    cur = p.get("current")
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = T.font("display", 64)
    gap = 46
    widths = [d.textlength(w, font=f) for w in words]
    x = (W - (sum(widths) + gap * (len(words) - 1))) / 2
    y = H * 0.72
    for i, (w, tw) in enumerate(zip(words, widths)):
        k = M.ease_out(M.ramp(t, 0.18 * i if cur is None else 0.0, 0.25))
        if k <= 0:
            break
        lit = cur is None or cur == i
        if lit and cur is not None:
            d.rectangle([x - 12, y - 6, x + tw + 12, y + 72], fill=YEL)
        col = INK if (lit and cur is not None) else (255, 255, 255, int(255 * k)) if lit else (205, 205, 205, int(150 * k))
        if not (lit and cur is not None):
            d.text((x + 3, y + 3), w, font=f, fill=(0, 0, 0, int(160 * k)))
        d.text((x, y), w, font=f, fill=col)
        x += tw + gap
    return L.fade(img, 1.0 - M.ramp(t, dur - 0.2, 0.2))


STORY_CARDS = {"fx_flash": fx_flash, "fx_roadmap": fx_roadmap}

# ================================================================================================================ detection
_HUMAN = re.compile(r"\b(killed|dead|died|wounded|injured|hurt|child|children|boy|girl|family|families|civilians?|victims?)\b", re.IGNORECASE)
_FAST = re.compile(r"\b(strikes?|struck|hit|hits|fired|launched|attacks?|attacked|shot down|exploded|explosion|bomb\w*|missiles?|drones?|"
                   r"burning|fire|blew)\b", re.IGNORECASE)
_TURN = re.compile(r"^\W*(then|but|so|meanwhile|now|yet|still|and then|here is|here's)\b|\?\s*$", re.IGNORECASE)
_CALLBACK = re.compile(r"\b(had said|had promised|had claimed|had called|once said|once called|promised|called (?:it|the|them)|claimed that|"
                       r"said in \d{4}|said that .* could)\b", re.IGNORECASE)
_RECAP = re.compile(r"\b(here is the full account|to sum up|in short|to recap|here is the whole story|so far, then|let'?s recap)\b", re.IGNORECASE)
_ROADMAP_LIST = re.compile(r"\b(\w+),\s+(\w+),?\s+and\s+(\w+)\.?\s*$", re.IGNORECASE)
_ORD = {"first": 0, "second": 1, "third": 2, "fourth": 3}


def _fits(meta: Dict[str, Any]) -> bool:
    from .broadcast import _fits as f

    return f(meta)


def _keywords(A: Any, sent: Any) -> set:
    out = {(e.id or e.name).lower() for e in sent.entities if not getattr(e, "ambiguous", False)}
    out |= {w.lower() for w in re.findall(r"\b[A-Z][a-z]{3,}\b", sent.text)} - {"then", "this", "that", "here", "there", "when"}
    return out


# ================================================================================================================ passes
def roadmap(plan: Any, rows: Sequence[Dict[str, Any]], cat: Any) -> int:
    """'X, Y and Z.' followed by 'First, X' ... -> the roadmap card when the list is said, and at each part with that part lit."""
    n = 0
    rows = sorted(rows, key=lambda r: r["_start"])
    for i, r in enumerate(rows):
        text = str(r.get("text") or "")
        A = S.analyze_scene(text, cat, r.get("words"), r["_start"], r["_end"])
        for sent in A.sentences:
            m = _ROADMAP_LIST.search(sent.text)
            if not m:
                continue
            words = [m.group(1), m.group(2), m.group(3)]
            ahead = " ".join(str(x.get("text") or "") for x in rows[i:i + 6]).lower()
            if not all(re.search(r"\b(first|second|third)\b,?\s+" + re.escape(w.lower()), ahead) for w in words[:2]):
                continue
            a = A.time_at(sent.span[0] + m.start())
            plan.layers.append(Layer("fx_roadmap", fr(a), fr(min(a + 3.4, r["_end"] + 0.6)), {"words": words}, dim=False))
            n += 1
            for r2 in rows[i:i + 12]:
                t2 = str(r2.get("text") or "")
                for mo in re.finditer(r"\b(first|second|third),?\s+(\w+)", t2, re.IGNORECASE):
                    idx = _ORD[mo.group(1).lower()]
                    if idx < len(words) and mo.group(2).lower() == words[idx].lower():
                        A2 = S.analyze_scene(t2, cat, r2.get("words"), r2["_start"], r2["_end"])
                        a2 = A2.time_at(mo.start())
                        plan.layers.append(Layer("fx_roadmap", fr(a2), fr(min(a2 + 2.6, r2["_end"] + 0.4)), {"words": words, "current": idx}, dim=False))
                        n += 1
            return n
    return n


def _shots_of(plan: Any, r: Dict[str, Any]) -> List[Shot]:
    return [s for s in plan.shots if r.get("footage") and s.path == r["footage"] and s.start < r["_end"] and s.end > r["_start"]]


def _insert(plan: Any, src: Shot, a: float, b: float) -> bool:
    """Cut the earlier picture in over [a, b] (on top of whatever footage is there); never over a full-frame card."""
    from .broadcast import _opaque

    a, b = fr(a), fr(b)
    if b - a < 1.0 or any(ly.start < b and ly.end > a and _opaque(ly) for ly in plan.layers):
        return False
    if sum(max(0.0, min(b, s.end) - max(a, s.start)) for s in plan.shots) < (b - a) - 0.08:
        return False                                     # only where footage already plays (a callback never fills a hole)
    out: List[Shot] = []
    for s in plan.shots:
        if s.end <= a or s.start >= b:
            out.append(s)
            continue
        if s.start < a:
            out.append(Shot(s.path, s.start, a, s.seek, s.treat, s.dissolve_in))
        if s.end > b:
            out.append(Shot(s.path, b, s.end, round(s.seek + (b - s.start), 3), s.treat, 0.0))
    out.append(Shot(src.path, a, b, round(src.seek + 0.4, 3)))
    plan.shots[:] = sorted(out, key=lambda s: s.start)
    return True


def callbacks_and_recap(plan: Any, rows: Sequence[Dict[str, Any]], cat: Any) -> Dict[str, int]:
    out = {"callbacks": 0, "recap_cuts": 0}
    rows = sorted(rows, key=lambda r: r["_start"])
    seen: List[Tuple[set, Dict[str, Any]]] = []
    recap_left = 0
    for r in rows:
        text = str(r.get("text") or "")
        if not text.strip():
            continue
        A = S.analyze_scene(text, cat, r.get("words"), r["_start"], r["_end"])
        for sent in A.sentences:
            keys = _keywords(A, sent)
            if _RECAP.search(sent.text):
                recap_left = 6
                continue
            want = recap_left > 0 or bool(_CALLBACK.search(sent.text))
            if want and keys:
                best = max((x for x in seen if x[1] is not r and keys & x[0] and _shots_of(plan, x[1])), key=lambda x: len(keys & x[0]), default=None)
                if best is not None:
                    src = _shots_of(plan, best[1])[0]
                    a = A.time_at(sent.span[0]) + 0.1
                    if _insert(plan, src, a, min(a + 1.6, r["_end"])):
                        out["recap_cuts" if recap_left > 0 else "callbacks"] += 1
            if recap_left > 0:
                recap_left -= 1
            if keys and r.get("footage") and _fits(r.get("footage_meta") or {}):
                seen.append((keys, r))
    return out


def flashes(plan: Any, rows: Sequence[Dict[str, Any]], cat: Any) -> int:
    """A light flash on the cut that opens a section turn, at most one per 20 s, never on a human-cost sentence."""
    from .broadcast import _on_footage

    n, last = 0, -1e9
    for r in sorted(rows, key=lambda r: r["_start"]):
        text = str(r.get("text") or "").strip()
        if not text or not _TURN.search(text) or _HUMAN.search(text) or r["_start"] - last < 20.0:
            continue
        a = r["_start"] - 0.12
        if a < 1.0 or not _on_footage(plan, max(0.0, a), a + 0.3):
            continue
        plan.layers.append(Layer("fx_flash", fr(a), fr(a + 0.3), {"tone": "warm" if n % 2 else "white"}, dim=False))
        last = r["_start"]
        n += 1
    return n


def pace(plan: Any, rows: Sequence[Dict[str, Any]], cat: Any) -> int:
    """Strike / escalation sentences over fitting footage: 1.4-2.4 s cuts (a different moment of the clip each time). Human-cost lines hold."""
    n = 0
    fast_spans = []
    for r in rows:
        text = str(r.get("text") or "")
        if r.get("footage") and _fits(r.get("footage_meta") or {}) and _FAST.search(text) and not _HUMAN.search(text):
            fast_spans.append((r["_start"], r["_end"]))
    if not fast_spans:
        return 0
    out: List[Shot] = []
    for s in sorted(plan.shots, key=lambda s: s.start):
        inside = any(a - 0.05 <= s.start and s.end <= b + 0.6 for a, b in fast_spans)
        dur = s.end - s.start
        if not inside or dur < 3.2:
            out.append(s)
            continue
        k = max(2, int(round(dur / 1.9)))
        piece = dur / k
        from .story import _clip_len

        clen = _clip_len(s.path)
        for i in range(k):
            a, b = fr(s.start + i * piece), fr(s.end if i == k - 1 else s.start + (i + 1) * piece)
            seek = s.seek + i * piece * 1.35
            if clen > 0:
                seek = min(seek, max(0.0, clen - (b - a) - 0.1))   # never past the clip's end
            out.append(Shot(s.path, a, b, round(seek, 3), s.treat, s.dissolve_in if i == 0 else 0.0))
        n += 1
    plan.shots[:] = out
    return n
