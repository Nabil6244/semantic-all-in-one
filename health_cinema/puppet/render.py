"""Render puppet shots and transitions to mp4: a rigged character walking/acting over a collage still (or across a seam between two stills).

    render_shot(still_path, character, action, out_path, duration=5.0, fps=30, direction='right', size=(1920, 1080), params=None) -> out_path
    render_transition(still_a, still_b, character, transition, out_path, duration, fps=30, size=(1920, 1080), direction='right', params=None) -> out_path

Both are cached on disk (out/puppet_cache/clips/<key>.mp4) by every input plus VERSION plus a hash of the puppet sources, so an unchanged shot is copied,
not re-rendered. Safe from worker threads/processes: all state is per call, files are written to a temp name and renamed, pipes are always closed.
params (shot): x0, x1 (screen fractions the walker travels between, default -0.14 -> 1.14), y / y1 (feet row fraction, default the still's walking line),
char_h (character height as a fraction of H at the walking line, default 0.44), x (fraction for standing actions), zoom (end camera zoom, default 1.05),
occluders ('auto' | 'off' | [('rect', x0, y0, x1, y1) | ('poly', [(x, y), ...])] in screen fractions), boil (px), grain, dust (count), action (dict passed on to the rig),
seed, cancel (callable -> True to abort) and progress (callable(fraction)) are accepted as keyword arguments / params. See transitions.py for transition params.

TIMELINE MODE (narration-driven scene clip). It is used when params has any of beats / enter / exit / link_in / link_out (otherwise the legacy single-action
shot above runs unchanged). The picture is NOT mirrored here: the character itself faces left or right.
  beats : [{"t0", "t1", "action", "x0", "x1", "params"}] seconds inside the clip, x as screen-width fractions (<0 or >1 = off-screen). Beats run in order
          (an overlapping t0 is pushed to the previous t1); between beats the character holds its last x and idles (stand_idle). Locomotion beats
          (walk, run, stop) move x0 -> x1 at constant speed and tie the foot phase to the ground distance travelled; stand-in-place beats (look/look_around,
          point, wave, pick_up, put_down, sit, turn, ...) hold x (x0, else the last x) and play over the beat ("look" loops, the others are stretched to the beat
          length; params["duration"] wins). "turn" flips the facing at its end. A walk that ends in a stand beat gets a natural 0.9 s decelerating `stop`.
          beat params: facing ('left'|'right'), phase0 / phase1 (gait phase in cycles at the beat's start / end), plus rig params (prop, step_scale ...).
  enter : 'left' | 'right' | 'none'. Walk-in starting just off that edge at t=0, reaching x_in (default 0.3 from the left, 0.7 from the right) in ~1.6 s
          (enter_dur; or distance / link speed when link_in carries one).
  exit  : 'left' | 'right' | 'none'. Walk-out from wherever the character stands, off the frame, finishing at duration - exit_margin (default 0.6 s: the app
          adds a 0.5 s margin to scene clips, so the cut never catches half a body). With enter and exit and no beats and a walk/run action
          the character simply crosses the frame in one go.
  link_in / link_out : {"y", "char_h", "facing", "phase", "speed"}: y = feet row (fraction of H), char_h = height fraction of H, facing, phase = gait phase (cycles)
          AT THE CUT (clip end for link_out, clip start for link_in), speed = screen widths per second. Clip N's exit and clip N+1's entry then share y, height,
          facing, speed and a gait phase that carries on across the cut (offscreen distance covered between them is accounted for), so the cut reads as one walk.
          Away from the link the character eases (about 1 s) to the clip's own y / char_h (params y, char_h, else this still's walking line and perspective height).
          link_params(still_a, still_b, direction) builds the matched pair.
  x_in, enter_dur, exit_margin, auto_stop (default True), zoom (amplitude of a slow breathing push, default 0.04: it is 0 at both ends of the clip so link
  positions stay exact), char_h / y (clip's own height fraction / feet row), ref_person_h (height fraction of people already in the still, for perspective).
render_shot(...) also accepts params["beats"] with action=None.

LANE (timeline mode). params["lane"] = {"x0", "x1", "y", "h_hint", "avoid": [[a, b], ...]} (fractions of the frame; extra keys such as conf/source are ignored) says where on
  the picture the character may stand. The string "none" raises RenderError("no usable lane") so the caller can fall back to the plain still; None/absent keeps the old behaviour.
  * every beat x is clamped into [lane.x0, lane.x1]; feet row = lane.y (unless params y), height = clip(lane.h_hint, .34, .50) (unless params char_h); link_in/link_out still win at the cut.
  * avoid spans (expanded by half the character width) cut the lane into clear intervals. Stand positions snap to the nearest clear x; a walk never leaves the interval it starts in
    (it stops short of the span) unless the span is behind a foreground occluder of the still (then it is walked behind).
  * lane ends: an end that lies at the frame edge (within 0.02) is a hard end: the character walks in/out off the frame as before. Any other end (lane stops inside the picture, or an avoid span
    is in the way) is soft: the character appears AT that end with a 0.4 s alpha fade-in while already walking, and on exit walks along the lane to the soft end and fades out over 0.4 s there.
    A walk beat that asks for an off-frame x on a soft side is clamped to the end and fades out too. Enter/exit that cannot cross an avoid span (no single interval) do not cross.
  default heights: when no lane/char_h, the perspective height is raised ~10% and clamped to .34-.50 (link_params as well).
  joins: a pose change (stand <-> walk, stand <-> gesture) cross-fades over 0.25 s (outgoing pose stays planted at its own x), a walk that starts from standing eases in over ~0.3 s,
  a gesture (point, wave, pick_up, put_down) waits 0.2 s of anticipation (still pose) before it starts.
  tint: params["tint"] = [r, g, b] multipliers (or 0-255 colour) applied to the sprite after the automatic scene tint; given to character.render_character_frame(tint=...) when it accepts
  it, otherwise multiplied here. "auto"/absent = scene light only. The contact shadow is stronger and longer than before."""
from __future__ import annotations
import hashlib, inspect, json, math, os, shutil, subprocess, tempfile, threading
from pathlib import Path
import numpy as np
from PIL import Image

from . import effects, scene, transitions

