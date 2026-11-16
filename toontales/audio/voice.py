"""Toon Tales voice: one spoken line -> wav + Rhubarb mouth cues (A-H, X), cached by text+voice.

Run: python3 toontales/audio/voice.py "<text>" <voice> <rate> <out dir>
Library: voice.speak(who, text, out_dir) uses the character's fixed voice from cast.json;
         voice.line(text, voice, rate, out_dir) -> {"wav", "dur", "cues": [{t0, t1, shape}]}
Edge TTS needs the network; Rhubarb is the copy already used by cartoon3d-engine.
"""
import asyncio
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RHUBARB = ROOT / "cartoon3d-engine" / "authoring" / "tools" / "Rhubarb-Lip-Sync-1.14.0-macOS" / "rhubarb"


def _dur(path):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", str(path)]))


def _tts(text, voice, rate, pitch, mp3, tries=8):
    """Edge TTS sometimes drops a request; retry with a short back-off before giving up."""
    import time

    import edge_tts
    for k in range(tries):
        try:
            asyncio.run(edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(str(mp3)))
            if Path(mp3).exists() and Path(mp3).stat().st_size > 0:
                return
        except Exception as e:  # NoAudioReceived, connection resets
            if k == tries - 1:
                raise RuntimeError(f"Edge TTS failed for {voice}: {text[:60]!r}") from e
        time.sleep(min(20.0, 2.0 * (k + 1) ** 1.5))


def line(text, voice, rate="+10%", out_dir=".", pitch="+0Hz"):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{voice}|{rate}|{pitch}|{text}".encode()).hexdigest()[:12]
    wav, cues_p = out / f"line_{key}.wav", out / f"line_{key}.json"
    if not wav.exists():
        mp3 = out / f"line_{key}.mp3"
        _tts(text, voice, rate, pitch, mp3)
        # trim the TTS lead/tail silence so cuts land on speech
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3), "-af",
                        "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                        "silenceremove=start_periods=1:start_threshold=-45dB,areverse",
                        "-ar", "44100", "-ac", "1", str(wav)], check=True)
        mp3.unlink(missing_ok=True)
    if not cues_p.exists():
        subprocess.run([str(RHUBARB), "-f", "json", "--extendedShapes", "GHX", "--dialogFile", "/dev/stdin",
                        "-o", str(cues_p), str(wav)], input=text.encode(), check=True, capture_output=True)
    mc = json.loads(cues_p.read_text())["mouthCues"]
    return {"wav": str(wav), "dur": round(_dur(wav), 3), "text": text,
            "cues": [{"t0": c["start"], "t1": c["end"], "shape": c["value"]} for c in mc]}


CAST = ROOT / "toontales" / "cast" / "cast.json"


def _lead_silence(mp3, db=-45):
    """Seconds of silence at the start (the same threshold line() trims), so word times match the wav."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(mp3), "-af", f"silencedetect=noise={db}dB:d=0.01",
                        "-f", "null", "-"], capture_output=True, text=True)
    starts = [float(x.split("silence_start:")[1].split()[0]) for x in r.stderr.splitlines() if "silence_start:" in x]
    ends = [float(x.split("silence_end:")[1].split()[0]) for x in r.stderr.splitlines() if "silence_end:" in x]
    if starts and ends and starts[0] <= 0.02:
        return ends[0]
    return 0.0


def words(text, voice, rate="+0%", out_dir=".", pitch="+0Hz", dur=None, tries=8):
    """Word timings for a line [{w, t0, t1}] (seconds in the trimmed wav), from Edge word boundaries. Cached."""
    import time

    import edge_tts
    out = Path(out_dir)
    key = hashlib.sha1(f"{voice}|{rate}|{pitch}|{text}".encode()).hexdigest()[:12]
    p = out / f"line_{key}.words.json"
    if p.exists():
        return json.loads(p.read_text())
    mp3 = out / f"words_{key}.mp3"

    async def go():
        c = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
        ws = []
        with open(mp3, "wb") as f:
            async for m in c.stream():
                if m["type"] == "audio":
                    f.write(m["data"])
                elif m["type"] == "WordBoundary":
                    ws.append((m["text"], m["offset"] / 1e7, m["duration"] / 1e7))
        return ws

    for k in range(tries):
        try:
            ws = asyncio.run(go())
            if ws:
                break
        except Exception as e:
            if k == tries - 1:
                raise RuntimeError(f"Edge word timing failed: {text[:60]!r}") from e
        time.sleep(min(20.0, 2.0 * (k + 1) ** 1.5))
    lead = _lead_silence(mp3)
    mp3.unlink(missing_ok=True)
    res = []
    for w, t0, d in ws:
        a = max(0.0, t0 - lead)
        b = a + d
        if dur:
            a, b = min(a, dur), min(b, dur)
        res.append({"w": w, "t0": round(a, 3), "t1": round(b, 3)})
    p.write_text(json.dumps(res))
    return res


def _cast_path(p):
    import os
    return Path(p or os.environ.get("TT_CAST") or CAST)


def speak(who, text, out_dir, cast_path=None):
    """Line in the character's own fixed voice from the cast file (the channel's, or cast.json)."""
    data = json.loads(_cast_path(cast_path).read_text())
    cast = {c["id"]: c for c in data["characters"]}
    v = data["narrator"]["voice"] if who == "narrator" else cast[who]["voice"]
    return line(text, v["name"], v.get("rate", "+0%"), out_dir, v.get("pitch", "+0Hz"))


def speak_words(who, text, out_dir, dur=None, cast_path=None):
    data = json.loads(_cast_path(cast_path).read_text())
    cast = {c["id"]: c for c in data["characters"]}
    v = data["narrator"]["voice"] if who == "narrator" else cast[who]["voice"]
    return words(text, v["name"], v.get("rate", "+0%"), out_dir, v.get("pitch", "+0Hz"), dur=dur)


def shape_at(cues, t):
    for c in cues:
        if c["t0"] <= t < c["t1"]:
            return c["shape"]
    return "X"


if __name__ == "__main__":
    r = line(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
    print(json.dumps({k: r[k] for k in ("wav", "dur")}), len(r["cues"]), "cues")
