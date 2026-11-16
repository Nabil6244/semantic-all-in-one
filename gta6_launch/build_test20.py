"""GTA 6 launch: 20 s "Leonida vs real Florida" test cut.

Game footage (Rockstar Trailer 2, muted) vs free Pexels Florida footage,
Vice-sunset graphics, a synthwave bed made here in code, edge-tts voice.
Run:  python3 gta6_launch/build_test20.py
"""
import asyncio, json, math, subprocess, wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
FOOT = ROOT / "footage"
WORK = ROOT / "work"
OUT = ROOT / "out"
WORK.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)

W, H, FPS, TOTAL = 1920, 1080, 30, 20.0
PINK, TEAL, NAVY, WHITE = (255, 46, 136), (0, 214, 201), (12, 16, 40), (255, 255, 255)
F_HEAD = "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf"
F_TAG = str(REPO / "assets/fonts/Outfit-ExtraBold.ttf")
TRAILER = FOOT / "trailer/gta6_trailer2.mp4"
STOCK = FOOT / "stock"
VOICE = "en-US-AndrewNeural"

# (voice line, shot) — shot: kind, sources, captions
SHOTS = [
    dict(line="GTA 6 drops November nineteenth.", kind="full",
         src=(TRAILER, 152.95, 0.0), head="NOV 19", sub="GTA VI  ·  3 DAYS TO LAUNCH"),
    dict(line="But its map isn't made up.", kind="full",
         src=(TRAILER, 38.5, 0.0), head="IS LEONIDA REAL?", sub=None),
    dict(line="Vice City? That's Miami.", kind="split",
         game=(TRAILER, 34.7), real=(STOCK / "pexels_11094699.mp4", 10.5),
         label=("VICE CITY", "MIAMI")),
    dict(line="The swamps are the Everglades. Even the airboats are real.", kind="split",
         game=(TRAILER, 138.2), real=(STOCK / "pexels_11840880.mp4", 0.3),
         label=("GRASSRIVERS", "EVERGLADES"), game_slow=0.48),
    dict(line="And those beaches? Miami Beach.", kind="split",
         game=(TRAILER, 6.1), real=(STOCK / "pexels_4135117.mp4", 2.0),
         label=("LEONIDA COAST", "MIAMI BEACH"), game_slow=0.7),
    dict(line="This is the real Florida behind GTA six.", kind="full",
         src=(STOCK / "pexels_3770584.mp4", 7.0, 0.0), head="THE REAL LEONIDA",
         sub="FULL VIDEO  ·  NOV 19", end=True),
]


def run(cmd):
    subprocess.run(cmd, check=True)


def dur(p):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]))


# ---------- voice ----------
async def _tts(text, path):
    import edge_tts
    await edge_tts.Communicate(text, VOICE, rate="+6%").save(str(path))


def make_voice():
    for i, s in enumerate(SHOTS):
        mp3 = WORK / f"vo{i}.mp3"
        for attempt in range(4):
            if mp3.exists() and mp3.stat().st_size > 0:
                break
            text = s["line"] if attempt < 2 else s["line"].replace("?", ",")
            try:
                asyncio.run(_tts(text, mp3))
            except Exception as e:
                print("voice retry", i, e)
                mp3.unlink(missing_ok=True)
        s["vo"] = mp3
        s["vo_dur"] = dur(mp3)
    # timing: 0.35 s lead, 0.3 s gap after each line; last shot fills to TOTAL
    t = 0.35
    for i, s in enumerate(SHOTS):
        s["vo_at"] = t
        s["start"] = 0.0 if i == 0 else t - 0.12   # cut just before the line
        t += s["vo_dur"] + 0.3
    for i, s in enumerate(SHOTS):
        nxt = SHOTS[i + 1]["start"] if i + 1 < len(SHOTS) else TOTAL
        s["len"] = round(nxt - s["start"], 3)
    assert SHOTS[-1]["len"] > 2.0, "voice too long for 20 s"


