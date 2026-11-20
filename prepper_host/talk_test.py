"""Talking-head test: one Flow video (Ingredients mode) of Dale in the talking set, made from his reference pictures,
saying one line so Veo moves the lips with the words. Uses Flow video credits (one clip).
Usage: python prepper_host/talk_test.py
"""
import json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT.parent
sys.path.insert(0, str(APP))
from providers.flow.engine_manager import FlowEngineManager  # noqa: E402

OUT = ROOT / "out" / "talk" / time.strftime("run_%H%M%S")
m = json.loads((ROOT / "out" / "manifest.json").read_text())
import shutil  # noqa: E402
_refdir = ROOT / "out" / "refs"
_refdir.mkdir(parents=True, exist_ok=True)
REFS = []
for key in ("portrait_1", "set_talking"):   # unique file names: Flow's picker finds references by name
    dst = _refdir / f"dale_{key}.png"
    shutil.copyfile(m[key], dst)
    REFS.append(str(dst))
LINE = "Ninety days without power. Most families won't last ninety hours. So here's the one cart I'd load first."
PROMPT = ("Photorealistic video, static medium shot on a tripod. The man from the reference pictures (short grey hair, short "
          "salt-and-pepper beard, olive-green canvas work jacket over a red-and-black flannel shirt) sits on a wooden stool in "
          "his barn-wood home workshop with shelves of mason jars, canned food and water jugs, warm tungsten light. He looks "
          f"straight into the camera and talks calmly with small natural hand gestures. He says: \"{LINE}\" "
          "Deep, warm, slightly gravelly American male voice, no music, quiet room tone. No text, no subtitles, no logos.")

s = json.loads((APP / "settings.json").read_text())
prof = next(p for p in s["video_profiles"] if p["id"] == s.get("default_video_profile_id", "default"))
OUT.mkdir(parents=True, exist_ok=True)
settings = {"mediaKind": "video", "videoModel": prof["model"], "aspectRatio": prof["aspectRatio"],
            "videoDuration": int(prof["duration"]), "videoResolution": prof["resolution"], "imageCount": 1,
            "autoDownload": True, "outputDir": str(OUT), "folder": "prepper_host", "generationMode": "ui",
            "referenceImages": REFS}
print("profile", {k: prof.get(k) for k in ("model", "aspectRatio", "duration", "resolution")}, flush=True)
c = FlowEngineManager(log=lambda m_: None).ensure_running()
time.sleep(1.5)
events = []
c.subscribe(lambda e: events.append(e) or (e.get("type") in ("PROMPT_RESULT", "GENERATE_DONE") or e.get("generateError"))
            and print(json.dumps({k: str(e.get(k))[:300] for k in ("type", "status", "error", "path", "generateError")}), flush=True))
c.generate([PROMPT], settings, prof["account_ids"], prompt_keys=["prepper_host_talk_1"])
c.wait_for(lambda e: e.get("type") == "GENERATE_DONE" or bool(e.get("generateError")), timeout=1500)
mp4s = sorted(OUT.rglob("*.mp4"))
print("RESULT", json.dumps([str(p) for p in mp4s]), flush=True)
c.close()
