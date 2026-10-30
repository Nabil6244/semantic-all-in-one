"""Cadence measurement for Rep Theory plans. Everything is derived from the scene dicts the renderer consumes (not from the planner's intentions), so the legacy plan and the beat plan are
measured by the same code and the numbers are comparable. Two event types are kept apart:
  primary   = the composition changes (a new scene: new picture / board / callout layout)
  secondary = something develops inside the composition (a new callout page, a chip, a ring, a glow, an equation term, a tier mark, a grip, a hand switch, a squeeze)
Targets (diagnostic, not permission to add meaningless motion): secondary roughly every 2-3.5 s, primary at most about 6-8 s unless a continuous development justifies the hold."""
from __future__ import annotations
import json, statistics
from pathlib import Path
from typing import Dict, List

PRIMARY_MAX_S, SECONDARY_MAX_S = 8.0, 3.5
CONTINUOUS = {"tier": "the tier board builds row by row and places the item", "equation": "the equation lockup builds term by term"}

DRAWS_PAGE_TEXT = {"callout", "trainee", "pose", "prop", "hold", "sketch", "illus"}      # kinds whose callout column shows a page's headline / value; anatomy and equation scenes only show a page's chips (anatomy's label is its glow's)

def _sig(sc: dict) -> tuple:
    sk = sc.get("sketch") or {}; return (sc["kind"], sk.get("move") or sc.get("art") or "", sk.get("variant") or sc.get("prop") or "")

def events(scenes: List[dict]) -> List[dict]:
    """[{t, type: primary|secondary, what, scene, meaningful}] sorted by time.
    primary   = a new composition (its kind / picture / prop differs from the scene before): the viewer is looking at something else.
    secondary = something develops. `meaningful` is False for repeated decoration (a pulse on a word, a ring that stays where it was, a cut to the same composition), True for a change of what is communicated."""
    ev: List[dict] = []; prev = None
    for sc in scenes:
        n = sc.get("no"); new_comp = prev is None or _sig(sc) != _sig(prev)
        ev.append({"t": float(sc["start"]), "type": "primary" if new_comp else "secondary", "what": f"{sc['kind']} composition" if new_comp else f"new {sc['kind']} page (cut)", "scene": n, "meaningful": new_comp or sc["kind"] == "callout", "boundary": True})
        shown = sc["kind"] in DRAWS_PAGE_TEXT
        for i, pg in enumerate(sc.get("pages", [])):
            if i and shown: ev.append({"t": float(pg["at"]), "type": "secondary", "what": "callout page", "scene": n, "target": pg.get("headline", ""), "meaningful": True})
            if shown and pg.get("headline") and (i or pg.get("headline_at", 0) > sc["start"] + 0.05): ev.append({"t": float(pg.get("headline_at", pg["at"])), "type": "secondary", "what": "headline", "scene": n, "target": pg["headline"], "meaningful": True})
            for c in pg.get("chips", []): ev.append({"t": float(c["at"]), "type": "secondary", "what": "chip", "scene": n, "target": c["text"], "meaningful": True})
            if shown and pg.get("value"): ev.append({"t": float(pg.get("value_at", pg.get("headline_at", pg["at"]) + 0.25)), "type": "secondary", "what": "value", "scene": n, "target": pg["value"], "meaningful": True})
        seen_ring: set = set()
        for r in sc.get("rings", []):
            key = (r.get("x"), r.get("y")); ev.append({"t": float(r["at"]), "type": "secondary", "what": "ring", "scene": n, "meaningful": key not in seen_ring}); seen_ring.add(key)
        for q in sc.get("squeezes", []): ev.append({"t": float(q), "type": "secondary", "what": "squeeze", "scene": n, "meaningful": False})
        for e in sc.get("equations", []): ev += [{"t": float(e["at_l"]), "type": "secondary", "what": "equation term", "scene": n, "meaningful": True}, {"t": float(e["at_r"]), "type": "secondary", "what": "equation term", "scene": n, "meaningful": True}]
        for m in sc.get("tier_marks", []): ev.append({"t": float(m["at"]), "type": "secondary", "what": "tier mark", "scene": n, "meaningful": True})
        tr = sc.get("tier")
        if tr and tr.get("letter") and tr.get("at", 1e9) < sc["end"] + 5: ev.append({"t": float(tr["at"]), "type": "secondary", "what": "tier placement", "scene": n, "meaningful": True})
        seen_g: set = set()
        for g in sorted((sc.get("glows") or ([sc["glow"]] if sc.get("glow") else [])), key=lambda g: g["at"]):
            key = (g.get("label"), tuple(map(tuple, g.get("regions", ())))); ev.append({"t": float(g["at"]), "type": "secondary", "what": "glow", "scene": n, "target": g.get("label", ""), "meaningful": key not in seen_g}); seen_g.add(key)
        if sc.get("grip_at") is not None: ev.append({"t": float(sc["grip_at"]), "type": "secondary", "what": "grip ring", "scene": n, "meaningful": True})
        if sc.get("flip_at") is not None: ev.append({"t": float(sc["flip_at"]), "type": "secondary", "what": "hand switch", "scene": n, "meaningful": True})
        for c in sc.get("cues", []): ev.append({"t": float(c["at"]), "type": "secondary", "what": c.get("what", "cue"), "scene": n, "meaningful": True})
        prev = sc
    return sorted(ev, key=lambda e: (e["t"], e["type"] != "primary"))

