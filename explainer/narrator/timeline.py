"""Frame-based narrator timeline: what the narrator looks like on every clip frame, where it is, and the exact box it can ever cover.
Spec: docs/explainer/explainer_cue_schema_v1_1.md. Everything is a function of the clip frame number and the cue frames; nothing reads a clock, nothing uses
random or hash(). Imports nothing from the application and nothing from explainer.board (the board package imports this one)."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import rig

POSES = ("idle", "point", "surprise", "think", "shrug", "explain")
SIDES = ("left", "right")
ACTIONS = ("show", "pose", "hide")
MOTIONS = ("slide", "none")
ENTER_FRAMES, EXIT_FRAMES, FADE_FRAMES = 12, 12, 4
START_VISIBLE_PX = 40
BOB_PERIOD, BOB_AMP = 90, 3
BOB = [0, 0, 0, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 2, 2, 2, 2, 2, 2, 2, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, -1, -1, -1, -1, -1, -2, -2, -2, -2, -2, -2, -2, -3, -3, -3, -3, -3, -3, -3, -3, -3, -3, -3, -3, -3, -3, -3, -3, -2, -2, -2, -2, -2, -2, -2, -1, -1, -1, -1, -1, 0, 0]
BLINK_FRAMES, BLINK_MIN_GAP, BLINK_SPREAD = 4, 75, 61
MOUTH_PERIOD, MOUTH_BRIDGE = 6, 4
MOUTH_SHAPES = ("open", "o", "wide")
FRAME_W, FRAME_H = 1920, 1080
ZONE = {"left": (96, 640), "right": (1280, 1824)}
BOTTOM_SCREEN_Y = 981         # the lowest opaque pixel of any pose sits here before bob; + bob (3) = 984, the bottom safe line
SCALE_MIN, SCALE_MAX = 0.45, 1.0
Rect = Tuple[float, float, float, float]

assert len(BOB) == BOB_PERIOD and all(abs(abs(BOB_AMP * math.sin(2 * math.pi * i / BOB_PERIOD)) % 1 - 0.5) > 1e-6 for i in range(BOB_PERIOD)), "bob table must have no rounding ties"


@dataclass
class Event:
    frame: int
    action: str
    cue_id: str
    pose: str = ""
    scale_pct: int = 100
    side: str = "left"
    enter: str = "slide"
    exit: str = "slide"


@dataclass
class Layer:
    pose: str
    scale_pct: int
    alpha_q: int      # 4 = opaque; 1..3 = cross-fade steps
    x: int
    y: int


@dataclass
class State:
    layers: List[Layer]
    eyes: str
    mouth: str
    side: str


def ease(k: float) -> float:
    k = max(0.0, min(1.0, k))
    return 1 - (1 - k) ** 3


def blink_starts(beat_id: str, first_frame: int, last_frame: int) -> List[int]:
    h = hashlib.sha256(f"{beat_id}|narrator|blink".encode("utf-8")).digest()
    out, f = [], first_frame
    while True:
        f += BLINK_MIN_GAP + int.from_bytes(h[:2], "big") % BLINK_SPREAD
        if f > last_frame:
            return out
        out.append(f)
        h = hashlib.sha256(h).digest()


def speech_runs(words_frames: Sequence[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """[first frame, end frame) of each speech run: a word covers its frames; runs at most MOUTH_BRIDGE frames apart are merged."""
    runs: List[List[int]] = []
    for s, e in sorted(words_frames):
        e = max(e, s + 1)
        if runs and s - runs[-1][1] <= MOUTH_BRIDGE:
            runs[-1][1] = max(runs[-1][1], e)
        else:
            runs.append([s, e])
    return [(a, b) for a, b in runs]


class NarratorTrack:
    def __init__(self, events: List[Event], words_frames: Sequence[Tuple[int, int]], clip_frames: int, beat_id: str):
        self.assets = rig.load_assets()
        self.events = events
        self.clip_frames = clip_frames
        self.beat_id = beat_id
        self.show = events[0]
        self.poses = [e for e in events if e.action in ("show", "pose")]
        self.hide = next((e for e in events if e.action == "hide"), None)
        self.side = self.show.side
        self.flip = self.side == "right"
        self.runs = speech_runs(words_frames)
        self.f_first = self.show.frame
        self.f_end = (self.hide.frame + (EXIT_FRAMES if self.hide.exit == "slide" else 0)) if self.hide else None
        last = self.f_end if self.f_end is not None else clip_frames
        self.blinks = blink_starts(beat_id, self.f_first, last)
        m = self.assets.manifest
        self.bbox = {p: tuple(m["poses"][p]["bbox"]) for p in m["poses"]}
        self.canvas = rig.canvas_size()
        self.uy1 = max(b[3] for b in self.bbox.values())      # lowest opaque row of any pose (design px at scale 1)
        self._bounds: Optional[Tuple[Rect, Rect]] = None

    # ---- per-frame definitions ----
    def settled_xy(self, scale_pct: int) -> Tuple[int, int]:
        z0, z1 = ZONE[self.side]
        s = scale_pct / 100.0
        return round((z0 + z1) / 2 - self.canvas[0] * s / 2), round(BOTTOM_SCREEN_Y - self.uy1 * s)

    def start_x(self, scale_pct: int, pose: str) -> int:
        """x of the sprite when only START_VISIBLE_PX px of this pose's outline are inside the frame edge it slides over."""
        s = scale_pct / 100.0
        x1 = self.bbox[pose][2]
        if self.side == "left":
            return round(START_VISIBLE_PX - x1 * s)
        return round(FRAME_W - START_VISIBLE_PX - (self.canvas[0] - x1) * s)

    def _pose_at(self, n: int) -> Tuple[Event, Optional[Event]]:
        j = max(i for i, e in enumerate(self.poses) if e.frame <= n)
        cur = self.poses[j]
        prev = self.poses[j - 1] if j > 0 and n < cur.frame + FADE_FRAMES else None
        return cur, prev

    def mouth_at(self, n: int) -> str:
        for a, b in self.runs:
            if a <= n < b:
                i = n - a
                return "closed" if i % MOUTH_PERIOD >= MOUTH_PERIOD // 2 else MOUTH_SHAPES[(i // MOUTH_PERIOD) % len(MOUTH_SHAPES)]
        return "closed"

    def eyes_at(self, n: int, pose: str) -> str:
        if pose == "explain":
            return "happy"
        if any(b <= n < b + BLINK_FRAMES for b in self.blinks):
            return "blink"
        return "open"

    def state(self, n: int) -> Optional[State]:
        if n < self.f_first:
            return None
        if self.hide is not None:
            if self.hide.exit == "slide" and n >= self.hide.frame + EXIT_FRAMES:
                return None
            if self.hide.exit == "none" and n >= self.hide.frame:
                return None
        cur, prev = self._pose_at(n)
        bob = BOB[(n - self.f_first) % BOB_PERIOD]
        x_fin, y_fin = self.settled_xy(cur.scale_pct)
        x = x_fin
        if self.show.enter == "slide" and n < self.f_first + ENTER_FRAMES:
            xs = self.start_x(cur.scale_pct, cur.pose)
            x = round(xs + (x_fin - xs) * ease((n - self.f_first) / ENTER_FRAMES))                # ease-out cubic, k = 0 on the first frame
        elif self.hide is not None and self.hide.exit == "slide" and n >= self.hide.frame:
            xs = self.start_x(cur.scale_pct, cur.pose)
            p = (n - self.hide.frame + 1) / EXIT_FRAMES
            x = round(x_fin + (xs - x_fin) * p * p)                                                 # ease-in quadratic, p = 1 / 12 on the first frame
        layers: List[Layer] = []
        if prev is not None:
            px, py = self.settled_xy(prev.scale_pct)
            layers.append(Layer(prev.pose, prev.scale_pct, 4, px, py + bob))
            layers.append(Layer(cur.pose, cur.scale_pct, n - cur.frame + 1, x_fin, y_fin + bob))
        else:
            layers.append(Layer(cur.pose, cur.scale_pct, 4, x, y_fin + bob))
        return State(layers, self.eyes_at(n, cur.pose), self.mouth_at(n), self.side)

    def layer_rect(self, ly: Layer) -> Rect:
        b = self.bbox[ly.pose]
        s = ly.scale_pct / 100.0
        x0, x1 = (self.canvas[0] - b[2], self.canvas[0] - b[0]) if self.flip else (b[0], b[2])
        return (ly.x + x0 * s, ly.y + b[1] * s, ly.x + x1 * s, ly.y + b[3] * s)

    def frame_rect(self, n: int) -> Optional[Rect]:
        st = self.state(n)
        if st is None:
            return None
        rs = [self.layer_rect(l) for l in st.layers]
        return (min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs))

    def bounds(self) -> Tuple[Rect, Rect]:
        """(collision box over every frame on screen, box over the settled frames only), each grown by 2 px for anti-aliasing."""
        if self._bounds is None:
            last = self.f_end if self.f_end is not None else self.clip_frames
            allr, setr = [], []
            for n in range(self.f_first, last):
                r = self.frame_rect(n)
                if r is None:
                    continue
                allr.append(r)
                slide_in = self.show.enter == "slide" and n < self.f_first + ENTER_FRAMES
                slide_out = self.hide is not None and self.hide.exit == "slide" and n >= self.hide.frame
                if not slide_in and not slide_out:
                    setr.append(r)
            u = lambda rs: (min(r[0] for r in rs) - 2, min(r[1] for r in rs) - 2, max(r[2] for r in rs) + 2, max(r[3] for r in rs) + 2) if rs else (0, 0, 0, 0)
            self._bounds = (u(allr), u(setr))
        return self._bounds

    def draw(self, im, n: int, mouth: Optional[str] = None, eyes: Optional[str] = None) -> None:
        """Paste the narrator for clip frame n. mouth / eyes override the scheduled face (used only by the verification's template matching)."""
        st = self.state(n)
        if st is None:
            return
        em, ee = mouth or st.mouth, eyes or st.eyes
        for ly in st.layers:
            sp = rig.sprite(ly.pose, ee, em, ly.scale_pct, self.flip) if ly.alpha_q >= 4 else rig.faded(ly.pose, ee, em, ly.scale_pct, self.flip, ly.alpha_q)
            im.paste(sp, (ly.x, ly.y), sp)

    def summary(self) -> Dict[str, Any]:
        allb, setb = self.bounds()
        return {"asset_id": self.assets.manifest["asset_id"], "assets_manifest_sha256": self.assets.manifest_sha256, "side": self.side,
                "events": [{"cue": e.cue_id, "frame": e.frame, "action": e.action, "pose": e.pose, "scale_pct": e.scale_pct} for e in self.events],
                "visible_from_frame": self.f_first, "gone_from_frame": self.f_end, "blink_start_frames": self.blinks, "speech_runs": [list(r) for r in self.runs],
                "collision_box": [round(v, 1) for v in allb], "settled_box": [round(v, 1) for v in setb]}


