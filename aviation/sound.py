"""Aviation sound pass (docs/aviation/MASTER_PLAN.md section 7): SFX on the stage, a music bed per chapter mood, one -14 LUFS mix.

    SFX_MAP                                  style.SOUNDS names -> files of the app's SFX library (assets/bundled-sfx)
    events(plan, scenes) -> [ {t, file, gain_db, kind[, duck_from]} ]
                                             pop / whoosh / thud / typewriter tick from stage shots' cues (shot["cues"] = absolute
                                             [(t, name)]), a soft whoosh on every card, a low hit on a re-hook marker
                                             ({"layer": "retention.lay_rehook"}) with duck_from = t - 0.4 s; footage slots get nothing;
                                             flight / weather map stretches stay calm (no whooshes, no card sounds); two sounds are never
                                             closer than 0.25 s (the stronger one wins). gain_db = dB below the sample's own peak.
    music_plan(plan, scenes, total_s=None) -> [ {start, end, bed, gain_db, mood, xfade, dips} ]
                                             one bed per chapter (story / news / flight; picture modes of plan.modes), neighbours overlap by
                                             `xfade` s (crossfade); gain_db = the bed's LUFS before the voice ducks it; dips = [(a, b, db)]
                                             music dips: 0.4 s before a re-hook, 0.8 s of near-silence before the biggest reveal
                                             (the last story line that opens with a turn word, else the longest story stage shot)
    mix(voice_path, events, music, out_path, total_s) -> out_path
                                             ONE ffmpeg graph: SFX are placed sparsely into a single mono stem with numpy (no per-event
                                             filters), the beds are streamed (looped) inputs, sidechain-ducked under the voice, then
                                             loudnorm to -14 LUFS / -1.5 dBTP. The caller may hand the result to runner.render_film as
                                             its `voice` (it normalises to -14 again; a no-op on an already -14 file).
No downloads: only files already in assets/. A missing file is skipped, never an error.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import style as S

ROOT = Path(__file__).resolve().parents[1]
SFX_DIR = ROOT / "assets" / "bundled-sfx"
MUSIC_DIR = ROOT / "assets" / "music"

# style.SOUNDS name -> library file (closest existing sample; no download)
SFX_MAP: Dict[str, Path] = {
    "pop": SFX_DIR / "ui" / "ui_pop_01.opus",                      # 0.38 s soft pop
    "whoosh_soft": SFX_DIR / "whoosh" / "whoosh_05.opus",          # 0.5 s short whoosh
    "thud_soft": SFX_DIR / "impact" / "impact_01.opus",            # 0.33 s low-intensity thump
    "typewriter_tick": SFX_DIR / "text" / "text_007.opus",         # 0.17 s dry tick
    "low_hit": SFX_DIR / "impact" / "impact_007.opus",             # 0.88 s low rumble hit
    "pen_scribble": SFX_DIR / "text" / "text_006.opus",            # 0.46 s scratchy tick (closest to a pen)
}
# dB below each sample's own peak (samples are peak-normalised before placing); theory-style lowered levels
GAIN_DB = {"pop": -19.0, "whoosh_soft": -25.0, "thud_soft": -22.0, "typewriter_tick": -24.0, "low_hit": -15.0, "pen_scribble": -27.0}
KIND = {"pop": "pop", "whoosh_soft": "whoosh", "thud_soft": "thud", "typewriter_tick": "tick", "low_hit": "hit", "pen_scribble": "write"}
PRIORITY = {"hit": 0, "tick": 1, "pop": 2, "write": 3, "thud": 4, "whoosh": 5}

MIN_GAP_S = 0.25
DUCK_BEFORE_REHOOK_S = 0.4
REVEAL_SILENCE_S = 0.8
REVEAL_DIP_DB = -30.0
REHOOK_DIP_DB = -14.0
XFADE_S = 3.0
MIN_CHAPTER_S = 8.0
CARD_PREFIXES = ("cards.", "war.lay_document", "gfx.lay_sheet", "gfx.lay_place_title", "gfx.lay_end_card")
MAP_PREFIXES = ("flightmap.", "hud.", "gfx_air.", "gfx.lay_weather")
MAP_MODES = ("flight", "weather")
TURN = re.compile(r"^\s*(but|then|until|instead|suddenly|and then|what|that is when|and yet)\b", re.I)

# mood -> beds (assets/music) and bed level in LUFS before the voice ducks it (story_fast levels: -33 low .. -27 high)
BEDS = {"story": ["lost_frontier", "ascending_the_vale"], "news": ["interloper", "stormfront"], "flight": ["long_note_four", "echoes_of_time_v2"]}
BED_LUFS = {"story": -32.0, "news": -31.0, "flight": -35.0}
MOOD_OF_MODE = {"story": "story", "people": "story", "fleet": "story", "flight": "flight", "weather": "flight"}   # the rest -> news


# ---------------------------------------------------------------------------------------------------------------- helpers

def _shots(plan: Any) -> List[Dict[str, Any]]:
    return list(plan.get("shots", []) if isinstance(plan, dict) else getattr(plan, "shots", []) or [])


def _modes(plan: Any) -> List[str]:
    return list(plan.get("modes", []) if isinstance(plan, dict) else getattr(plan, "modes", []) or [])


def _f(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _layer(s: Dict[str, Any]) -> str:
    return str(s.get("layer") or "")


def _calm_spans(shots: Sequence[Dict[str, Any]], scenes: Sequence[Dict[str, Any]], modes: Sequence[str]) -> List[Tuple[float, float]]:
    out = []
    for s in shots:
        if _layer(s).startswith(MAP_PREFIXES) or (s.get("mode") in MAP_MODES and s.get("kind") != "footage" and _layer(s)):
            out.append((_f(s.get("start")), _f(s.get("end"))))
    for sc, m in zip(scenes, modes):
        if m in MAP_MODES:
            out.append((_f(sc.get("start")), _f(sc.get("end"))))
    return out


def _calm(t: float, spans: Sequence[Tuple[float, float]]) -> bool:
    return any(a - 1e-6 <= t < b for a, b in spans)


def _ev(t: float, name: str, **extra: Any) -> Dict[str, Any]:
    d = {"t": round(float(t), 3), "file": str(SFX_MAP[name]), "gain_db": GAIN_DB[name], "kind": KIND[name]}
    d.update(extra)
    return d


# ---------------------------------------------------------------------------------------------------------------- events

def events(plan: Any, scenes: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    shots = _shots(plan)
    calm = _calm_spans(shots, scenes, _modes(plan))
    raw: List[Dict[str, Any]] = []
    for s in shots:
        lay, a = _layer(s), _f(s.get("start"))
        if s.get("kind") == "footage":
            continue                                           # clips: the picture cuts, the music carries it
        if lay.endswith("lay_rehook"):
            raw.append(_ev(a, "low_hit", duck_from=round(max(0.0, a - DUCK_BEFORE_REHOOK_S), 3)))
        elif s.get("cues"):
            for t, name in s["cues"]:
                if name in SFX_MAP and not (KIND[name] == "whoosh" and _calm(_f(t), calm)):
                    raw.append(_ev(_f(t), name))
        elif lay.startswith(CARD_PREFIXES) and not _calm(a, calm):
            raw.append(_ev(a, "whoosh_soft"))
    raw.sort(key=lambda e: (PRIORITY[e["kind"]], e["t"]))      # the stronger sound claims its slot first
    kept: List[Dict[str, Any]] = []
    for e in raw:
        if all(abs(e["t"] - k["t"]) >= MIN_GAP_S for k in kept):
            kept.append(e)
    return sorted(kept, key=lambda e: e["t"])


# ---------------------------------------------------------------------------------------------------------------- music

def _chapters(scenes: Sequence[Dict[str, Any]], modes: Sequence[str], total: float) -> List[List[Any]]:
    ch: List[List[Any]] = []
    for sc, m in zip(scenes, modes):
        mood = MOOD_OF_MODE.get(m, "news")
        a, b = _f(sc.get("start")), _f(sc.get("end"))
        if ch and ch[-1][2] == mood:
            ch[-1][1] = b
        else:
            ch.append([a, b, mood])
    merged: List[List[Any]] = []
    for c in ch:                                               # a chapter shorter than MIN_CHAPTER_S joins the previous one
        if merged and (c[1] - c[0] < MIN_CHAPTER_S):
            merged[-1][1] = c[1]
        else:
            merged.append(c)
    if not merged:
        merged = [[0.0, total, "news"]]
    merged[0][0] = 0.0
    merged[-1][1] = max(total, merged[-1][1])
    for i in range(1, len(merged)):
        merged[i][0] = merged[i - 1][1]
    return merged


def _reveal(shots: Sequence[Dict[str, Any]], scenes: Sequence[Dict[str, Any]], modes: Sequence[str]) -> Optional[float]:
    turn = None
    for sc, m in zip(scenes, modes):
        if m == "story" and TURN.match(str(sc.get("text") or "")):
            turn = _f(sc.get("start"))
    if turn is not None:
        return turn
    best, at = 0.0, None
    for s in shots:
        if _layer(s).endswith("lay_stage") and _f(s.get("end")) - _f(s.get("start")) > best:
            best, at = _f(s.get("end")) - _f(s.get("start")), _f(s.get("start"))
    return at


def music_plan(plan: Any, scenes: Sequence[Dict[str, Any]], total_s: Optional[float] = None) -> List[Dict[str, Any]]:
    shots, modes = _shots(plan), _modes(plan)
    total = float(total_s) if total_s else max([_f(s.get("end")) for s in scenes] + [_f(s.get("end")) for s in shots] + [0.0])
    if total <= 0:
        return []
    chapters = _chapters(scenes, modes, total)
    dips: List[Tuple[float, float, float]] = []
    for s in shots:
        if _layer(s).endswith("lay_rehook"):
            a = _f(s.get("start"))
            dips.append((max(0.0, a - DUCK_BEFORE_REHOOK_S), a + 0.6, REHOOK_DIP_DB))
    r = _reveal(shots, scenes, modes)
    if r is not None and r > REVEAL_SILENCE_S:
        dips.append((r - REVEAL_SILENCE_S, r, REVEAL_DIP_DB))
    used: Dict[str, int] = {}
    beds: List[Dict[str, Any]] = []
    last = None
    for a, b, mood in chapters:
        pool = BEDS[mood]
        k = used.get(mood, 0)
        name = pool[k % len(pool)]
        if name == last and len(pool) > 1:
            k += 1
            name = pool[k % len(pool)]
        used[mood] = k + 1
        last = name
        beds.append({"start": a, "end": b, "bed": str(MUSIC_DIR / f"{name}.opus"), "gain_db": BED_LUFS[mood], "mood": mood, "xfade": XFADE_S})
    for i, bd in enumerate(beds):                              # neighbours overlap by xfade: each side reaches half into the other
        h = XFADE_S / 2
        if i > 0:
            bd["start"] = max(0.0, bd["start"] - h)
        if i < len(beds) - 1:
            bd["end"] = bd["end"] + h
        bd["dips"] = [d for d in dips if d[1] > bd["start"] and d[0] < bd["end"]]
    return beds


# ---------------------------------------------------------------------------------------------------------------- mix

SR = 44100


def _run(cmd: Sequence[str], timeout: float = 3600) -> subprocess.CompletedProcess:
    try:
        from providers import ffmpeg_runner as FR
        r = FR.run_ffmpeg(list(cmd), owner="aviation_sound", timeout=timeout, check=False)
        if getattr(r, "returncode", 0) not in (0, None):
            raise RuntimeError(f"ffmpeg failed: {getattr(r, 'stderr', '')[-400:]}")
        return r
    except ImportError:
        return subprocess.run(list(cmd), check=True, capture_output=True, timeout=timeout)


@lru_cache(maxsize=64)
def _sample(path: str):
    import numpy as np
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"], capture_output=True, timeout=60)
    a = np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    pk = float(np.abs(a).max()) if a.size else 0.0
    return a / pk if pk > 0 else a                              # peak 1.0; gain_db is then dB below the sample's own peak


@lru_cache(maxsize=32)
def lufs_of(path: str) -> float:
    """Integrated loudness of the first 90 s of a file (ebur128), cached per process."""
    p = subprocess.run(["ffmpeg", "-nostats", "-t", "90", "-i", path, "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True, timeout=120)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", p.stderr)
    return float(m[-1]) if m else -20.0


def _stem(evs: Sequence[Dict[str, Any]], total_s: float, path: Path) -> bool:
    import numpy as np
    n = int(total_s * SR) + SR
    buf = np.zeros(n, dtype=np.float32)
    placed = 0
    for e in evs:
        if not Path(e["file"]).is_file():
            continue
        a = _sample(str(e["file"]))
        i = int(_f(e["t"]) * SR)
        if i < 0 or i >= n or not a.size:
            continue
        seg = a[: n - i] * (10 ** (_f(e.get("gain_db"), -20.0) / 20.0))
        buf[i:i + seg.size] += seg
        placed += 1
    if not placed:
        return False
    pcm = (np.clip(buf, -1.0, 1.0) * 32767).astype(np.int16)
    import wave
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return True


def mix(voice_path: str, events: Sequence[Dict[str, Any]], music: Sequence[Dict[str, Any]], out_path: str, total_s: float) -> str:
    """voice + SFX stem + sidechain-ducked beds -> out_path (.m4a/.wav/.flac by extension) at -14 LUFS, exactly total_s long."""
    total_s = float(total_s)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="avsound_") as td:
        stem = Path(td) / "sfx.wav"
        has_sfx = _stem(events, total_s, stem)
        cmd: List[str] = ["ffmpeg", "-v", "error", "-y", "-i", str(voice_path)]
        n_in = 1
        fl = ["[0:a]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=0:%.3f,asplit=2[v][k]" % total_s]
        mix_in = ["[v]"]
        if has_sfx:
            cmd += ["-i", str(stem)]
            fl.append(f"[{n_in}:a]aresample=48000,aformat=channel_layouts=stereo[sfx]")
            mix_in.append("[sfx]")
            n_in += 1
        labels = []
        for j, m in enumerate(b for b in music if Path(b["bed"]).is_file()):
            a, b = _f(m["start"]), min(_f(m["end"]), total_s)
            d = max(0.5, b - a)
            xf = min(_f(m.get("xfade"), XFADE_S), d / 2)
            cmd += ["-stream_loop", "-1", "-i", str(m["bed"])]
            vol = _f(m.get("gain_db"), -32.0) - lufs_of(str(m["bed"]))
            ms = int(a * 1000)
            chain = (f"[{n_in}:a]atrim=0:{d:.3f},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,volume={vol:.2f}dB,"
                     f"afade=t=in:d={xf:.3f},afade=t=out:st={max(0.0, d - xf):.3f}:d={xf:.3f},adelay={ms}|{ms}")
            for da, db, ddb in m.get("dips", []):
                chain += f",volume=enable='between(t,{da:.3f},{db:.3f})':volume={ddb:.1f}dB"
            fl.append(chain + f"[m{j}]")
            labels.append(f"[m{j}]")
            n_in += 1
        if labels:
            fl.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=longest[mus]")
            fl.append("[mus][k]sidechaincompress=threshold=0.025:ratio=8:attack=40:release=300[musd]")
            mix_in.append("[musd]")
        else:
            fl.append("[k]anullsink")
        fl.append("".join(mix_in) + f"amix=inputs={len(mix_in)}:normalize=0:duration=longest,atrim=0:{total_s:.3f},"
                  "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[o]")
        codec = ["-c:a", "aac", "-b:a", "192k"] if out.suffix.lower() in (".m4a", ".mp4", ".aac") else ["-c:a", "pcm_s16le"]
        tmp = out.with_name(out.stem + ".part" + out.suffix)
        cmd += ["-filter_complex", ";".join(fl), "-map", "[o]", "-t", f"{total_s:.3f}", *codec, str(tmp)]
        _run(cmd, timeout=max(120.0, total_s * 2))
        tmp.replace(out)
    return str(out)
