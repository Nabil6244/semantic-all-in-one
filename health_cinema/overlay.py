"""Shared label overlay + encode for 3D journey frames (backend-neutral). Labels come from journey.sample(); sizes scale with frame height
(1080p base: label 40 px). Usage: overlay.py FRAMES_JSON FRAME_DIR OUT_MP4 FPS"""
import json, math, subprocess, sys, shutil
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

def draw_labels(im, labels, H, k=1.0):      # k: a spec's label_scale (a clip shown small inside another layout asks for bigger labels); 1.0 for every Health Cinema scene
    W = im.width; px = round(label_px(min(W, H)) * k); f = _font(px); ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
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

CARD_W_1080 = 640      # card width at 1080p (landscape illustration + header + footer); scaled with the frame and, slightly, with the camera distance

_CARD_CACHE: dict = {}

def _card_plate(path, title, tag, foot, w, H):
    """The finished card (RGBA): dark glass plate, hairline cyan border with corner brackets, an 'ILLUSTRATION' chip + title, the picture, a footer line. Cached per card and size."""
    key = (path, title, tag, foot, w, H)
    if key in _CARD_CACHE: return _CARD_CACHE[key]
    k = H / 1080; pad = round(14 * k); head = round(48 * k); footh = round(40 * k); img = Image.open(path).convert("RGB"); iw = w - 2 * pad; ih = round(iw * img.height / img.width)
    img = img.resize((iw, ih), Image.LANCZOS); h = pad + head + ih + footh + pad // 2
    plate = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(plate); r = round(10 * k)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=r, fill=(7, 13, 26, 232), outline=(110, 200, 255, 210), width=max(1, round(1.5 * k)))
    bl = round(22 * k); lw = max(2, round(3 * k)); c = (170, 225, 255, 255)
    for (x, y, dx, dy) in ((0, 0, 1, 1), (w - 1, 0, -1, 1), (0, h - 1, 1, -1), (w - 1, h - 1, -1, -1)):
        d.line([(x, y), (x + dx * bl, y)], fill=c, width=lw); d.line([(x, y), (x, y + dy * bl)], fill=c, width=lw)
    f1, f2 = _font(round(24 * k)), _font(round(21 * k)); tw = d.textlength(tag, font=f1)
    d.rounded_rectangle((pad, pad, pad + tw + 2 * round(10 * k), pad + head - round(6 * k)), radius=round(5 * k), fill=(60, 150, 220, 235))
    d.text((pad + round(10 * k), pad + round(3 * k)), tag, font=f1, fill=(255, 255, 255, 255))
    d.text((pad + tw + 3 * round(10 * k), pad + round(4 * k)), title, font=f1, fill=(235, 244, 255, 255))
    plate.paste(img, (pad, pad + head)); d.rectangle((pad, pad + head, pad + iw, pad + head + ih), outline=(90, 170, 230, 160), width=max(1, round(k)))
    d.text((pad, pad + head + ih + round(7 * k)), foot, font=f2, fill=(170, 190, 215, 255))
    _CARD_CACHE[key] = plate
    if len(_CARD_CACHE) > 12: _CARD_CACHE.pop(next(iter(_CARD_CACHE)))
    return plate

def draw_cards(im, cards, H):
    """Illustration cards pinned to anatomy: a leader line from the pin on the body to the card edge, an entrance (scale, fade, scan from the top), a trace of float. The card sits on its
    side of the frame (`side`), away from the centre where the camera keeps the anatomy, and its size follows the camera distance a little."""
    if not cards: return im
    W = im.width; k = H / 1080; ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    for cd in cards:
        enter = min(1.0, cd["age"] / 0.8); leave = min(1.0, max(0.0, cd["left"] / 0.5)); a = enter * leave
        if a <= 0.01: continue
        ease = enter * enter * (3 - 2 * enter); cw = round(CARD_W_1080 * k * (0.92 + 0.08 * ease) * min(1.12, max(0.9, (0.9 / max(0.3, cd["dist"])) ** 0.12)))
        plate = _card_plate(cd["image"], cd["title"], cd["tag"], cd["foot"], cw, H); ph = plate.height
        m = round(W * 0.035); x0 = W - m - cw if cd["side"] == "right" else m
        px, py = cd["xy"]; cy = min(max(py, H * 0.06 + ph / 2), H * 0.94 - ph / 2) + 5 * k * math.sin(cd["age"] * 1.3); y0 = round(cy - ph / 2)
        reveal = max(0.02, ease); vis = plate.crop((0, 0, cw, max(1, round(ph * reveal)))); vis = vis.copy(); vis.putalpha(vis.getchannel("A").point(lambda v: int(v * a)))
        ex = x0 if cd["side"] == "right" else x0 + cw; ey = y0 + round(54 * k); bend = ex - (50 * k if cd["side"] == "right" else -50 * k)
        la = int(235 * a * min(1.0, cd["age"] / 0.4)); lw = max(2, round(2.5 * k)); pts = [(px, py), (bend, ey), (ex, ey)]
        d.line(pts, fill=(150, 215, 255, la), width=lw, joint="curve"); r0 = max(5, round(7 * k)); d.ellipse([px - r0, py - r0, px + r0, py + r0], outline=(255, 255, 255, la), width=lw)
        d.ellipse([px - r0 / 2, py - r0 / 2, px + r0 / 2, py + r0 / 2], fill=(255, 90, 80, la)); ov.alpha_composite(vis, (x0, y0))
    return Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")

def draw_footer(im, text, H):
    if not text: return im
    d = ImageDraw.Draw(im, "RGBA"); px = max(22, round(30 * H / 1080)); f = _font(px); m = round(im.width * 0.03)
    d.text((m, im.height - m - px), text, font=f, fill=(190, 202, 225, 235)); return im

def run(frames_json, frame_dir, out_mp4, fps, ffmpeg=None):
    data = json.loads(Path(frames_json).read_text()); frames = data["frames"]; footer = (data.get("spec") or {}).get("footer", ""); caps = (data.get("spec") or {}).get("captions", []); lk = float((data.get("spec") or {}).get("label_scale", 1.0)); fd = Path(frame_dir); tmp = fd.parent / (fd.name + "_lbl"); tmp.mkdir(exist_ok=True)
    for fr in frames:
        p = fd / f"f{fr['i']:05d}.png"
        if not p.exists(): continue
        im = Image.open(p); im = draw_footer(draw_cards(draw_labels(im, fr["labels"], im.height, lk), fr.get("cards", []), im.height), footer, im.height)
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
