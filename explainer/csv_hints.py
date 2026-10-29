"""A Hybrid CSV as guidance for the Explainer director: the CSV says where footage goes and which places the story visits; the director still builds every board, narrator and caption beat.
`read(text, words, duration)` reads the CSV with the same importers as Load CSV (so rows land on the narrator's words) and returns the footage spans and place names.
`apply(plan, hints)` turns each director beat that falls inside a footage span into a footage beat that uses the CSV's clips. Nothing outside a span changes."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

FOOTAGE_MODES = ("footage", "map_footage")


def read(text: str, words: Sequence, duration: float) -> Dict[str, Any]:
    """-> {"spans": [{"start", "end", "clips": [{"asset", "reason"}]}], "places": [...], "notes": [...]}. Raises what the importers raise (a CSV with problems)."""
    from hybrid.beat_csv import import_beats, is_beat_csv
    from hybrid.csv_import import plan_from_csv

    got = (import_beats if is_beat_csv(text) else plan_from_csv)(text, words, duration)
    spans: List[Dict[str, Any]] = []
    places: List[str] = []
    for b in got.plan.beats:
        clips = [{"asset": c.asset, "reason": c.reason or "from the loaded CSV"} for c in b.clips if str(c.asset or "").strip()]
        if b.mode in FOOTAGE_MODES and clips:
            spans.append({"start": float(b.start), "end": float(b.end), "clips": clips})
        for name in [b.cam_place] + [s.place for s in b.camera]:
            name = (name or "").strip()
            if name and name not in places and not _is_coordinate(name):
                places.append(name)
    return {"spans": spans, "places": places, "notes": list(getattr(got, "notes", []) or [])}


def _is_coordinate(name: str) -> bool:
    parts = name.replace(" ", "").split(",")
    if len(parts) != 2:
        return False
    try:
        float(parts[0]), float(parts[1])
        return True
    except ValueError:
        return False


def apply(plan: Dict[str, Any], hints: Dict[str, Any]) -> List[str]:
    """Edits the director's plan dict in place; returns log lines. A span covering several beats gives its clips to those beats in order (cycling)."""
    notes: List[str] = []
    beats = plan.get("beats") or []
    for span in hints.get("spans") or []:
        inside = [b for b in beats if span["start"] - 1e-6 <= (float(b["start"]) + float(b["end"])) / 2 < span["end"] + 1e-6]
        if not inside:
            notes.append(f"CSV footage at {span['start']:.1f}s has no Explainer beat under it; skipped.")
            continue
        for k, b in enumerate(inside):
            clip = span["clips"][k % len(span["clips"])]
            b["mode"] = "footage"
            b["footage"] = {"clips": [dict(clip)]}
            b["purpose"] = "explainer footage from the loaded CSV"
            for key in ("layers", "camera", "support", "more_cards"):
                b.pop(key, None)
        notes.append(f"CSV footage at {span['start']:.1f}-{span['end']:.1f}s: {len(inside)} beat(s) became footage.")
    return notes
