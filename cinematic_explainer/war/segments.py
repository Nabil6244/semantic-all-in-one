"""Bounded-memory, segment-compatible renderer for the War Documentary style (isolated: reads Phase 1 constants, edits nothing).

One ffmpeg process per shot piece (a shot, or a 10 s piece of a long shot, never cutting through a card or a dim ramp). The dimmed plate
comes from a second decode of the same clip, so no filter branch ever waits for another (the Phase 1 single graph queued every clear frame
before its first dim span: 2.5 GB at 25 s). Card frames are drawn in Python with GLOBAL time and piped in as RGBA, so a card is the same
pixels whichever segment draws it. Pieces are joined with the concat demuxer (-c copy); audio is attached once at the end.

Measured fixes (agent R, lossless): setparams bt709/tv after setsar=1 on every clip (the Phase 1 graph silently re-tagged and darkened the
bt709 clips), and format=yuva420p before the last overlay when a piece has no dim span, so segments equal the single-graph frames.

    render_segmented(shots, layers, out_path, *, audio_path=None, state_dir=None, cancel_check=None, progress_cb=None) -> dict

FOOTAGE TREATMENT (optional, per shot; a shot without it renders exactly as before)
    Shot.treat = {"motion": "push_in" | "push_out" | "pan_left" | "pan_right" | "none",   # slow camera move over the whole shot
                  "z0": 1.0, "z1": 1.06,         # zoom at the start / end of the shot (clamped to 1.0..1.08; 1.0..1.03 for sources under 540 px high)
                  "grade": "cold" | "warm_archive" | "neutral",
                  "vignette": 0..1,              # 0 = none (0.85 is about the dim plates' own vignette)
                  "grain": 0..1,                 # fine deterministic noise (0.5 = noise strength 6)
                  "blur_fill": "auto" | True | False}   # contained foreground over a blurred copy instead of a centre crop (auto: only for odd aspects)
    Shot.dissolve_in = seconds (0 = hard cut): the previous shot's clip fades out under this shot's first frames, inside the first piece of the shot.
    The treatment is applied identically to the clear clip and every dim plate (the cross-fade stays seamless), zoom is one continuous
    eased curve over the whole shot even when the shot is cut into 10 s pieces, and it is part of the segment cache key.
    Non-16:9 sources (4:3, portrait, ultra-wide) get blur-fill by default (blur_fill "auto" works with no treat dict at all).
"""

from __future__ import annotations

import concurrent.futures as cf
import dataclasses
import hashlib
import json
import logging
import math
import os
import shutil
import subprocess
import tempfile
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .. import look as L
from ..render import Layer, Shot, dim_spans
from .. import cards as _phase1_cards

log = logging.getLogger("cinematic_explainer.war.segments")

W, H, FPS = L.W, L.H, L.FPS
PIECE_S = 10.0                      # longest piece of a long shot
MAX_INPUTS = 8                      # clip decodes per piece: 1 clear + one per dim span
PACK_VERSION = "war-seg-1"
REUSE_BYTES = False                 # an unchanged card frame re-sends the previous bytes object
GOP = 50                            # closed GOP, a keyframe every 2 s and at every piece start
CRF = 20
TAG = "setsar=1,setparams=colorspace=bt709:range=tv:color_primaries=bt709:color_trc=bt709"


class RenderError(RuntimeError):
    """A segment could not be rendered (ffmpeg text included)."""


class RenderCancelled(RuntimeError):
    """cancel_check returned True."""


class MissingInput(RenderError):
    """A footage file named by a shot does not exist."""


# --------------------------------------------------------------------------- planning
def _frame(t: float) -> int:
    return int(round(t * FPS))


@dataclasses.dataclass(frozen=True)
class Piece:
    index: int
    path: str
    f0: int              # first global frame
    f1: int              # one past the last global frame
    seek: float          # seconds into the clip where this piece starts
    treat: Optional[str] = None        # canonical JSON of the shot's treatment plus its global frame span (see _shot_treat); None = untreated
    dissolve: float = 0.0              # seconds of cross-fade from the previous shot at the start of this piece
    prev_path: str = ""
    prev_seek: float = 0.0
    prev_treat: Optional[str] = None

    @property
    def frames(self) -> int:
        return self.f1 - self.f0

    @property
    def start(self) -> float:
        return self.f0 / FPS

    @property
    def end(self) -> float:
        return self.f1 / FPS


def _protected(layers: Sequence[Layer]) -> List[Tuple[float, float]]:
    """Intervals a cut must never fall inside: every layer, and every dim ramp (merged span widened by the ramp)."""
    spans = [(ly.start, ly.end) for ly in layers]
    spans += [(a - L.DIM_IN_S, b + L.DIM_IN_S) for a, b in dim_spans(layers)]
    return spans


