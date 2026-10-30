"""Scenes drawn in code from the narration itself: a line figure doing the exercise the beat names (push-up variants, pull-up, squat, plank), or standing in the setting it names (gym). Nothing is stored or
generated: every scene is computed from a small spec {move, variant, setting, highlight} that the beat planner reads out of the words, so a new script gets its own scenes with no new art.
Side-view figures are solved with two-bone IK from fixed contact points (hands on the wall / bench / floor, feet or knees on the floor), so the body stays connected while it moves."""
from __future__ import annotations
import math
from typing import Dict, Optional, Tuple

from PIL import Image, ImageDraw

from . import theme as T

Pt = Tuple[float, float]
LIMB, DIM = (236, 236, 236), (92, 92, 98)

# body proportions in units of L (L = 11% of the frame height)
THIGH, SHIN, TORSO, UARM, FARM, HEAD = 1.1, 1.1, 1.5, 0.95, 0.9, 0.38

def _ik(a: Pt, b: Pt, l1: float, l2: float, sign: int) -> Pt:
    """Middle joint of a two-bone chain from a to b (clamped to reachable); sign picks which way it bends."""
    dx, dy = b[0] - a[0], b[1] - a[1]; d = min(max(math.hypot(dx, dy), abs(l1 - l2) + 1e-3), l1 + l2 - 1e-3); base = math.atan2(dy, dx)
    ang = math.acos(max(-1.0, min(1.0, (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d)))); return (a[0] + l1 * math.cos(base + sign * ang), a[1] + l1 * math.sin(base + sign * ang))

def _lerp(a: Pt, b: Pt, k: float) -> Pt: return (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)
def _wave(t: float, period: float = 2.6) -> float: return 0.5 - 0.5 * math.cos(2 * math.pi * t / period)      # 0 at the top of the movement, 1 at the bottom, then back

class Pen:
    def __init__(self, cv: Image.Image, ctx, L: float, hi: set):
        self.d = ImageDraw.Draw(cv, "RGBA"); self.ctx = ctx; self.L = L; self.w = max(3, int(L * 0.19)); self.hi = hi
    def limb(self, pts, part: str = "", dim: bool = False):
        col = T.ORANGE if part in self.hi else (DIM if dim else LIMB); w = self.w
        for a, b in zip(pts, pts[1:]): self.d.line([a, b], fill=col + (255,), width=w)
        for p in pts: self.d.ellipse((p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2), fill=col + (255,))
    def head(self, c: Pt):
        r = self.L * HEAD; self.d.ellipse((c[0] - r, c[1] - r, c[0] + r, c[1] + r), outline=LIMB + (255,), width=max(3, int(self.L * 0.12)), fill=(14, 14, 16, 255))
    def line(self, a: Pt, b: Pt, w: float = 0.07, col=(120, 120, 128), alpha: int = 255): self.d.line([a, b], fill=col + (alpha,), width=max(2, int(self.L * w)))
    def box(self, x0, y0, x1, y1, col=(60, 60, 66)): self.d.rectangle((x0, y0, x1, y1), fill=col + (255,), outline=(140, 140, 148, 255), width=max(2, int(self.L * 0.05)))

def _frame_box(ctx) -> Tuple[float, float, float, float]: return (ctx.W * 0.05, ctx.H * 0.10, ctx.W * 0.58, ctx.H * 0.80)

