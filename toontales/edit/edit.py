"""Toon Tales edit: rendered shot clips -> finished Short (captions, overlays, voice, SFX, music, loudness).

Run: python3 -m toontales.edit.edit <plan.json> [--draft]
  uses toontales/build/stories/<id>/clips[_draft].json from the shot builder; renders nothing in Blender.
Out: out/toontales_<id>.mp4  (or out/toontales_<id>_draft_edit.mp4)

Per shot (cached): one-word captions ~70% down (word timings from the voice), the plan overlay
(chalk / arrow / circle / stamp / label / cross). Then the shots are joined (hard cuts; dissolves only on
time jumps) and the sound is mixed: voice lines back to back, plan SFX, automatic SFX for physical
actions (fall, bonk, throw, jump, crash zoom, overlay pop), a banjo bed ducked under the voice, -14 LUFS.

Retention layer: hook title card on the first shot + punch-in zoom (first shot, stamp overlays, plan
"punch"); key words (numbers, money, plan "keywords") pop bigger in yellow; a shot's "freeze" holds its
last frame (FREEZE s, with the text as a big card, record scratch, music stops) as a pattern break;
music follows the story mood per beat (upbeat -> sneaky con -> sad twist -> upbeat payoff), with a
whoosh on every change of place; music never fades at the very end so the Short loops cleanly.
"""
import re
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from toontales.plan import schema as S

TT = S.TT
ROOT = TT.parent
sys.path[:0] = [str(TT / "audio"), str(TT / "edit")]
import art  # noqa: E402
import hud  # noqa: E402
import sfx  # noqa: E402
import voice  # noqa: E402

BUILD = TT / "build"
SR = 48000
DISSOLVE = 0.3
POP = 1 / 15                      # caption pop-in: slightly bigger for the first two frames
OVERLAY_IN = 0.12
VERSION = "e2"
FREEZE = 0.65
TITLE_T = 1.7
PUNCH = 1.14
MOOD = {"hook": "upbeat", "concept": "upbeat", "setup": "upbeat", "deadline": "sneaky", "obstacle": "sneaky",
        "con": "sneaky", "escalate": "sneaky", "twist": "sad", "payoff": "upbeat"}
HOT_RE = re.compile(r"[\d$%]")
SFX_GAIN = {"boom": 0.55, "gunshot": 0.5, "thud": 0.6, "whoosh": 0.35, "pop": 0.4, "crowd": 0.35, "car": 0.45,
            "train": 0.4, "laugh": 0.6, "gasp": 0.6}
AUTO = {  # action -> (sound, seconds after the action starts)
    "fall": ("thud", 0.62), "bonk": ("bonk", 0.0), "throw": ("whoosh", 0.5),
    "pick_up": ("paper", 0.45), "celebrate": ("pop", 0.1), "jump": ("boing", 0.2),
}
MUSIC_GAIN, MUSIC_DUCK = 0.20, 0.5