def plan_pieces(shots: Sequence[Shot], layers: Sequence[Layer]) -> List[Piece]:
    """Frame-exact pieces: boundaries are whole frames, shot i ends where shot i+1 starts, long shots split at PIECE_S without cutting a card."""
    prot = _protected(layers)
    pieces: List[Piece] = []
    # One continuous timeline from frame 0 to the last shot's end. A planner may hand over shots that overlap (a scene's picture starts 0.2 s
    # before its first word while the previous scene runs to the word) or leave the start at 0.4 s: rendering each shot over its own
    # [start, end) would repeat those frames and shift every later card against the narration (audio starts at 0). So shot i runs from its own
    # start to the next shot's start; the first shot starts at frame 0; a gap is absorbed by the shot before it.
    live = [s for s in shots if _frame(s.end) > _frame(s.start)]
    if not live:
        return pieces
    starts = [_frame(s.start) for s in live]
    bounds = [0]
    for i in range(1, len(live)):
        bounds.append(max(starts[i], bounds[-1] + 1))
    bounds.append(max(_frame(live[-1].end), bounds[-1] + 1))
    prev: Optional[Tuple[str, float, Optional[str], int]] = None      # (path, seek at its first frame, treatment, first frame) of the shot before
    for i, s in enumerate(live):
        f0, f1 = bounds[i], bounds[i + 1]
        if f1 <= f0:
            continue
        # the clip position at f0: unchanged when the shot starts where planned; later when an overlap pushed its start forward
        s = dataclasses.replace(s, seek=s.seek + max(0, f0 - starts[i]) / FPS)
        tr = _shot_treat(s, f0, f1)
        extra: Dict[str, Any] = {}
        d_in = float(getattr(s, "dissolve_in", 0.0) or 0.0)
        if d_in > 0 and prev is not None:        # the first piece of the shot fades the previous clip out under its first frames
            extra = {"dissolve": min(d_in, (f1 - f0) / FPS / 2), "prev_path": prev[0], "prev_seek": prev[1] + (f0 - prev[3]) / FPS, "prev_treat": prev[2]}
        cut_from = f0
        while (f1 - cut_from) / FPS > PIECE_S + 1.0:
            target = (cut_from + int(PIECE_S * FPS)) / FPS
            for a, b in prot:                       # move a cut out of any protected interval (later, so the piece only grows)
                if a < target < b:
                    target = b
            cut = _frame(target)
            if cut >= f1 - FPS // 2 or cut <= cut_from:
                break
            pieces.append(Piece(len(pieces), s.path, cut_from, cut, s.seek + (cut_from - f0) / FPS, tr, **(extra if cut_from == f0 else {})))
            cut_from = cut
        pieces.append(Piece(len(pieces), s.path, cut_from, f1, s.seek + (cut_from - f0) / FPS, tr, **(extra if cut_from == f0 else {})))
        prev = (s.path, s.seek, tr, f0)
    return pieces


# --------------------------------------------------------------------------- cards
def all_cards() -> Dict[str, Callable]:
    """War cards and maps when their modules exist, else only the Phase 1 kinds (lazy: nothing is imported until a render)."""
    try:
        from . import registry  # type: ignore

        return dict(registry.all_cards())
    except Exception:
        return dict(_phase1_cards.CARDS)


def _compose(t: float, active: Sequence[Layer], cards: Dict[str, Callable], on_error: Callable[[Layer, Exception], None]):
    from PIL import Image

    img = L.blank()
    for ly in active:
        fn = cards.get(ly.kind)
        if fn is None:
            continue
        try:
            out = fn(t - ly.start, ly.end - ly.start, ly.params)
        except Exception as exc:       # one broken card never stops the render
            on_error(ly, exc)
            continue
        if out is not None:
            img = Image.alpha_composite(img, out)
    return img


