"""The UI-independent entry points the app's Hybrid Map mode calls (no Tk, like pakmap.app_integration)."""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Sequence

from .compile import HybridCompileError, compile_plan, plan_to_rows
from .pipeline import PlanResult, plan_hybrid
from .plan import HybridPlan
from .validate import Finding, errors, validate, warnings

MODE_LABEL = {"map": "MAP", "footage": "FOOTAGE", "map_footage": "MAP+FOOTAGE"}


def plan_with_ai(words: Sequence, script: Optional[str], settings: Dict[str, Any], *, duration: Optional[float] = None,
                 on_progress: Optional[Callable[[str], None]] = None, style_guidance: str = "", llm: Any = None, checkpoint_dir: Any = None,
                 state_dir: Any = None) -> PlanResult:
    """Script + timed narration -> a validated, locally-fixed, conditionally critiqued plan. The AI requests go through the AI router
    (Gemini and Groq, per task); `llm` lets a caller supply its own."""
    if llm is None:
        from ai_router import MISSING_AI_KEY, providers_configured, router_from_settings

        if not any(providers_configured(settings).values()):
            raise RuntimeError(MISSING_AI_KEY)
        llm = router_from_settings(settings, state_dir=state_dir)
    return plan_hybrid(words, llm, script=script, duration=duration, style_guidance=style_guidance, on_progress=on_progress, checkpoint_dir=checkpoint_dir)


_LABEL = re.compile(r"^beat (\S+) · (?:footage clip (\d+)|(supporting card))")


def _scene_map(plan: HybridPlan) -> List[dict]:
    """Every picture or clip the plan needs, in the order (and with the numbers) the generator and the Visual Plan table use."""
    from pakmap.sourcing import find_occurrences

    rows, line_map, _ = plan_to_rows(plan)
    out = []
    for o in find_occurrences(rows):
        m = _LABEL.match(line_map.get(o.line, ""))
        out.append({"occ": o, "beat": m.group(1) if m else "", "clip": int(m.group(2)) if m and m.group(2) else 0, "card": bool(m and m.group(3))})
    return out


def visual_dicts(plan: HybridPlan) -> List[dict]:
    """The plan's footage as rows for the EXISTING Visual Plan table: one per clip and per supporting card. Map beats are not rows: there
    is nothing to replace in them (they stay in the plan view)."""
    beats = {b.id: b for b in plan.beats}
    order = list(beats)
    out = []
    for item in _scene_map(plan):
        o, b = item["occ"], beats.get(item["beat"])
        n = order.index(item["beat"]) + 1 if b else 0
        what = "supporting card" if item["card"] else (f"footage, clip {item['clip']}/{len(b.clips)}" if b and len(b.clips) > 1 else "footage")
        why = ((b.support.label if item["card"] and b.support and b.support.label else "") or b.footage_intent or b.purpose) if b else ""
        ch = f"Ch {b.chapter} · " if b and b.chapter else ""
        out.append({"scene_number": str(o.scene_number), "script_segment": f"{_span(b.start) if b else ''}  {ch}Hybrid beat {n:02d} · {what} — {why}".strip(),
                    "asset_type": o.kind, "prompt": o.prompt})
    return out


def _span(t: float) -> str:
    return f"{int(t // 60)}:{int(t % 60):02d}"