def _probe_size(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height", "-of", "csv=p=0", str(path)], text=True)
    w, h = out.strip().split(",")[:2]
    return int(w), int(h)


def caption_windows(words, dur):
    """[(word, t0, t1)]: each word stays until the next one starts; the last one holds a moment."""
    out = []
    for i, w in enumerate(words):
        if not art.clean_word(w["w"]):
            continue
        t0 = w["t0"]
        t1 = words[i + 1]["t0"] if i + 1 < len(words) else min(dur, w["t1"] + 0.25)
        if t1 - t0 > 0.02:
            out.append((w["w"], round(t0, 3), round(min(t1, dur), 3)))
    return out


def phrase_windows(words, dur, max_words=4, max_chars=20):
    """[(phrase, t0, t1)]: 2-4 words per caption, broken after punctuation; each holds until the next starts."""
    groups, cur = [], []
    ws = [w for w in words if art.clean_word(w["w"])]
    for i, w in enumerate(ws):
        cur.append(w)
        text = " ".join(x["w"] for x in cur)
        nxt = ws[i + 1]["w"] if i + 1 < len(ws) else ""
        ends = w["w"][-1:] in ",.;:?!"
        full = len(cur) >= max_words or len(text) >= max_chars
        if full and not ends and nxt[-1:] in ",.;:?!" and len(cur) <= max_words and len(text) + len(nxt) < max_chars + 8:
            continue  # let the clause's last word join this phrase instead of standing alone
        if ends or full or len(cur) > max_words:
            groups.append(cur)
            cur = []
    if cur:
        if groups and len(cur) == 1 and len(" ".join(x["w"] for x in groups[-1])) < max_chars:
            groups[-1] += cur  # no lonely last word
        else:
            groups.append(cur)
    out = []
    for i, g in enumerate(groups):
        t0 = g[0]["t0"]
        t1 = groups[i + 1][0]["t0"] if i + 1 < len(groups) else min(dur, g[-1]["t1"] + 0.35)
        out.append((" ".join(x["w"] for x in g), round(t0, 3), round(min(t1, dur), 3)))
    return out


def is_hot(word, keywords):
    w = art.clean_word(word)
    return bool(HOT_RE.search(w)) or w.lower() in keywords


def compose_shot(clip, words, overlay, dur, size, work, keywords=(), punch=False, title=None, hud_spec=None,
                 callout=None, phrases=False):
    """Burn punch zoom, title card, captions, overlay and the car HUD (meter, callout) into one shot clip
    (cached by content)."""
    wins = phrase_windows(words, dur) if phrases else caption_windows(words, dur)
    if title and callout:  # the hook title card owns the top third: hang the label below it
        callout = dict(callout, text_y=max(callout.get("text_y", 0.2), 0.37), y=max(callout.get("y", 0.34), 0.5))
    parts =[Path(clip).name, wins, overlay, size, art.VERSION, VERSION, sorted(keywords), punch, title, phrases]
    if hud_spec or callout:
        parts += [hud_spec, callout, hud.VERSION]
    key = hashlib.sha1(json.dumps(parts).encode()).hexdigest()[:16]
    out = work / f"{key}.mp4"
    if out.exists():
        return out
    W, H = size
    inputs, chain, n = ["-i", str(clip)], [], 1
    if punch:  # snap in over 4 frames, ease back out over a second: a hit on the first beat
        z = f"if(lt(on,4),1+{PUNCH - 1:.3f}*on/4,max(1,{PUNCH:.3f}-{PUNCH - 1:.3f}*(on-4)/30))"
        chain.append(f"[0:v]zoompan=z='{z}':d=1:x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':s={W}x{H}:fps=30[z]")
        last = "[z]"
    else:
        last = "[0:v]"
    if title:
        inputs += ["-i", str(art.title(title, size))]
        chain.append(f"{last}[{n}:v]overlay=0:0:enable='lt(t,{TITLE_T})'[v{n}]")
        last, n = f"[v{n}]", n + 1
    if hud_spec:
        inputs += ["-framerate", "30", "-i", hud.frames(hud_spec, dur, size, work)]
        chain.append(f"{last}[{n}:v]overlay=0:0:eof_action=repeat[v{n}]")
        last, n = f"[v{n}]", n + 1
    if callout:
        inputs += ["-i", str(hud.callout(callout, size, work))]
        chain.append(f"{last}[{n}:v]overlay=0:0:enable='gte(t,{OVERLAY_IN})'[v{n}]")
        last, n = f"[v{n}]", n + 1
    if overlay:
        inputs += ["-i", str(art.overlay(overlay, size))]
        chain.append(f"{last}[{n}:v]overlay=0:0:enable='gte(t,{OVERLAY_IN})'[v{n}]")
        last, n = f"[v{n}]", n + 1
    for w, t0, t1 in (wins if phrases else []):  # calm phrase captions: one image per phrase, no pop
        inputs += ["-i", str(art.phrase(w, size))]
        chain.append(f"{last}[{n}:v]overlay=0:0:enable='between(t,{t0},{t1})'[v{n}]")
        last, n = f"[v{n}]", n + 1
    for w, t0, t1 in ([] if phrases else wins):
        hot = is_hot(w, keywords)
        big, small = art.caption(w, size, pop=True, hot=hot), art.caption(w, size, hot=hot)
        inputs += ["-i", str(big), "-i", str(small)]
        chain.append(f"{last}[{n}:v]overlay=0:0:enable='between(t,{t0},{min(t1, t0 + POP):.3f})'[v{n}]")
        chain.append(f"[v{n}][{n + 1}:v]overlay=0:0:enable='between(t,{t0 + POP:.3f},{t1})'[v{n + 1}]")
        last, n = f"[v{n + 1}]", n + 2
    cmd = ["ffmpeg", "-v", "error", "-y", *inputs]
    if chain:
        cmd += ["-filter_complex", ";".join(chain), "-map", last]
    cmd += ["-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "medium", "-r", "30",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", str(out)]
    subprocess.run(cmd, check=True)
    return out


def freeze_part(shot_part, text, size, work):
    """FREEZE s hold of a shot's last frame: slight zoom, cooler colour, the text as a big card."""
    key = hashlib.sha1(json.dumps([Path(shot_part).name, text, size, VERSION]).encode()).hexdigest()[:16]
    out = work / f"frz_{key}.mp4"
    if out.exists():
        return out
    W, H = size
    still = work / f"frz_{key}.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-sseof", "-0.1", "-i", str(shot_part), "-frames:v", "1",
                    "-update", "1", str(still)], check=True)
    inputs = ["-loop", "1", "-t", f"{FREEZE}", "-i", str(still)]
    chain = [f"[0:v]scale={int(W * 1.06)}:{int(H * 1.06)},crop={W}:{H},eq=saturation=0.55:brightness=-0.04[f]"]
    last = "[f]"
    if text:
        inputs += ["-i", str(art.freeze_text(text, size))]
        chain.append(f"[f][1:v]overlay=0:0[t]")
        last = "[t]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(chain), "-map", last,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "medium", "-r", "30",
                    "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", str(out)], check=True)
    return out


