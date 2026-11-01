"""story_fast glue: the 'glued' Story Motion look (story_strip = "glued").

Every picture change gets one of four joins, chosen from the narration and the prompts:
    travel_right   pictures glued side by side with a torn seam, the camera travels on (the default)
    travel_up      the same, travelling upwards (rise / growth / empire words, and for variety after 3 sideways travels)
    push_through   the camera dives into a door / window / screen of A and comes out in B (B is an interior / a place entered)
    torn_wipe      A tears away like a sheet of paper (a jump in time or topic: "But ...", "In 1928 ...", a new year)

    segs, groups = plan(shots, images, usable, fps)          groups {shot_id: (seg_id, panel index)}; segs {seg_id: segment dict}
    render_segment(seg, out_path, cancel=None)               one mp4 of exactly seg["frames"] frames: the travel, then the link to the next segment

A segment is a run of glued pictures (1..MAX_PANELS) the camera travels along, ending in the link (if any) that carries it into the next segment.
The link takes the LAST link_frames of the segment, so the next picture is fully on screen when its words start (like the travel).
Travel dwells start and end centred, so a link starts/ends on exactly the strip's framing (strip_zoom): no jump at either end.
Consecutive shots on the same picture are one panel (the camera keeps dwelling). Unusable shots (graphic, no picture, AI video) break the chain: hard cut.
"""
from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
from typing import Callable, Dict, List, Optional, Sequence, Tuple

KINDS = ("travel_right", "travel_up", "push_through", "torn_wipe")
LINKS = ("push_through", "torn_wipe")
MAX_PANELS = 6                # pictures per glued strip; a longer run is split with a torn wipe
TRAVEL_S = 1.6                # the calm travel the user picked (v2)
LINK_S = 1.4
MIN_LINK_S = 0.8
PUSH_MAX_SHARE, PUSH_GAP = 0.12, 4      # at most 12% of the changes, at least 4 changes apart
TORN_MAX_SHARE, TORN_GAP = 0.25, 2
SIDEWAYS_RUN = 3              # after 3 sideways travels in a row the next travel goes up
GAP_S = 0.6                   # shots further apart than this are not one chain

_PORTAL = re.compile(r"\b(?:doors?|doorways?|windows?|screens?|gates?|gateways?|tunnels?|portals?|entrances?|archways?|curtains?)\b")
_INTERIOR = re.compile(r"\b(?:inside|interior|indoors?|rooms?|halls?|cinemas?|theatres?|theaters?|offices?|studios?|chambers?|corridors?|vaults?|cabins?|caves?)\b")
_INTO = re.compile(r"\b(?:into|inside|enter|enters|entered|entering|through)\b")
_SHIFT = re.compile(r"^\s*(?:but|however|meanwhile|then|later|now|years|decades|centuries|after|before|soon|next|in\s+\d{4}|by\s+\d{4}|on\s+\w+\s+\d{1,2},?\s+\d{4})\b")
_YEAR = re.compile(r"\b(1[5-9]\d\d|20\d\d)\b")
_RISE = re.compile(r"\b(?:rise|rises|rose|risen|rising|grew|grow|grows|growing|growth|empire|empires|bigger|biggest|top|towers?|sky|skies|climb\w*|soar\w*|success\w*|"
                   r"valuable|giant|huge|up|upward|heights?|peak|summit|throne|crown\w*)\b")


# ------------------------------------------------------------------ choosing the joins
def _txt(p: dict, k: str) -> str:
    return str(p.get(k) or "").lower()


def choose_joins(pictures: Sequence[dict]) -> List[str]:
    """One join kind per picture change (len(pictures) - 1). pictures: [{text, prompt}] in order. Deterministic, never raises."""
    n = max(len(pictures) - 1, 0)
    if not n:
        return []
    cap_push = max(1, int(PUSH_MAX_SHARE * n)) if n >= 4 else 0
    cap_torn = max(1, int(TORN_MAX_SHARE * n)) if n >= 2 else 0
    out: List[str] = []
    last_push = last_torn = -99
    pushes = torns = 0
    sideways = 0
    years: List[str] = []
    for i in range(len(pictures)):
        ys = _YEAR.findall(_txt(pictures[i], "text"))
        years.append(ys[0] if ys else "")
    seen_year = years[0]
    for k in range(n):
        a, b = pictures[k], pictures[k + 1]
        bt, bp, ap = _txt(b, "text"), _txt(b, "prompt"), _txt(a, "prompt")
        new_year = bool(years[k + 1]) and years[k + 1] != seen_year
        if years[k + 1]:
            seen_year = years[k + 1]
        kind = "travel_right"
        if pushes < cap_push and k - last_push >= PUSH_GAP and _PORTAL.search(ap) and (_INTO.search(bt) or _INTERIOR.search(bp)):
            kind = "push_through"
        elif torns < cap_torn and k - last_torn >= TORN_GAP and (_SHIFT.search(bt) or new_year):
            kind = "torn_wipe"
        elif (out[-1:] != ["travel_up"]) and (_RISE.search(bt) or sideways >= SIDEWAYS_RUN):
            kind = "travel_up"
        if kind == "push_through":
            pushes += 1; last_push = k
        elif kind == "torn_wipe":
            torns += 1; last_torn = k
        sideways = sideways + 1 if kind == "travel_right" else 0
        out.append(kind)
    return out


