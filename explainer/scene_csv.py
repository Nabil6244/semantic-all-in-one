"""The Explainer scene CSV: one spreadsheet that says, for each stretch of narration, where it happens, when, in what architecture, who is there and how they look.

    row    what it is            columns used
    cast   a recurring person    id, name, look (age, face, clothing: written once, repeated in every picture that has the person)
    scene  a stretch of story    vo_anchor (the first words of the narration it covers), place, type, region, period, architecture, background, people (cast ids, comma-separated),
                                 activity, objects, mood, continues (yes when the narration stays in the same scene), route (auto | compose | flow)

A scene ends where the next scene starts (the last one at the end of the narration). `read` returns the planner's `scene_notes` (explainer/scene_intel.from_notes) plus the place names and problems;
nothing is guessed, and a row it cannot use is reported with its row number, never silently dropped. A scene that repeats the previous scene's place and people without `continues: yes` is
reported (the same backdrop twice in a row is what the tool must not do)."""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Sequence

COLUMNS = ("row", "scene", "vo_anchor", "id", "name", "look", "place", "type", "region", "period", "architecture", "background", "people", "activity", "objects", "mood", "continues", "route")


def is_scene_csv(text: str) -> bool:
    head = (text or "").lstrip("﻿ \n\r").split("\n", 1)[0].strip().lower().replace(" ", "")
    return head.startswith("row,scene,vo_anchor")


def read(text: str, words: Sequence, duration: float) -> Dict[str, Any]:
    """-> {"scene_notes": [{"start", "end", "text"}], "places": [...], "cast": {id: look}, "problems": [...], "notes": [...]}. Never raises on a bad row."""
    from anchor_clock import AnchorClock

    rows = list(csv.DictReader(io.StringIO((text or "").lstrip("﻿"))))
    problems: List[str] = []
    notes: List[str] = []
    cast: Dict[str, str] = {}
    scenes: List[Dict[str, Any]] = []
    clock = AnchorClock(words, notes)
    for n, r in enumerate(rows, start=2):
        r = {k: (v or "").strip() for k, v in r.items() if k}
        kind = r.get("row", "").lower()
        if kind == "cast":
            if not r.get("id") or not r.get("look"):
                problems.append(f"row {n}: a cast row needs an id and a look")
                continue
            cast[r["id"].lower()] = (r.get("name") or r["id"]) + ", " + r["look"]
        elif kind == "scene":
            if not r.get("vo_anchor"):
                problems.append(f"row {n}: a scene row needs vo_anchor (the first words of the narration it covers)")
                continue
            try:
                t = clock.at(r["vo_anchor"], advance=True, before=scenes[-1]["anchor"] if scenes else "")
            except Exception as exc:
                problems.append(f"row {n}: the words {r['vo_anchor']!r} were not found in the narration ({str(exc)[:80]})")
                continue
            if t is None:
                problems.append(f"row {n}: the words {r['vo_anchor']!r} were not found in the narration")
                continue
            scenes.append({"row": n, "start": 0.0 if not scenes else float(t), "anchor": r["vo_anchor"], "r": r})
        elif kind:
            problems.append(f"row {n}: unknown row kind {kind!r} (cast or scene)")
    out: List[Dict[str, Any]] = []
    places: List[str] = []
    prev_key = None
    for k, sc in enumerate(scenes):
        r = sc["r"]
        end = scenes[k + 1]["start"] if k + 1 < len(scenes) else float(duration)
        looks = []
        for pid in [x.strip().lower() for x in r.get("people", "").split(",") if x.strip()]:
            if pid in cast:
                looks.append(cast[pid])
            else:
                problems.append(f"row {sc['row']}: person {pid!r} has no cast row")
        parts = [("place", r.get("place")), ("type", r.get("type")), ("region", r.get("region")), ("period", r.get("period")), ("architecture", r.get("architecture")),
                 ("background", r.get("background")), ("people", r.get("people")), ("activity", r.get("activity")), ("objects", r.get("objects")), ("mood", r.get("mood")),
                 ("continues", r.get("continues")), ("route", r.get("route")), ("looks", " | ".join(looks))]
        out.append({"start": sc["start"], "end": end, "text": "; ".join(f"{a}: {b.replace(';', ',')}" for a, b in parts if b)})
        for nm in (r.get("region"), r.get("place")):
            if nm and nm not in places:
                places.append(nm)
        key = (r.get("place", "").lower(), r.get("background", "").lower(), tuple(sorted(x.strip().lower() for x in r.get("people", "").split(","))))
        if key == prev_key and r.get("continues", "").lower() not in ("yes", "true", "1", "y"):
            problems.append(f"row {sc['row']}: the same place, backdrop and people as the scene before; give it a different place or backdrop, or set continues to yes")
        prev_key = key
    return {"scene_notes": out, "places": places, "cast": cast, "problems": problems, "notes": notes}
