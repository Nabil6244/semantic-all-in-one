"""Steps 3-6 of the brief for '10 Secret GTA 6 Chapter 2 Tricks' (after align.py has put cut_in/cut_out into manifest.json).

  3. each beat's footage comes from that beat's own links (raw slices in footage/library/raw/yt_ch2 + yt_endings),
     cut into short segments that fill the beat exactly
  4. every segment is scaled to 1920x1080 @ 30 fps with its audio removed; vertical uploads sit over a blurred copy
  5. each beat's overlay_graphics show as yellow-on-dark pills top-left for the beat's first 5.5 s, and two-line white
     captions from the Whisper words run bottom-centre (drawn with PIL into one transparent overlay track)
  6. voice (0 dB) + the Game Launch music bed (-24 dB) are muxed with +faststart; ffprobe checks video vs audio length

Run:  python3 assemble.py [voice.mp3]     (default manual_vo_mastered.mp3; run align.py with the same voice first)"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from game_launch import look as L  # noqa: E402

VO = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "manual_vo_mastered.mp3"
RAW = HERE.parent / "footage/library/raw/yt_ch2"
RAW1 = HERE.parent / "footage/library/raw/yt_endings"
WORK = HERE / "work"
OUT = HERE.parent / "out/gta6_chapter2_10_tricks_final.mp4"
W, H, FPS = 1920, 1080, 30
SEG = 5.5                    # seconds per footage segment

# Footage = each beat's exact source_clips from manifest.json (downloaded by fetch_ranges.py as <id>_<start>_<end>.mp4).
# Every range gets a share of the beat in proportion to its length, plays from its start, and repeats only if its share is
# longer than the range itself, so every range the manifest lists is on screen and nothing outside the ranges is used.
from fetch_ranges import name as range_name, secs  # noqa: E402


def src(name):
    for p in (RAW / f"{name}.mp4", RAW1 / f"{name}.mp4"):
        if p.is_file():
            return p
    raise FileNotFoundError(name)


def probe(p, what):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", what, "-of", "csv=p=0", str(p)],
                         capture_output=True, text=True).stdout.strip().strip(",")
    return out


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True).stdout)


def segment(name, at, length, out):
    """One normalized piece: 1920x1080 30 fps, no audio; a vertical source sits over a blurred copy of itself."""
    p = src(name)
    w, h = (int(x) for x in probe(p, "stream=width,height").split(",")[:2])
    total = dur(p)
    at = max(0.0, min(at, total - length - 0.1))
    if h > w:
        vf = (f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:2,eq=brightness=-0.12[bg];"
              f"[b]scale=-2:{H}[fg];[bg][fg]overlay=(W-w)/2:0,fps={FPS},setsar=1")
    else:
        vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.2f}", "-t", f"{length:.3f}", "-i", str(p), "-filter_complex", vf,
                    "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)],
                   check=True)


def footage(beats):
    WORK.mkdir(parents=True, exist_ok=True)
    parts = []
    for b in beats:
        need = b["cut_out_sec"] - b["cut_in_sec"]
        clips = [(range_name(c), secs(c["end"]) - secs(c["start"])) for c in b["source_clips"]]
        total = sum(n for _f, n in clips)
        made, k = 0.0, 0
        for i, (f_, n) in enumerate(clips):
            share = need - made if i == len(clips) - 1 else need * n / total
            got, pos = 0.0, 0.0
            while share - got > 0.05:
                length = min(SEG, share - got, n - pos)
                if length < 0.5:                          # end of the range: start it again
                    pos = 0.0
                    continue
                f = WORK / f"{b['beat_id']}_{k:02d}.mp4"
                if not f.is_file():
                    segment(f_, pos, length, f)
                parts.append(f)
                real = round(length * FPS) / FPS
                got, pos, k = got + real, pos + real, k + 1
            made += got
    lst = WORK / "concat.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    silent = WORK / "video.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent)], check=True)
    return silent


# ------------------------------------------------------------------------------------------------ overlays (PIL)

YELLOW, PILL = (255, 214, 10, 255), (10, 10, 15, 209)


def pill_layer(img, lines):
    d = ImageDraw.Draw(img)
    f1, f2 = L.font(L.F_HEAD, 50), L.font(L.F_HEAD, 36)
    y = 48
    for i, t in enumerate(lines):
        f = f1 if i == 0 else f2
        x0, y0, x1, y1 = d.textbbox((0, 0), t, font=f)
        w_, h_ = x1 - x0, y1 - y0
        d.rounded_rectangle((48, y, 48 + w_ + 56, y + h_ + 36), radius=(h_ + 36) // 2, fill=PILL)
        d.text((48 + 28 - x0, y + 18 - y0), t, font=f, fill=YELLOW)
        y += h_ + 36 + 14


def caption_layer(img, text):
    d = ImageDraw.Draw(img)
    f = L.font(L.F_HEAD, 54)
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        if d.textlength((cur + " " + w_).strip(), font=f) > 1500 and cur:
            lines.append(cur)
            cur = w_
        else:
            cur = (cur + " " + w_).strip()
    lines.append(cur)
    y = H - 70 - 66 * len(lines)
    wmax = max(d.textlength(t, font=f) for t in lines)
    top = min(y - 22, 880)                       # the band also hides the creators' own burnt-in subtitles
    d.rounded_rectangle(((W - wmax) / 2 - 40, top, (W + wmax) / 2 + 40, H - 40), radius=22, fill=(8, 8, 12, 190))
    for t in lines:
        tw = d.textlength(t, font=f)
        x = (W - tw) / 2
        for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2), (-2, 2), (2, -2)):
            d.text((x + dx, y + dy), t, font=f, fill=(0, 0, 0, 230))
        d.text((x, y), t, font=f, fill=(255, 255, 255, 255))
        y += 66


def chunks(words):
    """Caption chunks: up to ~9 words / 2 lines, broken at sentence ends and pauses."""
    out, cur = [], []
    for w_ in words:
        if cur and (len(cur) >= 9 or w_["s"] - cur[-1]["e"] > 0.5):
            out.append(cur)
            cur = []
        cur.append(w_)
        if w_["w"].rstrip().endswith((".", "?", "!")):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return [(c[0]["s"], c[-1]["e"], " ".join(x["w"].strip() for x in c)) for c in out]


def overlay_track(beats, words, total):
    """One transparent mov: the pills and captions laid out as a list of still states with durations."""
    caps = chunks(words)
    marks = {0.0, total}
    pills = [(b["cut_in_sec"], min(b["cut_in_sec"] + 5.5, b["cut_out_sec"]), b["overlay_graphics"]) for b in beats]
    for a, b_, _ in pills + [(s, e, None) for s, e, _t in caps]:
        marks.update((round(a, 2), round(b_, 2)))
    marks = sorted(m for m in marks if 0 <= m <= total)
    odir = WORK / "ov"
    odir.mkdir(exist_ok=True)
    cache, entries = {}, []
    for a, b_ in zip(marks, marks[1:]):
        if b_ - a < 0.01:
            continue
        t = (a + b_) / 2
        pl = next((p for s, e, p in pills if s <= t < e), None)
        cp = next((c for s, e, c in caps if s <= t < e + 0.25), None)
        key = (tuple(pl) if pl else None, cp)
        if key not in cache:
            img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            if pl:
                pill_layer(img, pl)
            if cp:
                caption_layer(img, cp)
            f = odir / f"o{len(cache):04d}.png"
            img.save(f)
            cache[key] = f
        entries.append((cache[key], b_ - a))
    lst = WORK / "ov.txt"
    lst.write_text("".join(f"file '{f}'\nduration {d:.3f}\n" for f, d in entries) + f"file '{entries[-1][0]}'\n")
    mov = WORK / "overlay.mov"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-vf", f"fps={FPS},format=argb",
                    "-c:v", "qtrle", "-t", f"{total:.3f}", str(mov)], check=True)
    return mov


if __name__ == "__main__":
    m = json.loads((HERE / "manifest.json").read_text())
    beats, words = m["beats"], json.loads((HERE / "words.json").read_text())
    total = dur(VO)
    print("footage...", flush=True)
    silent = footage(beats)
    print("overlays...", flush=True)
    ov = overlay_track(beats, words, total)
    print("music + mix...", flush=True)
    mus = WORK / "music.wav"
    L.music(total, mus, cache=WORK / "cache")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(ov), "-i", str(VO), "-i", str(mus), "-filter_complex",
                    f"[0:v][1:v]overlay=0:0:shortest=0[v];[3:a]volume=-24dB[m];[2:a][m]amix=inputs=2:duration=first:normalize=0[a]",
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", "-movflags", "+faststart", str(OUT)], check=True)
    v = float(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration", "-of",
                              "csv=p=0", str(OUT)], capture_output=True, text=True).stdout.strip().strip(","))
    a = float(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=duration", "-of",
                              "csv=p=0", str(OUT)], capture_output=True, text=True).stdout.strip().strip(","))
    print(f"DONE {OUT}  video {v:.2f}s  audio {a:.2f}s  diff {abs(v - a):.2f}s  {'OK' if abs(v - a) <= 0.2 else 'MISMATCH'}")
