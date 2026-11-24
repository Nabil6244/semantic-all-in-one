"""The voiceover: your own file (+ its .words.json or a local Whisper pass), or the free Edge voice made one sentence at a
time (Edge refuses some multi-sentence pieces: 'No audio was received', 2026-11-20) in parallel, cached per sentence,
then joined into one track with word times shifted to their place."""
import hashlib
import json
import re
import subprocess
import time
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "out" / "prepper_host" / "voice_cache"
GAP = 0.12   # seconds of air between two sentences


def _duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True, timeout=120)
    return float(out.stdout.strip())


def from_file(audio, log=print):
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from stickman import voice as sv
    return sv.from_file(audio, log=log)


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", str(text or "").strip()) if s.strip()]


def _one(sentence, voice, speed):
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import edge_voiceover
    key = hashlib.sha1(f"{voice}|{speed}|{sentence}".encode()).hexdigest()[:16]
    mp3 = CACHE / f"{key}.mp3"
    wj = Path(str(mp3) + ".words.json")
    if mp3.is_file() and wj.is_file():
        return mp3
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = CACHE / f"{key}.tmp.mp3"
    last = None
    for _ in range(3):
        try:
            edge_voiceover.synthesize(sentence, str(tmp), voice=voice, speed=speed)
            Path(str(tmp) + ".words.json").replace(wj)
            tmp.replace(mp3)
            return mp3
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"Edge could not read: \"{sentence[:80]}\" ({last})")


def _one_in_halves(sentence, voice, speed):
    """Edge refuses some exact sentences but reads their halves (2026-11-23: '...handles flour at the plant.'): read the
    sentence in two pieces split at the comma nearest the middle (else the middle word) and join them, same words."""
    words = sentence.split()
    if len(words) < 4:
        raise RuntimeError("too short to split")
    mid = len(words) // 2
    commas = [i + 1 for i, w in enumerate(words[:-1]) if w.endswith((",", ";", ":"))]
    cut = min(commas, key=lambda i: abs(i - mid)) if commas else mid
    a, b = " ".join(words[:cut]), " ".join(words[cut:])
    key = hashlib.sha1(f"{voice}|{speed}|halves|{sentence}".encode()).hexdigest()[:16]
    mp3 = CACHE / f"{key}.mp3"
    wj = Path(str(mp3) + ".words.json")
    if mp3.is_file() and wj.is_file():
        return mp3
    pa, pb = _one(a, voice, speed), _one(b, voice, speed)
    d0 = _duration(pa)
    lst = CACHE / f"{key}.txt"
    lst.write_text(f"file '{pa}'\nfile '{pb}'\n")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c:a", "libmp3lame", "-b:a", "96k", str(mp3)],
                   check=True, timeout=300)
    w = json.loads(Path(str(pa) + ".words.json").read_text())
    w += [{"word": x["word"], "start": round(x["start"] + d0, 4), "end": round(x["end"] + d0, 4)}
          for x in json.loads(Path(str(pb) + ".words.json").read_text())]
    wj.write_text(json.dumps(w))
    return mp3


def edge(text, voice="en-US-AndrewNeural", speed=1.0, log=print, workers=6):
    parts = sentences(text)
    if not parts:
        raise ValueError("no narration to voice")
    key = hashlib.sha1(f"{voice}|{speed}|{'|'.join(parts)}".encode()).hexdigest()[:16]
    out = CACHE / f"full_{key}.wav"
    wj = Path(str(out) + ".words.json")
    if out.is_file() and wj.is_file():
        return {"path": str(out), "duration": _duration(out), "words": json.loads(wj.read_text())}
    log(f"prepper host: Edge voice {voice}, {len(parts)} sentences")

    def safe(s):
        try:
            return _one(s, voice, speed)
        except Exception as e:  # noqa: BLE001 - tried again below, one at a time
            return e

    with ThreadPoolExecutor(max_workers=workers) as ex:
        mp3s = list(ex.map(safe, parts))
    # A sentence Edge refused ("No audio was received", 2026-11-23: one plain sentence stopped a whole video) usually
    # means it is throttling a burst: wait, then try the refused ones one at a time; last of all at a hair's different
    # speed, which Edge treats as a new request (the timing difference is too small to hear).
    for round_, pause in enumerate((15, 30, 60)):
        bad = [i for i, m in enumerate(mp3s) if isinstance(m, Exception)]
        if not bad:
            break
        log(f"prepper host: Edge refused {len(bad)} sentence(s); waiting {pause} s, then one at a time")
        time.sleep(pause)
        for i in bad:
            sp = speed if round_ < 2 else round(speed * 0.99, 3)
            try:
                mp3s[i] = _one(parts[i], voice, sp)
            except Exception as e:  # noqa: BLE001
                mp3s[i] = e
    for i, m in enumerate(mp3s):          # still refused: read it in two halves
        if isinstance(m, Exception):
            try:
                mp3s[i] = _one_in_halves(parts[i], voice, speed)
                log(f"prepper host: Edge read this sentence in two halves: {parts[i][:60]}")
            except Exception as e:  # noqa: BLE001
                mp3s[i] = e
    bad = [parts[i][:70] for i, m in enumerate(mp3s) if isinstance(m, Exception)]
    if bad:
        raise RuntimeError(f"Edge could not read {len(bad)} sentence(s) after waiting and retrying: " + " | ".join(bad))
    words, t = [], 0.0
    lst = CACHE / f"full_{key}.txt"
    sil = CACHE / "gap.wav"
    if not sil.is_file():
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(GAP), "-c:a", "pcm_s16le", str(sil)], check=True)
    lines = []
    for m in mp3s:
        wav = m.with_suffix(".wav")
        if not wav.is_file():
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(m), "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(wav)], check=True, timeout=300)
        d = _duration(wav)
        for w in json.loads(Path(str(m) + ".words.json").read_text()):
            words.append({"word": w["word"], "start": round(w["start"] + t, 4), "end": round(w["end"] + t, 4)})
        lines += [f"file '{wav}'", f"file '{sil}'"]
        t += d + GAP
    lst.write_text("\n".join(lines) + "\n")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-ac", "1", "-ar", "24000", str(out)],
                   check=True, timeout=1800)
    wj.write_text(json.dumps(words))
    real = _duration(out)
    if words and abs(real - t) > 0.5:   # mp3 padding drift: scale the times to the real track
        k = real / t
        for w in words:
            w["start"], w["end"] = round(w["start"] * k, 4), round(w["end"] * k, 4)
        wj.write_text(json.dumps(words))
    return {"path": str(out), "duration": real, "words": words}
