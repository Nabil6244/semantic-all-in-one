"""Vector puppet animals, built the way the reference channel builds theirs (docs/ocean/PATTERNS.md section 9): flat
shapes with one soft gradient, separate jointed legs (thigh + shin, a bend at the knee / hock, a paw), far legs one
darker solid colour behind the body, a tail made of segments that sways in a wave, a head that nods. One four-legged
template with settings makes every land animal; each frame is drawn fresh, so the legs really walk.

    p = Puppet("lion", width=560)
    img = p.pose(phase, "walk")          # RGBA, facing right; p.feet = the ground line on that image

Gaits: walk (four-beat: hind near, front near, hind far, front far), run (a bound: the hind pair then the front pair),
idle (standing: breathing, tail sway, a slow head turn).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter

SS = 2                      # supersampling: shapes are drawn twice as big, then smoothed down
Pt = Tuple[float, float]
RGB = Tuple[int, int, int]


@dataclass(frozen=True)
class Spec:
    # body (units: hip joint to shoulder joint = 1.0)
    body_h: float = 0.52            # torso depth
    rump: float = 0.2               # torso behind the hip
    chest: float = 0.2              # torso in front of the shoulder
    belly_tuck: float = 0.12        # waist tuck near the hips (cats, dogs)
    hump: float = 0.0               # shoulder hump (buffalo, wildebeest, hyena)
    back_slope: float = 0.0         # back higher at the shoulders (+) e.g. hyena, giraffe
    # legs
    thigh: float = 0.25
    shin: float = 0.25
    leg_w: float = 0.18             # width at the top of the leg
    paw: float = 0.085
    # neck + head
    neck_len: float = 0.06
    neck_up: float = 0.02           # how high the head is carried
    neck_w: float = 0.36
    head_r: float = 0.23
    snout: float = 0.1              # snout length beyond the head circle
    snout_h: float = 0.55           # snout height as a share of the head
    ears: str = "round"             # round | point | long | none
    # tail
    tail_len: float = 0.7
    tail_w: float = 0.05
    tail_up: float = 0.35           # how much the tail rises (0 droops, 1 up)
    tail_tuft: bool = False
    tail_bands: bool = False
    # colours
    coat: RGB = (196, 148, 84)
    coat_top: Optional[RGB] = None  # gradient top (darker back); None = coat darkened
    belly: RGB = (232, 206, 160)
    far: Optional[RGB] = None       # far legs; None = coat darkened
    paw_col: Optional[RGB] = None
    nose: RGB = (60, 40, 34)
    eye: RGB = (230, 190, 60)
    # markings
    mane: Optional[RGB] = None
    stripes: Optional[RGB] = None
    spots: Optional[RGB] = None
    spot_r: float = 0.017           # spot size (giraffe patches are big)
    cape: Optional[RGB] = None      # a light band over the whole top (honey badger)
    horns: Optional[RGB] = None
    face_patch: Optional[RGB] = None   # light cheeks / muzzle
    leg_dark: Optional[RGB] = None  # lower legs a different colour (wildebeest socks, badger)


def _dk(c: RGB, k: float) -> RGB:
    return tuple(max(0, min(255, int(v * k))) for v in c)  # type: ignore[return-value]


SPECS: Dict[str, Spec] = {
    "lion": Spec(mane=(120, 74, 34), tail_tuft=True, tail_up=0.15, face_patch=(236, 214, 170), coat=(200, 150, 86),
                 head_r=0.21, ears="round"),
    "lioness": Spec(coat=(206, 166, 108), tail_tuft=True, tail_up=0.15, face_patch=(238, 222, 186), head_r=0.19,
                    body_h=0.46, belly=(236, 214, 176)),
    "tiger": Spec(coat=(224, 120, 40), belly=(246, 232, 214), stripes=(32, 24, 22), tail_bands=True,
                  face_patch=(246, 238, 226), head_r=0.24, body_h=0.56, tail_up=0.45),
    "leopard": Spec(coat=(214, 170, 90), belly=(240, 226, 196), spots=(54, 40, 30), body_h=0.44, leg_w=0.14,
                    tail_len=0.85, tail_up=0.45, face_patch=(240, 228, 204), head_r=0.17),
    "cheetah": Spec(coat=(220, 180, 104), belly=(242, 230, 204), spots=(40, 32, 26), body_h=0.32, thigh=0.42, shin=0.42,
                    leg_w=0.1, tail_len=0.8, head_r=0.12, belly_tuck=0.3),
    "hyena": Spec(coat=(176, 150, 110), belly=(206, 188, 150), spots=(70, 56, 44), hump=0.08, back_slope=0.1,
                  thigh=0.32, shin=0.34, ears="round", head_r=0.16, snout=0.16, tail_len=0.4, tail_up=0.1,
                  leg_dark=(120, 100, 76)),
    "honey_badger": Spec(coat=(34, 32, 32), coat_top=(40, 38, 38), belly=(22, 22, 22), far=(18, 18, 18),
                         cape=(196, 196, 188), body_h=0.44, rump=0.26, chest=0.22, belly_tuck=0.0, thigh=0.19, shin=0.19,
                         leg_w=0.15, paw=0.09, neck_len=0.08, neck_up=0.0, head_r=0.15, snout=0.12, ears="none",
                         tail_len=0.34, tail_w=0.07, tail_up=0.2, eye=(30, 30, 30), nose=(16, 16, 16),
                         paw_col=(28, 28, 28)),
    "cape_buffalo": Spec(coat=(60, 56, 56), belly=(78, 74, 72), far=(36, 34, 34), body_h=0.56, rump=0.2, chest=0.3,
                         belly_tuck=0.0, hump=0.06, thigh=0.3, shin=0.3, leg_w=0.15, paw=0.06, neck_len=0.1,
                         neck_up=-0.05, neck_w=0.34, head_r=0.17, snout=0.14, snout_h=0.7, ears="long",
                         horns=(150, 140, 128), tail_len=0.5, tail_up=0.0, tail_tuft=True, eye=(30, 30, 30),
                         nose=(30, 28, 28), paw_col=(30, 28, 28)),
    "wildebeest": Spec(coat=(110, 104, 100), belly=(128, 122, 118), mane=(40, 38, 36), hump=0.07, back_slope=0.08,
                       body_h=0.46, belly_tuck=0.05, thigh=0.36, shin=0.38, leg_w=0.12, neck_len=0.14,
                       neck_up=0.04, head_r=0.15, snout=0.18, snout_h=0.7, horns=(70, 66, 62), tail_tuft=True,
                       tail_up=0.0, leg_dark=(70, 66, 64), eye=(30, 30, 30), paw_col=(40, 38, 36)),
    "zebra": Spec(coat=(238, 236, 230), belly=(246, 244, 238), stripes=(30, 30, 32), far=(150, 150, 150), body_h=0.46,
                  belly_tuck=0.06, thigh=0.36, shin=0.38, leg_w=0.12, neck_len=0.2, neck_up=0.2, neck_w=0.24,
                  head_r=0.13, snout=0.2, snout_h=0.7, ears="long", mane=(40, 40, 40), tail_tuft=True,
                  tail_up=0.0, eye=(30, 30, 30), paw_col=(40, 40, 40)),
    "giraffe": Spec(coat=(222, 182, 112), belly=(236, 214, 170), spots=(146, 88, 40), spot_r=0.055, body_h=0.5,
                    back_slope=0.18, thigh=0.5, shin=0.55, leg_w=0.13, paw=0.06, neck_len=0.3, neck_up=1.05,
                    neck_w=0.22, head_r=0.12, snout=0.14, snout_h=0.75, ears="long", horns=(120, 90, 60),
                    tail_len=0.5, tail_up=0.0, tail_tuft=True, mane=(150, 96, 50), eye=(30, 30, 30),
                    paw_col=(70, 50, 36), belly_tuck=0.05),
    "dog": Spec(coat=(150, 110, 70), belly=(200, 170, 130), body_h=0.38, thigh=0.32, shin=0.32, ears="point",
                head_r=0.15, snout=0.15, tail_len=0.5, tail_up=0.6),
    "wolf": Spec(coat=(128, 124, 120), belly=(200, 196, 190), body_h=0.4, thigh=0.34, shin=0.36, ears="point",
                 head_r=0.15, snout=0.17, tail_len=0.6, tail_up=0.1, tail_w=0.08),
    "hiker": Spec(),  # not a four-legged animal: falls back to the library picture
}
ALIASES = {"jackal": "dog", "wild_dog": "dog", "african_wild_dog": "hyena", "jaguar": "leopard", "panther": "leopard",
           "black_panther": "leopard", "bull": "cape_buffalo", "buffalo": "cape_buffalo", "gnu": "wildebeest"}
QUADRUPEDS = {k for k in SPECS if k != "hiker"}


def has(name: str) -> bool:
    return ALIASES.get(name, name) in QUADRUPEDS


# ------------------------------------------------------------------------------------------------------------- geometry

def _rot(p: Pt, a: float, c: Pt = (0.0, 0.0)) -> Pt:
    s, co = math.sin(a), math.cos(a)
    x, y = p[0] - c[0], p[1] - c[1]
    return (c[0] + x * co - y * s, c[1] + x * s + y * co)


def _seg(p0: Pt, ang: float, ln: float) -> Pt:
    """The end of a segment from p0 pointing `ang` radians from straight down (positive = forward / right)."""
    return (p0[0] + math.sin(ang) * ln, p0[1] + math.cos(ang) * ln)


def _quad(p0: Pt, p1: Pt, w0: float, w1: float) -> List[Pt]:
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    n = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / n, dx / n
    return [(p0[0] + nx * w0 / 2, p0[1] + ny * w0 / 2), (p1[0] + nx * w1 / 2, p1[1] + ny * w1 / 2),
            (p1[0] - nx * w1 / 2, p1[1] - ny * w1 / 2), (p0[0] - nx * w0 / 2, p0[1] - ny * w0 / 2)]


def _ellipse(c: Pt, rx: float, ry: float, n: int = 28, rot: float = 0.0) -> List[Pt]:
    return [_rot((c[0] + rx * math.cos(2 * math.pi * i / n), c[1] + ry * math.sin(2 * math.pi * i / n)), rot, c)
            for i in range(n)]


# ------------------------------------------------------------------------------------------------------------- the puppet

@dataclass
class Frame:
    shapes: List[Tuple[int, List[Pt], RGB, str]] = field(default_factory=list)   # (layer, points, colour, tag)


class Puppet:
    def __init__(self, name: str, width: int = 560):
        self.name = ALIASES.get(name, name)
        self.spec = SPECS.get(self.name, SPECS["lion"])
        sp = self.spec
        self.ok = self.name in QUADRUPEDS
        self.leg_len_u = sp.thigh + sp.shin
        shapes, feet_y = self._shapes(0.0, "idle")          # the standing outline sets the frame: the whole animal
        xs = [x for _t, pts, _c in shapes for x, _y in pts]  # (snout to tail tip) fits, with room for swinging legs
        ys = [y for _t, pts, _c in shapes for _x, y in pts]
        x0, x1, y0 = min(xs), max(xs), min(ys)
        self.unit = width / ((x1 - x0) * 1.12)                # pixels per unit
        self.width = int(width)
        self.height = int((feet_y - y0 + 0.2) * self.unit * 1.15)
        self.feet = int(self.height - 0.06 * self.unit)
        self._origin_x = (-x0 + (x1 - x0) * 0.06) * self.unit

    # body outline (local units, hip joint at (0, 0), shoulder at (1, -back_slope))
    def _torso(self, bob: float, pitch: float) -> List[Pt]:
        sp = self.spec
        x0, x1 = -sp.rump, 1.0 + sp.chest
        cx, rx = (x0 + x1) / 2, (x1 - x0) / 2
        pts_top, pts_bot = [], []
        n = 40
        for i in range(n + 1):
            u = -1 + 2 * i / n
            x = cx + rx * u
            e = (1 - abs(u) ** 2.6) ** (1 / 2.6)
            slope = sp.back_slope * (x / 1.0)
            hump = sp.hump * math.exp(-((x - 0.85) / 0.18) ** 2)
            top = -sp.body_h * 0.55 * e - slope - hump - 0.05
            tuck = sp.belly_tuck * max(0.0, 1 - (x + 0.1) / 0.6) if x < 0.5 else 0.0
            chest = 0.08 * max(0.0, (x - 0.6) / 0.6)
            bot = sp.body_h * 0.45 * e * (1 - tuck) + chest - 0.05 - slope * 0.6
            pts_top.append((x, top))
            pts_bot.append((x, bot))
        pts = pts_top + pts_bot[::-1]
        return [_rot((x, y + bob), pitch, (0.5, 0.0)) for x, y in pts]

    def _leg(self, hip: Pt, a_thigh: float, a_shin: float, hind: bool) -> Tuple[List[Pt], List[Pt], List[Pt], Pt]:
        sp = self.spec
        knee = _seg(hip, a_thigh, sp.thigh)
        foot = _seg(knee, a_shin, sp.shin)
        w0, w1, w2 = sp.leg_w * (1.3 if hind else 1.1), sp.leg_w * 0.78, sp.leg_w * 0.66
        thigh = _quad(hip, knee, w0, w1)
        shin = _quad(knee, foot, w1, w2)
        pw = sp.paw
        paw = _ellipse((foot[0] + pw * 0.35, foot[1] - pw * 0.15), pw * 0.8, pw * 0.42)
        return thigh, shin, paw, foot

    def _shapes(self, phase: float, gait: str) -> Tuple[List[Tuple[str, List[Pt], RGB]], float]:
        """Every shape of the frame in drawing order, local units; and the lowest foot y (to stand it on the ground)."""
        sp = self.spec
        tau = 2 * math.pi
        coat_top = sp.coat_top or _dk(sp.coat, 0.82)
        far = sp.far or _dk(sp.coat, 0.6)
        paw_col = sp.paw_col or (sp.belly if sp.belly != sp.coat else _dk(sp.coat, 0.9))
        if gait == "run":
            amp_t, amp_s, bob, pitch_a = 0.62, 0.9, 0.05, 0.06
            offs = {"hind_near": 0.0, "hind_far": 0.1, "front_near": 0.5, "front_far": 0.6}
        elif gait == "walk":
            amp_t, amp_s, bob, pitch_a = 0.3, 0.7, 0.016, 0.0
            offs = {"hind_near": 0.0, "front_near": 0.25, "hind_far": 0.5, "front_far": 0.75}
        else:
            amp_t, amp_s, bob, pitch_a = 0.0, 0.0, 0.0, 0.0
            offs = {"hind_near": 0.0, "front_near": 0.0, "hind_far": 0.0, "front_far": 0.0}
        body_bob = -bob * abs(math.sin(tau * phase * 2)) if gait == "walk" else -bob * math.sin(tau * phase)
        if gait == "idle":
            body_bob = 0.006 * math.sin(tau * phase)
        pitch = pitch_a * math.sin(tau * phase + 1.0)
        out: List[Tuple[str, List[Pt], RGB]] = []

        def legs(far_side: bool) -> List[Tuple[str, List[Pt], RGB]]:
            res = []
            for kind in ("hind", "front"):
                role = f"{kind}_{'far' if far_side else 'near'}"
                ph = tau * (phase + offs[role])
                swing = math.sin(ph)                      # +1 = leg forward
                lift = max(0.0, math.cos(ph))             # leg in the air while it swings forward
                bend = amp_s * lift                       # the lower leg folds while the leg swings forward
                if kind == "hind":
                    hip = _rot((0.0, 0.04 + body_bob), pitch, (0.5, 0.0))
                    a_t = 0.32 + amp_t * swing            # knee forward under the belly
                    a_s = a_t - 0.7 - bend * 0.8          # hock back: the hind leg's zig-zag, deeper when lifted
                else:
                    hip = _rot((0.95, -sp.back_slope + 0.06 + body_bob), pitch, (0.5, 0.0))
                    a_t = -0.04 + amp_t * swing
                    a_s = a_t + 0.08 - bend * 1.1         # the wrist folds back as the paw lifts
                if gait == "idle":
                    a_t += 0.02 * math.sin(tau * phase + (1.0 if far_side else 0.0))
                    a_s = a_t - (0.7 if kind == "hind" else -0.08)
                thigh, shin, paw, foot = self._leg(hip, a_t, a_s, kind == "hind")
                top = sp.leg_dark if sp.leg_dark else None
                col = far if far_side else sp.coat
                low = (_dk(top, 0.75) if far_side else top) if top else col
                if kind == "hind":                        # the big haunch the thigh hangs from
                    mus = _ellipse((hip[0] - 0.02, hip[1] - 0.1), 0.2, 0.25, 28, a_t * 0.5)
                else:                                     # the shoulder blade
                    mus = _ellipse((hip[0] - 0.02, hip[1] - 0.12), 0.13, 0.24, 28, a_t * 0.5 - 0.2)
                res.append((f"leg_{role}_m", mus, col))
                res += [(f"leg_{role}", thigh, col), (f"shin_{role}", shin, low),
                        (f"paw_{role}", paw, _dk(paw_col, 0.7) if far_side else paw_col)]
                res.append((f"joint_{role}", _ellipse(_seg(hip, a_t, sp.thigh), sp.leg_w * 0.31, sp.leg_w * 0.31), col))
            return res

        out += legs(True)
        # tail: a chain of segments swaying in a wave
        base = _rot((-sp.rump + 0.04, -sp.body_h * 0.3 + body_bob), pitch, (0.5, 0.0))
        n = 8
        b0 = 1.15 - 1.6 * sp.tail_up                     # angle below the horizontal at the base (hangs / rises)
        p = base
        sway_a = 0.10 if gait == "idle" else 0.16
        seg = sp.tail_len / n
        for i in range(n):
            bi = b0 - 0.10 * i * (0.5 - sp.tail_up) + sway_a * (i + 1) / n * \
                math.sin(tau * phase * (0.5 if gait == "idle" else 1.0) - i * 0.55)
            q = (p[0] - math.cos(bi) * seg, p[1] + math.sin(bi) * seg)
            w0 = sp.tail_w * (1 - 0.35 * i / n)
            col = (sp.stripes if (sp.tail_bands and i % 2 == 1) else None) or sp.coat
            out.append((f"tail{i}", _quad(p, q, w0, w0 * 0.92), col))
            out.append((f"tailj{i}", _ellipse(q, w0 * 0.46, w0 * 0.46, 12), col))
            p = q
        if sp.tail_tuft:
            out.append(("tuft", _ellipse(p, sp.tail_w * 1.1, sp.tail_w * 0.8, 16), sp.mane or _dk(sp.coat, 0.45)))
        # torso, neck, head
        torso = self._torso(body_bob, pitch)
        out.append(("torso", torso, sp.coat))
        nod = (0.03 * math.sin(tau * phase * 2 + 0.6)) if gait != "idle" else 0.04 * math.sin(tau * phase * 0.5)
        sh = _rot((1.0 + sp.chest * 0.4, -sp.back_slope - sp.body_h * 0.2 + body_bob), pitch, (0.5, 0.0))
        hc = (1.0 + sp.chest + sp.neck_len + sp.head_r * 0.45, sh[1] - sp.neck_up - sp.body_h * 0.08 + nod)
        if sp.mane:
            mane = _ellipse((hc[0] - sp.head_r * 0.7, hc[1] + sp.head_r * 0.35), sp.head_r * 1.5, sp.head_r * 1.45, 32,
                            -0.3) if self.name == "lion" else \
                _quad((sh[0] - 0.1, sh[1] - sp.body_h * 0.32), (hc[0] - sp.head_r * 0.4, hc[1] - sp.head_r * 0.8),
                      0.08, 0.06)
            out.append(("mane", mane, sp.mane))
        neck = _quad((sh[0] - 0.05, sh[1] + 0.02), (hc[0] - sp.head_r * 0.3, hc[1] + sp.head_r * 0.1), sp.neck_w,
                     sp.head_r * 1.4)
        out.append(("neck", neck, sp.coat))
        if self.name == "lion" and sp.mane:
            out.append(("mane2", _ellipse((hc[0] - sp.head_r * 0.25, hc[1] + sp.head_r * 0.1), sp.head_r * 1.25,
                                          sp.head_r * 1.3, 32), sp.mane))
        # ears behind the head
        hr = sp.head_r
        if sp.ears != "none":
            ex, ey = hc[0] - hr * 0.35, hc[1] - hr * 0.8
            if sp.ears == "round":
                out.append(("ear", _ellipse((ex, ey), hr * 0.3, hr * 0.3, 16), _dk(sp.coat, 0.75)))
            elif sp.ears == "point":
                out.append(("ear", [(ex - hr * 0.25, ey + hr * 0.2), (ex + hr * 0.05, ey - hr * 0.55),
                                    (ex + hr * 0.3, ey + hr * 0.2)], _dk(sp.coat, 0.8)))
            else:
                out.append(("ear", _ellipse((ex - hr * 0.3, ey + hr * 0.1), hr * 0.45, hr * 0.16, 16, -0.5),
                            _dk(sp.coat, 0.8)))
        if sp.horns:
            hx, hy = hc[0] - hr * 0.1, hc[1] - hr * 0.7
            horn = [(hx - hr * 0.9, hy + hr * 0.2), (hx - hr * 0.4, hy - hr * 0.5), (hx + hr * 0.3, hy - hr * 0.55),
                    (hx + hr * 0.5, hy - hr * 0.9), (hx + hr * 0.45, hy - hr * 0.35), (hx + hr * 0.1, hy - hr * 0.05),
                    (hx - hr * 0.4, hy + hr * 0.15)]
            out.append(("horn", horn, sp.horns))
        head = _ellipse(hc, hr, hr * 0.92, 32)
        out.append(("head", head, sp.coat))
        sx = hc[0] + hr * 0.65
        snout = _ellipse((sx + sp.snout * 0.45, hc[1] + hr * 0.3), hr * 0.42 + sp.snout * 0.6, hr * sp.snout_h * 0.62, 24)
        out.append(("snout", snout, sp.face_patch or sp.coat))
        if sp.face_patch:
            out.append(("cheek", _ellipse((hc[0] + hr * 0.15, hc[1] + hr * 0.45), hr * 0.55, hr * 0.38, 20), sp.face_patch))
        tip = (sx + sp.snout * 0.45 + hr * 0.42 + sp.snout * 0.6, hc[1] + hr * 0.18)
        out.append(("nose", _ellipse((tip[0] - hr * 0.08, tip[1]), hr * 0.12, hr * 0.09, 14), sp.nose))
        out.append(("eye", _ellipse((hc[0] + hr * 0.42, hc[1] - hr * 0.12), hr * 0.12, hr * 0.09, 14), sp.eye))
        out.append(("pupil", _ellipse((hc[0] + hr * 0.46, hc[1] - hr * 0.12), hr * 0.05, hr * 0.07, 10), (20, 16, 14)))
        out += legs(False)
        feet_y = max(max(pt[1] for pt in s[1]) for s in out if s[0].startswith("paw_"))
        return out, feet_y

    # ---------------------------------------------------------------------------------------------------------- draw

    def pose(self, phase: float = 0.0, gait: str = "idle") -> Image.Image:
        sp = self.spec
        shapes, feet_y = self._shapes(phase, gait)
        u = self.unit * SS
        W, H = self.width * SS, self.height * SS
        ox = self._origin_x * SS
        oy = self.feet * SS - feet_y * u                  # the lowest foot stands on the ground line

        def px(pts: Sequence[Pt]) -> List[Pt]:
            return [(ox + x * u, oy + y * u) for x, y in pts]

        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        body_mask = Image.new("L", (W, H), 0)
        bm = ImageDraw.Draw(body_mask)
        coat_top = sp.coat_top or _dk(sp.coat, 0.82)
        for tag, pts, col in shapes:
            d.polygon(px(pts), fill=col + (255,))
            if tag in ("torso", "neck", "head", "mane", "mane2"):
                bm.polygon(px(pts), fill=255)
        # one soft gradient over the coat: darker back, lighter belly (the reference's only shading)
        box = body_mask.getbbox()
        if box:
            grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            gd = ImageDraw.Draw(grad)
            y0, y1 = box[1], box[3]
            for y in range(y0, y1):
                k = (y - y0) / max(1, y1 - y0)
                if k < 0.45:
                    c, a = coat_top, int(150 * (1 - k / 0.45))
                else:
                    c, a = sp.belly, int(170 * min(1.0, (k - 0.45) / 0.35))
                gd.line((0, y, W, y), fill=c + (a,))
            m = body_mask.copy()
            img.alpha_composite(Image.composite(grad, Image.new("RGBA", (W, H), (0, 0, 0, 0)), m))
        # markings, clipped to the body
        if sp.stripes or sp.spots or sp.cape:
            mark = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            md = ImageDraw.Draw(mark)
            tbox = [s for s in shapes if s[0] == "torso"][0][1]
            xs = [p[0] for p in tbox]
            ys = [p[1] for p in tbox]
            if sp.cape:
                top = sorted(tbox[:41], key=lambda p: p[0])
                hd = [s for s in shapes if s[0] == "head"][0][1]
                hx = max(p[0] for p in hd)
                band = [(x, y - 0.02) for x, y in top] + [(hx, min(p[1] for p in hd) - 0.02), (hx, min(p[1] for p in hd) +
                        sp.head_r * 0.75)] + [(x, y + sp.body_h * 0.42) for x, y in reversed(top)]
                md.polygon(px(band), fill=sp.cape + (255,))
            if sp.stripes:
                n = 15 if self.name == "tiger" else 18
                for i in range(n):
                    x = min(xs) + (max(xs) - min(xs)) * (i + 0.6) / (n + 0.4)
                    w = 0.022 if self.name == "tiger" else 0.03
                    ln = (max(ys) - min(ys)) * (0.8 if self.name == "tiger" else 0.95)
                    lean = 0.06 * math.sin(i * 1.7)
                    md.polygon(px([(x - w, min(ys) - 0.02), (x + w, min(ys) - 0.02), (x + lean + w * 0.3, min(ys) + ln),
                                   (x + lean - w * 0.3, min(ys) + ln)]), fill=sp.stripes + (255,))
                    if self.name == "tiger" and i % 2 == 0:                  # tigers: a lower broken stripe too
                        md.polygon(px([(x + 0.02, max(ys) - ln * 0.55), (x + 0.04, max(ys) - ln * 0.55),
                                       (x + 0.05, max(ys) - 0.08), (x + 0.03, max(ys) - 0.08)]), fill=sp.stripes + (255,))
            if sp.spots:
                import random as _r
                rg = _r.Random(self.name)
                for _ in range(110 if sp.spot_r < 0.03 else 40):
                    x, y = rg.uniform(min(xs), max(xs)), rg.uniform(min(ys), max(ys))
                    r = rg.uniform(sp.spot_r * 0.7, sp.spot_r * 1.3)
                    md.ellipse([ox + (x - r) * u, oy + (y - r) * u, ox + (x + r) * u, oy + (y + r) * u],
                               fill=sp.spots + (235,))
            clip = body_mask.copy()
            if not sp.cape:                               # markings stay on the torso / neck
                hm = Image.new("L", (W, H), 0)
                ImageDraw.Draw(hm).polygon(px([s for s in shapes if s[0] == "head"][0][1]), fill=255)
                from PIL import ImageChops
                clip = ImageChops.subtract(clip, hm)
            mark.putalpha(Image.composite(mark.getchannel("A"), Image.new("L", (W, H), 0), clip))
            img.alpha_composite(mark)
            # the face, eye and near legs go back on top of the markings
            for tag, pts, col in shapes:
                if tag in ("snout", "cheek", "nose", "eye", "pupil") or (sp.cape and tag.startswith(("leg_", "shin_", "paw_", "joint_"))
                                                                          and "near" in tag and not tag.endswith("_m")):
                    d.polygon(px(pts), fill=col + (255,))
        if sp.stripes:                                    # the near legs carry stripes too (the reference tiger)
            for tag, pts, col in shapes:
                if tag.startswith(("leg_", "shin_")) and "near" in tag and not tag.endswith("_m"):
                    (a0, a1, a2, a3) = pts[:4]
                    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                    ld = ImageDraw.Draw(lay)
                    for f in (0.3, 0.62):
                        l0 = (a3[0] + (a2[0] - a3[0]) * f, a3[1] + (a2[1] - a3[1]) * f)
                        r0 = (a0[0] + (a1[0] - a0[0]) * f, a0[1] + (a1[1] - a0[1]) * f)
                        w = 0.018
                        ld.polygon(px([(l0[0] - 0.05, l0[1] - w), (r0[0] + 0.05, r0[1] - w), (r0[0] + 0.05, r0[1] + w),
                                       (l0[0] - 0.05, l0[1] + w)]), fill=sp.stripes + (255,))
                    clip = Image.new("L", (W, H), 0)
                    ImageDraw.Draw(clip).polygon(px(pts), fill=255)
                    lay.putalpha(Image.composite(lay.getchannel("A"), Image.new("L", (W, H), 0), clip))
                    img.alpha_composite(lay)
        out = img.resize((self.width, self.height), Image.LANCZOS)
        return out

    @property
    def body(self) -> Image.Image:                     # for callers that only need the size
        return Image.new("RGBA", (self.width, self.height))

    @property
    def leg_len(self) -> float:
        return self.leg_len_u * self.unit


@lru_cache(maxsize=32)
def puppet(name: str, width: int) -> Puppet:
    return Puppet(name, width)
