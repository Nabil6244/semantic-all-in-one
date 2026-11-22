"""Voiceover + word timings for a stickman video.

Either a supplied voice file with its '<file>.words.json' (what the Voiceover tab writes),
or a fresh free Edge voice. Edge results are cached by script + voice, so a re-render
never fetches the same voice twice.
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "out" / "stickman" / "voice_cache"


def _duration(path):
    import subprocess
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True, timeout=120)
    return float(out.stdout.strip())


def from_file(audio, log=print):
    """Your own voice file. Word times come from '<file>.words.json' (the Voiceover tab writes it), else from a
    one-time local Whisper pass whose result is cached next to the stickman voice cache."""
    audio = Path(audio)
    wp = Path(str(audio) + ".words.json")
    if wp.is_file():
        words = json.loads(wp.read_text())
    else:
        st = audio.stat()
        key = hashlib.sha1(f"{audio.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:16]
        cached = CACHE / f"{key}.whisper.json"
        if cached.is_file():
            words = json.loads(cached.read_text())
        else:
            if log:
                log(f"stickman: finding word times in {audio.name} (local Whisper, once)")
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from kids_audio.lyric_align import transcribe
            words = [{"word": w["w"], "start": w["t0"], "end": w["t1"]} for w in transcribe(str(audio))]
            CACHE.mkdir(parents=True, exist_ok=True)
            cached.write_text(json.dumps(words))
    return {"path": str(audio), "duration": _duration(audio), "words": words}


def edge(text, voice="en-US-AndrewNeural", speed=1.0, log=print):
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import edge_voiceover
    key = hashlib.sha1(f"{voice}|{speed}|{text}".encode()).hexdigest()[:16]
    mp3 = CACHE / f"{key}.mp3"
    if not (mp3.is_file() and Path(str(mp3) + ".words.json").is_file()):
        CACHE.mkdir(parents=True, exist_ok=True)
        if log:
            log(f"stickman: fetching Edge voice {voice} ({len(text.split())} words)")
        tmp = CACHE / f"{key}.tmp.mp3"
        edge_voiceover.synthesize(text, str(tmp), voice=voice, speed=speed)
        shutil.move(str(tmp) + ".words.json", str(mp3) + ".words.json")
        shutil.move(str(tmp), str(mp3))
    return from_file(mp3, log=log)