def timeline(clips):
    """Start time of every shot (dissolves overlap the previous shot; freezes add a hold after theirs),
    the start of every freeze, and the total length."""
    starts, freezes, t = [], [], 0.0
    for i, c in enumerate(clips):
        if i and c.get("transition") == "dissolve":
            t -= DISSOLVE
        starts.append(round(t, 3))
        t += c["dur"]
        if c.get("freeze") is not None:
            freezes.append(round(t, 3))
            t += FREEZE
    return starts, freezes, round(t, 3)


def join_video(seq, out):
    """seq: [(path, dur, transition)] in order (freeze holds included)."""
    if not any(tr == "dissolve" for _, _, tr in seq[1:]):
        lst = out.with_suffix(".txt")
        lst.write_text("".join(f"file '{p}'\n" for p, _, _ in seq))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                        str(out)], check=True)
        return out
    inputs = sum((["-i", str(p)] for p, _, _ in seq), [])
    chain, last, acc = [], "[0:v]", seq[0][1]
    for i in range(1, len(seq)):
        if seq[i][2] == "dissolve":
            chain.append(f"{last}[{i}:v]xfade=transition=fade:duration={DISSOLVE}:offset={acc - DISSOLVE:.3f}[x{i}]")
            acc += seq[i][1] - DISSOLVE
        else:
            chain.append(f"{last}[{i}:v]concat=n=2:v=1:a=0[x{i}]")
            acc += seq[i][1]
        last = f"[x{i}]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(chain), "-map", last,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "medium", str(out)], check=True)
    return out


def _load(path):
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(SR),
                                   "-"])
    return np.frombuffer(raw, dtype="<f4").reshape(-1, 2).T.copy()


def _place(buf, x, at, gain=1.0):
    i = int(round(at * SR))
    if i < 0:
        x, i = x[:, -i:], 0
    m = min(x.shape[1], buf.shape[1] - i)
    if m > 0:
        buf[:, i:i + m] += x[:, :m] * gain


def sound_cues(clips, shots, starts, freezes=()):
    """Every SFX in the film: the plan's own plus automatic ones for actions, camera hits, overlays,
    place changes (whoosh) and freeze holds (record scratch)."""
    cues = [("scratch", t) for t in freezes]
    for i, (c, sj, st) in enumerate(zip(clips, shots, starts)):
        if i and c.get("set") != clips[i - 1].get("set"):
            cues.append(("whoosh", st - 0.12))
        for fx in c.get("sfx") or []:
            cues.append((fx["name"], st + float(fx.get("at", 0))))
        for a in sj.get("actions", []):
            if a["do"] in AUTO:
                name, dt = AUTO[a["do"]]
                cues.append((name, st + a["t0"] + dt))
        if sj.get("camera", {}).get("ease") == "out_fast":
            cues.append(("whoosh", st))
        if c.get("overlay"):
            cues.append(("pop", st + OVERLAY_IN))
    cues.sort(key=lambda x: x[1])
    out = []
    for name, t in cues:  # the plan's sound wins over an automatic duplicate
        if not any(n == name and abs(t - u) < 0.4 for n, u in out):
            out.append((name, t))
    return out


def music_runs(clips, starts, freezes, total):
    """[(mood, t0, t1)]: one run per stretch of the same mood; a freeze cuts the music."""
    marks = [(st, c.get("mood") or MOOD.get(c.get("beat"), "upbeat")) for c, st in zip(clips, starts)]
    cuts = sorted(freezes)
    runs = []
    for i, (st, mood) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else total
        fz = next((f for f in cuts if st < f <= end), None)
        if fz is not None:
            end = fz
        if runs and runs[-1][0] == mood and abs(runs[-1][2] - st) < 0.05:
            runs[-1][2] = end
        else:
            runs.append([mood, st, end])
    return [tuple(r) for r in runs if r[2] - r[1] > 0.05]


