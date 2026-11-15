"""Voice a cartoon2d episode script: Edge voices per character, lines spoken together, songs on the beat, Rhubarb mouths.

python3 cartoon2d/voice.py <script.json> <out dir>
script.json = {"voices": {who: {"voice", "rate", "pitch"}}, "bpm": 104, "lead_in": 0.8, "gap": 0.45, "tail": 2.5,
               "lines": [{"who": "molly" | ["lily", "ollie"], "text": "...", "gap_after": 1.6, "chant": true, ...}]}
Writes timeline.json ({"total", "bpm", "lines": [{who, with, start, end, text, cues_by: {who: [{t0,t1,shape}]}, ...story fields}]}),
dialogue.wav (all voices placed), chapters.txt. Audio per (text, voice) is cached in <out>/cache, so edits re-voice only what changed.
"""
import asyncio
import hashlib
import json
import math
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import edge_tts
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kids_audio.chant import chant  # noqa: E402
from kids_audio.library import read_audio, write_wav  # noqa: E402
from kids_audio.synth import SR  # noqa: E402

RHUBARB = ROOT / "cartoon3d-engine" / "authoring" / "tools" / "Rhubarb-Lip-Sync-1.14.0-macOS" / "rhubarb"
PASS = ("act", "also", "cam", "card", "card_at", "pic", "sfx", "place", "hold", "drop", "give", "title", "endcard", "chapter",
        "word_cards", "chant", "go", "run", "game", "your_turn", "face", "hand", "fx", "tr")


def sig(*parts):
    return hashlib.sha1(json.dumps(parts).encode()).hexdigest()[:12]


async def speak(text, v, mp3):
    """Edge voice with word timings (needed for songs). Three tries: network hiccups happen on long scripts."""
    for attempt in range(3):
        try:
            words, audio = [], bytearray()
            com = edge_tts.Communicate(text, v["voice"], rate=v.get("rate", "+0%"), pitch=v.get("pitch", "+0Hz"), boundary="WordBoundary")
            async for ch in com.stream():
                if ch["type"] == "audio":
                    audio.extend(ch["data"])
                elif ch["type"] == "WordBoundary":
                    t0 = ch["offset"] / 1e7
                    words.append({"text": ch["text"], "t0": round(t0, 3), "t1": round(t0 + ch["duration"] / 1e7, 3)})
            if not audio:
                raise RuntimeError("no audio")
            mp3.write_bytes(bytes(audio))
            mp3.with_suffix(".words.json").write_text(json.dumps(words))
            return
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                raise RuntimeError(f"Edge voice failed for {text!r}: {e}")
            await asyncio.sleep(2.0)


async def speak_all(jobs, limit=6):
    sem = asyncio.Semaphore(limit)

    async def one(j):
        async with sem:
            if not (j["mp3"].exists() and j["mp3"].with_suffix(".words.json").exists()):
                await speak(j["text"], j["v"], j["mp3"])
    await asyncio.gather(*(one(j) for j in jobs))


# Edge voices arrive as 24 kHz / 48 kbps mp3: thin, a little boxy, hard "s" sounds. A gentle broadcast-style chain per clip:
# rumble cut, less boxiness, presence for clear words, de-essing, light compression so quiet words are not lost under the
# music, a soft high-shelf for air, and a short soft room so the voices sit in the playroom instead of floating dry on top.
VOICE_FX = ",".join([
    "aresample=48000:filter_size=64:cutoff=0.97",
    "highpass=f=85:poles=2",
    "equalizer=f=320:t=q:w=1.1:g=-2.5",
    "equalizer=f=2800:t=q:w=1.3:g=2.0",
    "highshelf=f=9000:g=2.5",
    "deesser=i=0.35:m=0.5:f=0.5",
    "acompressor=threshold=-21dB:ratio=2.6:attack=6:release=140:makeup=2.5:knee=4",
    "aecho=0.9:0.25:22|37:0.10|0.06",
    "alimiter=limit=0.89:attack=4:release=60",
])
FX_TAG = "fx2"                                   # bump when VOICE_FX changes: cached wavs are re-made, the mp3s are reused


def to_wav(mp3, wav):
    if not wav.exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3), "-af", VOICE_FX, "-ar", str(SR), "-ac", "1", str(wav)], check=True)


def mouths(wav, text, out_json):
    if not out_json.exists():
        subprocess.run([str(RHUBARB), "-f", "json", "--extendedShapes", "GHX", "--dialogFile", "/dev/stdin", "-o", str(out_json), str(wav)],
                       input=text.encode(), check=True, capture_output=True)
    return json.loads(out_json.read_text())["mouthCues"]


