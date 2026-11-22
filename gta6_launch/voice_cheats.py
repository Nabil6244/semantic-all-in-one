"""Chatterbox voiceover for the cheats video with the saved 'gta voice' clone -> gta6_launch/cheats_voice.mp3."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from voice_clone import chatterbox_engine as cb, engine

ROOT = Path(__file__).resolve().parent
ref = engine.data_dir() / "voices" / "gta_voice" / "sample.wav"
text = (ROOT / "cheats_script.txt").read_text(encoding="utf-8").replace("X|S", "X and S").replace("“", "").replace("”", "")
t0 = time.time()
r = cb.synthesize(text, str(ROOT / "cheats_voice.mp3"), str(ref),
                  progress=lambda d, n: print(f"{d}/{n} pieces  {time.time() - t0:.0f}s", flush=True), keep_dir=str(ROOT / "work_cheats_voice"))
print("done", r.get("path"), r.get("duration"))
