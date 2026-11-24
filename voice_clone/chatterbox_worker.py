"""Runs inside the Chatterbox environment (its own Python), never imported by the app.

Usage: python chatterbox_worker.py job.json
job = {"ref": sample.wav, "device": "" | "mps" | "cpu" | "cuda", "pieces": [{"text": ..., "out": piece.wav}, ...]}
Prints one JSON line per event on stdout: {"ready": device, "model": kind}, {"done": i, "seconds": s}, {"error": msg}.
"""
import json
import os
import sys
import wave

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")


def say(**kw):
    print(json.dumps(kw), flush=True)


def load_model(device):
    import torch
    if not device:
        device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    try:
        from chatterbox.tts_turbo import ChatterboxTurboTTS as Model
        kind = "turbo"
    except ImportError:
        from chatterbox.tts import ChatterboxTTS as Model
        kind = "standard"
    try:
        return Model.from_pretrained(device=device), device, kind
    except Exception:  # noqa: BLE001 - a graphics chip that cannot run it falls back to the processor
        if device == "cpu":
            raise
        return Model.from_pretrained(device="cpu"), "cpu", kind


def write_wav(path, samples, rate):
    import numpy as np
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


def expected_seconds(text):
    return max(1.0, len(text.split()) / 2.6)      # ~156 words a minute


def main():
    job = json.load(open(sys.argv[1], encoding="utf-8"))
    model, device, kind = load_model(job.get("device") or "")
    ref = job["ref"]
    primed = False
    try:
        model.prepare_conditionals(ref)          # read the voice once, not once per piece
        primed = True
    except Exception:  # noqa: BLE001
        pass
    say(ready=device, model=kind)
    for i, piece in enumerate(job["pieces"]):
        text = piece["text"]
        best = None
        for _attempt in range(3):               # a piece that comes out far too long or empty is made again
            try:
                wav = model.generate(text) if primed else model.generate(text, audio_prompt_path=ref)
            except Exception as exc:  # noqa: BLE001 - a graphics chip that loads the model but fails on a line (out of memory,
                if device == "cpu":   # an op it lacks) finishes the run on the processor instead of stopping it
                    raise
                print(f"chatterbox: {device} failed ({type(exc).__name__}: {str(exc)[:200]}); continuing on the CPU", file=sys.stderr, flush=True)
                model, device, kind = load_model("cpu")
                primed = False
                try:
                    model.prepare_conditionals(ref)
                    primed = True
                except Exception:  # noqa: BLE001
                    pass
                say(ready=device, model=kind)
                wav = model.generate(text) if primed else model.generate(text, audio_prompt_path=ref)
            samples = wav.squeeze().detach().cpu().float().numpy()
            sec = samples.size / model.sr
            best = samples
            if 0.3 < sec < expected_seconds(text) * 2.5 + 3:
                break
        write_wav(piece["out"], best, model.sr)
        say(done=i, seconds=round(best.size / model.sr, 2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()                    # to stderr: the app keeps it in chatterbox_run.log
        say(error=f"{type(exc).__name__}: {str(exc)[:300]}")
        sys.exit(1)
