"""Film texture for board clips: light grain, a soft vignette and a few drifting dust or snow specks. Opt-in; off never touches a frame.

    layer, note = get_layer(size)          # loaded once per size; layer is None (and note says why) when an asset is missing or does not match its manifest
    im = apply(im, layer, frame_no, fps, "dust")

Deterministic per frame index with no RNG state: the grain window of the (pre-tiled) grain tile is picked by an integer hash of the frame index, and every speck's position is a closed-form
function of (speck number, time). Same frame number -> same pixels.
Never-stop: a missing or altered asset gives the plain frame and a one-line note (the caller records it); nothing is ever written here (assets are built by build_texture.py)."""

from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageChops

DIR = Path(__file__).resolve().parents[1] / "assets" / "texture"
GRAIN_SIGMA = 3.0          # grain strength in levels of 255 (std)
VIGNETTE_MAX = 24          # darkest the corners get, in levels
N_SPECKS = 22
MODES = ("clean", "dust", "snow")
_NEEDED = ("grain_tile.png", "vignette.png", "dust_s.png", "dust_m.png", "dust_l.png")


def normalize(texture) -> str:
    """False/None/'off' -> '' (off); True/'on'/'dust' -> 'dust'; 'snow'; 'clean' (grain + vignette only)."""
    if texture in (None, False, "", "off", "none"):
        return ""
    if texture in (True, "on", "dust"):
        return "dust"
    if texture in MODES:
        return str(texture)
    return "dust"


def manifest_digest() -> str:
    """Short digest of the asset manifest for the cache key ('' if there is none): an edited texture must not reuse an old clip."""
    try:
        return hashlib.sha256((DIR / "manifest.json").read_bytes()).hexdigest()[:16]
    except OSError:
        return "missing"


def _mix(x: int) -> int:                       # 32-bit integer hash (lowbias32), pure
    x &= 0xFFFFFFFF
    x ^= x >> 16
    x = (x * 0x7FEB352D) & 0xFFFFFFFF
    x ^= x >> 15
    x = (x * 0x846CA68B) & 0xFFFFFFFF
    x ^= x >> 16
    return x


class Layer:
    """`overlays`: K full-frame RGB images that bake the vignette and one window of the grain tile each (128 = no change); a frame adds one of them (a single saturating C pass)."""

    def __init__(self, size: Tuple[int, int], overlays: List[Image.Image], sprites: Dict[str, Image.Image]):
        self.size, self.overlays, self.sprites = size, overlays, sprites
        self.specks = self._specks(size)
        self.masks: Dict[Tuple[str, int], Image.Image] = {}

    @staticmethod
    def _specks(size):
        W, H = size
        out = []
        for k in range(N_SPECKS):
            h = [_mix(k * 7919 + j * 104729 + 12345) / 4294967296.0 for j in range(6)]
            out.append({"x": h[0] * W, "y": h[1] * H, "vx": (h[2] - 0.5) * 24.0, "vy": 6.0 + h[3] * 22.0, "ph": h[4] * 6.2832, "sz": "s" if h[5] < 0.5 else "m" if h[5] < 0.85 else "l",
                        "a": 0.18 + 0.30 * h[2]})
        return out


@lru_cache(maxsize=4)
def _load(size: Tuple[int, int]) -> Tuple[Optional[Layer], str]:
    try:
        man = json.loads((DIR / "manifest.json").read_text())
        files = man["files"]
        blobs = {}
        for n in _NEEDED:
            b = (DIR / n).read_bytes()
            if hashlib.sha256(b).hexdigest() != files[n]["sha256"]:
                return None, f"texture asset {n} does not match its manifest; the clip was made without grain, vignette and dust (rebuild with explainer/motion/build_texture.py)"
            blobs[n] = b
        import io
        W, H = size
        tile = np.asarray(Image.open(io.BytesIO(blobs["grain_tile.png"])).convert("L"), dtype=np.float32)
        g = np.rint((tile - 128.0) / 28.0 * GRAIN_SIGMA).astype(np.int16)
        t = g.shape[0]
        big = np.tile(g, (H // t + 2, W // t + 2))
        vm = Image.open(io.BytesIO(blobs["vignette.png"])).convert("L").resize((W, H), Image.BILINEAR)
        dark = np.rint(np.asarray(vm, dtype=np.float32) * (VIGNETTE_MAX / 255.0)).astype(np.int16)
        k = 8 if W * H <= 2200000 else 6
        overlays = []
        for j in range(k):                                  # window offsets are fixed integers (a pure function of j), so the overlays are the same on every run
            ox, oy = (_mix(j * 2 + 1) % t), (_mix(j * 2 + 2) % t)
            o = np.clip(128 + big[oy:oy + H, ox:ox + W] - dark, 0, 255).astype(np.uint8)
            ol = Image.fromarray(o, "L")
            overlays.append(Image.merge("RGB", (ol, ol, ol)))
        sprites = {k: Image.open(io.BytesIO(blobs[f"dust_{k}.png"])).convert("L") for k in ("s", "m", "l")}
        return Layer(size, overlays, sprites), ""
    except Exception as exc:                  # never stop a render for a texture
        return None, f"texture assets are not available ({type(exc).__name__}: {exc}); the clip was made without grain, vignette and dust"


def get_layer(size: Tuple[int, int]) -> Tuple[Optional[Layer], str]:
    return _load((int(size[0]), int(size[1])))


def _specks(im: Image.Image, layer: Layer, t: float, mode: str) -> None:
    W, H = layer.size
    for s in layer.specks:
        if mode == "snow":
            y = (s["y"] + s["vy"] * 3.0 * t) % (H + 40) - 20
            x = (s["x"] + 14.0 * math.sin(0.7 * t + s["ph"]) + s["vx"] * t * 0.5) % W
            alpha, col = min(0.85, s["a"] * 2.0), (255, 255, 255)
        else:
            y = (s["y"] - s["vy"] * 0.6 * t) % (H + 40) - 20           # dust drifts slowly upward and sideways
            x = (s["x"] + s["vx"] * t + 10.0 * math.sin(0.4 * t + s["ph"])) % W
            alpha, col = s["a"], (255, 250, 238)
        key = (s["sz"], int(alpha * 100))
        m = layer.masks.get(key)
        if m is None:
            m = layer.masks[key] = layer.sprites[s["sz"]].point(lambda v, a=alpha: int(v * a + 0.5))
        im.paste(col, (int(x) - m.width // 2, int(y) - m.height // 2), m)


def apply(im: Image.Image, layer: Optional[Layer], frame_no: int, fps: int, mode: str = "dust") -> Image.Image:
    """Dust/snow specks, then vignette + grain in one integer pass. A frame number gives the same result every time."""
    if layer is None or not mode:
        return im
    if im.size != layer.size:
        return im
    if mode in ("dust", "snow"):
        _specks(im, layer, frame_no / float(fps), mode)
    k = (frame_no * 3 + _mix(frame_no) % 2) % len(layer.overlays)       # neighbouring frames never use the same overlay (step 2..4 of 8, or of 6)
    return ImageChops.add(im, layer.overlays[k], 1.0, -128)
