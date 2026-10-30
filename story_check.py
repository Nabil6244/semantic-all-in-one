"""story_check -- the offline "Check plan" for the Story Motion style: reads the dense CSV (and the Whisper words when they exist), changes nothing, spends nothing.

    rep = check_csv(rows, words=None, wps=2.5) -> {"ok": bool, "errors": [...], "warnings": [...], "stats": {...}, "text": str}

rows = list of dicts with scene_number, script_segment, prompt (asset_type optional). Without words the row lengths are estimated from the word count (wps spoken words per second);
with Whisper words the rows are aligned (story_align) and planned (shot_director) and the same numbers the render audit uses are reported."""
from __future__ import annotations
import re
from typing import Any, Dict, List, Optional, Sequence

MIN_WORDS, MAX_WORDS = 4, 16          # a row shows one picture for ~1.6-6.4 s of narration
MIN_PROMPT_WORDS = 12

def _words(t: str) -> List[str]:
    return [w for w in re.split(r"\s+", (t or "").strip()) if w]

def _jacc(a: str, b: str) -> float:
    sa, sb = set(a.lower().split()), set(b.lower().split())
    return len(sa & sb) / max(1, len(sa | sb))

def check_csv(rows: Sequence[Dict[str, Any]], words: Optional[Sequence[Sequence[Any]]] = None, wps: float = 2.5) -> Dict[str, Any]:
    errors: List[str] = []; warnings: List[str] = []; rows = [dict(r) for r in rows or []]
    if not rows:
        return {"ok": False, "errors": ["The CSV has no rows."], "warnings": [], "stats": {}, "text": "The CSV has no rows."}
    cols = set().union(*(r.keys() for r in rows))
    for need in ("scene_number", "script_segment", "prompt"):
        if need not in cols: errors.append(f"Column '{need}' is missing.")
    if errors:
        return {"ok": False, "errors": errors, "warnings": [], "stats": {}, "text": "\n".join(errors)}
    lens = []; prev_prompt = ""; seen = {}
    for i, r in enumerate(rows, 1):
        n = str(r.get("scene_number", i)); w = _words(r.get("script_segment", "")); p = (r.get("prompt") or "").strip(); lens.append(len(w))
        if not w: errors.append(f"Row {n}: the script text is empty (a row with no words cannot be timed).")
        elif len(w) < MIN_WORDS: warnings.append(f"Row {n}: only {len(w)} word(s) (~{len(w) / wps:.1f} s): too short to show a picture; merge it into a neighbour.")
        elif len(w) > MAX_WORDS: warnings.append(f"Row {n}: {len(w)} words (~{len(w) / wps:.0f} s) on one picture; split it at a comma or a connector.")
        if len(_words(p)) < MIN_PROMPT_WORDS: warnings.append(f"Row {n}: the picture prompt is very short ({len(_words(p))} words).")
        if p and p in seen: warnings.append(f"Row {n}: the same prompt as row {seen[p]} (Flow would make the same picture twice).")
        elif p and prev_prompt and _jacc(p, prev_prompt) > 0.8: warnings.append(f"Row {n}: almost the same prompt as the row before; give it another framing.")
        if p: seen.setdefault(p, n)
        prev_prompt = p
        if str(r.get("asset_type", "image")).strip().lower() == "reuse": warnings.append(f"Row {n}: asset_type 'reuse'. The dense CSV makes one picture per row; use 'image'.")
    est = [x / wps for x in lens]
    stats: Dict[str, Any] = {"rows": len(rows), "avg_words": round(sum(lens) / len(lens), 1), "est_seconds": round(sum(est), 1), "longest_row_s": round(max(est), 1), "shortest_row_s": round(min(est), 1)}
    lines = [f"{len(rows)} rows, about {stats['est_seconds']:.0f} s of narration ({stats['avg_words']} words a row, longest ~{stats['longest_row_s']:.0f} s, shortest ~{stats['shortest_row_s']:.1f} s)."]
    if words:
        try:
            import story_align, shot_director
            sc = [{"scene_number": str(r.get("scene_number", i)), "script_segment": r.get("script_segment", ""), "asset_type": "image", "prompt": r.get("prompt", "")} for i, r in enumerate(rows, 1)]
            al, end, rep = story_align.align_story(sc, [list(w) for w in words], log=lambda *a, **k: None)
            plan = shot_director.plan_shots(al, [list(w) for w in words], {}, lambda *a, **k: None); st = plan["stats"]
            sync = None
            try:
                import story_audit; sync = story_audit.sync_report(al, words)
            except Exception: pass
            stats.update({"audio_s": round(float(end), 1), "shots": st["shots"], "longest_same_picture_s": st["longest_same_picture_s"], "max_shot_s": st["max_len"], "align_coverage": round(float(rep.get("coverage", 0)), 2)})
            lines.append(f"Voice: {end:.0f} s, {int(round(100 * float(rep.get('coverage', 0))))}% of the script words were heard; weak rows: {rep.get('weak') or 'none'}.")
            if sync: lines.append(f"Timing: {sync.get('pct_inside', 0):.0f}% of matched words fall inside their row's window.")
            lines.append(f"Plan: {st['shots']} shots (average {st['avg_len']} s, longest {st['max_len']} s); the same picture stays on screen at most {st['longest_same_picture_s']} s; links {st['tiers'].get('link', 0)}, graphics {st['tiers'].get('graphic', 0)}.")
            if st["longest_same_picture_s"] > 6.5: warnings.append(f"A picture would stay on screen {st['longest_same_picture_s']} s; add a row there.")
        except Exception as e:  # noqa: BLE001 - a check must never raise
            warnings.append(f"The voice check could not run ({e}).")
    else:
        lines.append("No voice transcript yet: timing is estimated. After Generate transcribes the voice, run Check plan again for the exact plan.")
    text = "\n".join(lines + ([""] + [f"ERROR  {e}" for e in errors] if errors else []) + ([""] + [f"warning  {w}" for w in warnings[:40]] + ([f"... and {len(warnings) - 40} more warnings"] if len(warnings) > 40 else []) if warnings else []))
    if not errors and not warnings: text += "\n\nAll checks passed."
    return {"ok": not errors, "errors": errors, "warnings": warnings, "stats": stats, "text": text}
