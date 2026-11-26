"""Turns the Vice Ranked endings source links (downloaded into footage/library/raw/endings_src) into 16:9 clips
the ranked-endings CSV can name in game_clip: X post screenshots on a moving blurred backdrop, Shorts pillarboxed
on their own blur, and the ending-footage clip as is. Each clip is hard-linked into footage/trailer.
Run:  python3 gta6_launch/make_endings_sources.py"""
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "footage/library/raw/endings_src"
LIB, TRAILER = ROOT / "footage/library", ROOT / "footage/trailer"
ENC = ["-c:v", "h264_videotoolbox", "-b:v", "8M", "-pix_fmt", "yuv420p", "-r", "30"]
ENDING = RAW / "19HTPoQVd2w_204_535.mp4"                     # 2:04-5:35 of the source; ~60-80 s are X-post frames
POSTS = {  # tweet id -> (clip name, backdrop second in ENDING)
    "2123961510494130498": ("gta6_src_x_moviefans_endings", 10),
    "2123909681144021158": ("gta6_src_x_kruqia_five_endings", 30),
    "2123863591048876457": ("gta6_src_x_siddhiman_more_than_two", 50),
    "2124012260632789167": ("gta6_src_x_sultan_2m_savings", 120),
    "2110350398976368750": ("gta6_src_x_cyberleek_has_ending", 150),
    "2110355784542364031": ("gta6_src_x_ign_cyberleek", 170),
    "2123562180335505734": ("gta6_src_x_omxr_story_plus", 190),
}
SHORTS = {"6w5ItpDl6CE.mp4": "gta6_src_short_all_endings", "rgOc2-gbZYg.mp4": "gta6_src_short_bridge"}
POST_SEC = 8.0


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr[-1500:])


def card(png: Path) -> Path:
    """Crop the dark embed card off the white page below it."""
    im = Image.open(png).convert("RGB")
    w, h = im.size
    bottom = h
    for y in range(h - 1, 0, -1):
        if sum(im.getpixel((w // 2, y))) < 300 or sum(im.getpixel((20, y))) < 300:
            bottom = y + 1
            break
    out = png.with_name(png.stem + "_card.png")
    im.crop((0, 0, w, bottom)).save(out)
    return out


def link(out: Path):
    t = TRAILER / out.name
    if t.exists():
        t.unlink()
    os.link(out, t)


def post_clip(tid: str, name: str, bg_at: float):
    c = card(RAW / f"x_{tid}.png")
    cw, ch = Image.open(c).size
    s = min(1000 / cw, 940 / ch)
    w0 = int(cw * s) // 2 * 2
    out = LIB / f"{name}.mp4"
    fc = (f"[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,boxblur=30:2,eq=brightness=-0.25[bg];"
          f"[1:v]scale=w='trunc({w0}*(1+0.05*t/{POST_SEC})/2)*2':h=-2:eval=frame[fg];"
          f"[bg][fg]overlay=x=(W-w)/2:y=(H-h)/2:eval=frame,setsar=1[v]")
    run(["ffmpeg", "-v", "error", "-y", "-ss", str(bg_at), "-t", str(POST_SEC), "-i", str(ENDING),
         "-loop", "1", "-t", str(POST_SEC), "-i", str(c), "-filter_complex", fc, "-map", "[v]", "-an", *ENC, str(out)])
    link(out)
    print("post", out.name)


def short_clip(src: str, name: str):
    out = LIB / f"{name}.mp4"
    fc = ("[0:v]split[a][b];[a]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,boxblur=30:2,"
          "eq=brightness=-0.25[bg];[b]scale=-2:1080[fg];[bg][fg]overlay=x=(W-w)/2:y=0,setsar=1[v]")
    run(["ffmpeg", "-v", "error", "-y", "-i", str(RAW / src), "-filter_complex", fc, "-map", "[v]", "-an", *ENC, str(out)])
    link(out)
    print("short", out.name)


if __name__ == "__main__":
    for tid, (name, at) in POSTS.items():
        post_clip(tid, name, at)
    for src, name in SHORTS.items():
        short_clip(src, name)
    out = LIB / "gta6_src_ending_footage.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(ENDING), "-vf", "scale=1920:1080,setsar=1", "-an", *ENC, str(out)])
    link(out)
    print("ending", out.name)
