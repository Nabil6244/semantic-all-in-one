"""Runs OpenVoice inside its own Python environment (made with uv), never imported by the app.

The packaged app (Windows exe / Mac .app) carries no PyTorch, so it starts this script with that environment's Python instead.
Usage: python openvoice_worker.py <ffmpeg>
Reads one JSON request per line on stdin and answers one JSON line on stdout:
  {"op": "embed", "wav": sample.wav, "out": se.pt}                                   -> {"ok": true}
  {"op": "convert", "src": piece.mp3, "dst": out.mp3, "tgt": se.pt, "tau": 0.3, "job": id} -> {"ok": true}
First line out is {"ready": true} once the model is loaded, or {"error": msg}.
"""
import json
import os
import sys
import traceback
from pathlib import Path

_out = sys.stdout
sys.stdout = sys.stderr          # anything torch or the model prints must not mix with the answers


def say(**kw):
    _out.write(json.dumps(kw) + "\n")
    _out.flush()


def main():
    ffmpeg = sys.argv[1] if len(sys.argv) > 1 else "ffmpeg"
    # appended, not prepended: in the packaged app this folder also holds the app's own compiled packages (numpy...) for
    # another Python version, and this environment's own copies must win
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    try:
        from voice_clone import engine
        cloner = engine.Cloner(ffmpeg)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        say(error=f"{type(exc).__name__}: {exc}")
        return
    torch = cloner.torch
    say(ready=True)
    sources, targets = {}, {}
    for line in sys.stdin:
        try:
            req = json.loads(line)
            if req["op"] == "embed":
                audio = engine.read_audio(req["wav"], ffmpeg)
                torch.save(cloner.embedding(audio).cpu(), req["out"])
            elif req["op"] == "convert":
                audio = engine.read_audio(req["src"], ffmpeg)
                job = req.get("job", "")
                if job not in sources:           # the narration's own voice, taken once from the first piece
                    sources[job] = cloner.embedding(audio[: int(engine.GOOD_SAMPLE_SEC * engine.SR)])
                if req["tgt"] not in targets:
                    targets[req["tgt"]] = torch.load(req["tgt"], map_location="cpu", weights_only=True)
                out = cloner.convert(audio, sources[job], targets[req["tgt"]], float(req.get("tau", engine.DEFAULT_TAU)))
                engine.write_mp3(out, req["dst"], ffmpeg)
            else:
                raise ValueError(f"unknown op {req.get('op')!r}")
            say(ok=True)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            say(error=f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    main()