def mix(clips, shots, starts, total, out, freezes=()):
    buf_v = np.zeros((2, int(total * SR) + SR))
    for c, st in zip(clips, starts):
        _place(buf_v, _load(c["wav"]), st)
    peak = np.abs(buf_v).max() + 1e-9
    buf_v *= 0.8 / peak
    buf_fx = np.zeros_like(buf_v)
    for name, t in sound_cues(clips, shots, starts, freezes):
        _place(buf_fx, _load(sfx.path(name)), t, SFX_GAIN.get(name, 0.5))
    buf_m = np.zeros_like(buf_v)
    runs = music_runs(clips, starts, freezes, total)
    for k, (mood, t0, t1) in enumerate(runs):
        bed = _load(sfx.music_bed(t1 - t0 + 2.0, mood=mood))[:, : int((t1 - t0) * SR)]
        n = bed.shape[1]
        fi, fo = int(0.08 * SR), int(0.15 * SR) if k + 1 < len(runs) else 0  # the end never fades: it loops
        ramp = np.ones(n)
        ramp[:fi] = np.linspace(0, 1, min(fi, n))[: min(fi, n)]
        fo = min(fo, n // 2)
        if fo:
            ramp[-fo:] = np.linspace(1, 0, fo)
        _place(buf_m, bed * ramp, t0, MUSIC_GAIN)
    # duck the bed under the voice: 50 ms RMS envelope, smoothed
    mono = buf_v.mean(0) ** 2
    win = int(0.05 * SR)
    env = np.sqrt(np.convolve(mono, np.ones(win) / win, "same"))
    env = np.convolve(env, np.ones(int(0.2 * SR)) / int(0.2 * SR), "same")
    duck = 1 - MUSIC_DUCK * np.clip(env / 0.04, 0, 1)
    mixed = buf_v + buf_fx + buf_m * duck
    mixed = mixed[:, : int(total * SR)]
    mixed *= 0.95 / (np.abs(mixed).max() + 1e-9)
    raw = out.with_suffix(".f32")
    raw.write_bytes(mixed.T.astype("<f4").tobytes())
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", str(raw), str(out)],
                   check=True)
    raw.unlink()
    return out


def edit(plan_path, draft=False):
    plan = S.load_plan(plan_path)
    import os
    os.environ["TT_CAST"] = str(S.cast_file_for(plan))  # word timing in the channel cast's voices
    sid = plan["id"]
    work = BUILD / "stories" / sid
    man = json.loads((work / ("clips_draft.json" if draft else "clips.json")).read_text())
    clips = man["clips"]
    missing = [c["id"] for c in clips if not Path(c["clip"]).exists()]
    if missing:
        raise SystemExit(f"shots not rendered yet: {', '.join(missing)} (run toontales.shots.build_story first)")
    shots = [json.loads((work / "shots" / f"{c['id']}.json").read_text()) for c in clips]
    size = _probe_size(clips[0]["clip"])
    ed = BUILD / "edit"
    ed.mkdir(parents=True, exist_ok=True)
    keywords = {k.lower() for k in man.get("keywords") or []}
    seq = []
    ch = S.channel(plan)
    phrases = ch.get("captions") == "phrase"  # Channel 5: calm phrase captions, no punch-ins, no title slab
    voice.prefetch_words([(c["speaker"], c["text"], c["voice_dur"]) for c in clips], BUILD / "voice")
    for i, c in enumerate(clips):
        ws = voice.speak_words(c["speaker"], c["text"], BUILD / "voice", dur=c["voice_dur"])
        punch = i == 0 or bool(c.get("punch")) or (c.get("overlay") or {}).get("type") == "stamp"
        punch = punch and not phrases
        title = man.get("hook_title") if i == 0 and ch.get("title_card", True) else None
        part = compose_shot(c["clip"], ws, c.get("overlay"), c["dur"], size, ed, keywords, punch,
                            title, c.get("hud"), c.get("callout"), phrases)
        seq.append((part, c["dur"], c.get("transition", "cut")))
        if c.get("freeze") is not None:
            seq.append((freeze_part(part, c["freeze"], size, ed), FREEZE, "cut"))
        print("SHOT", c["id"], "captions", len(ws), flush=True)
    starts, freezes, total = timeline(clips)
    video = join_video(seq, work / "video.mp4")
    audio = mix(clips, shots, starts, total, work / "mix.wav", freezes)
    out = ROOT / "out" / f"toontales_{sid}{'_draft_edit' if draft else ''}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-i", str(audio), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", str(SR), "-c:a", "aac",
                    "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)], check=True)
    print("FINAL ->", out, f"({total:.1f}s)")
    return out


if __name__ == "__main__":
    edit(Path(sys.argv[1]), draft="--draft" in sys.argv)
