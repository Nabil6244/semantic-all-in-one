"""New 3D every time: the planned 3D phone shots of a film are varied after planning, so the same move never runs twice the same way.

- no move twice in a row and no move more than about 15 % of the film's phone shots: an over-used move is swapped for another
  that shows the same part of the phone (the back and camera, the front and screen, the frame and details);
- every shot gets its own camera variation (shot["vary"]: yaw / lift / dist / roll / fov, read by whatif-engine/lib/product.mjs)
  and a side (cam_side mirrors the move);
- the backdrop changes only where no dark text sits over the shot (dark ink needs the bright daylight set);
- the numbers come from a seed per film (the voice-over and script), so each new video gets different shots.
No AI call, no render time: only the plan changes."""
from __future__ import annotations

import hashlib
import math
import random
from typing import Any, Dict, List, Optional, Sequence

GROUPS = {   # moves that show the same part of the phone
    "back": ["island", "monolith", "hero_back", "orbit"],
    "front": ["screen", "hero", "flip", "rise", "reveal"],
    "body": ["edge", "buttons", "port", "profile"],
}
GROUP_OF = {m: g for g, ms in GROUPS.items() for m in ms}
TEXT_MOVES = {"hero", "monolith", "orbit", "flip", "rise", "hero_back"}   # the phone sits to one side: room for a title
MACRO = {"island", "screen", "edge", "port", "buttons"}
SHARE = 0.15            # the most any one move may take of the film's phone shots
RECENT = 2              # a move is not used again within this many phone shots
BRIGHT = "daylight"
OTHER_SETS = ["daylight", "daylight", "daylight", "wash", "charcoal"]   # mostly bright, as the review references
WASHES = ["#6d8bff", "#ff8a5c", "#3ec7b0", "#b07cff", "#ffc04d"]


def film_seed(*parts: Any) -> int:
    """A stable number per film: the same inputs give the same film, a new voice-over or script a new one."""
    h = hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8", "replace")).hexdigest()
    return int(h[:8], 16)


def _phone_shots(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [s for s in spec.get("shots", []) if s.get("kind") == "product" and s.get("object") == "phone" and s.get("move") in GROUP_OF]


def _dark_text_over(spec: Dict[str, Any], shot: Dict[str, Any]) -> bool:
    a, b = float(shot.get("start", 0)), float(shot.get("end", 0))
    return any(L.get("ink") == "dark" and float(L.get("start", 0)) < b and float(L.get("end", 0)) > a for L in spec.get("layers", []))


def _pick_move(move: str, used: Dict[str, int], recent: Sequence[str], cap: int, rng: random.Random) -> str:
    if move not in recent and used.get(move, 0) < cap:
        return move
    pool = [m for m in GROUPS[GROUP_OF[move]] if m != move]
    if move in TEXT_MOVES:                                   # a title may sit beside the phone: keep a move that leaves it room
        pool = [m for m in pool if m in TEXT_MOVES] or pool
    fresh = [m for m in pool if m not in recent and used.get(m, 0) < cap]
    if not fresh:
        fresh = [m for m in pool if m not in recent] or [move]
    low = min(used.get(m, 0) for m in fresh)
    return rng.choice([m for m in fresh if used.get(m, 0) == low])


def _vary(move: str, rng: random.Random) -> Dict[str, float]:
    u = lambda a, b: round(rng.uniform(a, b), 3)
    if move in MACRO:      # a macro is close: small turns only, or the subject slides out of the frame
        return {"yaw": u(-0.18, 0.18), "lift": u(-0.08, 0.08), "dist": u(0.93, 1.08), "roll": u(-0.04, 0.04), "fov": u(-2, 2)}
    if move in ("flip", "rise", "reveal"):   # these end on a pose the shot needs: a gentler change
        return {"yaw": u(-0.25, 0.25), "lift": u(-0.2, 0.25), "dist": u(0.92, 1.12), "roll": u(-0.03, 0.03), "fov": u(-2, 2)}
    return {"yaw": u(-0.4, 0.4), "lift": u(-0.3, 0.35), "dist": u(0.88, 1.18), "roll": u(-0.05, 0.05), "fov": u(-3, 3)}


def vary_shots(spec: Dict[str, Any], seed: int) -> Dict[str, Any]:
    """Vary the film's 3D phone shots in place (and return the spec). Author directives keep their move (shot["_own"])."""
    rng = random.Random(seed)
    shots = _phone_shots(spec)
    if not shots:
        return spec
    cap = max(1, math.ceil(len(shots) * SHARE))
    used: Dict[str, int] = {}
    recent: List[str] = []
    prev_set = None
    for s in shots:
        move = s["move"] if s.get("_own") else _pick_move(s["move"], used, recent, cap, rng)
        s["move"] = move
        used[move] = used.get(move, 0) + 1
        recent = (recent + [move])[-RECENT:]
        s["vary"] = _vary(move, rng) if not s.get("_hero") else {"yaw": round(rng.uniform(-0.15, 0.15), 3), "lift": 0.0, "dist": round(rng.uniform(1.02, 1.12), 3), "roll": 0.0, "fov": 0.0}   # a hero render keeps the whole phone in frame
        s["cam_side"] = rng.choice(["left", "right"])
        if not s.get("_hero"):
            s["seed"] = rng.randrange(1, 10_000)
        if s.get("backdrop") == BRIGHT and not _dark_text_over(spec, s):
            pick = rng.choice([b for b in OTHER_SETS if b != prev_set] or OTHER_SETS)
            s["backdrop"] = pick
            if pick == "wash":
                s["wash"] = rng.choice(WASHES)
        prev_set = s.get("backdrop")
    return spec


def fingerprint(shot: Dict[str, Any]) -> tuple:
    """What a viewer sees as 'the same shot': the move, the set, the side and the camera turn in coarse steps."""
    v = shot.get("vary") or {}
    return (shot.get("move"), shot.get("backdrop"), shot.get("cam_side"), round(float(v.get("yaw", 0)) / 0.1), round(float(v.get("lift", 0)) / 0.1))
