"""Shared label overlay + encode for 3D journey frames (backend-neutral). Labels come from journey.sample(); sizes scale with frame height
(1080p base: label 40 px). Usage: overlay.py FRAMES_JSON FRAME_DIR OUT_MP4 FPS"""
import json, subprocess, sys, shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

def _font(px):
    for p in ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"):
        if Path(p).exists():
            try: return ImageFont.truetype(p, px, index=1) if p.endswith(".ttc") else ImageFont.truetype(p, px)
            except Exception: pass
    return ImageFont.load_default()

BASE_PX_1080 = 40      # label text height at 1080p (design range 32-44 px)
MIN_PX = 26            # never smaller than this, so 540p labels stay legible

def label_px(H):   # pass the SHORT side of the frame (min(W, H)) so portrait and landscape get the same text size
    """Label text size for an output height: proportional to 1080p (40 px) with a legibility floor."""
    return max(MIN_PX, round(BASE_PX_1080 * H / 1080))

def label_box(text_w, px, x, y, side, W, H):
    """Box (x0, y0, x1, y1) and text origin for a label whose dot is at (x, y); clamped inside a 3% safe margin of the frame."""
    pad = px * 0.4; dx = px * 3.2 * (1 if side == "right" else -1); tx = x + dx; ty = y - px * 1.6
    bw = text_w + 2 * pad; bx0 = tx if dx > 0 else tx - bw
    m = 0.03; bx0 = min(max(bx0, W * m), W * (1 - m) - bw); ty = min(max(ty, H * m + pad * 0.4), H * (1 - m) - px * 1.25 - pad * 0.4)
    return (bx0, ty - pad * 0.4, bx0 + bw, ty + px * 1.25 + pad * 0.4), (bx0 + pad, ty)

def draw_labels(im, labels, H):
    W = im.width; px = label_px(min(W, H)); f = _font(px); ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    for lb in labels:
        a = int(255 * lb["a"]); x, y = lb["xy"]; w = d.textlength(lb["text"], font=f)
        box, org = label_box(w, px, x, y, lb["side"], W, H); ex = box[0] if lb["side"] == "right" else box[2]
        d.line([(x, y), (ex, (box[1] + box[3]) / 2)], fill=(255, 255, 255, a), width=max(2, round(px / 14)))
        r = max(4, round(px / 6)); d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, a))
        import math; ph = (lb.get("t", 0.0) * 1.25) % 1.0; rr = r * (2.2 + 2.2 * ph); ra = int(a * (1 - ph) * 0.9)
        d.ellipse([x - rr, y - rr, x + rr, y + rr], outline=(255, 80, 80, ra), width=max(2, round(px / 14)))
        d.rounded_rectangle(box, radius=px * 0.25, fill=(8, 14, 28, int(a * 0.86)), outline=(120, 200, 255, a), width=max(1, round(px / 20)))
        d.text(org, lb["text"], font=f, fill=(255, 255, 255, a))
    return Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")

def draw_footer(im, text, H):
    if not text: return im
    d = ImageDraw.Draw(im, "RGBA"); px = max(22, round(30 * H / 1080)); f = _font(px); m = round(im.width * 0.03)
    d.text((m, im.height - m - px), text, font=f, fill=(190, 202, 225, 235)); return im

def run(frames_json, frame_dir, out_mp4, fps, ffmpeg=None):
    data = json.loads(Path(frames_json).read_text()); frames = data["frames"]; footer = (data.get("spec") or {}).get("footer", ""); caps = (data.get("spec") or {}).get("captions", []); fd = Path(frame_dir); tmp = fd.parent / (fd.name + "_lbl"); tmp.mkdir(exist_ok=True)
    for fr in frames:
        p = fd / f"f{fr['i']:05d}.png"
        if not p.exists(): continue
        im = Image.open(p); im = draw_footer(draw_labels(im, fr["labels"], im.height), footer, im.height)
        for a, b, text in caps:
            if a <= fr["t"] < b:
                from .graphics import draw_caption
                im = draw_caption(im, text, im.height, alpha=min(1.0, (fr["t"] - a) / 0.15, (b - fr["t"]) / 0.15)); break
        im.save(tmp / p.name)
    ff = ffmpeg or shutil.which("ffmpeg")
    subprocess.run([ff, "-y", "-v", "error", "-framerate", str(fps), "-i", str(tmp / "f%05d.png"), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_mp4)], check=True, timeout=3600)
    shutil.rmtree(tmp, ignore_errors=True)   # the labelled PNGs are only an intermediate

if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]))