# --------------------------------------------------------------------------- probing
@lru_cache(maxsize=256)
def _color_tags(path: str) -> Tuple[str, str]:
    """(colour space, range) as tagged in the file; '' when untagged."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=color_space,color_range",
                            "-of", "default=nw=1:nk=0", path], capture_output=True, text=True, timeout=30)
        d = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
        return d.get("color_space", "") if d.get("color_space") != "unknown" else "", d.get("color_range", "") if d.get("color_range") != "unknown" else ""
    except Exception:
        return "", ""


@lru_cache(maxsize=256)
def clip_duration(path: str) -> float:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                           capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def _scale_args(path: str) -> str:
    """Untagged and bt709 clips are only re-labelled (what Phase 1 pixels need); a bt601 / bt2020 clip is converted properly."""
    cs, rng = _color_tags(path)
    extra = ""
    if cs in ("smpte170m", "bt470bg", "smpte240m"):
        extra = ":in_color_matrix=bt601:out_color_matrix=bt709"
    elif cs.startswith("bt2020"):
        extra = ":in_color_matrix=bt2020:out_color_matrix=bt709"
    if rng == "pc":
        extra += ":in_range=full:out_range=limited"
    return extra


def _base_chain(path: str, duration: float) -> str:
    return (f"scale={W}:{H}:force_original_aspect_ratio=increase{_scale_args(path)},crop={W}:{H},fps={FPS},tpad=stop_mode=clone:stop_duration=60,{TAG},"
            f"trim=duration={duration:.3f},setpts=PTS-STARTPTS")


@lru_cache(maxsize=256)
def _dims(path: str) -> Tuple[int, int]:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path],
                           capture_output=True, text=True, timeout=30)
        w, h = r.stdout.strip().split("x")[:2]
        return int(w), int(h)
    except Exception:
        return 0, 0


MOTIONS = ("push_in", "push_out", "pan_left", "pan_right", "none")
GRADES = ("cold", "warm_archive", "neutral")
ZOOM_MAX, ZOOM_MAX_LOWRES = 1.08, 1.03
FILL_BELOW, FILL_ABOVE = 1.5, 2.1       # source aspect ratios outside this band get blur-fill instead of a hard centre crop (16:9 = 1.78)


def _shot_treat(shot: Shot, f0: int, f1: int) -> Optional[str]:
    """Canonical JSON of a shot's treatment (clamped to what the source can carry) with the shot's global frame span, or None when the shot is
    plain and needs nothing: then every graph and cache key is exactly what it was before treatments existed."""
    t = dict(getattr(shot, "treat", None) or {})
    w, h = _dims(shot.path)
    motion = str(t.get("motion") or "none")
    motion = motion if motion in MOTIONS else "none"
    grade = str(t.get("grade") or "neutral")
    grade = grade if grade in GRADES else "neutral"
    try:
        vig, grain = min(1.0, max(0.0, float(t.get("vignette") or 0.0))), min(1.0, max(0.0, float(t.get("grain") or 0.0)))
    except (TypeError, ValueError):
        vig = grain = 0.0
    bf = t.get("blur_fill", "auto")
    aspect = (w / h) if (w and h) else 1.7778
    fill = bool(bf) if bf in (True, False) else (aspect < FILL_BELOW or aspect > FILL_ABOVE)
    zmax = ZOOM_MAX_LOWRES if (h and h < 540) else ZOOM_MAX
    try:
        z0 = min(zmax, max(1.0, float(t.get("z0", 1.0))))
        z1 = min(zmax, max(1.0, float(t.get("z1", 1.06))))
    except (TypeError, ValueError):
        z0, z1 = 1.0, 1.06
    if motion == "push_in" and z1 <= z0:
        z0, z1 = 1.0, max(z1, 1.0)
    if motion == "push_out" and z0 <= z1:
        z0, z1 = max(z0, z1, 1.04), 1.0
    if motion.startswith("pan"):
        z0 = z1 = min(zmax, max(z0, z1, 1.05))
    if motion == "none" and not (fill or grade != "neutral" or vig or grain):
        return None
    d: Dict[str, Any] = {"m": motion, "g": grade, "v": round(vig, 3), "n": round(grain, 3), "fill": fill}
    if motion != "none":
        d.update({"z0": round(z0, 4), "z1": round(z1, 4), "sf0": int(f0), "sf1": int(f1)})
    return json.dumps(d, sort_keys=True)


def _grade_filters(g: str) -> str:
    if g == "cold":
        return "eq=contrast=1.05:gamma=0.97,lutyuv=u='(val-128)*0.72+128+4':v='(val-128)*0.72+128-3',"
    if g == "warm_archive":
        return "eq=contrast=1.03,lutyuv=u='(val-128)*0.6+128-4':v='(val-128)*0.6+128+5',"
    return ""


def _zoompan(tr: Dict[str, Any], off: int) -> str:
    """Zoom/pan on the 2x canvas: one eased (smoothstep) curve over the whole shot, evaluated from the global frame (off = frames since the
    shot began when this piece starts), so cutting a long shot into pieces never restarts or jumps the move."""
    n1 = max(1, int(tr["sf1"]) - int(tr["sf0"]) - 1)
    f = f"min(1,(on+{off})/{n1})"
    e = f"(({f})*({f})*(3-2*({f})))"
    z0, z1 = tr["z0"], tr["z1"]
    if tr["m"] in ("pan_left", "pan_right"):
        g = e if tr["m"] == "pan_right" else f"(1-{e})"
        return f"zoompan=z='{z1}':x='(iw-iw/zoom)*{g}':y='(ih-ih/zoom)/2':d=1:s={W}x{H}:fps={FPS},"
    return f"zoompan=z='{z0}+({z1}-{z0})*{e}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS},"


def _stage(path: str, src: str, out: str, duration: float, treat: Optional[str], off: int, uid: str, plate: bool = False) -> str:
    """`[src]...[out]`: the clip scaled to the canvas, trimmed to `duration`. No treatment: exactly the original _base_chain."""
    if not treat:
        return f"[{src}]{_base_chain(path, duration)}[{out}]"
    tr = json.loads(treat)
    moving = tr["m"] != "none"
    cw, ch = (W * 2, H * 2) if moving else (W, H)
    sa = _scale_args(path)
    if tr["fill"]:
        q = (W // 4, H // 4)
        head = (f"[{src}]split[bs{uid}][fs{uid}];[bs{uid}]scale={q[0]}:{q[1]}:force_original_aspect_ratio=increase{sa},crop={q[0]}:{q[1]},"
                f"boxblur=5:2,scale={cw}:{ch}:flags=bicubic,lutyuv=y='val*0.6':u='(val-128)*0.8+128':v='(val-128)*0.8+128'[bb{uid}];"
                f"[fs{uid}]scale={cw}:{ch}:force_original_aspect_ratio=decrease{sa}[ff{uid}];[bb{uid}][ff{uid}]overlay=(W-w)/2:(H-h)/2,")
    else:
        head = f"[{src}]scale={cw}:{ch}:force_original_aspect_ratio=increase{sa},crop={cw}:{ch},"
    chain = head + f"fps={FPS},tpad=stop_mode=clone:stop_duration=60,"
    if moving:
        chain += _zoompan(tr, off)
    chain += _grade_filters(tr["g"])
    if tr["v"] and not plate:           # a dim plate is blurred and carries its own vignette: grain and a second one would be invisible work
        chain += f"vignette={0.12 + 0.6 * tr['v']:.4f},"   # ffmpeg's angle grows with the effect: 0.63 (PI/5) is already a strong vignette, so v=0.25 is about 0.27
    if tr["n"] and not plate:
        chain += f"noise=alls={max(1, int(round(12 * tr['n'])))}:allf=t:all_seed=11,"
    chain += f"{TAG},trim=duration={duration:.3f},setpts=PTS-STARTPTS"
    return f"{chain}[{out}]"


def _sf0(treat: Optional[str], default: int) -> int:
    try:
        return int(json.loads(treat).get("sf0", default)) if treat else default
    except (ValueError, TypeError):
        return default


def _dissolving(piece: Piece) -> bool:
    return piece.dissolve > 0 and bool(piece.prev_path)


def piece_graph(piece: Piece, spans_local: Sequence[Tuple[float, float]]) -> str:
    """Inputs: 0 clear clip, 1..m the same clip again (dim plates), then the previous shot's clip when this piece dissolves from it, then the overlay pipe."""
    m = len(spans_local)
    d = piece.frames / FPS
    base = _base_chain(piece.path, d)
    off = piece.f0 - _sf0(piece.treat, piece.f0)
    plain = not piece.treat
    parts = [_stage(piece.path, "0:v", "c0", d, piece.treat, off, "c")]
    last = "c0"
    dis = _dissolving(piece)
    if dis:
        poff = piece.f0 - _sf0(piece.prev_treat, piece.f0)
        parts.append(_stage(piece.prev_path, f"{m + 1}:v", "pv", d, piece.prev_treat, poff, "p"))
        parts.append(f"[pv]format=yuv420p[pvf];[c0]format=yuva420p,fade=t=in:st=0:d={piece.dissolve:.3f}:alpha=1[c0f];[pvf][c0f]overlay=format=yuv420[c0m]")
        last = "c0m"
    if m == 0:
        parts.append(f"[{last}]format=yuva420p[c0a]")        # same pixel path as the single graph's pass-through overlays
        last = "c0a"
    for j, (a, b) in enumerate(spans_local):
        a0, b0 = max(0.0, a - L.DIM_IN_S), min(d, b + L.DIM_IN_S)
        tail = (f"setpts=PTS+{a0:.3f}/TB,trim=start={a0:.3f}:end={b0:.3f},"
                f"scale=iw/{L.BACKDROP_SHRINK}:ih/{L.BACKDROP_SHRINK},scale={W}:{H}:flags=bicubic,"
                f"lutyuv=y='val*{L.BACKDROP_BRIGHTNESS}':u='(val-128)*0.8+128':v='(val-128)*0.8+128',vignette=PI/5,"
                f"format=yuva420p,fade=t=in:st={a0:.3f}:d={L.DIM_IN_S}:alpha=1,fade=t=out:st={b:.3f}:d={L.DIM_IN_S}:alpha=1[dm{j}]")
        if plain:
            parts.append(f"[{j + 1}:v]{base},{tail}")
        else:
            parts.append(_stage(piece.path, f"{j + 1}:v", f"pb{j}", d, piece.treat, off, f"d{j}", plate=True) + f";[pb{j}]{tail}")
        parts.append(f"[{last}][dm{j}]overlay=enable='between(t,{a0:.3f},{b0:.3f})':eof_action=pass[o{j}]")
        last = f"o{j}"
    parts.append(f"[{last}][{m + 1 + (1 if dis else 0)}:v]overlay=format=auto,format=yuv420p[out]")
    return ";\n".join(parts)


