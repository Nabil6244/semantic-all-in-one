"""Sung track for the paint-board test: Edge child voice -> kids_audio.sing onto the timeline melody -> one voice wav,
then kids_audio.mixer adds the sunny bed and the sound effects.

python3 -m toycolors.song OUT_DIR   -> OUT_DIR/mix.wav
"""
import json
import os
import subprocess
import sys

import numpy as np

from kids_audio import library as L
from kids_audio.mixer import mix
from kids_audio.sing import sing
from kids_audio.synth import SR
from toycolors import timeline as T

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOICE = "en-US-AnaNeural"            # Edge child voice


def build(out):
    os.makedirs(out, exist_ok=True)
    L.build()
    lines = T.song_lines()
    job = {"voice": VOICE, "rate": "-5%",
           "lines": [{"text": text, "out": os.path.join(out, f"line{i}.mp3")} for i, (_, text, _) in enumerate(lines)]}
    jp = os.path.join(out, "tts.json")
    json.dump(job, open(jp, "w"))
    subprocess.run([sys.executable, os.path.join(ROOT, "cartoon3d-engine/tools/tts_words.py"), jp], check=True)

    track = np.zeros((2, int(T.DURATION * SR)))
    transpose = None
    for i, (t0, text, tune) in enumerate(lines):
        mp3 = job["lines"][i]["out"]
        words = json.load(open(mp3 + ".words.json"))
        if len(words) != len(tune):
            raise RuntimeError(f"{text!r}: voice gave {len(words)} words, tune has {len(tune)}")
        r = sing({"voice": mp3, "words": words, "tune": tune, "bpm": T.BPM,
                  "out": os.path.join(out, f"sung{i}.wav"), "transpose": transpose})
        transpose = r["transpose"]               # one key for the whole song
        y = L.read_audio(r["file"])
        a = int(t0 * SR)
        n = min(y.shape[1], track.shape[1] - a)
        track[:, a:a + n] += y[:, :n]
    # bring the sung voice to -14 LUFS, the level the mixer expects
    g = 10 ** ((-14.0 - L.lufs(track)) / 20)
    voice = os.path.join(out, "voice.wav")
    L.write_wav(voice, np.clip(track * g, -1, 1))

    rep = mix({"voice": voice, "out": os.path.join(out, "mix.wav"), "duration": T.DURATION,
               "music": {"bed": "sunny", "gap_db": -9, "duck_db": -6, "fade_in": 0.5, "fade_out": 1.5},
               "sfx": T.sfx(), "voice_lufs": -14, "target_lufs": -14})
    print(json.dumps(rep, indent=1)[:600])
    return os.path.join(out, "mix.wav")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "toycolors/out/audio"))
