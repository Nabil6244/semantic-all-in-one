"""Paper-cutout puppets: a small cast of rigged characters and reusable action clips (walk, run, idle, pick_up ...).

    list_characters() -> names;  list_actions() -> names;  action_duration(action, params)
    render_character_frame(character, action, t, scale, facing='right', ground_phase=None, params=None) -> (RGBA image, (anchor_x, anchor_y))

anchor = the point on the ground under the pelvis inside the returned image; place it at the character's world position.
For walk/run, ground_phase is the gait phase in cycles; or give params['distance'] (world px walked) and the phase follows the background scroll
(stride_length() tells how far one cycle travels). turn flips the facing over its duration (use the opposite facing afterwards).
params: prop ('briefcase' | 'box' | 'parcel' | 'phone' | None; defaults to the character's own prop in walk/run/idle), duration, step_scale, period, box_x, angle.
"""
from __future__ import annotations
import math
from typing import Optional, Tuple
from PIL import Image

from . import actions as _act
from . import cast as _cast

_DEFAULT_PROP_ACTIONS = {"walk", "run", "stand_idle", "stop", "look_around", "turn"}


def list_characters() -> list: return _cast.list_names()
def list_actions() -> list: return _act.names()


def action_duration(action: str, params: Optional[dict] = None) -> float:
    return _act.get(action).duration(params)


def stride_length(character: str, action: str = "walk", scale: float = 1.0, params: Optional[dict] = None) -> float:
    """World pixels one gait cycle covers at this scale (feet stay planted while the background moves by this per cycle)."""
    s = _act.get(action).stride(_cast.get_rig(character).d, params)
    return (s or 0.0) * scale


def action_travel(character: str, action: str, t: float, scale: float, params: Optional[dict] = None) -> float:
    """World pixels the figure itself moves by time t. Only `stop` moves on its own (a decelerating walk); the others are driven by the caller."""
    if action != "stop": return 0.0
    return _act.stop_travel(t, params or {}, _cast.get_rig(character).d) * scale


def render_character_frame(character: str, action: str, t: float, scale: float, facing: str = "right", ground_phase: Optional[float] = None,
                           params: Optional[dict] = None, tint=None) -> Tuple[Image.Image, Tuple[float, float]]:
    rig = _cast.get_rig(character); act = _act.get(action); p = dict(params or {})
    if "prop" not in p and action in _DEFAULT_PROP_ACTIONS and rig.spec.get("prop"): p["prop"] = rig.spec["prop"]
    phase = ground_phase
    if phase is None and act.cyclic and p.get("distance") is not None: phase = float(p["distance"]) / (act.stride(rig.d, p) * scale)
    t = max(0.0, float(t))
    pose = act.pose_at(t, p, rig.d, phase)
    # secondary motion: coat / scarf trail the body, sampled a moment earlier
    lag = 0.14
    lp = act.pose_at(max(0.0, t - lag), p, rig.d, None if phase is None else phase - lag / (p.get("period") or act.period or 1.0))
    sp = pose.get("speed", 0.0); tt = phase * (act.period or 1.0) if phase is not None else t
    pose["coat"] = -sp * 9 - 0.28 * lp.get("thb", 0) + 0.12 * lp.get("tha", 0) + 1.5 * math.sin(tt * 1.9)
    pose["scarf"] = -sp * 24 - 0.8 * lp.get("head", 0) + 0.4 * (lp.get("lean", 0) - pose.get("lean", 0)) + (4 + 4 * sp) * math.sin(tt * 5.1)
    return rig.draw(pose, scale, facing, tint)


def render_shot(*a, **k):
    from .render import render_shot as f
    return f(*a, **k)


def render_transition(*a, **k):
    from .render import render_transition as f
    return f(*a, **k)


def list_transitions():
    from .transitions import list_transitions as f
    return f()


try:
    from .render import VERSION
except Exception:
    VERSION = "1"