def _stats(gaps: List[float]) -> dict:
    if not gaps: return {"n": 0, "median": None, "p90": None, "max": None}
    g = sorted(gaps); p90 = g[min(len(g) - 1, int(round(0.9 * (len(g) - 1))))]
    return {"n": len(g), "median": round(statistics.median(g), 2), "p90": round(p90, 2), "max": round(g[-1], 2)}

def _gaps(times: List[float], total: float) -> List[dict]:
    ts = sorted(set(round(t, 3) for t in times if 0 <= t <= total)); marks = ts + [total]
    return [{"t0": a, "t1": b, "gap": round(b - a, 2)} for a, b in zip(marks, marks[1:])]

def _scene_at(scenes: List[dict], t: float) -> dict:
    return next((s for s in scenes if s["start"] <= t + 1e-6 < s["end"]), scenes[-1])

def _window(scenes: List[dict], ev: List[dict], t0: float, t1: float) -> dict:
    """What is on screen in [t0, t1): the words spoken, the visual, and the texts shown, for the report."""
    sc = _scene_at(scenes, (t0 + t1) / 2); words = " ".join(w["w"] for s in scenes for w in s.get("words", []) if t0 - 1e-6 <= w["t0"] < t1 + 1e-6)
    shown = [f"{e['t']:.1f}s {e['what']}" + (f" '{e['target']}'" if e.get("target") else "") for e in ev if t0 <= e["t"] < t1 and e["type"] == "secondary"]
    return {"scene": sc.get("no"), "kind": sc["kind"], "visual": ":".join(x for x in _sig(sc) if x), "narration": words, "developments": shown}

def metrics(scenes: List[dict], total: float = 0.0) -> dict:
    """Gap statistics, kept apart: primary (new composition), meaningful secondary (what is communicated changes), any meaningful development, and the old scene-boundary gaps for comparison with earlier plans.
    Decoration (a pulse, a ring that stays, a cut to the same composition) never closes a gap. Every over-limit gap is listed with its time range, narration, visual, developments inside and a justification."""
    total = total or (scenes[-1]["end"] if scenes else 0.0); ev = events(scenes)
    prim = [e["t"] for e in ev if e["type"] == "primary"]; sec = [e["t"] for e in ev if e["type"] == "secondary" and e["meaningful"]]; deco = [e for e in ev if e["type"] == "secondary" and not e["meaningful"]]
    bounds = [float(s["start"]) for s in scenes]
    gp, gs, ga, gb = _gaps(prim, total), _gaps(sec, total), _gaps(prim + sec, total), _gaps(bounds, total)
    over: List[dict] = []
    for g in gp:
        if g["gap"] > PRIMARY_MAX_S:
            w = _window(scenes, ev, g["t0"], g["t1"]); inner = sorted([g["t0"]] + [e["t"] for e in ev if e["type"] == "secondary" and e["meaningful"] and g["t0"] < e["t"] < g["t1"]] + [g["t1"]])
            n = len(inner) - 2; worst = max(b - a for a, b in zip(inner, inner[1:])); why = CONTINUOUS.get(w["kind"], "")
            ok = bool(why) or (n >= 2 and worst <= SECONDARY_MAX_S)
            over.append({"event": "primary", **g, **w, "meaningful_events_inside": n, "largest_internal_gap": round(worst, 2), "development": n > 0, "hold_justified": ok,
                         "justification": why or (f"the composition holds with continuous meaningful development ({n} changes of what is communicated, largest gap {worst:.1f} s)" if ok else f"unjustified: {n} meaningful changes inside, largest gap {worst:.1f} s")})
    for g in ga:
        if g["gap"] > SECONDARY_MAX_S:
            w = _window(scenes, ev, g["t0"], g["t1"]); why = CONTINUOUS.get(w["kind"], "")
            over.append({"event": "any", **g, **w, "meaningful_events_inside": 0, "development": bool(why), "hold_justified": bool(why), "justification": why or "unjustified: nothing that changes what is communicated happens"})
    kinds: Dict[str, int] = {}
    for s in scenes: kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
    arts = [(s["kind"], s.get("art") or "", s.get("prop") or "") for s in scenes]; repeats = sum(1 for a, b in zip(arts, arts[1:]) if a == b)
    return {"duration": round(total, 2), "scenes": len(scenes), "events": {"primary": len(prim), "secondary_meaningful": len(sec), "secondary_decorative": len(deco)}, "primary_gaps": _stats([g["gap"] for g in gp]), "secondary_only_gaps": _stats([g["gap"] for g in gs]),
            "any_development_gaps": _stats([g["gap"] for g in ga]), "scene_boundary_gaps": _stats([g["gap"] for g in gb]), "over_limit": over, "scene_lengths": _stats([round(s["end"] - s["start"], 2) for s in scenes]), "kind_counts": kinds, "consecutive_same_composition": repeats,
            "limits": {"primary_max_s": PRIMARY_MAX_S, "secondary_max_s": SECONDARY_MAX_S}}

