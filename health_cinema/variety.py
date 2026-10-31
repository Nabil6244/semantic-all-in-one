"""Variety director for Health Cinema 3D scenes: every 3D scene in a video gets its own camera move, colour mood and light direction, and no combination
is shown again in a later video (the same organ in two videos never looks like the same clip).

A direction is chosen per scene from MOVES x LOOKS with a generator seeded by the video (its script) and the scene's place in it, skipping combinations
that earlier videos already used (a small history file, HISTORY). Re-rendering the same video gets the same directions back from the history, so its
clips stay in the render cache. Nothing here changes what is shown (organ, layers, labels): only how it is filmed and lit.

Camera moves reshape the template's own keys along the shot (an orbit sweep, a crane, a push in or a pull back), within limits that keep the framing rules
(framing.py): the organ is never pushed past library.FILL_MAX or moved behind the camera. Body-map shots follow their beats, so they only take a look."""
from __future__ import annotations
import hashlib, json, os, random, threading, time
from pathlib import Path
from typing import Dict, List, Optional

# name -> (azimuth offset at start, azimuth sweep over the shot, elevation offset at start, elevation change, zoom at start, zoom at end)
# zoom multiplies how much of the frame the subject fills (1.0 = the template's own framing)
MOVES: Dict[str, tuple] = {
    "as_designed": (0, 0, 0, 0, 1.0, 1.0),
    "orbit_left": (18, -40, 0, 2, 1.0, 1.0),
    "orbit_right": (-18, 40, 0, 2, 1.0, 1.0),
    "push_in": (-6, 12, 2, 0, 0.82, 1.08),
    "pull_back": (8, -14, 4, 2, 1.08, 0.8),
    "crane_up": (-10, 18, -8, 20, 0.95, 1.0),
    "crane_down": (12, -16, 22, -18, 1.0, 0.96),
    "low_arc": (30, -46, -7, 3, 0.95, 1.02),
    "high_arc": (-34, 52, 20, -6, 0.98, 1.0),
    "side_reveal": (68, -66, 6, 0, 0.9, 1.04),
    "slow_drift": (-8, 10, 3, 1, 1.0, 1.02),
}
# name -> page look: atmosphere palette (threejs/atmosphere.js), light rig rotation about the view axis (degrees), exposure factor, rim/glow tint
LOOKS: Dict[str, dict] = {
    "midnight": {"palette": "organ", "key_rot": 0, "exposure": 1.0, "rim": None},
    "teal_lab": {"palette": "teal", "key_rot": 35, "exposure": 1.02, "rim": [0.55, 1.0, 0.92]},
    "violet": {"palette": "violet", "key_rot": -30, "exposure": 0.98, "rim": [0.82, 0.7, 1.0]},
    "amber_dusk": {"palette": "amber", "key_rot": 60, "exposure": 0.96, "rim": [1.0, 0.8, 0.55]},
    "crimson": {"palette": "crimson", "key_rot": -55, "exposure": 0.95, "rim": [1.0, 0.6, 0.6]},
    "steel": {"palette": "steel", "key_rot": 15, "exposure": 1.04, "rim": [0.8, 0.9, 1.0]},
    "emerald": {"palette": "emerald", "key_rot": -15, "exposure": 1.0, "rim": [0.6, 1.0, 0.75]},
    "ocean": {"palette": "ocean", "key_rot": 80, "exposure": 1.0, "rim": [0.5, 0.8, 1.0]},
}
# lens: field of view factor. A telephoto flattens and isolates, a wide lens exaggerates depth; the subject keeps its size (fill keys refit, distance keys rescale)
LENSES: Dict[str, float] = {"normal": 1.0, "tele": 0.62, "wide": 1.5}
RECENT = 4      # a new video avoids the looks and moves this subject had in its last RECENT videos
HISTORY = Path(os.environ.get("HEALTH_CINEMA_VARIETY_HISTORY", str(Path.home() / ".semantic_yt_studio" / "health_cinema" / "variety_history.json")))
_LOCK = threading.Lock()


