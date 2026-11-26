"""Reddit-style story Shorts (Ch1): post card while the title is read, then big word captions,
over narration-matched cartoon pictures (painted once by reddit_shorts.paint), each cut in on its phrase
with a slow push-in.

Usage: python3 -m reddit_shorts.render <story_id> [<story_id> ...]   (or 'all'); the app uses reddit_shorts.runner
Output: out/reddit_shorts/<id>.mp4, copied to $DEST (default ~/Downloads/Reddit Shorts Ch1).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import edge_voiceover  # noqa: E402
import re  # noqa: E402

W, H, FPS = 1080, 1920, 30
FONTS = os.path.join(ROOT, "assets", "fonts")
CAP_FONT = os.path.join(FONTS, "Outfit-ExtraBold.ttf")
CARD_BOLD = os.path.join(FONTS, "Inter-Bold.ttf")
CARD_REG = os.path.join(FONTS, "Inter-Regular.ttf")
SFX = os.path.join(ROOT, "assets", "bundled-sfx")
MUSIC_DIR = os.path.join(ROOT, "assets", "music")
OUT = os.path.join(ROOT, "out", "reddit_shorts")
DEST = os.environ.get("DEST", os.path.expanduser("~/Downloads/Reddit Shorts Ch1"))

YELLOW = (255, 221, 51)
SPEED = 1.1


def _font(path, size):
    return ImageFont.truetype(path, size)


def _wrap(draw, text, font, width):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def make_card(st) -> Image.Image:
    cw, pad = 960, 44
    title_f = _font(CARD_BOLD, 56)
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    lines = _wrap(probe, st["title"], title_f, cw - 2 * pad)
    lh = 70
    ch = pad + 96 + 26 + len(lines) * lh + 30 + 56 + pad
    img = Image.new("RGBA", (cw + 40, ch + 40), (0, 0, 0, 0))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((26, 30, cw + 26, ch + 30), 40, fill=(0, 0, 0, 90))
    img = Image.alpha_composite(img, sh)
    d = ImageDraw.Draw(img)
    x0, y0 = 20, 20
    d.rounded_rectangle((x0, y0, x0 + cw, y0 + ch), 40, fill=(255, 255, 255, 255))
    # avatar: plain orange circle with a smile (generic, no logo)
    ax, ay = x0 + pad, y0 + pad
    d.ellipse((ax, ay, ax + 96, ay + 96), fill=(255, 112, 36))
    d.ellipse((ax + 28, ay + 34, ax + 40, ay + 46), fill="white")
    d.ellipse((ax + 56, ay + 34, ax + 68, ay + 46), fill="white")
    d.arc((ax + 26, ay + 40, ax + 70, ay + 74), 20, 160, fill="white", width=6)
    d.text((ax + 120, ay + 6), f"r/{st['sub']}", font=_font(CARD_BOLD, 40), fill=(20, 20, 20))
    d.text((ax + 120, ay + 56), f"u/{st['user']} · 6h", font=_font(CARD_REG, 32), fill=(120, 124, 128))
    ty = ay + 96 + 26
    for i, ln in enumerate(lines):
        d.text((x0 + pad, ty + i * lh), ln, font=title_f, fill=(15, 15, 15))
    fy = ty + len(lines) * lh + 30
    small = _font(CARD_BOLD, 34)
    # upvote pill
    d.rounded_rectangle((x0 + pad, fy, x0 + pad + 250, fy + 56), 28, fill=(238, 240, 243))
    tx = x0 + pad + 24
    d.polygon([(tx, fy + 38), (tx + 14, fy + 16), (tx + 28, fy + 38)], fill=(255, 69, 0))
    d.text((tx + 42, fy + 8), st["ups"], font=small, fill=(30, 30, 30))
    d.polygon([(tx + 170, fy + 18), (tx + 184, fy + 40), (tx + 198, fy + 18)], fill=(120, 124, 128))
    # comments pill
    cx = x0 + pad + 274
    d.rounded_rectangle((cx, fy, cx + 230, fy + 56), 28, fill=(238, 240, 243))
    d.rounded_rectangle((cx + 22, fy + 16, cx + 52, fy + 40), 8, outline=(80, 84, 88), width=4)
    d.text((cx + 66, fy + 8), st["com"], font=small, fill=(30, 30, 30))
    # share pill
    sx = cx + 254
    d.rounded_rectangle((sx, fy, sx + 170, fy + 56), 28, fill=(238, 240, 243))
    d.text((sx + 30, fy + 8), "Share", font=small, fill=(30, 30, 30))
    return img


def make_caption(words, active) -> Image.Image:
    size = 128
    while True:
        f = _font(CAP_FONT, size)
        probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        text = " ".join(w.upper() for w in words)
        tw = probe.textlength(text, font=f)
        if tw <= 960 or size <= 70:
            break
        size -= 6
    stroke = max(8, size // 11)
    sp = probe.textlength(" ", font=f)
    img = Image.new("RGBA", (int(tw) + 4 * stroke, size + 4 * stroke + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = 2 * stroke
    for i, w in enumerate(words):
        wu = w.upper()
        d.text((x, 2 * stroke), wu, font=f, fill=YELLOW if i == active else (255, 255, 255),
               stroke_width=stroke, stroke_fill=(0, 0, 0))
        x += probe.textlength(wu, font=f) + sp
    return img


def _ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def chunks_of(words):
    out, cur = [], []
    for i, w in enumerate(words):
        if cur and (len(cur) >= 3 or w["start"] - cur[-1]["end"] > 0.28
                    or sum(len(x["word"]) for x in cur) + len(w["word"]) > 16):
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def _norm(w):
    return re.sub(r"[^a-z0-9]", "", w.lower())


def beat_times(beats, words, n_title, sid=""):
    """Start time of every picture: the title picture at 0, the rest on the first word of their phrase."""
    toks = [_norm(w["word"]) for w in words]
    out, pos = [], n_title
    for ph, _ in beats:
        p = [_norm(x) for x in ph.split() if _norm(x)]
        if not p:
            out.append(0.0)
            continue
        hit = next((i for i in range(pos, len(toks) - len(p) + 1) if toks[i:i + len(p)] == p), None)
        if hit is None:
            raise RuntimeError(f"{sid}: picture cue not heard in the voice: {ph!r}")
        out.append(words[hit]["start"])
        pos = hit + 1
    return out


def title_words(title):
    return sum(1 for t in title.split() if any(c.isalnum() for c in t))


def make_voice(st, work):
    """Edge voice of title + story with word timings; cached by text, voice and speed."""
    os.makedirs(work, exist_ok=True)
    vo = os.path.join(work, "voice.mp3")
    text = st["title"] + " " + st["body"]
    key = os.path.join(work, "voice.key")
    sig = json.dumps([text, st["voice"], SPEED])
    if not (os.path.isfile(vo) and os.path.isfile(vo + ".words.json") and os.path.isfile(key)
            and open(key).read() == sig):
        edge_voiceover.synthesize(text, vo, voice=st["voice"], speed=SPEED)
        with open(key, "w") as f:
            f.write(sig)
    words = json.load(open(vo + ".words.json"))
    if not words:
        raise RuntimeError("The voice came back without word timings; click Generate again.")
    return {"path": vo, "words": vo + ".words.json", "duration": edge_voiceover._duration(vo)}


def load_picture(path):
    im = Image.open(path).convert("RGB")
    # cover 1080x1920 with 12% room for the push-in
    k = max(W * 1.12 / im.width, H * 1.12 / im.height)
    return im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)


def picture_frame(im, u, flip):
    """u = 0..1 through the beat: ease from wide to a 10% push-in, drifting up (or down on odd beats)."""
    e = _ease(min(1.0, u))
    cw0 = min(im.width, im.height * W / H)
    z = 1.0 - 0.1 * e
    cw, chh = cw0 * z, cw0 * z * H / W
    cx = (im.width - cw) / 2
    f = (0.6 - 0.3 * e) if flip else (0.3 + 0.3 * e)
    cy = (im.height - chh) * f
    return im.resize((W, H), Image.BILINEAR, box=(cx, cy, cx + cw, cy + chh))


def _blank():
    return Image.new("RGB", (int(W * 1.12), int(H * 1.12)), (40, 44, 52))


def render_spec(spec, out, progress=None, cancel=None, log=print):
    """spec (from reddit_shorts.runner.plan) -> mp4 at out. A picture Flow did not make shows a plain dark frame."""
    say = progress or (lambda f, m="": None)
    st = spec["story"]
    vo = spec["voice"]["path"]
    words = json.load(open(spec["voice"]["words"]))
    dur_vo = spec["voice"]["duration"]
    n_title = title_words(st["title"])
    title_end = words[min(n_title, len(words)) - 1]["end"]
    body = words[n_title:]
    total = dur_vo + 0.7
    nfr = int(total * FPS)

    # captions timeline
    caps = []
    ch = chunks_of(body)
    for ci, c in enumerate(ch):
        for wi, w in enumerate(c):
            t0 = w["start"]
            if wi + 1 < len(c):
                t1 = c[wi + 1]["start"]
            elif ci + 1 < len(ch):
                t1 = ch[ci + 1][0]["start"]
            else:
                t1 = total
            caps.append((t0, t1, ci, [x["word"] for x in c], wi))
    card = make_card(st)
    card_out = title_end + 0.15

    have = (spec.get("assets") or {}).get("pictures") or {}
    keys = [b["key"] for b in spec["beats"]]
    pics = [load_picture(have[k]) if have.get(k) and os.path.isfile(have[k]) else _blank() for k in keys]
    starts = [b["start"] for b in spec["beats"]]
    ends = starts[1:] + [total]

    musics = sorted(f for f in os.listdir(MUSIC_DIR) if f.endswith(".opus"))
    music = os.path.join(MUSIC_DIR, musics[int(spec.get("music_index", 0)) % len(musics)])
    pop = os.path.join(SFX, "ui", "ui_pop_01.opus")
    whoosh = os.path.join(SFX, "whoosh", "whoosh_002.opus")
    out = str(out)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    part = out[:-4] + ".part.mp4" if out.endswith(".mp4") else out + ".part.mp4"
    co_ms = int(card_out * 1000)
    cut_ms = [int(t * 1000) for t in starts[1:] if abs(t - card_out) > 0.4]
    w_in, w_fx, w_lab = [], [], []
    for j, ms in enumerate(cut_ms):
        w_in += ["-i", os.path.join(SFX, "whoosh", f"whoosh_00{1 + j % 4}.opus")]
        w_fx.append(f"[{5 + j}:a]volume=0.22,adelay={ms}|{ms}[c{j}]")
        w_lab.append(f"[c{j}]")
    cuts_fx = (";".join(w_fx) + ";") if w_fx else ""
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-i", vo, "-stream_loop", "-1", "-i", music, "-i", pop, "-i", whoosh, *w_in,
         "-filter_complex",
         cuts_fx + f"[1:a]apad[v];[2:a]volume=0.16,afade=t=out:st={total - 1:.2f}:d=1[m];"
         f"[3:a]volume=0.5[p];[4:a]volume=0.45,adelay={co_ms}|{co_ms}[w];"
         f"[v][m][p][w]{''.join(w_lab)}amix=inputs={4 + len(w_lab)}:duration=first:normalize=0,atrim=0:{total:.2f}[a]",
         "-map", "0:v", "-map", "[a]", "-t", f"{total:.2f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", part], stdin=subprocess.PIPE)

    cache, ci_ptr = {}, 0
    bi = 0
    try:
        for fi in range(nfr):
            if cancel and cancel():
                raise RuntimeError("Stopped.")
            if fi % 30 == 0:
                say(fi / nfr, "drawing the Short")
            t = fi / FPS
            while bi + 1 < len(starts) and starts[bi + 1] <= t:
                bi += 1
            u = (t - starts[bi]) / max(0.5, ends[bi] - starts[bi])
            fr = picture_frame(pics[bi], u, bi % 2 == 1)
            if t < card_out + 0.22:
                if t < card_out:
                    k = _ease(t / 0.3)
                    s, alpha = 0.86 + 0.14 * k, k
                else:
                    k = (t - card_out) / 0.22
                    s, alpha = 1.0 + 0.08 * k, 1 - k
                im = card if abs(s - 1.0) < 1e-3 else card.resize((int(card.width * s), int(card.height * s)), Image.BILINEAR)
                if alpha < 0.999:
                    im = im.copy()
                    im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
                fr.paste(im, ((W - im.width) // 2, (H - im.height) // 2 - 80), im)
            else:
                while ci_ptr + 1 < len(caps) and caps[ci_ptr + 1][0] <= t:
                    ci_ptr += 1
                if caps and caps[ci_ptr][0] <= t < caps[ci_ptr][1]:
                    t0, t1, cidx, ws, act = caps[ci_ptr]
                    k = (cidx, act)
                    if k not in cache:
                        cache.clear()
                        cache[k] = make_caption(ws, act)
                    im = cache[k]
                    age = t - ch[cidx][0]["start"]
                    if age < 0.1:
                        s = 0.8 + 0.2 * _ease(age / 0.1)
                        im = im.resize((int(im.width * s), int(im.height * s)), Image.BILINEAR)
                    fr.paste(im, ((W - im.width) // 2, int(H * 0.58) - im.height // 2), im)
            enc.stdin.write(fr.tobytes())
        enc.stdin.close()
        enc.wait()
    except BaseException:
        enc.kill()
        enc.wait()
        if os.path.exists(part):
            os.remove(part)
        raise
    if enc.returncode != 0:
        raise RuntimeError(f"encode failed for {st['id']}")
    os.replace(part, out)
    say(1.0, "done")
    log(f"reddit shorts: wrote {out} ({total:.1f} s)")
    return {"video": out, "seconds": total}


def main(ids):
    """Batch the built-in stories into $DEST (Ch1 test folder)."""
    from reddit_shorts import runner, story
    order = story.builtin_ids()
    for sid in (order if ids == ["all"] else ids):
        spec = runner.plan(story.builtin(sid), os.path.join(OUT, sid), music_index=order.index(sid))
        mp4 = os.path.join(OUT, f"{sid}.mp4")
        render_spec(spec, mp4)
        os.makedirs(DEST, exist_ok=True)
        safe = "".join(c for c in spec["story"]["title"] if c not in '/:?"\\')[:90].strip()
        dst = os.path.join(DEST, f"Ch1 Reddit {order.index(sid) + 1:02d} - {safe}.mp4")
        shutil.copy(mp4, dst)
        print(f"DONE {sid} -> {dst}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or ["all"])
