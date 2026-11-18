"""Story director for Toy Vehicles stories: a story script (toycolors/stories/*.json) becomes a narrated, voiced video.

python3 -m toycolors.story toycolors/stories/zip_mud.json [--out DIR] [--stills] [--render] [--quality 540|720|1080]

--quality 540: ultra fast (960x540, 8 samples, upscaled to 720p). 540 and 720 render TOY_JOBS shots at once (default 2) -> story_540p.mp4
--quality 720: fast preview (1280x720, 16 samples, about 3x faster) -> story_720p.mp4
--quality 1080: final (1920x1080, 24 samples) -> story_1080p.mp4. Both keep their own shot cache.

1. Every line is spoken with its character's Edge voice (cached by voice + text).
2. Lines are laid out in their shot; a shot lasts as long as its action and its lines need.
3. Each shot becomes a spec for toycolors/story_scene.py. Shots are cached in toycolors/out/shot_cache/<hash>/shot.mp4,
   keyed by the spec and the scene code, so a shot made once is reused by every later story. Frames are encoded and
   deleted right away, so a long story needs little disk.
4. An episode file joins adventures: {"title": "...", "parts": ["zip_mud.json", "zip_race.json", ...]} (paths next to
   it). Voices and cast merge; each part opens with its own title card over its first shot.
5. --stills: one quick still per shot and a contact sheet. --render: render missing shots, mix voice + music + effects,
   join into story.mp4.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

import numpy as np

from kids_audio import library as L
from kids_audio.mixer import mix
from kids_audio.synth import SR
from toycolors.post import STORY_GRADE as GRADE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from toycolors.paths import blender as _blender_path

BLENDER = _blender_path()
CACHE = os.path.join(ROOT, "toycolors/out/shot_cache")
CODE = ["toycolors/story_scene.py", "toycolors/toy.py", "toycolors/kit.py", "toycolors/templates.py"]
ACTION_FN = {"idle": "a_idle", "drive_in": "a_drive_in", "spot": "a_spot", "stuck": "a_stuck", "tow": "a_tow",
             "wash": "a_wash", "dance": "a_dance", "race": "a_race", "jump": "a_jump", "flat": "a_flat", "hide": "a_hide",
             "template": "template_shot"}
MIN_DUR = {"idle": 2.0, "drive_in": 3.2, "spot": 3.0, "stuck": 4.5, "tow": 6.0, "wash": 5.5, "dance": 4.0,
           "template": 16 * 60 / 112, "race": 6.0, "jump": 5.0, "flat": 6.5, "hide": 6.0}
LEAD, GAP, TAIL = 0.4, 0.3, 0.7


def code_hash(action=None):
    """Hash of the code a shot depends on: the shared files, plus from story_actions.py only the shared helpers and
    this shot's own action, so adding or editing another action keeps every other cached shot."""
    import ast
    h = hashlib.sha1()
    for p in CODE:
        h.update(open(os.path.join(ROOT, p), "rb").read())
    src = open(os.path.join(ROOT, "toycolors/story_actions.py")).read()
    others = set(ACTION_FN.values()) - {ACTION_FN.get(action)}
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name in others:
            continue
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") in ("ACTIONS", "MIN_DUR") for t in node.targets):
            continue                                 # the action table grows with every new action
        h.update((ast.get_source_segment(src, node) or "").encode())
    return h.hexdigest()[:10]


def load(path):
    """A story file, or an episode file whose parts are story files. Every part's first shot carries its title."""
    st = json.load(open(path))
    if "parts" not in st:
        st["shots"][0].setdefault("title", st["title"])
        return st
    ep = {"title": st["title"], "set": st.get("set", "mud"), "voices": dict(st.get("voices", {})),
          "cast": dict(st.get("cast", {})), "shots": []}
    for part in st["parts"]:
        ps = load(os.path.join(os.path.dirname(os.path.abspath(path)), part))
        ep["voices"].update(ps["voices"])
        ep["cast"].update(ps["cast"])
        for sh in ps["shots"]:
            sh.setdefault("set", ps.get("set", "mud"))
        ep["shots"] += ps["shots"]
    return ep


def speak(story, out):
    vd = os.path.join(out, "voice")
    os.makedirs(vd, exist_ok=True)
    job = {"lines": []}
    for sh in story["shots"]:
        for ln in sh["lines"]:
            v = story["voices"][ln[0]]
            key = hashlib.sha1(json.dumps([v, ln[1]]).encode()).hexdigest()[:12]
            job["lines"].append({"text": ln[1], "out": os.path.join(vd, f"{ln[0]}_{key}.mp3"), **v})
    jp = os.path.join(vd, "tts.json")
    json.dump(job, open(jp, "w"))
    subprocess.run([sys.executable, os.path.join(ROOT, "cartoon3d-engine/tools/tts_words.py"), jp], check=True)
    return [l["out"] for l in job["lines"]]


