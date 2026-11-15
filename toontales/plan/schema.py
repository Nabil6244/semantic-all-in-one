"""Toon Tales story plan: format, vocabulary and shot-length estimates (pure Python, no Blender).

A story plan (toontales/stories/<id>/plan.json) is written by the toon-tales skill (Claude), never Gemini:

{
  "id": "snake_oil", "title": "How Snake Oil Salesmen Worked", "topic": "snake oil medicine shows",
  "cast": ["walt", "pip"],
  "hook_title": "HE NEVER DUG FOR GOLD",        <- 2-7 words, big card over the first shot
  "keywords": ["shovel", "millionaire"],         <- extra caption words to pop in yellow (numbers/$ are automatic)
  "places": {"store": "Inside a small 1848 general store: shelves of picks, pans and shovels, ..."},
                                       <- each place is painted once by Flow; a shot's set is a place name
  "shots": [
    {"id": "s01", "beat": "hook", "speaker": "narrator", "text": "One sentence of the script.",
     "set": "mine", "camera": "medium", "move": "push",
     "cast": [{"id": "walt", "mark": "A", "acts": [{"do": "point", "at": 0.3, "params": {}}],
               "eyes": "money", "mouth": null}],
     "props": [{"type": "sign", "text": "SURE THING MINE", "spot": "wall_r"}],
     "overlay": {"type": "chalk", "text": "10 FT"}, "sfx": [{"name": "coins", "at": 0.5}],
     "transition": "cut", "time_jump": false, "offscreen": false,
     "freeze": "WAIT...",            <- optional: hold the last frame 0.65 s with this card (pattern break)
     "punch": true, "mood": "sneaky",  <- optional: punch-in zoom; music mood (upbeat|sneaky|sad), else by beat
     "dur": 2.4}                       <- filled from the real voice later; estimated before that
  ]
}
"""
import json
import re
from pathlib import Path

TT = Path(__file__).resolve().parents[1]
CAST_FILE = TT / "cast" / "cast.json"
KITS_FILE = TT / "sets" / "kits.json"
STORIES = TT / "stories"

BEATS = ["hook", "concept", "setup", "deadline", "obstacle", "con", "escalate", "twist", "payoff"]
CAMERAS = ["wide", "medium", "two_shot", "close", "insert", "low", "high", "pov", "over_shoulder"]
MOVES = ["push", "pull", "pan_l", "pan_r", "tilt_up", "tilt_down", "orbit_l", "orbit_r", "crash_zoom", "drift"]
TRANSITIONS = ["cut", "dissolve", "whip"]
PROP_TYPES = {  # type: needs text
    "sign": True, "newspaper": True, "board": True, "label": True, "letter": True, "bottle": True,
    "sack": False, "coins": False, "gold": False, "money": False, "box": False, "tool": False,
    "gun": False, "dynamite": False, "map": True, "rock": False,
}
OVERLAYS = ["chalk", "arrow", "circle", "stamp", "label", "cross"]
SFX = ["pick", "gunshot", "splash", "coins", "bonk", "fuse", "boom", "footsteps", "car", "whoosh",
       "crowd", "cash", "door", "ding", "thud", "laugh", "gasp", "horse", "train", "glass", "paper", "pop", "scratch", "boing"]

SHOT_MIN, SHOT_MAX = 1.0, 3.5          # seconds per shot (reference: 1.5-3 s)
STILL_MAX = 2.0                        # longest stretch without a new action
STORY_MIN, STORY_MAX = 40.0, 75.0
PAD = 0.09                             # breath after each line


def load_cast(path=CAST_FILE):
    data = json.loads(Path(path).read_text())
    return {c["id"]: c for c in data["characters"]}, data.get("narrator", {})


def load_kits(path=KITS_FILE):
    return json.loads(Path(path).read_text())["kits"]


def _rate(v):
    m = re.match(r"([+-]?\d+)%", str(v.get("rate", "+0%")))
    return int(m.group(1)) / 100 if m else 0.0


def words(text):
    return [w for w in re.split(r"\s+", text.strip()) if re.search(r"\w", w)]


def estimate_dur(text, voice):
    """Seconds this line will take in this voice (before any audio exists)."""
    wpm = voice.get("base_wpm", 160) * (1 + _rate(voice))
    n = len(words(text))
    pauses = 0.12 * len(re.findall(r"[,;:]", text)) + 0.18 * len(re.findall(r"[.!?](?=\s+\S)", text))
    return round(n / wpm * 60 + pauses + PAD, 2)


def voice_of(who, cast, narrator):
    if who == "narrator":
        return narrator.get("voice", {"base_wpm": 190, "rate": "+20%"})
    return cast.get(who, {}).get("voice", {"base_wpm": 160})


def shot_dur(shot, cast, narrator):
    """Real duration when the voice has been made, else the estimate."""
    if shot.get("dur"):
        return float(shot["dur"])
    return estimate_dur(shot.get("text", ""), voice_of(shot.get("speaker", "narrator"), cast, narrator))


def place_image(plan, name, stories=STORIES):
    """The painted picture for one story place (made once by toontales/sets/paint_places.mjs)."""
    return Path(stories) / plan["id"] / "places" / f"{name}.png"


def kit_for(plan, set_name, kits):
    """Set kit for a shot: a built set ("mine") or one of the plan's places on the painted stage."""
    kit = kits.get(set_name)
    if kit is not None and kit.get("kind") != "backdrop":
        return kit
    places = plan.get("places") or {}
    if set_name in places:
        k = dict(kits["stage"], place=set_name)
        p = places[set_name]
        k["about"] = p if isinstance(p, str) else p.get("prompt", "")
        return k
    return None


def load_plan(path):
    return json.loads(Path(path).read_text())


def save_plan(plan, path):
    Path(path).write_text(json.dumps(plan, indent=1, ensure_ascii=False))


def used_topics(stories=STORIES):
    """Topics of stories already made (so a new story does not repeat one)."""
    idx = Path(stories) / "index.json"
    if not idx.exists():
        return []
    return json.loads(idx.read_text()).get("stories", [])
