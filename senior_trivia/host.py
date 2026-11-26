"""The quiz host, Hal: a friendly American man of about 67 in his living room. He appears only in his own Flow talking
clips (5-6 per show), never as a still picture (owner rule). His pack lives in out/senior_trivia/hosts/<name>/:
  portrait.png  waist-up reference (face + clothes)   set.png  him in his armchair set   host.json  overrides
The pack pictures are made once by Flow (free pictures) the first time a show needs his clips.
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOSTS = ROOT / "out" / "senior_trivia" / "hosts"

HAL = {
    "name": "Hal",
    "voice": "Achird",   # Flow (Gemini) voice, "friendly"; the same in every clip. Change in host.json.
    "voice_performance": "warm, friendly American grandfather in his late sixties, relaxed and kind, a gentle smile in the voice",
    "tagline": "your quiz host",
    "look": ("Hal, a friendly American man about 67 years old, neat short white hair, clean-shaven, warm smile lines, "
             "light-blue eyes behind thin wire-rimmed glasses, wearing a soft oatmeal-coloured cardigan over a light-blue "
             "button-down shirt, tan chinos"),
    "set": ("sitting in a brown leather armchair in a cozy American living room: warm table lamp, wooden bookshelf with "
            "framed family photos, a vintage radio cabinet, soft late-afternoon window light"),
}


def load(name="hal"):
    d = HOSTS / name.lower()
    meta = dict(HAL)
    jf = d / "host.json"
    if jf.is_file():
        meta.update(json.loads(jf.read_text(encoding="utf-8")))
    meta["dir"] = str(d)
    meta["portrait"] = str(d / "portrait.png") if (d / "portrait.png").is_file() else None
    meta["set_image"] = str(d / "set.png") if (d / "set.png").is_file() else None
    return meta


def pack_jobs(meta):
    """Flow picture jobs for a missing pack: {library key: prompt}."""
    jobs = {}
    if not meta.get("portrait"):
        jobs["st_host_portrait_" + meta["name"].lower()] = (
            f"Photorealistic waist-up portrait of {meta['look']}, facing the camera with a kind smile, plain warm-grey studio "
            "background, soft key light, sharp focus, no text")
    if not meta.get("set_image"):
        jobs["st_host_set_" + meta["name"].lower()] = (
            f"Photorealistic medium shot of {meta['look']}, {meta['set']}, looking at the camera, 16:9, no text")
    return jobs


def save_pack(meta, made):
    """Copy the Flow pictures into the pack folder; -> the reloaded meta."""
    d = Path(meta["dir"])
    d.mkdir(parents=True, exist_ok=True)
    for key, path in made.items():
        if path and key.startswith("st_host_portrait_"):
            shutil.copyfile(path, d / "portrait.png")
        elif path and key.startswith("st_host_set_"):
            shutil.copyfile(path, d / "set.png")
    return load(meta["name"])
