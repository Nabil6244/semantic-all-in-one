"""Join finished episodes into one long video for parents (30-60+ minutes): chapters, a collage thumbnail, UPLOAD.md.

python3 cartoon2d/compile.py "Learn Colours, Numbers, Shapes & Animals" ep02 ep03 ep04
-> cartoon2d/episodes/Compilation - <title>/ (video, thumbnail.jpg, UPLOAD.md)
Episodes are taken from their packaged folders (package.py) and joined without re-encoding (same size / fps / codecs);
if the join fails a re-encode is used.
"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import package  # noqa: E402

OUT = ROOT / "cartoon2d" / "episodes"
FONT = "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf"


def _dur(f):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)]))


def _mmss(t):
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def _secs(s):
    p = [int(x) for x in s.split(":")]
    return p[0] * 60 + p[1] if len(p) == 2 else p[0] * 3600 + p[1] * 60 + p[2]


def thumb(eps, minutes, dest):
    W, H = 1280, 720
    im = Image.new("RGB", (W, H), (255, 214, 90))
    tiles = [Image.open(OUT / package.META[e]["folder"] / "thumbnail_1.jpg").convert("RGB") for e in eps[:4]]
    n = len(tiles)
    if n == 3:                                          # one big on the left, two stacked on the right: no empty corner
        big = tiles[0].resize((int(W * 0.5 * 720 / 640 * 1.0) * 2, H), Image.LANCZOS)
        cx = (big.width - W // 2) // 2
        im.paste(big.crop((cx, 0, cx + W // 2, H)), (0, 0))
        for i, t in enumerate(tiles[1:]):
            im.paste(t.resize((W // 2, H // 2), Image.LANCZOS), (W // 2, i * H // 2))
    else:
        cols = 2 if n >= 3 else n
        rows = (n + cols - 1) // cols
        tw, th = W // cols, H // rows
        for i, t in enumerate(tiles):
            im.paste(t.resize((tw, th), Image.LANCZOS), ((i % cols) * tw, (i // cols) * th))
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, 110)
    text = f"{minutes} MIN" if minutes < 60 else f"{minutes // 60} HOUR" + ("S" if minutes >= 120 else "") + ("+" if minutes % 60 > 5 else "")
    w = f.getlength(text) + 80
    d.rounded_rectangle([W / 2 - w / 2, H / 2 - 85, W / 2 + w / 2, H / 2 + 85], radius=60, fill=(255, 255, 255), outline=(230, 60, 60), width=10)
    d.text((W / 2, H / 2 + 4), text, font=f, fill=(230, 60, 60), anchor="mm", stroke_width=6, stroke_fill=(255, 255, 255))
    im.save(dest, quality=92)


def main():
    if sys.argv[1] == "--thumb":                        # remake only the thumbnail of an existing compilation
        title, eps = sys.argv[2], sys.argv[3:]
        dest = OUT / f"Compilation - {title}"
        thumb(eps, int(round(_dur(dest / f"{title}.mp4") / 60)), dest / "thumbnail.jpg")
        return
    title, eps = sys.argv[1], sys.argv[2:]
    dest = OUT / f"Compilation - {title}"
    dest.mkdir(parents=True, exist_ok=True)
    vids = [OUT / package.META[e]["folder"] / f"{package.META[e]['folder']}.mp4" for e in eps]
    lst = dest / "list.txt"
    lst.write_text("".join(f"file '{v}'\n" for v in vids))
    out = dest / f"{title}.mp4"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", "-movflags", "+faststart", str(out)])
    total = sum(_dur(v) for v in vids)
    if r.returncode != 0 or abs(_dur(out) - total) > 3:
        print("plain join failed, re-encoding", flush=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c:v", "libx264", "-preset", "fast",
                        "-tune", "animation", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", str(out)], check=True)
    lst.unlink()
    chapters, off = [], 0.0
    for e, v in zip(eps, vids):
        m = package.META[e]
        name = m["folder"].split(" - ", 1)[1]
        st = json.loads((ROOT / "cartoon2d" / "scenes" / f"{e}_render.json").read_text())
        chap = (ROOT / st["build"] / "chapters.txt").read_text().strip().splitlines()
        chapters.append(f"{_mmss(off)} {name}")
        for c in chap[1:]:                              # each episode's own chapters, minus its "0:00" line
            tc, label = c.split(" ", 1)
            chapters.append(f"{_mmss(off + _secs(tc))} {name}: {label}")
        off += _dur(v)
    minutes = int(round(total / 60))
    thumb(eps, minutes, dest / "thumbnail.jpg")
    names = [package.META[e]["folder"].split(" - ", 1)[1].replace(" with Ms Molly and Bobo", "") for e in eps]
    tags = ", ".join(sorted({t for e in eps for t in package.META[e]["tags"][:4]} | set(package.COMMON_TAGS) |
                            {"compilation for toddlers", "1 hour toddler learning", "long videos for kids"}))
    desc = "\n".join([f"{minutes} minutes of learning and fun with Ms Molly, Lily, Ollie and Bobo the Bear! 🐻",
                      f"Episodes in this video: {', '.join(names)}.", "",
                      "Perfect for car rides, quiet time and long play. Sing, dance and learn along!", "", "Chapters:", *chapters, "",
                      "Parent tip: after watching, play a quick game: ask your child to find one thing from the video at home.",
                      "", "#ToddlerLearning #KidsSongs #MsMolly"])
    (dest / "UPLOAD.md").write_text(f"# Compilation - {title}\n\nLength: {_mmss(total)}\n\n## Title\n\n{title} | {minutes} Min of Toddler "
                                    f"Learning with Ms Molly & Bobo\n\n## Description\n\n```\n{desc}\n```\n\n## Tags\n\n```\n{tags}\n```\n\n"
                                    "## Settings\n\nMade for Kids = Yes · Category: Education\n")
    print("COMPILED", out, _mmss(total))


if __name__ == "__main__":
    main()
