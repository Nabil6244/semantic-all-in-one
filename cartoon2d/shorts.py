"""Cut vertical Shorts (1080x1920, 25-55 s) from a finished episode: songs, games and funny Bobo moments.

python3 cartoon2d/shorts.py ep05 [n]   -> cartoon2d/episodes/<episode folder>/Shorts/short_1.mp4 ... + SHORTS.md
Layout: the episode frame fills the width in the middle over a soft blurred copy of itself, a title banner at the top and
"Full episode on our channel!" at the bottom (the whole picture stays visible, nobody is cropped out).
"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import hook  # noqa: E402
import package  # noqa: E402
import storycheck  # noqa: E402

from fonts import FONT  # noqa: E402  (Arial Rounded on the Mac, a shipped font elsewhere)
MIN_LEN, MAX_LEN = 25.0, 55.0
FUNNY = {"silly", "tumble", "sneeze", "wobble", "spin"}


def score(lines):
    s = 0.0
    for ln in lines:
        s += len(storycheck.events(ln))
        s += 3 if ln.get("chant") else 0
        s += 3 if ln.get("game") else 0
        s += 2 if ln.get("act") in FUNNY else 0
        s += 2 if ln.get("found") else 0
    return s


def candidates(tl):
    lines, total = tl["lines"], tl["total"]
    out = []
    for i, ln in enumerate(lines):
        if not (ln.get("chant") or ln.get("game") or ln.get("act") in FUNNY or ln.get("find") or ln.get("chapter")):
            continue
        t0 = max(0.0, ln["start"] - 0.4)
        if t0 < 30 or t0 > total - 70:
            continue
        seg = []
        for l2 in lines[i:]:
            if l2["end"] - t0 > MAX_LEN:
                break
            seg.append(l2)
        while seg and seg[-1]["end"] - t0 > MIN_LEN and (seg[-1].get("chant") is None and len(seg) > 1 and seg[-1]["text"].endswith("?")):
            seg.pop()                                    # never end on a question
        if not seg or seg[-1]["end"] - t0 < MIN_LEN:
            continue
        chap = next((l.get("chapter") for l in reversed(lines[: i + 1]) if l.get("chapter")), "")
        out.append((score(seg) / (seg[-1]["end"] - t0) * 30, t0, seg[-1]["end"] + 0.6, chap))
    return sorted(out, reverse=True)


def banner(title):
    im = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, 78)
    words, rows, cur = title.split(), [], ""
    for w in words:                                      # wrap to the banner width
        if f.getlength((cur + " " + w).strip()) > 900:
            rows.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    rows.append(cur)
    h = 110 * len(rows) + 70
    d.rounded_rectangle([50, 230, 1030, 230 + h], radius=50, fill=(255, 255, 255, 240), outline=(255, 190, 60, 255), width=8)
    cols = [(230, 70, 70), (60, 140, 240), (60, 170, 90)]
    for i, r in enumerate(rows):
        d.text((540, 230 + 70 + 110 * i), r, font=f, fill=cols[i % 3] + (255,), anchor="mm", stroke_width=5, stroke_fill=(255, 255, 255, 255))
    f2 = ImageFont.truetype(FONT, 56)
    d.rounded_rectangle([110, 1500, 970, 1610], radius=50, fill=(230, 60, 60, 240))
    d.text((540, 1556), "Full episode on our channel!", font=f2, fill=(255, 255, 255, 255), anchor="mm")
    return im


def main():
    ep = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    st = json.loads((ROOT / "cartoon2d" / "scenes" / f"{ep}_render.json").read_text())
    tl = json.loads((ROOT / st["timeline"]).read_text())
    m = package.META[ep]
    video = ROOT / st["build"] / f"{st['name']}.mp4"
    shift = hook.length(hook.windows(st, tl))            # 0 unless the story opted in to the "Coming up!" teaser
    dest = ROOT / "cartoon2d" / "episodes" / m["folder"] / "Shorts"
    dest.mkdir(parents=True, exist_ok=True)
    picked = []
    for sc, t0, t1, chap in candidates(tl):
        if any(not (t1 < a or t0 > b) for _, a, b, _ in picked):
            continue
        picked.append((sc, t0, t1, chap))
        if len(picked) >= n:
            break
    picked.sort(key=lambda p: p[1])
    md = [f"# Shorts from {m['folder']}\n", "Upload each as a YouTube Short; link the full episode (related video).\n"]
    for i, (_, t0, t1, chap) in enumerate(picked, 1):
        title = f"{chap} with Bobo!" if chap else m["word"]
        png = dest / f"banner_{i}.png"
        banner(title).save(png)
        out = dest / f"short_{i}.mp4"
        fc = ("[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=28,eq=brightness=-0.04[bg];"
              "[b]scale=1080:-2[fg];[bg][fg]overlay=0:(H-h)/2[v1];[v1][1:v]overlay=0:0,format=yuv420p[v]")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0 + shift:.2f}", "-t", f"{t1 - t0:.2f}", "-i", str(video), "-i", str(png),
                        "-filter_complex", fc, "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "medium", "-tune", "animation",
                        "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-af", f"afade=t=out:st={max(0, t1 - t0 - 0.6):.2f}:d=0.6",
                        str(out)], check=True)
        png.unlink()
        md.append(f"## short_{i}.mp4 ({t1 - t0:.0f} s, from {int(t0 // 60)}:{int(t0 % 60):02d})\n\nTitle: {title} 🐻 #shorts #toddlerlearning\n\n"
                  f"Description: {m['intro'].split('!')[0]}! Watch the full episode on our channel. #shorts #kidssongs #learning\n")
        print("SHORT", out, f"{t1 - t0:.0f}s", chap)
    (dest / "SHORTS.md").write_text("\n".join(md))


if __name__ == "__main__":
    main()
