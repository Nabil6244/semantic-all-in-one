"""One Flow video: the alligator walking into a convenience store (the voice line the trailers have no shot for)."""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from providers.flow.client import FlowClient

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "footage/flow"
PROMPT = ("Photorealistic modern open-world video game graphics, sunny Florida strip mall in the afternoon. A large alligator "
          "slowly walks through the open glass doors into a brightly lit convenience store, past snack shelves, while a startled "
          "clerk behind the counter steps back. Handheld smartphone footage feel, warm sunlight, palm trees outside the window, "
          "cinematic, no text, no logos, no watermark.")
s = json.loads((ROOT.parent / "settings.json").read_text())
prof = next(p for p in s["video_profiles"] if p["id"] == s.get("default_video_profile_id", "default"))
settings = {"mediaKind": "video", "videoModel": prof["model"], "aspectRatio": prof["aspectRatio"],
            "videoDuration": int(prof["duration"]), "videoResolution": prof["resolution"], "imageCount": 1,
            "autoDownload": True, "outputDir": str(OUT), "folder": "gator", "generationMode": "ui" if s.get("flow_ui_mode") else "rpc"}
c = FlowClient("ws://127.0.0.1:8787/ws", log=lambda m: None)
c.connect()
time.sleep(1.5)
st = c.get_state()
busy = any(st.get(k) for k in ("isRunning", "running", "generating", "isGenerating"))
print("engine state keys:", sorted(st)[:12], "busy:", busy, flush=True)
if busy:
    print("Flow engine is busy with another run - not sending."); sys.exit(3)
events = []
c.subscribe(lambda m: events.append(m) or (m.get("type") in ("PROMPT_RESULT", "GENERATE_DONE") or m.get("generateError"))
            and print(json.dumps({k: str(m.get(k))[:200] for k in ("type", "status", "message", "path", "generateError")}), flush=True))
c.generate([PROMPT], settings, prof["account_ids"], prompt_keys=["gta6_gator"])
done = c.wait_for(lambda m: m.get("type") == "GENERATE_DONE" or bool(m.get("generateError")), timeout=1200)
mp4s = sorted(OUT.rglob("*.mp4"), key=lambda p: p.stat().st_mtime)
print("RESULT", json.dumps({"done": done.get("type"), "mp4s": [str(p) for p in mp4s]}), flush=True)
c.close()
