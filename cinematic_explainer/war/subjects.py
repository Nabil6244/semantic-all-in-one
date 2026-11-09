"""War Documentary: the picture follows the sentence's subject (reference study section 10, rule 1).

A sentence whose subject is a person from the figures catalogue ("Putin could not break Ukraine ...", "Zelensky's office ...") shows that
person: the catalogue's verified portrait in the figure layout (name, role), for the length of the sentence. Only when

  - the scene's own clip does not already fit the sentence (the CSV's pick or a relevant match keeps the screen),
  - nothing full-frame is on screen then and no speaker / figure card already shows a person,
  - the same person was not shown in the last FIG_GAP_S seconds,
  - a verified portrait is cached (portraits.portrait_for: nothing is downloaded here).

The narration is never put in the person's mouth: the card carries name and role only, no statement.
Config: "subject_pictures" (True).
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, Optional, Sequence

from ..render import Layer
from . import semantics as S

FIG_GAP_S = 45.0       # the same face at most once in this many seconds
MIN_S = 2.4            # a sentence shorter than this keeps its clip
MAX_S = 5.5            # the portrait never holds longer (the reference holds a face 2-5 s unless the person speaks)
SUBJECT_CHARS = 30     # the person must be named within the sentence's first words: its subject, not a passing mention
PERSON_KINDS = {"lay_figure_hero", "lay_figure_pair", "lay_speaker_quote", "figure_card", "portrait"}


def subject_figure(sent: Any) -> Optional[Any]:
    """The catalogue person the sentence is about: named (or possessive) within its first SUBJECT_CHARS characters."""
    for e in sent.entities:
        if e.kind != "figure" or not e.specific or e.ambiguous or not e.entry:
            continue
        if e.span[0] - sent.span[0] <= SUBJECT_CHARS:
            return e
    return None


def _portrait(e: Any) -> Optional[str]:
    try:
        from . import portraits as P

        hit = P.portrait_for(e.id)
        return hit["path"] if hit else None
    except Exception:
        return None


def apply(plan: Any, rows: Sequence[Dict[str, Any]], cat: Any, log_by_no: Dict[str, Any], counts: Dict[str, int], full_kinds: set,
          fits: Callable[[Dict[str, Any]], bool], portrait: Callable[[Any], Optional[str]] = _portrait) -> int:
    added = 0
    last: Dict[str, float] = {}
    side = 0
    for r in rows:
        text = str(r.get("text") or "")
        if not text.strip():
            continue
        if r.get("footage") and fits(r.get("footage_meta") or {}):
            continue                                    # the clip already shows what the sentence is about
        A = S.analyze_scene(text, cat, r.get("words"), r["_start"], r["_end"])
        for sent in A.sentences:
            e = subject_figure(sent)
            if e is None:
                continue
            key = str(e.id or e.name)
            a = max(r["_start"], A.time_at(sent.span[0]) - 0.05)
            s_end = A.time_at(sent.span[1] - 1) + 0.3 if sent.span[1] > sent.span[0] else r["_end"]
            b = min(r["_end"] + 0.3, max(s_end, a + 3.0), a + MAX_S)
            if b - a < MIN_S or a - last.get(key, -1e9) < FIG_GAP_S:
                continue
            if any(ly.start < b and ly.end > a and (ly.kind in full_kinds or ly.kind in PERSON_KINDS) for ly in plan.layers):
                continue
            img = portrait(e)
            if not img:
                continue
            role = re.split(r"\s+(?:since|from|until)\s+|\s*\(", str(e.entry.get("role") or ""))[0].strip()
            params = {"name": str(e.entry.get("name") or e.name), "role": role[:60], "image": img, "statement": "",
                      "side": "right" if side % 2 == 0 else "left", "subject": True}
            side += 1
            plan.layers.append(Layer("lay_figure_hero", round(a * 25) / 25, round(b * 25) / 25, params, dim=True))
            last[key] = a
            added += 1
            dec = log_by_no.get(str(r["_no"]))
            if dec is not None:
                dec.flags.append("dir:subject_portrait")
                dec.candidates.append({"kind": "lay_figure_hero", "score": 0.0, "accepted": True, "start": a, "end": b,
                                       "reason": f"direction: the sentence is about {params['name']}: their portrait"})
    if added:
        counts["subject_portraits"] = counts.get("subject_portraits", 0) + added
    return added
