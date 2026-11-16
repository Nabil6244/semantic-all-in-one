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


WORLDS = Path(__file__).resolve().parents[1] / "sets" / "worlds"


CHANNELS = Path(__file__).resolve().parents[1] / "channels"


def channel(plan):
    """The plan's channel preset (toontales/channels/<name>.json): cast, look, backgrounds, captions. {} = Toon Tales."""
    name = plan.get("channel")
    if not name:
        return {}
    return json.loads((CHANNELS / f"{name}.json").read_text())


def channel_names():
    return sorted(p.stem for p in CHANNELS.glob("*.json"))


def cast_file_for(plan):
    ch = channel(plan)
    return (CHANNELS / ch["cast"]) if ch.get("cast") else CAST_FILE


def bg_mode(plan):
    """'3d' (Blender toon world) or 'flow' (painted picture): plan setting, else the channel default, else 3d."""
    return plan.get("backgrounds") or channel(plan).get("backgrounds") or "3d"


def world_layout(plan, name):
    """A 3D toon-world place: {"world": "<layout in sets/worlds>", "add": [pieces], "sky"/"ground"/"sun"?: overrides}.
    Returns the merged layout dict, or None for a painted place."""
    p = (plan.get("places") or {}).get(name)
    if not is_world(plan, name):
        return None
    base = json.loads((WORLDS / f"{p['world']}.json").read_text())
    for k, v in (channel(plan).get("look") or {}).items():  # the channel's light/sky over the world's own
        if k in ("sky", "light", "sun", "clouds"):
            base[k] = v
    base["pieces"] = list(base.get("pieces", [])) + list(p.get("add", []))
    clear = p.get("clear", [])  # spots [x, y] where this place drops the layout's own piece (to put its own there)
    base["pieces"] = [q for q in base["pieces"] if q in p.get("add", []) or not any(
        abs(q.get("at", [0, 0])[0] - c[0]) < 0.2 and abs(q.get("at", [0, 0])[1] - c[1]) < 0.2 for c in clear)]
    drop = set(p.get("remove", []))  # piece ids from the layout this place does not want
    base["pieces"] = [q for q in base["pieces"] if q.get("id") not in drop]
    for k in ("sky", "ground", "sun", "clouds"):
        if k in p:
            base[k] = p[k]
    return base


PACKS = Path(__file__).resolve().parents[2] / "assets" / "toon_world" / "kenney"


def world_models():
    """Every model name a world layout may use: file stems and pack/stem."""
    out = set()
    for g in PACKS.glob("*/Models/*/*.glb"):
        out.add(g.stem)
        out.add(f"{g.parts[len(PACKS.parts)]}/{g.stem}")
    ph = {f"ph:{d.name}" for d in (Path(__file__).resolve().parents[2] / "assets" / "diorama" / "models").glob("*")
          if d.is_dir()}
    return out | {"@" + k for k in PART_KINDS + DIORAMA_KINDS} | ph


DIORAMA_KINDS = ("slice", "shaft", "water", "room", "house", "beam", "bottle", "cap", "cork", "coin", "magnet", "ball", "wall", "lathe", "shears", "shavings", "scale_stand",
                 "scale_beam", "magnifier")  # sets/diorama.py (realistic cut-aways)
PART_KINDS = ("engine", "turbo", "supercharger", "stand", "tiles", "pegboard", "start_tree", "finish", "box", "strip", "clock", "motor")  # sets/parts.py


def world_names():
    return sorted(p.stem for p in WORLDS.glob("*.json"))


def is_world(plan, name):
    """A place is built in 3D when it has a world and the background mode is 3d (or it has no picture prompt)."""
    p = (plan.get("places") or {}).get(name)
    if not (isinstance(p, dict) and p.get("world")):
        return False
    return bg_mode(plan) == "3d" or not p.get("prompt")


def kit_for(plan, set_name, kits):
    """Set kit for a shot: a built set ("mine") or one of the plan's places on the painted stage."""
    kit = kits.get(set_name)
    if kit is not None and kit.get("kind") != "backdrop":
        return kit
    places = plan.get("places") or {}
    if set_name in places:
        k = dict(kits["stage"], place=set_name)
        p = places[set_name]
        k["about"] = p if isinstance(p, str) else p.get("prompt", p.get("world", ""))
        if is_world(plan, set_name):
            k["world"] = p["world"]
            lay = world_layout(plan, set_name) or {}
            k["pieces"] = lay.get("pieces", [])  # the camera sizes shots to these
            if lay.get("marks"):  # a layout with its own cast spots (dioramas): cameras aim there too
                k["marks"] = dict(k["marks"], **lay["marks"])
            k["bounds"] = {"x": [-40.0, 40.0], "y": [-40.0, 30.0], "z": [0.25, 25.0]}  # a real place: the camera roams
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
