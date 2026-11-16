"""What every style's Wall Moments adapter shares: turn the style's timeline (Shot / Layer lists of cinematic_explainer.render) into planner
input, run the planner, and swap the layers. A style gives only its own lists (aviation/wall_moments.py, cinematic_explainer/war/wall_moments.py).

    Style(card, keep, transient, theme, allow_strong=True, clip_extra=None)
        card       layer kinds (prefixes) that today are graphic cards: a wall moment replaces them
        keep       kinds that must stay as they are (maps, titles): no moment overlaps them
        transient  small marks (source tags, re-hooks, flashes): dropped inside a moment, never block one
        allow_strong   False: a moment never covers a scene's own real footage (it stays full screen in the style's own render)
        clip_extra(shot, at) -> dict   extra clip params for a wall print of this shot at film time `at` (a decode graph that matches the
                                       style's own look of the shot at the hand-off frame)
    planner_input(shots, layers, scenes, style) -> (wall scenes, wall shots, blocks)
    apply(shots, layers, scenes, words, style, *, pct, work, log) -> (layers, report)
        report = {"segments", "share", "spans", "cues": [(t, sound)], "plan"}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

LAYER = "wall.lay_wall"


@dataclass
class Style:
    card: Tuple[str, ...]
    keep: Tuple[str, ...]
    transient: Tuple[str, ...]
    theme: str = "slate"
    allow_strong: bool = True
    clip_extra: Optional[Callable[[Any, float], Dict[str, Any]]] = None
    name: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def _g(o: Any, k: str, d: Any = None) -> Any:
    return o.get(k, d) if isinstance(o, dict) else getattr(o, k, d)


def _kind_of_path(path: str) -> str:
    n = Path(str(path)).name.lower()
    if n.startswith("black") or "backdrop" in n or "plate" in n:
        return "black"
    # a picture made into a slow push-in clip: '<n>.still.mp4' (aviation.runner) or '<image>.war.mp4' (war.integration.still_to_clip)
    return "still" if (".still." in n or n.endswith(".war.mp4")) else "footage"


def _ov(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _is(kind: str, names: Tuple[str, ...]) -> bool:
    return any(kind == n or (n.endswith((".", "_")) and kind.startswith(n)) for n in names)


def planner_input(shots: Sequence[Any], layers: Sequence[Any], scenes: Sequence[Dict[str, Any]], style: Style):
    wshots = []
    for k, s in enumerate(shots):
        path = str(_g(s, "path", ""))
        wshots.append({"start": float(_g(s, "start")), "end": float(_g(s, "end")), "seek": float(_g(s, "seek", 0.0)), "path": path,
                       "kind": _g(s, "kind") or _kind_of_path(path), "_i": k})
    blocks = []
    for ly in layers:
        kind, a, b = str(_g(ly, "kind")), float(_g(ly, "start")), float(_g(ly, "end"))
        if _is(kind, style.transient) or b - a <= 1.0:
            continue
        blocks.append((a, b))
    wscenes = []
    for sc in scenes:
        a, b = float(sc["start"]), float(sc["end"])
        card = keep = 0.0
        for ly in layers:
            kind, la, lb = str(_g(ly, "kind")), float(_g(ly, "start")), float(_g(ly, "end"))
            o = _ov(a, b, la, lb)
            if o <= 0:
                continue
            if _is(kind, style.keep):
                keep += o
            elif _is(kind, style.card):
                card += o
        d = max(0.01, b - a)
        strong = sum(_ov(a, b, s["start"], s["end"]) for s in wshots if s["kind"] == "footage") / d
        wscenes.append({"no": sc.get("scene_no", sc.get("no")), "text": sc.get("text", ""), "start": a, "end": b,
                        "card": round(min(1.0, card / d), 3),
                        "keep": keep > 0.05 or (not style.allow_strong and strong > 0.5)})
    return wscenes, wshots, blocks


def apply(shots: Sequence[Any], layers: Sequence[Any], scenes: Sequence[Dict[str, Any]], words: Any, style: Style, *, pct: float = 20.0,
          work: Optional[str] = None, log: Callable[[str], None] = lambda m: None):
    from cinematic_explainer.render import Layer
    from . import planner as WP

    total = float(_g(shots[-1], "end")) if shots else 0.0
    wscenes, wshots, blocks = planner_input(shots, layers, scenes, style)
    if style.clip_extra is not None:
        for ws in wshots:
            ws["_shot"] = shots[ws["_i"]]
    pl = WP.plan(wscenes, words, total, wshots, pct=pct, blocks=blocks, theme=style.theme, work=work,
                 clip_extra=style.clip_extra)
    spans = [(s["start"], s["end"]) for s in pl["segments"]]
    out: List[Any] = []
    for ly in layers:
        a, b = float(_g(ly, "start")), float(_g(ly, "end"))
        hit = [(sa, sb) for sa, sb in spans if _ov(a, b, sa, sb) > 1e-6]
        if not hit:
            out.append(ly)
            continue
        sa, sb = hit[0]
        if a >= sa - 1e-6 and b <= sb + 1e-6:
            continue                                            # inside the moment: the wall replaces it
        if a < sa and b <= sb + 1e-6:
            if sa - a >= 0.4:                                   # ends inside: cut at the moment's start (its clock is unchanged)
                out.append(Layer(ly.kind, a, sa, ly.params, ly.dim))
            continue
        if a >= sa - 1e-6 and b > sb:
            continue                                            # starts inside (only short marks can: long layers block the planner)
        out.append(ly)                                          # spans the whole moment (film-long grain): the opaque wall covers it
    for s in pl["segments"]:
        out.append(Layer(LAYER, s["start"], s["end"], s["params"]))
    out.sort(key=lambda ly: (float(ly.start), float(ly.end)))
    cues = sorted(c for s in pl["segments"] for c in s.get("cues", []))
    rep = {"segments": [{k: s[k] for k in ("start", "end", "scenes", "closing")} for s in pl["segments"]], "share": pl["share"],
           "spans": spans, "cues": cues, "plan": pl}
    name = f"{style.name} " if style.name else ""
    if pl["segments"]:
        log(f"{name}wall moments: {len(spans)} moments, {pl['share']:.1f}% of the film (target {pct:g}%)")
    else:
        log(f"{name}wall moments: no stretch of this script suits the wall (no numbers, cards or twists to pin); the film is unchanged")
    return out, rep
