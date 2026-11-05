"""Roblox Cinema audio mix. Ambience beds (the app's bundled Sonniss-derived library) + synthesized event sounds placed on the
visible events (cues.json) + a music bed (the app's bundled Kevin MacLeod tracks, CC BY 4.0, credited on screen) ducked under the
voice with health_cinema.edit.audio.speech_duck (reused unchanged) + two-pass loudnorm to -14 LUFS / -1 dBTP, then the FINAL file is measured.
    python3 tools/mix_audio.py out/dday.mp4 --voice out/vo.wav [--video out/dday_silent.mp4 --final out/dday_final.mp4] [--no-music]
Reads <base>.plan.json and <base>.cues.json (written by render.mjs). Writes <base>.mix.wav and <base>.mix.json (measurements)."""
import argparse, json, re, subprocess, sys, zlib
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
import sfx_synth as SX  # noqa: E402

SR = 48000
AMB = ROOT / 'assets' / 'bundled-sfx' / 'ambience'
MUSIC = ROOT / 'assets' / 'music'
# bed name (director) -> ambience library groups, synthesized layer, level in dB
BEDS = {
    'map': (['atmospheric'], None, -30), 'camp': (['nature', 'crowd'], None, -30), 'coast_wind': (['water'], 'wind', -30), 'sea': (['water'], 'wind', -30), 'surf': (['water'], 'surf', -29),
    'storm': (['rain'], 'wind', -27), 'rain': (['rain'], None, -28), 'room_rain': (['room', 'rain'], None, -32), 'room': (['room'], None, -32), 'night_wind': (['nature'], 'wind', -31),
    'town_night': (['city'], 'wind', -31), 'crowd': (['crowd'], None, -29), 'battle': (['fire', 'atmospheric'], 'gunfire_far', -30), 'convoy': (['traffic', 'transport'], None, -30),
    'factory': (['technology'], None, -31), 'port': (['water', 'transport'], None, -30), 'jungle': (['nature'], None, -29), 'village': (['nature', 'crowd'], None, -31),
    'nature': (['nature'], None, -30), 'wind': (['atmospheric'], 'wind', -31),
}
LOOPING = {'gunfire': ('gunfire_near', -22), 'distant_gunfire': ('distant_gunfire', -26), 'tanks': ('tanks', -25), 'marching': ('marching', -27), 'planes_pass': ('planes_pass', -22), 'clock': ('clock', -34)}
ONESHOT = {'thunder': -18, 'bells': -24, 'shot_single': -20, 'explosion': -15, 'ramp_drop': -18, 'ship_guns': -17}
db = lambda x: 10 ** (x / 20.0)


def ff(*a, **k): return subprocess.run(['ffmpeg', '-v', 'error', *a], check=True, **k)


def decode(path, ch=2, start=0.0, dur=None):
    cmd = ['ffmpeg', '-v', 'error', '-ss', f'{start:.3f}'] + (['-t', f'{dur:.3f}'] if dur else []) + ['-i', str(path), '-f', 'f32le', '-ac', str(ch), '-ar', str(SR), '-']
    a = np.frombuffer(subprocess.run(cmd, capture_output=True, timeout=1800).stdout, dtype=np.float32)
    return a.reshape(-1, ch) if ch > 1 else a


def rms_norm(x, dbfs):
    r = float(np.sqrt(np.mean(x ** 2))) or 1e-6; return x / r * db(dbfs)