def _pushup(p: Pen, spec: dict, t: float, box) -> None:
    L = p.L; var = spec.get("variant", "full"); gy = box[3] - L * 0.2; ph = _wave(t); right = box[2] - L * 1.2
    knee = var == "knee"; Lb = (THIGH + TORSO) * L if knee else (THIGH + SHIN + TORSO) * L; reach = (UARM + FARM - 0.1) * L
    if var == "wall": H = (right, gy - L * 2.7); Stop = (H[0] - reach, H[1]); support = "wall"
    elif var == "incline": hb = L * 1.7; H = (right, gy - hb); Stop = (H[0] - reach * 0.55, H[1] - reach * 0.83); support = "bench"
    else: H = (right, gy); Stop = (H[0], H[1] - reach); support = "floor"
    Fy = gy; Fx = Stop[0] - math.sqrt(max(1.0, Lb * Lb - (Fy - Stop[1]) ** 2)); F = (Fx, Fy)
    a_top = math.atan2(F[1] - Stop[1], Stop[0] - F[0]); a = a_top - (0.20 if var == "wall" else 0.30) * ph; S = (F[0] + Lb * math.cos(a), F[1] - Lb * math.sin(a))
    p.line((box[0], gy + L * 0.12), (box[2], gy + L * 0.12), 0.05)
    if support == "wall": p.box(H[0] + L * 0.1, gy - L * 5.2, H[0] + L * 0.45, gy + L * 0.12)
    elif support == "bench": p.box(H[0] - L * 0.9, gy - L * 1.7, H[0] + L * 0.5, gy + L * 0.1)
    body = [F, _lerp(F, S, (Lb - TORSO * L) / Lb), S]; legs_hi = "legs"
    if knee: foot = (F[0] - L * 0.85, F[1] - L * 0.55); p.limb([foot, F], "legs", dim=True)
    p.limb(body[:2], "legs"); p.limb(body[1:], "torso")
    el = _ik(S, H, UARM * L, FARM * L, 1); p.limb([S, el, H], "arms")
    if var == "onearm": pass
    d = (S[0] - body[1][0], S[1] - body[1][1]); n = math.hypot(*d) or 1; p.head((S[0] + d[0] / n * L * 0.55, S[1] + d[1] / n * L * 0.55 - L * 0.1))

def _plank(p: Pen, spec: dict, t: float, box) -> None:
    L = p.L; gy = box[3] - L * 0.2; knee = spec.get("variant") == "knee"; sway = 0.04 * L * math.sin(t * 2.1); ex = box[0] + L * 3.3; hand = (ex + L * 0.95, gy); elb = (ex, gy)
    S = (ex - L * 0.05, gy - UARM * L * 0.98); Lb = (THIGH + SHIN + TORSO) * L if not knee else (THIGH + TORSO) * L
    Fx = S[0] - math.sqrt(max(1.0, Lb * Lb - (gy - S[1] - sway) ** 2)); F = (Fx, gy); hip = _lerp(F, (S[0], S[1]), (Lb - TORSO * L) / Lb); hip = (hip[0], hip[1] - sway * 2)
    p.line((box[0], gy + L * 0.12), (box[2], gy + L * 0.12), 0.05)
    if knee: p.limb([(F[0] - L * 0.9, F[1] - L * 0.6), F], "legs", dim=True)
    p.limb([F, hip], "legs"); p.limb([hip, S], "torso"); p.limb([S, elb, hand], "arms"); p.limb([S, (ex, gy)], "arms")
    d = (S[0] - hip[0], S[1] - hip[1]); n = math.hypot(*d) or 1; p.head((S[0] + d[0] / n * L * 0.6, S[1] + d[1] / n * L * 0.6 - L * 0.1))

def _squat(p: Pen, spec: dict, t: float, box) -> None:
    L = p.L; gy = box[3] - L * 0.2; ph = _wave(t, 2.8); fx = box[0] + L * 3.4; foot = (fx, gy); toe = (fx + L * 0.55, gy)
    h = (THIGH + SHIN) * L * (0.97 - 0.42 * ph); hip = (fx - L * (0.35 + 1.35 * ph), gy - h); knee = _ik(foot, hip, SHIN * L, THIGH * L, -1)
    lean = 0.12 + 0.55 * ph; S = (hip[0] + math.sin(lean) * TORSO * L, hip[1] - math.cos(lean) * TORSO * L); hand = (S[0] + L * 1.55, S[1] + L * 0.1 + 0.1 * L * ph)
    p.line((box[0], gy + L * 0.12), (box[2], gy + L * 0.12), 0.05); p.limb([toe, foot], "legs"); p.limb([foot, knee, hip], "legs"); p.limb([hip, S], "torso"); p.limb([S, _lerp(S, hand, 0.5), hand], "arms")
    p.head((S[0] + math.sin(lean) * L * 0.5, S[1] - math.cos(lean) * L * 0.5 - L * 0.05))

