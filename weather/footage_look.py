"""Does a clip LOOK like what was asked for? A small CLIP model run on this computer (free, no network, no credits).

weather/footage_match.py compares a clip's TITLE with the request; a title cannot say that a "storm" clip shows only calm clouds. This
module looks at the pictures: it takes a few frames of the clip and measures how close they are to the words of the request
(CLIP: a picture and a sentence both become a list of 512 numbers; the closer, the more the picture looks like the sentence).

    look = Look.load()            # None when the model files are not on this computer: the title check alone is used
    s = look.score(frames, "flooded street")     # about 0.15 (not it) .. 0.35 (it): compare clips with each other, not with a fixed number
    look.rank(video_files, request)              # the files, best first, with their scores

The model is OpenAI's CLIP ViT-B/32 as 8-bit ONNX files (Xenova/clip-vit-base-patch32 on Hugging Face, about 155 MB): vision_model_int8.onnx,
text_model_int8.onnx, tokenizer.json. They are looked for in $SEMANTIC_YT_CLIP_DIR, then in the app's models folder (see model_dirs)."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np

MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
FILES = ("onnx/vision_model_int8.onnx", "onnx/text_model_int8.onnx", "tokenizer.json")


def model_dirs() -> List[Path]:
    out = []
    if os.environ.get("SEMANTIC_YT_CLIP_DIR"):
        out.append(Path(os.environ["SEMANTIC_YT_CLIP_DIR"]))
    out.append(Path.home() / ".semantic_yt_studio" / "models" / "clip")
    return out


def find_model() -> Optional[Path]:
    for d in model_dirs():
        if all((d / f).is_file() for f in FILES):
            return d
    return None


class Look:
    def __init__(self, folder: Path):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self._vision = ort.InferenceSession(str(folder / FILES[0]), opts, providers=["CPUExecutionProvider"])
        self._text = ort.InferenceSession(str(folder / FILES[1]), opts, providers=["CPUExecutionProvider"])
        self._tok = Tokenizer.from_file(str(folder / FILES[2]))
        self._texts: dict = {}

    @classmethod
    def load(cls, folder: "str | Path | None" = None) -> Optional["Look"]:
        """The model, or None when its files (or onnxruntime) are not here: callers then keep to the title check."""
        try:
            d = Path(folder) if folder else find_model()
            return cls(d) if d else None
        except Exception:
            return None

    # ---- pictures -----------------------------------------------------------------------------------------------------------
    @staticmethod
    def _prepare(path: "str | Path") -> np.ndarray:
        from PIL import Image

        im = Image.open(path).convert("RGB")
        w, h = im.size
        s = 224 / min(w, h)
        im = im.resize((max(224, round(w * s)), max(224, round(h * s))), Image.BICUBIC)
        w, h = im.size
        l, t = (w - 224) // 2, (h - 224) // 2
        a = np.asarray(im.crop((l, t, l + 224, t + 224)), dtype=np.float32) / 255.0
        return ((a - MEAN) / STD).transpose(2, 0, 1)

    def images(self, paths: Sequence["str | Path"]) -> np.ndarray:
        """Unit-length fingerprints, one row per picture."""
        if not paths:
            return np.zeros((0, 512), dtype=np.float32)
        x = np.stack([self._prepare(p) for p in paths]).astype(np.float32)
        e = self._vision.run(None, {"pixel_values": x})[0]
        return e / np.linalg.norm(e, axis=1, keepdims=True)

    # ---- words --------------------------------------------------------------------------------------------------------------
    def texts(self, sentences: Sequence[str]) -> np.ndarray:
        out = []
        for s in sentences:
            if s not in self._texts:
                ids = self._tok.encode(s).ids[:77]
                e = self._text.run(None, {"input_ids": np.array([ids], dtype=np.int64)})[0][:1]
                self._texts[s] = (e / np.linalg.norm(e, axis=1, keepdims=True))[0]
            out.append(self._texts[s])
        return np.stack(out) if out else np.zeros((0, 512), dtype=np.float32)

    # ---- scores -------------------------------------------------------------------------------------------------------------
    def score(self, frames: Sequence["str | Path"], request: str, template: str = "a photo of {}") -> float:
        """How much the frames look like the request: the mean cosine of the frames with the sentence."""
        im, tx = self.images(frames), self.texts([template.format(request)])[0]
        return float((im @ tx).mean()) if len(im) else 0.0

    def compare(self, frames: Sequence["str | Path"], options: Sequence[str]) -> List[float]:
        """Probabilities (they sum to 1) that the frames show each of `options`: the request against what it could be mistaken for."""
        im, tx = self.images(frames), self.texts([f"a photo of {o}" for o in options])
        if not len(im):
            return [1.0 / len(options)] * len(options)
        logits = 100.0 * (im @ tx.T).mean(axis=0)
        e = np.exp(logits - logits.max())
        return [float(v) for v in e / e.sum()]


def frames_of(video: "str | Path", n: int = 3, size: int = 448, ffmpeg: str = "ffmpeg") -> List[Path]:
    """`n` pictures of a video at 20 %, 50 % and 80 % of its length (in a temporary folder the caller deletes with `drop`)."""
    video = Path(video)
    d = Path(tempfile.mkdtemp(prefix="wx_look_"))
    try:
        dur = float(subprocess.run([ffmpeg.replace("ffmpeg", "ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                                   capture_output=True, text=True, timeout=30).stdout.strip() or 0)
    except Exception:
        dur = 0.0
    out: List[Path] = []
    for k in range(n):
        t = dur * (0.2 + 0.6 * k / max(1, n - 1)) if dur > 0 else 0.0
        f = d / f"{k}.jpg"
        subprocess.run([ffmpeg, "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", "-vf", f"scale={size}:-2", "-y", str(f)],
                       capture_output=True, timeout=60)
        if f.is_file() and f.stat().st_size > 0:
            out.append(f)
    return out


def drop(frames: Sequence[Path]) -> None:
    import shutil

    for d in {f.parent for f in frames}:
        shutil.rmtree(d, ignore_errors=True)
