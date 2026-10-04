"""The Hybrid critic: a second Gemini pass that judges a finished HybridPlan and returns STRUCTURED findings. It never rewrites the plan;
beats it marks "weak" go back to the Director for repair (hybrid.pipeline)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

from .director import DirectorError, _complete, load_prompt, parse_json
from .plan import HybridPlan
from .validate import Finding

CATEGORIES = ("mode", "motivation", "redundancy", "churn", "overlays", "pacing", "support", "transition", "accuracy")
SEVERITIES = ("weak", "note")


@dataclass
class CriticFinding:
    beat: str
    severity: str
    category: str
    issue: str
    suggestion: str = ""

    def to_dict(self) -> dict:
        return {"beat": self.beat, "severity": self.severity, "category": self.category, "issue": self.issue, "suggestion": self.suggestion}

    def __str__(self) -> str:
        return f"{self.category}: {self.issue}" + (f" ({self.suggestion})" if self.suggestion else "")


@dataclass
class Critique:
    findings: List[CriticFinding] = field(default_factory=list)
    overall: Dict[str, Any] = field(default_factory=dict)
    ran: bool = False

    def weak(self) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        for f in self.findings:
            if f.severity == "weak":
                out.setdefault(f.beat, []).append(str(f))
        return out

    def to_dict(self) -> dict:
        return {"overall": self.overall, "findings": [f.to_dict() for f in self.findings], "ran": self.ran}


def _layer_text(l) -> str:
    """Everything that defines a layer, so the critic never judges a layer it cannot see (a number chip is its value, not its label)."""
    if l.type == "stat":
        what = f"{l.value_from if l.value_from is not None else l.value_to:g} -> {l.value_to:g} '{l.format}' sub '{l.sub}'" if l.value_to is not None else "NO VALUE"
    elif l.type == "line":
        what = f"{l.kind} through {' > '.join(l.places)}"
    elif l.type == "caption":
        what = f"'{l.text}'"
    elif l.type == "hud_title":
        what = f"'{l.label}' / '{l.sub}'"
    else:
        what = f"{l.label or '(no label)'} at {l.place}" + (f" role {l.role}" if l.role else "")
    return f"{l.type} {what} @{l.t:.1f}s until {l.until}"


MODE_TAG = {"map": "MAP", "footage": "FOOTAGE", "map_footage": "MAP+CARD"}


def _clock(t: float) -> str:
    return f"{int(t // 60):02d}:{int(t % 60):02d}"


def plan_summary(plan: HybridPlan, findings: Sequence[Finding] = (), *, says: int = 220) -> str:
    """The plan as a critic needs it: ONE LINE per beat (time, mode, what it shows, what is drawn on it, a clip of what the narrator says,
    what the validator already noticed). The full renderer plan stays on disk; none of its technical fields help to judge storytelling."""
    by_beat: Dict[str, List[str]] = {}
    for f in findings:
        by_beat.setdefault(f.beat, []).append(f"{f.severity}: {f.message}")
    lines = [f"Video {plan.duration:.0f}s, {len(plan.beats)} beats. One line per beat: id | time (length) | mode | what it shows | details | the narrator says."]
    for b in plan.beats:
        if b.mode == "footage":
            shows = f"footage: {b.footage_intent or b.purpose}"
            detail = "clips: " + "; ".join(c.asset + (f" ({c.reason})" if c.reason else "") for c in b.clips)
        else:
            shows = f"map: {b.geo_intent or b.purpose} [camera {b.cam_place or '-'} {b.cam_frame} {b.cam_move}]".strip()
            parts = []
            if b.layers:
                parts.append("layers: " + "; ".join(_layer_text(l) for l in b.layers))
            if b.support:
                parts.append(f"card: {b.support.asset}" + (f" '{b.support.label}'" if b.support.label else ""))
            detail = " | ".join(parts) or "no layers"
        row = f"{b.id} | {_clock(b.start)} ({b.end - b.start:.0f}s) | {MODE_TAG.get(b.mode, b.mode)} | {shows} | {detail} | says: {b.narration[:says].strip()}"
        if by_beat.get(b.id):
            row += " | validator: " + " / ".join(by_beat[b.id])
        lines.append(row)
    if by_beat.get(""):
        lines.append("plan-level validator findings: " + " | ".join(by_beat[""]))
    return "\n".join(lines)


def parse_critique(payload: Any, valid_beats: Sequence[str]) -> Critique:
    if not isinstance(payload, dict):
        raise DirectorError("the critic's answer is not a JSON object")
    crit = Critique(overall=dict(payload.get("overall") or {}), ran=True)
    for raw in payload.get("findings") or []:
        if not isinstance(raw, dict) or str(raw.get("beat", "")) not in valid_beats:
            continue  # never act on a beat that does not exist
        sev = str(raw.get("severity", "note")).lower()
        cat = str(raw.get("category", "")).lower()
        crit.findings.append(CriticFinding(beat=str(raw["beat"]), severity=sev if sev in SEVERITIES else "note", category=cat if cat in CATEGORIES else "motivation",
                                           issue=str(raw.get("issue", "")).strip(), suggestion=str(raw.get("suggestion", "")).strip()))
    return crit


def _readable(raw: str, valid: Sequence[str]) -> bool:
    try:
        parse_critique(parse_json(raw), valid)
        return True
    except Exception:
        return False


def critique(llm: Any, plan: HybridPlan, findings: Sequence[Finding] = (), say: Any = None, *, label: str = "") -> Critique:
    valid = [b.id for b in plan.beats]
    raw = _complete(llm, load_prompt("hybrid_critic_prompt.txt"), plan_summary(plan, findings) + "\n\nReturn the JSON findings.", say,
                    task="critic", label=label or "plan", accept=lambda t: _readable(t, valid))
    return parse_critique(parse_json(raw), valid)
