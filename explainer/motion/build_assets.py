"""ONE-TIME asset builder for the stamp texture. Run by hand, never during a render:

    python3 -B explainer/motion/build_assets.py            # writes explainer/assets/stamps/ (two grunge masks + manifest.json)
    python3 -B explainer/motion/build_assets.py --check    # rebuilds in memory, compares bytes with the files on disk, writes nothing

A mask is a grey image: 255 keeps the stamp's ink, lower values wear it away (specks, scratches, a soft blotch). The masks are drawn from a fixed seed with Pillow, so the same Pillow gives the
same bytes. No outside art is used."""

from __future__ import annotations

import hashlib
import io
import json
import random
import sys
from pathlib import Path
from typing import Dict

import PIL
from PIL import Image, ImageChops, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parents[1] / "assets" / "stamps"
ASSET_ID = "stamp_texture_v1"
SIZE = (1024, 512)
VARIANTS = {"a": 7001, "b": 7002}


def draw_mask(seed: int) -> Image.Image:
    rnd = random.Random(seed)
    m = Image.new("L", SIZE, 255)
    d = ImageDraw.Draw(m)
    for _ in range(1500):                                   # fine specks
        x, y, r = rnd.randrange(SIZE[0]), rnd.randrange(SIZE[1]), rnd.choice((1, 1, 1, 2, 2, 3))
        d.ellipse([x - r, y - r, x + r, y + r], fill=rnd.choice((0, 30, 70)))
    for _ in range(14):                                     # scratches
        x, y = rnd.randrange(SIZE[0]), rnd.randrange(SIZE[1])
        dx, dy = rnd.randint(-140, 140), rnd.randint(-30, 30)
        d.line([x, y, x + dx, y + dy], fill=rnd.choice((20, 60)), width=rnd.choice((1, 2)))
    blot = Image.new("L", SIZE, 0)
    bd = ImageDraw.Draw(blot)
    for _ in range(9):                                      # soft worn patches
        x, y, r = rnd.randrange(SIZE[0]), rnd.randrange(SIZE[1]), rnd.randint(30, 80)
        bd.ellipse([x - r, y - r, x + r, y + r], fill=rnd.randint(40, 90))
    blot = blot.filter(ImageFilter.GaussianBlur(26))
    m = ImageChops.subtract(m, blot)
    return m.filter(ImageFilter.GaussianBlur(0.7))


def png_bytes(im: Image.Image) -> bytes:
    b = io.BytesIO()
    im.save(b, "PNG", optimize=False, compress_level=9)
    return b.getvalue()


def build() -> Dict[str, bytes]:
    files: Dict[str, bytes] = {}
    meta = {}
    for name, seed in VARIANTS.items():
        b = png_bytes(draw_mask(seed))
        fn = f"grunge_{name}.png"
        files[fn] = b
        meta[name] = {"file": fn, "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b), "size": list(SIZE), "seed": seed}
    manifest = {"asset_id": ASSET_ID, "version": 1, "pillow_version": PIL.__version__, "built_by": "explainer/motion/build_assets.py", "masks": meta}
    files["manifest.json"] = (json.dumps(manifest, indent=1, sort_keys=True) + "\n").encode()
    return files


def main(argv) -> int:
    files = build()
    if "--check" in argv:
        bad = [n for n, b in files.items() if not (OUT / n).is_file() or (OUT / n).read_bytes() != b]
        extra = sorted(p.name for p in OUT.glob("*") if p.name not in files) if OUT.exists() else []
        print(json.dumps({"files": len(files), "differ_or_missing": bad, "extra_on_disk": extra}, indent=1))
        return 0 if not bad and not extra else 1
    OUT.mkdir(parents=True, exist_ok=True)
    for n, b in files.items():
        (OUT / n).write_bytes(b)
    print(f"wrote {len(files)} files to {OUT}; manifest sha256 {hashlib.sha256(files['manifest.json']).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
