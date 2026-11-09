"""War Footage Director, Stage 4: look at a candidate's pictures BEFORE capturing anything.

docs/war/FOOTAGE_DIRECTOR_PLAN.md. YouTube storyboards (yt-dlp lists them: 3x3 JPEG sheets of 320x180 tiles, about one tile every 2 s, served from
i.ytimg.com, not the video stream) are cut into timed tiles. Each tile is classified with numpy only (no models):

  pillarbox     phone video in a 16:9 frame: blurred or black side bars, detail only in the middle
  text_screen   an article / document / caption card: large pale flat area with fine dark detail
  graphic       a drawn screen (map, chart, title card): a few flat colours cover most of it
  studio        a presenter shot: skin-tone block in the middle third and almost no change from the tile before
  dark          too dark to read
  static        no change from the tile before (a still, a freeze)
  footage       none of the above: filmed pictures

choose_window() picks the best CLIP_S window of footage tiles with no cut inside it (a cut only at its start), away from the first and last 5 %
of the video. Tile hashes (64-bit dHash) let the film-wide registry spot the same picture under another URL.
"""

from __future__ import annotations

import io
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

CLIP_S = 8.0
EDGE_SKIP = 0.05
CUT_HASH = 24             # dHash distance between neighbouring tiles that, with CUT_DIFF, marks a scene change
CUT_DIFF = 38.0           # ... and mean abs pixel change (0-255): hand-held motion changes the hash, a cut changes both
MIN_S = 3.0               # the shortest usable stretch (a documentary shot is 3-6 s; problem 12)
STATIC_DIFF = 2.5         # mean abs change (0-255) below which two neighbouring tiles are the same picture
FOOTAGE = "footage"
BAD = ("pillarbox", "text_screen", "graphic", "studio", "dark")


@dataclass
class Tile:
    t: float
    img: np.ndarray                    # (h, w, 3) uint8
    kind: str = FOOTAGE
    hash: str = ""
    cut_before: bool = False
    detail: float = 0.0
    flags: List[str] = field(default_factory=list)


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (VideoGenerator War footage check)"})
    with urllib.request.urlopen(req, timeout=20) as r:          # noqa: S310 - a storyboard URL from yt-dlp's own metadata
        return r.read()


def tiles_from_storyboard(sb: Dict[str, Any], fetch: Callable[[str], bytes] = _fetch, around: Optional[Tuple[float, float]] = None,
                          max_sheets: int = 40) -> List[Tile]:
    """Cut a storyboard into timed tiles. `around` (t0, t1) fetches only the sheets covering that span."""
    from PIL import Image
    rows, cols = int(sb.get("rows") or 1), int(sb.get("columns") or 1)
    step = float(sb.get("interval") or 2.0)
    per = rows * cols
    out: List[Tile] = []
    for i, fr in enumerate((sb.get("fragments") or [])[:max_sheets]):
        t_sheet = i * per * step
        if around and (t_sheet > around[1] or t_sheet + per * step < around[0]):
            continue
        try:
            im = Image.open(io.BytesIO(fetch(fr["url"]))).convert("RGB")
        except Exception:  # noqa: BLE001 - a missing sheet leaves a gap, never a guess
            continue
        a = np.asarray(im)
        th, tw = a.shape[0] // rows, a.shape[1] // cols
        for k in range(per):
            r_, c_ = divmod(k, cols)
            tile = a[r_ * th:(r_ + 1) * th, c_ * tw:(c_ + 1) * tw]
            if tile.size == 0 or tile.mean() < 1.0 and tile.std() < 0.5:
                continue                                       # the empty cells after the last frame of the video
            out.append(Tile(t=round(t_sheet + k * step, 3), img=tile))
    return out