def _spans_local(piece: Piece, layers: Sequence[Layer]) -> List[Tuple[float, float]]:
    t0, t1 = piece.start, piece.end
    if os.path.basename(str(piece.path)).startswith("war_backdrop"):
        return []                       # the atmosphere plate is already a quiet backdrop: dimming it again only turns it black
    sel = [ly for ly in layers if ly.dim and ly.end > t0 and ly.start < t1]
    out = []
    for a, b in dim_spans(sel):
        out.append((max(a, t0) - t0, min(b, t1) - t0))
    return out[:MAX_INPUTS - 1 - (1 if _dissolving(piece) else 0)]


# --------------------------------------------------------------------------- cache key
_HASH_HEAD = 16 * 1024 * 1024


def _file_identity(path: str) -> list:
    try:
        p = Path(path)
        st = p.stat()
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            h.update(fh.read(_HASH_HEAD))
        return ["sha256-head:" + h.hexdigest(), st.st_size]
    except OSError:
        return [str(path), None]


def _canon(v: Any) -> Any:
    """Canonical JSON-able form of layer params: floats rounded, dicts sorted, pictures and existing files by content."""
    try:
        from PIL import Image

        if isinstance(v, Image.Image):
            return ["img", v.size, hashlib.sha1(v.convert("RGBA").tobytes()).hexdigest()]
    except Exception:
        pass
    if isinstance(v, dict):
        return {str(k): _canon(x) for k, x in sorted(v.items(), key=lambda kv: str(kv[0]))}
    if isinstance(v, (list, tuple)):
        return [_canon(x) for x in v]
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, Path):
        v = str(v)
    if isinstance(v, str) and 0 < len(v) < 400 and "\n" not in v and os.path.isfile(v):
        return [v, _file_identity(v)]
    if isinstance(v, (int, bool)) or v is None or isinstance(v, str):
        return v
    return repr(v)


