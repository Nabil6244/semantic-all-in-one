"""Music + sound effects under the voiced dialogue, then mux with the silent render at -14 LUFS.

python3 cartoon2d/mix.py <story_render.json> [--mux]
Music follows the place (story "music": {place: bed}); songs keep the playroom bed (their beat grid) and duck less.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kids_audio.mixer import mix  # noqa: E402
from kids_audio.library import read_audio, write_wav  # noqa: E402
from kids_audio.synth import SR  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hook  # noqa: E402
import games  # noqa: E402
import numpy as np  # noqa: E402

st = json.loads(Path(sys.argv[1]).read_text())
tl = json.loads((ROOT / st["timeline"]).read_text())
build = ROOT / st["build"]
total = tl["total"]
beds = st.get("music", {})
place = st.get("start_place", "main")
segs, t_prev = [], 0.0
for ln in tl["lines"]:
    if ln.get("place") and ln["place"] != place:
        tc = max(0.0, ln["start"] - 0.45)
        segs.append({"t0": t_prev, "t1": tc, "bed": beds.get(place, "playroom")})
        place, t_prev = ln["place"], tc
segs.append({"t0": t_prev, "t1": total, "bed": beds.get(place, "playroom")})
segs = [s for s in segs if s["t1"] - s["t0"] > 0.05]
sfx, duck = [], []
for ln in tl["lines"]:
    if ln.get("sfx"):
        sfx.append({"t": max(0.0, ln["start"] - 0.05), "name": ln["sfx"], "gain_db": -2})
    if ln.get("pic"):
        sfx.append({"t": ln["start"] + 0.3, "name": "pop", "gain_db": -5})
    if ln.get("card") and not ln.get("sfx"):
        t0 = ln["start"] + float(ln.get("card_at", 0)) * (ln["end"] - ln["start"])
        sfx.append({"t": t0, "name": "pop", "gain_db": -6})
    if ln.get("give"):
        sfx.append({"t": ln["start"] + 0.35, "name": "sparkle", "gain_db": -6})
    if ln.get("chant"):
        duck.append({"t0": ln["start"], "t1": ln["end"], "duck_db": -4})
sfx += games.sfx(tl)
job = {"voice": str(build / "audio" / "dialogue.wav"), "out": str(build / "final_mix.wav"), "duration": total,
       "music": {"segments": segs, "gap_db": -12, "duck_db": -10, "fade_in": 1.5, "fade_out": 3.0, "crossfade": 1.2},
       "sfx": sfx, "duck_regions": duck, "voice_lufs": -14, "target_lufs": -14}
(build / "mix_job.json").write_text(json.dumps(job, indent=1))
print(json.dumps(mix(job)))
# hook teaser: the same moments render.py puts in front of the cold open, cut from the finished mix, each with short
# fades and a whoosh on the cut, then the episode
win = hook.windows(st, tl)
final = build / "final_mix.wav"
if win:
    x = read_audio(str(final))
    parts = []
    for t0, d in win:
        seg = x[:, int(t0 * SR):int((t0 + d) * SR)].copy()
        f = int(0.04 * SR)
        seg[:, :f] *= np.linspace(0, 1, f)
        seg[:, -f:] *= np.linspace(1, 0, f)
        parts.append(seg)
    hk = np.concatenate(parts, 1)
    pop = read_audio(str(ROOT / "kids_audio" / "library" / "sfx_pop.wav"))   # a pop on every cut, a sparkle on the first
    spk = read_audio(str(ROOT / "kids_audio" / "library" / "sfx_sparkle.wav"))
    pos = 0
    for i, seg in enumerate(parts):
        for fx, g in ((pop, 0.5),) + (((spk, 0.35),) if i == 0 else ()):
            n = min(fx.shape[1], hk.shape[1] - pos)
            hk[:, pos:pos + n] += fx[:, :n] * g
        pos += seg.shape[1]
    final = build / "final_mix_hook.wav"
    write_wav(str(final), np.concatenate([hk, x], 1))
    L = sum(d for _, d in win)
    ch = (build / "audio" / "chapters.txt")
    if ch.exists():                                   # YouTube chapters move by the hook length; the first one must be 0:00
        rows = ["0:00 Coming up!"]
        for row in ch.read_text().split("\n"):
            if row.strip():
                mm, rest = row.split(" ", 1)
                s_ = int(mm.split(":")[0]) * 60 + int(mm.split(":")[1]) + L
                rows.append(f"{int(s_ // 60)}:{int(s_ % 60):02d} {rest}")
        (build / "chapters.txt").write_text("\n".join(rows) + "\n")
    print("HOOK", win, round(L, 2), "s")
if "--mux" in sys.argv:
    name = st.get("name", build.name)
    out = build / f"{name}.mp4"
    # two-pass linear loudness: one gain for the whole film (single-pass loudnorm rides the level up and down = pumping)
    meas = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(final), "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
                           "-f", "null", "-"], capture_output=True, text=True).stderr
    m = json.loads(meas[meas.rindex("{"):meas.rindex("}") + 1])
    ln = (f"loudnorm=I=-14:TP=-1.5:LRA=11:linear=true:measured_I={m['input_i']}:measured_TP={m['input_tp']}"
          f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(build / "video_silent.mp4"), "-i", str(final),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-af", ln, "-ar", "48000",
                    "-c:a", "aac", "-b:a", "256k", "-shortest", str(out)], check=True)
    print("MUXED", out)
