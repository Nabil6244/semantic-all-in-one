"""The mood library: dark cinematic stock clips, built ONCE and reused by every Podcast Cut video.

Each clip is a free Pexels / Pixabay video, cut to its best 8 s (skipping the first second), filled to 1920x1080,
graded into the Podcast Cut look, silent, saved small (CRF 23). index.json lists them with their mood tag, source page
and author. Only the 8 s that are kept are read over the network (ffmpeg reads the remote file), never the whole file.

Folder: PODCAST_MOOD_DIR, else settings.json "podcast_mood_dir", else out/podcast_mood_library. Your own clips can be
dropped into <folder>/mine/<tag>/ (any .mp4/.mov): they are graded on first use and listed like the rest.

  python -m podcast_cut.library --per-tag 6          # build or top up (skips clips already there)
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from podcast_cut import look  # noqa: E402

CLIP_SECONDS = 8.0
# mood tag -> Pexels / Pixabay searches (dark, cinematic, no faces talking to camera)
MOODS: Dict[str, List[str]] = {
    "night_rain_street": ["rainy street at night", "rain city night neon reflections"],
    "city_aerial_night": ["city aerial night", "drone city lights night"],
    "skyline": ["city skyline night", "skyscrapers dusk"],
    "window_silhouette": ["man silhouette window", "person looking out window dark"],
    "lone_walker": ["man walking alone street", "lonely man walking night"],
    "forest_light": ["forest sunlight trees", "misty forest morning"],
    "ocean_dusk": ["ocean waves sunset", "dark ocean waves"],
    "mountain_mist": ["mountains fog", "mountain peak clouds"],
    "storm": ["storm clouds lightning", "dark storm sky"],
    "gym_dark": ["gym workout dark", "boxing training dark"],
    "running_dawn": ["man running sunrise", "runner silhouette"],
    "hands_close": ["hands close up dark", "man hands thinking"],
    "desk_night": ["working late night desk", "man laptop night dark"],
    "clock_time": ["clock ticking", "hourglass time"],
    "crowd_topdown": ["crowd top view", "people crossing street aerial"],
    "road_drive_night": ["driving at night road", "highway night timelapse"],
    "candle_fire": ["candle flame dark", "fire burning dark"],
    "sunset_field": ["sunset field silhouette", "golden hour field"],
    "train_window": ["train window view", "subway train night"],
    "empty_room": ["empty room light", "abandoned room window light"],
    "stairs_climb": ["man climbing stairs", "stairs walking up"],
    "cliff_edge": ["man standing cliff edge", "person mountain top"],
    "water_drops": ["water drops slow motion", "rain drops window"],
    "chess_think": ["chess pieces dark", "chess game close up"],
}
# words heard in a window -> the moods that fit it (first match wins; the rest rotate through GENERAL)
MOOD_WORDS = [
    ({"fear", "afraid", "scared", "panic", "anxiety", "anxious", "stress", "stressed", "danger", "threat", "trauma"},
     ["storm", "night_rain_street", "water_drops"]),
    ({"grief", "loss", "lost", "died", "death", "heartbreak", "breakup", "alone", "lonely", "sad", "sadness", "miss"},
     ["window_silhouette", "empty_room", "lone_walker", "train_window"]),
    ({"discipline", "work", "training", "effort", "hard", "harder", "push", "pushing", "endure", "suffering", "pain"},
     ["gym_dark", "running_dawn", "stairs_climb"]),
    ({"success", "goal", "goals", "milestone", "ambition", "future", "build", "career", "achieve", "win"},
     ["skyline", "city_aerial_night", "cliff_edge", "stairs_climb"]),
    ({"calm", "peace", "relax", "relaxed", "rest", "sleep", "breathe", "breathing", "quiet", "nature"},
     ["ocean_dusk", "forest_light", "mountain_mist", "sunset_field"]),
    ({"time", "years", "age", "old", "young", "past", "forever", "never"},
     ["clock_time", "road_drive_night", "sunset_field"]),
    ({"mind", "brain", "think", "thinking", "thoughts", "decide", "decision", "choice", "focus", "attention"},
     ["chess_think", "desk_night", "hands_close", "lone_walker"]),
    ({"people", "society", "everyone", "social", "media", "phone", "world", "others"},
     ["crowd_topdown", "city_aerial_night", "train_window"]),
    ({"energy", "fire", "passion", "drive", "motivation", "motivated", "dopamine", "adrenaline"},
     ["candle_fire", "running_dawn", "road_drive_night"]),
]
GENERAL = ["night_rain_street", "city_aerial_night", "lone_walker", "skyline", "forest_light", "ocean_dusk",
           "window_silhouette", "road_drive_night", "mountain_mist", "hands_close", "desk_night", "crowd_topdown"]
PRESENTS_TAGS = ["sunset_field", "skyline", "ocean_dusk"]


def library_dir() -> Path:
    env = os.environ.get("PODCAST_MOOD_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    try:
        d = json.loads((ROOT / "settings.json").read_text()).get("podcast_mood_dir", "")
        if d:
            return Path(d).expanduser()
    except Exception:
        pass
    return ROOT / "out" / "podcast_mood_library"


def load_index(folder: Optional[Path] = None) -> List[dict]:
    folder = Path(folder or library_dir())
    try:
        items = json.loads((folder / "index.json").read_text())
    except Exception:
        items = []
    items = [it for it in items if (folder / it["file"]).is_file() and (folder / it["file"]).stat().st_size >= 20000]
    mine = folder / "mine"
    if mine.is_dir():
        for p in sorted(mine.glob("*/*")):
            if p.suffix.lower() in (".mp4", ".mov", ".m4v", ".mkv"):
                items.append({"file": str(p.relative_to(folder)), "tag": p.parent.name, "provider": "mine", "graded": False,
                              "duration": 0.0})
    return items


def moods_for(text: str) -> List[str]:
    toks = {t.strip(".,!?;:'\"").lower() for t in text.split()}
    for words, tags in MOOD_WORDS:
        if toks & words:
            return tags
    return []


def _keys() -> Dict[str, str]:
    try:
        s = json.loads((ROOT / "settings.json").read_text())
    except Exception:
        s = {}
    return {"pexels": s.get("pexels_api_key") or os.environ.get("PEXELS_API_KEY", ""),
            "pixabay": s.get("pixabay_api_key") or os.environ.get("PIXABAY_API_KEY", "")}


def grab(url: str, dest: Path, start: float = 1.0, seconds: float = CLIP_SECONDS, w: int = look.W, h: int = look.H,
         graded: bool = True, timeout: float = 240) -> Path:
    """Read `seconds` of a remote (or local) video from `start`, fill/grade it, save it silent and small."""
    from providers.media_clip.ffmpeg_clip import _ffmpeg, _tls_opts
    vf = look.fit_filter(w, h) + ("," + look.GRADE if graded else "") + ",fps=25,format=yuv420p"
    tls = _tls_opts(url) if str(url).lower().startswith("https://") else []
    tmp = dest.with_name(dest.stem + "_part.mp4")
    cmd = [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *tls, "-ss", f"{start:.2f}", "-i", str(url),
           "-t", f"{seconds:.2f}", "-an", "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
           "-movflags", "+faststart", str(tmp)]
    subprocess.run(cmd, check=True, timeout=timeout, capture_output=True)
    if not usable(tmp):           # a seek past the end writes an empty file that has no video at all
        tmp.unlink(missing_ok=True)
        raise RuntimeError("the clip came out empty (shorter than the part asked for)")
    tmp.replace(dest)
    return dest


def usable(path: Path, min_seconds: float = 1.5) -> bool:
    """A real clip: has a video stream and lasts at least min_seconds."""
    try:
        from providers.media_clip.ffmpeg_clip import _ffprobe
        if Path(path).stat().st_size < 20000:
            return False
        out = subprocess.run([_ffprobe(), "-v", "error", "-select_streams", "v:0", "-show_entries", "format=duration",
                              "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=30).stdout.strip()
        return float(out or 0) >= min_seconds
    except Exception:
        return False


def build(per_tag: int = 6, folder: Optional[Path] = None, tags: Optional[List[str]] = None, log: Callable = print,
          cancel=None, min_free_gb: float = 1.0) -> int:
    """Top the library up to `per_tag` clips per mood. Returns how many were added. Stops before the disk gets full."""
    import shutil
    from providers.stock.pexels import PexelsBackend
    from providers.stock.pixabay import PixabayBackend
    folder = Path(folder or library_dir())
    folder.mkdir(parents=True, exist_ok=True)
    keys = _keys()
    backends = []
    if keys["pexels"]:
        backends.append(PexelsBackend(keys["pexels"]))
    if keys["pixabay"]:
        backends.append(PixabayBackend(keys["pixabay"]))
    if not backends:
        raise RuntimeError("No Pexels or Pixabay key in Settings, so the mood library can't be built.")
    try:
        index = json.loads((folder / "index.json").read_text())
    except Exception:
        index = []
    have_ids = {(it.get("provider"), str(it.get("id"))) for it in index}
    added = 0
    for tag in (tags or list(MOODS)):
        n_have = sum(1 for it in index if it["tag"] == tag and (folder / it["file"]).is_file())
        if n_have >= per_tag:
            continue
        cands = []
        for q in MOODS[tag]:
            for be in backends:
                try:
                    cands += [(be.name, q, c) for c in be.search(q, media_type="video", per_page=10)]
                except Exception as exc:
                    log(f"  {be.name} search '{q}' failed: {exc}")
        random.Random(tag).shuffle(cands)
        cands.sort(key=lambda x: 0 if (x[2].duration or 0) >= CLIP_SECONDS + 2 and x[2].width >= 1280 else 1)
        for prov, q, c in cands:
            if n_have >= per_tag:
                break
            if cancel and cancel():
                return added
            if (prov, str(c.asset_id)) in have_ids or (c.width and c.height and c.width < c.height):
                continue
            if shutil.disk_usage(folder).free < min_free_gb * 1e9:
                log(f"Stopped: less than {min_free_gb:g} GB free on the disk.")
                (folder / "index.json").write_text(json.dumps(index, indent=1))
                return added
            dur = float(c.duration or 0)
            start = 1.0 if dur < CLIP_SECONDS + 4 else min(dur * 0.25, dur - CLIP_SECONDS - 1)
            safe_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(c.asset_id))     # "pixabay:123" -> "pixabay_123" (no colons in names)
            dest = folder / tag / f"{tag}_{prov}_{safe_id}.mp4"
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                grab(c.url, dest, start=start, seconds=min(CLIP_SECONDS, max(3.0, dur - start - 0.2)) if dur else CLIP_SECONDS)
            except Exception as exc:
                log(f"  skipped {prov} {c.asset_id}: {str(exc)[-120:]}")
                continue
            index.append({"file": str(dest.relative_to(folder)), "tag": tag, "provider": prov, "id": str(c.asset_id),
                          "query": q, "author": c.author, "source_url": c.source_url, "graded": True,
                          "duration": min(CLIP_SECONDS, dur - start) if dur else CLIP_SECONDS})
            have_ids.add((prov, str(c.asset_id)))
            n_have += 1
            added += 1
            log(f"  + {tag} ({n_have}/{per_tag}) {prov} {c.asset_id}")
        (folder / "index.json").write_text(json.dumps(index, indent=1))
    (folder / "index.json").write_text(json.dumps(index, indent=1))
    return added


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build / top up the Podcast Cut mood library (free stock, made once).")
    ap.add_argument("--per-tag", type=int, default=6)
    ap.add_argument("--tags", nargs="*")
    ap.add_argument("--folder")
    a = ap.parse_args(argv)
    n = build(per_tag=a.per_tag, folder=Path(a.folder) if a.folder else None, tags=a.tags)
    print(f"Added {n} clip(s); the library has {len(load_index(Path(a.folder) if a.folder else None))}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
