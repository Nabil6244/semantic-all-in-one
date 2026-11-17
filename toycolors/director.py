"""Song director for Toy Vehicles Colours: a list of colours becomes a sung colour song with one scene per verse.

python3 -m toycolors.director --colours red,yellow,green,blue,orange --out toycolors/out/song1 [--tune wheels] [--stills] [--render] [--fast]

--tune sings our colour words to a public-domain nursery tune (kids_audio/tunes.py: wheels, mary, twinkle, london) over
a matching backing track that doubles the melody; each verse sings one half of the tune. --tune none keeps the older
one-note-a-word melody over the "sunny" bed.

Every verse is 16 beats (8.57 s at 112 bpm), one scene template, one colour and one vehicle, with two sung lines
(beat 0 and beat 8). Default run: plan.json + sung mix.wav. --stills adds one quick still per verse and a contact
sheet. --render renders every verse (cached per verse) and joins them into song.mp4 with the mix.
Variety rules: no template or vehicle twice in a row; wheels only for wheeled toys that read well (monster, car);
the portal verse starts from the previous verse's colour.
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np

from kids_audio import library as L
from kids_audio import tunes as TU
from kids_audio.mixer import mix
from kids_audio.sing import sing
from kids_audio.synth import SR
from toycolors import timeline as T
from toycolors.template_events import EVENTS
from toycolors.post import GRADE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"
VOICE = "en-US-AnaNeural"
VERSE_BEATS = 16
VERSE = VERSE_BEATS * T.BEAT

SPOKEN = {"car": "car", "bus": "bus", "dump": "dump truck", "monster": "monster truck", "tanker": "water truck",
          "crane": "crane truck", "fire": "fire truck"}
ORDER = ["egg", "pour", "garage", "portal", "wheels", "convoy"]
KINDS = {"egg": ["car", "bus", "monster", "tanker", "fire", "dump", "crane"],
         "pour": ["car", "fire", "bus", "tanker", "monster"],
         "garage": ["car", "dump", "tanker", "crane"], "portal": ["monster", "car", "bus", "fire"],
         "wheels": ["monster", "car"], "convoy": ["monster", "bus", "fire", "tanker"]}
LYRICS = {
    "egg": ["What is in the {c} egg?", "It's a {c} {k}, hooray!"],
    "pour": ["Paint it {c}, paint it {c}!", "Now the {k} is {c}!"],
    "garage": ["Open up the {c} door!", "Here comes the {c} {k}!"],
    "portal": ["Through the magic ring we go!", "Now the {k} is {c}!"],
    "wheels": ["New {c} wheels go round and round!", "Look at the {k} go!"],
    "convoy": ["{C} trucks, all in a row!", "Beep beep, here we go!"],
}
# a cheerful C-major line shape, one note per word; the last word holds to the end of the 8-beat line
PHRASES = [[60, 64, 67, 69, 67, 64, 67, 72], [67, 67, 69, 71, 72, 71, 69, 67]]


def plan(colours, start=0, tune=None):
    verses, last_t, last_k = [], None, None
    halves = TU.halves_for(tune, len(colours)) if tune else None
    for i, c in enumerate(colours):
        t = ORDER[(start + i) % len(ORDER)]
        if t == last_t:
            t = ORDER[(ORDER.index(t) + 1) % len(ORDER)]
        kinds = [k for k in KINDS[t] if k != last_k]
        k = kinds[i % len(kinds)]
        v = {"i": i, "template": t, "colour": c, "kind": k, "t0": round(i * VERSE, 4),
             "from": colours[i - 1] if (t == "portal" and i > 0) else None}
        v["lines"] = [x.format(c=c, C=c.capitalize(), k=SPOKEN[k]) for x in LYRICS[t]]
        v["lines"] = [ln[0].upper() + ln[1:] for ln in v["lines"]]
        if tune:
            v["half"] = halves[i]
            v["lines"] = [TU.fill(ln, c, SPOKEN[k])[0] for ln in TU.TUNES[tune][halves[i]]["lines"]]
        verses.append(v)
        last_t, last_k = t, k
    return {"bpm": T.BPM, "tune": tune, "verse_s": VERSE, "duration": round(len(verses) * VERSE, 4), "verses": verses}


def tune_for(n_words, phrase):
    """Notes for an 8-beat line: one beat a word (half beats if the line is long), last word held to fill the line."""
    step = 1.0 if n_words <= 7 else 0.5
    notes = [[[phrase[i % len(phrase)], step]] for i in range(n_words)]
    used = step * n_words
    hold = min(2.0, 8 - used)
    notes[-1] = [[phrase[(n_words - 1) % len(phrase)], step + hold * 0.5], [None, max(0.0, 8 - used - hold * 0.5)]]
    return notes


def build_audio(p, out):
    L.build()
    lines = []
    tune = p.get("tune")
    for v in p["verses"]:
        for j, text in enumerate(v["lines"]):
            l = {"t0": v["t0"] + j * 8 * T.BEAT, "text": text, "phrase": PHRASES[j],
                 "out": os.path.join(out, "voice", f"v{v['i']:02d}_{j}.mp3")}
            if tune:
                l["text"], l["sung"], l["notes"] = TU.fill(TU.TUNES[tune][v["half"]]["lines"][j], v["colour"], SPOKEN[v["kind"]])
            lines.append(l)
    os.makedirs(os.path.join(out, "voice"), exist_ok=True)
    jp = os.path.join(out, "voice", "tts.json")
    json.dump({"voice": VOICE, "rate": "-5%", "lines": [{"text": l["text"], "out": l["out"]} for l in lines]}, open(jp, "w"))
    subprocess.run([sys.executable, os.path.join(ROOT, "cartoon3d-engine/tools/tts_words.py"), jp], check=True)
    track = np.zeros((2, int(p["duration"] * SR)))
    transpose = None
    for l in lines:
        words = json.load(open(l["out"] + ".words.json"))
        if tune and len(words) != len(l["notes"]):
            raise ValueError(f"TTS split {l['text']!r} into {len(words)} words, the tune has {len(l['notes'])}: "
                             + " ".join(w["text"] for w in words))
        notes = l["notes"] if tune else tune_for(len(words), l["phrase"])
        r = sing({"voice": l["out"], "words": words, "tune": notes, "bpm": T.BPM,
                  "out": l["out"][:-4] + "_sung.wav", "transpose": transpose, "octave_only": bool(tune)})
        transpose = r["transpose"]                  # one key for the whole song
        y = L.read_audio(r["file"])
        a = int(l["t0"] * SR)
        n = min(y.shape[1], track.shape[1] - a)
        track[:, a:a + n] += y[:, :n]
    g = 10 ** ((-14.0 - L.lufs(track)) / 20)
    voice = os.path.join(out, "voice.wav")
    L.write_wav(voice, np.clip(track * g, -1, 1))
    sfx = []
    for v in p["verses"]:
        for e in v.get("events", []):
            sfx.append({"t": round(v["t0"] + e["t"], 3), "name": e["sfx"], "gain_db": -4})
    music = {"bed": "sunny", "gap_db": -9, "duck_db": -6, "fade_in": 0.5, "fade_out": 1.5}
    if tune:                                         # backing in the tune's key; its lead doubles the singer, so it ducks less
        back = os.path.join(out, "backing.wav")
        L.write_wav(back, np.clip(TU.accompaniment(tune, [v["half"] for v in p["verses"]], T.BPM), -1, 1))
        music = {"file": back, "gap_db": -8, "duck_db": -4, "fade_in": 0.2, "fade_out": 1.5}
    rep = mix({"voice": voice, "out": os.path.join(out, "mix.wav"), "duration": p["duration"],
               "music": music,
               "sfx": sfx, "voice_lufs": -14, "target_lufs": -14})
    return os.path.join(out, "mix.wav"), rep


def template_events(p):
    for v in p["verses"]:
        v["events"] = EVENTS[v["template"]]


def blender(args, log):
    with open(log, "a") as f:
        subprocess.run([BLENDER, "-b", "-P", os.path.join(ROOT, "toycolors/scene_template.py"), "--"] + args,
                       stdout=f, stderr=subprocess.STDOUT, check=True)


def verse_args(v, out_dir):
    a = [v["template"], v["colour"], v["kind"], out_dir]
    if v.get("from"):
        a += ["--from", v["from"]]
    return a


def stills(p, out, fast=True):
    sd = os.path.join(out, "stills")
    os.makedirs(sd, exist_ok=True)
    pics = []
    for v in p["verses"]:
        t = {"egg": 5.0, "pour": 3.6, "garage": 5.4, "portal": 3.2, "wheels": 6.0, "convoy": 3.0}[v["template"]]
        blender(verse_args(v, sd) + ["--still", str(t)] + (["--fast"] if fast else []), os.path.join(out, "blender.log"))
        raw = os.path.join(sd, f"{v['template']}_{v['colour']}_{t:05.2f}.png")
        graded = raw[:-4] + "_g.png"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", raw, "-vf", GRADE, graded], check=True)
        pics.append(graded)
    from toycolors import overlay as O
    for path, tpath in zip(pics, titles(p, out)):
        from PIL import Image
        O.compose(path, [Image.open(tpath)], path)
    cols = 3
    ins = sum([["-i", x] for x in pics], [])
    n = len(pics)
    while n % cols:                                  # blank tiles fill the last row
        ins += ["-f", "lavfi", "-i", "color=c=white:s=1280x720:d=1"]
        n += 1
    rows = []
    fc = "".join(f"[{i}]scale=520:-1[s{i}];" for i in range(n))
    for r in range(n // cols):
        fc += "".join(f"[s{r * cols + c}]" for c in range(cols)) + f"hstack={cols}[r{r}];"
        rows.append(f"[r{r}]")
    fc += "".join(rows) + (f"vstack={len(rows)}" if len(rows) > 1 else "null")
    sheet = os.path.join(out, "verses_sheet.jpg")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y"] + ins + ["-filter_complex", fc, "-frames:v", "1", sheet], check=True)
    return sheet


def titles(p, out):
    """One outlined title PNG per verse ("RED FIRE TRUCK") in the verse colour."""
    from toycolors import overlay as O
    td = os.path.join(out, "titles")
    os.makedirs(td, exist_ok=True)
    paths = []
    for v in p["verses"]:
        rgb = tuple(int(min(255, c * 255 * 1.15 + 10)) for c in dict(T.COLOURS)[v["colour"]])
        path = os.path.join(td, f"v{v['i']:02d}.png")
        # the title names what the verse teaches: the wheels verse colours the wheels, the convoy is many trucks
        what = {"wheels": "wheels", "convoy": "trucks"}.get(v["template"], SPOKEN[v["kind"]])
        O.title(f"{v['colour']} {what}", rgb).save(path)
        paths.append(path)
    return paths


def render(p, out, mix_wav, fast=False, limit=None):
    """limit: seconds; render only the start of the song (short tests). Finished verses are reused."""
    out = os.path.abspath(out)                       # the frame list is read relative to its own folder
    mix_wav = os.path.abspath(mix_wav)
    parts = []
    for v in p["verses"]:
        if limit is not None and v["t0"] >= limit:
            break
        vd = os.path.join(out, "verses", f"v{v['i']:02d}_{v['template']}_{v['colour']}_{v['kind']}")
        need = int(round(VERSE * T.FPS))
        extra = []
        if limit is not None and v["t0"] + VERSE > limit:
            need = int(round((limit - v["t0"]) * T.FPS))
            extra = ["--frames", str(need)]
        done = len([f for f in os.listdir(vd) if f.startswith("f_")]) if os.path.isdir(vd) else 0
        if done < need:                              # a finished verse is reused, a partial one is rendered again
            blender(verse_args(v, vd) + (["--fast"] if fast else []) + extra, os.path.join(out, "blender.log"))
        parts.append((vd, need))
    lst = os.path.join(out, "frames.txt")
    with open(lst, "w") as f:
        for vd, need in parts:
            for fr in sorted(x for x in os.listdir(vd) if x.startswith("f_"))[:need]:
                f.write(f"file '{os.path.join(vd, fr)}'\nduration {1 / T.FPS:.6f}\n")
    mp4 = os.path.join(out, "song.mp4" if limit is None else f"song_{int(limit)}s.mp4")
    tl = titles(p, out)
    ins, fc, last = [], f"[0:v]fps={T.FPS},{GRADE}[g0];", "g0"
    for k, (v, path) in enumerate(zip(p["verses"], tl)):
        if limit is not None and v["t0"] >= limit:
            break
        ins += ["-loop", "1", "-t", str(p["duration"]), "-i", path]
        a0, a1 = v["t0"] + 0.4, v["t0"] + VERSE - 0.4     # title shows for the verse, off at the cut
        fc += f"[{last}][{k + 2}:v]overlay=0:0:enable='between(t,{a0:.3f},{a1:.3f})'[g{k + 1}];"
        last = f"g{k + 1}"
    fc = fc.rstrip(";")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-i", mix_wav]
                   + ins + ["-filter_complex", fc, "-map", f"[{last}]", "-map", "1:a",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                    "-c:a", "aac", "-b:a", "192k", "-shortest"] + (["-t", str(limit)] if limit else []) + ["-movflags", "+faststart", mp4], check=True)
    return mp4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--colours", default="red,yellow,green,blue,orange")
    ap.add_argument("--out", default=os.path.join(ROOT, "toycolors/out/song1"))
    ap.add_argument("--start", type=int, default=0, help="which template opens the song")
    ap.add_argument("--tune", default="wheels", choices=sorted(TU.TUNES) + ["none"])
    ap.add_argument("--stills", action="store_true")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--fast", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    p = plan([c.strip() for c in a.colours.split(",")], a.start, None if a.tune == "none" else a.tune)
    template_events(p)
    json.dump(p, open(os.path.join(a.out, "plan.json"), "w"), indent=1)
    for v in p["verses"]:
        print(f"{v['t0']:6.2f}s  {v['template']:7s} {v['colour']:7s} {v['kind']:8s} | " + " / ".join(v["lines"]))
    mix_wav, rep = build_audio(p, a.out)
    print("audio:", mix_wav, json.dumps(rep["voice_over_music_db"]), "lufs", rep["lufs"])
    if a.stills:
        print("sheet:", stills(p, a.out, fast=True))
    if a.render:
        print("video:", render(p, a.out, mix_wav, fast=a.fast))


if __name__ == "__main__":
    main()