def layout(story, mp3s):
    """Times for every line and shot; returns the shot specs and the voice placements."""
    specs, voice, t_song, k = [], [], 0.0, 0
    for sh in story["shots"]:
        t, talk = LEAD, {}
        for ln in sh["lines"]:
            mp3 = mp3s[k]
            k += 1
            words = json.load(open(mp3 + ".words.json"))
            start = ln[2] if len(ln) > 2 else t
            end = start + (words[-1]["t1"] if words else 1.0)
            voice.append({"t": t_song + start, "file": mp3, "who": ln[0], "text": ln[1]})
            if ln[0] != "narrator":
                talk.setdefault(ln[0], []).extend([[round(start + w["t0"], 3), round(start + w["t1"], 3)] for w in words])
            t = end + GAP
        dur = round(max(MIN_DUR[sh["action"]], t - GAP + TAIL, sh.get("min", 0)), 2)
        cast = []
        for cid, c in sh.get("cast", {}).items():
            cast.append({"id": cid, **story["cast"][cid], **c})
        spec = {"set": sh.get("set", story.get("set", "mud")), "dur": dur, "action": sh["action"],
                "args": sh.get("args", {}), "cast": cast, "talk": talk, "camera": sh.get("camera", {})}
        specs.append({"t0": round(t_song, 3), "spec": spec, "title": sh.get("title")})
        t_song += dur
    return specs, voice, round(t_song, 3)


def blender(args, log):
    with open(log, "a") as f:
        subprocess.run([BLENDER, "-b", "-P", os.path.join(ROOT, "toycolors/story_scene.py"), "--"] + args,
                       stdout=f, stderr=subprocess.STDOUT, check=True)


def _tag(fast):
    return "ultra" if fast == "ultra" else "fast" if fast else ""


def _flag(fast):
    return ["--ultra"] if fast == "ultra" else ["--fast"] if fast else []


def shot_dir(spec, fast):
    # the key holds everything that changes the picture: the shot, the scene code, the quality and any TOY_* render knobs
    knobs = sorted((k, v) for k, v in os.environ.items() if k.startswith("TOY_") and k != "TOY_JOBS")   # JOBS: speed only
    knobs = json.dumps(knobs) if knobs else ""
    key = hashlib.sha1((json.dumps(spec, sort_keys=True) + code_hash(spec["action"]) + _tag(fast) + knobs).encode()).hexdigest()[:14]
    return os.path.join(CACHE, key)


def render_shot(spec, out, fast=False):
    """-> (shot.mp4, events). Cached: a shot that exists is reused."""
    sd = shot_dir(spec, fast)
    mp4 = os.path.join(sd, "shot.mp4")
    if not os.path.exists(mp4):
        fr = os.path.join(sd, "frames")
        shutil.rmtree(fr, ignore_errors=True)
        os.makedirs(fr)
        jp = os.path.join(sd, "spec.json")
        json.dump(spec, open(jp, "w"), indent=1)
        blender([jp, fr] + _flag(fast), os.path.join(out, "blender.log"))
        shutil.move(os.path.join(fr, "events.json"), os.path.join(sd, "events.json"))
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", "24", "-i", os.path.join(fr, "f_%04d.png"),
                        "-c:v", "libx264", "-preset", "medium", "-crf", "12", "-pix_fmt", "yuv420p", mp4 + ".tmp.mp4"],
                       check=True)
        os.replace(mp4 + ".tmp.mp4", mp4)
        shutil.rmtree(fr)                            # frames are not kept: the mp4 is the cache
    return mp4, json.load(open(os.path.join(sd, "events.json")))