VERSION = "3"
CLIP_DIR = scene.CACHE_DIR / "clips"
_HERE = Path(__file__).resolve().parent
_REF: dict = {}
_LOCK = threading.Lock()

class RenderError(RuntimeError): pass
class Cancelled(RenderError): pass

def _analyse(path):
    try: return scene.analyse(path)
    except scene.SceneError as e: raise RenderError(str(e)) from e

def _puppet():
    from . import __init__ as _p  # noqa: F401  (package namespace; raises a clear error if Agent A's files are missing)
    import importlib
    return importlib.import_module(__package__)

def _ffmpeg() -> str:
    try:
        from .. import assets
        p = assets.ffmpeg_path()
        if p: return p
    except Exception: pass
    return shutil.which("ffmpeg") or "ffmpeg"

def _code_hash() -> str:
    h = hashlib.sha256(VERSION.encode())
    for f in sorted(_HERE.glob("*.py")): h.update(f.name.encode()); h.update(f.read_bytes())
    return h.hexdigest()[:16]

def _file_hash(path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for c in iter(lambda: fh.read(1 << 20), b""): h.update(c)
    except OSError as e:
        raise RenderError(f"cannot read still {path}: {e}") from e
    return h.hexdigest()[:20]

def _key(**kw) -> str:
    return hashlib.sha256(json.dumps(kw, sort_keys=True, default=str).encode() + _code_hash().encode()).hexdigest()[:24]

def _check(character, action, duration, fps, size, direction, P):
    if character not in P.list_characters(): raise RenderError(f"unknown character {character!r}; have {P.list_characters()}")
    if action is not None and action not in P.list_actions(): raise RenderError(f"unknown action {action!r}; have {P.list_actions()}")
    if not (duration and duration > 0): raise RenderError(f"duration must be > 0, got {duration!r}")
    if not (1 <= fps <= 120): raise RenderError(f"fps must be 1..120, got {fps!r}")
    if direction not in ("left", "right"): raise RenderError(f"direction must be 'left' or 'right', got {direction!r}")
    if size[0] < 64 or size[1] < 64 or size[0] % 2 or size[1] % 2: raise RenderError(f"size must be even and at least 64x64, got {size!r}")

# ---------------------------------------------------------------- sprites
def _ref_height(P, character: str) -> float:
    """Pixels from the ground anchor to the top of the head at scale 1.0 (the unit for char_h)."""
    with _LOCK:
        if character not in _REF:
            im, (ax, ay) = P.render_character_frame(character, "stand_idle", 0.0, 1.0)
            bb = im.getbbox(); _REF[character] = max(ay - (bb[1] if bb else 0), 1.0)
        return _REF[character]

class Sprites:
    """Per-render sprite cache: gait is cyclic so a few dozen distinct phases cover a whole shot."""
    def __init__(self, P, character, action, aparams):
        self.P, self.c, self.a, self.ap = P, character, action, aparams or {}; self.cache = {}; self.ref = _ref_height(P, character)
        from . import actions as _act
        self.act = _act.get(action); self.dur = P.action_duration(action, self.ap)
    def stride_ratio(self) -> float:
        return (self.P.stride_length(self.c, self.a, 1.0, self.ap) / self.ref) if self.act.cyclic else .62
    def get(self, h_px: float, t: float, phase):
        scale = round(h_px / self.ref, 3)
        if self.act.cyclic and phase is not None: k = ("p", scale, round(phase * 40) % 40); ph = (k[2] / 40.0) % 1.0; tt = t
        else:
            tt = min(max(t, 0.0), self.dur) if not self.act.cyclic else t; k = ("t", scale, round(tt * 30)); ph = None; tt = k[2] / 30.0
        if k not in self.cache:
            if len(self.cache) > 400: self.cache.clear()
            self.cache[k] = self.P.render_character_frame(self.c, self.a, tt, scale, "right", ph, self.ap)
        return self.cache[k]

def _over(frame: Image.Image, layer: Image.Image, pos, occ: Image.Image | None, alpha: float = 1.0):
    """Composite an RGBA layer at integer pos; its alpha is multiplied by `alpha` and by (1 - occluder)."""
    x, y = pos; W, H = frame.size
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + layer.width, W), min(y + layer.height, H)
    if x1 <= x0 or y1 <= y0: return
    lay = layer.crop((x0 - x, y0 - y, x1 - x, y1 - y)); a = np.asarray(lay.split()[3], dtype=np.float32) * alpha
    if occ is not None: a = a * (1 - np.asarray(occ.crop((x0, y0, x1, y1)), dtype=np.float32) / 255.0)
    lay.putalpha(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)))
    reg = frame.crop((x0, y0, x1, y1)).convert("RGBA"); reg.alpha_composite(lay)
    frame.paste(reg.convert("RGB"), (x0, y0))

def _place(P, frame, occ, sprites: Sprites, t, ch, light, jitter):
    """Draw soft ground shadow then the tinted puppet at ch = {x, y (feet), h, alpha, phase}."""
    if ch is None or ch["alpha"] <= .003: return
    ch = {**ch, "h": float(ch["h"]), "x": float(ch["x"]), "y": float(ch["y"]), "alpha": float(ch["alpha"])}
    sp, (ax, ay) = sprites.get(ch["h"], t, ch.get("phase"))
    sp = scene.tint_character(sp, light)
    fx, fy = ch["x"] + jitter[0], ch["y"] + jitter[1]
    bw, bh = int(ch["h"] * 1.4), int(ch["h"] * .34)
    sh = scene.ground_shadow((bw, bh), (bw / 2, bh / 2), ch["h"], light)
    _over(frame, sh, (int(fx - bw / 2), int(fy - bh / 2)), occ, ch["alpha"])
    _over(frame, sp, (int(round(fx - ax)), int(round(fy - ay))), occ, ch["alpha"])


# ---------------------------------------------------------------- timeline mode
_ALIAS = {"look": "look_around", "idle": "stand_idle", "pickup": "pick_up", "putdown": "put_down", "none": None}
_LOCO = ("walk", "run", "stop")
_LOOP = ("look_around", "stand_idle")
LINK_ACTION = {"step_scale": 1.4}   # longer strides so a link walk covers ground at a purposeful pace (cadence ~1.25x natural)
_PERIOD = {"walk": .95, "run": .62, "stop": .95}

