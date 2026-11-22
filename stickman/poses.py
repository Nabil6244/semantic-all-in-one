"""The pose library: 36 still poses, 3 moving cycles (walk, run, sneak) and the jump = 40.

Some still poses carry a small loop (OSC: a wave, a clap, laughing shakes).
POSE_PROPS puts a prop in the hand or above the head while a pose is held.
"""
import math

from .rig import NEUTRAL, blend, make

STATIC = {
    "stand": dict(NEUTRAL),
    "point": make(lean=5, head=4, sh_f=92, el_f=-4, sh_b=-15, el_b=15, mouth="open"),
    "shrug": make(head=12, sh_b=-50, el_b=-75, sh_f=50, el_f=75, mouth="flat"),
    "think": make(head=-8, sh_f=75, el_f=140, sh_b=-20, el_b=60, mouth="flat", eyes="up"),
    "cheer": make(head=-6, sh_b=-135, el_b=-30, sh_f=135, el_f=30, hip_b=-10, hip_f=10,
                  mouth="big", eyes="happy"),
    "facepalm": make(lean=8, head=18, sh_f=80, el_f=105, sh_b=-10, el_b=10,
                     mouth="frown", eyes="closed"),
    "scared": make(lean=-12, head=-6, sh_f=75, el_f=55, sh_b=55, el_b=70,
                   hip_b=-14, kn_b=22, hip_f=18, kn_f=22, mouth="o", eyes="wide"),
    # ---- Phase 3
    "wave": make(sh_f=120, el_f=30, sh_b=-12, el_b=10, mouth="smile", eyes="happy"),
    "clap": make(sh_f=60, el_f=50, sh_b=60, el_b=50, mouth="big", eyes="happy"),
    "dance": make(sh_f=130, el_f=20, sh_b=-130, el_b=-20, hip_f=12, kn_f=20, mouth="big", eyes="happy"),
    "laugh": make(lean=-8, head=-12, sh_f=25, el_f=90, sh_b=20, el_b=95, mouth="big", eyes="happy"),
    "cry": make(lean=6, head=20, sh_f=80, el_f=105, sh_b=70, el_b=115, mouth="frown", eyes="closed"),
    "sad": make(lean=10, head=25, sh_f=4, el_f=4, sh_b=-4, el_b=4, kn_f=6, kn_b=6, mouth="frown"),
    "angry": make(lean=6, head=6, sh_f=30, el_f=-10, sh_b=-30, el_b=10, hip_f=10, hip_b=-10,
                  mouth="frown", eyes="angry"),
    "tired": make(lean=14, head=28, sh_f=10, el_f=4, sh_b=4, el_b=4, kn_f=10, kn_b=10,
                  mouth="flat", eyes="half"),
    "yawn": make(lean=-6, head=-14, sh_f=120, el_f=40, sh_b=-120, el_b=-40, mouth="o", eyes="closed"),
    "arms_crossed": make(lean=-2, sh_f=35, el_f=-135, sh_b=-35, el_b=135, mouth="flat"),
    "hands_hips": make(lean=-3, sh_f=40, el_f=-76, sh_b=-40, el_b=76, hip_f=10, hip_b=-10, mouth="smile"),
    "present": make(sh_f=70, el_f=20, sh_b=-70, el_b=-20, mouth="open"),
    "stop": make(lean=-5, sh_f=80, el_f=75, sh_b=-12, el_b=10, mouth="flat"),
    "look": make(lean=8, head=-4, sh_f=110, el_f=95, sh_b=-12, el_b=10, mouth="flat"),
    "phone": make(head=6, sh_f=60, el_f=135, sh_b=-12, el_b=10, mouth="open"),
    "type": make(lean=10, head=15, sh_f=25, el_f=65, sh_b=15, el_b=75, mouth="flat"),
    "carry": make(lean=-6, sh_f=50, el_f=50, sh_b=45, el_b=55, kn_f=8, kn_b=8, mouth="flat"),
    "push": make(lean=25, head=-6, sh_f=85, el_f=0, sh_b=80, el_b=5, hip_b=-30, kn_b=0, hip_f=20, kn_f=25,
                 mouth="flat", eyes="closed"),
    "pull": make(lean=-20, head=6, sh_f=75, el_f=5, sh_b=70, el_b=10, hip_f=30, kn_f=5, hip_b=-10, kn_b=20,
                 mouth="flat"),
    "lift": make(sh_f=135, el_f=40, sh_b=-135, el_b=-40, kn_f=12, kn_b=12, hip_f=12, hip_b=-12, mouth="flat"),
    "sit": make(lean=-10, sh_f=60, el_f=20, sh_b=45, el_b=30, hip_f=115, kn_f=50, hip_b=108, kn_b=40),
    "sleep": make(rot=-90, lean=0, sh_f=-5, el_f=5, sh_b=-10, el_b=5, hip_f=4, kn_f=4, hip_b=-4, kn_b=4,
                  mouth="flat", eyes="closed"),
    "fall": make(rot=80, sh_f=160, el_f=0, sh_b=150, el_b=0, hip_f=0, kn_f=10, hip_b=-6, kn_b=20,
                 mouth="o", eyes="closed"),
    "kneel": make(sh_f=40, el_f=10, sh_b=-12, el_b=10, hip_f=80, kn_f=80, hip_b=0, kn_b=100, mouth="smile"),
    "crouch": make(lean=30, head=-10, sh_f=50, el_f=20, sh_b=40, el_b=30, hip_f=70, kn_f=130,
                   hip_b=60, kn_b=125, mouth="flat", eyes="wide"),
    "bow": make(lean=50, head=10, sh_f=-30, el_f=0, sh_b=-40, el_b=0, mouth="smile", eyes="closed"),
    "fist_up": make(lean=-4, sh_f=170, el_f=5, sh_b=-12, el_b=10, mouth="big", eyes="happy"),
    "idea": make(head=-6, sh_f=75, el_f=95, sh_b=-12, el_b=10, mouth="open", eyes="wide"),
    "shiver": make(sh_f=35, el_f=-135, sh_b=-35, el_b=135, hip_f=2, hip_b=-2, kn_f=8, kn_b=8,
                   mouth="flat", eyes="wide"),
}

