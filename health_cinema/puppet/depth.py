"""Per-still depth with Depth Anything V2 Small (ONNX, runs locally on onnxruntime, ~0.3 s per still, cached by pixel hash).

    depth_map(path_or_image) -> float32 array (H, W) in 0..1, 1 = NEAR, at the picture's own size.

The model file is a one-time download (out/models/depth_anything_v2_small/model.onnx). If it is missing or onnxruntime is not installed,
available() is False and callers fall back to the old pseudo depth / plain camera move."""
from __future__ import annotations
import hashlib
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "out" / "models" / "depth_anything_v2_small" / "model.onnx"
CACHE = ROOT / "out" / "puppet_cache" / "depth"
SIZE = 518
_sess = None

def available() -> bool:
    try:
        import onnxruntime  # noqa: F401
    except Exception:
        return False
    return MODEL.is_file()

def _session():
    global _sess
    if _sess is None:
        import onnxruntime as ort
        _sess = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])
    return _sess

def depth_map(src) -> np.ndarray:
    im = src if isinstance(src, Image.Image) else Image.open(src)
    im = im.convert("RGB")
    key = hashlib.sha256(im.resize((96, 54)).tobytes() + str(im.size).encode()).hexdigest()[:20]
    f = CACHE / (key + ".npy")
    if f.is_file():
        return np.load(f).astype(np.float32)
    x = np.asarray(im.resize((SIZE, SIZE), Image.BICUBIC), np.float32) / 255.0
    x = ((x - np.array([.485, .456, .406], np.float32)) / np.array([.229, .224, .225], np.float32)).transpose(2, 0, 1)[None]
    s = _session(); out = s.run(None, {s.get_inputs()[0].name: x.astype(np.float32)})[0]
    d = np.squeeze(out).astype(np.float32)
    lo, hi = np.percentile(d, 1), np.percentile(d, 99)
    d = np.clip((d - lo) / max(hi - lo, 1e-6), 0, 1)
    d = np.asarray(Image.fromarray(d, "F").resize(im.size, Image.BICUBIC), np.float32).clip(0, 1)
    CACHE.mkdir(parents=True, exist_ok=True); np.save(f, d.astype(np.float16))
    return d
