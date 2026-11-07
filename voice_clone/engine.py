"""Voice cloner: copy the voice of a sample recording onto the narration.

The narration is made first by the Voiceover tab's Edge voice (any language), then OpenVoice v2's small tone-colour converter
(MIT licence, https://github.com/myshell-ai/OpenVoice) swaps the speaker's timbre for the one in the user's sample while the
words, timing and pacing stay. It runs on this computer after a one-time download (PyTorch + a ~130 MB model); nothing about the
sample is sent anywhere. Only use a voice that is yours or whose owner agreed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Callable, Optional

import numpy as np

SR = 22050                      # the converter's sampling rate
MODEL_BASE = "https://huggingface.co/myshell-ai/OpenVoiceV2/resolve/main/converter/"
MODEL_FILES = {"config.json": 300, "checkpoint.pth": 100_000_000}   # name -> minimum plausible bytes
MIN_SAMPLE_SEC, GOOD_SAMPLE_SEC, MAX_SAMPLE_SEC = 6.0, 20.0, 90.0
MAX_WINDOW_SEC = 30.0           # longer narration pieces are converted in windows cut at quiet points
DEFAULT_TAU = 0.3


def data_dir() -> Path:
    """Per-user folder for the model and saved voices (VIDEOGEN_VOICE_CLONE overrides it)."""
    override = os.environ.get("VIDEOGEN_VOICE_CLONE")
    if override:
        base = Path(override)
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "SemanticYTStudio" / "voice_clone"
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "SemanticYTStudio" / "voice_clone"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "semantic-yt-studio" / "voice_clone"
    base.mkdir(parents=True, exist_ok=True)
    return base


def ensure_torch(say: Optional[Callable[[str], None]] = None) -> bool:
    """True when PyTorch imports. Otherwise install it once with pip (not possible in a packaged build)."""
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        pass
    if getattr(sys, "frozen", False):
        return False
    if say:
        say("Setting up the voice cloner (one time, a few minutes)...")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "torch"], capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        return False
    import importlib
    importlib.invalidate_caches()
    try:
        import torch  # noqa: F401,F811
        return True
    except ImportError:
        return False


def _model_dir() -> Path:
    d = data_dir() / "model"
    d.mkdir(parents=True, exist_ok=True)
    return d


def models_ready() -> bool:
    d = _model_dir()
    return all((d / n).is_file() and (d / n).stat().st_size >= m for n, m in MODEL_FILES.items())


def ensure_models(say: Optional[Callable[[str], None]] = None) -> bool:
    d = _model_dir()
    for name, minimum in MODEL_FILES.items():
        dest = d / name
        if dest.is_file() and dest.stat().st_size >= minimum:
            continue
        if say:
            say(f"Downloading the voice model ({name}, one time)...")
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            req = urllib.request.Request(MODEL_BASE + name, headers={"User-Agent": "semantic-yt-studio"})
            with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
                while True:
                    block = r.read(1 << 20)
                    if not block:
                        break
                    f.write(block)
            if tmp.stat().st_size < minimum:
                raise OSError("download too small")
            os.replace(tmp, dest)
        except Exception:  # noqa: BLE001
            try:
                tmp.unlink()
            except OSError:
                pass
            return False
    return True


def read_audio(path: str, ffmpeg: str = "ffmpeg", start: float = 0.0, seconds: Optional[float] = None) -> np.ndarray:
    """Any audio/video file -> mono float32 at the converter's rate."""
    cmd = [ffmpeg, "-v", "error", "-nostdin"]
    if start:
        cmd += ["-ss", str(start)]
    cmd += ["-i", str(path)]
    if seconds:
        cmd += ["-t", str(seconds)]
    cmd += ["-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    out = subprocess.run(cmd, capture_output=True, timeout=1800)
    if out.returncode != 0 or not out.stdout:
        raise ValueError("could not read audio: " + out.stderr.decode("utf-8", "replace")[:160])
    return np.frombuffer(out.stdout, dtype=np.float32).copy()


def write_mp3(audio: np.ndarray, path: str, ffmpeg: str = "ffmpeg", rate: int = 24000, bitrate: str = "48k") -> None:
    """Float samples at the converter's rate -> mp3 in the same shape the Voiceover tab's pieces use (mono, 24 kHz)."""
    pcm = np.clip(audio, -1.0, 1.0).astype(np.float32).tobytes()
    r = subprocess.run([ffmpeg, "-y", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", "-ar", str(rate),
                        "-c:a", "libmp3lame", "-b:a", bitrate, str(path)], input=pcm, capture_output=True, timeout=1800)
    if r.returncode != 0:
        raise OSError("could not write audio: " + r.stderr.decode("utf-8", "replace")[:160])


def speech_seconds(audio: np.ndarray) -> float:
    """Seconds with real speech energy (frames above a fraction of the loudest), to judge a sample before using it."""
    if audio.size < SR // 10:
        return 0.0
    hop = SR // 50
    n = audio.size // hop
    rms = np.sqrt((audio[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
    return float((rms > max(0.01, 0.1 * float(rms.max()))).sum() * hop / SR)


def split_windows(audio: np.ndarray, max_sec: float = MAX_WINDOW_SEC) -> list:
    """Cut long audio into windows of at most max_sec at the quietest nearby point so no word is cut in half."""
    limit = int(max_sec * SR)
    if audio.size <= limit:
        return [audio]
    out, pos, hop = [], 0, SR // 100
    while audio.size - pos > limit:
        lo, hi = pos + int(limit * 0.6), pos + limit
        seg = audio[lo:hi]
        n = seg.size // hop
        rms = np.sqrt((seg[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
        cut = lo + int(np.argmin(rms)) * hop + hop // 2
        out.append(audio[pos:cut])
        pos = cut
    out.append(audio[pos:])
    return out


class Cloner:
    """Loads the converter once; makes voice profiles and converts audio. Use from a worker thread."""

    def __init__(self, ffmpeg: str = "ffmpeg"):
        import torch
        from .ov import models, spec
        self.torch, self.spec, self.ffmpeg = torch, spec, ffmpeg
        d = _model_dir()
        self.hps = spec.hparams_from_file(str(d / "config.json"))
        self.device = "cpu"          # CPU is quick enough for this small model and behaves the same on every machine
        self.model = models.SynthesizerTrn(len(getattr(self.hps, "symbols", [])), self.hps.data.filter_length // 2 + 1,
                                           n_speakers=self.hps.data.n_speakers, **self.hps.model).to(self.device)
        ckpt = torch.load(str(d / "checkpoint.pth"), map_location="cpu", weights_only=True)   # tensors only, never pickled code
        self.model.load_state_dict(ckpt["model"], strict=False)
        self.model.eval()

    def embedding(self, audio: np.ndarray):
        """The speaker embedding (a small tensor) of mono audio at the converter's rate."""
        torch, h = self.torch, self.hps
        y = torch.from_numpy(audio).float().unsqueeze(0)
        s = self.spec.spectrogram_torch(y, h.data.filter_length, h.data.sampling_rate, h.data.hop_length, h.data.win_length, center=False)
        with torch.no_grad():
            return self.model.ref_enc(s.transpose(1, 2)).unsqueeze(-1).detach()

    def convert(self, audio: np.ndarray, src_se, tgt_se, tau: float = DEFAULT_TAU) -> np.ndarray:
        torch, h = self.torch, self.hps
        outs = []
        for win in split_windows(audio):
            y = torch.from_numpy(win).float().unsqueeze(0)
            s = self.spec.spectrogram_torch(y, h.data.filter_length, h.data.sampling_rate, h.data.hop_length, h.data.win_length, center=False)
            lens = torch.LongTensor([s.size(-1)])
            with torch.no_grad():
                o = self.model.voice_conversion(s, lens, sid_src=src_se, sid_tgt=tgt_se, tau=tau)[0][0, 0]
            outs.append(o.data.cpu().float().numpy())
        return np.concatenate(outs) if outs else audio


# ---- saved voices -------------------------------------------------------------------------------------------------------

def _voices_dir() -> Path:
    d = data_dir() / "voices"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(name: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")[:40] or "voice"


def list_voices() -> list:
    """[(name, embedding path)] of the saved cloned voices, oldest first."""
    out = []
    for meta in sorted(_voices_dir().glob("*/voice.json"), key=lambda p: p.stat().st_mtime):
        try:
            info = json.loads(meta.read_text(encoding="utf-8"))
            se = meta.parent / "se.pt"
            if se.is_file():
                out.append((info.get("name") or meta.parent.name, str(se)))
        except (OSError, ValueError):
            continue
    return out


def check_sample(path: str, ffmpeg: str = "ffmpeg") -> tuple:
    """(ok, message, audio). A sample needs several seconds of clear speech; more is better up to about a minute."""
    try:
        audio = read_audio(path, ffmpeg, seconds=MAX_SAMPLE_SEC)
    except Exception as exc:  # noqa: BLE001
        return False, f"That file could not be read as audio ({exc}).", None
    sec = speech_seconds(audio)
    if sec < MIN_SAMPLE_SEC:
        return False, f"Only {sec:.0f} s of speech found. Use at least {MIN_SAMPLE_SEC:.0f} s of one person talking, ideally {GOOD_SAMPLE_SEC:.0f}-60 s with no music.", None
    note = "" if sec >= GOOD_SAMPLE_SEC else f" (a longer sample, around {GOOD_SAMPLE_SEC:.0f} s, copies the voice more closely)"
    return True, f"{sec:.0f} s of speech found{note}.", audio


def make_voice(name: str, audio: np.ndarray, cloner: "Cloner") -> str:
    """Save a cloned voice from checked sample audio; returns the embedding path."""
    d = _voices_dir() / _slug(name)
    d.mkdir(parents=True, exist_ok=True)
    cloner.torch.save(cloner.embedding(audio).cpu(), str(d / "se.pt"))
    (d / "voice.json").write_text(json.dumps({"name": name, "sample_seconds": round(audio.size / SR, 1)}), encoding="utf-8")
    return str(d / "se.pt")


def delete_voice(name: str) -> None:
    import shutil
    shutil.rmtree(_voices_dir() / _slug(name), ignore_errors=True)


def make_converter_for(se_path: str, cloner: "Cloner", tau: float = DEFAULT_TAU) -> Callable[[str, str], None]:
    """A function (piece_mp3 -> converted_mp3, in place of the piece) for edge_voiceover.synthesize(convert=...).
    The source embedding is taken from the narration itself (the first piece), so any Edge voice in any language works."""
    tgt = cloner.torch.load(se_path, map_location="cpu", weights_only=True)
    state: dict = {"src": None}

    def convert(src_mp3: str, dst_mp3: str) -> None:
        audio = read_audio(src_mp3, cloner.ffmpeg)
        if state["src"] is None:
            state["src"] = cloner.embedding(audio[: int(GOOD_SAMPLE_SEC * SR)])
        write_mp3(cloner.convert(audio, state["src"], tgt, tau), dst_mp3, cloner.ffmpeg)

    return convert
