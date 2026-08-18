"""
Generate a voiceover with Coqui XTTS-v2 (voice cloning).

Requires: assets/reference.wav and script.csv (script_segment column).
Exports: voiceover.mp3

Requires Python 3.11 (Coqui TTS does not support 3.13). Use the audio venv:

  /opt/homebrew/bin/python3.11 -m venv .venv-audio
  .venv-audio/bin/python -m pip install -r requirements-audio.txt
  .venv-audio/bin/python audio_generator.py

Note: pydub needs ffmpeg for MP3 export. Install separately if missing
(e.g. `brew install ffmpeg` on macOS). ffmpeg is already available on this system.
"""

import csv
import os
import re
import sys
import tempfile
import traceback

# Homebrew Python on newer macOS links pyexpat to /usr/lib/libexpat, which is
# missing symbols. Re-exec with DYLD_LIBRARY_PATH so dyld resolves Homebrew's
# libexpat before any imports pull in pyexpat (matplotlib via Coqui TTS).
def _reexec_with_homebrew_expat():
    if os.environ.get("_VG_EXPAT_FIXED") == "1":
        return

    candidates = [
        "/opt/homebrew/opt/expat/lib",  # Apple Silicon
        "/usr/local/opt/expat/lib",  # Intel Homebrew
    ]
    lib_dir = next(
        (d for d in candidates if os.path.isfile(os.path.join(d, "libexpat.1.dylib"))),
        None,
    )
    if not lib_dir:
        return

    env = os.environ.copy()
    env["_VG_EXPAT_FIXED"] = "1"
    env["MPLBACKEND"] = env.get("MPLBACKEND", "Agg")
    existing = env.get("DYLD_LIBRARY_PATH", "")
    env["DYLD_LIBRARY_PATH"] = lib_dir if not existing else f"{lib_dir}:{existing}"
    os.execve(sys.executable, [sys.executable, *sys.argv], env)


_reexec_with_homebrew_expat()
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
import soundfile as sf
import torch
import torchaudio
from pydub import AudioSegment
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models import xtts as xtts_module
from TTS.tts.models.xtts import Xtts
from TTS.utils.manage import ModelManager

# Paths relative to this script's directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REFERENCE_WAV = os.path.join(SCRIPT_DIR, "assets", "reference.wav")
SCRIPT_CSV = os.path.join(SCRIPT_DIR, "script.csv")
OUTPUT_MP3 = os.path.join(SCRIPT_DIR, "voiceover.mp3")

MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
SAMPLE_RATE = 24000
MAX_CHUNK_CHARS = 250  # XTTS English hard limit; longer text gets truncated
SILENCE_MS = 200  # shorter gap = less dead air between chunks
TEMPERATURE = 0.65
# >1.0 = faster speech + fewer decoder steps (1.0 = natural pace, 1.2 ≈ 20% quicker)
SPEED = 1.2

# XTTS download prompts for Coqui license acceptance; set for non-interactive runs
os.environ.setdefault("COQUI_TOS_AGREED", "1")
# Allow CPU fallback for rare ops not implemented on Apple MPS
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")


def patch_xtts_audio_loader():
    """
    Newer torchaudio.load() requires torchcodec. Patch Coqui's load_audio to use
    soundfile instead (already a dependency), keeping resample via torchaudio.
    """

    def load_audio(audiopath, sampling_rate):
        data, lsr = sf.read(audiopath, dtype="float32")
        audio = torch.from_numpy(np.asarray(data))
        if audio.ndim == 1:
            audio = audio.unsqueeze(0)
        else:
            # soundfile: (samples, channels) -> (channels, samples)
            audio = audio.transpose(0, 1)
            if audio.size(0) != 1:
                audio = torch.mean(audio, dim=0, keepdim=True)

        if lsr != sampling_rate:
            audio = torchaudio.functional.resample(audio, lsr, sampling_rate)

        if torch.any(audio > 10) or not torch.any(audio < 0):
            print(f"Error with {audiopath}. Max={audio.max()} min={audio.min()}")
        audio.clip_(-1, 1)
        return audio

    xtts_module.load_audio = load_audio