def _ease(u): u = min(max(u, 0.0), 1.0); return u * u * (3 - 2 * u)

def _fit_h(horizon_f: float, y_f: float, ref=None) -> float:
    """Character height as a fraction of the frame for feet at y_f (perspective from the horizon). Uses character.fit_height when present."""
    try:
        from .character import fit_height
        v = float(fit_height(1.0, y_f, horizon_f, ref))
    except Exception:
        d = max(.05, y_f - horizon_f); v = float(min(.48, max(.30, .42 * (d / .40) ** .6)))
    return float(min(.50, max(.34, v * 1.1)))

class SpriteBank:
    """Quantised sprite cache for timeline mode: gait sprites by phase (1/40 cycle), others by time (1/30 s), scale in 1% steps, per facing."""
    def __init__(self, P, character, tint=None):
        self.P, self.c, self.cache = P, character, {}; self.ref = _ref_height(P, character)
        try: self.tint_kw = "tint" in inspect.signature(P.render_character_frame).parameters
        except (TypeError, ValueError): self.tint_kw = False
        self.tint = tint if tint not in (None, "auto") else None
    def stride_ratio(self, action, ap=None) -> float:
        if action not in _LOCO: return .62
        return self.P.stride_length(self.c, action, 1.0, ap or {}) / self.ref
    def get(self, action, ap, h_px, t, phase, facing):
        sk = int(round(math.log(max(h_px, 1.0) / self.ref) / math.log(1.01))); scale = 1.01 ** sk
        akey = json.dumps(ap, sort_keys=True, default=str) if ap else ""
        if phase is not None: q = int(round(phase * 40)) % 40; k = (action, akey, sk, facing, "p", q); ph = q / 40.0; tt = t
        else: q = int(round(max(t, 0.0) * 30)); k = (action, akey, sk, facing, "t", q); ph = None; tt = q / 30.0
        if k not in self.cache:
            if len(self.cache) > 500: self.cache.clear()
            kw = {"tint": self.tint} if (self.tint_kw and self.tint is not None) else {}
            self.cache[k] = self.P.render_character_frame(self.c, action, tt, scale, facing, ph, ap or None, **kw)
        return self.cache[k]

def link_params(still_a, still_b, direction="right", character="suit_man", size=(1920, 1080), phase=0.0, speed=None, action="walk"):
    """Matched params for two consecutive scene clips so that the character walks OFF scene A's `direction` edge and IN from the opposite edge of scene B
    at the same feet row, height, facing, speed and gait phase. -> (params_a, params_b), each ready to merge into render_shot params
    (A gets exit + link_out, B gets enter + link_in). y/height are a compromise that stands on both floors: when only one still has a reliable floor (floor_ok)
    that floor wins, else the mean; the feet are kept at least 0.22 of the frame below each horizon. speed defaults to a brisk purposeful pace
    (1.25x natural cadence with 1.4x strides, in screen widths / s); both dicts also carry action={'step_scale': 1.4}. phase = gait phase (cycles) at the cut."""
    if direction not in ("left", "right"): raise RenderError(f"direction must be 'left' or 'right', got {direction!r}")
    sa, sb = _analyse(still_a), _analyse(still_b)
    if sa.floor_ok and not sb.floor_ok: y = sa.walk_y
    elif sb.floor_ok and not sa.floor_ok: y = sb.walk_y
    else: y = (sa.walk_y + sb.walk_y) / 2
    y = float(min(.93, max(y, max(sa.horizon, sb.horizon) + .22, .74)))
    ch = float(np.clip((_fit_h(sa.horizon, y) + _fit_h(sb.horizon, y)) / 2, .38, .50))
    if speed is None:
        P = _puppet(); bank = SpriteBank(P, character); speed = 1.25 * bank.stride_ratio(action, LINK_ACTION) * ch * size[1] / _PERIOD.get(action, .95) / size[0]
    face = direction; enter = "left" if direction == "right" else "right"
    link = lambda: {"y": round(y, 4), "char_h": round(ch, 4), "facing": face, "phase": round(float(phase) % 1.0, 4), "speed": round(float(speed), 4)}
    return {"exit": direction, "link_out": link(), "action": dict(LINK_ACTION)}, {"enter": enter, "link_in": link(), "action": dict(LINK_ACTION)}

_JOIN = .25      # pose cross-fade at a change of beat (s)
_FADE = .4       # alpha fade at a soft lane end (s)
_GESTURES = ("point", "wave", "pick_up", "put_down")

def _lane_norm(lane):
    """-> None | dict(x0, x1, y, h, avoid[(a, b)]) validated; the string 'none' (or an empty/degenerate lane) -> RenderError('no usable lane')."""
    if lane is None: return None
    if isinstance(lane, str):
        raise RenderError("no usable lane")
    if not isinstance(lane, dict): raise RenderError(f"lane must be a dict, got {type(lane).__name__}")
    try:
        x0, x1 = float(lane.get("x0", 0.0)), float(lane.get("x1", 1.0))
        x0, x1 = max(0.0, min(x0, x1)), min(1.0, max(x0, x1))
        av = [(min(float(a), float(b)), max(float(a), float(b))) for a, b in (lane.get("avoid") or [])]
        y = lane.get("y"); h = lane.get("h_hint")
        y = None if y is None else min(.97, max(.3, float(y))); h = None if h is None else min(.50, max(.34, float(h)))
    except (TypeError, ValueError) as e: raise RenderError(f"bad lane {lane!r}: {e}") from e
    if x1 - x0 < .04: raise RenderError("no usable lane")
    return dict(x0=x0, x1=x1, y=y, h=h, avoid=av)

def _intervals(lane, hw, cover=None):
    """Clear intervals [(a, b, hard_a, hard_b)] of the lane after removing avoid spans (grown by hw). A span a foreground occluder hides is walked behind instead."""
    lx0, lx1 = lane["x0"], lane["x1"]; spans = sorted(sp for sp in lane["avoid"] if not (cover and cover(*sp)))
    iv = []; cur = lx0
    for a, b in spans:
        a2, b2 = a - hw, b + hw
        if a2 > cur: iv.append([cur, min(a2, lx1)])
        cur = max(cur, b2)
    if cur < lx1: iv.append([cur, lx1])
    iv = [(a, b, a <= lx0 + 1e-9 and lx0 <= .02, b >= lx1 - 1e-9 and lx1 >= .98) for a, b in iv if b - a >= .03]
    if not iv: raise RenderError("no usable lane")
    return iv

