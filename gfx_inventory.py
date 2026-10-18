"""The graphics library, template by template, from the real registry (gfx-core/templates): what each graphic needs, whether it draws, where it may be
used (over the map, above footage, as a full-screen plate), whether the production planner can place it on its own, and if not, exactly why not.

    python gfx_inventory.py            # writes docs/hybrid/template_inventory.md and .json

Nothing here is a count to trust from a document: the numbers are computed from the registry every time (the tests check them against it)."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import gfx_templates as G

_SERIES = {"rows", "values", "labels"}


def _needs(t: Dict[str, Any]) -> List[str]:
    out = []
    for name, spec in (t.get("slots") or {}).items():
        if spec.get("required"):
            out.append(f"{name} ({spec.get('from') or 'params.slots'})")
    return out


def _why_not_auto(t: Dict[str, Any]) -> str:
    """The exact condition that keeps this graphic out of the automatic planner (empty when it has a rule)."""
    if t["id"] in G.RULES:
        return ""
    if t["id"] == "tag_fact":
        return "an extractor exists (superlatives) but it is not a rule: on the real project every tag restated a caption, counter or marker the plan already showed"
    if t["id"] in G.DOC_STYLE_TWINS:
        return "placed by Doc Style as the look of the plan's own title chips, captions and counters (not by narration rules)"
    required = {s.get("from") or n: n for n, s in (t.get("slots") or {}).items() if s.get("required")}
    if G.map_bound(t):
        return "sits on the map (needs places or follows one): the planner does not know what the camera shows, so it is written into a map beat by the plan"
    if G.needs_picture(t):
        return "needs a picture of its own, which the narration does not supply"
    if not (t.get("slots") or {}) or t["family"] == "text":
        return "a pure text or transition effect: nothing in the narration says when it belongs, so it is never forced (an author may still ask for it)"
    series = [k for k in required if k in _SERIES]
    if series:
        return f"needs {'/'.join(sorted(series))}: a table or series of figures that a spoken sentence rarely states completely (no figure is invented to fill it)"
    if any(n in ("date", "prev_date", "year_from", "year_to", "frames", "before", "after", "total") for n in required.values()):
        return "needs figures (dates, frames, before/after values) of its own that no sentence supplies reliably"
    return "no extractor yet reads its required slots from a sentence: " + ", ".join(_needs(t))


def _render_check(lib: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """{template id: {"map": fatal|None, "footage": fatal|None, "repairs": [...]}} from the mock-canvas dry run of pakmap-engine (node)."""
    from pakmap.guard import check_gfx

    events = []
    for tid, t in lib.items():
        tpl = G._public(t)
        hold = float(t.get("hold", 6))
        base = {"type": "map_template", "template": tpl, "slots": {}, "t_in": 0.0, "t_out": hold}
        events.append({**base, "id": f"{tid}__map", **({"follow": {"lon": 0.0, "lat": 0.0}} if any(it.get("follow") for it in G._all_items(t)) else {})})
        if not G.map_bound(t):
            events.append({**base, "id": f"{tid}__footage", "template": G._footage_backing(copy.deepcopy(tpl)), "over_footage": True})
    got = check_gfx({"width": 1280, "height": 720, "events": events})
    out: Dict[str, Dict[str, Any]] = {}
    for tid in lib:
        m, f = got.get(f"{tid}__map"), got.get(f"{tid}__footage")
        out[tid] = {"map": (m or {}).get("fatal") if m is not None else "not checked", "footage": ((f or {}).get("fatal") if f is not None else ("n/a (sits on the map)" if G.map_bound(lib[tid]) else "not checked")),
                    "repairs": list((m or {}).get("repairs", []))}
    return out


def inventory(render_check: bool = True) -> List[Dict[str, Any]]:
    lib = G.load_library()
    checks = _render_check(lib) if render_check else {}
    in_auto = {}
    for tid, _pat, _fn in G.AUTO:
        in_auto.setdefault(tid, 0)
        in_auto[tid] += 1
    rows = []
    for tid, t in lib.items():
        c = checks.get(tid, {})
        footage_problem = G.over_footage_problem(tid)
        rule = G.RULES.get(tid)
        rows.append({
            "id": tid, "family": t["family"], "use": t["use"], "niches": t.get("niches", []), "hold_s": t.get("hold"), "full_screen_plate": bool(t.get("plate")),
            "required": _needs(t), "map_bound": G.map_bound(t), "needs_picture": G.needs_picture(t),
            "renders_on_map": (c.get("map") is None) if c else None, "renders_over_footage": None if (not c or G.map_bound(t)) else (c.get("footage") is None),
            "render_problem": (c.get("map") or (None if G.map_bound(t) else c.get("footage"))) if c else None,
            "context_map": "map" in t.get("niches", []) or "any" in t.get("niches", []),
            "context_over_footage": footage_problem is None,
            "over_footage_problem": footage_problem,
            "plan_layer_on_map_beat": True, "plan_layer_on_footage_beat": footage_problem is None,
            "auto_rule": bool(rule), "auto_rows": in_auto.get(tid, 0), "rule": ({k: (list(v) if isinstance(v, tuple) else v) for k, v in rule.items()} if rule else None),
            "why_not_auto": _why_not_auto(t),
        })
    return rows


def summary(rows: List[Dict[str, Any]], used: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    n = len(rows)
    out = {
        "templates_in_library": n,
        "technically_renderable": sum(1 for r in rows if r["renders_on_map"]) if rows and rows[0]["renders_on_map"] is not None else None,
        "eligible_over_the_map": sum(1 for r in rows if r["context_map"]),
        "eligible_over_footage": sum(1 for r in rows if r["context_over_footage"]),
        "full_screen_plates": sum(1 for r in rows if r["full_screen_plate"]),
        "map_only": sum(1 for r in rows if r["map_bound"]),
        "with_an_automatic_rule": sum(1 for r in rows if r["auto_rule"]),
    }
    if used is not None:
        out["selected_by_the_planner_in_this_project"] = len(used)
    return out


def markdown(rows: List[Dict[str, Any]], used: Optional[Dict[str, int]] = None) -> str:
    s = summary(rows, used)
    lines = ["# Graphics template inventory", "",
             "Generated by `python gfx_inventory.py` from `gfx-core/templates` (the registry is the source of truth). Do not edit by hand.", ""]
    lines += [f"- templates in the library: **{s['templates_in_library']}**",
              f"- technically renderable (mock-canvas dry run, default slots): **{s['technically_renderable']}**",
              f"- eligible over the map: **{s['eligible_over_the_map']}**; eligible above footage: **{s['eligible_over_footage']}** ({s['map_only']} are map-only)",
              f"- with an implemented automatic placement rule: **{s['with_an_automatic_rule']}**", ""]
    lines += ["| template | family | renders | map | footage | plate | auto rule | why it is not placed automatically |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        ok = {True: "yes", False: "NO", None: "?"}
        lines.append(f"| {r['id']} | {r['family']} | {ok[r['renders_on_map']]} | {'yes' if r['context_map'] else 'no'} | {'yes' if r['context_over_footage'] else 'no'} | "
                     f"{'yes' if r['full_screen_plate'] else ''} | {'yes' if r['auto_rule'] else ''} | {r['why_not_auto']} |")
    lines += ["", "## Automatic placement rules", ""]
    for r in rows:
        if r["rule"]:
            ru = r["rule"]
            lines += [f"### {r['id']}", f"- requires: {ru['requires']}", f"- eligible when: {ru['eligible']}", f"- where: {', '.join(ru['where'])}", f"- placement: {ru['placement']}",
                      f"- timing: {ru['timing']}", f"- fallback: {ru['fallback']}", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    rows = inventory()
    out = root / "docs" / "hybrid"
    out.mkdir(parents=True, exist_ok=True)
    (out / "template_inventory.json").write_text(json.dumps({"summary": summary(rows), "templates": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "template_inventory.md").write_text(markdown(rows), encoding="utf-8")
    print(json.dumps(summary(rows), indent=1))
    sys.exit(0)