def video_key(script: str, title: str = "") -> str:
    """One video = one key: its script (and title). The same script rendered again is the same video; a new script is a new video."""
    return hashlib.sha256(("\x1f".join([title.strip(), " ".join(script.split())])).encode()).hexdigest()[:16]


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"used": {}, "videos": {}}


def _save(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True); tmp = path.with_suffix(".tmp"); tmp.write_text(json.dumps(data), encoding="utf-8"); os.replace(tmp, path)
    except OSError:
        pass      # a read-only home only loses the cross-video memory, never the render


def fingerprint(subject: str, move: str, look: str, lens: str = "normal") -> str:
    return f"{subject}|{move}|{look}|{lens}"


def choose(subjects: List[str], key: str, *, body: Optional[List[bool]] = None, history: Path = HISTORY, record: bool = True) -> List[dict]:
    """One direction per 3D scene ({move, look, fp}), in scene order. `subjects` names what each scene shows (its template); `body` marks body-map scenes
    (their camera follows the beats: they only get a look). A video seen before gets its stored directions back."""
    body = body or [False] * len(subjects)
    with _LOCK:
        data = _load(history); mine = data["videos"].get(key) or []
        kept: Dict[tuple, dict] = {}      # (subject, n-th time in the video) -> the direction it already has: an edited video keeps every unchanged scene's look (and its cached clip)
        cnt: Dict[str, int] = {}
        for d in mine:
            n = cnt.get(d.get("subject"), 0); cnt[d.get("subject")] = n + 1; kept[(d.get("subject"), n)] = d
        used_elsewhere = {fp for fp, rec in data["used"].items() if rec.get("video") != key}
        recent: Dict[str, List[tuple]] = {}      # subject -> [(move, look, lens)] of the latest other videos, newest first
        for fp, rec in sorted(data["used"].items(), key=lambda kv: -kv[1].get("t", 0)):
            if rec.get("video") == key: continue
            parts = fp.split("|"); subj = parts[0]
            if len(recent.setdefault(subj, [])) < RECENT: recent[subj].append(tuple(parts[1:4]) + (("normal",) if len(parts) < 4 else ()))
        out, taken, seen_n = [], {d["fp"] for d in kept.values() if d.get("fp")}, {}
        for i, (subj, is_body) in enumerate(zip(subjects, body)):
            nth = seen_n.get(subj, 0); seen_n[subj] = nth + 1
            if (subj, nth) in kept: out.append(dict(kept[(subj, nth)])); continue
            rng = random.Random(f"{key}:{subj}:{nth}")
            moves = ["as_designed"] if is_body else list(MOVES); looks = list(LOOKS); lenses = ["normal"] if is_body else list(LENSES)
            combos = [(m, l, z) for m in moves for l in looks for z in lenses]; rng.shuffle(combos)
            if not is_body and i == 0: combos.sort(key=lambda c: c[0] == "as_designed")      # the designed move is one option among many, never the default
            fresh = [c for c in combos if fingerprint(subj, *c) not in used_elsewhere and fingerprint(subj, *c) not in taken]
            seen = recent.get(subj, []); prev = out[-1] if out else None
            def score(c):      # lower is better: unlike this subject's recent videos and unlike the scene just before
                return (sum(c[1] == r[1] for r in seen) * 3 + sum(c[0] == r[0] for r in seen) * 2 + sum(c[2] == r[2] for r in seen[:1])
                        + (4 if prev and c[1] == prev["look"] else 0) + (3 if prev and c[0] == prev["move"] else 0))
            pick = min(fresh, key=score) if fresh else None      # combos are shuffled: equal scores are broken by the video's own seed
            if pick is None:      # every combination for this subject has been used: take the one used longest ago
                ages = {fp: rec.get("t", 0) for fp, rec in data["used"].items()}
                pick = min(combos, key=lambda c: ages.get(fingerprint(subj, *c), 0))
            fp = fingerprint(subj, *pick); taken.add(fp)
            seed = int(hashlib.sha256(f"{key}:{subj}:{nth}".encode()).hexdigest()[:8], 16) % 1000003      # drawn scenes (conditions, procedural) lay themselves out from this: new in every video
            out.append({"subject": subj, "move": pick[0], "look": pick[1], "lens": pick[2], "fp": fp, "seed": seed})
        now = time.time()
        for d in out: data["used"][d["fp"]] = {"video": key, "t": now}
        data["videos"][key] = out
        if record: _save(history, data)      # a preview or a test run directs the same way but is not remembered as a published video
        return [dict(d) for d in out]