class Timeline:
    """Normalises beats / enter / exit / links into contiguous segments and answers state(t) -> dict(x, y, h, facing, action, ap, t, phase, alpha) in output pixels."""
    def __init__(self, P, bank, p, duration, size, base_y, horizon, action, direction):
        self.P, self.bank, self.W, self.H, self.dur = P, bank, size[0], size[1], float(duration)
        W, H = self.W, self.H; li, lo = p.get("link_in") or {}, p.get("link_out") or {}
        self.lane = _lane_norm(p.get("lane")); ln = self.lane or {}
        self.ymid = float(p.get("y", ln.get("y") if ln.get("y") is not None else base_y)); ref = p.get("ref_person_h")
        self.hmid = float(p.get("char_h", ln.get("h") if ln.get("h") is not None else _fit_h(horizon, self.ymid, ref)))
        self.yin, self.hin = float(li.get("y", self.ymid)), float(li.get("char_h", self.hmid))
        self.yout, self.hout = float(lo.get("y", self.ymid)), float(lo.get("char_h", self.hmid))
        face0 = li.get("facing") or p.get("facing") or direction
        enter, exit_ = p.get("enter", "none") or "none", p.get("exit", "none") or "none"
        if li and enter == "none": enter = "left" if face0 == "right" else "right"
        if lo and exit_ == "none": exit_ = lo.get("facing") or direction
        for nm, v in (("enter", enter), ("exit", exit_)):
            if v not in ("left", "right", "none"): raise RenderError(f"{nm} must be 'left', 'right' or 'none', got {v!r}")
        self.margin = lambda h: (.30 * h * H) / W + .02
        self.iv = _intervals(self.lane, .15 * self.hmid * H / W + .01, p.get("_occ_cover")) if self.lane else None
        allowed = set(P.list_actions()); beats = []
        for b in sorted((dict(b) for b in (p.get("beats") or [])), key=lambda b: float(b.get("t0", 0))):
            a = b.get("action", "stand_idle"); a = _ALIAS.get(a, a)
            if a not in allowed: raise RenderError(f"unknown beat action {b.get('action')!r}; have {sorted(allowed)}")
            t0, t1 = float(b.get("t0", 0)), float(b.get("t1", b.get("t0", 0) + 1)); t0 = min(max(t0, 0.0), self.dur); t1 = min(max(t1, t0 + .05), self.dur)
            beats.append(dict(t0=t0, t1=t1, action=a, x0=b.get("x0"), x1=b.get("x1"), ap=dict(p.get("action") or {}, **(b.get("params") or {})), face=(b.get("params") or {}).get("facing")))
        self.segs = []; t_cur = 0.0; x_cur = self._snap(float(p.get("x", .5)))[1]; face = face0; ph_acc = float((li.get("phase") if li else p.get("phase", 0.0)) or 0.0)
        h_in = self.hin if li else self.hmid; speed = float(li.get("speed") or 0.0) or None
        cross = (not beats and enter != "none" and exit_ != "none" and enter != exit_ and (action in ("walk", "run") or action is None) and (not self.iv or len(self.iv) == 1))
        gone = False
        if enter != "none":
            xs = -self.margin(h_in) if enter == "left" else 1 + self.margin(h_in); xi = float(p.get("x_in", .3 if enter == "left" else .7))
            if cross: xi = (1 + self.margin(h_in)) if exit_ == "right" else -self.margin(h_in)
            fade_in = fade_out = 0.0
            if self.iv:
                a_, b_, ha_, hb_ = self.iv[0 if enter == "left" else -1]
                if enter == "left" and not ha_: xs, fade_in = a_, _FADE
                if enter == "right" and not hb_: xs, fade_in = b_, _FADE
                if cross:
                    if exit_ == "right" and not hb_: xi, fade_out = b_, _FADE
                    if exit_ == "left" and not ha_: xi, fade_out = a_, _FADE
                else:
                    xi = min(max(xi, a_), b_)
                    if abs(xi - xs) < .05 and fade_in: xi = min(b_, xs + .12) if enter == "left" else max(a_, xs - .12)
            d = abs(xi - xs); te = float(p.get("enter_dur", d / speed if speed else 1.6))
            if cross: te = max(self.dur - float(p.get("exit_margin", .6)), .6)
            if self.iv and fade_in: te = max(te, .8)
            te = min(te, self.dur * .8) if not cross else te
            bb = dict(t0=0.0, t1=te, action="walk" if action not in ("run",) else "run", x0=xs, x1=xi, ap=dict(p.get("action") or {}), face=None, phase0=ph_acc, enter=True, cross=cross, fade_in=fade_in, fade_out=fade_out if cross else 0.0)
            if cross:
                bb["exit"] = False
                if lo and lo.get("phase") is not None:
                    gap_d = d / max(te, .1) * max(self.dur - te, 0.0); bb["phase1"] = float(lo["phase"]) - gap_d * W / max(bank.stride_ratio(bb["action"], bb["ap"]) * self.hout * H, 1.0)
            beats.insert(0, bb)
        if exit_ != "none" and not cross:
            beats.append(dict(t0=None, t1=None, action="run" if p.get("exit_action") == "run" else "walk", x0=None, x1=None, ap=dict(p.get("action") or {}), face=None, exit=True))
        # lay out in order
        out = []; prev = None; gone = False
        for i, b in enumerate(beats):
            if b.get("exit"):
                a = b["action"]; h_o = self.hout if lo else self.hmid; t_end = max(self.dur - float(p.get("exit_margin", .6)), (prev["t1"] if prev else 0) + .4)
                xe = 1 + self.margin(h_o) if exit_ == "right" else -self.margin(h_o); x0 = x_cur; b["fade_out"] = 0.0
                if self.iv:
                    a_, b_, ha_, hb_ = self.iv[self._snap(x_cur)[0]]
                    if exit_ == "right" and not hb_: xe, b["fade_out"] = max(b_, x0), _FADE
                    if exit_ == "left" and not ha_: xe, b["fade_out"] = min(a_, x0), _FADE
                d = abs(xe - x0)
                sp = float(lo.get("speed") or 0.0) or None; dur_e = d / sp if sp else float(p.get("exit_dur", 1.5)); dur_e = max(dur_e, .5)
                t0 = max(t_cur, t_end - dur_e); t0 = min(t0, t_end - .3)
                # leaving the side the character already is not on: walk through
                b.update(t0=t0, t1=t_end, x0=x0, x1=xe)
                if lo and lo.get("phase") is not None:
                    gap_d = (sp or d / max(t_end - t0, .1)) * max(self.dur - t_end, 0.0)
                    b["phase1"] = float(lo["phase"]) - gap_d * W / max(self.bank.stride_ratio(a, b["ap"]) * h_o * H, 1.0)
            else:
                b["t0"] = max(b["t0"], t_cur); b["t1"] = max(b["t1"], b["t0"] + .05)
                if b["action"] in _LOCO and b["action"] != "stop":
                    if b.get("x0") is None: b["x0"] = x_cur if not b.get("enter") else b["x0"]
                    if b.get("x1") is None: b["x1"] = (1 + self.margin(self.hmid)) if face == "right" else -self.margin(self.hmid)
                    b["x0"], b["x1"] = float(b["x0"]), float(b["x1"])
                    if self.iv and not b.get("enter"):
                        i_ = self._snap(b["x0"])[0]; a_, b_, ha_, hb_ = self.iv[i_]; x0_ = b["x0"]; b["fade_in"] = 0.0
                        if x0_ < 0 or x0_ > 1:    # starts off-frame: only on a hard lane end, else it appears at the end by fading in
                            if not (ha_ if x0_ < 0 else hb_): x0_ = a_ if x0_ < 0 else b_; b["fade_in"] = _FADE
                        else: x0_ = min(max(x0_, a_), b_)
                        b["x0"] = x0_; b["x1"], off_ = self._clampx(i_, b["x1"]); b["fade_out"] = _FADE if off_ else 0.0
                        if abs(b["x1"] - b["x0"]) < .004 and not b["fade_in"] and not b["fade_out"]: b["action"] = "stand_idle"
                else:
                    b["x0"] = float(b["x0"]) if b.get("x0") is not None else x_cur; b["x1"] = b["x0"]
                    if self.iv: b["x0"] = b["x1"] = self._snap(b["x0"])[1]
            if b["t0"] > t_cur + 1e-6: out.append(dict(kind="hold", t0=t_cur, t1=b["t0"], x=x_cur, face=face, action="stand_idle", ap={}, gone=gone))
            if b["action"] in _LOCO and b["action"] != "stop":
                face = b.get("face") or ("right" if b["x1"] >= b["x0"] else "left"); b["face"] = face; x_cur = b["x1"]
            else:
                face = b.get("face") or face; b["face"] = face
                if b["action"] == "turn": b["face_after"] = "left" if face == "right" else "right"
                x_cur = b["x0"]
            b["kind"] = "loco" if b["action"] in _LOCO else "stand"; out.append(b); t_cur = b["t1"]; prev = b; gone = bool(b.get("fade_out"))
        if t_cur < self.dur - 1e-6: out.append(dict(kind="hold", t0=t_cur, t1=self.dur + 1.0, x=x_cur, face=face, action="stand_idle", ap={}, gone=gone))
        elif out[-1]["kind"] != "hold": out.append(dict(kind="hold", t0=out[-1]["t1"], t1=self.dur + 1.0, x=x_cur, face=face, action="stand_idle", ap={}, gone=gone))
        if not out: out.append(dict(kind="hold", t0=0.0, t1=self.dur + 1.0, x=x_cur, face=face, action="stand_idle", ap={}, gone=gone))
        # auto decelerating stop after a locomotion beat that is followed by standing (not an exit, not off-screen)
        fin = []
        for i, b in enumerate(out):
            nxt = out[i + 1] if i + 1 < len(out) else None
            if b["kind"] == "loco" and b["action"] in ("walk", "run") and not b.get("enter") and (i == 0 or out[i - 1]["kind"] != "loco"): b["ease_in"] = True
            if (p.get("auto_stop", True) and b["kind"] == "loco" and b["action"] == "walk" and not b.get("exit") and not b.get("cross") and not b.get("fade_out") and nxt is not None and nxt["kind"] != "loco"
                    and -.02 < b["x1"] < 1.02 and (b["t1"] - b["t0"]) > 1.0 and "stop" in allowed):
                D = .9; trav = P.action_travel(bank.c, "stop", D, self.hmid * H / bank.ref, {"duration": D}) / W * (1 if b["x1"] >= b["x0"] else -1)
                tm = b["t1"] - D; xm = b["x1"] - trav
                b1 = dict(b, t1=tm, x1=xm); b2 = dict(kind="loco", t0=tm, t1=b["t1"], action="stop", x0=xm, x1=b["x1"], ap={"duration": D}, face=b["face"], stopcont=True)
                fin += [b1, b2]
            else: fin.append(b)
        self.segs = fin; self._phases()
        self.stride = lambda a, ap, h: max(self.bank.stride_ratio(a, ap) * h, 1.0)
        self.enter_end = next((0.0 if b.get("cross") else b["t1"] for b in self.segs if b.get("enter")), 0.0)
        self.exit_start = next((b["t0"] for b in self.segs if b.get("exit")), self.dur)

    def _snap(self, x, allow_off=False):
        """-> (interval index, x) nearest clear point of the lane (x unchanged without a lane)."""
        if not self.iv: return 0, x
        best = None
        for i, (a, b, _, _) in enumerate(self.iv):
            xc = min(max(x, a), b); d = abs(xc - x)
            if best is None or d < best[0] - 1e-9: best = (d, i, xc)
        return best[1], best[2]

    def _clampx(self, i, x):
        """Clamp x into interval i; (x', wanted_off_frame_on_a_soft_end). An off-frame x is kept only at a hard end."""
        a, b, ha, hb = self.iv[i]
        if x < a: return (x, False) if (ha and x < 0) else (a, x < 0)
        if x > b: return (x, False) if (hb and x > 1) else (b, x > 1)
        return x, False

    def _phases(self):
        """Assign phase0 / total phase advance to each locomotion segment (distance / stride, or anchored at both ends when links ask)."""
        acc = 0.0
        for b in self.segs:
            if b["kind"] != "loco": continue
            h = (self.hin if b.get("enter") else self.hout if b.get("exit") else self.hmid) * self.H
            st = max(self.bank.stride_ratio(b["action"], b["ap"]) * h, 1.0); d = abs(b["x1"] - b["x0"]) * self.W
            if b["action"] == "stop": b["ph0"] = (b.get("ap", {}).get("phase0")) if b.get("ap", {}).get("phase0") is not None else acc % 1.0; b["ap"] = dict(b["ap"], phase0=b["ph0"]); continue
            ph0 = b.get("phase0"); ph1 = b.get("phase1"); nat = d / st
            if (b.get("ap") or {}).get("phase0") is not None: ph0 = b["ap"]["phase0"]
            if (b.get("ap") or {}).get("phase1") is not None: ph1 = b["ap"]["phase1"]
            if ph0 is None: ph0 = acc if ph1 is None else ph1 - nat
            total = nat
            if ph1 is not None and (b.get("phase0") is not None or (b.get("ap") or {}).get("phase0") is not None):
                total = round(nat - ((ph1 - ph0) % 1.0)) + ((ph1 - ph0) % 1.0)
                total = max(total, nat * .6)
            b["ph0"], b["tot"] = ph0, total; acc = ph0 + total
        for b in self.segs:
            if b["kind"] == "loco" and b["action"] == "stop" and "ph0" not in b: b["ph0"] = 0.0

    def yh(self, t):
        a = self.enter_end; z = self.exit_start; r = max(min(1.0, (z - a) / 2), .2)
        y0, h0 = (self.yin, self.hin); y1, h1 = self.ymid, self.hmid; y2, h2 = self.yout, self.hout
        if t < a: y, h = y0, h0
        elif t < a + r: k = _ease((t - a) / r); y, h = y0 + (y1 - y0) * k, h0 + (h1 - h0) * k
        else: y, h = y1, h1
        if t > z - r: k = _ease((t - (z - r)) / r); y, h = y + (y2 - y) * k, h + (h2 - h) * k
        return y * self.H, h * self.H

    def _alpha(self, seg, t):
        if seg.get("gone"): return 0.0
        lt = t - seg["t0"]; D = max(seg["t1"] - seg["t0"], 1e-3); a = 1.0
        if seg.get("fade_in"): a *= _ease(lt / seg["fade_in"])
        if seg.get("fade_out"): fo = min(seg["fade_out"], D); a *= 1 - _ease((lt - (D - fo)) / fo)
        return a

    def state(self, t):
        idx = len(self.segs) - 1
        for k, s_ in enumerate(self.segs):
            if t < s_["t1"]: idx = k; break
        seg = self.segs[idx]; y, h = self.yh(t)
        st = self._eval(seg, t, y, h); st["alpha"] = self._alpha(seg, t); lt = t - seg["t0"]
        if idx > 0 and 0 <= lt < _JOIN and not seg.get("enter"):
            pv = self.segs[idx - 1]
            if pv["kind"] != seg["kind"] or (pv["kind"] == "stand" and pv["action"] != seg["action"]):
                if not pv.get("gone") and not (pv["kind"] == "hold" and seg["kind"] == "hold"):
                    ps = self._eval(pv, pv["t1"] - 1e-3, y, h); ps["alpha"] = self._alpha(pv, pv["t1"] - 1e-3)
                    st["prev"] = ps; st["w"] = _ease(lt / _JOIN)
        return st

    def _eval(self, seg, t, y, h):
        lt = max(t - seg["t0"], 0.0); W = self.W
        if seg["kind"] == "hold":
            return dict(x=seg["x"] * W, y=y, h=h, facing=seg["face"], action="stand_idle", ap={}, t=t, phase=None)
        if seg["kind"] == "stand":
            a = seg["action"]; D = seg["t1"] - seg["t0"]; ap = dict(seg["ap"])
            if a in _LOOP: tt = lt % max(self.P.action_duration(a, ap), .5) if a != "stand_idle" else t
            else:
                if "duration" not in ap: ap["duration"] = min(max(D, 1.2), 5.0) if a in ("point", "wave") else max(D, .5)
                lag = .2 if (a in _GESTURES and D > .9) else 0.0    # anticipation: hold the still pose briefly before the gesture starts
                tt = min(max(lt - lag, 0.0), ap["duration"])
            face = seg["face"] if not (a == "turn" and lt >= D) else seg["face_after"]
            return dict(x=seg["x0"] * W, y=y, h=h, facing=face, action=a, ap=ap, t=tt, phase=None)
        D = max(seg["t1"] - seg["t0"], 1e-3)
        if seg["action"] == "stop":
            trav = self.P.action_travel(self.bank.c, "stop", lt, h / self.bank.ref, seg["ap"]) / W * (1 if seg["face"] == "right" else -1)
            return dict(x=(seg["x0"] + trav) * W, y=y, h=h, facing=seg["face"], action="stop", ap=seg["ap"], t=min(lt, seg["ap"].get("duration", .9)), phase=None)
        if seg.get("ease_in") and D > .8:   # start from rest: speed ramps up linearly over T (distance fraction stays 0 -> 1)
            T = .3; u = min(((lt * lt / (2 * T)) if lt < T else (lt - T / 2)) / (D - T / 2), 1.0)
        else: u = min(lt / D, 1.0)
        x = seg["x0"] + (seg["x1"] - seg["x0"]) * u
        ph = seg["ph0"] + seg["tot"] * u
        return dict(x=x * W, y=y, h=h, facing=seg["face"], action=seg["action"], ap=seg["ap"], t=t, phase=ph)