def _frame(t: float, fps: int) -> int:
    return int(math.ceil(t * fps - 1e-9))


def build_track(resolved, words, clip_origin: float, clip_length: float, fps: int, beat_id: str, tail_frames: int = 0) -> Optional[NarratorTrack]:
    """Check the narrator cues of one beat and build its track. Problems are added to the cues (never raised); None when there is nothing valid to draw.
    `resolved` are explainer.board.cues.ResolvedCue objects; `words` the (text, start, end) list in narration seconds."""
    cues = [r for r in resolved if r.cue.kind == "narrator" and not r.problems and r.first_frame is not None]
    if not cues:
        return None
    try:
        rig.load_assets()
    except rig.AssetError as e:
        for r in cues:
            r.problems.append(f"cue {r.cue.id}: narrator assets unavailable: {e}")
        return None
    events: List[Event] = []
    for r in sorted(cues, key=lambda r: (r.first_frame, [x.cue.id for x in resolved].index(r.cue.id))):
        p = r.cue.params or {}
        act = p.get("action")
        if act not in ACTIONS:
            r.problems.append(f"cue {r.cue.id}: params.action must be one of {', '.join(ACTIONS)}")
            continue
        ev = Event(r.first_frame, act, r.cue.id)
        if act in ("show", "pose"):
            pose = p.get("pose", events[-1].pose if events and act == "pose" else "idle")
            if pose not in POSES:
                r.problems.append(f"cue {r.cue.id}: unknown pose {pose!r} (use {', '.join(POSES)})")
                continue
            sc = p.get("scale", (events[-1].scale_pct / 100.0) if events and act == "pose" else 1.0)
            if not isinstance(sc, (int, float)) or not (SCALE_MIN - 1e-9 <= sc <= SCALE_MAX + 1e-9):
                r.problems.append(f"cue {r.cue.id}: scale must be between {SCALE_MIN} and {SCALE_MAX}")
                continue
            ev.pose, ev.scale_pct = pose, int(round(sc * 100))
        if act == "show":
            side, enter = p.get("side", "left"), p.get("enter", "slide")
            if side not in SIDES or enter not in MOTIONS:
                r.problems.append(f"cue {r.cue.id}: side must be left or right and enter slide or none")
                continue
            ev.side, ev.enter = side, enter
        if act == "hide":
            ex = p.get("exit", "slide")
            if ex not in MOTIONS:
                r.problems.append(f"cue {r.cue.id}: exit must be slide or none")
                continue
            ev.exit = ex
        # state machine
        shown = bool(events) and not any(e.action == "hide" for e in events)
        if act == "show" and events:
            r.problems.append(f"cue {r.cue.id}: the narrator is already shown or was shown earlier in this beat (one show per beat)")
            continue
        if act != "show" and not events:
            r.problems.append(f"cue {r.cue.id}: {act} before any show: the narrator is not on screen")
            continue
        if act != "show" and not shown:
            r.problems.append(f"cue {r.cue.id}: {act} after the narrator left")
            continue
        first = events[0] if events else ev
        if act in ("pose", "hide"):
            if first.enter == "slide" and ev.frame < first.frame + ENTER_FRAMES:
                r.problems.append(f"cue {r.cue.id}: {act} at frame {ev.frame}, during the enter slide (frames {first.frame} to {first.frame + ENTER_FRAMES - 1})")
                continue
            last_pose = [e for e in events if e.action in ("show", "pose")][-1]
            if last_pose is not first and ev.frame < last_pose.frame + FADE_FRAMES:
                r.problems.append(f"cue {r.cue.id}: {act} at frame {ev.frame}, during the previous pose change (needs {FADE_FRAMES} frames)")
                continue
        if act == "pose":
            ev.side = first.side
        events.append(ev)
    if not events or events[0].action != "show":
        return None
    wf = [(_frame(s - clip_origin, fps), _frame(e - clip_origin, fps)) for _w, s, e in words if e - clip_origin > 0 and s - clip_origin < clip_length]
    return NarratorTrack(events, [(max(0, a), b) for a, b in wf], int(round(clip_length * fps)) + max(0, int(tail_frames)), beat_id)
