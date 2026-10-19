"""Narration -> gfx-core template events for a Normal Video (nothing is drawn here).

    plan_graphics(words, total, rows, display_timeline, existing_specs, *, captions=False) -> Plan

Two sources, both limited to the templates allowlist.json lets through:
  auto   gfx_templates.auto_events (the Hybrid Map planner): quotes, numbers, shares, records, versions, dates, named people. Each template's
         own extractor fills its slots from the sentence, so a graphic shows only what was said; its pacing rules apply (nothing in the first 4 s,
         6 s apart, 3 a minute, no repeated fact). Every scene is footage, so each graphic is made for footage: a full-screen plate becomes a soft
         backing under the type only (gfx_templates._footage_backing) and nothing opaque ever covers the picture.
  doc    graphics/doc_plan.plan_doc_extras (the Doc Style detectors: a list, three items, day values, a reason, a strong line, the case file, a glitch
         cut) with each look drawn by its gfx-core template (animated) instead of the still PNG.
Reservations: the windows of the graphics the Normal Video's own planner already placed (names, stats, titles), and of each other; a gfx-core number
replaces a plain stat that shows the same number (its id is in Plan.replaced_graphic_ids, for the caller to leave out of the render).
Geographic templates never appear (allowlist), and a template whose required slots the narration does not fill is skipped, never invented.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import gfx_templates as G


@dataclass
class Plan:
    events: List[Dict[str, Any]] = field(default_factory=list)       # gfx-core map_template events (t_in/t_out in narration time)
    replaced_graphic_ids: List[str] = field(default_factory=list)    # plain stats a template replaced
    notes: List[str] = field(default_factory=list)


def allowlist() -> Dict[str, Any]:
    from map_scene.render import _find

    found = _find("normal_gfx/allowlist.json")
    path = found if found is not None else Path(__file__).with_name("allowlist.json")
    return json.loads(Path(path).read_text(encoding="utf-8"))


def allowed(mode: str, data: Optional[dict] = None) -> List[str]:
    data = data or allowlist()
    out = [t for t, v in data["templates"].items() if v["mode"] == mode or (v["mode"] == "full_frame" and data.get("full_frame_enabled") and mode == "doc" and t in data["doc_looks"].values())]
    return sorted(out)


def _enabled(tid: str, data: Optional[dict] = None) -> bool:
    """May this template be drawn at all: auto / doc, or a full-frame card once the switch for those is on."""
    data = data or allowlist()
    mode = data["templates"].get(tid, {}).get("mode")
    return mode in ("auto", "doc") or (mode == "full_frame" and bool(data.get("full_frame_enabled")))


_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _stat_events(specs: Sequence[Any]) -> List[Dict[str, Any]]:
    """The plain number graphics (graphics/schema.py STATISTIC / DATA) as the stat dicts the template planner compares against."""
    out = []
    for s in specs:
        if str(getattr(s, "role", "")).upper() not in ("STATISTIC", "DATA"):
            continue
        text = str(getattr(getattr(s, "text", None), "text", "") or "")
        m = _NUM.search(text)
        if not m:
            continue
        try:
            value = float(m.group(0).replace(",", ""))
        except ValueError:
            continue
        sub = str(getattr(getattr(s, "text", None), "secondary_text", "") or "")
        out.append({"id": s.graphic_id, "t_in": float(s.start), "t_out": float(s.end), "value_to": value, "format": text, "sub": sub})
    return out


class _Window:
    """A stand-in with the start/end the Doc Style planner reads (a gfx-core event another planner already placed)."""
    def __init__(self, a: float, b: float):
        self.start, self.end = a, b


def _doc_slots(look: str, params: dict, text: str, t0: float, t1: float) -> Tuple[str, Dict[str, Any]]:
    """(template id, slots) for one Doc Style look, or raises KeyError when the look has no animated twin."""
    tid = allowlist()["doc_looks"][look]
    if look == "checklist":
        return tid, {"title": params["title"], "items": list(params["items"])}
    if look == "rings":
        return tid, {"items": list(params["items"])}
    if look == "forecast":
        rows = [{"label": d, "text": v} for d, v in zip(params["days"], params["values"])]
        return tid, {"title": params["title"], "rows": rows, "unit": params.get("unit", "")}
    if look == "panel":
        return tid, {"title": params["title"], "bullets": list(params["bullets"])}
    if look in ("quote", "quote_card"):
        return tid, {"text": str(params["text"]).upper()}
    if look == "dossier":
        return tid, {"title": params["title"], "rows": [{"label": k.title(), "text": v} for k, v in params["fields"]]}
    if look == "glitch":
        return tid, {}
    raise KeyError(look)


def plan_graphics(words: Sequence[Tuple[str, float, float]], total: float, rows: Sequence[dict], display_timeline: Sequence[Tuple[float, float]],
                  existing_specs: Sequence[Any], *, captions: bool = False, log=print) -> Plan:
    data = allowlist()
    plan = Plan()
    taken: List[Tuple[float, float]] = [(float(s.start), float(s.end)) for s in existing_specs or []
                                        if str(getattr(s, "decision", "")) != "WATERMARK"]
    # ---- auto: the narration's own facts, through the Hybrid planner ----
    try:
        replaced: List[str] = []
        autos = G.auto_events(words, niche="map", taken=taken, total=total, id_prefix="ngfx", enabled=allowed("auto", data),
                              stats=_stat_events(existing_specs), replaced=replaced, footage=[(0.0, float(total))],
                              narration_fill=False)   # the Hybrid clip-fill and dates recap are for real footage clips
        for ev in autos:
            if str(ev.get("template", {}).get("id")) in data["templates"] and data["templates"][ev["template"]["id"]]["mode"] == "excluded":
                continue
            plan.events.append(ev)
        stats = _stat_events(existing_specs)
        for ev in plan.events:      # which plain stats each template replaces (so a stat goes only when its replacement is really drawn)
            ids = [st["id"] for st in stats if st["id"] in replaced and G.stat_is_redundant(st, ev["template"].get("id"), ev.get("slots") or {})
                   and st["t_in"] - 1.0 < ev["t_out"] and ev["t_in"] < st["t_out"] + 1.0]
            if ids:
                ev["replaces"] = ids
        plan.replaced_graphic_ids = sorted(set(replaced))
    except Exception as exc:
        plan.notes.append(f"narration graphics skipped ({exc})")
    # ---- rules.py: a question the narrator asks, a part title ("Part two"); they take their time before the Doc Style detectors look ----
    try:
        from . import rules as R

        busy = sorted(list(taken) + [(e["t_in"], e["t_out"]) for e in plan.events])
        plan.events += R.new_events(words, total, busy, plan.events, len(plan.events))
    except Exception as exc:
        plan.notes.append(f"question and part-title rules skipped ({exc})")
    # ---- doc: the Doc Style detectors, drawn by their animated templates ----
    try:
        from graphics.doc_plan import plan_doc_extras

        reserved = list(existing_specs or []) + [_Window(e["t_in"], e["t_out"]) for e in plan.events]
        extras = plan_doc_extras(list(rows), list(display_timeline), [r for r in reserved if r not in ()], lambda _k: None, channel="")
        wanted = set(data["doc_looks"])
        for spec in extras:
            look = str((spec.payload or {}).get("doc_look") or "")
            if look not in wanted or not _enabled(data["doc_looks"][look], data):
                continue
            if look in ("quote", "quote_card") and re.search(r"[\"“”]|\b(?:Dr|Mr|Mrs|Ms|Prof|St)\.\s*$", str(getattr(spec.text, "text", "") or "")):
                plan.notes.append(f"{look} skipped: the sentence holds a quotation or was cut at an abbreviation")
                continue                       # a quotation has its own template (quote_card); half a sentence is never shown
            try:
                tid, slots = _doc_slots(look, (spec.payload or {}).get("doc_params") or {}, str(getattr(spec.text, "text", "") or ""), spec.start, spec.end)
                ev, _hold = G.event_for(tid, {}, event_id=f"ngfx_doc_{look}_{len(plan.events) + 1}", t_in=float(spec.start), t_out=float(spec.end), extra=slots, words=words)
            except (KeyError, ValueError) as exc:
                plan.notes.append(f"{look} skipped ({exc})")
                continue
            ev["template"] = G._footage_backing(ev["template"])
            ev["over_footage"] = True
            plan.events.append(ev)
    except Exception as exc:
        plan.notes.append(f"Doc Style graphics skipped ({exc})")
    # ---- the variants (normal_gfx/rules.py): the same facts in the least-used look ----
    try:
        from . import rules as R

        rot = R.Rotation()
        plan.events.sort(key=lambda e: e["t_in"])
        plan.events = [R.adapt(e, rot) for e in plan.events]
    except Exception as exc:
        plan.notes.append(f"template variants skipped ({exc})")
    plan.events.sort(key=lambda e: e["t_in"])
    # never two at once (the planners reserve each other's windows; this is the guarantee)
    kept: List[Dict[str, Any]] = []
    for e in plan.events:
        if kept and e["t_in"] < kept[-1]["t_out"] - 1e-6:
            plan.notes.append(f"{e['id']} skipped: overlaps {kept[-1]['id']}")
            continue
        kept.append(e)
    plan.events = kept
    return plan
