"""Word timings for a voice-over, produced the way the application produces them (faster-whisper, word_timestamps=True, vad_filter=True,
CPU int8, audio decoded by ffmpeg to 16 kHz mono first: see video_generator._transcribe_locked). Runs OFFLINE: the model must already be in the
local Hugging Face cache (HF_HUB_OFFLINE=1 is set so nothing is downloaded).

usage: python3 -B -I transcribe_words.py <audio> <out.json> [model_size, default base]

Writes both forms of the words:
  raw_words        [text with punctuation as Whisper wrote it, start, end]
  app_style_words [normalised token, start, end]: lower case, punctuation removed, one entry per token. An approximation of the application's
                   split_words (that function lives in video_generator.py, which this script does not import)."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

os.environ["HF_HUB_OFFLINE"] = "1"
audio, out = Path(sys.argv[1]), Path(sys.argv[2])
size = sys.argv[3] if len(sys.argv) > 3 else "base"
import numpy as np
from faster_whisper import WhisperModel

pcm = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(audio), "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True, check=True, timeout=1800).stdout
x = np.frombuffer(pcm, np.float32).copy()
model = WhisperModel(size, device="cpu", compute_type="int8", cpu_threads=4, num_workers=1)
segments, info = model.transcribe(x, word_timestamps=True, vad_filter=True)
raw, app = [], []
for seg in segments:
    for w in seg.words or []:
        raw.append([w.word.strip(), round(float(w.start), 3), round(float(w.end), 3)])
        for tok in re.findall(r"[a-z0-9']+", w.word.lower().replace("-", " ")):
            app.append([tok.strip("'"), round(float(w.start), 3), round(float(w.end), 3)])
app = [a for a in app if a[0]]
out.write_text(json.dumps({"audio": str(audio), "model": size, "duration_s": round(len(x) / 16000, 3), "language": info.language, "raw_words": raw, "app_style_words": app}, indent=1))
print(f"{len(raw)} words ({len(app)} app-style tokens) over {len(x) / 16000:.1f} s -> {out}")