def assign(scenes, script: str, title: str = "", history: Path = HISTORY, log=lambda m: None, key: Optional[str] = None, record: bool = True) -> None:
    """Give every 3D scene of a planned video its direction (sc.visual['direction']). `key` names the video (the engine passes its project folder, so editing
    the script keeps the video's identity: unchanged scenes keep their directions); without it the script and title name it."""
    three = [sc for sc in scenes if getattr(sc, "kind", "") == "anatomy_3d" and (sc.visual.get("template") or sc.visual.get("body_rows"))]
    if not three: return
    subj = [sc.visual.get("template") or "body_map" for sc in three]
    dirs = choose(subj, key or video_key(script, title), body=[bool(sc.visual.get("body_rows")) for sc in three], history=history, record=record)
    k = key or video_key(script, title)
    for sc, d in zip(three, dirs): sc.visual["direction"] = dict(d, video=k, record=bool(record))      # the render's uniqueness check needs to know whose clip it is
    log("3D directions: " + ", ".join(f"{d['subject']}={d['move']}/{d['look']}/{d.get('lens', 'normal')}" for d in dirs))


def apply(spec: dict, direction: Optional[dict]) -> dict:
    """The spec filmed and lit the chosen way (a new dict; the template is not changed). No direction = unchanged."""
    if not direction: return spec
    from . import library
    s = json.loads(json.dumps(spec)); mv = MOVES.get(direction.get("move"), MOVES["as_designed"]); lk = LOOKS.get(direction.get("look"), LOOKS["midnight"])
    az0, daz, el0, del_, z0, z1 = mv; D = float(s.get("duration") or 1.0)
    if not s.get("body_camera_locked"):
        for k in s.get("camera", []):
            u = min(1.0, max(0.0, k["t"] / D)); z = z0 + (z1 - z0) * u
            k["az"] = round(k["az"] + az0 + daz * u, 3); k["el"] = round(max(-12.0, min(40.0, k["el"] + el0 + del_ * u)), 3)
            if "fill" in k: k["fill"] = round(min(library.FILL_MAX, max(0.2, k["fill"] * z)), 4)
            elif "dist" in k: k["dist"] = round(k["dist"] / max(0.5, z), 4)
    zf = LENSES.get(direction.get("lens", "normal"), 1.0)
    if zf != 1.0:
        import math
        for k in s.get("camera", []):
            f0 = k["fov"]; k["fov"] = round(max(14.0, min(55.0, f0 * zf)), 3)
            if "dist" in k: k["dist"] = round(k["dist"] * math.tan(math.radians(f0 / 2)) / math.tan(math.radians(k["fov"] / 2)), 4)      # same size on screen through the other lens
    if "procedural" in s and direction.get("seed") is not None:
        s["procedural"]["seed"] = int(direction["seed"]); s["procedural"]["variant"] = int(direction["seed"]) % 97 or 1
    s["palette"] = lk["palette"]; s["key_rot"] = lk["key_rot"]; s["exposure"] = round(float(s.get("exposure", 1.0)) * lk["exposure"], 4)
    if lk["rim"]:
        for g in s.get("glow", []):
            if g.get("color") and max(g["color"]) > 0.5 and min(g["color"]) > 0.4: g["color"] = lk["rim"]      # the cool hologram rims take the mood's tint; red/disease glows keep theirs
    s["id"] = f"{s.get('id', '')}_{direction.get('move')}_{direction.get('look')}_{direction.get('lens', 'normal')}"
    s["direction"] = {"move": direction.get("move"), "look": direction.get("look"), "lens": direction.get("lens", "normal")}
    return s