# ------------------------------------------------------------------ planning segments
def _bounds(shots, fps):
    b = [int(round(float(shots[0]["start"]) * fps))] + [int(round(float(s["end"]) * fps)) for s in shots]
    for i in range(1, len(b)):
        b[i] = max(b[i], b[i - 1])
    return b


def plan(shots: Sequence[dict], stills: Sequence[Optional[str]], usable: Sequence[bool], fps: int = 30, size=(1920, 1080), seed: int = 0) -> Tuple[Dict[str, dict], Dict[str, Tuple[str, int]]]:
    """-> (segments, groups). stills[i] = shot i's picture, usable[i] = it may be glued. Segments tile their shots' frames exactly (the runner's bounds)."""
    shots = list(shots)
    if not shots:
        return {}, {}
    bnd = _bounds(shots, fps)
    # chains of touching usable shots, each a list of panels (same picture in a row = one panel)
    chains: List[List[dict]] = []
    cur: List[dict] = []
    for i, sh in enumerate(shots):
        if not usable[i] or not stills[i]:
            if cur: chains.append(cur)
            cur = []
            continue
        if cur and abs(float(sh["start"]) - float(shots[cur[-1]["idx"][-1]]["end"])) >= GAP_S:
            chains.append(cur); cur = []
        if cur and cur[-1]["still"] == stills[i]:
            cur[-1]["idx"].append(i)
        else:
            cur.append({"still": str(stills[i]), "idx": [i], "text": str(sh.get("text") or ""), "prompt": str(sh.get("prompt_en") or sh.get("prompt") or "")})
    if cur:
        chains.append(cur)
    segs: Dict[str, dict] = {}
    groups: Dict[str, Tuple[str, int]] = {}
    sid_n = 0
    for chain in chains:
        kinds = choose_joins(chain)
        # split into segments at links and at MAX_PANELS (the split becomes a torn wipe)
        parts: List[Tuple[List[dict], List[str], Optional[str]]] = []
        pan, dirs = [chain[0]], []
        for k, kind in enumerate(kinds):
            if kind in LINKS or len(pan) >= MAX_PANELS:
                parts.append((pan, dirs, kind if kind in LINKS else "torn_wipe"))
                pan, dirs = [chain[k + 1]], []
            else:
                pan.append(chain[k + 1]); dirs.append("up" if kind == "travel_up" else "right")
        parts.append((pan, dirs, None))
        for j, (pan, dirs, link) in enumerate(parts):
            sid_n += 1
            gid = f"glue{sid_n:03d}"
            f0, f1 = bnd[pan[0]["idx"][0]], bnd[pan[-1]["idx"][-1] + 1]
            last_f = f1 - bnd[pan[-1]["idx"][0]]
            lf = 0
            if link:
                lf = min(int(round(LINK_S * fps)), last_f - int(round(0.6 * fps)))
                if lf < int(round(MIN_LINK_S * fps)):
                    link, lf = None, 0          # the last picture is too short to carry a link: a plain cut
            nxt = parts[j + 1] if link and j + 1 < len(parts) else None
            panels = [dict(still=p["still"], start=round((bnd[p["idx"][0]] - f0) / fps, 4), end=round((bnd[p["idx"][-1] + 1] - f0) / fps, 4),
                           shots=[shots[i]["shot_id"] for i in p["idx"]]) for p in pan]
            segs[gid] = dict(id=gid, panels=panels, dirs=dirs, start_frame=f0, end_frame=f1, frames=f1 - f0, fps=int(fps), size=list(size), seed=int(seed) + sid_n,
                             link=(dict(kind=link, frames=lf, still_b=nxt[0][0]["still"], vertical_b=any(d == "up" for d in nxt[1]),
                                        dir=("l" if (sid_n % 2) else "r")) if nxt else None))
            for k, p in enumerate(pan):
                for i in p["idx"]:
                    groups[shots[i]["shot_id"]] = (gid, k)
    return segs, groups