def _constants_hash() -> str:
    from . import tokens as T

    snap: Dict[str, Any] = {}
    for mod in (L, T):
        for k in dir(mod):
            val = getattr(mod, k)
            if k.isupper() and isinstance(val, (int, float, str, tuple)):
                snap[f"{mod.__name__}.{k}"] = val
    try:
        snap["fonts"] = T.fonts_in_use()
    except Exception:
        pass
    return hashlib.sha256(json.dumps(snap, sort_keys=True, default=repr).encode()).hexdigest()[:16]


def segment_key(piece: Piece, layers: Sequence[Layer], spans_local: Sequence[Tuple[float, float]], codec: str, consts: str) -> str:
    t0, t1 = piece.start, piece.end
    sel = [{"kind": ly.kind, "f0": _frame(ly.start), "f1": _frame(ly.end), "dim": bool(ly.dim), "params": _canon(ly.params)}
           for ly in layers if ly.end > t0 and ly.start < t1]
    payload = {"pack": PACK_VERSION, "consts": consts, "canvas": [W, H, FPS], "enc": [codec, CRF, GOP],
               "clip": _file_identity(piece.path), "seek": round(piece.seek, 4), "frames": piece.frames, "f0": piece.f0,
               "spans": [[round(a, 4), round(b, 4)] for a, b in spans_local], "layers": sel}
    if piece.treat:
        payload["treat"] = piece.treat
    if _dissolving(piece):
        payload["dissolve"] = [round(piece.dissolve, 4), _file_identity(piece.prev_path), round(piece.prev_seek, 4), piece.prev_treat]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=repr).encode()).hexdigest()


