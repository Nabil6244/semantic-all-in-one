"""Story Motion sound design: one plan (music bed that follows the story's energy, room/ambience beds per location, whooshes and hits only
at intentional joins) and one ffmpeg pass that mixes it under the UNTOUCHED narration.

    plan = build_plan(shots, duration)                    # pure + deterministic, no audio decoded, no ffmpeg
    info = render_mix(plan, voiceover_wav, out_path)      # out_path .wav/.flac/.m4a ; falls back to narration only on any failure

Reuses what the repo already ships: the Kevin MacLeod beds in assets/music (starmap.music.TRACKS), the curated Sonniss ambience / whoosh /
impact / riser / transition samples in assets/bundled-sfx/catalog.json, sfx.ambience_profiles for profile names, and the same sidechain
ducking starmap.music uses (down in 40 ms when the voice starts, back in 300 ms in the gaps). The narration is only up-mixed to stereo:
its samples and timing are never changed (film_qa measures that afterwards).

Memory/time for 45 minutes: the sparse effects/ambience stem is written in 60 s windows (never more than a few decoded samples in RAM);
the music is NOT pre-rendered, its segments are inputs of the one final ffmpeg graph (streaming)."""
from __future__ import annotations

import hashlib, json, math, os, re, struct, subprocess, sys, tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
SR = 44100
PLAN_VERSION = "sf-sound-1"
CACHE_DIR = ROOT / "out" / "story_fast_cache" / "sound"

# --------------------------------------------------------------------------------------------- music
# energy 1 (calm drone) .. 5 (driving). `dark`: only when the words are tense. Titles/moods are starmap.music.TRACKS; this table only adds energy.
TRACK_ENERGY = {
    "long_note_four": (1.0, False), "echoes_of_time_v2": (1.6, False), "dark_fog": (1.6, True), "lost_frontier": (2.6, False),
    "interloper": (2.6, True), "ascending_the_vale": (3.5, False), "stormfront": (4.5, True), "despair_and_triumph": (4.5, False),
}
# music bed level (LUFS of the bed BEFORE ducking) by energy class; the voice sits at about -18 LUFS and the sidechain takes ~9 dB more while it speaks
MUSIC_LUFS = {"low": -33.0, "mid": -30.0, "high": -27.0}
QUIET_DB = -3.0                       # extra dip where the narration needs the room (calm emotional passages)
XFADE_S = 4.0                          # crossfade between two music segments
MIN_SECTION_S = 40.0
TENSE = re.compile(r"\b(debt|fear|panic|crash|lost|loss|broke|anxious|worry|worried|danger|risk|trap|fail\w*|collapse|crisis|scam|stress\w*|bankrupt\w*)\b", re.I)
WARM = re.compile(r"\b(hope|freedom|grow\w*|win|won|success\w*|calm|peace|safe|secure\w*|finally|dream\w*|built|saved|free)\b", re.I)

# --------------------------------------------------------------------------------------------- ambience
LOC_PROFILE = {"room": "room", "market": "crowd", "sky": "atmospheric", "river": "water", "mountain": "nature", "road": "traffic",
               "city": "city", "office": "room", "unknown": "room"}
ENV_PROFILE = {"rain": "rain", "snow": "atmospheric"}
AMBIENCE_LUFS = -41.0                  # target of an ambience bed on its own (the curated samples are about -34 LUFS)
MIN_BED_S, MAX_BED_S, BED_XFADE_S = 12.0, 55.0, 3.0

# --------------------------------------------------------------------------------------------- sfx
SFX_LEVEL_DB = {"whoosh": -26.0, "transition": -27.0, "impact": -23.0, "riser": -29.0}   # target RMS (dBFS) of the sample as placed
MIN_GAP_S = 6.0                        # two effects never closer than this (so each one is heard as intentional)
MAX_PER_MIN = 3
SOFT_TRANSITIONS = ("dissolve", "soft", "fade")


def _f(x, d=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _h(*parts) -> int:
    return int(hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:8], 16)


