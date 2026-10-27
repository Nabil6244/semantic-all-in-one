"""ONE-TIME asset builder for the film texture layer. Run by hand, never during a render:

    python3 -B explainer/motion/build_texture.py            # writes explainer/assets/texture/ (grain tile, vignette mask, three dust sprites + manifest.json)
    python3 -B explainer/motion/build_texture.py --check    # rebuilds in memory, compares bytes with the files on disk, writes nothing

grain_tile.png   512x512 'L', seamless (drawn on a torus), mean 128, std about 28; the renderer scales it to about 3 levels of 255.
vignette.png     480x270 'L', 0 in the middle, 255 at the corners (smooth); the renderer resizes it once per frame size.
dust_{s,m,l}.png soft round sprites ('L' alpha) 12, 20 and 32 px.
Everything is drawn with numpy from fixed seeds (np.random.RandomState); the same numpy and Pillow give the same bytes. No outside art."""

from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Dict

import numpy as np
import PIL
from PIL import Image

OUT = Path(__file__).resolve().parents[1] / "assets" / "texture"
ASSET_ID = "film_texture_v1"
GRAIN = 512
VIG = (480, 270)
DUST = {"s": 12, "m": 20, "l": 32}


def grain_tile() -> Image.Image:
    rs = np.random.RandomState(9101)
    n = rs.normal(0.0, 1.0, (GRAIN, GRAIN)).astype(np.float32)
    # a little spatial correlation (wrap-around blur) so it reads as grain, not TV static; the roll keeps the tile seamless
    b = (n + 0.6 * (np.roll(n, 1, 0) + np.roll(n, -1, 0) + np.roll(n, 1, 1) + np.roll(n, -1, 1)) * 0.5) / np.sqrt(1 + 0.36 * 2 * 0.5)
    b = b / b.std()
    return Image.fromarray(np.clip(128 + 28 * b + 0.5, 0, 255).astype(np.uint8), "L")


def vignette_mask() -> Image.Image:
    w, h = VIG
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((x - w / 2) / (w / 2)) ** 2 + ((y - h / 2) / (h / 2)) ** 2) / 1.4142
    v = np.clip((d - 0.35) / 0.65, 0, 1) ** 2.0
    return Image.fromarray(np.clip(v * 255 + 0.5, 0, 255).astype(np.uint8), "L")


def dust_sprite(px: int) -> Image.Image:
    y, x = np.mgrid[0:px, 0:px].astype(np.float32)
    r = np.sqrt((x - (px - 1) / 2) ** 2 + (y - (px - 1) / 2) ** 2) / (px / 2)
    a = np.clip(1.0 - r, 0, 1) ** 1.6
    return Image.fromarray(np.clip(a * 255 + 0.5, 0, 255).astype(np.uint8), "L")


def png_bytes(im: Image.Image) -> bytes:
    b = io.BytesIO()
    im.save(b, "PNG", optimize=False, compress_level=9)
    return b.getvalue()


def build() -> Dict[str, bytes]:
    files: Dict[str, bytes] = {"grain_tile.png": png_bytes(grain_tile()), "vignette.png": png_bytes(vignette_mask())}
    for k, px in DUST.items():
        files[f"dust_{k}.png"] = png_bytes(dust_sprite(px))
    meta = {n: {"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)} for n, b in sorted(files.items())}
    manifest = {"asset_id": ASSET_ID, "version": 1, "pillow_version": PIL.__version__, "numpy_version": np.__version__, "built_by": "explainer/motion/build_texture.py", "files": meta}
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