def detect_device():
    """Prefer CUDA, then Apple MPS (M1/M2/M3), else CPU."""
    if torch.cuda.is_available():
        device = "cuda"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"
    print(f"Using device: {device}")
    if device == "cpu":
        print(
            "Warning: CPU is very slow for XTTS (~minutes per chunk). "
            "On Apple Silicon, MPS should be used automatically."
        )
    return device


def load_xtts_model(device):
    """
    Load XTTS-v2 from the local TTS cache.
    ModelManager auto-downloads on first run if the model is not cached yet.
    """
    print(f"Loading {MODEL_NAME} (from cache, or downloading on first run)...")
    manager = ModelManager()
    model_path, config_path, _model_item = manager.download_model(MODEL_NAME)

    # XTTS special-case: download_model returns (checkpoint_dir, None, item)
    # instead of (model.pth, config.json, item) used by other models.
    if config_path is None:
        checkpoint_dir = model_path
        config_path = os.path.join(checkpoint_dir, "config.json")
    else:
        checkpoint_dir = os.path.dirname(model_path)

    if not os.path.isfile(config_path):
        raise FileNotFoundError(f"XTTS config not found at {config_path}")

    config = XttsConfig()
    config.load_json(config_path)
    model = Xtts.init_from_config(config)

    # PyTorch 2.6+ defaults torch.load(weights_only=True), which breaks Coqui
    # checkpoints that pickle config objects. Official XTTS weights are trusted.
    _orig_torch_load = torch.load

    def _torch_load_compat(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return _orig_torch_load(*args, **kwargs)

    torch.load = _torch_load_compat
    try:
        model.load_checkpoint(config, checkpoint_dir=checkpoint_dir, eval=True)
    finally:
        torch.load = _orig_torch_load

    model.eval()
    if device == "cuda":
        model.cuda()
    elif device == "mps":
        model.to(torch.device("mps"))
    else:
        model.cpu()

    print("Model loaded.")
    return model


def read_script(path):
    """
    Build the full voiceover script from script.csv.
    Joins script_segment values in scene_number order (same CSV as the video tool).
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "script_segment" not in reader.fieldnames:
            raise ValueError(
                f"{path} must include a script_segment column "
                f"(found: {reader.fieldnames})"
            )
        rows = list(reader)

    if "scene_number" in (reader.fieldnames or []):
        def sort_key(row):
            try:
                return int(str(row.get("scene_number", "")).strip())
            except ValueError:
                return str(row.get("scene_number", "")).strip()

        rows.sort(key=sort_key)

    segments = [
        (row.get("script_segment") or "").strip()
        for row in rows
        if (row.get("script_segment") or "").strip()
    ]
    return " ".join(segments)


def _split_long_sentence(sentence, max_chars):
    """If a sentence exceeds max_chars, split on commas/semicolons (not mid-word)."""
    if len(sentence) <= max_chars:
        return [sentence]

    parts = re.split(r"(?<=[,;:])\s+", sentence)
    pieces = []
    current = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if not current:
            candidate = part
        else:
            candidate = f"{current} {part}"

        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                pieces.append(current)
            # Hard-wrap only if a single clause is still too long
            if len(part) > max_chars:
                for i in range(0, len(part), max_chars):
                    pieces.append(part[i : i + max_chars])
                current = ""
            else:
                current = part
    if current:
        pieces.append(current)
    return pieces


def split_into_chunks(text, max_chars=MAX_CHUNK_CHARS):
    """
    Pack text into ~max_chars chunks on sentence boundaries.
    Oversized sentences are split on commas so we stay under XTTS's 250-char limit
    (avoids truncated audio and wasted generation).
    """
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    units = []
    for sentence in sentences:
        sentence = sentence.strip()
        if sentence:
            units.extend(_split_long_sentence(sentence, max_chars))

    chunks = []
    current = ""
    for unit in units:
        if not current:
            current = unit
        elif len(current) + 1 + len(unit) <= max_chars:
            current = f"{current} {unit}"
        else:
            chunks.append(current)
            current = unit
    if current:
        chunks.append(current)
    return chunks


def generate_voiceover():
    """Main pipeline: load model, clone voice, synthesize chunks, merge to MP3."""
    import time

    # Fail early with clear messages if inputs are missing
    if not os.path.isfile(REFERENCE_WAV):
        raise FileNotFoundError(
            f"Missing reference voice sample: {REFERENCE_WAV}\n"
            "Place a WAV file at assets/reference.wav."
        )
    if not os.path.isfile(SCRIPT_CSV):
        raise FileNotFoundError(
            f"Missing script file: {SCRIPT_CSV}\n"
            "Place script.csv (with a script_segment column) in the same directory "
            "as this script."
        )

    device = detect_device()
    model = load_xtts_model(device)
    patch_xtts_audio_loader()

    # Compute speaker conditioning latents ONCE; reuse for every chunk
    print(f"Computing speaker latents from {REFERENCE_WAV}...")
    with torch.inference_mode():
        gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
            audio_path=[REFERENCE_WAV]
        )
    print("Speaker latents ready.")

    script_text = read_script(SCRIPT_CSV)
    chunks = split_into_chunks(script_text)
    total = len(chunks)
    if total == 0:
        raise ValueError("script.csv has no script_segment text — nothing to synthesize.")

    print(f"Split script into {total} chunk(s). Generating audio...")

    temp_dir = tempfile.mkdtemp(prefix="xtts_chunks_")
    chunk_paths = []
    t0 = time.perf_counter()

    try:
        # Generate one WAV per chunk (packed to ~250 chars to minimize round-trips)
        for i, chunk_text in enumerate(chunks, start=1):
            chunk_start = time.perf_counter()
            with torch.inference_mode():
                out = model.inference(
                    chunk_text,
                    "en",
                    gpt_cond_latent,
                    speaker_embedding,
                    temperature=TEMPERATURE,
                    speed=SPEED,
                    enable_text_splitting=False,
                )
            if device == "mps":
                torch.mps.synchronize()

            wav = np.asarray(out["wav"], dtype=np.float32)
            chunk_path = os.path.join(temp_dir, f"chunk_{i:04d}.wav")
            sf.write(chunk_path, wav, SAMPLE_RATE)
            chunk_paths.append(chunk_path)

            elapsed = time.perf_counter() - t0
            avg = elapsed / i
            eta = avg * (total - i)
            chunk_secs = time.perf_counter() - chunk_start
            print(
                f"Chunk {i}/{total} done ({chunk_secs:.1f}s) — "
                f"ETA ~{eta / 60:.1f} min"
            )

        # Concatenate chunks with a short silence gap between them
        print(f"Merging chunks with {SILENCE_MS}ms silence gaps...")
        silence = AudioSegment.silent(duration=SILENCE_MS)
        combined = AudioSegment.empty()

        for i, path in enumerate(chunk_paths):
            segment = AudioSegment.from_wav(path)
            if i > 0:
                combined += silence
            combined += segment

        # Export final voiceover as MP3 (requires ffmpeg)
        combined.export(OUTPUT_MP3, format="mp3")
        total_mins = (time.perf_counter() - t0) / 60
        print(f"Saved voiceover to {OUTPUT_MP3} (generation took {total_mins:.1f} min)")

    finally:
        # Clean up temp per-chunk WAV files and the temp directory
        for path in chunk_paths:
            try:
                os.remove(path)
            except OSError:
                pass
        try:
            os.rmdir(temp_dir)
        except OSError:
            # Directory may still have leftover files; remove what we can
            for name in os.listdir(temp_dir):
                try:
                    os.remove(os.path.join(temp_dir, name))
                except OSError:
                    pass
            try:
                os.rmdir(temp_dir)
            except OSError:
                pass


if __name__ == "__main__":
    try:
        generate_voiceover()
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"Error generating voiceover: {exc}")
        traceback.print_exc()
        raise SystemExit(1) from exc