def _tint_mul(tint):
    v = np.array([float(c) for c in tint][:3], np.float32)
    if v.size != 3: raise RenderError(f"tint must be 3 numbers, got {tint!r}")
    return v / 255.0 if v.max() > 2 else v

def _mul_rgb(rgba: Image.Image, mul) -> Image.Image:
    a = np.asarray(rgba, dtype=np.float32).copy(); a[..., :3] *= mul
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")

_TIMELINE_KEYS = ("beats", "enter", "exit", "link_in", "link_out")

# ---------------------------------------------------------------- ffmpeg sink
class _Sink:
    def __init__(self, size, fps, path):
        self.err = tempfile.TemporaryFile(); self.path = path
        cmd = [_ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{size[0]}x{size[1]}", "-r", str(fps), "-i", "-",
               "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart", path]
        try: self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=self.err)
        except OSError as e:
            self.err.close(); raise RenderError(f"cannot start ffmpeg: {e}") from e
    def write(self, b: bytes):
        try: self.p.stdin.write(b)
        except (BrokenPipeError, OSError) as e: raise RenderError(f"ffmpeg stopped early: {self._msg()}") from e
    def _msg(self) -> str:
        try: self.err.seek(0); return self.err.read().decode("utf8", "replace").strip()[-600:]
        except Exception: return ""
    def close(self):
        try:
            if self.p.stdin and not self.p.stdin.closed: self.p.stdin.close()
        except OSError: pass
        rc = self.p.wait(); msg = self._msg(); self.err.close()
        if rc != 0: raise RenderError(f"ffmpeg failed ({rc}): {msg}")
    def abort(self):
        try: self.p.kill()
        except Exception: pass
        try:
            if self.p.stdin: self.p.stdin.close()
        except Exception: pass
        try: self.p.wait(timeout=5)
        except Exception: pass
        try: self.err.close()
        except Exception: pass