def _pullup(p: Pen, spec: dict, t: float, box) -> None:
    L = p.L; cx = (box[0] + box[2]) / 2; yb = box[1] + L * 0.9; ph = _wave(t, 3.0); e = (UARM + FARM) * L * (0.98 - 0.52 * ph); ys = yb + e; gap = L * 0.62
    p.line((cx - L * 2.2, yb), (cx + L * 2.2, yb), 0.14, LIMB)
    for s in (-1, 1):
        sh = (cx + s * L * 0.42, ys); hand = (cx + s * gap, yb); el = _ik(sh, hand, UARM * L, FARM * L, 1 if s > 0 else -1); p.limb([sh, el, hand], "arms")
    hip = (cx, ys + TORSO * L); p.limb([(cx - L * 0.42, ys), (cx + L * 0.42, ys)], "torso"); p.limb([(cx, ys), hip], "torso")
    for s in (-1, 1): p.limb([hip, (cx + s * L * 0.22, hip[1] + THIGH * L), (cx + s * L * 0.1, hip[1] + (THIGH + SHIN) * L)], "legs")
    p.head((cx, ys - L * 0.62 + 0.0 * L))
    gy = hip[1] + (THIGH + SHIN) * L + L * 0.9; p.line((box[0], min(gy, box[3])), (box[2], min(gy, box[3])), 0.04, DIM)

def _stand(p: Pen, cx: float, gy: float, t: float, walk: float = 0.0) -> None:
    L = p.L; bob = 0.05 * L * math.sin(t * 5.0) * (1 if walk else 0); hip = (cx, gy - (THIGH + SHIN) * L + bob); S = (cx, hip[1] - TORSO * L); sw = math.sin(t * 5.0) * 0.35 * walk
    for s in (-1, 1): p.limb([hip, (cx + s * L * 0.18 + sw * s * L * 0.4, hip[1] + THIGH * L), (cx + s * L * 0.16 + sw * s * L * 0.7, gy)], "legs")
    p.limb([hip, S], "torso"); p.limb([(cx - L * 0.45, S[1] + L * 0.08), (cx + L * 0.45, S[1] + L * 0.08)], "torso")
    for s in (-1, 1): p.limb([(cx + s * L * 0.45, S[1] + L * 0.08), (cx + s * L * (0.62 - sw * s * 0.3), S[1] + L * 0.8), (cx + s * L * (0.6 + sw * s * 0.4), S[1] + L * 1.6)], "arms")
    p.head((cx, S[1] - L * 0.62))

def _gym(p: Pen, spec: dict, t: float, box) -> None:
    L = p.L; gy = box[3] - L * 0.2; p.line((box[0], gy + L * 0.12), (box[2], gy + L * 0.12), 0.05)
    rx = box[2] - L * 3.3; top = gy - L * 4.0
    for x in (rx - L * 1.1, rx + L * 1.1): p.box(x - L * 0.12, top, x + L * 0.12, gy + L * 0.1)
    p.line((rx - L * 1.9, top + L * 0.6), (rx + L * 1.9, top + L * 0.6), 0.12, LIMB)
    for x in (rx - L * 1.75, rx + L * 1.75, rx - L * 1.45, rx + L * 1.45): p.box(x - L * 0.12, top + L * 0.1, x + L * 0.12, top + L * 1.1, (70, 70, 78))
    for i, dx in enumerate((-L * 2.4, -L * 2.0)): p.box(box[0] + L * 0.5 + i * L * 0.55, gy - L * 0.5 - i * L * 0.3, box[0] + L * 0.95 + i * L * 0.55, gy + L * 0.1, (70, 70, 78))      # a rack of plates
    walk = min(1.0, t / 1.6); x = box[0] + L * 2.3 + (rx - L * 4.6 - box[0]) * (1 - (1 - walk) ** 2); _stand(p, x, gy, t, walk=0.0 if walk >= 1 else 1.0)

MOVES = {"pushup": _pushup, "plank": _plank, "squat": _squat, "pullup": _pullup, "gym": _gym, "stand": lambda p, spec, t, box: _stand(p, (box[0] + box[2]) / 2, box[3] - p.L * 0.2, t)}

def draw(cv: Image.Image, ctx, spec: dict, t: float) -> None:
    """Draws the spec's scene into the left ~55% of the frame at time t (seconds from the scene's start)."""
    box = _frame_box(ctx); L = ctx.H * 0.125; hi = set(spec.get("highlight", ())); p = Pen(cv, ctx, L, hi); fn = MOVES.get(spec.get("move", "stand"), MOVES["stand"]); fn(p, spec, max(0.0, t), box)

def label(spec: dict) -> str:
    v = {"wall": "WALL", "incline": "INCLINE", "knee": "KNEE", "onearm": "ONE-ARM", "full": "FULL"}.get(spec.get("variant", ""), "")
    m = {"pushup": "PUSH-UPS", "pullup": "PULL-UPS", "squat": "SQUATS", "plank": "PLANK", "gym": "GYM"}.get(spec.get("move", ""), "")
    return (v + " " + m).strip() if m else ""