def main():
    script = json.loads(Path(sys.argv[1]).read_text())
    out = Path(sys.argv[2])
    cache = out / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    voices = script["voices"]
    bpm = float(script.get("bpm", 104))
    beat = 60.0 / bpm
    lines = script["lines"]
    # 1) every (line, speaker) voice, in parallel
    jobs = []
    for i, ln in enumerate(lines):
        whos = ln["who"] if isinstance(ln["who"], list) else [ln["who"]]
        ln["_whos"] = whos
        ln["_parts"] = []
        for w in whos:
            v = voices[w]
            key = sig(ln["text"], v)
            j = {"text": ln["text"], "v": v, "mp3": cache / f"{key}.mp3", "wav": cache / f"{key}_{FX_TAG}.wav", "key": key, "who": w}
            ln["_parts"].append(j)
            jobs.append(j)
    print("VOICING", len(jobs), "clips", flush=True)
    asyncio.run(speak_all(jobs))
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda j: to_wav(j["mp3"], j["wav"]), jobs))
    # 2) songs: each speaker's clip re-timed onto the beat grid
    for ln in lines:
        if not ln.get("chant"):
            continue
        for j in ln["_parts"]:
            words = json.loads(j["mp3"].with_suffix(".words.json").read_text())
            cw = cache / f"{j['key']}_chant{int(bpm)}.wav"
            res = chant({"voice": str(j["wav"]), "words": words, "text": ln["text"], "bpm": bpm, "out": str(cw)})
            j["wav"], j["chant"] = cw, res
    # 3) mouths for every clip, in parallel
    with ThreadPoolExecutor(6) as ex:
        cues = list(ex.map(lambda j: mouths(j["wav"], j["text"], j["wav"].with_suffix(".mouth.json")), jobs))
    for j, c in zip(jobs, cues):
        j["cues"] = c
    # 4) timeline
    t = float(script.get("lead_in", 0.8))
    timeline, chapters = [], []
    for i, ln in enumerate(lines):
        if ln.get("chant"):
            grid = 2 * beat                                   # songs start on a half bar of the bed (beds run from t = 0)
            t = math.ceil(t / grid - 1e-6) * grid
        durs = []
        for j in ln["_parts"]:
            durs.append(float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(j["wav"])])))
        d = max(durs)
        item = {"who": ln["_whos"][0], "with": ln["_whos"][1:], "start": round(t, 3), "end": round(t + d, 3), "text": ln["text"],
                "wavs": [str(j["wav"]) for j in ln["_parts"]],
                "cues_by": {j["who"]: [{"t0": round(t + c["start"], 3), "t1": round(t + c["end"], 3), "shape": c["value"]} for c in j["cues"]]
                            for j in ln["_parts"]}}
        for k in PASS:
            if k in ln:
                item[k] = ln[k]
        if ln.get("chant"):
            res = ln["_parts"][0]["chant"]
            item["beats"] = [round(t + k * res["beat"], 3) for k in range(res["beats"])]
            item["words"] = [{"text": w["text"], "t0": round(t + w["t0"], 3), "t1": round(t + w["t1"], 3)} for w in res["words"]]
        if ln.get("chapter"):
            chapters.append((t, ln["chapter"]))
        timeline.append(item)
        t += d + float(ln.get("gap_after", script.get("gap", 0.45)))
    total = t + float(script.get("tail", 2.5))
    (out / "timeline.json").write_text(json.dumps({"total": round(total, 3), "bpm": bpm, "lines": timeline}, indent=1))
    # 5) one dialogue track (together lines are summed a little quieter so they don't clip)
    N = int(total * SR) + SR
    mix = np.zeros((2, N))
    for it in timeline:
        g = 1.0 if len(it["wavs"]) == 1 else 0.8 / math.sqrt(len(it["wavs"]))
        for w in it["wavs"]:
            x = read_audio(w)
            i0 = int(it["start"] * SR)
            n = min(x.shape[1], N - i0)
            mix[:, i0:i0 + n] += x[:, :n] * g
    write_wav(str(out / "dialogue.wav"), mix[:, :int(total * SR)])
    (out / "chapters.txt").write_text("\n".join(f"{int(c // 60)}:{int(c % 60):02d} {name}" for c, name in chapters) + "\n")
    print("TOTAL", round(total, 2), "s =", f"{int(total // 60)}:{int(total % 60):02d}", "lines", len(timeline))


if __name__ == "__main__":
    main()