# ---- uniqueness check: a finished video's 3D clips are compared, frame by frame, with every earlier video's clips of the same subject ----
SAMPLE_AT = (0.3, 0.6, 0.9)      # where in a clip its frames are sampled
NEAR_BITS = 6                    # two 64-bit frame hashes this close (or closer) show the same picture
NEAR_FRAMES = 2                  # ... and a clip this many near frames like one earlier clip is "the same clip again"


def frame_hashes(path: str, ffmpeg: str = "ffmpeg") -> List[int]:
    """64-bit difference hashes of a clip's frames at SAMPLE_AT (a 9x8 grey thumbnail: each bit says whether a pixel is brighter than its right neighbour)."""
    import subprocess
    try:
        dur = float(subprocess.run([ffmpeg.replace("ffmpeg", "ffprobe") if "ffmpeg" in ffmpeg else "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                   capture_output=True, text=True, timeout=60).stdout.strip() or 0)
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    out = []
    for u in SAMPLE_AT:
        try:
            px = subprocess.run([ffmpeg, "-v", "error", "-ss", f"{dur * u:.3f}", "-i", path, "-frames:v", "1", "-vf", "scale=9:8:flags=area,format=gray", "-f", "rawvideo", "-"],
                                capture_output=True, timeout=60).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        if len(px) < 72: continue
        h = 0
        for y in range(8):
            for x in range(8): h = (h << 1) | (1 if px[y * 9 + x] > px[y * 9 + x + 1] else 0)
        out.append(h)
    return out


def too_similar(direction: dict, hashes: List[int], history: Path = HISTORY) -> Optional[str]:
    """The fingerprint of an earlier video's clip of the same subject that these frames repeat, or None."""
    if not hashes or not direction: return None
    data = _load(history); subj, key = direction.get("subject"), direction.get("video")
    for rec in data.get("frames", []):
        if rec.get("subject") != subj or rec.get("video") == key: continue
        near = sum(1 for h in hashes if any(bin(h ^ g).count("1") <= NEAR_BITS for g in rec.get("h", [])))
        if near >= NEAR_FRAMES: return rec.get("fp")
    return None


def remember_frames(direction: dict, hashes: List[int], history: Path = HISTORY) -> None:
    if not hashes or not direction or not direction.get("record"): return
    with _LOCK:
        data = _load(history); fr = [r for r in data.get("frames", []) if not (r.get("video") == direction.get("video") and r.get("fp") == direction.get("fp"))]
        fr.append({"subject": direction.get("subject"), "video": direction.get("video"), "fp": direction.get("fp"), "h": hashes, "t": time.time()})
        data["frames"] = fr[-20000:]; _save(history, data)      # about a year of videos at 60 a month


def reroll(direction: dict, avoid: List[str], history: Path = HISTORY) -> dict:
    """Another direction for the same scene: none of `avoid` (the fingerprints that came out too similar), unused elsewhere if possible."""
    subj, key = direction.get("subject"), direction.get("video") or "reroll"
    with _LOCK:
        data = _load(history); used = {fp for fp, rec in data["used"].items() if rec.get("video") != key} | set(avoid) | {direction.get("fp")}
        rng = random.Random(f"{key}:{subj}:reroll:{len(avoid)}")
        is_body = direction.get("move") == "as_designed" and subj == "body_map"
        combos = [(m, l, z) for m in (["as_designed"] if is_body else list(MOVES)) for l in LOOKS for z in (["normal"] if is_body else list(LENSES))]; rng.shuffle(combos)
        # the new one should differ in the look AND the move from the one that repeated
        combos.sort(key=lambda c: (c[1] == direction.get("look")) + (c[0] == direction.get("move")))
        pick = next((c for c in combos if fingerprint(subj, *c) not in used), combos[0])
        new = dict(direction, move=pick[0], look=pick[1], lens=pick[2], fp=fingerprint(subj, *pick), seed=(int(direction.get("seed") or 0) * 31 + 7) % 1000003)
        if direction.get("record"):
            data["used"][new["fp"]] = {"video": key, "t": time.time()}
            vids = data["videos"].get(key) or []
            for i, d in enumerate(vids):
                if d.get("fp") == direction.get("fp"): vids[i] = {k: v for k, v in new.items() if k not in ("video", "record")}
            _save(history, data)
        return new
