"""Build an archive beat (plan data): footage beat with local pictures, a reason for each and the subject phrases that tie it to its own narration window."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .relevance import PlanBuildError, Word, beat_tokens, find_phrase, local_file_problem


def make_archive_beat(beat_id: str, start: float, end: float, words: Sequence[Word], clips: Sequence[Dict[str, Any]], *, base_dir: Optional[Path] = None,
                      purpose: str = "", strict: bool = True) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    """clips: [{asset: local file, reason: text, subject: [phrases spoken in this window], kenburns=True, dur=None}].
    Returns (beat dict, evidence, problems); evidence['subjects'] is the side record check_plan needs."""
    tk = beat_tokens(words, start, end)
    problems: List[str] = []
    out_clips: List[Dict[str, Any]] = []
    ev: Dict[str, Any] = {"beat": beat_id, "clips": [], "subjects": {}}
    for k, c in enumerate(clips):
        why = local_file_problem(c.get("asset", ""), base_dir)
        if why:
            problems.append(f"beat {beat_id}: clip {k + 1}: {why}")
        if not str(c.get("reason", "")).strip():
            problems.append(f"beat {beat_id}: clip {k + 1}: an archive clip needs a non-empty reason (what it shows that the map cannot)")
        subj = [s for s in (c.get("subject") or []) if str(s).strip()]
        hits = [m for m in (find_phrase(tk, s) for s in subj) if m]
        if not subj:
            problems.append(f"beat {beat_id}: clip {k + 1}: no subject phrase given, so its relevance to the narration cannot be established")
        elif not hits:
            problems.append(f"beat {beat_id}: clip {k + 1}: none of its subjects {subj} is spoken inside this beat's narration ({start:g} to {end:g} s)")
        entry = {"asset": c.get("asset", ""), "reason": str(c.get("reason", "")).strip()}
        if c.get("kenburns", True):
            entry["kenburns"] = True
        if c.get("dur") is not None:
            entry["dur"] = float(c["dur"])
        out_clips.append(entry)
        ev["clips"].append({"clip": k, "asset": entry["asset"], "subject": subj, "subject_matches": hits})
        ev["subjects"].setdefault(beat_id, {})[str(k)] = subj
    beat = {"id": beat_id, "mode": "footage", "start": float(start), "end": float(end), "purpose": purpose or "archive picture", "footage": {"clips": out_clips}}
    if problems and strict:
        raise PlanBuildError(problems)
    return beat, ev, problems