def _produce(out_path, key_parts, size, fps, nframes, make_frame, cancel, progress):
    """Cache lookup -> render into a temp file -> atomic rename -> copy to out_path."""
    key = _key(**key_parts); CLIP_DIR.mkdir(parents=True, exist_ok=True); cached = CLIP_DIR / f"{key}.mp4"
    out_path = str(out_path); os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    if not cached.exists() or cached.stat().st_size == 0:
        fd, tmp = tempfile.mkstemp(dir=CLIP_DIR, suffix=".part.mp4"); os.close(fd)
        sink = _Sink(size, fps, tmp)
        try:
            for i in range(nframes):
                if cancel and cancel(): raise Cancelled("render cancelled")
                sink.write(make_frame(i)); 
                if progress: progress((i + 1) / nframes)
            sink.close(); os.replace(tmp, cached)
        except BaseException:
            sink.abort()
            try: os.unlink(tmp)
            except OSError: pass
            raise
    fd, tmp2 = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(out_path)), suffix=".part")
    os.close(fd)
    try: shutil.copyfile(cached, tmp2); os.replace(tmp2, out_path)
    except BaseException:
        try: os.unlink(tmp2)
        except OSError: pass
        raise
    return out_path

# ---------------------------------------------------------------- public
def _render_timeline(still_path, character, action, out_path, duration, fps, direction, size, p, cancel, progress, P):
    sc = _analyse(still_path); W, H = size
    occ_mode = p.get("occluders", "auto"); shapes = occ_mode if isinstance(occ_mode, (list, tuple)) else None
    fit = sc.fit(size, 1.0, shapes=shapes, auto_occ=(occ_mode != "off"))
    if isinstance(p.get("lane"), str): raise RenderError("no usable lane")
    tint = p.get("tint"); bank = SpriteBank(P, character, tint)
    tmul = None if (tint in (None, "auto") or bank.tint_kw) else _tint_mul(tint)
    oc = np.asarray(fit.occ, dtype=np.float32) / 255.0
    def cover(a, b):    # is the span hidden by a foreground occluder at the character's body height? then the character can walk behind it
        yy = p.get("y", (p.get("lane") or {}).get("y") or sc.walk_y); x0_, x1_ = int(max(a, 0) * W), int(min(b, 1) * W)
        if x1_ <= x0_: return False
        return float(oc[int((yy - .25) * H):int(yy * H), x0_:x1_].mean()) > .5
    tl = Timeline(P, bank, dict(p, _occ_cover=cover), duration, size, sc.walk_y, sc.horizon, action, direction)
    n = max(1, int(round(duration * fps))); zamp = float(p.get("zoom", .04)); zamp = max(zamp - 1, 0.0) if zamp > .5 else zamp
    wp = effects.Warper(size, p.get("boil", 2.2), seed=p.get("seed", 7)); post = effects.Post(size, seed=p.get("seed", 7) + 4, grain=p.get("grain", 4.0), dust=p.get("dust", 40))
    key = dict(kind="shot2", still=_file_hash(still_path), character=character, action=action, duration=duration, fps=fps, direction=direction, size=size, params={k: v for k, v in p.items()})
    cx, cy = W / 2, H / 2; light = fit.scene.light; has_occ = bool(fit.occ.getbbox())

    def frame(i):
        t = i / fps; u = i / max(n - 1, 1); z = 1 + zamp * math.sin(math.pi * u)
        sx, sy = wp.source(t, z, (0, 0), fit.depth, (8 * math.sin(2 * math.pi * u), 0))
        img = wp.warp(fit.rgb, sx, sy); occ = wp.warp(fit.occ, sx, sy) if has_occ else None
        s = tl.state(t); r = np.random.default_rng(p.get("seed", 7) * 1000 + int(t * 10)); jit = (r.uniform(-1, 1) * 1.1 * W / 1920, r.uniform(-1, 1) * .8 * W / 1920)
        def draw(st, alpha, shadow=True):
            if alpha <= .003: return
            x, y_, h_ = (st["x"] - cx) * z + cx, (st["y"] - cy) * z + cy, st["h"] * z
            if x < -h_ or x > W + h_: return
            sp, (ax, ay) = bank.get(st["action"], st["ap"], h_, st["t"], st["phase"], st["facing"])
            sp = scene.tint_character(sp, light)
            if tmul is not None: sp = _mul_rgb(sp, tmul)
            fx, fy = x + jit[0], y_ + jit[1]
            if shadow:
                bw, bh = int(h_ * 1.4), int(h_ * .34)
                sh = scene.ground_shadow((bw, bh), (bw / 2, bh / 2), h_, light)
                _over(img, sh, (int(fx - bw / 2), int(fy - bh / 2)), occ, alpha)
            _over(img, sp, (int(round(fx - ax)), int(round(fy - ay))), occ, alpha)
        if "prev" in s:
            pv = s["prev"]; draw(pv, pv["alpha"]); draw(s, s["alpha"] * s["w"])
        else: draw(s, s["alpha"])
        return post.apply(img, t, i).tobytes()
    out = _produce(out_path, key, size, fps, n, frame, cancel, progress)
    return out