def fade(x, a, b):
    x = x.copy(); n = len(x); a, b = min(a, n // 2), min(b, n // 2)
    if a: x[:a] *= np.linspace(0, 1, a)[:, None] if x.ndim > 1 else np.linspace(0, 1, a)
    if b: x[-b:] *= np.linspace(1, 0, b)[:, None] if x.ndim > 1 else np.linspace(1, 0, b)
    return x


def stereo(m): return np.stack([m, m], axis=1) if m.ndim == 1 else m


def place(buf, snd, t, gain):
    i = int(t * SR)
    if i >= len(buf) or i + len(snd) <= 0: return
    s0 = max(0, -i); j = min(len(buf), i + len(snd)); buf[max(i, 0):j] += snd[s0: s0 + (j - max(i, 0))] * gain


def loop_fill(src, n):
    """src looped to n samples with equal-power-ish crossfades at the joins (mono or stereo, any length)."""
    if len(src) >= n: return src[:n]
    c = max(1, min(int(1.5 * SR), len(src) // 3)); out = src
    w = np.linspace(0, 1, c); w = w[:, None] if src.ndim > 1 else w
    while len(out) < n + c:
        out = np.concatenate([out[:-c], out[-c:] * (1 - w) + src[:c] * w, src[c:]])
    return out[:n]


def pick_amb(groups, seed):
    files = sorted(p for g in groups for p in AMB.glob(f'amb_{g}_*.opus'))
    return files[zlib.crc32(seed.encode()) % len(files)] if files else None


def ambience(plan, cues, total):
    N = int(total * SR); bus = np.zeros((N, 2), np.float32); used = []
    for k, seg in enumerate(cues['ambience']):
        spec = BEDS.get(seg['bed'], BEDS['wind']); t0, t1 = max(0, seg['t0'] - 0.8), min(total, seg['t1'] + 0.8); n = int((t1 - t0) * SR)
        if n <= 0: continue
        f = pick_amb(spec[0], f"{seg['bed']}:{k}")
        layer = np.zeros((n, 2), np.float32)
        if f:
            a = decode(f, 2); layer += rms_norm(loop_fill(a, n), spec[2]); used.append(f.name)
        if spec[1]:
            sy = SX.render(spec[1], max(4.0, t1 - t0), k) if spec[1] not in ('gunfire_far',) else SX.render('gunfire_far', t1 - t0, k)
            layer += stereo(rms_norm(loop_fill(sy.astype(np.float32), n), spec[2] - 3))
        layer = fade(layer, int(1.0 * SR), int(1.0 * SR))
        i = int(t0 * SR); bus[i:i + n] += layer[: max(0, min(n, N - i))]
    return bus, used


def event_bus(plan, cues, total):
    N = int(total * SR); bus = np.zeros((N, 2), np.float32); counts = {}
    seen = set()
    for c in cues['cues']:
        name = c['cue']; counts[name] = counts.get(name, 0) + 1
        if c.get('loop') and c.get('t1') is not None:
            d = c['t1'] - c['t']; s = SX.render(name, min(d + 1, 60), zlib.crc32(name.encode()))
            if s is None: continue
            s = fade(loop_fill(s, int(d * SR)), int(0.8 * SR), int(0.8 * SR)); place(bus, stereo(s), c['t'], db(c.get('gain', -18) - 4))
        else:
            s = SX.render(name, 3.0, int(c['t'] * 100))
            if s is None: continue
            pan = float(np.clip((c.get('x', 0) or 0) / 200.0, -1, 1)); st = np.stack([s * (1 - max(0, pan) * 0.5), s * (1 + min(0, pan) * 0.5)], 1)
            place(bus, st, c['t'], db(c.get('gain', -16) - 4))
    # recipe-level cues of each scene (a scene about tanks has tank sound; one of battle has gunfire), once per scene
    for s in plan['scenes']:
        for name in s.get('cues') or []:
            key = (s['id'], name)
            if name in LOOPING:
                cue, g = LOOPING[name]; d = s['t1'] - s['t0']; snd = SX.render(cue, min(d, 60), zlib.crc32(f'{s["id"]}{name}'.encode()))
                if snd is not None: place(bus, stereo(fade(loop_fill(snd, int(d * SR)), int(1.2 * SR), int(1.2 * SR))), s['t0'], db(g)); counts[name] = counts.get(name, 0) + 1
            elif name in ONESHOT:
                snd = SX.render(name, 3.0, zlib.crc32(f'{s["id"]}{name}'.encode()))
                if snd is not None: place(bus, stereo(snd), s['t0'] + 1.2, db(ONESHOT[name])); counts[name] = counts.get(name, 0) + 1
            elif name == 'crowd':
                f = pick_amb(['crowd'], s['id'])
                if f: d = s['t1'] - s['t0']; place(bus, fade(rms_norm(loop_fill(decode(f, 2), int(d * SR)), -30), int(1 * SR), int(1 * SR)), s['t0'], 1.0)
    return bus, counts


def music_bed(stems, total):
    """Every listed track is used: the film is cut into equal parts, one track each, joined with 5 s crossfades (so the on-screen credit is true)."""
    N = int((total + 1) * SR); cross = int(5.0 * SR); stems = [s for s in stems if (MUSIC / f'{s}.opus').is_file()]
    if not stems: return None
    part = N // len(stems); out = np.zeros((0, 2), np.float32)
    for k, s in enumerate(stems):
        a = decode(MUSIC / f'{s}.opus', 2)
        if len(a) == 0: continue
        need = part + (cross if k < len(stems) - 1 else 0) + (cross if k else 0)
        a = loop_fill(a, need)
        if len(out) == 0: out = a
        else:
            c = min(cross, len(a), len(out)); w = np.linspace(0, 1, c)[:, None]; out = np.concatenate([out[:-c], out[-c:] * np.cos(w * np.pi / 2) + a[:c] * np.sin(w * np.pi / 2), a[c:]])
    if len(out) < N: out = np.tile(out, (N // len(out) + 1, 1))
    return rms_norm(out[:N], -24.0)


def loudnorm(src, dst, target=-14.0, tp=-1.0):
    j = measure(src, target, tp)
    flt = (f"loudnorm=I={target}:TP={tp}:LRA=11:measured_I={j.get('input_i')}:measured_TP={j.get('input_tp')}:measured_LRA={j.get('input_lra')}:measured_thresh={j.get('input_thresh')}:offset={j.get('target_offset')}:linear=true,alimiter=limit=0.80:attack=2:release=60:level=disabled")
    ff('-y', '-i', str(src), '-af', flt, '-ar', str(SR), '-ac', '2', str(dst))


def measure(path, target=-14.0, tp=-1.0):
    r = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(path), '-af', f'loudnorm=I={target}:TP={tp}:LRA=11:print_format=json', '-f', 'null', '-'], capture_output=True, text=True, timeout=1800)
    m = re.search(r'\{[^{}]*"input_i"[^{}]*\}', r.stderr, re.S); return json.loads(m.group(0)) if m else {}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('base'); ap.add_argument('--voice'); ap.add_argument('--video'); ap.add_argument('--final'); ap.add_argument('--no-music', action='store_true')
    a = ap.parse_args(); base = a.base
    plan = json.load(open(base + '.plan.json')); cues = json.load(open(base + '.cues.json')); total = float(plan['duration'])
    N = int(total * SR); report = {'duration': total}
    voice = None
    if a.voice:
        v = decode(a.voice, 1)[:N]; v = np.pad(v, (0, max(0, N - len(v)))); voice = v / (float(np.percentile(np.abs(v[np.abs(v) > 1e-4]), 95)) or 1) * 0.35
    amb, used = ambience(plan, cues, total); ev, counts = event_bus(plan, cues, total)
    mix = amb + ev
    report['ambience_files'] = used; report['cue_counts'] = counts
    if not a.no_music:
        stems = (cues.get('music') or {}).get('tracks') or []
        mb = music_bed(stems, total)
        if mb is not None:
            sys.path.insert(0, str(ROOT))
            from health_cinema.edit.audio import speech_duck
            duck = speech_duck(voice, floor_db=-9.0) if voice is not None else np.ones(N, np.float32)
            lvl = np.ones(N, np.float32)
            # music swells a little in the map scenes and under battle, always a bed under speech; faded in over 3 s, out over the last 5 s
            mb = mb[:N] * (duck[:N, None] if len(duck) >= N else 1) * db(-1.0)
            mix += fade(mb, int(3 * SR), int(5 * SR)); report['music'] = stems
    if voice is not None: mix += stereo(voice)
    # soft limiter on the pre-master (the loudnorm below sets the final level and true peak)
    pre = np.tanh(mix * 0.85) / 0.85
    import wave
    tmp = Path(base + '.premix.wav'); w = wave.open(str(tmp), 'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((np.clip(pre, -1, 1) * 32767).astype('<i2').tobytes()); w.close()
    out = Path(base + '.mix.wav'); loudnorm(tmp, out); tmp.unlink()
    report['measured_mix'] = {k: v for k, v in measure(out).items() if k in ('input_i', 'input_tp', 'input_lra')}
    if a.video and a.final:
        ff('-y', '-i', a.video, '-i', str(out), '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', a.final)
        r = measure(a.final); report['final_file'] = {'path': a.final, 'integrated_lufs': r.get('input_i'), 'true_peak_dbtp': r.get('input_tp'), 'lra': r.get('input_lra')}
    Path(base + '.mix.json').write_text(json.dumps(report, indent=1)); print(json.dumps(report, indent=1))


if __name__ == '__main__':
    main()