# small loops on top of a still pose: (angle, amplitude, period s)
OSC = {
    "wave": [("el_f", 28, 0.5)],
    "clap": [("el_f", 16, 0.36), ("el_b", 16, 0.36)],
    "dance": [("lean", 7, 0.6), ("sh_f", 30, 0.6), ("sh_b", 30, 0.6), ("hip_f", 10, 0.6)],
    "laugh": [("lean", 4, 0.24), ("head", 4, 0.24)],
    "cry": [("head", 3, 0.4)],
    "angry": [("lean", 2, 0.14)],
    "type": [("el_f", 5, 0.18), ("el_b", -5, 0.18)],
    "push": [("lean", 2, 0.5)],
    "lift": [("sh_f", 4, 0.8), ("sh_b", -4, 0.8)],
    "shiver": [("lean", 1.6, 0.08), ("head", 1.5, 0.1)],
    "tired": [("head", 3, 2.0)],
}

# props a pose carries: (prop, where, size in figure heights)
POSE_PROPS = {
    "phone": [("phone", "hand_f", 0.13)],
    "type": [("laptop", "front_low", 0.30)],
    "carry": [("box", "hands", 0.26)],
    "lift": [("barbell", "hands_up", 0.62)],
    "sleep": [("zzz", "above", 0.22)],
    "tired": [("zzz", "above", 0.16)],
    "idea": [("bulb", "above", 0.22)],
    "think": [("question", "above", 0.16)],
    "cry": [("drop", "face", 0.07)],
}

CYCLES = {"walk": 0.9, "run": 0.5, "sneak": 1.1}          # seconds per full cycle (two steps)
JUMP_DUR = 1.0
JUMP_HEIGHT = 0.45                            # figure heights

_CROUCH = make(lean=18, head=8, sh_b=-55, el_b=20, sh_f=-45, el_f=20,
               hip_b=40, kn_b=80, hip_f=50, kn_f=90, mouth="flat")