# --------------------------------------------------------------------------------------------- libraries
def sfx_catalog(root: Optional[Path] = None) -> dict:
    """{category: [entry]} from the bundled catalog (entries get an absolute `path`). Missing files are dropped."""
    base = Path(root) if root else ROOT / "assets" / "bundled-sfx"
    out: Dict[str, List[dict]] = {}
    try:
        data = json.loads((base / "catalog.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    for e in data.get("sfx", []):
        p = base / e.get("file", "")
        if p.is_file():
            out.setdefault(e.get("category", ""), []).append(dict(e, path=str(p)))
    return out


def music_tracks(folder: Optional[Path] = None) -> List[dict]:
    """The shipped beds: [{stem, title, path, energy, dark}] (only files that exist)."""
    try:
        from starmap.music import TRACKS, music_dir
        d = Path(folder) if folder else music_dir()
        titles = {k: v[0] for k, v in TRACKS.items()}
    except Exception:
        d = Path(folder) if folder else ROOT / "assets" / "music"
        titles = {}
    out = []
    for stem, (en, dark) in TRACK_ENERGY.items():
        p = d / f"{stem}.opus"
        if p.is_file():
            out.append({"stem": stem, "title": titles.get(stem, stem), "path": str(p), "energy": en, "dark": dark})
    return out


# --------------------------------------------------------------------------------------------- plan: music
def _shot_energy(sh: dict) -> float:
    e = _f(sh.get("energy"), 3.0)
    g = str(sh.get("genre") or "")
    if g == "emotional":
        e -= 0.3
    elif g == "action":
        e += 0.3
    return e


def energy_curve(shots: Sequence[dict], duration: float, step: float = 5.0, radius: float = 22.0) -> List[float]:
    """Duration-weighted moving average of the shots' energy on a `step` grid (one value per step)."""
    n = max(1, int(math.ceil(duration / step)))
    raw = [3.0] * n
    for sh in shots:
        a, b = _f(sh.get("start")), _f(sh.get("end"))
        for k in range(int(a // step), min(n, int(math.ceil(b / step)))):
            raw[k] = _shot_energy(sh)
    r = max(1, int(radius / step))
    return [sum(raw[max(0, k - r):k + r + 1]) / len(raw[max(0, k - r):k + r + 1]) for k in range(n)]


def _class_of(e: float) -> str:
    return "low" if e < 2.55 else "high" if e >= 3.25 else "mid"


def music_sections(shots: Sequence[dict], duration: float, step: float = 5.0) -> List[dict]:
    """Sections of one energy class each (hysteresis + a minimum length) -> [{start,end,cls,energy,tense}]."""
    curve = energy_curve(shots, duration, step)
    srt = sorted(curve)
    q = lambda f: srt[min(len(srt) - 1, int(f * len(srt)))]
    if len(srt) >= 8 and q(0.9) - q(0.1) >= 0.3:         # the director's energy is often flat (mostly 3): rank within the film so it still has an arc
        lo, hi = q(0.3), q(0.7)
        cls = ["low" if e <= lo else "high" if e >= hi else "mid" for e in curve]
    else:
        cls = [_class_of(e) for e in curve]
    runs: List[list] = []
    for k, c in enumerate(cls):
        if runs and runs[-1][0] == c:
            runs[-1][2] = k + 1
        else:
            runs.append([c, k, k + 1])
    changed = True
    while changed and len(runs) > 1:                 # merge runs shorter than MIN_SECTION_S into the stronger neighbour
        changed = False
        for i, r in enumerate(runs):
            if (r[2] - r[1]) * step < MIN_SECTION_S:
                nb = i - 1 if i > 0 and (i == len(runs) - 1 or (runs[i - 1][2] - runs[i - 1][1]) >= (runs[i + 1][2] - runs[i + 1][1])) else i + 1
                lo, hi = sorted((i, nb))
                runs[lo:hi + 1] = [[runs[nb][0], runs[lo][1], runs[hi][2]]]
                changed = True
                break
    out = []
    for c, k0, k1 in runs:
        a, b = k0 * step, min(duration, k1 * step)
        seg = curve[k0:k1]
        txt = " ".join(str(s.get("text") or "") for s in shots if _f(s.get("end")) > a and _f(s.get("start")) < b)
        out.append({"start": round(a, 2), "end": round(b if k1 * step < duration else duration, 2), "cls": c,
                    "energy": round(sum(seg) / max(1, len(seg)), 2), "tense": len(TENSE.findall(txt)) >= 2 and len(TENSE.findall(txt)) > len(WARM.findall(txt))})
    if out:
        out[0]["start"], out[-1]["end"] = 0.0, round(duration, 2)
    return out


def _quiet_windows(shots: Sequence[dict]) -> List[tuple]:
    """Where the narration needs the room: calm emotional shots (energy <= 2) and runs of them merged."""
    w: List[list] = []
    for sh in shots:
        if _f(sh.get("energy"), 3) <= 2 and str(sh.get("genre")) == "emotional":
            a, b = _f(sh.get("start")), _f(sh.get("end"))
            if w and a - w[-1][1] < 1.0:
                w[-1][1] = b
            else:
                w.append([a, b])
    return [(a, b) for a, b in w if b - a >= 3.0]


def plan_music(shots: Sequence[dict], duration: float, tracks: Optional[List[dict]] = None, no_repeat_s: float = 480.0, seed: int = 0) -> List[dict]:
    tracks = music_tracks() if tracks is None else tracks
    if not tracks or duration < 8:
        return []
    secs = music_sections(shots, duration)
    last_used: Dict[str, float] = {}
    segs: List[dict] = []
    prev_stem = None
    quiet = _quiet_windows(shots)
    for si, sec in enumerate(secs):
        t = sec["start"]
        while t < sec["end"] - 0.01:
            want = 1.4 + (sec["energy"] - 2.0) * 1.3 + {"low": -0.5, "mid": 0.0, "high": 0.7}[sec["cls"]]   # absolute energy, nudged by the section's rank in the film
            want = max(1.0, min(4.5, want))
            if si == 0:
                want = min(want, 2.7)                      # the film opens calm: the music enters low and builds

            def cost(tr):
                c = abs(tr["energy"] - want)
                if tr["dark"] and not sec["tense"]:
                    c += 1.6
                if tr["stem"] == prev_stem:
                    c += 50
                age = t - last_used.get(tr["stem"], -1e9)
                if age < no_repeat_s:
                    c += 8 + (no_repeat_s - age) / no_repeat_s * 6
                return c + (_h(seed, tr["stem"], si, int(t)) % 100) / 1000.0
            tr = min(tracks, key=cost)
            length = _track_len(tr)
            used_before = last_used.get(tr["stem"])
            off = 0.0 if used_before is None else min(max(0.0, length - 60.0), (_h(seed, tr["stem"], "off") % 60) * 2.0)
            room = max(20.0, length - off - 6.0)
            end = min(sec["end"], t + room)
            if 0 < sec["end"] - end < 15.0 and sec["end"] - t <= room + 5.0:   # never leave a stub behind (but never run past the track's end)
                end = sec["end"]
            segs.append({"start": round(t, 2), "end": round(end, 2), "stem": tr["stem"], "title": tr["title"], "path": tr["path"],
                         "offset": round(off, 2), "cls": sec["cls"], "energy": sec["energy"], "tense": sec["tense"]})
            last_used[tr["stem"]] = end
            prev_stem = tr["stem"]
            t = end
    # level: class bed level, a gentle film arc (enter low, rise toward ~70%, settle at the end) and the quiet windows
    for s in segs:
        mid = (s["start"] + s["end"]) / 2.0 / max(1.0, duration)
        arc = -2.0 * max(0.0, 1.0 - mid / 0.2) + (-1.0 * max(0.0, (mid - 0.85) / 0.15))
        q = QUIET_DB if any(a <= (s["start"] + s["end"]) / 2 <= b for a, b in quiet) else 0.0
        s["target_lufs"] = round(MUSIC_LUFS[s["cls"]] + arc + q, 2)
    return segs


_LEN: Dict[str, float] = {}


def _track_len(tr: dict) -> float:
    p = tr["path"]
    if p not in _LEN:
        try:
            r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p], capture_output=True, text=True, timeout=30)
            _LEN[p] = float(r.stdout.strip())
        except Exception:
            _LEN[p] = 240.0
    return _LEN[p]


# --------------------------------------------------------------------------------------------- plan: ambience
def shot_profile(sh: dict) -> str:
    env = [str(e) for e in (sh.get("env") or [])]
    for e in env:
        if e in ENV_PROFILE and e == "rain":
            return ENV_PROFILE[e]
    loc = str((sh.get("continuity") or {}).get("location") or "unknown")
    return LOC_PROFILE.get(loc, "room")


def plan_ambience(shots: Sequence[dict], duration: float, cat: Optional[dict] = None, no_repeat_s: float = 360.0, seed: int = 0) -> List[dict]:
    cat = sfx_catalog() if cat is None else cat
    pool_all = cat.get("ambience", [])
    if not pool_all or not shots:
        return []
    runs: List[dict] = []
    for sh in shots:
        pr = shot_profile(sh)
        a, b = _f(sh.get("start")), _f(sh.get("end"))
        if runs and runs[-1]["profile"] == pr:
            runs[-1]["end"] = b
        else:
            runs.append({"profile": pr, "start": a, "end": b, "loc": (sh.get("continuity") or {}).get("location")})
    merged: List[dict] = []                           # a location visit shorter than MIN_BED_S keeps the previous bed running
    for r in runs:
        if merged and (r["end"] - r["start"] < MIN_BED_S or merged[-1]["profile"] == r["profile"]):
            merged[-1]["end"] = r["end"]
        else:
            merged.append(dict(r))
    if len(merged) > 1 and merged[0]["end"] - merged[0]["start"] < MIN_BED_S:
        merged[1]["start"] = merged[0]["start"]
        merged.pop(0)
    merged[0]["start"], merged[-1]["end"] = 0.0, duration
    last_used: Dict[str, float] = {}
    beds: List[dict] = []
    for r in merged:
        t = r["start"]
        while t < r["end"] - 0.5:
            end = min(r["end"], t + MAX_BED_S)
            if r["end"] - end < MIN_BED_S:
                end = r["end"] if r["end"] - t <= MAX_BED_S + MIN_BED_S - 1 else end
            pool = [e for e in pool_all if (e.get("tags") or [""])[0] == r["profile"]] or [e for e in pool_all if r["profile"] in (e.get("tags") or [])] \
                or [e for e in pool_all if (e.get("tags") or [""])[0] == "room"] or pool_all
            e = min(pool, key=lambda x: (t - last_used.get(x["id"], -1e9) < no_repeat_s, last_used.get(x["id"], -1e9), _h(seed, x["id"], int(t))))
            last_used[e["id"]] = end
            span = end - t
            off = 0.0 if e["duration"] <= span + BED_XFADE_S * 2 else (_h(seed, e["id"], int(t)) % int(max(1, e["duration"] - span - BED_XFADE_S * 2)))
            beds.append({"start": round(t, 2), "end": round(end, 2), "profile": r["profile"], "location": r["loc"], "sample": e["id"], "path": e["path"],
                         "sample_lufs": _f(e.get("loudness_lufs"), -34.0), "sample_dur": _f(e["duration"]), "offset": float(off),
                         "gain_db": round(max(-24.0, min(12.0, AMBIENCE_LUFS - _f(e.get("loudness_lufs"), -34.0))), 2)})
            t = end
    return beds


# --------------------------------------------------------------------------------------------- plan: sfx
def _pick_sfx(cat: dict, kinds: Sequence[str], want_dur: tuple, last: Dict[str, float], t: float, no_repeat_s: float, seed: int, tag_pref: Sequence[str] = ()) -> Optional[dict]:
    pool = [e for k in kinds for e in cat.get(k, []) if want_dur[0] <= _f(e.get("duration")) <= want_dur[1]]
    if not pool:
        return None
    return min(pool, key=lambda e: (t - last.get(e["id"], -1e9) < no_repeat_s, -sum(1 for g in tag_pref if g in (e.get("tags") or [])), last.get(e["id"], -1e9), _h(seed, e["id"], int(t))))


def plan_sfx(shots: Sequence[dict], duration: float, cat: Optional[dict] = None, no_repeat_s: float = 240.0, seed: int = 0) -> List[dict]:
    """Effects only where a join is intentional: a flash / zoom-blur join, a soft join that is also a change of location, a strong move at a high-energy
    beat, and a riser + hit into a climax. Never closer than MIN_GAP_S, never more than MAX_PER_MIN, never in the first 2 s, never in calm emotional shots."""
    cat = sfx_catalog() if cat is None else cat
    if not cat:
        return []
    cand: List[dict] = []
    for i, sh in enumerate(shots):
        t = _f(sh.get("start"))
        prev = shots[i - 1] if i else None
        tr = str(sh.get("transition_in") or "cut")
        en = _f(sh.get("energy"), 3)
        calm = str(sh.get("genre")) == "emotional" and en <= 2
        newloc = bool(prev) and not (sh.get("continuity") or {}).get("same_location_as_prev", True)
        dur = _f(sh.get("end")) - t
        kind, pri, why = None, 0.0, ""
        if tr == "flash":
            kind, pri, why = ("impact" if en >= 4 else "whoosh"), 5.0, "flash join"
        elif tr == "zoom_blur":
            kind, pri, why = "whoosh", 4.5, "zoom-blur join"
        elif tr in SOFT_TRANSITIONS and newloc and not calm:
            kind, pri, why = "transition", 3.0 + (0.5 if tr == "fade" else 0.0), f"{tr} into a new location"
        elif str(sh.get("treatment")) in ("dolly_through", "track_lateral", "arc") and en >= 3 and dur >= 2.0 and not calm and tr == "cut":
            kind, pri, why = "whoosh", 2.0 + 0.2 * en, f"strong {sh.get('treatment')} move"
        if en >= 4 and prev and _f(prev.get("energy"), 3) <= 3 and not calm and kind is None:
            kind, pri, why = "impact", 4.0, "step up to a high-energy beat"
        if kind and t >= 2.0 and not calm:
            cand.append({"i": i, "t": t, "kind": kind, "pri": pri, "why": why, "shot_id": sh.get("shot_id"), "energy": en, "prev_dur": _f(prev.get("end")) - _f(prev.get("start")) if prev else 0})
    cand.sort(key=lambda c: (-c["pri"], c["t"]))
    chosen: List[dict] = []
    for c in cand:                                   # strongest first, so a weak join never blocks a strong one
        if any(abs(c["t"] - o["t"]) < MIN_GAP_S for o in chosen):
            continue
        minute = int(c["t"] // 60)
        if sum(1 for o in chosen if int(o["t"] // 60) == minute) >= MAX_PER_MIN:
            continue
        chosen.append(c)
    chosen.sort(key=lambda c: c["t"])
    last: Dict[str, float] = {}
    events: List[dict] = []
    for c in chosen:
        k = c["kind"]
        soft = k == "transition"
        e = _pick_sfx(cat, (k,) if not soft else ("transition", "whoosh"), (0.25, 3.2) if k != "impact" else (0.2, 2.6), last, c["t"], no_repeat_s, seed,
                      tag_pref=("soft", "sweep") if soft else ("fast",) if k == "whoosh" else ("punch", "cinematic"))
        if e is None:
            continue
        last[e["id"]] = c["t"]
        d = _f(e["duration"])
        lead = min(d * 0.4, 0.45) if k in ("whoosh", "transition") else 0.0   # the sweep peaks at the join, not after it
        ev = {"t": round(c["t"], 3), "start": round(max(0.0, c["t"] - lead), 3), "kind": k, "sample": e["id"], "path": e["path"], "sample_dur": d,
              "gain_db": round(max(-18.0, min(6.0, SFX_LEVEL_DB[k] - _f(e.get("loudness_db"), -21.0) - (4.0 if soft else 0.0))), 2),
              "fade_out": round(min(0.6, d * 0.35), 3), "why": c["why"], "shot_id": c["shot_id"]}
        events.append(ev)
        # a riser into a climax hit: only when the previous shot is long enough to hold it
        if k == "impact" and c["energy"] >= 4.5 and c["prev_dur"] >= 3.0:
            r = _pick_sfx(cat, ("riser",), (0.9, min(5.6, c["prev_dur"] - 0.3)), last, c["t"], no_repeat_s, seed, tag_pref=("tension",))
            if r is not None and not any(abs(c["t"] - o["t"]) < MIN_GAP_S and o is not ev for o in events if o["kind"] == "riser"):
                rd = _f(r["duration"])
                last[r["id"]] = c["t"]
                events.append({"t": round(c["t"], 3), "start": round(c["t"] - rd, 3), "kind": "riser", "sample": r["id"], "path": r["path"], "sample_dur": rd,
                               "gain_db": round(max(-18.0, min(6.0, SFX_LEVEL_DB["riser"] - _f(r.get("loudness_db"), -21.0))), 2), "fade_out": 0.05,
                               "why": "riser into climax hit", "shot_id": c["shot_id"]})
    events.sort(key=lambda e: e["start"])
    return events


# --------------------------------------------------------------------------------------------- the plan
def build_plan(shots: Sequence[dict], duration: float, seed: int = 0, music: bool = True, ambience: bool = True, sfx: bool = True,
               tracks: Optional[List[dict]] = None, catalog: Optional[dict] = None) -> dict:
    """Everything the mixer needs, as plain JSON. `shots` = direct.json shots (start/end/text/genre/energy/treatment/transition_in/continuity/env)."""
    shots = [dict(s, end=min(_f(s.get("end")), float(duration))) for s in shots if _f(s.get("start")) < float(duration)]
    shots = [s for s in shots if _f(s.get("end")) > _f(s.get("start"))]
    cat = sfx_catalog() if catalog is None else catalog
    plan = {"version": PLAN_VERSION, "duration": round(float(duration), 3), "seed": int(seed),
            "music": plan_music(shots, duration, tracks, seed=seed) if music else [],
            "ambience": plan_ambience(shots, duration, cat, seed=seed) if ambience else [],
            "sfx": plan_sfx(shots, duration, cat, seed=seed) if sfx else [],
            "duck": {"threshold": 0.025, "ratio": 8, "attack_ms": 40, "release_ms": 300}}
    plan["stats"] = plan_stats(plan)
    return plan


def plan_stats(plan: dict) -> dict:
    d = max(1.0, plan["duration"])
    per_min = len(plan["sfx"]) / (d / 60.0)
    ids = [s["stem"] for s in plan["music"]]
    hits = [e for e in plan["sfx"] if e["kind"] != "riser"]
    gaps = [b["t"] - a["t"] for a, b in zip(hits, hits[1:])]
    return {"music_segments": len(plan["music"]), "music_tracks": sorted(set(ids)), "music_coverage": round(sum(s["end"] - s["start"] for s in plan["music"]) / d, 3),
            "ambience_beds": len(plan["ambience"]), "ambience_samples": len({b["sample"] for b in plan["ambience"]}), "sfx": len(plan["sfx"]),
            "sfx_per_min": round(per_min, 2), "sfx_min_gap_s": round(min(gaps), 2) if gaps else None,
            "sfx_kinds": {k: sum(1 for e in plan["sfx"] if e["kind"] == k) for k in sorted({e["kind"] for e in plan["sfx"]})}}


def check_plan(plan: dict) -> List[str]:
    """Rule violations of a plan (empty = obeys its own limits)."""
    bad = []
    ev = [e for e in plan["sfx"] if e["kind"] != "riser"]
    for a, b in zip(ev, ev[1:]):
        if b["t"] - a["t"] < MIN_GAP_S - 1e-6:
            bad.append(f"sfx {a['sample']}@{a['t']} and {b['sample']}@{b['t']} closer than {MIN_GAP_S}s")
    by_min: Dict[int, int] = {}
    for e in ev:
        by_min[int(e["t"] // 60)] = by_min.get(int(e["t"] // 60), 0) + 1
    bad += [f"minute {m}: {n} sfx > {MAX_PER_MIN}" for m, n in by_min.items() if n > MAX_PER_MIN]
    segs = plan["music"]
    for a, b in zip(segs, segs[1:]):
        if abs(a["end"] - b["start"]) > 0.05:
            bad.append(f"music gap/overlap {a['end']} -> {b['start']}")
        if a["stem"] == b["stem"]:
            bad.append(f"same track twice in a row at {b['start']}")
    for a, b in zip(plan["ambience"], plan["ambience"][1:]):
        if abs(a["end"] - b["start"]) > 0.05:
            bad.append(f"ambience gap/overlap {a['end']} -> {b['start']}")
    return bad


# --------------------------------------------------------------------------------------------- decode / measure
def _run(cmd: List[str], **kw) -> subprocess.CompletedProcess:
    try:
        from providers import hidden_subprocess
        return hidden_subprocess.run(cmd, **kw)
    except ImportError:
        return subprocess.run(cmd, **kw)


def decode(path: str, start: float = 0.0, dur: Optional[float] = None, ffmpeg: str = "ffmpeg"):
    """Float32 stereo array [n,2] at 44.1 kHz."""
    import numpy as np
    cmd = [ffmpeg, "-v", "error", "-ss", f"{start:.3f}"] + (["-t", f"{dur:.3f}"] if dur else []) + ["-i", path, "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"]
    r = _run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or b"").decode("utf-8", "ignore")[-300:])
    return np.frombuffer(r.stdout, dtype="<f4").reshape(-1, 2).copy()


def measure_lufs(path: str, ffmpeg: str = "ffmpeg", cache: Optional[Path] = None, seconds: float = 90.0) -> float:
    """Integrated loudness of the first `seconds` of a file (cached by path+size+mtime)."""
    cache = Path(cache) if cache else CACHE_DIR / "lufs.json"
    st = os.stat(path)
    key = f"{path}|{st.st_size}|{int(st.st_mtime)}|{int(seconds)}"
    try:
        c = json.loads(cache.read_text())
    except Exception:
        c = {}
    if key in c:
        return float(c[key])
    r = _run([ffmpeg, "-hide_banner", "-nostats", "-t", f"{seconds:.0f}", "-i", path, "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True)
    m = re.findall(r"I:\s*(-?[\d.]+)\s*LUFS", r.stderr or "")
    v = float(m[-1]) if m else -23.0
    if v < -69:                                   # silence reads as -70: treat as unmeasurable
        v = -23.0
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        c[key] = v
        cache.write_text(json.dumps(c))
    except OSError:
        pass
    return v


# --------------------------------------------------------------------------------------------- effects/ambience stem
def _env(n: int, fi: int, fo: int):
    import numpy as np
    e = np.ones(n, dtype=np.float32)
    fi, fo = min(fi, n), min(fo, n)
    if fi > 1:
        e[:fi] *= np.sin(np.linspace(0, math.pi / 2, fi, dtype=np.float32)) ** 2
    if fo > 1:
        e[n - fo:] *= np.cos(np.linspace(0, math.pi / 2, fo, dtype=np.float32)) ** 2
    return e


def _bed_audio(b: dict, ffmpeg: str):
    """The bed's samples (looped with a crossfade only if the sample is shorter than the bed)."""
    import numpy as np
    n = int((b["end"] - b["start"]) * SR) + 2 * int(BED_XFADE_S * SR)
    a = decode(b["path"], b["offset"], None, ffmpeg)
    if len(a) >= n:
        return a[:n]
    xf = min(len(a) // 4, int(1.5 * SR))
    out = a.copy()
    while len(out) < n:
        w = np.linspace(0, 1, xf, dtype=np.float32)[:, None]
        out = np.concatenate([out[:-xf], out[-xf:] * (1 - w) + a[:xf] * w, a[xf:]])
    return out[:n]


def _write_wav_header(f, frames: int):
    data = frames * 4
    f.write(b"RIFF" + struct.pack("<I", 36 + data) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 2, SR, SR * 4, 4, 16) + b"data" + struct.pack("<I", data))


def _fx_gain(a, it: dict) -> float:
    import numpy as np
    if len(a) == 0:
        return 0.0
    m = np.abs(a).max(1)
    live = a[m > 10 ** (-50 / 20)]
    rms = float(np.sqrt(np.mean(live ** 2))) if len(live) else 1e-4
    g = 10 ** (SFX_LEVEL_DB[it["kind"]] / 20.0) / max(rms, 1e-5) * (10 ** (-4.0 / 20) if it["why"].endswith("new location") else 1.0)
    g = min(g, 10 ** (-6.0 / 20) / max(float(m.max()), 1e-5), 10 ** (12 / 20.0))
    return float(g)


def render_fx_stem(plan: dict, out_wav: str, ffmpeg: str = "ffmpeg", window_s: float = 60.0, log: Callable[[str], None] = lambda s: None) -> dict:
    """Ambience beds + effects -> a 16-bit stereo 44.1 kHz wav of the full duration, written window by window."""
    import numpy as np
    D = plan["duration"]
    total = int(round(D * SR))
    stats = {"beds": 0, "events": 0, "skipped": []}
    items = []
    for b in plan["ambience"]:
        items.append(("bed", b["start"] - BED_XFADE_S / 2 if b["start"] > 0 else 0.0, b["end"] + BED_XFADE_S / 2, b))
    for e in plan["sfx"]:
        items.append(("fx", e["start"], e["start"] + e["sample_dur"], e))
    cache: Dict[str, object] = {}

    def audio_of(kind, it):
        key = kind + it["sample"] + str(it.get("offset", "")) + str(it["start"])
        if key not in cache:
            if len(cache) > 6:
                cache.pop(next(iter(cache)))
            cache[key] = _bed_audio(it, ffmpeg) if kind == "bed" else decode(it["path"], 0.0, None, ffmpeg)
        return cache[key]
    with open(out_wav, "wb") as f:
        _write_wav_header(f, total)
        pos = 0
        W = int(window_s * SR)
        while pos < total:
            n = min(W, total - pos)
            buf = np.zeros((n, 2), dtype=np.float32)
            t0, t1 = pos / SR, (pos + n) / SR
            for kind, a, b, it in items:
                if b <= t0 or a >= t1:
                    continue
                try:
                    au = audio_of(kind, it)
                except Exception as ex:                    # one broken sample must not stop the mix
                    stats["skipped"].append(f"{it['sample']}: {str(ex)[:80]}")
                    continue
                g = 10 ** (it["gain_db"] / 20.0)
                if kind == "bed":                          # the catalogue's loudness is not trusted: measure the sample (cached)
                    g = 10 ** (max(-24.0, min(12.0, AMBIENCE_LUFS - measure_lufs(it["path"], ffmpeg, seconds=60.0))) / 20.0)
                if kind == "fx":                           # measured, not catalogued: RMS of the sound part, peak kept under -6 dBFS
                    g = _fx_gain(au[:int(it["sample_dur"] * SR)], it)
                if kind == "bed":
                    s0 = int(round(a * SR))
                    seg = au[:int(round((b - a) * SR))]
                    seg = seg * _env(len(seg), int(BED_XFADE_S * SR) if a > 0 else int(2.0 * SR), int(BED_XFADE_S * SR) if b < D else int(3.0 * SR))[:, None]
                else:
                    s0 = int(round(it["start"] * SR))
                    seg = au[:int(it["sample_dur"] * SR)]
                    seg = seg * _env(len(seg), int(0.02 * SR), int(it["fade_out"] * SR))[:, None]
                lo, hi = max(s0, pos), min(s0 + len(seg), pos + n)
                if hi > lo:
                    buf[lo - pos:hi - pos] += seg[lo - s0:hi - s0] * g
            f.write((np.clip(buf, -1.0, 1.0) * 32767.0).astype("<i2").tobytes())
            pos += n
    stats["beds"], stats["events"] = len(plan["ambience"]), len(plan["sfx"])
    return stats


# --------------------------------------------------------------------------------------------- final mix
def _probe_duration(path: str) -> float:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return 0.0
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


_CODEC = {".wav": ["-c:a", "pcm_s16le"], ".flac": ["-c:a", "flac"], ".m4a": ["-c:a", "aac", "-b:a", "192k"], ".aac": ["-c:a", "aac", "-b:a", "192k"],
          ".mp3": ["-c:a", "libmp3lame", "-b:a", "192k"]}


def _fallback(voice: str, out: str, ffmpeg: str, why: str) -> dict:
    r = _run([ffmpeg, "-v", "error", "-y", "-i", voice, "-vn", "-ar", str(SR)] + _CODEC.get(Path(out).suffix.lower(), _CODEC[".wav"]) + [out], capture_output=True, text=True)
    return {"ok": r.returncode == 0 and os.path.isfile(out), "fallback": True, "reason": why, "path": out}


def render_mix(plan: dict, voiceover: str, out_path: str, ffmpeg: str = "ffmpeg", work_dir: Optional[str] = None, log: Callable[[str], None] = lambda s: None) -> dict:
    """Voiceover + music (ducked under it) + ambience + effects -> `out_path`. The voice is only up-mixed to stereo (no gain, EQ, trim or delay).
    Returns {"ok", "fallback", "path", "credits", "seconds", ...}; on any failure the result is the narration alone (fallback=True, reason set)."""
    try:
        voice_dur = _probe_duration(voiceover)
        if voice_dur <= 0:
            return _fallback(voiceover, out_path, ffmpeg, "voiceover unreadable")
        D = float(plan.get("duration") or voice_dur)
        if abs(D - voice_dur) > 0.5:
            plan = dict(plan, duration=voice_dur)         # the mix is exactly as long as the voice
            D = voice_dur
        if not (plan.get("music") or plan.get("ambience") or plan.get("sfx")):
            return _fallback(voiceover, out_path, ffmpeg, "empty plan")
        tmp = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="sfsound_"))
        tmp.mkdir(parents=True, exist_ok=True)
        stem = tmp / "fx_stem.wav"
        fx_stats = {}
        have_fx = bool(plan.get("ambience") or plan.get("sfx"))
        if have_fx:
            fx_stats = render_fx_stem(plan, str(stem), ffmpeg, log=log)
        args = [ffmpeg, "-v", "error", "-y", "-i", voiceover]
        chain = ["[0:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,asplit=2[vo][key]"]
        n_in = 1
        labels = []
        segs = plan.get("music") or []
        for i, s in enumerate(segs):
            lufs = measure_lufs(s["path"], ffmpeg)
            g = s["target_lufs"] - lufs
            first, last = i == 0, i == len(segs) - 1
            pre = 0.0 if first else XFADE_S / 2
            post = 0.0 if last else XFADE_S / 2
            a = s["start"] - pre
            ln = (s["end"] + post) - a
            fin = 2.5 if first else XFADE_S
            fout = 5.0 if last else XFADE_S
            args += ["-ss", f"{s['offset']:.3f}", "-t", f"{ln:.3f}", "-i", s["path"]]
            ms = int(round(a * 1000))
            chain.append(f"[{n_in}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={g:.2f}dB,afade=t=in:st=0:d={fin}:curve=qsin,"
                         f"afade=t=out:st={max(0.0, ln - fout):.3f}:d={fout}:curve=qsin,adelay={ms}|{ms}[mu{i}]")
            labels.append(f"[mu{i}]")
            n_in += 1
        if labels:
            d = plan.get("duck", {})
            chain.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=longest,atrim=0:{D:.3f},asetpts=PTS-STARTPTS[bed]")
            chain.append(f"[bed][key]sidechaincompress=threshold={d.get('threshold', 0.025)}:ratio={d.get('ratio', 8)}:attack={d.get('attack_ms', 40)}:"
                         f"release={d.get('release_ms', 300)}:makeup=1[duck]")
            mix_in = ["[vo]", "[duck]"]
        else:
            chain[0] = chain[0].replace("asplit=2[vo][key]", "anull[vo]")
            mix_in = ["[vo]"]
        if have_fx:
            args += ["-i", str(stem)]
            chain.append(f"[{n_in}:a]aformat=sample_fmts=fltp:channel_layouts=stereo[fx]")
            mix_in.append("[fx]")
            n_in += 1
        chain.append("".join(mix_in) + f"amix=inputs={len(mix_in)}:normalize=0:duration=first,compand=attacks=0.002:decays=0.05:points=-90/-90|-2/-2|0/-2[out]")
        args += ["-filter_complex", ";".join(chain), "-map", "[out]", "-t", f"{D:.3f}", "-ar", str(SR)] + _CODEC.get(Path(out_path).suffix.lower(), _CODEC[".wav"]) + [out_path]
        r = _run(args, capture_output=True, text=True)
        if r.returncode != 0 or not os.path.isfile(out_path):
            return _fallback(voiceover, out_path, ffmpeg, "ffmpeg mix failed: " + (r.stderr or "")[-300:])
        try:
            stem.unlink()
        except OSError:
            pass
        credits = []
        try:
            from starmap.music import credit
            credits = [credit(s) for s in dict.fromkeys(x["stem"] for x in segs)]
        except Exception:
            pass
        return {"ok": True, "fallback": False, "path": out_path, "credits": credits, "seconds": D, "fx": fx_stats, "stats": plan.get("stats")}
    except Exception as ex:                                  # never lose the narration
        return _fallback(voiceover, out_path, ffmpeg, f"{type(ex).__name__}: {ex}")


def shots_from_direct(path: str) -> List[dict]:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    d = d.get("data", d)
    return list(d["shots"] if isinstance(d, dict) else d)


if __name__ == "__main__":      # python -m story_fast.sound direct.json voiceover.wav out.m4a [seconds]
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("direct"); ap.add_argument("voice"); ap.add_argument("out"); ap.add_argument("--seconds", type=float, default=0)
    ap.add_argument("--plan-only", action="store_true")
    a = ap.parse_args()
    shots = shots_from_direct(a.direct)
    dur = _probe_duration(a.voice)
    plan = build_plan(shots, dur)
    print(json.dumps(plan["stats"], indent=1)); print("violations:", check_plan(plan))
    if not a.plan_only:
        print(render_mix(plan, a.voice, a.out))