# --------------------------------------------------------------------------- rendering
def _workers(requested: Optional[int]) -> int:
    if requested:
        return max(1, int(requested))
    try:
        from hardware.governor import get_governor

        return max(1, int(get_governor().recommend_ffmpeg_workers()))
    except Exception:
        return max(1, min(4, (os.cpu_count() or 2) // 2))


def _encoder_args(codec: str) -> List[str]:
    if codec == "ffv1":
        return ["-c:v", "ffv1", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(CRF), "-g", str(GOP), "-keyint_min", str(GOP), "-sc_threshold", "0",
            "-video_track_timescale", "12800", "-pix_fmt", "yuv420p"]


def _render_piece(piece: Piece, layers: Sequence[Layer], out_path: Path, codec: str, cards: Dict[str, Callable],
                  cancel: Callable[[], bool], errors: List[str], procs: "set[subprocess.Popen]", procs_lock: threading.Lock,
                  stats: Dict[str, float]) -> None:
    have = clip_duration(piece.path)
    if have and piece.seek > have - 0.1:           # a seek past the clip's end would decode nothing: hold the clip's last frame instead
        piece = dataclasses.replace(piece, seek=max(0.0, have - 0.1))
    if _dissolving(piece) and not os.path.isfile(piece.prev_path):
        piece = dataclasses.replace(piece, dissolve=0.0)      # the previous clip vanished: a hard cut, never a failed render
    spans = _spans_local(piece, layers)
    graph = piece_graph(piece, spans)
    script = out_path.with_suffix(".graph.txt")
    script.write_text(graph, encoding="utf-8")
    d = piece.frames / FPS
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for _ in range(1 + len(spans)):
        cmd += ["-ss", f"{piece.seek:.3f}", "-t", f"{d + 0.5:.3f}", "-i", piece.path]
    if _dissolving(piece):
        pseek = piece.prev_seek
        phave = clip_duration(piece.prev_path)
        if phave and pseek > phave - 0.1:
            pseek = max(0.0, phave - 0.1)
        cmd += ["-ss", f"{pseek:.3f}", "-t", f"{piece.dissolve + 0.5:.3f}", "-i", piece.prev_path]
    cmd += ["-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-filter_complex_script", str(script),
            "-map", "[out]", "-an"] + _encoder_args(codec) + ["-frames:v", str(piece.frames), str(out_path)]
    active_all = [ly for ly in layers if ly.end > piece.start and ly.start < piece.end]
    blank = bytes(W * H * 4)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    with procs_lock:
        procs.add(proc)
    prev_img_sig: Optional[bytes] = None
    prev_bytes: Optional[bytes] = None
    reused = 0

    def on_error(ly: Layer, exc: Exception) -> None:
        msg = f"card '{ly.kind}' failed at piece {piece.index}: {exc}"
        if msg not in errors:
            errors.append(msg)
            log.warning(msg)

    try:
        assert proc.stdin is not None
        for f in range(piece.f0, piece.f1):
            if cancel():
                raise RenderCancelled()
            t = f / FPS
            active = [ly for ly in active_all if ly.start <= t < ly.end]
            if not active:
                data = blank
            else:
                img = _compose(t, active, cards, on_error)
                data = img.tobytes()
                sig = hashlib.blake2b(data, digest_size=8).digest()
                if REUSE_BYTES and sig == prev_img_sig and prev_bytes is not None:
                    data = prev_bytes            # an unchanged frame reuses the previous bytes object (no second 3.7 MB copy kept alive)
                    reused += 1
                prev_img_sig, prev_bytes = sig, data
            proc.stdin.write(data)
        proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
        try: rc = proc.wait(timeout=900)
        except subprocess.TimeoutExpired: raise RenderError(f"ffmpeg timed out on piece {piece.index}")   # the BaseException handler below kills it
    except BrokenPipeError:
        err = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
        try: rc = proc.wait(timeout=60)
        except subprocess.TimeoutExpired: proc.kill(); rc = -9
        raise RenderError(f"ffmpeg stopped early on piece {piece.index}: {err[-600:]}")
    except RenderCancelled:
        _kill(proc)
        raise
    except BaseException:
        _kill(proc)
        raise
    finally:
        with procs_lock:
            procs.discard(proc)
        script.unlink(missing_ok=True)
    stats["reused_frames"] = stats.get("reused_frames", 0) + reused
    if rc != 0:
        raise RenderError(f"ffmpeg failed on piece {piece.index} (rc {rc}): {err[-600:]}")
    if not out_path.is_file() or out_path.stat().st_size == 0:
        raise RenderError(f"ffmpeg wrote nothing for piece {piece.index}")
    got = _probe_duration(out_path)
    if got and abs(got - piece.frames / FPS) > 1.5 / FPS:
        raise RenderError(f"piece {piece.index} has {got:.3f}s, expected {piece.frames / FPS:.3f}s (source clip too short or unreadable?)")


def _kill(proc: subprocess.Popen) -> None:
    try:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)
    except Exception:
        pass


def _concat_path_text(p: Path) -> str:
    """Absolute, forward slashes, quote-escaped: what the app's ffmpeg_concat_path_text does (copied so video_generator is not imported)."""
    text = Path(p).resolve().as_posix()
    return text.replace("\\", "\\\\").replace("'", r"'\''")


def _join(parts: Sequence[Path], out_path: Path) -> None:
    lst = out_path.with_suffix(".list.txt")
    lst.write_text("".join(f"file '{_concat_path_text(p)}'\n" for p in parts), encoding="utf-8")
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out_path)],
                           capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        lst.unlink(missing_ok=True); raise RenderError("join timed out")
    lst.unlink(missing_ok=True)
    if r.returncode != 0:
        raise RenderError(f"join failed: {r.stderr[-600:]}")