def render_shot(still_path, character, action, out_path, duration=5.0, fps=30, direction="right", size=(1920, 1080), params=None, cancel=None, progress=None):
    P = _puppet(); size = tuple(int(v) for v in size); p = dict(params or {}); cancel = cancel or p.pop("cancel", None); progress = progress or p.pop("progress", None)
    _check(character, action, duration, fps, size, direction, P)
    if isinstance(p.get("lane"), str): raise RenderError("no usable lane")
    if any(k in p for k in _TIMELINE_KEYS): return _render_timeline(still_path, character, action, out_path, duration, fps, direction, size, p, cancel, progress, P)
    sc = _analyse(still_path); W, H = size
    occ_mode = p.get("occluders", "auto")
    shapes = occ_mode if isinstance(occ_mode, (list, tuple)) else None
    fit = sc.fit(size, 1.0, shapes=shapes, auto_occ=(occ_mode != "off"))
    if direction == "left": fit = transitions.mirror_fit(fit)
    sprites = Sprites(P, character, action, p.get("action"))
    loco = action in ("walk", "run")
    ch0 = p.get("char_h", .44) * H; z1 = float(p.get("zoom", 1.05)); n = max(1, int(round(duration * fps)))
    y0 = p.get("y", fit.scene.walk_y) * H; y1 = p.get("y1", p.get("y", fit.scene.walk_y)) * H
    xa, xb = (p.get("x0", -.14) * W, p.get("x1", 1.14) * W) if loco else (p.get("x", .5) * W,) * 2
    wp = effects.Warper(size, p.get("boil", 2.2), seed=p.get("seed", 7)); post = effects.Post(size, seed=p.get("seed", 7) + 4, grain=p.get("grain", 4.0), dust=p.get("dust", 40))
    # perspective-scaled height along the path and cumulative gait phase (distance / stride)
    ys = np.linspace(y0, y1, n + 1); xs = np.linspace(xa, xb, n + 1); hs = ch0 * np.array([fit.scene.scale_at(y / H) for y in ys])
    ph = np.concatenate([[0], np.cumsum(np.hypot(np.diff(xs), np.diff(ys)) / (sprites.stride_ratio() * (hs[1:] + hs[:-1]) / 2))]) if loco else np.zeros(n + 1)
    key = dict(kind="shot", still=_file_hash(still_path), character=character, action=action, duration=duration, fps=fps, direction=direction, size=size, params={k: v for k, v in p.items()})

    def frame(i):
        t = i / fps; u = i / max(n - 1, 1); z = 1 + (z1 - 1) * u * 1.0 + .04
        sx, sy = wp.source(t, z, (0, 0), fit.depth, (12 * (u - .5), 0))
        img = wp.warp(fit.rgb, sx, sy); occ = wp.warp(fit.occ, sx, sy) if fit.occ.getbbox() else None
        cx, cy = W / 2, H / 2
        light = fit.scene.light
        ch = dict(x=(xs[i] - cx) * z + cx, y=(ys[i] - cy) * z + cy, h=hs[i] * z, alpha=1.0, phase=float(ph[i]) if loco else None)
        r = np.random.default_rng(p.get("seed", 7) * 1000 + int(t * 10)); jit = (r.uniform(-1, 1) * 1.1 * W / 1920, r.uniform(-1, 1) * .8 * W / 1920)
        _place(P, img, occ, sprites, t, ch, light, jit)
        a = post.apply(img, t, i)
        return (a[:, ::-1] if direction == "left" else a).tobytes()
    return _produce(out_path, key, size, fps, n, frame, cancel, progress)