def _row(b: dict) -> str:
    v = b.get("visual", {}); st = b.get("status", "")
    return (f"| {b['id']} | {b['t0']:.1f}-{b['t1']:.1f} ({b['timing']}) | {b['role']} | {', '.join(b.get('entity_summary', [])) or '-'} | {v.get('key', '-')} | {st} | {b['confidence']:.2f} | {b.get('unit') or '-'} | "
            f"{b['text'].replace('|', '/')} |")

def write_report(path, plan: dict) -> None:
    """plan = {title, planner, timing, beats, scenes, metrics, narrative, summary}. Writes <path>.json and <path>.md next to each other."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    slim = dict(plan); slim["scenes"] = [{k: v for k, v in s.items() if k not in ("words",)} for s in plan.get("scenes", [])]
    Path(str(path) + ".json").write_text(json.dumps(slim, indent=1, default=str), encoding="utf-8")
    m = plan["metrics"]; lines = [f"# Rep Theory plan: {plan.get('title', '')}", "", f"planner `{plan.get('planner')}` · timing `{plan.get('timing')}` · {m['scenes']} scenes · {m['duration']} s", ""]
    s = plan.get("summary")
    if s: lines += ["## Summary", ""] + [f"- {k}: {v}" for k, v in s.items()] + [""]
    lines += ["## Cadence", "", "| event type | n | median gap | p90 | max |", "|---|---|---|---|---|"]
    for lab, key in (("primary (composition change)", "primary_gaps"), ("secondary only (development inside a composition)", "secondary_only_gaps"), ("any development", "any_development_gaps"), ("scene boundaries (old measure)", "scene_boundary_gaps"), ("scene length", "scene_lengths")):
        g = m[key]; lines.append(f"| {lab} | {g['n']} | {g['median']} | {g['p90']} | {g['max']} |")
    lines += ["", f"Over-limit gaps (primary > {m['limits']['primary_max_s']} s, any > {m['limits']['secondary_max_s']} s): {len(m['over_limit'])}", ""]
    for o in m["over_limit"]:
        lines += [f"- **{o['event']} {o['t0']:.1f}-{o['t1']:.1f} s ({o['gap']} s)** scene {o['scene']} `{o['visual']}` · development inside: {'yes' if o['development'] else 'no'} · justified: {'yes' if o['hold_justified'] else 'NO'}",
                  f"  - narration: \"{o['narration']}\"", f"  - {o['justification']}", f"  - developments: {', '.join(o['developments']) or 'none'}"]
    if plan.get("narrative"): lines += ["", "## Narrative elements found", "", "```json", json.dumps(plan["narrative"], indent=1, default=str), "```"]
    if plan.get("beats"):
        lines += ["", "## Beats", "", "| id | time (timing) | role | entities | visual | status | conf | unit | text |", "|---|---|---|---|---|---|---|---|---|"] + [_row(b) for b in plan["beats"]]
        bad = [b for b in plan["beats"] if b.get("status") not in ("grounded",)]
        lines += ["", f"## Not grounded ({len(bad)})", ""] + [f"- {b['id']} [{b.get('status')}] {b['text']} → {b.get('reason', '')}" for b in bad]
    Path(str(path) + ".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