def plan_text(plan: HybridPlan, findings: Optional[Sequence[Finding]] = None, *, scene_status: Optional[Dict[str, str]] = None, report: Optional[PlanResult] = None) -> str:
    """The Check plan view: the editorial structure, beat by beat."""
    findings = list(findings) if findings is not None else validate(plan)
    map_s = sum(b.end - b.start for b in plan.beats if b.mode != "footage")
    lines = [f"Hybrid plan: {len(plan.beats)} beats, {plan.duration:.1f}s  ·  map {100 * map_s / plan.duration:.0f}% / footage {100 * (plan.duration - map_s) / plan.duration:.0f}%"]
    scenes: Dict[str, List[str]] = {}
    for item in _scene_map(plan):
        scenes.setdefault(item["beat"], []).append(str(item["occ"].scene_number))
    chapter_of = {int(c["id"]): c for c in plan.chapters if "id" in c}
    seen_chapter = 0
    for i, b in enumerate(plan.beats, 1):
        if b.chapter and b.chapter != seen_chapter:
            seen_chapter = b.chapter
            c = chapter_of.get(b.chapter, {})
            lines.append(f"\n=== Chapter {b.chapter}: {c.get('title', '')} ({_span(float(c.get('start', b.start)))}-{_span(float(c.get('end', b.end)))}) ===")
        conf = f"  confidence {b.confidence:.2f}" if b.confidence < 1.0 else ""
        lines.append(f"\n #{i:<2} {_span(b.start)}-{_span(b.end)} ({b.end - b.start:4.1f}s)  {MODE_LABEL[b.mode]:<11} [{b.validation or '-'}]{conf}")
        if b.purpose:
            lines.append(f"       why: {b.purpose}")
        if b.mode == "footage":
            if b.footage_intent:
                lines.append(f"       footage: {b.footage_intent}")
        else:
            if b.geo_intent:
                lines.append(f"       map: {b.geo_intent}")
            cam = f"{b.cam_place} ({b.cam_frame})" if b.cam_place else ", ".join(f"{c.action} {c.place}".strip() for c in b.camera)
            if cam:
                lines.append(f"       camera: {cam}")
            if b.layers:
                lines.append("       layers: " + ", ".join(f"{l.type} {l.label or l.place or l.text or ''}".strip() + f" @{_span(l.t)}" for l in b.layers))
        for c in b.clips:
            lines.append(f"       clip: {c.asset}" + (f"  — {c.reason}" if c.reason else ""))
        if b.support:
            lines.append(f"       card: {b.support.asset}" + (f"  — {b.support.label}" if b.support.label else ""))
        for sid in scenes.get(b.id, []):
            status = (scene_status or {}).get(sid)
            lines.append(f"       Visual Plan scene {sid}" + (f": {status}" if status else ""))
        for f in b.findings:
            lines.append(f"       ! {f}")
    plan_level = [f for f in findings if not f.beat]
    if plan_level:
        lines.append("")
        lines += [f"! {f}" for f in plan_level]
    if report is not None:
        if report.critique.overall:
            o = report.critique.overall
            lines.append(f"\nCritic: {o.get('balance', '?')}, coherence {o.get('coherence', '?')}/5. {o.get('summary', '')}")
        if report.repair_passes:
            lines.append(f"Repaired {sum(len(x) for x in report.repaired)} weak beat(s) in {report.repair_passes} pass(es).")
        if report.stats.get("critic_skipped") and not report.stats.get("critic_calls"):
            lines.append("Critic: skipped, nothing in the plan looked creatively wrong.")
        if report.stats.get("local_fixes"):
            lines.append(f"Fixed locally without AI: {report.stats['local_fixes']} small thing(s).")
        if report.stats.get("ai_summary"):
            lines.append("\n" + report.stats["ai_summary"])
    ne, nw = len(errors(findings)), len(warnings(findings))
    lines.append(f"\n{ne} error(s), {nw} warning(s)." + ("  Errors must be fixed before rendering." if ne else ""))
    return "\n".join(lines)


def check_plan(plan: HybridPlan, *, report: Optional[PlanResult] = None, scene_status: Optional[Dict[str, str]] = None, engine: bool = True) -> "tuple[str, bool]":
    """Validate, then compile (the renderer's own rules and every place), and describe the plan. Returns (text, ok)."""
    findings = validate(plan)
    text = plan_text(plan, findings, scene_status=scene_status, report=report)
    ok = not errors(findings)
    if ok:
        try:
            res = compile_plan(plan, validate=engine)
            for n in res.notes:
                text += f"\nnote: {n}"
            for w in res.report.warnings:
                text += f"\nwarning: {w}"
        except HybridCompileError as exc:
            ok = False
            text += "\n\nThe plan does not compile:\n" + "\n".join(f"  ERROR: {p}" for p in exc.problems)
        except Exception as exc:  # never escape into the UI thread
            ok = False
            text += f"\n\nThe plan could not be compiled: {exc}"
    return text, ok