def render_transition(still_a, still_b, character, transition, out_path, duration, fps=30, size=(1920, 1080), direction="right", params=None, cancel=None, progress=None):
    P = _puppet(); size = tuple(int(v) for v in size); p = dict(params or {}); cancel = cancel or p.pop("cancel", None); progress = progress or p.pop("progress", None)
    action = p.get("action_name", "walk")
    _check(character, action, duration, fps, size, direction, P)
    if transition not in transitions.TRANSITIONS: raise RenderError(f"unknown transition {transition!r}; choose from {transitions.list_transitions()}")
    W, H = size
    fa, fb = _analyse(still_a).fit(size), _analyse(still_b).fit(size)
    if p.get("occluders") == "off": fa.occ, fb.occ = Image.new("L", size, 0), Image.new("L", size, 0)
    if direction == "left": fa, fb = transitions.mirror_fit(fa), transitions.mirror_fit(fb)
    sprites = Sprites(P, character, action, p.get("action"))
    tp = dict(p); tp.setdefault("stride_ratio", sprites.stride_ratio())
    tr = transitions.make(transition, fa, fb, size, tp, seed=int(p.get("seed", 5)))
    n = max(1, int(round(duration * fps)))
    wp = effects.Warper(size, p.get("boil", 2.2), seed=p.get("seed", 7)); post = effects.Post(size, seed=p.get("seed", 7) + 4, grain=p.get("grain", 4.0), dust=p.get("dust", 40))
    key = dict(kind="transition", a=_file_hash(still_a), b=_file_hash(still_b), character=character, transition=transition, duration=duration, fps=fps, direction=direction, size=size, params=p)

    def frame(i):
        t = i / fps; u = i / max(n - 1, 1); tf = tr.frame(u)
        sx, sy = wp.source(t, tf.zoom, tf.pan, tf.depth, tf.par)
        img = wp.warp(tf.img, sx, sy); occ = wp.warp(tf.occ, sx, sy) if tf.occ is not None and tf.occ.getbbox() else None
        light = transitions.mix_light(fa.scene.light, fb.scene.light, tf.light_w)
        r = np.random.default_rng(p.get("seed", 7) * 1000 + int(t * 10)); jit = (r.uniform(-1, 1) * 1.1 * W / 1920, r.uniform(-1, 1) * .8 * W / 1920)
        _place(P, img, occ, sprites, t, tf.char, light, jit)
        a = post.apply(img, t, i, dark=tf.dark, dark_xy=tf.dark_xy, fade=tf.fade)
        return (a[:, ::-1] if direction == "left" else a).tobytes()
    return _produce(out_path, key, size, fps, n, frame, cancel, progress)
