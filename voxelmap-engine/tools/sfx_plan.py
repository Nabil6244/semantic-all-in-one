"""Scene sound design for a voxel map video: timeline.json -> sfx plan JSON -> stereo sfx stem.

    python3 tools/sfx_plan.py plan   timeline.json plan.json [--events events.json]
    python3 tools/sfx_plan.py render plan.json voiceover.wav sfx.wav

plan: one ambience bed per beat chosen by its site / rung. The bed starts when the camera arrives (travelT1) and
fades in over 1.5 s; the previous bed holds through the camera move (no dead air in the narration silence) and is
crossfaded out over the same 1.5 s (equal power). Battle-type beds add a seeded, irregular schedule of distant gunfire /
rumble (low-passed catalog impacts) that stops when the beat ends. No whooshes. Deterministic: every random choice is
drawn from sha256(beat id | site | rung), so the same timeline always gives the same plan.
events.json ([{t, kind: blast|plane|crowd}]) adds spot effects at those times.

render: levels are relative to the voice. The bed reference is (speech RMS - 16 dB) in the silences and is ducked by the
app's speech_duck (floor -6 dB, so ~22 dB under the voice during speech, +6 dB in the silences). Event peaks are
capped so they never exceed the voice's peak. Only files listed in assets/bundled-sfx/catalog.json are used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mix_audio import SR, decode, speech_duck, speech_rms  # noqa: E402

LIB = Path(__file__).resolve().parents[2] / "assets" / "bundled-sfx"
XFADE = 1.5
BED_DB = -16.0      # bed reference (unducked) relative to the voice's speech RMS
DUCK_DB = -6.0      # speech_duck floor: -16 + -6 = -22 dB under the voice during speech
PEAK_CAP = 0.9      # spot peaks <= this fraction of the voice's peak

# recipe -> (kind, level_db, layers [(catalog id, gain_db)], gunfire intensity)
BEDS = {
    "battle":        ("battle", 0.0, [("amb_fire_01", 0.0), ("amb_atmospheric_03", -3.0)], "high"),
    "fortress":      ("battle", 0.0, [("amb_fire_02", 0.0), ("amb_atmospheric_01", -3.0)], "medium"),
    "lz":            ("battle", 0.0, [("amb_atmospheric_05", 0.0), ("amb_fire_03", -6.0)], "low"),
    "jungle":        ("nature", 0.0, [("amb_nature_01", 0.0), ("amb_atmospheric_05", -9.0)], None),
    "trail":         ("nature", 0.0, [("amb_nature_02", 0.0)], None),
    "village":       ("nature", 0.0, [("amb_nature_02", 0.0), ("amb_crowd_04", -14.0)], None),
    "delta":         ("nature", 0.0, [("amb_water_01", 0.0), ("amb_nature_01", -6.0)], None),
    "city":          ("city", 0.0, [("amb_city_03", 0.0), ("amb_city_01", -6.0)], None),
    "beach_landing": ("surf", 0.0, [("amb_water_02", 0.0), ("amb_crowd_04", -12.0), ("amb_atmospheric_02", -8.0)], None),
    "airfield":      ("technology", 0.0, [("amb_technology_05", 0.0), ("amb_atmospheric_05", -6.0)], None),
}
RUNG_BEDS = {
    "globe":   ("pad", 0.0, [("amb_atmospheric_01", 0.0)], None),
    "map":     ("low", -10.0, [("amb_atmospheric_03", 0.0)], None),
    "oblique": ("low", -10.0, [("amb_atmospheric_04", 0.0)], None),
    "ground":  ("low", -8.0, [("amb_atmospheric_05", 0.0)], None),
}
# gunfire: (min gap, max gap, burst probability, rumble probability, peak range dB re voice RMS)
INTENSITY = {"high": (0.7, 3.8, 0.40, 0.16, (-19, -12)), "medium": (1.5, 5.5, 0.30, 0.14, (-21, -14)), "low": (2.5, 8.0, 0.20, 0.10, (-23, -16))}
FIRE_FILES = ["impact_005", "impact_006", "impact_007", "impact_022", "impact_034", "impact_025", "impact_019", "cinematic_012"]
RUMBLE_FILES = ["impact_003", "cinematic_007", "impact_026"]
# spot kind -> (catalog ids, max seconds, peak gain re voice RMS)
SPOTS = {"blast": (["cinematic_013", "impact_009", "cinematic_002"], 3.5, 0.0),
         "plane": (["impact_014", "impact_024"], 7.0, -10.0),
         "crowd": (["amb_crowd_04"], 6.0, -10.0)}


# ---- catalog -------------------------------------------------------------------------------------------------------

_CAT = None


def catalog() -> dict:
    global _CAT
    if _CAT is None:
        _CAT = {x["id"]: x for x in json.loads((LIB / "catalog.json").read_text())["sfx"]}
    return _CAT


def catalog_file(cid: str) -> Path:
    x = catalog().get(cid)
    if x is None:
        raise KeyError(f"{cid} is not in the sfx catalog")
    p = LIB / x["file"]
    if not p.exists():
        raise FileNotFoundError(p)
    return p


# ---- planning ------------------------------------------------------------------------------------------------------

def beat_rng(b: dict) -> random.Random:
    return random.Random(int(hashlib.sha256(f"{b['id']}|{b.get('site')}|{b.get('rung')}".encode()).hexdigest()[:16], 16))


def choose_bed(b: dict):
    return BEDS.get(b.get("site")) or RUNG_BEDS.get(b.get("rung")) or RUNG_BEDS["ground"]


def gunfire(rng: random.Random, t0: float, t1: float, intensity: str) -> list:
    gmin, gmax, p_burst, p_rumble, (plo, phi) = INTENSITY[intensity]
    ev, t = [], t0 + rng.uniform(0.4, 2.0)
    while t < t1 - 0.3:
        if rng.random() < p_rumble:
            ev.append({"t": round(t, 3), "kind": "rumble", "id": rng.choice(RUMBLE_FILES), "gain_db": round(rng.uniform(plo + 1, phi), 2),
                       "lp_hz": 220, "dur": round(rng.uniform(2.5, 4.5), 2), "pan": round(rng.uniform(-0.5, 0.5), 2)})
        else:
            n = rng.randint(2, 5) if rng.random() < p_burst else 1
            f, g, pan = rng.choice(FIRE_FILES), rng.uniform(plo, phi), rng.uniform(-0.8, 0.8)
            tt = t
            for k in range(n):
                if tt >= t1 - 0.2:
                    break
                ev.append({"t": round(tt, 3), "kind": "distant_fire", "id": f if rng.random() < 0.6 else rng.choice(FIRE_FILES),
                           "gain_db": round(g - 1.5 * k + rng.uniform(-1.5, 1.5), 2), "lp_hz": int(rng.uniform(650, 1300)), "dur": 1.6,
                           "pan": round(pan, 2)})
                tt += rng.uniform(0.08, 0.32)
            t = tt
        t += rng.uniform(gmin, gmax)
    return ev


def build_plan(tl: dict, events: list | None = None) -> dict:
    beats = tl["beats"]
    dur = float(tl["duration"])
    out = []
    for i, b in enumerate(beats):
        start = float(b["travelT1"])
        nxt = beats[i + 1] if i + 1 < len(beats) else None
        end = float(nxt["travelT0"]) if nxt else dur            # the beat's own end
        fade_out = [float(nxt["travelT1"]), float(nxt["travelT1"]) + XFADE] if nxt else [max(start, dur - 2.0), dur]
        kind, level, layers, inten = choose_bed(b)
        rng = beat_rng(b)
        out.append({
            "id": b["id"], "site": b.get("site"), "rung": b.get("rung"), "kind": kind, "level_db": level,
            "start": round(start, 3), "end": round(end, 3),
            "fade_in": [round(start, 3), round(start + XFADE, 3)], "fade_out": [round(fade_out[0], 3), round(fade_out[1], 3)],
            "layers": [{"id": cid, "file": catalog()[cid]["file"], "gain_db": g, "offset": round(rng.uniform(0, max(0.0, catalog()[cid]["duration"] - 1.0)), 2)}
                       for cid, g in layers],
            "events": gunfire(rng, start, end, inten) if inten else [],
        })
    spots = []
    for e in sorted(events or [], key=lambda e: (e["t"], e["kind"])):
        if e.get("kind") not in SPOTS or not 0 <= float(e["t"]) < dur:
            continue
        files, mx, g = SPOTS[e["kind"]]
        rng = random.Random(int(hashlib.sha256(f"spot|{e['kind']}|{float(e['t']):.3f}".encode()).hexdigest()[:16], 16))
        cid = rng.choice(files)
        spots.append({"t": round(float(e["t"]), 3), "kind": e["kind"], "id": cid, "file": catalog()[cid]["file"], "gain_db": g, "dur": mx,
                      "pan": round(rng.uniform(-0.4, 0.4), 2), "offset": 0.0 if e["kind"] != "crowd" else round(rng.uniform(0, 40), 2)})
    return {"version": 1, "duration": dur, "crossfade_s": XFADE, "beats": out, "spots": spots}


def plan_files(plan: dict) -> set:
    f = {l["id"] for b in plan["beats"] for l in b["layers"]}
    f |= {e["id"] for b in plan["beats"] for e in b["events"]} | {s["id"] for s in plan["spots"]}
    return f


# ---- rendering -----------------------------------------------------------------------------------------------------

_DEC = {}


def decode_stereo(cid: str, lp_hz: int | None = None) -> np.ndarray:
    key = (cid, lp_hz)
    if key not in _DEC:
        cmd = ["ffmpeg", "-v", "error", "-i", str(catalog_file(cid))]
        if lp_hz:
            cmd += ["-af", f"lowpass=f={lp_hz}"]
        raw = subprocess.run(cmd + ["-f", "f32le", "-ac", "2", "-ar", str(SR), "-"], capture_output=True, check=True, timeout=1800).stdout
        _DEC[key] = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).copy()
    return _DEC[key]


def loop_to(x: np.ndarray, n: int, offset_s: float = 0.0, xf_s: float = 1.0) -> np.ndarray:
    """n samples of x looped from offset_s, joined with equal-power crossfades so the wrap is seamless."""
    L = len(x)
    xf = min(int(xf_s * SR), L // 3)
    x = np.roll(x, -(int(offset_s * SR) % L), axis=0)
    if L >= n:
        return x[:n].copy()
    step = L - xf
    ramp = np.linspace(0, np.pi / 2, xf, dtype=np.float32)[:, None]
    out = np.zeros((n + L, 2), np.float32)
    pos, first = 0, True
    while pos < n:
        seg = x.copy()
        if not first:
            seg[:xf] *= np.sin(ramp)
            out[pos:pos + xf] *= np.cos(ramp)
        out[pos:pos + L] += seg
        pos += step
        first = False
    return out[:n]


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x.astype(np.float64) ** 2))) if len(x) else 0.0


def bed_envelope(plan_beat: dict, n: int) -> np.ndarray:
    """Equal-power gain per sample: 0 -> 1 over fade_in, 1 -> 0 over fade_out."""
    t = np.arange(n) / SR
    a0, a1 = plan_beat["fade_in"]; b0, b1 = plan_beat["fade_out"]
    up = np.clip((t - a0) / max(1e-6, a1 - a0), 0, 1)
    dn = np.clip((b1 - t) / max(1e-6, b1 - b0), 0, 1)
    return (np.sin(up * np.pi / 2) * np.sin(dn * np.pi / 2)).astype(np.float32)


def shape_clip(x: np.ndarray, peak: float, fade_out_s: float) -> np.ndarray:
    x = x.copy()
    if not len(x):
        return x
    x *= peak / max(1e-9, float(np.max(np.abs(x))))
    fi, fo = min(len(x) // 4, int(0.005 * SR)), min(len(x) // 2, int(fade_out_s * SR))
    if fi:
        x[:fi] *= np.linspace(0, 1, fi, dtype=np.float32)[:, None]
    if fo:
        x[-fo:] *= np.linspace(1, 0, fo, dtype=np.float32)[:, None]
    return x


def put(out: np.ndarray, clip: np.ndarray, t: float, pan: float):
    i = int(t * SR)
    if i < 0 or i >= len(out) or not len(clip):
        return
    n = min(len(clip), len(out) - i)
    th = (pan + 1) * np.pi / 4
    mono = clip[:n].mean(axis=1)
    out[i:i + n, 0] += mono * float(np.cos(th))
    out[i:i + n, 1] += mono * float(np.sin(th))


def render(plan: dict, voice: np.ndarray) -> np.ndarray:
    """-> float32 (n, 2) stem, n = len(voice). Levels are relative to the voice (see module doc)."""
    n = len(voice)
    vr = speech_rms(voice)
    vpeak = float(np.max(np.abs(voice))) or 1.0
    ref = vr * 10 ** (BED_DB / 20)
    bed = np.zeros((n, 2), np.float32)
    for b in plan["beats"]:
        t0 = int(max(0.0, b["fade_in"][0]) * SR); t1 = min(n, int(b["fade_out"][1] * SR) + 1)
        if t1 <= t0:
            continue
        env = bed_envelope(b, n)[t0:t1]
        norm = float(np.sqrt(sum(10 ** (l["gain_db"] / 10) for l in b["layers"])))
        acc = np.zeros((t1 - t0, 2), np.float32)
        for l in b["layers"]:
            lay = loop_to(decode_stereo(l["id"]), t1 - t0, l["offset"])
            acc += lay * (10 ** (l["gain_db"] / 20) / max(1e-6, rms(lay)) / norm)   # level from the segment actually used
        bed[t0:t1] += acc * env[:, None] * (ref * 10 ** (b["level_db"] / 20))
    ev = np.zeros((n, 2), np.float32)
    for b in plan["beats"]:
        for e in b["events"]:
            peak = min(vr * 10 ** (e["gain_db"] / 20), vpeak * PEAK_CAP)
            put(ev, shape_clip(decode_stereo(e["id"], e.get("lp_hz"))[: int(e["dur"] * SR)], peak, 0.25), e["t"], e["pan"])
    for s in plan["spots"]:
        peak = min(vr * 10 ** (s["gain_db"] / 20) * 4.0, vpeak * PEAK_CAP)  # spots are peaks: ~12 dB above the RMS reference
        x = decode_stereo(s["id"])
        clip = np.roll(x, -(int(s.get("offset", 0.0) * SR) % len(x)), axis=0)[: int(s["dur"] * SR)]
        put(ev, shape_clip(clip, peak, 0.4), s["t"], s["pan"])
    duck = speech_duck(voice, floor_db=DUCK_DB)[:n]
    stem = ((bed + ev) * duck[:, None]).astype(np.float32)
    pk = float(np.max(np.abs(stem))) if n else 0.0
    if pk > vpeak * PEAK_CAP:                      # safety net: bed + overlapping events never above the voice peak
        stem *= vpeak * PEAK_CAP / pk
    return stem


def write_stereo(path, x: np.ndarray):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", "-c:a", "pcm_f32le", str(path)],
                   input=x.astype(np.float32).tobytes(), check=True, timeout=1800)


def read_stereo(path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"], capture_output=True, check=True, timeout=1800).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("plan"); a.add_argument("timeline"); a.add_argument("out"); a.add_argument("--events", default=None)
    r = sub.add_parser("render"); r.add_argument("plan"); r.add_argument("voice"); r.add_argument("out")
    o = p.parse_args(argv)
    if o.cmd == "plan":
        ev = json.loads(Path(o.events).read_text()) if o.events else None
        plan = build_plan(json.loads(Path(o.timeline).read_text()), ev)
        Path(o.out).write_text(json.dumps(plan, indent=1))
        print(json.dumps({"event": "plan", "beats": len(plan["beats"]), "files": sorted(plan_files(plan)), "out": o.out}))
    else:
        voice = decode(o.voice)
        write_stereo(o.out, render(json.loads(Path(o.plan).read_text()), voice))
        print(json.dumps({"event": "render", "out": o.out, "seconds": round(len(voice) / SR, 2)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