def summary(segs: Dict[str, dict]) -> Dict[str, int]:
    """How many changes of each kind the plan has (for the log and the tests)."""
    c = {k: 0 for k in KINDS}
    for s in segs.values():
        for d in s["dirs"]:
            c["travel_up" if d == "up" else "travel_right"] += 1
        if s.get("link"):
            c[s["link"]["kind"]] += 1
    return c


# ------------------------------------------------------------------ rendering
def strip_zoom(still: str, size, vertical: bool) -> float:
    """How much the travel strip magnifies a picture compared with a plain cover fit (what links.py calls zoom 1.0)."""
    from PIL import Image

    W, H = int(size[0]), int(size[1])
    zx, zy = (1.16, 1.27) if vertical else (1.16, 1.16)          # travel.Strip._layout with zoom=None
    with Image.open(still) as im:
        iw, ih = im.size
    return max(W * zx / iw, H * zy / ih) / max(W / iw, H / ih)


def _frames_of(path: str) -> int:
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", path],
                       capture_output=True, text=True, timeout=120)
    try:
        return int(r.stdout.strip())
    except ValueError:
        return 0


def render_segment(seg: dict, out_path: str, cancel: Optional[Callable[[], bool]] = None) -> str:
    """The segment's travel (+ its outgoing link) as one mp4 of exactly seg['frames'] frames. Raises on failure (the runner falls back)."""
    from health_cinema.puppet import links as L
    from health_cinema.puppet import travel as T

    fps, size, N = int(seg["fps"]), tuple(seg["size"]), int(seg["frames"])
    link = seg.get("link")
    lf = int(link["frames"]) if link else 0
    tf = N - lf
    pans = seg["panels"]
    starts = [float(p["start"]) for p in pans]
    ends = [float(p["end"]) for p in pans]
    ends[-1] = tf / fps
    stills = [p["still"] for p in pans]
    sched = T.plan_schedule(starts, ends, travel_s=TRAVEL_S, ease="smooth", dirs=list(seg["dirs"]) if len(pans) > 1 else None)
    base = os.fspath(out_path)
    travel_p = base + ".travel.mp4"
    T.render_travel(stills, sched, travel_p, fps=fps, size=size, walker=None, seed=int(seg["seed"]), cancel=cancel)
    parts = [(travel_p, tf)]
    if link:
        if cancel and cancel():
            raise T.TravelCancelled("cancelled")
        za = strip_zoom(stills[-1], size, any(d == "up" for d in seg["dirs"]))
        zb = strip_zoom(link["still_b"], size, bool(link.get("vertical_b")))
        params = dict(cam_a=[[za, 0, 0], [za * 1.035, 0, 0]], cam_b=[[zb * 1.035, 0, 0], [zb, 0, 0]])
        if link["kind"] == "torn_wipe":
            params["dir"] = link.get("dir") or "l"
        else:
            params.update(dip=0.15, zoom_max=3.0)        # no black hole in the middle, a gentler dive
        link_p = base + ".link.mp4"
        L.render_link(stills[-1], link["still_b"], link["kind"], link_p, duration=lf / fps, fps=fps, size=size, seed=int(seg["seed"]), params=params, cancel=cancel)
        parts.append((link_p, lf))
    ff = shutil.which("ffmpeg") or "ffmpeg"
    ins: List[str] = []
    fl = ""
    for i, (p, n) in enumerate(parts):
        ins += ["-i", p]
        fl += f"[{i}:v]trim=end_frame={n},setpts=PTS-STARTPTS,fps={fps},format=yuv420p,tpad=stop_mode=clone:stop={n}[v{i}];[v{i}]trim=end_frame={n}[w{i}];"
    fl += "".join(f"[w{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=1:a=0[v]"
    tmp = base + ".part.mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", *ins, "-filter_complex", fl, "-map", "[v]", "-frames:v", str(N), "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
                    "-pix_fmt", "yuv420p", "-an", tmp], check=True, capture_output=True, timeout=1800)
    os.replace(tmp, base)
    for p, _n in parts:
        for q in (p, p + ".key"):
            try: os.unlink(q)
            except OSError: pass
    return base