# ---------- graphics ----------
def font(path, size):
    return ImageFont.truetype(path, size)


def shadow_text(img, xy, text, f, fill=WHITE, anchor="mm", blur=10):
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((xy[0] + 4, xy[1] + 6), text, font=f, fill=(0, 0, 0, 200), anchor=anchor)
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))
    ImageDraw.Draw(img).text(xy, text, font=f, fill=fill, anchor=anchor)


def pill(img, xy, text, bg, size=40, anchor="lt"):
    d = ImageDraw.Draw(img)
    f = font(F_TAG, size)
    l, t, r, b = d.textbbox((0, 0), text, font=f)
    pw, ph = r - l + 44, b - t + 26
    x, y = xy
    if anchor == "rt":
        x -= pw
    d.rounded_rectangle((x, y, x + pw, y + ph), radius=ph // 2, fill=bg + (235,))
    d.text((x + 22 - l, y + 13 - t), text, font=f, fill=WHITE)


def headline_png(s, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # soft dark band at bottom so text reads on bright footage
    band = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    for y in range(H // 2, H):
        a = int(170 * ((y - H / 2) / (H / 2)) ** 1.6)
        bd.line([(0, y), (W, y)], fill=NAVY + (a,))
    img.alpha_composite(band)
    big = 210 if len(s["head"]) < 10 else 170
    f = font(F_HEAD, big)
    shadow_text(img, (W // 2, 760), s["head"], f)
    tw = ImageDraw.Draw(img).textlength(s["head"], font=f)
    ImageDraw.Draw(img).rectangle((W // 2 - tw / 2, 850, W // 2 + tw / 2, 862), fill=PINK)
    if s.get("sub"):
        shadow_text(img, (W // 2, 925), s["sub"], font(F_TAG, 46), fill=(255, 220, 235))
    pill(img, (70, 60), "GTA VI", PINK, 38)
    img.save(path)


def split_png(s, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((W // 2 - 5, 0, W // 2 + 5, H), fill=PINK + (255,))
    pill(img, (60, 60), "IN GAME", PINK, 40)
    pill(img, (W - 60, 60), "REAL LIFE", (0, 150, 150), 40, anchor="rt")
    band = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    for y in range(H - 330, H):
        a = int(190 * ((y - (H - 330)) / 330) ** 1.4)
        bd.line([(0, y), (W, y)], fill=NAVY + (a,))
    img.alpha_composite(band)
    g, r = s["label"]
    f = font(F_HEAD, 120)
    eq = "  =  "
    wg, we, wr = (d.textlength(t, font=f) for t in (g, eq, r))
    x = W / 2 - (wg + we + wr) / 2
    shadow_text(img, (x, 990), g, f, anchor="ls")
    shadow_text(img, (x + wg, 990), eq, f, fill=PINK, anchor="ls")
    shadow_text(img, (x + wg + we, 990), r, f, fill=TEAL, anchor="ls")
    img.save(path)


# ---------- shots ----------
GLITCH = "rgbashift=rh=-14:bh=14:gv=6:enable='lt(t,0.18)',noise=alls=35:allf=t:enable='lt(t,0.14)'"


def render_shot(i, s):
    out = WORK / f"shot{i}.mp4"
    L = s["len"]
    png = WORK / f"ov{i}.png"
    ease = "pow(max(0,1-t/0.4),2)"
    if s["kind"] == "full":
        headline_png(s, png)
        p, ss, _ = s["src"]
        slow = s.get("slow", 1.0)
        need = L * slow + 0.2
        fc = (f"[0:v]setpts=PTS/{slow},fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,"
              f"crop={W}:{H},scale=w='trunc({W}*(1+0.07*t/{L})/2)*2':h=-2:eval=frame,"
              f"crop={W}:{H},setsar=1[bg];"
              f"[1:v]format=rgba,fade=in:st=0.15:d=0.35:alpha=1[ov];"
              f"[bg][ov]overlay=x=0:y='60*{ease.replace('t/0.4', '(t-0.15)/0.4')}':shortest=0,{GLITCH}[v]")
        inputs = ["-ss", str(ss), "-t", str(need), "-i", str(p)]
    else:
        split_png(s, png)
        (gp, gss), (rp, rss) = s["game"], s["real"]
        gs = s.get("game_slow", 1.0)
        half = f"scale=-2:{H},crop={W//2}:{H}"
        fc = (f"[0:v]setpts=PTS/{gs},fps={FPS},{half},setsar=1[g];"
              f"[2:v]fps={FPS},{half},setsar=1[r];"
              f"color=c=black:s={W}x{H}:r={FPS}:d={L}[base];"
              f"[base][g]overlay=x=0:y=0:shortest=1[b1];"
              f"[b1][r]overlay=x='{W//2}+{W//2}*pow(max(0,1-(t-0.25)/0.45),3)':y=0[b2];"
              f"[1:v]format=rgba,fade=in:st=0.3:d=0.3:alpha=1[ov];"
              f"[b2][ov]overlay=0:0,{GLITCH}[v]")
        inputs = ["-ss", str(gss), "-t", str(L * gs + 0.2), "-i", str(gp)]
    run(["ffmpeg", "-v", "error", "-y", *inputs,
         "-loop", "1", "-t", str(L), "-i", str(png),
         *([] if s["kind"] == "full" else ["-ss", str(s["real"][1]), "-t", str(L + 0.2), "-i", str(s["real"][0])]),
         "-filter_complex", fc, "-map", "[v]", "-t", str(L), "-r", str(FPS),
         "-c:v", "libx264", "-preset", "fast", "-crf", "16", "-pix_fmt", "yuv420p", "-an", str(out)])
    return out


# ---------- music: synthwave bed made in code ----------
SR = 44100


def synthwave(seconds, path):
    bpm = 108
    beat = 60 / bpm
    n = int(seconds * SR)
    t = np.arange(n) / SR
    mix = np.zeros(n)
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)
    chords = [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62)]  # Am F C G
    bar = beat * 4

    def lp(x, a):
        y = np.empty_like(x); acc = 0.0
        for k in range(len(x)):
            acc += a * (x[k] - acc); y[k] = acc
        return y

    def saw(f, tt):
        return 2 * ((tt * f) % 1) - 1

    # pad
    pad = np.zeros(n)
    for c in range(int(seconds / bar) + 1):
        s0 = int(c * bar * SR); s1 = min(n, int((c + 1) * bar * SR))
        if s0 >= n: break
        tt = t[s0:s1] - t[s0]
        env = np.minimum(1, tt / 0.6) * np.minimum(1, (bar - tt) / 0.3)
        for m in chords[c % 4]:
            for det in (-0.12, 0.12):
                pad[s0:s1] += saw(hz(m + 12) * 2 ** (det / 12), tt) * env
    mix += lp(pad, 0.06) * 0.05
    # bass 8ths
    for k in range(int(seconds / (beat / 2))):
        s0 = int(k * beat / 2 * SR); s1 = min(n, s0 + int(beat / 2 * SR))
        if s0 >= n: break
        tt = t[s0:s1] - t[s0]
        root = chords[int(k * beat / 2 / bar) % 4][0] - 24
        mix[s0:s1] += saw(hz(root), tt) * np.exp(-tt * 6) * 0.22
    # arp 16ths
    for k in range(int(seconds / (beat / 4))):
        s0 = int(k * beat / 4 * SR); s1 = min(n, s0 + int(beat / 4 * SR))
        if s0 >= n: break
        tt = t[s0:s1] - t[s0]
        ch = chords[int(k * beat / 4 / bar) % 4]
        m = (ch + tuple(x + 12 for x in ch))[k % 6] + 12
        mix[s0:s1] += np.sign(np.sin(2 * np.pi * hz(m) * tt)) * np.exp(-tt * 18) * 0.035
    # drums
    rng = np.random.default_rng(7)
    for k in range(int(seconds / beat) + 1):
        s0 = int(k * beat * SR)
        if s0 >= n: break
        seg = min(n - s0, int(0.45 * SR)); tt = np.arange(seg) / SR
        if k % 2 == 0:  # kick
            mix[s0:s0 + seg] += np.sin(2 * np.pi * (45 * tt + 2.5 * (1 - np.exp(-tt * 30)))) * np.exp(-tt * 9) * 0.5
        else:  # gated snare
            mix[s0:s0 + seg] += rng.standard_normal(seg) * np.exp(-tt * 9) * 0.16
        for h in (0, 0.5):  # hats
            hs = int((k + h) * beat * SR); hl = min(n - hs, int(0.05 * SR))
            if hl > 0:
                mix[hs:hs + hl] += np.diff(rng.standard_normal(hl + 1)) * np.exp(-np.arange(hl) / SR * 80) * 0.03
    fade = np.minimum(1, t / 0.4) * np.minimum(1, (seconds - t) / 1.2)
    mix = np.tanh(mix * fade * 1.4) * 0.7
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())


# ---------- audio mix + final ----------
def final(shots):
    lst = WORK / "concat.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in shots))
    silent = WORK / "video.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-vf", "eq=saturation=1.12:contrast=1.05,"
                "colorbalance=rs=-0.03:bs=0.06:rh=0.06:bh=-0.04,vignette=PI/5",
         "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
         "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", str(silent)])
    music = WORK / "synthwave.wav"
    synthwave(TOTAL, music)
    whoosh = REPO / "assets/bundled-sfx/wall/whoosh.wav"
    impact = REPO / "assets/bundled-sfx/impact/impact_001.opus"
    ins, parts = [], []
    for i, s in enumerate(SHOTS):
        ins += ["-i", str(s["vo"])]
        parts.append(f"[{i}:a]adelay={int(s['vo_at']*1000)}:all=1,volume=1.6[v{i}]")
    k = len(SHOTS)
    ins += ["-i", str(music)]
    sfx = []
    for j, s in enumerate(SHOTS[1:], 1):
        ins += ["-i", str(whoosh)]
        parts.append(f"[{k+j}:a]adelay={max(0,int(s['start']*1000)-120)}:all=1,volume=0.35[w{j}]")
        sfx.append(f"[w{j}]")
    ins += ["-i", str(impact)]
    ki = k + len(SHOTS)
    parts.append(f"[{ki}:a]adelay={int(SHOTS[-1]['start']*1000)}:all=1,volume=0.5[imp]")
    vo = "".join(f"[v{i}]" for i in range(k))
    parts.append(f"{vo}amix=inputs={k}:normalize=0,asplit=2[vo][sc]")
    parts.append(f"[{k}:a]volume=0.55[mus]")
    parts.append("[mus][sc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=350[duck]")
    parts.append(f"[vo][duck]{''.join(sfx)}[imp]amix=inputs={len(sfx)+3}:normalize=0,"
                 f"alimiter=limit=0.9,atrim=0:{TOTAL}[a]")
    mixwav = WORK / "mix.wav"
    run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(parts),
         "-map", "[a]", "-ar", "48000", "-ac", "2", str(mixwav)])
    out = OUT / "gta6_leonida_test_20s.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(mixwav), "-map", "0:v", "-map", "1:a",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", str(TOTAL), "-movflags", "+faststart", str(out)])
    return out


if __name__ == "__main__":
    make_voice()
    print(json.dumps([(s["line"], round(s["start"], 2), s["len"]) for s in SHOTS], indent=1))
    shots = [render_shot(i, s) for i, s in enumerate(SHOTS)]
    print(final(shots), dur(OUT / "gta6_leonida_test_20s.mp4"))