_AIR = make(lean=-4, head=-8, sh_b=-160, el_b=-10, sh_f=160, el_f=10,
            hip_b=25, kn_b=60, hip_f=55, kn_f=75, mouth="big", eyes="happy")

ALL = tuple(STATIC) + tuple(CYCLES) + ("jump",)


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


#           stride  pelvis  bob    lift  arm swing  elbow
_GAITS = {"walk": (0.32, 0.400, 0.012, 0.07, 18, 14),
          "run": (0.44, 0.370, 0.020, 0.16, 42, 80),
          "sneak": (0.20, 0.330, 0.008, 0.05, 6, 70)}


def leg_ik(x, y):
    """Hip and knee angles that put the foot at (x forward, y down) from the pelvis; the knee bends forward."""
    from .rig import SHIN, THIGH
    d = min(math.hypot(x, y), (THIGH + SHIN) * 0.999)
    t = math.degrees(math.atan2(x, y))
    alpha = math.degrees(math.acos((THIGH ** 2 + d ** 2 - SHIN ** 2) / (2 * THIGH * d)))
    beta = math.degrees(math.acos((SHIN ** 2 + d ** 2 - THIGH ** 2) / (2 * SHIN * d)))
    return t + alpha, alpha + beta


def cycle(name, phase):
    """Walk or run pose at a cycle phase (0..1 repeats).

    Each foot follows a path: on the ground it slides back in a straight line at a steady
    speed (so the foot lock carries the body forward with no slip), in the air it arcs
    forward. The knees come from IK, so the swinging foot is always above the planted one.
    """
    stride, hp, bob, lift, arm, el = _GAITS[name]
    p = {"walk": lambda: make(lean=5, head=2, mouth="smile"),
         "run": lambda: make(lean=14, head=4, mouth="open"),
         "sneak": lambda: make(lean=20, head=-6, mouth="flat", eyes="wide")}[name]()
    hp = hp - bob * math.cos(4 * math.pi * phase)          # lowest at double support
    for s, off in (("f", 0.0), ("b", 0.5)):
        q = (phase + off) % 1.0
        if q < 0.5:                                         # planted
            x, y = stride / 2 - stride * (q / 0.5), hp
        else:                                               # swinging
            u = (q - 0.5) / 0.5
            x, y = -stride / 2 + stride * smooth(u), hp - lift * math.sin(math.pi * u)
        p["hip_" + s], p["kn_" + s] = leg_ik(x, y)
        swing = math.cos(2 * math.pi * q)
        p["sh_" + s] = (55 if name == "sneak" else 0) - arm * swing
        p["el_" + s] = el + 0.3 * el * swing
    return p


def jump(u):
    """Jump at progress u (0..1): crouch, air, land. Returns (pose, lift in figure heights)."""
    if u < 0.25:
        return blend(NEUTRAL, _CROUCH, smooth(u / 0.25)), 0.0
    if u < 0.75:
        s = (u - 0.25) / 0.5
        if s < 0.75:
            pose = blend(_CROUCH, _AIR, smooth(s / 0.25))
        else:
            pose = blend(_AIR, _CROUCH, smooth((s - 0.75) / 0.25))
        return pose, 4 * s * (1 - s) * JUMP_HEIGHT
    return blend(_CROUCH, NEUTRAL, smooth((u - 0.75) / 0.25)), 0.0


def idle(pose, t, seed, name=None):
    """Small breathing sway so a still pose never looks frozen, plus the pose's own loop."""
    p = dict(pose)
    for key, amp, period in OSC.get(name, ()):
        p[key] += amp * math.sin(2 * math.pi * t / period + seed)
    p["lean"] += 1.2 * math.sin(2 * math.pi * t / 2.8 + seed)
    p["head"] += 1.6 * math.sin(2 * math.pi * t / 3.7 + seed * 1.7)
    p["sh_b"] -= 2.0 * math.sin(2 * math.pi * t / 2.8 + seed + 0.6)
    p["sh_f"] += 2.0 * math.sin(2 * math.pi * t / 2.8 + seed + 0.6)
    return p