def tiles_from_thumbnails(video_id: str, duration: Optional[float], fetch: Callable[[str], bytes] = _fetch) -> List[Tile]:
    """Fallback preview when the storyboard needs a sign-in (age-restricted videos): YouTube's three automatic thumbnails, taken at about
    25 %, 50 % and 75 % of the video, from i.ytimg.com. Coarse (no cuts known), so a capture from them is checked again on its own frames."""
    from PIL import Image
    out: List[Tile] = []
    dur = float(duration or 0) or 0.0
    for k, frac in ((1, 0.25), (2, 0.5), (3, 0.75)):
        try:
            im = Image.open(io.BytesIO(fetch(f"https://i.ytimg.com/vi/{video_id}/hq{k}.jpg"))).convert("RGB")
        except Exception:  # noqa: BLE001
            continue
        a = np.asarray(im.resize((160, 120)))
        a = a[15:105]                                    # hq thumbnails are 4:3 with letterbox bars: keep the 16:9 middle
        out.append(Tile(t=round(dur * frac, 2), img=np.ascontiguousarray(a)))
    return out


def window_from_thumbnails(tiles: Sequence[Tile], duration: Optional[float], clip_s: float = CLIP_S,
                           usable: Callable[[float, float, List[str]], bool] = lambda a, b, h: True) -> Optional[Dict[str, Any]]:
    """A capture window around the first thumbnail that looks like filmed footage (cuts unknown: the capture is trimmed afterwards)."""
    dur = float(duration or 0)
    for t in tiles:
        if t.kind != FOOTAGE or dur <= 0:
            continue
        a = max(dur * EDGE_SKIP, t.t - clip_s / 2)
        b = min(dur * (1 - EDGE_SKIP), a + clip_s)
        if b - a >= MIN_S and usable(a, b, [t.hash]):
            return {"start": round(a, 2), "end": round(b, 2), "seconds": round(b - a, 2), "score": 0.0, "hashes": [t.hash],
                    "inspection": "thumbnails"}
    return None