def stills(specs, out):
    sd = os.path.join(out, "stills")
    os.makedirs(sd, exist_ok=True)
    pics = []
    for i, s in enumerate(specs):
        spec = s["spec"]
        t = round(spec["dur"] * 0.55, 2)
        d = os.path.join(sd, f"s{i:02d}")
        jp = os.path.join(sd, f"s{i:02d}.json")
        json.dump(spec, open(jp, "w"), indent=1)
        blender([jp, d, "--still", str(t), "--fast"], os.path.join(out, "blender.log"))
        raw = os.path.join(d, f"still_{t:05.2f}.png")
        g = os.path.join(sd, f"s{i:02d}.png")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", raw, "-vf", GRADE + ",scale=480:-1", g], check=True)
        pics.append(g)
    cols = 4
    while len(pics) % cols:
        pics.append(pics[-1])
    ins = sum([["-i", p] for p in pics], [])
    fc = ""
    rows = []
    for r in range(len(pics) // cols):
        fc += "".join(f"[{r * cols + c}]" for c in range(cols)) + f"hstack={cols}[r{r}];"
        rows.append(f"[r{r}]")
    fc += "".join(rows) + (f"vstack={len(rows)}" if len(rows) > 1 else "null")
    sheet = os.path.join(out, "shots_sheet.jpg")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y"] + ins + ["-filter_complex", fc, "-frames:v", "1", sheet], check=True)
    return sheet


def audio(specs, voice, events, dur, out):
    L.build()
    track = np.zeros((2, int((dur + 1) * SR)))
    for v in voice:
        y = L.read_audio(v["file"])
        a = int(v["t"] * SR)
        n = min(y.shape[1], track.shape[1] - a)
        track[:, a:a + n] += y[:, :n]
    g = 10 ** ((-14.0 - L.lufs(track)) / 20)
    vp = os.path.join(out, "voice.wav")
    L.write_wav(vp, np.clip(track * g, -1, 1))
    sfx = [{"t": round(s["t0"] + e["t"], 3), "name": e["sfx"], "gain_db": -6} for s, ev in zip(specs, events) for e in ev]
    sfx += [{"t": round(s["t0"] + 0.3, 3), "name": "chime", "gain_db": -4} for s in specs if s.get("title")]
    mix({"voice": vp, "out": os.path.join(out, "mix.wav"), "duration": dur,
         "music": {"bed": "playroom", "gap_db": -10, "duck_db": -9, "fade_in": 0.5, "fade_out": 2.0},
         "sfx": sfx, "voice_lufs": -14, "target_lufs": -14})
    return os.path.join(out, "mix.wav")


def render(story, specs, voice, dur, out, fast=False):
    # several Blender processes at once: one alone leaves the GPU idle while it loads and builds each shot
    from concurrent.futures import ThreadPoolExecutor
    jobs = int(os.environ.get("TOY_JOBS", 2 if fast else 1))          # 720p previews: two at a time
    done = [0]

    def one(i):
        r = render_shot(specs[i]["spec"], out, fast)
        done[0] += 1
        print(f"shot {done[0]}/{len(specs)} {specs[i]['spec']['action']} {specs[i]['spec']['dur']}s", flush=True)
        return r
    with ThreadPoolExecutor(max(1, jobs)) as ex:
        res = list(ex.map(one, range(len(specs))))
    clips, events = [r[0] for r in res], [r[1] for r in res]
    mixp = audio(specs, voice, events, dur, out)
    lst = os.path.join(out, "clips.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{c.replace(os.sep, '/')}'\n" for c in clips)   # forward slashes: ffmpeg lists on Windows too
    from toycolors import overlay as O
    size = "1280:720" if fast else "1920:1080"
    up = "scale=1280:720:flags=lanczos," if fast == "ultra" else ""     # ultra shots are 540p
    ins, fc, last = [], f"[0:v]{up}{GRADE}[g0];", "g0"
    for k, s in enumerate(x for x in specs if x.get("title")):     # a title card over each adventure's first shot
        tp = os.path.join(out, f"title_{k:02d}.png")
        O.title(s["title"], (255, 215, 40)).save(tp)
        ins += ["-loop", "1", "-t", str(dur), "-i", tp]
        a0, a1 = s["t0"] + 0.3, s["t0"] + min(3.6, s["spec"]["dur"] - 0.2)
        fc += f"[{k + 2}:v]scale={size}[t{k}];[{last}][t{k}]overlay=0:0:enable='between(t,{a0:.2f},{a1:.2f})'[g{k + 1}];"
        last = f"g{k + 1}"
    mp4 = os.path.join(out, {"ultra": "story_540p.mp4", True: "story_720p.mp4"}.get(fast, "story_1080p.mp4"))
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-i", mixp]
                   + ins + ["-filter_complex", fc.rstrip(";"),
                    "-map", f"[{last}]", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                    "-c:a", "aac", "-b:a", "192k", "-t", str(dur), "-movflags", "+faststart", mp4], check=True)
    return mp4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("--out")
    ap.add_argument("--stills", action="store_true")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--quality", choices=["540", "720", "1080"], default="1080")
    ap.add_argument("--fast", action="store_true", help="same as --quality 720")
    a = ap.parse_args()
    a.fast = "ultra" if a.quality == "540" else (a.fast or a.quality == "720")
    story = load(a.story)
    out = os.path.abspath(a.out or os.path.join(ROOT, "toycolors/out/stories", os.path.splitext(os.path.basename(a.story))[0]))
    os.makedirs(out, exist_ok=True)
    specs, voice, dur = layout(story, speak(story, out))
    json.dump({"duration": dur, "shots": specs, "voice": voice}, open(os.path.join(out, "plan.json"), "w"), indent=1)
    for i, s in enumerate(specs):
        lines = [v["text"] for v in voice if s["t0"] <= v["t"] < s["t0"] + s["spec"]["dur"]]
        print(f"{s['t0']:6.2f}s {s['spec']['action']:9s} {s['spec']['dur']:5.2f}s | " + " / ".join(lines))
    print(f"total {dur:.1f}s")
    if a.stills:
        print("sheet:", stills(specs, out))
    if a.render:
        print("video:", render(story, specs, voice, dur, out, fast=a.fast))


if __name__ == "__main__":
    main()
