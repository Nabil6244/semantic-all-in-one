"""Voices + lip-sync cues for a playland scene: Edge TTS per line, Rhubarb mouth shapes, one timeline json.
Run: python3 sets/scene_audio.py <scene.json> <out dir>
scene.json = {"gap": 0.35, "lines": [{"who": "host", "text": "...", "voice": "...", "rate": "+0%", "pitch": "+0Hz"}, ...]}
Out: line{i}.wav, line{i}.json (Rhubarb), timeline.json [{who, start, end, wav, cues:[{t0,t1,shape}]}], mix.wav
"""
import asyncio
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import edge_tts

RHUBARB = Path(__file__).resolve().parent.parent / "tools" / "Rhubarb-Lip-Sync-1.14.0-macOS" / "rhubarb"
scene = json.loads(Path(sys.argv[1]).read_text())
out = Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)


async def tts(text, voice, rate, pitch, mp3):
    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(str(mp3))


def dur(path):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]))


t = scene.get("lead_in", 0.6)
timeline = []
for i, ln in enumerate(scene["lines"]):
    sig = hashlib.sha1(json.dumps([ln["text"], ln["voice"], ln.get("rate", "+0%"), ln.get("pitch", "+0Hz")]).encode()).hexdigest()[:10]
    mp3, wav, cues = out / f"line{i}_{sig}.mp3", out / f"line{i}_{sig}.wav", out / f"line{i}_{sig}.json"   # cache follows the words + voice
    if not wav.exists():
        asyncio.run(tts(ln["text"], ln["voice"], ln.get("rate", "+0%"), ln.get("pitch", "+0Hz"), mp3))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3), "-ar", "44100", "-ac", "1", str(wav)], check=True)
    if not cues.exists():
        subprocess.run([str(RHUBARB), "-f", "json", "--extendedShapes", "GHX", "--dialogFile", "/dev/stdin", "-o", str(cues), str(wav)],
                       input=ln["text"].encode(), check=True, capture_output=True)
    d = dur(wav)
    mc = json.loads(cues.read_text())["mouthCues"]
    timeline.append({"who": ln["who"], "start": round(t, 3), "end": round(t + d, 3), "wav": str(wav), "text": ln["text"],
                     "cues": [{"t0": round(t + c["start"], 3), "t1": round(t + c["end"], 3), "shape": c["value"]} for c in mc],
                     **{k: ln[k] for k in ("act", "also", "cam", "card", "card_at", "pic", "sfx") if k in ln}})   # story directions ride along
    print("LINE", i, ln["who"], round(t, 2), "->", round(t + d, 2), len(mc), "cues")
    t += d + ln.get("gap_after", scene.get("gap", 0.35))
total = t + scene.get("tail", 1.2)
(out / "timeline.json").write_text(json.dumps({"total": round(total, 3), "lines": timeline}, indent=1))
# one mixed dialogue track
inputs, filt = [], []
for i, ln in enumerate(timeline):
    inputs += ["-i", ln["wav"]]
    filt.append(f"[{i}]adelay={int(ln['start'] * 1000)}:all=1[a{i}]")
filt.append("".join(f"[a{i}]" for i in range(len(timeline))) + f"amix=inputs={len(timeline)}:normalize=0,apad,atrim=0:{total:.3f}[m]")
subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filt), "-map", "[m]", "-ar", "44100", str(out / "mix.wav")], check=True)
print("TOTAL", round(total, 2))