def dhash(img: np.ndarray) -> str:
    g = img.astype(np.float32).mean(axis=2)
    h, w = g.shape
    ys = (np.arange(8) * h / 8).astype(int)
    xs = (np.arange(9) * w / 9).astype(int)
    small = np.array([[g[y:y + max(1, h // 8), x:x + max(1, w // 9)].mean() for x in xs] for y in ys])
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return f"{int(''.join('1' if b else '0' for b in bits), 2):016x}"


def _hd(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def _lap(g: np.ndarray) -> np.ndarray:
    return np.abs(4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:])


def _same_size(a: np.ndarray, b: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    h, w = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
    return a[:h, :w], b[:h, :w]


def classify(img: np.ndarray, prev: Optional[np.ndarray] = None) -> Tuple[str, float, List[str]]:
    """(kind, detail, extra flags) of one tile."""
    a = img.astype(np.float32)
    g = a.mean(axis=2)
    h, w = g.shape
    lap = _lap(g)
    detail = float(lap.mean())
    flags: List[str] = []
    if g.mean() < 22 and g.std() < 18:
        return "dark", detail, flags
    side = max(2, int(w * 0.16))
    mid = lap[:, side:w - side - 2]
    edges = np.concatenate([lap[:, :side - 1], lap[:, w - side - 1:]], axis=1)
    if mid.mean() > 1.5 and edges.mean() < 0.35 * mid.mean():
        return "pillarbox", detail, flags
    # side bars that are a blurred colour copy of the picture (phone video at night): flat sides, a hard seam where the picture starts
    col = np.abs(np.diff(g, axis=1)).mean(axis=0)
    seam_l, seam_r = col[int(w * 0.12):int(w * 0.35)], col[int(w * 0.65):int(w * 0.88)]
    if len(seam_l) and len(seam_r) and edges.mean() < 0.5 * max(mid.mean(), 1e-3) and \
            seam_l.max() > 4 * max(np.median(col), 0.5) and seam_r.max() > 4 * max(np.median(col), 0.5):
        return "pillarbox", detail, flags
    q = (img >> 5).astype(np.int32)
    keys = ((q[..., 0] << 6) | (q[..., 1] << 3) | q[..., 2]).ravel()
    top = np.sort(np.bincount(keys, minlength=512))[::-1]
    flat8 = float(top[:8].sum()) / keys.size
    pale = float((g > 200).mean())
    if pale > 0.35 and flat8 > 0.6 and detail > 3.0:
        return "text_screen", detail, flags
    pm = (g[1:-1, 1:-1] > 200)
    if pm.mean() > 0.10 and float(lap[pm].mean()) > 14.0 and float(lap[~pm].mean() if (~pm).any() else 0) < float(lap[pm].mean()) * 0.8:
        return "text_screen", detail, flags                   # a pale text box laid over a picture (an article quote card)
    if 0.025 < pm.mean() <= 0.10 and float(lap[pm].mean()) > 14.0:
        flags.append("caption")                               # a burnt-in caption box: usable, but a clean stretch is preferred
    if flat8 > 0.82 and float(top[0]) / keys.size > 0.35:
        return "graphic", detail, flags
    if prev is not None:
        x, y = _same_size(a, prev.astype(np.float32))
        change = float(np.abs(x - y).mean())
        r_, gg, b = a[..., 0], a[..., 1], a[..., 2]
        skin = (r_ > 95) & (gg > 40) & (b > 20) & (r_ > gg + 12) & (r_ > b + 12)
        centre = skin[h // 6: h * 5 // 6, w // 3: w * 2 // 3].mean()
        if centre > 0.18 and change < 9.0:
            return "studio", detail, flags
        if change < STATIC_DIFF:
            flags.append("static")
    return FOOTAGE, detail, flags


def _cells(img: np.ndarray, prev: np.ndarray) -> List[List[float]]:
    a, b = _same_size(img.astype(np.float32), prev.astype(np.float32))
    h, w = a.shape[:2]
    return [[float(np.abs(a[r * h // 4:(r + 1) * h // 4, c * w // 4:(c + 1) * w // 4] - b[r * h // 4:(r + 1) * h // 4, c * w // 4:(c + 1) * w // 4]).mean())
             for c in range(4)] for r in range(3)]


def persistent_inset(tiles: Sequence["Tile"]) -> int:
    """The grid column (0-3) that stays still in at least half of the tile pairs where the rest of the frame moves: a studio split-screen
    layout for the whole programme (CNN 'NEW TONIGHT'); -1 when there is none."""
    votes, pairs = [0, 0, 0, 0], 0
    for a, b in zip(tiles, tiles[1:]):
        ch = _cells(b.img, a.img)
        mov = [ch[r][c] for r in range(3) for c in range(4) if ch[r][c] > 18]
        if len(mov) < 4:
            continue
        pairs += 1
        calm = min(26.0, max(6.0, 0.4 * float(np.median(mov))))
        for c in range(4):
            if sum(1 for r in range(3) if ch[r][c] < calm) >= 2:
                votes[c] += 1
    if pairs < 3:
        return -1
    c = int(np.argmax(votes))
    return c if votes[c] >= 0.5 * pairs else -1


def inset_box(img: np.ndarray, prev: np.ndarray) -> bool:
    """A news layout with a box that does not change while the rest of the frame does (a studio presenter beside the pictures, CNN /
    France 24 style): in a 4x4 grid of the upper three rows, at least two touching cells in one column are still while at least four other
    cells changed. Logos and lower thirds are small or in the bottom row and do not count."""
    a, b = _same_size(img.astype(np.float32), prev.astype(np.float32))
    h, w = a.shape[:2]
    ch = [[float(np.abs(a[r * h // 4:(r + 1) * h // 4, c * w // 4:(c + 1) * w // 4] - b[r * h // 4:(r + 1) * h // 4, c * w // 4:(c + 1) * w // 4]).mean())
           for c in range(4)] for r in range(3)]
    mov = [ch[r][c] for r in range(3) for c in range(4) if ch[r][c] > 18]
    if len(mov) < 4:
        return False
    calm = min(26.0, max(6.0, 0.4 * float(np.median(mov))))   # measured on CNN (2026-11-09): anchor 13-22 while the pictures moved 35-77
    for c in range(4):
        still = [ch[r][c] < calm for r in range(3)]
        if (still[0] and still[1]) or (still[1] and still[2]):
            col = a[: h * 3 // 4, c * w // 4:(c + 1) * w // 4]
            if float(col.std()) > 18:                       # a textured box (a person), not a flat bar
                return True
    return False


def inspect(tiles: List[Tile]) -> List[Tile]:
    prev = None
    prev_hash = ""
    for t in tiles:
        t.kind, t.detail, t.flags = classify(t.img, prev)
        if t.kind == FOOTAGE and prev is not None and inset_box(t.img, prev):
            t.kind, t.flags = "studio", t.flags + ["inset_presenter"]
        t.hash = dhash(t.img)
        if prev_hash and prev is not None:
            x, y = _same_size(t.img.astype(np.float32), prev.astype(np.float32))
            t.cut_before = _hd(prev_hash, t.hash) > CUT_HASH and float(np.abs(x - y).mean()) > CUT_DIFF
        prev, prev_hash = t.img, t.hash
    if persistent_inset(tiles) >= 0:
        for t in tiles:
            if t.kind == FOOTAGE:
                t.kind, t.flags = "studio", t.flags + ["inset_presenter", "studio_layout"]
    return tiles


def choose_window(tiles: Sequence[Tile], duration: Optional[float], clip_s: float = CLIP_S, hint: Optional[float] = None,
                  usable: Callable[[float, float, List[str]], bool] = lambda a, b, h: True, min_s: float = MIN_S) -> Optional[Dict[str, Any]]:
    """The best stretch of min_s..clip_s seconds: every tile footage, no cut after its first tile (so no one-second fragment of another shot
    reaches the film), not in the first / last 5 % of the video, allowed by `usable(start, end, hashes)` (the no-repeat registry).
    Longer is better, then detail and motion, then nearness to a transcript `hint`."""
    if not tiles:
        return None
    step = max(0.2, tiles[1].t - tiles[0].t) if len(tiles) > 1 else 2.0
    total = duration or (tiles[-1].t + step)
    lo, hi = total * EDGE_SKIP, min(total * (1 - EDGE_SKIP), total - 0.3)
    best = None
    for i, first in enumerate(tiles):
        if first.kind != FOOTAGE or first.t < lo:
            continue
        run = [first]
        for t in tiles[i + 1:]:
            if t.kind != FOOTAGE or t.cut_before or t.t - first.t >= clip_s:
                break
            run.append(t)
        a = first.t
        b = min(a + clip_s, run[-1].t + step, hi)
        if b - a < min_s - 1e-6:
            continue
        if sum(1 for t in run if "static" in t.flags) > len(run) // 2:
            continue
        hashes = [t.hash for t in run]
        if not usable(a, b, hashes):
            continue
        sc = (b - a) * 1.5 + sum(t.detail for t in run) / len(run) + sum(_hd(x.hash, y.hash) for x, y in zip(run, run[1:])) * 0.1
        sc -= 2.5 * sum(1 for t in run if "caption" in t.flags)
        if hint is not None:
            sc -= abs(a - hint) / 30.0
        if best is None or sc > best["score"]:
            best = {"start": round(a, 2), "end": round(b, 2), "seconds": round(b - a, 2), "score": round(sc, 2), "hashes": hashes}
    return best


def summary(tiles: Sequence[Tile]) -> Dict[str, Any]:
    kinds: Dict[str, int] = {}
    for t in tiles:
        kinds[t.kind] = kinds.get(t.kind, 0) + 1
    n = len(tiles) or 1
    return {"tiles": len(tiles), "kinds": kinds, "footage_share": round(kinds.get(FOOTAGE, 0) / n, 3),
            "cuts": sum(1 for t in tiles if t.cut_before)}
