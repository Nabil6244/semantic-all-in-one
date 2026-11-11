"""War Footage Director: moment relevance. The cut segment must come from the part of the video that is about the line's subject.

Render 050: a 15-minute UATV news show was cut at 845 s - a segment about a satellite system - for 'drones crossed toward Saint
Petersburg', because the title matched and nothing checked where in the programme the window was. A short upload (a raw news clip) is
about one thing, so its title decides; a long programme is only cut near a transcript passage that names the line's subject.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

LONG_S = 240.0            # uploads longer than this are programmes with several stories: the moment must be found in the transcript
BEFORE_S = 20.0           # the cut may start this long before the passage that names the subject ...
AFTER_S = 45.0            # ... and this long after it (news pictures follow the words that introduce them)
GROUP = 3                 # transcript lines read together (one spoken sentence spans several caption lines)


def terms_of(reading: Any) -> List[str]:
    """What the moment must be about: the line's own subject, else its section's (narration_read.read_scenes)."""
    out: List[str] = []
    for t in list(getattr(reading, "section_terms", None) or []) + list(getattr(reading, "key_terms", None) or []):
        if t and t not in out:
            out.append(t)
    return out


def find(segments: Sequence[Dict[str, Any]], terms: Sequence[str], has: Callable[[str, str], bool]) -> Optional[Tuple[float, int]]:
    """(start of the transcript passage that names the most of `terms`, how many it names) or None when no passage names any."""
    from .narration_read import fold

    best: Optional[Tuple[float, int]] = None
    for i in range(len(segments)):
        text = fold(" ".join(str(s.get("text") or "") for s in segments[i:i + GROUP])).lower()
        n = sum(1 for t in terms if has(text, t))
        if n and (best is None or n > best[1]):
            best = (float(segments[i].get("start") or 0.0), n)
    return best


def chapter_hint(chapters: Optional[Sequence[Dict[str, Any]]], terms: Sequence[str], has: Callable[[str, str], bool]) -> Optional[float]:
    """Start of the chapter whose title names the most of `terms`, None when no title names any."""
    from .narration_read import fold

    best: Optional[Tuple[float, int]] = None
    for ch in chapters or []:
        title = fold(str(ch.get("title") or "")).lower()
        n = sum(1 for t in terms if has(title, t))
        if n and (best is None or n > best[1]):
            best = (float(ch.get("start") or 0.0), n)
    return best[0] if best else None


def check(duration: Optional[float], segments: Optional[Sequence[Dict[str, Any]]], reading: Any,
          has: Optional[Callable[[str, str], bool]] = None, status: str = "",
          chapters: Optional[Sequence[Dict[str, Any]]] = None) -> Tuple[bool, Optional[float], str]:
    """(may be used, transcript time to cut near or None, reason when not). Without a transcript, a chapter title that names the line's
    subject gives the hint; a rate-limited transcript is reported as unverified, never as a programme about something else."""
    if not duration or float(duration) <= LONG_S:
        return True, None, ""
    terms = terms_of(reading)
    if not terms:
        return False, None, "moment: the line names nothing to find in a long programme"
    if has is None:
        from .director_rules import _has as has
    if not segments:
        hint = chapter_hint(chapters, terms, has) if chapters else None
        if hint is not None:
            return True, hint, ""
        if status == "rate_limited":
            return False, None, "moment: transcript rate-limited (not checked, retried later): the cut cannot be verified"
        return False, None, f"moment: a {float(duration) / 60:.0f}-minute programme without a transcript: the cut cannot be checked"
    hit = find(segments, terms, has)
    if hit is None:
        return False, None, f"moment: the programme never talks about {', '.join(terms[:3])}"
    return True, hit[0], ""


def near(hint: Optional[float]) -> Callable[[float, float], bool]:
    """A window predicate: inside [hint - BEFORE_S, hint + AFTER_S] (always true without a hint)."""
    if hint is None:
        return lambda a, b: True
    return lambda a, b: hint - BEFORE_S <= a <= hint + AFTER_S


def inside(start: float, hint: Optional[float]) -> bool:
    return near(hint)(start, start)
