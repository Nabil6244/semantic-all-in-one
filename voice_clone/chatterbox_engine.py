"""Chatterbox Turbo voice cloning: reads the script straight in the cloned voice (its accent and rhythm too, not only its tone).

Chatterbox (Resemble AI, MIT licence, https://github.com/resemble-ai/chatterbox) runs on this computer in its own Python
environment under the voice-clone data folder, so its pinned packages never touch the app's own. The first use downloads it once
(about 5 GB with the model). English only. Slower than Edge + OpenVoice: roughly 1-1.5x real time on an Apple M2.
Only use a voice that is yours or whose owner agreed.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Optional

from . import engine

PACKAGES = ["chatterbox-tts", "setuptools<81"]   # uv envs have no setuptools; the watermarker needs its pkg_resources
CHECK = "import chatterbox, pkg_resources; from perth.perth_net.perth_net_implicit.perth_watermarker import PerthImplicitWatermarker"
PY_VERSION = "3.11"             # Chatterbox's pinned packages have wheels for 3.10-3.11
MAX_CHUNK_CHARS = 260           # short pieces keep Chatterbox from skipping or repeating words
PAUSE_SEC = 0.25
REF_SECONDS = 20.0


def env_dir() -> Path:
    return engine.data_dir() / "chatterbox_env"


def env_python() -> Path:
    d = env_dir()
    return d / "Scripts" / "python.exe" if sys.platform == "win32" else d / "bin" / "python"


def worker_path() -> Path:
    return Path(__file__).with_name("chatterbox_worker.py")


def is_ready() -> bool:
    py = env_python()
    if not py.is_file():
        return False
    try:
        r = subprocess.run([str(py), "-c", CHECK], capture_output=True, timeout=600, stdin=subprocess.DEVNULL, env=_child_env())      # first torch import on Windows (antivirus scan) can be slow
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def _child_env() -> dict:
    """Environment for the Chatterbox env's Python and for uv: drop the packaged app's own Python settings so they never leak in."""
    env = dict(os.environ)
    for k in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONEXECUTABLE", "VIRTUAL_ENV", "__PYVENV_LAUNCHER__"):
        env.pop(k, None)
    for k in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):       # PyInstaller saves the original as *_ORIG and points these at itself
        if k + "_ORIG" in env:
            env[k] = env[k + "_ORIG"]
        elif getattr(sys, "frozen", False):
            env.pop(k, None)
    env.setdefault("UV_PYTHON_INSTALL_DIR", str(engine.data_dir() / "uv_python"))   # uv's Python 3.11 lives with the env
    env.setdefault("UV_CACHE_DIR", str(engine.data_dir() / "uv_cache"))
    env["PYTHONUTF8"] = "1"      # the worker's messages and paths read the same on a Windows code page
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def setup_log() -> Path:
    """What the one-time setup printed (uv's own messages), so a failed setup on someone's PC can be read afterwards."""
    return engine.data_dir() / "chatterbox_setup.log"


def _run(cmd: list, timeout: int = 3600) -> bool:
    # utf-8 + replace: uv/pip print non-ASCII (progress marks, names); a Windows code page would raise UnicodeDecodeError here
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                           stdin=subprocess.DEVNULL, env=_child_env())
        ok, out = r.returncode == 0, f"exit {r.returncode}\n{r.stdout[-4000:]}\n{r.stderr[-4000:]}"
    except (OSError, subprocess.TimeoutExpired) as ex:
        ok, out = False, f"{type(ex).__name__}: {ex}"
    try:
        with open(setup_log(), "a", encoding="utf-8") as f:
            f.write(f"$ {' '.join(map(str, cmd))}\n{out}\n\n")
    except OSError:
        pass
    return ok


def _bundled_uv() -> Optional[Path]:
    """The uv binary shipped inside the exe / .app (VideoGenerator.spec puts it in bin/ next to ffmpeg)."""
    name = "uv.exe" if sys.platform == "win32" else "uv"
    roots = []
    if getattr(sys, "_MEIPASS", None):
        roots.append(Path(sys._MEIPASS))
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
    for r in roots:
        for p in (r / "bin" / name, r / name):
            if p.is_file():
                return p
    return None


def uv_command() -> Optional[list]:
    """How to call uv: the bundled binary, else uv on PATH, else (source runs only) the app Python's uv module, installed if missing."""
    p = _bundled_uv()
    if p:
        return [str(p)]
    import shutil
    w = shutil.which("uv")
    if w:
        return [w]
    if getattr(sys, "frozen", False):
        return None
    cmd = [sys.executable, "-m", "uv"]
    if _run(cmd + ["--version"], 120) or _run([sys.executable, "-m", "pip", "install", "--quiet", "uv"], 600):
        return cmd
    return None


def ensure_env(say: Optional[Callable[[str], None]] = None) -> bool:
    """Make the Chatterbox environment once: its own Python 3.11 (via uv, which fetches it) with chatterbox-tts installed.
    Works the same from source, the Windows exe and the Mac .app (both ship uv)."""
    if is_ready():
        return True
    uv = uv_command()
    if not uv:
        return False
    if say:
        say("Setting up Chatterbox (one time, about 5 GB with the model, 10-30 minutes)...")
    d = env_dir()
    if not env_python().is_file():
        if not _run(uv + ["venv", "--python", PY_VERSION, "--python-preference", "only-managed", str(d)], 1800):
            return False
    if say:
        say("Installing Chatterbox into its own environment (one time)...")
    install = uv + ["pip", "install", "--python", str(env_python()), *PACKAGES]
    # Windows/Linux: PyPI's torch is CPU-only there, so let uv pick the CUDA build when an NVIDIA card is present.
    # (Macs use PyPI's torch, which already has Apple GPU support.) Older uv lacks the flag, so retry without it.
    if sys.platform != "darwin" and _run(install + ["--torch-backend", "auto"], 3600):
        return is_ready()
    if not _run(install, 3600):
        return False
    return is_ready()


# ---- the voice sample ---------------------------------------------------------------------------------------------------

def reference_path(se_path: str) -> Path:
    """The sample Chatterbox copies, saved next to the saved voice's OpenVoice fingerprint."""
    return Path(se_path).parent / "sample.wav"


def save_reference(src: str, dest: Path, ffmpeg: str = "ffmpeg", seconds: float = REF_SECONDS) -> Path:
    """The first ~20 s of speech from the user's recording (leading silence dropped, cut at a pause), as a 24 kHz wav."""
    rate = 24000
    audio = engine.read_audio(src, ffmpeg, seconds=engine.MAX_SAMPLE_SEC, rate=rate)
    hop = rate // 50
    n = audio.size // hop
    if n:
        import numpy as np
        rms = np.sqrt((audio[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
        loud = np.nonzero(rms > max(0.01, 0.1 * float(rms.max())))[0]
        if loud.size:
            audio = audio[max(0, int(loud[0]) * hop - rate // 10):]
    audio = engine.split_windows(audio, seconds, rate=rate)[0]
    engine.write_wav(audio, str(dest), rate)
    return dest


# ---- making the voiceover -----------------------------------------------------------------------------------------------

def synthesize(text: str, out_mp3: str, ref_wav: str, speed: float = 1.0,
               ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe",
               progress: Optional[Callable[[int, int], None]] = None,
               cancel: Optional[Callable[[], bool]] = None, device: str = "", keep_dir: str = "") -> dict:
    """Same result shape as edge_voiceover.synthesize: {'path', 'duration', 'pieces', 'words_path'}.
    Chatterbox gives no word timings, so the words file is an empty list (later steps then transcribe as usual).
    keep_dir: keep the spoken pieces there, so a run that stops (disk full, crash, Stop) picks up where it left off."""
    import edge_voiceover as ev

    pieces = ev.split_script(text, MAX_CHUNK_CHARS)
    if not pieces:
        raise ValueError("empty script")
    if not Path(ref_wav).is_file():
        raise RuntimeError("this voice has no saved sample for Chatterbox; add the voice again from its recording")
    if keep_dir:
        os.makedirs(keep_dir, exist_ok=True)
    with (contextlib.nullcontext(keep_dir) if keep_dir else tempfile.TemporaryDirectory()) as wd:
        job = {"ref": str(ref_wav), "device": device,
               "pieces": [{"text": t, "out": os.path.join(wd, f"piece_{i:04d}_{hashlib.md5(t.encode('utf-8')).hexdigest()[:8]}.wav")}
                          for i, t in enumerate(pieces)]}
        todo = [q for q in job["pieces"] if not (os.path.isfile(q["out"]) and os.path.getsize(q["out"]) > 1000)]
        job_path = os.path.join(wd, "job.json")
        with open(job_path, "w", encoding="utf-8") as f:
            json.dump({**job, "pieces": todo}, f)
        done, error = len(pieces) - len(todo), ""
        proc = None
        if todo:                                      # every piece already kept from an earlier run: no model load needed
            proc = subprocess.Popen([str(env_python()), str(worker_path()), job_path], stdout=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", env=_child_env())
        try:
            for line in (proc.stdout if proc else []):
                if cancel and cancel():
                    raise RuntimeError("stopped")
                try:
                    ev_ = json.loads(line)
                except ValueError:
                    continue
                if "error" in ev_:
                    error = ev_["error"]
                elif "done" in ev_:
                    done += 1
                    if progress:
                        progress(done, len(pieces))
                elif "ready" in ev_ and progress:
                    progress(done, len(pieces))
            if proc:
                proc.wait()
        finally:
            if proc and proc.poll() is None:
                proc.kill()
                proc.wait()
        if done < len(pieces):
            raise RuntimeError("Chatterbox stopped early" + (f": {error}" if error else ""))

        gap = os.path.join(wd, "gap.wav")
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(PAUSE_SEC),
                        "-c:a", "pcm_s16le", gap], check=True, timeout=600)
        lst = os.path.join(wd, "list.txt")
        with open(lst, "w") as f:
            for p in job["pieces"]:
                f.write(ev._concat_line(p["out"]))
                f.write(ev._concat_line(gap))
        os.makedirs(os.path.dirname(os.path.abspath(out_mp3)), exist_ok=True)
        base = [ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst]
        tempo = [f"atempo={speed:.3f}"] if abs(speed - 1.0) > 0.01 else []
        enc = ["-ar", "44100", "-c:a", "libmp3lame", "-b:a", "192k", out_mp3]
        try:
            ok = subprocess.run(base + ["-af", ",".join(tempo + ["loudnorm=I=-14:TP=-1.5:LRA=11"])] + enc, timeout=1800).returncode == 0
        except subprocess.TimeoutExpired:
            ok = False
        if not ok or not os.path.isfile(out_mp3) or os.path.getsize(out_mp3) == 0:
            subprocess.run(base + (["-af", tempo[0]] if tempo else []) + enc, check=True, timeout=1800)
    words_path = out_mp3 + ".words.json"
    with open(words_path, "w") as f:
        json.dump([], f)
    return {"path": out_mp3, "duration": ev._duration(out_mp3, ffprobe), "pieces": len(pieces), "words_path": words_path}