def _mux_audio(video: Path, audio: str, out_path: Path, duration: float) -> None:
    """Attach the voiceover/music once: video stream copied, audio AAC, padded or cut to the exact video length."""
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-i", audio, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                            "-af", "apad", "-c:a", "aac", "-b:a", "192k", "-t", f"{duration:.4f}", "-movflags", "+faststart", str(out_path)],
                           capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        raise RenderError("audio mux timed out")
    if r.returncode != 0:
        raise RenderError(f"audio mux failed: {r.stderr[-600:]}")


def _probe_duration(path: Path) -> float:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration", "-of", "csv=p=0", str(path)],
                           capture_output=True, text=True, timeout=60)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def _probe_sync(path: Path) -> Tuple[int, float, float, float, float]:
    """(video packets, video duration, audio duration, video start, audio start); zeros when a stream or the probe is missing."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-show_entries", "stream=codec_type,start_time,duration,nb_read_packets",
                            "-of", "json", str(path)], capture_output=True, text=True, timeout=120)
        streams = json.loads(r.stdout).get("streams", [])
    except Exception:
        return 0, 0.0, 0.0, 0.0, 0.0
    v = next((x for x in streams if x.get("codec_type") == "video"), {})
    a = next((x for x in streams if x.get("codec_type") == "audio"), {})
    f = lambda d, k: float(d.get(k) or 0.0)
    return int(v.get("nb_read_packets") or 0), f(v, "duration"), f(a, "duration"), f(v, "start_time"), f(a, "start_time")


def validate_inputs(shots: Sequence[Shot]) -> None:
    for s in shots:
        if not s.path or not Path(s.path).is_file():
            raise MissingInput(f"footage file not found: {s.path!r}")
        have = clip_duration(s.path)
        if have and s.seek + (s.end - s.start) > have + 0.05:
            # the shot is longer than its clip: the last frame is held (exact duration kept); the planner should pick a longer clip
            log.warning("clip %s is %.1fs but the shot needs %.1fs from %.1fs: last frame held", Path(s.path).name, have, s.end - s.start, s.seek)


def render_segmented(shots: Sequence[Shot], layers: Sequence[Layer], out_path: str, *, audio_path: Optional[str] = None,
                     state_dir: Optional[str] = None, cancel_check: Optional[Callable[[], bool]] = None,
                     progress_cb: Optional[Callable[[float, str], None]] = None, workers: Optional[int] = None, codec: str = "x264",
                     temp_dir: Optional[str] = None) -> Dict[str, Any]:
    """Render shots + layers to out_path. Raises RenderCancelled / MissingInput / RenderError. Never leaves a temp folder behind."""
    t_start = time.time()
    cancel = cancel_check or (lambda: False)
    validate_inputs(shots)
    pieces = plan_pieces(shots, layers)
    if not pieces:
        raise RenderError("nothing to render: no shots with a duration")
    total_frames = pieces[-1].f1 - pieces[0].f0
    cards = all_cards()
    consts = _constants_hash()
    n_workers = min(_workers(workers), len(pieces))
    cache = None
    if state_dir:
        try:
            from render_cache import RenderCache

            cache = RenderCache(Path(state_dir) / "ce_segments")
        except Exception as exc:
            log.warning("segment cache unavailable: %s", exc)
    work = Path(tempfile.mkdtemp(prefix="ce_war_", dir=temp_dir))
    errors: List[str] = []
    stats: Dict[str, float] = {}
    procs: "set[subprocess.Popen]" = set()
    procs_lock = threading.Lock()
    hits = misses = 0
    done = [0]
    lock = threading.Lock()
    ext = "mkv" if codec == "ffv1" else "mp4"
    outs = [work / f"seg_{p.index:05d}.{ext}" for p in pieces]

    def one(p: Piece) -> None:
        nonlocal hits, misses
        if cancel():
            raise RenderCancelled()
        out = outs[p.index]
        spans = _spans_local(p, layers)
        key = segment_key(p, layers, spans, codec, consts) if cache else ""
        skey = f"ce_{p.f0}"
        if cache:
            hit = cache.get(skey, key)
            if hit is not None and cache.reuse(hit, out):
                with lock:
                    hits += 1
                    done[0] += p.frames
                _progress()
                return
        _render_piece(p, layers, out, codec, cards, cancel, errors, procs, procs_lock, stats)
        if cache:
            cache.put(skey, key, out)
        with lock:
            misses += 1
            done[0] += p.frames
        _progress()

    def _progress() -> None:
        if progress_cb:
            try:
                progress_cb(min(1.0, done[0] / total_frames), f"segments {sum(1 for o in outs if o.exists())}/{len(outs)}")
            except Exception:
                pass

    result: Dict[str, Any] = {}
    try:
        with cf.ThreadPoolExecutor(max_workers=n_workers) as ex:
            futs = [ex.submit(one, p) for p in pieces]
            try:
                for f in cf.as_completed(futs):
                    f.result(timeout=60)   # as_completed only yields finished futures
            except BaseException:
                for f in futs:
                    f.cancel()
                with procs_lock:
                    for pr in list(procs):
                        _kill(pr)
                raise
        joined = work / f"joined.{ext}"
        _join(outs, joined)
        duration = total_frames / FPS
        final = Path(out_path)
        final.parent.mkdir(parents=True, exist_ok=True)
        part = final.with_name(final.stem + ".part" + final.suffix)
        if audio_path:
            _mux_audio(joined, audio_path, part, duration)
        else:
            shutil.copy2(joined, part)
        got = _probe_duration(part)
        if got and abs(got - duration) > 2.5 / FPS:
            raise RenderError(f"output duration {got:.3f}s differs from the plan {duration:.3f}s")
        frames_out, v_dur, a_dur, v_start, a_start = _probe_sync(part)
        if frames_out and frames_out != total_frames:
            raise RenderError(f"output has {frames_out} frames, the plan has {total_frames}")
        if audio_path and a_dur and (abs(a_dur - v_dur) > 1.0 / FPS or abs(v_start) > 1e-3 or abs(a_start) > 1e-3):
            raise RenderError(f"audio and video are out of step: video {v_dur:.3f}s from {v_start:.3f}, audio {a_dur:.3f}s from {a_start:.3f}")
        os.replace(part, final)
        result = {"ok": True, "out": str(final), "frames": total_frames, "duration_s": duration, "segments": len(pieces),
                  "cache_hits": hits, "cache_misses": misses, "workers": n_workers, "reused_frames": int(stats.get("reused_frames", 0)),
                  "card_errors": list(errors), "fallback": False, "seconds": time.time() - t_start}
    finally:
        shutil.rmtree(work, ignore_errors=True)
        try:
            Path(out_path).with_name(Path(out_path).stem + ".part" + Path(out_path).suffix).unlink(missing_ok=True)
        except OSError:
            pass
    return result


def render_with_fallback(shots: Sequence[Shot], layers: Sequence[Layer], out_path: str, **kw: Any) -> Dict[str, Any]:
    """Segmented render; if it fails for a reason other than cancel or missing footage, the Phase 1 single-graph renderer is used with the
    layers it can draw (its card kinds), and the result says so. Memory-heavy on long videos: that is why it is only the fallback."""
    try:
        return render_segmented(shots, layers, out_path, **kw)
    except (RenderCancelled, MissingInput):
        raise
    except Exception as exc:
        log.error("segmented render failed (%s); falling back to the Phase 1 renderer", exc)
        from ..render import render as phase1_render

        known = set(_phase1_cards.CARDS)
        usable = [ly for ly in layers if ly.kind in known]
        skipped = len(layers) - len(usable)
        t0 = time.time()
        stats = phase1_render(list(shots), usable, out_path)
        return {"ok": True, "out": out_path, "frames": stats.get("frames"), "fallback": True, "fallback_reason": str(exc)[-300:],
                "skipped_layers": skipped, "seconds": time.time() - t0}
