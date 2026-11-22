"""Food Files adapter for Wall Moments (docs/wall/PLAN.md): about 10 % of the film moves onto the dark evidence wall used by War and
Aviation (counters, stamps, notes, red string on the narrator's word times), where the script is dense with numbers and twists.

    plan(spec, words, pct=10, log=print) -> report      adds spec["wall"] = [{start, end, params}] and the wall's sound cues to spec["sfx"]
    frame_at(spec, t) -> PIL RGB or None                the wall frame at film time t (None outside a moment)

Never on: the opening title, the #N item cards and "next up" teasers, the paid Flow talking clips, the last line.
The pictures around a moment become its entry and exit prints (the wall pulls out of one and dives into the next).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

THEME = "war"                       # the dark evidence wall (Food Files' own look is dark maroon cards)
PCT = 10.0
KEEP_KINDS = ("title", "number", "next")
CARD_KINDS = ("big", "explain", "compare", "symptoms", "tally", "timeline", "map", "folder", "flow", "states", "page",
              "headline", "quote", "tweet", "evidence", "scale", "beforeafter", "scene2d")
SOUND_DB = -19.0


def _scenes(spec) -> List[Dict[str, Any]]:
    rows = spec.get("rows") or []
    by_row: Dict[int, List[Dict[str, Any]]] = {}
    for s in spec["shots"]:
        if s.get("row") is not None:
            by_row.setdefault(s["row"], []).append(s)
    out = []
    last_row = max(by_row) if by_row else -1
    for r, shots in sorted(by_row.items()):
        a, b = min(s["t0"] for s in shots), max(s["t1"] for s in shots)
        d = max(0.01, b - a)
        card = sum(s["t1"] - s["t0"] for s in shots if s["kind"] in CARD_KINDS) / d
        keep = (r == last_row or any(s["kind"] in KEEP_KINDS or s.get("talk") for s in shots))
        out.append({"no": r, "text": (rows[r].get("line") if r < len(rows) else "") or "", "start": a, "end": b,
                    "card": round(min(1.0, card), 3), "keep": keep})
    return out


def _shots(spec) -> List[Dict[str, Any]]:
    pics = (spec.get("assets") or {}).get("pictures") or {}
    out = []
    for s in spec["shots"]:
        path, kind = "", "black"
        # never a print of the host on the wall: a frozen frame of him looks fake (owner, 2026-11-23); his clips stay full screen
        if s["kind"] in ("host", "split", "pip") or s.get("talk"):
            path, kind = "", "black"
        elif s.get("pic") and pics.get(s["pic"]) and not (spec.get("pictures", {}).get(s["pic"]) or {}).get("host"):
            path, kind = str(pics[s["pic"]]), "still"
        out.append({"start": float(s["t0"]), "end": float(s["t1"]), "seek": float(s.get("talk_at") or 0.0), "path": path, "kind": kind})
    return out


def plan(spec, words, pct: float = PCT, log: Callable[[str], None] = print, work: Optional[str] = None) -> Dict[str, Any]:
    from wall import planner as WP
    from wall import sfx as WS
    spec.pop("wall", None)
    spec["sfx"] = [e for e in spec.get("sfx", []) if not str(e.get("name", "")).startswith("wall:")]
    if pct <= 0 or not spec.get("shots"):
        return {"segments": [], "share": 0.0}
    total = float(spec["duration"])
    pl = WP.plan(_scenes(spec), words, total, _shots(spec), pct=pct, theme=THEME, work=work)
    segs = [{"start": round(s["start"], 3), "end": round(s["end"], 3), "params": s["params"]} for s in pl["segments"]]
    spec["wall"] = segs
    for s in pl["segments"]:
        for t, cue in s.get("cues", []):
            spec["sfx"].append({"t": round(float(t), 3), "name": f"wall:{WS.base(cue)}"})
    spec["sfx"].sort(key=lambda e: e["t"])
    if segs:
        log(f"food files: wall moments: {len(segs)} moment(s), {pl['share']:.1f}% of the film (target {pct:g}%) at "
            + ", ".join(f"{s['start'] / 60:.1f}" for s in segs) + " min")
    else:
        log("food files: wall moments: no stretch suits the wall (no numbers or twists to pin); the film is unchanged")
    return {"segments": segs, "share": pl["share"]}


def frame_at(spec, t: float):
    for s in spec.get("wall") or ():
        if s["start"] <= t < s["end"]:
            from wall import engine as WE
            im = WE.lay_wall(t - s["start"], s["end"] - s["start"], s["params"])
            if im is None:
                return None
            return im.convert("RGB")
    return None


def sound_table(spec) -> Dict[str, tuple]:
    """{cue name: (absolute sound file, dB)} for the wall cues in spec["sfx"] (the mixer joins an absolute path as it is)."""
    from wall import sfx as WS
    names = {e["name"] for e in spec.get("sfx", []) if str(e.get("name", "")).startswith("wall:")}
    if not names:
        return {}
    WS.ensure()
    return {n: (str(WS.file_for(n.split(":", 1)[1])), SOUND_DB) for n in names}
