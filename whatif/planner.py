"""What If: the shot planner. Narration (timed words) -> a sequence of full-frame shots plus the graphics over them, in the
editing grammar measured from the reference videos (docs/whatif/reference_targets.json):

  * hard cuts, a shot of about 6-10 s (median), cut only at the end of a clause (a pause or punctuation), never inside speech;
  * a visual change (a callout, a caption, a diagram build, a HUD state) at least every ~6.5 s inside a long shot;
  * what is shown is what is said: a named craft is that craft (its 3D model or its real photograph), a process or a number
    is a diagram, a world is that world, anything else is an illustration of the sentence -- never an unrelated filler;
  * no picture repeats within 90 s: a returning subject changes its framing;
  * every shot carries its citation (ILLUSTRATION / DIAGRAM / REAL IMAGE).

The planner decides; assets are fetched later (whatif/media.py) and a shot whose asset cannot be had falls back to a meaningful
plate (whatif/compile.py), never to an unrelated picture.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import narration as nr
from .narration import LEAD_S, Word

CALLOUT_ANCHORS = ("upper_left", "top", "upper_right", "mid")     # where the reference puts a number: in the empty sky beside the subject
TARGET_S = 6.4            # a shot is closed at the first clause end after this
MAX_S = 11.0              # never longer than this: closed at an earlier clause end
MIN_S = 3.0               # never shorter than this (a death or silence beat may be shorter)
MAX_HOLD_S = 7.0          # the longest stretch inside a shot with nothing new on screen
NO_REPEAT_S = 90.0        # the same subject is not shown the same way within this
HOOK_S, HOOK_MAX_S = 20.0, 5.5   # the opening: the references cut at 5.0-5.5 s and change the picture every 2-5 s in their first 20 s
MOVING_MIN_S = 6.0        # "both" Flow mode: an illustrated shot this long (or in the opening) is a Flow video, the rest Flow images
FLOW_VIDEO_MAX_S = 6.0    # a Flow video shot is never longer than this (the author's rule: a clip is never stretched or looped); longer ones are split
DIAGRAMS = {"tm_annotate", "tm_bars", "tm_compare", "tm_composition", "tm_curve", "tm_dial", "tm_discmap", "tm_grid", "tm_logaxis",
            "tm_orbitmap", "tm_phase", "tm_timeline", "tm_wave"}
PLATE_MIN_S, PLATE_MAX_S = 3.5, 6.2
PLATE_SHARE_MAX = 0.35
BLACK_MAX_S = 2.8         # a black shot is a breath (a death, a signal lost): the rest of a longer one is given to a picture
PLATE_HUDS = ("tm_gauge", "tm_survival")     # instruments that step back over plates (hide_on_plates) unless a plate is theirs alone

# craft that have a NASA 3D model in whatif-engine/assets/models: pattern -> (model file, name on screen)
CRAFT: List[Tuple[str, str, str]] = [
    (r"\bvoyager ?2\b", "voyager.glb", "VOYAGER 2"), (r"\bvoyager( ?1)?\b", "voyager.glb", "VOYAGER 1"), (r"\bcassini\b", "cassini.glb", "CASSINI"),
    (r"\bjuno\b", "juno.glb", "JUNO"), (r"\bgalileo (probe|spacecraft|orbiter)\b|\bgalileo\b(?! galilei)", "galileo.glb", "GALILEO"),
    (r"\bmagellan\b", "magellan.glb", "MAGELLAN"), (r"\bparker( solar)?( probe)?\b", "parker.glb", "PARKER SOLAR PROBE"),
    (r"\bperseverance\b", "perseverance.glb", "PERSEVERANCE"), (r"\bviking( lander| 1| 2)?\b", "viking_lander.glb", "VIKING LANDER"),
    (r"\bwebb\b|\bjwst\b", "jwst.glb", "JAMES WEBB SPACE TELESCOPE"), (r"\bhubble\b", "hubble.glb", "HUBBLE SPACE TELESCOPE"),
    (r"\blunar module\b|\beagle\b", "apollo_lm.glb", "APOLLO LUNAR MODULE"), (r"\bsaturn v\b", "saturn_v.glb", "SATURN V"),
    (r"\bdeep space network\b|\bdsn\b|\bradio dish\b|\b70[- ]metre\b", "dsn_70m.glb", "DEEP SPACE NETWORK"), (r"\bdawn\b(?= (probe|spacecraft|mission))", "dawn.glb", "DAWN"),
    (r"\bmessenger\b", "messenger.glb", "MESSENGER"), (r"\brosetta\b", "rosetta.glb", "ROSETTA"), (r"\bulysses\b", "ulysses.glb", "ULYSSES"),
    (r"\bingenuity\b", "ingenuity.glb", "INGENUITY"), (r"\binsight\b", "insight.glb", "INSIGHT"), (r"\bspace station\b|\biss\b", "iss.glb", "INTERNATIONAL SPACE STATION"),
    (r"\bpioneer( ?1[01])?\b", "pioneer10.glb", "PIONEER 10"), (r"\bdeep space 1\b", "deep_space_1.glb", "DEEP SPACE 1"), (r"\bstardust\b", "stardust.glb", "STARDUST"),
]
# worlds with a texture for a globe shot: pattern -> (texture, name, atmosphere colour, tint of diagram plates about it)
WORLDS: List[Tuple[str, str, str, Optional[str]]] = [
    (r"\bvenus\b", "2k_venus_atmosphere.jpg", "VENUS", "#f0c890"), (r"\bmars\b", "2k_mars.jpg", "MARS", "#e8a070"),
    (r"\bmercury\b", "2k_mercury.jpg", "MERCURY", None), (r"\bjupiter\b", "jupiter_cassini_pia07782.jpg", "JUPITER", None),
    (r"\buranus\b", "2k_uranus.jpg", "URANUS", "#a8e0e8"), (r"\bneptune\b", "2k_neptune.jpg", "NEPTUNE", "#6a8ae8"),
    (r"\bearth\b", "earth_bluemarble_5400.jpg", "EARTH", "#7fb0ff"), (r"\bmoon\b", "moon_lroc_4096.jpg", "THE MOON", None),
    (r"\bthe sun\b|\bsunlight\b", "2k_sun.jpg", "THE SUN", "#ffcf80"),
]
# a unit that is about an image or an event is not a "world in general": it needs a real or illustrated picture
EVENT = re.compile(r"\b(photo\w*|pictures?|images?|panorama|footage|film|first colou?r|landed|landing|touched down|launch\w*|lifted off|crash\w*|parachute\w*|"
                   r"descen\w*|signal|transmit\w*|radio|record\w*|mission|probe|lander|rover|astronaut\w*|engineer\w*|team)\b", re.I)
PHOTO = re.compile(r"\b(photo\w*|pictures?|images?|panorama|footage|film|first colou?r|pale blue dot|selfie|snapshot)\b", re.I)
MISSIONS_NO_MODEL = re.compile(r"\b(venera ?\d*|vega ?\d*|mariner ?\d*|pioneer venus|akatsuki|sputnik|luna ?\d*|lunokhod|mars ?\d+|mars rover|sojourner|spirit|opportunity|"
                               r"curiosity|new horizons|messenger|apollo ?\d*|artemis ?\d*|gemini|mercury seven|soyuz|vostok|skylab|mir)\b", re.I)
# worlds with no texture shipped: a real NASA picture of them (never an invention)
PHOTO_WORLDS = re.compile(r"\b(saturn(?:'s)?(?: rings)?|pluto|titan|europa|io|ganymede|callisto|enceladus|halley'?s? comet|asteroid\w*|the milky way|andromeda|black hole|the crab nebula|nebula)\b", re.I)
ENV = re.compile(r"\b(air|clouds?|atmospher\w*|surface|ground|sky|up|altitude|acid|haze|temperature|degrees|pressure|hot|cold|heat|rain|wind|storm)\b", re.I)
HOUSE = ("Sober, realistic CG render for a serious science documentary, like NASA mission animation: accurate engineering, matte metal and "
         "foil, no cartoon or toy look, no rounded cute shapes. Wide shot with the subject small and calm in a vast landscape, strong atmospheric "
         "haze, a single warm colour (burnt orange or slate), soft low sun, deep depth of field, restrained and desaturated, 16:9, no text, "
         "no logos, no labels. ")


HOUSE_SPACE = ("Cinematic, realistic CG for a serious space documentary, like NASA and ESA mission animation: deep black space, a real "
               "star field, accurate scale and lighting from a single distant star, crisp detail, restrained natural colour, slow and calm, "
               "16:9, no text, no numbers, no logos, no labels, no people. ")
SURFACE = re.compile(r"\b(surface|ground|landscape|plain|terrain|desert|ocean|sea|clouds?|sky|atmospher\w*|air|haze|lava|rock\w*|"
                     r"mountain\w*|valley|crater\w*|ice|snow|rain|storm|wind|land\w*|city|street|room|building)\b", re.I)
MOTION = re.compile(r"\b(drift\w*|push\w*|pull\w*|pan\w*|orbit\w*|rotat\w*|turn\w*|mov\w*|fly\w*|flies|fall\w*|rush\w*|zoom\w*|track\w*|slid\w*)\b", re.I)


def house(text: str) -> str:
    """The look an AI picture is asked in: a landscape (haze, low sun) only for a surface or a sky; anything in space is deep black space.
    One Venus-made style for everything turned Alpha Centauri into an orange hazy landscape."""
    return HOUSE if SURFACE.search(text or "") else HOUSE_SPACE


def brief(text: str) -> str:
    """A sentence as a picture brief: no digits or number words left to be drawn as garbled text."""
    t = re.sub(r"\b\d[\d,.]*\b", " ", text or "")
    t = re.sub(r"\b(light[- ]years?|light[- ]seconds?|kilomet\w+|km|percent|degrees?)\b", " ", t, flags=re.I)
    return describe(re.sub(r"\s+", " ", t))


def video_brief(asset: str) -> str:
    """A Flow video prompt says how it moves: a still's description gets a slow camera move."""
    return asset if MOTION.search(asset.split(":", 1)[-1]) else asset.rstrip(". ") + ". Slow, smooth camera push-in; gentle drift."


@dataclass
class Shot:
    id: str
    start: float
    end: float
    kind: str = "image"                    # image | video | plate | craft | globe | black
    text: str = ""                         # the narration it illustrates
    asset: str = ""                        # nasa_image:... / flow_image:... / flow_video:... / stock_*:... / file:...
    model: str = ""
    scene: str = ""                        # hero shots: venera_ground | venera_descent
    texture: str = ""
    tint: str = "cool"
    title: str = ""
    sub: str = ""
    cite: Tuple[str, str] = ("", "")
    cam: Dict[str, Any] = field(default_factory=dict)
    atmosphere: str = ""
    place: str = ""                        # the world or craft it is about (for subjects of captions)
    exit: str = "cut"
    name: str = ""                         # craft / archive name for the lower-left lockup
    row: int = 0                           # the media row number (assets)
    file: str = ""                         # resolved file
    credit: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def length(self) -> float:
        return self.end - self.start


@dataclass
class ShotPlan:
    shots: List[Shot]
    layers: List[Dict[str, Any]]
    duration: float
    title: str = ""
    notes: List[str] = field(default_factory=list)
    words: List[Word] = field(default_factory=list)


NAME_AGAIN_S = 120.0       # the same name on screen again only this long after it was last shown ("VOYAGER 1" on every craft shot is noise)
_DIRECTION = re.compile(r"^(in|on|against|with|behind|near|from|at|over|under|across|through|towards?|into|beside|above|below|far|alone|small|"
                        r"close|closer|wide|new|angle|view|shot|again|seen|still|now|then|after|before|during|and|as|while|\w+ing|"
                        r"is|was|are|begins|starts|turns|leaves|reaches|passes|heads|flies|sends|gets|goes|comes|keeps|sits|hangs|looks)$", re.I)
_MEDIA_WORDS = re.compile(r"\b(footage|photo|photograph|image|picture|illustration|render|clip|still|animation|mosaic view)\b", re.I)


_ING_NOUNS = {"crossing", "landing", "opening", "ending", "beginning", "building", "ceiling", "painting", "drawing", "recording", "reading",
              "warning", "wiring", "housing", "bearing", "coating", "mapping", "heating", "spring", "string", "lightning", "morning", "evening"}


def t_ok(last: Optional[float], t: float) -> bool:
    return last is None or t - last >= NAME_AGAIN_S


def screen_name(label: str) -> str:
    """What may stand on screen as a thing's name: "VOYAGER 1", "PALE BLUE DOT", "IO". A CSV label written as a shot direction
    ("Voyager 1 drifting in deep space", "Voyager 1 transmitting, new angle", "Saturn approach footage") was shown as the title (project
    #016); it is cut to the name in front of the direction. Returns "" when nothing name-like is left."""
    t = re.sub(r"\([^)]*\)", " ", str(label or ""))
    t = re.split(r"\s[—–-]\s|[,:;]", t)[0]
    t = _MEDIA_WORDS.sub(" ", t)
    words = t.split()
    keep = []
    for w in words:
        bare = w.strip(".'\"").lower()
        if _DIRECTION.match(bare) and keep and not (bare.endswith("ing") and (len(bare) <= 5 or bare in _ING_NOUNS)):
            break
        keep.append(w)
    if len(keep) > 4 or not keep:
        return ""
    return " ".join(keep).upper().strip(" .")


def _craft(text: str) -> Optional[Tuple[str, str]]:
    low = text.lower()
    for pat, model, name in CRAFT:
        if re.search(pat, low):
            return model, name
    return None


def _world(text: str) -> Optional[Tuple[str, str, str]]:
    low = re.sub(r"\bthan (?:on |at |in |for )?(?:the )?\w+", " ", text.lower())     # "harder than on Earth": Earth is the yardstick
    best = None
    for pat, tex, name, atm in WORLDS:
        m = re.search(pat, low)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), tex, name, atm or "")
    return best[1:] if best else None


# ---- timeline --------------------------------------------------------------------------------------------------------------
MID_SPEECH_SHARE = 0.25     # the references cut inside speech on 18-35 % of their cuts (65-82 % land in a pause): measured, docs/whatif/reference_spec.md


def _mid_candidates(words: List[Word]) -> List[float]:
    """Word starts where a cut inside speech reads as an edit: the first content word of a phrase, after a function word, with no pause
    before it (the references cut on 'the AIR presses...', never on a stray 'the')."""
    out = []
    for i in range(1, len(words)):
        w, prev = words[i], words[i - 1]
        if w.norm in nr.FILLER or w.norm in nr.TAIL_WORDS or len(w.norm) < 3:
            continue
        if w.start - prev.end >= 0.12 or re.search(r"[,;:.?!]$", prev.text):
            continue                                   # that is a pause: already a pause candidate
        if prev.norm in nr.FILLER or prev.norm in ("and", "but", "or", "so"):
            out.append(w.start - 0.04)
    return out


def cut_points(words: List[Word], duration: float) -> List[float]:
    """The shot boundaries. Most (about 75 %) fall in a pause, at the end of a clause; the rest fall on a content word inside a clause,
    as the reference's do (MID_SPEECH_SHARE). A shot closes at the first candidate once it has run TARGET_S (a sentence end once it has
    run 4.6 s and the next sentence changes subject), never after MAX_S. Deterministic: which cuts are mid-speech follows a fixed
    golden-ratio sequence, so the same narration always gives the same edit."""
    cl = nr.clauses(words)
    if not cl:
        return [0.0, duration]
    sn_end = {b for _, b in nr.sentences(words)}
    mids = _mid_candidates(words)
    cuts, t0, n = [0.0], 0.0, 0
    entity = lambda a, b: (_craft(nr.span_text(words, a, b)) or (None,))[0] or (_world(nr.span_text(words, a, b)) or (None,))[0]   # noqa: E731
    for k, (a, b) in enumerate(cl):
        end = words[b].end
        nxt_start = words[cl[k + 1][0]].start if k + 1 < len(cl) else duration
        cut_at = (end + nxt_start) / 2 if nxt_start - end > 0.12 else nxt_start - 0.06       # inside the pause, before the next word
        length = cut_at - t0
        e_here = entity(a, b)
        new_subject = k + 1 < len(cl) and entity(*cl[k + 1]) not in (None, e_here)
        want_mid = ((n + 1) * 0.6180339887) % 1.0 < MID_SPEECH_SHARE
        if want_mid and length >= TARGET_S - 1.2:
            # this cut is a mid-speech one: the content word in this clause nearest the usual length, if there is one
            ideal = t0 + TARGET_S
            inside = [t for t in mids if words[a].start < t < end - 0.4 and t - t0 >= MIN_S + 0.8 and duration - t >= MIN_S]
            if inside:
                t = min(inside, key=lambda x: abs(x - ideal))
                cuts.append(round(t, 3)); t0, n = t, n + 1
                continue
        close = length >= TARGET_S or (b in sn_end and length >= 4.6 and new_subject)
        if length >= MIN_S and close and duration - cut_at >= MIN_S:
            cuts.append(round(cut_at, 3)); t0, n = cut_at, n + 1
        elif length > MAX_S and k + 1 < len(cl):
            cuts.append(round(cut_at, 3)); t0, n = cut_at, n + 1
    cuts.append(round(duration, 3))
    return cuts


def carve(shots: List[Shot], new: Shot, force: bool = False) -> Optional[List[Shot]]:
    """Put `new` into the timeline over [start, end): neighbours are trimmed, a remnant under 2 s is absorbed by the plate."""
    out: List[Shot] = []
    for s in shots:
        if s.end <= new.start + 1e-6 or s.start >= new.end - 1e-6:
            out.append(s)
            continue
        if s.start < new.start - 1e-6:
            left = Shot(**{**s.__dict__, "end": new.start})
            if left.length >= 2.5:
                out.append(left)
            else:
                new.start = left.start
        if s.end > new.end + 1e-6:
            right = Shot(**{**s.__dict__, "start": new.end})
            if right.length >= 2.5:
                out.append(right)
            else:
                new.end = right.end
    if new.kind == "plate" and not force and new.end - new.start > PLATE_MAX_S + 1.5:
        return None                              # absorbing the remnants would make a plate too long: no plate
    out.append(new)
    return sorted(out, key=lambda x: x.start)


# ---- classification --------------------------------------------------------------------------------------------------------
def describe(text: str) -> str:
    """The sentence as a picture brief: filler dropped, kept short."""
    t = re.sub(r"\s+", " ", text).strip().rstrip(".?!")
    return t[:220]


def classify(text: str, *, flow_video: bool = False, topic: str = "", world_topic: str = "") -> Dict[str, Any]:
    """What one unit of narration is shown as: the fields of a Shot. `topic` is what the story was last about (a craft or a world):
    a sentence that names nothing ("it went silent") is still about that."""
    craft, world = _craft(text), _world(text)
    about = text if (craft or world or MISSIONS_NO_MODEL.search(text)) else f"{world_topic or topic}. {text}" if (world_topic and ENV.search(text)) or topic else text
    event, photo = bool(EVENT.search(text)), bool(PHOTO.search(text))
    missions = MISSIONS_NO_MODEL.search(text)
    pw = PHOTO_WORLDS.search(re.sub(r"\bthan (?:on |at |in |for )?(?:the )?\w+", " ", text))
    if not flow_video and BLACK_HOLE.search(text) and not photo:
        # a black hole has no camera picture but the two EHT photos ("photo" in the sentence keeps the real-image path): the engine ray-traces it (lib/blackhole.mjs), V4's hero shots
        low = text.lower()
        scene = ("blackhole_horizon" if re.search(r"\b(hover\w*|just above|skim\w*|edge itself)\b", low) else
                 "blackhole_lensing" if re.search(r"\b(bends?|bent|warp\w*|stars? (behind|around)|lens\w*|distort\w*)\b", low) else
                 "blackhole_top" if re.search(r"\b(from above|disc of|disk of|swirl\w*|orbiting gas)\b", low) else
                 "blackhole_ring" if re.search(r"\b(close|closer|bright (ring|edge)|photon sphere)\b", low) else "blackhole_disc")
        return {"kind": "hero", "scene": scene, "name": "", "place": "black hole", "cite": ("ILLUSTRATION", "RAY-TRACED BLACK HOLE"), "cam": {}}
    if pw and not craft and not missions:
        who = pw.group(0).strip()
        return {"kind": "image", "asset": f"nasa_image:{who}", "cite": ("REAL IMAGE", ""), "name": "", "place": who.upper()}
    if photo and (missions or craft):
        who = (missions.group(0) if missions else craft[1]).strip()
        return {"kind": "image", "asset": f"nasa_image:{who} {describe(text)}", "cite": ("REAL IMAGE", ""), "name": who.upper(), "place": who}
    if craft:
        model, name = craft
        return {"kind": "craft", "model": model, "name": name, "place": name, "cite": ("ILLUSTRATION", "NASA 3D MODEL")}
    if missions and re.match(r"venera", missions.group(0).strip(), re.I) and not flow_video:
        # the one craft the reference draws as a composed scene: the Venera lander, on the plain or under its parachute (lib/hero.mjs)
        who = missions.group(0).strip()
        if re.search(r"\b(parachute\w*|descen\w*|fell|fall\w*|dropp\w*)\b", text, re.I):
            return {"kind": "hero", "scene": "venera_descent", "name": who.upper(), "place": who, "cite": ("ILLUSTRATION", ""), "cam": {}}
        if event or re.search(r"\b(lander|ground|surface|plain|silent|hot|melt\w*|pressure|hours?|minutes?)\b", text, re.I):
            return {"kind": "hero", "scene": "venera_ground", "name": who.upper(), "place": who, "cite": ("ILLUSTRATION", ""), "cam": {}}
    if not flow_video and HABITAT.search(text) and not photo:
        # a spinning settlement (V5): drawn by the engine (lib/habitat.mjs) -- inside the cylinder, the ring station, or the cylinders outside
        low = text.lower()
        scene = ("cylinder_interior" if re.search(r"\b(inside|above your head|overhead|look up|the land|ground)\b", low) and "cylind" in low or "o'neill" in low and "inside" in low
                 else "cylinder_exterior" if "cylind" in low else "ring_station")
        return {"kind": "hero", "scene": scene, "name": "", "place": "space settlement", "cite": ("ILLUSTRATION", "SPACE SETTLEMENT"), "cam": {}}
    if not flow_video and AIRSHIP.search(text):
        return {"kind": "hero", "scene": "cloud_airship", "name": "", "place": "airship", "cite": ("ILLUSTRATION", ""), "cam": {}}
    if not flow_video and DRIVE.search(text) and not photo:
        return {"kind": "hero", "scene": "ship_engine", "name": "", "place": "your ship", "cite": ("ILLUSTRATION", ""), "cam": {}}
    if missions:
        who = missions.group(0).strip()
        src = "flow_video" if flow_video else "flow_image"
        return {"kind": "video" if flow_video else "image", "asset": f"{src}:{house(text)}{who}: {brief(text)}", "cite": ("AI ILLUSTRATION", ""), "name": who.upper(), "place": who}
    if world and not event:
        tex, name, atm = world
        return {"kind": "globe", "texture": tex, "atmosphere": atm, "name": name, "place": name, "cite": ("ILLUSTRATION", "")}
    src = "flow_video" if flow_video else "flow_image"
    return {"kind": "video" if flow_video else "image", "asset": f"{src}:{house(about)}{brief(about)}", "cite": ("AI ILLUSTRATION", ""),
            "place": world[1] if world else topic}


DEEP = re.compile(r"\b(galax(y|ies)|deep field|observable universe|edge of the universe)\b.{0,80}\b(away|never|reach|billion|far)\b|\b(never|billion).{0,60}\bgalax(y|ies)\b", re.I)
BLACK_HOLE = re.compile(r"\b(black holes?|event horizon|accretion dis[ck]|photon sphere|sagittarius a\*?|sgr a\*?|singularity)\b", re.I)
HABITAT = re.compile(r"\b(o'neill (cylinder|colony|habitat)s?|space (habitat|settlement|colony|city)|spinning (station|habitat|wheel)|rotating (station|habitat|wheel|cylinder)|stanford torus|wheel station)\b", re.I)
AIRSHIP = re.compile(r"\b(airships?|dirigibles?|balloons?|floating (city|habitat|home)|float\w* (above|in|on) the clouds)\b", re.I)
DRIVE = re.compile(r"\b(constant (acceleration|thrust)|never stops pushing|keeps? (accelerating|pushing|burning)|fusion (drive|engine)|engines? (burn|fire|push)\w*|"
                   r"accelerat\w+ at 1 ?g|1 ?g of acceleration|your ship'?s? engines?)\b", re.I)
FRAMINGS = ("wide establishing view", "medium view", "close detail", "low angle", "high angle looking down", "silhouette against the light")


EVOLVE_MAX_S = 20.0     # one subject held as one evolving shot at most this long (the reference's 8-20 s compositions, V3)


SHORT_SHOT_S = 2.0       # a picture on screen for less than this is a flash (a CSV whose anchors bunch up squeezed shots to 0.5 s)


def absorb_short(shots: List[Shot], notes: List[str]) -> List[Shot]:
    """A picture or clip shorter than SHORT_SHOT_S joins the neighbouring picture or clip, so the shots stay contiguous and the picture
    that stays is held for the whole stretch. Plates, crafts, globes, hero and black shots are left as they are."""
    ok = lambda x: x.kind in ("image", "video") and not x.extra.get("lockup")      # noqa: E731
    out: List[Shot] = list(shots)
    n = 0
    i = 0
    while i < len(out):
        s = out[i]
        if not ok(s) or s.length >= SHORT_SHOT_S:
            i += 1
            continue
        prev = out[i - 1] if i > 0 and ok(out[i - 1]) and abs(out[i - 1].end - s.start) < 0.05 else None
        nxt = out[i + 1] if i + 1 < len(out) and ok(out[i + 1]) and abs(out[i + 1].start - s.end) < 0.05 else None
        host = max((x for x in (prev, nxt) if x is not None), key=lambda x: x.length, default=None)
        if host is None:
            i += 1
            continue
        if host is prev:
            host.end, host.text = s.end, (host.text + " " + s.text).strip()
        else:
            host.start, host.text = s.start, (s.text + " " + host.text).strip()
        host.extra["about"] = " ".join(x for x in (host.extra.get("about"), s.extra.get("about")) if x and x not in (host.extra.get("about") or ""))
        del out[i]
        n += 1
        i = max(0, i - 1)
    if n:
        notes.append(f"plan: {n} flash shot(s) under {SHORT_SHOT_S:g} s joined the picture next to them")
    return out


def merge_beats(shots: List[Shot], notes: List[str]) -> List[Shot]:
    """Consecutive shots of the same subject -- the same 3D model, or the same world -- are one continuous, evolving shot: the
    reference holds a composition while its type and graphics arrive on their words, where a shot list per CSV row cut to a new
    framing of the same thing every 6 s (#016). A camera the CSV asks for on the next row ("close") is a real change and still cuts;
    so does a longer total than EVOLVE_MAX_S. The layers keep their own times, so nothing moves on the narration."""
    out: List[Shot] = []
    merged = 0
    for s in shots:
        prev = out[-1] if out else None
        same = prev is not None and prev.kind == s.kind and s.kind in ("craft", "globe") and abs(prev.end - s.start) < 0.05 \
            and (prev.model or prev.texture) == (s.model or s.texture) and (prev.model or prev.texture)
        own_cam = bool(s.cam) and s.cam != prev.cam if prev is not None else False
        if same and not own_cam and s.end - prev.start <= EVOLVE_MAX_S and not s.extra.get("lockup"):
            prev.end = s.end
            prev.text = (prev.text + " " + s.text).strip()
            merged += 1
            continue
        out.append(s)
    if merged:
        notes.append(f"plan: {merged} cut(s) between shots of the same subject removed: it is held as one evolving shot")
    return out


def vary(shots: List[Shot]) -> int:
    """No subject twice the same way within NO_REPEAT_S: a returning craft or world changes angle and distance, a returning picture
    changes its framing words. Returns how many shots were changed."""
    seen: Dict[str, List[Shot]] = {}
    changed = 0
    for s in shots:
        key = s.model or s.texture or s.scene or (s.asset.split(":", 1)[1][:60] if ":" in s.asset else "")
        if not key:
            continue
        prior = [p for p in seen.get(key, []) if s.start - p.end < NO_REPEAT_S]
        if prior:
            n = len(prior)
            if s.kind == "craft":
                s.cam = {"az0": (20, -40, 60, -70)[n % 4], "az1": (-25, 25, -10, 30)[n % 4], "el": (10, 28, -8, 36)[n % 4], "dist": (3.0, 2.2, 3.6, 2.6)[n % 4], "roll": (0, 6, -5, 0)[n % 4]}
            elif s.kind == "hero":
                # the reference revisits the lander wide, then close: the same scene, a new composition
                s.cam = ({"size": 0.09, "x": 0.66, "hover": 0.5, "turn": -0.9, "seed": 11}, {"size": 0.55, "x": 0.3, "hover": 1.0, "turn": 0.4, "seed": 13},
                         {"size": 0.34, "x": 0.58, "hover": 1.8, "turn": -0.2, "seed": 17})[(n - 1) % 3] if s.scene == "venera_ground" else \
                    {"size": (0.28, 0.45)[n % 2], "az": (0, 40)[n % 2], "y": (0, 1.5)[n % 2]}
            elif s.kind == "globe":
                s.cam = {"dist": (3.9, 2.3, 5.2, 2.8)[n % 4], "el": (6, 24, -10, 14)[n % 4], "ox": (0, 0.9, -0.7, 0.4)[n % 4], "oy": (0, -0.2, 0.3, 0)[n % 4], "spin0": 1.6 * n}
            elif s.asset:
                s.asset = f"{s.asset} -- {FRAMINGS[n % len(FRAMINGS)]}"
            changed += 1
        seen.setdefault(key, []).append(s)
    return changed


def flow_mode(v: Any) -> str:
    """The Flow switch: True/"videos" -> every illustrated shot moves, False/"images" -> stills, "both" -> motion where it matters."""
    if isinstance(v, str) and v in ("images", "videos", "both"):
        return v
    return "videos" if v is True else "images" if v is False else "both"


def _to_video(s: Shot) -> None:
    s.asset = video_brief("flow_video:" + s.asset.split(":", 1)[1])
    s.kind = "video"


def mix_flow(shots: List[Shot], mode: str, notes: List[str]) -> int:
    """Flow images or videos for the AI-illustrated shots, the CSV's too: "videos" moves them all; "both" moves the opening and the long
    holds (a still held MOVING_MIN_S+ reads as a frozen screen) and keeps the short ones as pictures. "images" leaves them as planned."""
    if mode == "images":
        return 0
    moved = [s for s in shots if s.asset.lower().startswith("flow_image:")
             and (mode == "videos" or s.start < HOOK_S or s.length >= MOVING_MIN_S)]
    for s in moved:
        _to_video(s)
    for s in shots:                 # every Flow video says how it moves (the CSV's and the planner's own too)
        if s.asset.lower().startswith("flow_video:"):
            s.asset = video_brief(s.asset)
    if moved:
        notes.append(f"plan: {len(moved)} illustrated shot(s) are Flow videos ({'all of them' if mode == 'videos' else 'the opening and the long holds'})")
    return len(moved)


FLOW_OPEN_S = HOOK_S        # Flow (AI pictures and clips) is a last resort: never in the opening (real footage there), then at most one per FLOW_LATER_GAP_S
FLOW_LATER_GAP_S = 180.0
STOCK_STOP = {"the", "a", "an", "of", "to", "and", "in", "on", "at", "it", "its", "is", "was", "were", "be", "that", "this", "these", "those", "with",
              "for", "from", "by", "as", "but", "so", "or", "if", "then", "than", "into", "over", "under", "you", "your", "we", "our", "they", "their",
              "would", "could", "can", "will", "just", "only", "very", "much", "more", "most", "about", "there", "here", "what", "which", "who"}


NICHE = "space astronomy"          # the channel's niche: a stock search is always anchored in it, so "move" cannot return a tape measure
_NICHE_WORDS = re.compile(r"\b(space|star\w*|galax\w*|planet\w*|solar|sun|moon|orbit\w*|cosmic|universe|nebula|telescope|spacecraft|"
                          r"voyager|mars|venus|jupiter|saturn|titan|earth|astronom\w*|milky|comet|asteroid)\b", re.I)


def stock_query(s: Shot, context: str = "") -> str:
    """A stock search for a shot from its CONTEXT, never one stray word: the sentence it sits in (extra["about"]), else its own words
    plus the neighbouring shots' (a 0.5 s shot's text is a single word), led by its subject, anchored in the niche when the words alone are not."""
    text = s.extra.get("about") or " ".join(x for x in (s.text, context) if x)
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]+", re.sub(r"\d[\d,.]*", " ", text)) if w.lower() not in STOCK_STOP and len(w) > 2]
    head = (s.name or s.place or "").strip()
    parts = list(dict.fromkeys(([head] if head else []) + words[:8]))
    if not _NICHE_WORDS.search(" ".join(parts)):
        parts.append(NICHE)
    return " ".join(parts)[:90] or NICHE


def limit_flow(shots: List[Shot], notes: List[str]) -> int:
    """Flow is a last resort (the author's correction: it was added where no AI picture was needed, the opening above all): none in the
    first FLOW_OPEN_S, then one Flow shot per FLOW_LATER_GAP_S is kept (a scene no camera could film), the rest become stock searches
    of the same subject. The CSV's rows too."""
    last, moved = -1e9, 0
    for i, s in enumerate(shots):
        if not s.asset.lower().startswith(("flow_image:", "flow_video:")):
            continue
        if s.start >= FLOW_OPEN_S and s.start - last >= FLOW_LATER_GAP_S:
            last = s.start
            continue
        src = "stock_video" if s.kind == "video" or s.asset.lower().startswith("flow_video:") else "stock_image"
        s.kind = "video" if src == "stock_video" else "image"
        around = " ".join(x.text for x in shots[max(0, i - 2):i + 3] if x is not s and x.text) if len(s.text.split()) < 8 else ""
        s.asset, s.cite = f"{src}:{stock_query(s, around)}", ("IMAGE", "")
        moved += 1
    if moved:
        notes.append(f"plan: Flow is a last resort (none in the first {FLOW_OPEN_S:.0f} s, one shot every {FLOW_LATER_GAP_S / 60:.0f} min at most); "
                     f"{moved} Flow shot(s) are real-footage searches instead")
    return moved


def split_long_videos(shots: List[Shot], words: Sequence[Word], layers: Sequence[Dict[str, Any]], notes: List[str]) -> List[Shot]:
    """Every Flow video shot is FLOW_VIDEO_MAX_S or shorter: a longer one is cut at a pause into clips of the same subject, each its own
    Flow video (vary() then gives each a different framing: wide, medium, close...), so a long hold still moves and no clip is stretched."""
    out: List[Shot] = []
    split = 0
    for s in shots:
        pieces = [s]
        while pieces[-1].asset.lower().startswith("flow_video:") and pieces[-1].length > FLOW_VIDEO_MAX_S:
            cur = pieces[-1]
            k = max(2, -(-cur.length // (FLOW_VIDEO_MAX_S - 0.5)))       # how many clips it becomes, evenly
            want = cur.start + cur.length / k
            lo, hi = cur.start + 2.0, min(cur.start + FLOW_VIDEO_MAX_S, cur.end - 2.0)
            # a real pause first (the references cut in a pause 65-82 % of the time), then any word boundary, then the clip's limit
            pauses = [(w0.end + w1.start) / 2 for w0, w1 in zip(words, words[1:]) if w1.start - w0.end > 0.12 and lo <= (w0.end + w1.start) / 2 <= hi]
            at = min(pauses, key=lambda x: abs(x - want)) if pauses else _gap_near(words, cur.start, cur.end, want, edge=min(2.5, cur.length / k - 0.5))
            if at is None or at - cur.start > FLOW_VIDEO_MAX_S or cur.end - at < 1.5:
                at = round(min(want, cur.start + FLOW_VIDEO_MAX_S - 0.2), 3)
            for L in layers:                 # the first clip's name lockup ends with it
                if L.get("type") == "tm_caption" and cur.start <= L["start"] < at and L["end"] > at - 0.2:
                    L["end"] = round(max(L["start"] + 1.0, at - 0.2), 3)
            nxt = Shot(id="", start=round(at, 3), end=cur.end, kind="video", asset=cur.asset, cite=cur.cite, place=cur.place, exit=cur.exit,
                       text=" ".join(w.text for w in words if at - 0.05 <= w.start < cur.end - 0.05), extra={k_: v for k_, v in cur.extra.items() if k_ != "row"})
            cur.end, cur.exit = round(at, 3), "cut"
            pieces.append(nxt)
            split += 1
        out.extend(pieces)
    if split:
        notes.append(f"plan: {split} long Flow video shot(s) split so every clip is {FLOW_VIDEO_MAX_S:.0f} s or shorter")
    return out


def _gap_near(words: Sequence[Word], a: float, b: float, at: float, edge: float = 2.5) -> Optional[float]:
    """The pause between two words nearest `at`, inside (a + edge, b - edge): a cut there never lands mid-word."""
    best = None
    for w0, w1 in zip(words, words[1:]):
        t = (w0.end + w1.start) / 2
        if a + edge <= t <= b - edge and (best is None or abs(t - at) + (0 if w1.start - w0.end > 0.12 else 0.6) < abs(best[0] - at) + best[1]):
            best = (t, 0 if w1.start - w0.end > 0.12 else 0.6)
    return best[0] if best else None


def hook(shots: List[Shot], words: Sequence[Word], layers: Sequence[Dict[str, Any]], mode: str, notes: List[str]) -> List[Shot]:
    """The opening (first HOOK_S): no shot longer than HOOK_MAX_S. A long one is cut at a pause and its second half becomes a new picture of
    what is said there (a moving one unless the mode is images); a real photograph in the opening fills the frame instead of letterboxing.
    A plate carrying a diagram is left whole (cutting it would break the build)."""
    out: List[Shot] = []
    split = 0
    for s in shots:
        pieces = [s]
        whole = s.text
        while pieces[-1].start < HOOK_S and pieces[-1].length > HOOK_MAX_S and pieces[-1].kind in ("image", "video", "globe", "craft", "plate", "black"):
            cur = pieces[-1]
            if cur.kind == "plate" and any(L.get("type") in DIAGRAMS and L["start"] < cur.end and cur.start < L["end"] for L in layers):
                break
            at = _gap_near(words, cur.start, cur.end, cur.start + min(HOOK_MAX_S - 0.5, cur.length / 2))
            if at is None:
                break
            text = " ".join(w.text for w in words if at - 0.05 <= w.start < cur.end - 0.05)
            if not text.strip():
                break
            if cur.asset.lower().startswith(("flow_image:", "flow_video:")):
                # an illustration split in two: the same picture brief again (vary() then frames it differently: wide, close...)
                fields = {"kind": cur.kind, "asset": cur.asset, "cite": cur.cite, "place": cur.place, "name": cur.name}
            else:
                fields = classify(whole, flow_video=mode != "images", topic=cur.place or cur.name)
            if fields.get("asset") and fields["asset"] == cur.asset and not cur.asset.lower().startswith("flow_") \
                    or fields["kind"] == cur.kind == "image" and fields.get("asset", "").startswith("nasa_image:"):
                # the same picture again is no change: an illustration of the words instead
                src = "flow_image" if mode == "images" else "flow_video"
                about = (cur.place + ". " if cur.place else "") + whole        # the whole sentence, not the fragment after the cut
                fields = {"kind": "image" if mode == "images" else "video", "asset": f"{src}:{house(about)}{brief(about)}",
                          "cite": ("AI ILLUSTRATION", ""), "place": cur.place}
            for L in layers:                 # the first half's name lockup ends with it
                if L.get("type") == "tm_caption" and cur.start <= L["start"] < at and L["end"] > at - 0.2:
                    L["end"] = round(max(L["start"] + 1.0, at - 0.2), 3)
            nxt = Shot(id="", start=round(at, 3), end=cur.end, text=text, exit=cur.exit, **fields)
            nxt.extra["split_of"] = True
            cur.end, cur.exit = round(at, 3), "cut"
            pieces.append(nxt)
            split += 1
        for p in pieces:
            if p.start < HOOK_S and p.kind == "image" and p.cite[0] == "REAL IMAGE":
                p.extra["full_bleed"] = True
        out.extend(pieces)
    if split:
        notes.append(f"plan: the opening is cut faster ({split} long shot(s) in the first {HOOK_S:.0f} s split, none over {HOOK_MAX_S} s)")
    return out


LIGHT_KM_S = 299792.458
MOVING = ("video", "craft", "globe", "hero")
_LOOK = ("kind", "asset", "cite", "name", "model", "texture", "scene", "cam", "atmosphere", "file", "credit")


def moving_open(shots: List[Shot], words: Sequence[Word], mode: str, notes: List[str]) -> List[Shot]:
    """Shot 1 moves (the references open on motion; a still photo held first read as a slide). The opening photo split by hook():
    its moving half goes first and the photograph second. A still opening that was not split: its first seconds become a Flow video of
    the same subject, the picture follows. Flow images only (mode "images"): left as it is."""
    if mode == "images" or not shots or shots[0].kind in MOVING:
        return shots
    s0 = shots[0]
    if len(shots) > 1 and shots[1].extra.get("split_of") and shots[1].kind in MOVING:
        s1 = shots[1]
        for k in _LOOK:
            a, b = getattr(s0, k), getattr(s1, k)
            setattr(s0, k, b)
            setattr(s1, k, a)
        for k in ("full_bleed",):
            if k in s0.extra:
                s1.extra[k] = s0.extra.pop(k)
        notes.append(f"plan: the video opens on motion (shot {s0.id}), the photograph follows")
        return shots
    if s0.kind not in ("image", "plate", "black") or s0.length < 4.0:
        return shots
    at = _gap_near(words, s0.start, s0.end, s0.start + min(3.0, s0.length / 2), edge=1.6) or round(s0.start + min(3.0, s0.length / 2), 3)
    subject = s0.place or s0.name or s0.text
    lead = Shot(id="", start=s0.start, end=round(at, 3), kind="video", text=" ".join(w.text for w in words if s0.start - 0.05 <= w.start < at - 0.05),
                asset=f"flow_video:{house(s0.text)}{brief(subject + '. ' + s0.text if subject != s0.text else s0.text)}", cite=("AI ILLUSTRATION", ""),
                place=s0.place, name=s0.name)
    s0.start = round(at, 3)
    notes.append("plan: the video opens on motion (a Flow video of the opening subject), the first picture follows")
    return [lead] + shots


def _overlap(s: Shot, L: Dict[str, Any]) -> float:
    return max(0.0, min(s.end, float(L.get("end", s.end))) - max(s.start, float(L.get("start", s.start))))


def _draws_on_plate(L: Dict[str, Any]) -> bool:
    """A layer that is a plate's content: a diagram, a title or section card, or an instrument told to stay on over plates. A corner clock
    (tm_clock) is not: it sits over every shot of an act, so a plate under it is still an empty slate."""
    t = L.get("type")
    if t == "tm_template":
        return bool(L.get("plate", True))          # a plate template is its plate's content; an overlay (stage header, end question) is not
    return t in DIAGRAMS or t in ("tm_title", "tm_section") or (t in PLATE_HUDS and L.get("hide_on_plates") is False)


def _bare_plate(s: Shot) -> bool:
    # a heading is not content: a CSV plate with only its heading ("TITAN FLYBY GEOMETRY") was never repaired and stood empty (#016)
    return s.kind == "plate" and not (s.file or s.asset or s.extra.get("lockup"))


def empty_plates(shots: Sequence[Shot], layers: Sequence[Dict[str, Any]]) -> List[Shot]:
    """The plan check: plates with nothing drawn over most of them (a caption or a number alone on a dark slate is an empty screen)."""
    return [s for s in shots if _bare_plate(s) and sum(_overlap(s, L) for L in layers if _draws_on_plate(L)) < 0.6 * s.length]


def show_lone_instruments(shots: Sequence[Shot], layers: List[Dict[str, Any]], notes: List[str]) -> int:
    """A gauge (or survival card) steps back over diagram plates, but a CSV hud row usually sits on a plate of its own: there it is the
    plate's only content and stays on (hide_on_plates False), held to the plate's end. Over a plate that has a diagram it still steps back."""
    shown = 0
    for L in layers:
        if L.get("type") not in PLATE_HUDS or L.get("hide_on_plates") is False:
            continue
        on = [s for s in shots if s.kind == "plate" and not s.extra.get("lockup") and _overlap(s, L) > 0.3]
        if not on or any(_overlap(s, D) > 0.3 for s in on for D in layers if D.get("type") in DIAGRAMS):
            continue
        L["hide_on_plates"] = False
        last = max(on, key=lambda s: s.end)
        if L["type"] == "tm_gauge" and _bare_plate(last) and L["end"] < last.end:
            L["end"] = round(last.end, 3)
        notes.append(f"plan: the {L['type'][3:]} at {L['start']:.1f}s is its plate's only content: it stays on over it")
        shown += 1
    return shown


def merge_bare_plates(shots: List[Shot], layers: List[Dict[str, Any]], notes: List[str]) -> List[Shot]:
    """A diagram row carved into a CSV plate leaves the plate's tail bare (the diagram held 5.5 s, the plate ran on): the tail joins the
    diagram plate before it, whose diagram holds to the new end, while the two together stay within MAX_S."""
    out: List[Shot] = []
    for s in shots:
        prev = out[-1] if out else None
        if prev is not None and prev.kind == "plate" and abs(prev.end - s.start) < 0.05 and s.end - prev.start <= MAX_S and s in empty_plates([s], layers):
            ends = [L for L in layers if L.get("type") in DIAGRAMS and _overlap(prev, L) > 0.3 and abs(float(L["end"]) - prev.end) < 0.4]
            if ends:
                for L in ends:
                    L["end"] = round(s.end, 3)
                notes.append(f"plan: the bare plate at {s.start:.1f}s joins the diagram before it (held to {s.end:.1f}s)")
                prev.end = s.end
                continue
        out.append(s)
    return out


def breathe_black(shots: List[Shot], words: Sequence[Word], layers: Sequence[Dict[str, Any]], notes: List[str]) -> List[Shot]:
    """A black shot is a breath: BLACK_MAX_S (or its title card and a beat). The rest of a longer one goes to the next shot when it is
    short, else to a plate that fill_empty_plates then gives its content (a distance scale or a picture of what is said there)."""
    out: List[Shot] = []
    for i, s in enumerate(shots):
        out.append(s)
        if s.kind != "black":
            continue
        cards = [float(L["end"]) for L in layers if L.get("type") == "tm_title" and s.start - 0.5 <= float(L["start"]) <= s.start + 1.0]
        cap = round(max([s.start + BLACK_MAX_S] + [e + 0.3 for e in cards]), 3)
        if s.end - cap < 1.0:
            continue
        text = " ".join(w.text for w in words if cap - 0.05 <= w.start < s.end - 0.05)
        nxt = shots[i + 1] if i + 1 < len(shots) else None
        if not text.strip() and nxt is None:
            continue                       # the last seconds after the final words: the video ends on black
        was = s.length
        if nxt is not None and (s.end - cap < 2.5 or not text.strip()):
            nxt.start = cap
            notes.append(f"plan: the black at {s.start:.1f}s is a breath ({cap - s.start:.1f} s, was {was:.1f} s); the next shot comes in earlier")
        else:
            prev = shots[i - 1] if i else None
            out.append(Shot(id="", start=cap, end=s.end, kind="plate", tint="cool", text=text, place=(prev.place if prev else "") or s.place,
                            cite=("DIAGRAM", "")))
            notes.append(f"plan: the black at {s.start:.1f}s is a breath ({cap - s.start:.1f} s, was {was:.1f} s); a picture of what is said takes the rest")
        s.end = cap
    return out


def fill_empty_plates(shots: List[Shot], words: Sequence[Word], layers: List[Dict[str, Any]], mode: str, notes: List[str]) -> int:
    """A plate is the dark ground a diagram is drawn on: one with nothing drawn on it (a shot CSV can ask for a plate with only a caption)
    is an empty screen. If a distance is spoken on it (or just before), it gets the distance scale the reference draws (V2/V3: the
    Moon, the Sun, Neptune and the stars in light-travel time, a marker landing on the number); otherwise it becomes a picture of
    what is said. Its captions and callouts stay on top."""
    metrics = [m for m in nr.extract_metrics(list(words)) if m.kind in ("distance", "light") and m.value > 0]
    fixed = 0
    for s in empty_plates(shots, layers):       # something drawn over most of a plate keeps it (a title card over its first second does not)
        inside = [m for m in metrics if s.start - 0.5 <= m.t < s.end - 0.3]         # said on the plate first, else just before it
        before = [m for m in metrics if s.start - 15.0 <= m.t < s.start - 0.5]
        m = inside[0] if inside else before[-1] if before else None
        secs = (m.value if m.kind == "light" else m.value / LIGHT_KM_S) if m else 0.0
        if m and 0.05 <= secs <= 3.2e8:
            marks = [{"v": v, "label": lab, "sub": sub} for v, lab, sub in nr.LANDMARKS if not 0.6 < secs / v < 1.6]
            close = next((lab for v, lab, _ in nr.LANDMARKS if 0.6 < secs / v < 1.6), "")
            marks.append({"v": secs, "label": close or "HERE", "sub": f"{m.shown} {m.unit}".strip(), "color": "amber"})
            layers.append({"type": "tm_logaxis", "min": 0.1, "max": 3.2e8, "marks": marks, "start": round(s.start, 3), "end": round(s.end, 3),
                           "keys": [{"t": round(max(s.start + 0.35, m.t - LEAD_S), 3), "v": secs}],
                           "node_label": "YOU" if re.search(r"\byou\b", s.text, re.I) else "", "fade_in": 0.05, "fade_out": 0.05})
            s.cite = ("DIAGRAM", "DISTANCES IN LIGHT-TRAVEL TIME, LOGARITHMIC SCALE")
            notes.append(f"shot {s.id}: an empty plate gets the distance scale ({m.shown} {m.unit})")
        else:
            fields = classify(s.text or s.place or "space", flow_video=mode != "images", topic=s.place)
            for k, v in fields.items():
                setattr(s, k, v)
            notes.append(f"shot {s.id}: an empty plate shows a picture of what is said instead")
        fixed += 1
    return fixed


# ---- the plan ------------------------------------------------------------------------------------------------------------------
def _busy(spans: Sequence[Tuple[float, float]], a: float, b: float, pad: float = 0.0) -> bool:
    return any(a < y + pad and x - pad < b for x, y in spans)


def plan(raw_words: Sequence[Any], script: str, duration: float, title: str = "", *, flow_video: "bool | str" = "both",
         shots: Optional[List[Shot]] = None, extra_layers: Optional[List[Dict[str, Any]]] = None,
         extra_plates: Optional[List[Shot]] = None, auto: bool = True) -> ShotPlan:
    """Narration -> ShotPlan. `shots` (from a shot CSV) are used as written; without them the planner builds the shot list."""
    notes: List[str] = []
    mode = flow_mode(flow_video)
    flow_video = mode == "videos"
    words = nr.words_of(raw_words, script)
    duration = float(duration or (words[-1].end if words else 0.0))
    cl, sn = nr.clauses(words), nr.sentences(words)
    text_all = " ".join(w.text for w in words) or script
    metrics = nr.extract_metrics(words) if auto else []

    if shots is None:
        cuts = cut_points(words, duration)
        shots, topic, world_topic = [], "", ""
        for a, b in zip(cuts, cuts[1:]):
            ws = [w for w in words if a - 0.05 <= w.start < b - 0.05]
            text = " ".join(w.text for w in ws)
            # the sentence(s) this shot is part of decide what it is about (a cut can fall inside a sentence)
            whole = " ".join(nr.span_text(words, x, y) for x, y in sn if words[y].end > a + 0.3 and words[x].start < b - 0.3) or text
            fields = classify(whole, flow_video=flow_video, topic=topic, world_topic=world_topic)
            w_ = _world(whole)
            if w_:
                world_topic = w_[1].replace("THE ", "").title()
            if fields.get("place") and fields["kind"] != "plate":
                topic = fields.get("name") or fields["place"]
                if fields["kind"] in ("image", "video") and MISSIONS_NO_MODEL.search(whole):
                    topic = f"{topic} lander" if re.search(r"\blander|landed|surface\b", whole, re.I) else topic
            shots.append(Shot(id="", start=a, end=b, text=text, extra={"about": whole}, **fields))
    else:
        for s in shots:
            if not s.text:
                s.text = " ".join(w.text for w in words if s.start - 0.2 <= w.start < s.end - 0.05)

    layers: List[Dict[str, Any]] = list(extra_layers or [])
    for pl in extra_plates or []:                         # a diagram the CSV asked for: its plate is a shot
        shots = carve(shots, pl, force=True) or shots
    for L in layers:
        # a plate that absorbed a short remnant before it starts earlier than its template: the template starts with it (cues kept on their words)
        if L.get("type") == "tm_template" and L.get("plate"):
            host = next((s for s in shots if s.kind == "plate" and s.start - 1e-6 <= L["start"] < s.end), None)
            if host and host.start < L["start"] - 0.05:
                d = L["start"] - host.start
                L["start"] = round(host.start, 3)
                L["cues"] = {k: round(v + d, 3) for k, v in (L.get("cues") or {}).items()}
    plates: List[Tuple[float, float]] = [(s.start, s.end) for s in shots if s.kind == "plate"]
    plate_budget = PLATE_SHARE_MAX * duration - sum(b - a for a, b in plates)

    # diagrams: a ratio, a light-time distance or a composition is shown as the mechanism (a plate), not described
    sentence_of = lambda i: next(((a, b) for a, b in sn if a <= i <= b), (i, i))   # noqa: E731
    for m in metrics:
        # judged on the words around the number: with no punctuation a "sentence" runs for minutes, and "300 years just to reach" the
        # Oort cloud became a light time because "light" was said somewhere in it (project #016)
        near = nr.span_text(words, max(0, m.i0 - 12), min(len(words) - 1, m.i1 + 4))
        if m.kind == "duration" and m.value >= 1.0 and re.search(r"\blight\b.{0,60}\b(takes?|took|reach\w*|travel\w*)\b|\b(takes?|took)\b.{0,40}\bfor (the )?light\b",
                                                              near, re.I):
            m.kind = "light"                       # "light takes eight minutes": a distance in light-travel time (seconds of it)
        if m.kind not in ("ratio", "light", "percent"):
            continue
        a, b = sentence_of(m.i0)
        ca = next((x for x, y in cl if x <= m.i0 <= y), m.i0)
        t0 = max(0.0, (words[ca - 1].end + words[ca].start) / 2 if ca > 0 and words[ca].start - words[ca - 1].end > 0.1 else words[ca].start - 0.06)   # cut between clauses
        t1 = min(max(t0 + PLATE_MIN_S, words[b].end + 0.4), t0 + PLATE_MAX_S)
        later = [x for x, _ in plates if x > t0 + 0.5]
        if later and min(later) - 0.05 < t1:
            t1 = min(later) - 0.05
        sent = nr.span_text(words, a, b)
        if t1 - t0 < 2.5 or t0 < 3.0 or t1 > duration - 0.5 or _busy(plates, t0, t1, 0.05) or plate_budget < t1 - t0:
            continue
        timing = {"start": round(t0, 3), "end": round(t1, 3), "fade_in": 0.05, "fade_out": 0.05}
        if m.kind == "percent":
            pcts = [x for x in metrics if x.kind == "percent" and sentence_of(x.i0) == (a, b)]
            if len(pcts) < 2 and not re.search(r"\b(carbon dioxide|nitrogen|oxygen|argon|hydrogen|helium|methane|made of|composed)\b", sent, re.I):
                continue
            names = re.findall(r"\b(carbon dioxide|nitrogen|oxygen|argon|hydrogen|helium|methane|sulfur dioxide|water vapou?r|water|iron|nickel|rock)\b", sent, re.I)
            parts, total = [], 0.0
            for x, nm in zip(pcts, names + ["OTHER"] * 4):
                parts.append({"label": nm.upper(), "pct": float(x.shown.replace(",", ""))})
                total += parts[-1]["pct"]
            if total < 99.5 and 0 < total < 100:
                parts.append({"label": "OTHER", "pct": round(100 - total, 2), "color": "#9AA6B5"})
            if len(parts) < 2:
                continue
            diag = {"type": "tm_composition", "title": "WHAT IT IS MADE OF", "parts": parts, **timing}
            cite = "COMPOSITION"
        elif m.kind == "light":
            marks = [{"v": v, "label": lab, "sub": sub} for v, lab, sub in nr.LANDMARKS if not 0.6 < m.value / v < 1.6]
            near = next((lab for v, lab, _ in nr.LANDMARKS if 0.6 < m.value / v < 1.6), "")
            marks.append({"v": m.value, "label": near or nr._subject(sent, [], t0), "sub": m.label, "color": "amber"})
            diag = {"type": "tm_logaxis", "min": 0.1, "max": 3.2e8, "marks": [x for x in marks if x["label"] or x["sub"]],
                    "keys": [{"t": round(max(t0 + 0.35, m.t - LEAD_S), 3), "v": m.value}], "node_label": "YOU" if re.search(r"\byou\b", sent, re.I) else "", **timing}
            cite = "DISTANCES IN LIGHT-TRAVEL TIME, LOGARITHMIC SCALE"
        else:
            than = re.search(r"\bthan\s+(?:on\s+|at\s+|in\s+)?(?:the\s+)?([A-Za-z']+(?:\s+[A-Z][a-z']+)?)", sent)
            left = (than.group(1) if than else "EARTH").upper().strip("'S")
            here = nr._subject(sent, [], t0, exclude=left) or "HERE"
            airy = re.search(r"\b(air|atmospher\w*|pressure|thick|thin|dense|gas)\b", sent, re.I)
            k = max(1.0, m.value)
            diag = {"type": "tm_compare", "mode": "particles" if airy else "bars", **timing,
                    "left": {"label": left, "value": "1×", "n": 6 if airy else 0, "amount": 1, "color": "cyan"},
                    "right": {"label": here, "value": f"{m.shown}×", "n": int(min(900, 6 * k)) if airy else 0, "amount": k, "color": "amber"}}
            cite = "TO SCALE" if k <= 50 or airy else "LOGARITHMIC SCALE"
        warm = bool(re.search(r"\b(venus|sun|mercury|lava|heat|hot)\b", sent, re.I))
        carved = carve(shots, Shot(id="", start=t0, end=t1, kind="plate", tint="warm" if warm else "cool", text=sent, cite=("DIAGRAM", cite)))
        if carved is None:
            continue
        shots = carved
        layers.append(diag)
        plates.append((t0, t1))
        plate_budget -= t1 - t0
        m.extra["shown"] = True
    # "galaxies ... never reach": Earth, a line leaving it, and the deep field as a feathered disc (V2 0:22)
    if auto and not any(L["type"] == "tm_discmap" for L in layers):
        for a, b in sn:
            sent = nr.span_text(words, a, b)
            if not DEEP.search(sent):
                continue
            t0 = max(0.0, words[a].start - 0.06)
            t1 = min(t0 + 5.5, duration - 0.5)
            if t0 < 3.0 or t1 - t0 < 3.5 or _busy(plates, t0, t1, 0.05):
                continue
            carved = carve(shots, Shot(id="", start=t0, end=t1, kind="plate", tint="cool", text=sent, cite=("DIAGRAM", "GALAXIES: NASA, ESA, CSA, STSCI"),
                                       asset="nasa_image:James Webb Space Telescope first deep field galaxies", name="JWST DEEP FIELD"))
            if carved is None:
                continue
            shots = carved
            layers.append({"type": "tm_discmap", "earth": "EARTH", "keys": [{"t": round(t0 + 1.0, 3), "reach": 0.5}], "start": round(t0, 3), "end": round(t1, 3),
                           "fade_in": 0.05, "fade_out": 0.05})
            plates.append((t0, t1))
            break
    # template visuals the narration asks for (whatif/templates.py: concept templates with a trigger -- light bending, a spacetime well, the
    # river of space ...): one plate each, at most one every 40 s and never the same one twice, inside the plate budget
    if auto:
        from . import templates as tpl
        used: List[str] = [L["template"]["id"] for L in layers if L.get("type") == "tm_template"]
        last = -1e9
        for a, b in sn:
            sent = nr.span_text(words, a, b)
            t0 = max(0.0, words[a].start - 0.06)
            if t0 - last < 40.0 or t0 < HOOK_S:
                continue
            t = tpl.match(sent, used, text_all)
            if t is None:
                continue
            t1 = min(t0 + max(float(t.get("hold", 6)), words[b].end + 0.4 - t0), t0 + float(t.get("max_s", 12)), duration - 0.5)
            later = [x for x, _ in plates if x > t0 + 0.5]
            if later and min(later) - 0.05 < t1:
                t1 = min(later) - 0.05
            if t1 - t0 < 3.5 or _busy(plates, t0, t1, 0.05) or plate_budget < t1 - t0:
                continue
            carved = carve(shots, Shot(id="", start=t0, end=t1, kind="plate", tint=t.get("tint", "cool"), text=sent, cite=tpl.split_cite(t.get("cite", ""))), force=True)
            if carved is None:
                continue
            shots = carved
            it = type("Row", (), {"id": t["id"], "hold": t1 - t0, "extra": {}, "_auto": True, **{c: None for c in tpl.COLUMNS}})()
            L, _ = tpl.layer_for(it, t0, t1, words)
            layers.append(L)
            plates.append((t0, t1))
            plate_budget -= t1 - t0
            used.append(t["id"])
            last = t0
            notes.append(f"template {t['id']} at {t0:.1f}s for: {sent[:70]}")
    shots = sorted(shots, key=lambda s: s.start)
    for i, s in enumerate(shots, 1):
        s.id = f"s{i}"
        s.text = " ".join(w.text for w in words if s.start - 0.05 <= w.start < s.end - 0.05)
    spans = [(s.start, s.end) for s in shots]
    shot_at = lambda t: next((s for s in shots if s.start <= t < s.end), shots[-1])   # noqa: E731
    on_plate = lambda t0, t1=None: any(s.kind == "plate" and s.start - 0.05 < (t1 or t0) and t0 < s.end + 0.05 for s in shots)   # noqa: E731

    # named things: the lower-left lockup (a craft's name, an archive picture's subject) as the shot opens
    shown_at: Dict[str, float] = {}
    for s in shots:
        name = screen_name(s.name)
        if name and s.kind in ("craft", "image", "video", "hero") and t_ok(shown_at.get(name), s.start):
            shown_at[name] = s.start
        else:
            name = ""
        if s.kind in ("craft", "image", "video", "hero") and name and s.cite[0] in ("ILLUSTRATION", "REAL IMAGE", "AI ILLUSTRATION") and s.length >= 4.0:
            dated = re.search(r"\b(\d{1,2} )?(january|february|march|april|may|june|july|august|september|october|november|december) \d{4}\b|\b(1[5-9]|20)\d\d\b", s.text, re.I)
            # a craft's 3D model: the big name at the lower left; a picture of it: the lockup centred at the bottom (V1 0:01.5); a real photograph:
            # its caption centred under the letterboxed picture (V1 6:40)
            real = s.cite[0] == "REAL IMAGE"
            L = {"type": "tm_caption", "text": name, "sub": dated.group(0).upper() if dated else "", "start": round(s.start + 0.35, 3),
                 "end": round(min(s.end - 0.2, s.start + 5.0), 3), "fade_in": 0.05, "fade_out": 0.3, "z": 5}
            L.update({"size": "large"} if s.kind == "craft" else {"size": "photo"} if real else {"size": "small", "anchor": "bc"})
            layers.append(L)

    # the act's instrument and the opening / closing cards
    beats_like = [type("B", (), {"start": s.start, "end": s.end, "place": s.place, "text": s.text})() for s in shots]
    beat_end = lambda t: next((s.end for s in shots if s.start <= t < s.end), duration)   # noqa: E731
    gauge = nr._gauge(words, sn, metrics, duration, notes, beat_end, ()) if auto else []
    hud_tl = auto and nr._survival_wanted(text_all)
    survival = nr._survival(words, sn, metrics, duration, notes, beat_end) if hud_tl else []
    if survival:
        # the survival clock's own scene (V1 0:25.5-0:31): the card centred and large on a dark warm plate while the verdict lands, then it
        # moves to the corner for the act. The plate is a shot (its lockup flag keeps the instruments on over it).
        sv = survival[0]
        first = next((x for x in sv["states"] if x["verdict"] != "—"), None)
        if first:
            t0 = max(0.0, first["t"] - 0.15)
            later = [x.start for x in shots if x.kind == "plate" and x.start > t0 + 1.0]
            t1 = min(t0 + 5.5, duration - 0.5, (min(later) - 0.05) if later else 1e9)       # never into the next diagram
            if t1 - t0 >= 3.5 and not _busy([(x.start, x.end) for x in shots if x.kind == "plate"], t0, t1, 0.05):
                carved = carve(shots, Shot(id="", start=t0, end=t1, kind="plate", tint="warm", cite=("ILLUSTRATION", ""), extra={"lockup": True}), force=True)
                if carved:
                    shots = carved
                    for i, x in enumerate(shots, 1):
                        x.id = f"s{i}"
                        x.text = " ".join(w.text for w in words if x.start - 0.05 <= w.start < x.end - 0.05)
                    sv["intro"] = {"start": round(t0, 3), "end": round(t1 - 0.2, 3)}
                    sv["start"] = round(t0, 3)
                    notes.append(f"plan: the survival clock opens as its own scene at {t0:.1f}-{t1:.1f}s")
    duals = [] if (hud_tl or not auto) else nr._dual_clocks(words, sn, metrics, duration, text_all, notes)
    if auto and not hud_tl and not duals:
        duals = nr.light_clock(words, sn, metrics, duration, text_all, notes)     # V3's light-from-Earth clock
    for m in metrics:
        if gauge and m.kind == "distance" and any(abs(k["t"] - (m.t - LEAD_S)) < 1e-3 for k in gauge[0]["keys"][1:]):
            m.extra["shown"] = True
    authored: List[Tuple[float, float]] = []
    if title and not any(L.get("type") == "tm_title" for L in layers):
        q = next(((a, b) for a, b in sn if words[a].start > 4.0 and words[b].text.endswith("?")), None) if duration > 40 else None
        t0 = words[q[0]].start - LEAD_S if q else (next((words[b].end + 0.1 for a, b in sn if words[b].end > 10.0), None) if duration > 40 else 0.3)
        if t0 is not None and not on_plate(t0, t0 + 2.5):
            t1 = max(t0 + 2.5, words[q[1]].end + 0.3) if q else t0 + 4.5
            layers.append({**nr._title_lines(title), "type": "tm_title", "start": round(t0, 3), "end": round(min(duration, t1), 3), "fade_in": 0.05, "fade_out": 0.3, "z": 6})
            authored.append((t0, t1))
    outro = next(((a, b) for a, b in reversed(sn) if re.search(r"\bcomments?\b", nr.span_text(words, a, b), re.I) and words[a].start > duration - 25), None)
    if outro:
        q = next(((a, b) for a, b in reversed(sn) if b < outro[0] and nr.span_text(words, a, b).rstrip().endswith("?")), None)
        if q and len(nr.span_text(words, *q).split()) <= 12:
            layers.append({**nr._title_lines(nr.span_text(words, *q)), "sub": "TELL ME IN THE COMMENTS", "type": "tm_title", "start": round(words[q[0]].start - LEAD_S, 3),
                           "end": round(min(duration, words[outro[1]].end + 1.5), 3), "fade_in": 0.05, "fade_out": 0.5, "z": 6})

    # every other spoken measurement: a callout a beat before it is heard -- on a model, a world or the sky, as the reference's information
    # block at the left (kicker from the words before the number, sub-line from the words after it: whatif/typeset.py)
    from .typeset import HOSTS as TYPE_HOSTS, number_words
    last_end = -1e9
    for m in metrics:
        if m.extra.get("shown") or (m.kind == "duration" and m.value < 1.0):
            continue
        if any(L["type"] == "tm_metric" and abs(float(L.get("start", 0)) - m.t) < 12.0
               and re.search(rf"(?<![\d.,]){re.escape(m.shown)}(?![\d])", f"{L.get('text', '')} {L.get('value', '')}") for L in layers):
            continue                       # the CSV already puts this number on screen (a second "4.37" a few seconds later is noise)
        t0 = max(0.0, m.t - LEAD_S)
        if t0 < 1.0 or t0 - last_end < nr.METRIC_GAP_S - nr.METRIC_MIN_S or on_plate(t0, t0 + 1.0) or _busy(authored, t0 - 0.2, t0 + 0.5):
            continue
        nxt = next((x.t for x in metrics if x.t > m.t + 0.5 and not x.extra.get("shown")), duration)
        t1 = min(max(t0 + nr.METRIC_MIN_S, m.t_end + 1.2), t0 + nr.METRIC_MAX_S, nxt - LEAD_S - 0.05, duration - 0.3)
        if t1 - t0 < 1.6:
            continue
        L = {"type": "tm_metric", "value": ("≈ " if m.approx and m.kind in ("distance", "light") else "") + m.shown + ("×" if m.kind == "ratio" else ""),
             "unit": "" if m.kind == "ratio" else m.unit, "sub": nr.sub_line(words, m, cl), "sub_color": "cyan" if m.kind in ("speed", "light") else "amber",
             "anchor": CALLOUT_ANCHORS[len([x for x in layers if x["type"] == "tm_metric"]) % len(CALLOUT_ANCHORS)],
             "size": "large" if len(m.label) <= 14 else "medium", "start": round(t0, 3), "end": round(t1, 3), "fade_in": 0.05, "fade_out": 0.3, "z": 5}
        if shot_at(m.t).kind in TYPE_HOSTS:
            kicker, sub = number_words(words, cl, m)
            L.update({"anchor": "left", "kicker": kicker, "sub": sub or L["sub"], "sub_color": "amber", "typeset": True})
        layers.append(L)
        last_end = t1
        m.extra["shown"] = True
    for T_ in [L for L in layers if L["type"] == "tm_title"]:       # the title card has the frame to itself: an instrument pinned then comes in after it
        for H in survival + gauge + duals:
            if H["start"] < T_["end"] and T_["start"] < H["start"] + 1.0:
                H["start"] = round(T_["end"], 3)
                for key in ("states", "keys"):
                    if isinstance(H.get(key), list) and H[key]:
                        H[key][0]["t"] = max(H[key][0]["t"], H["start"])
    layers += survival + gauge + duals
    # the instruments own the corners they sit in: a callout moves to the top centre
    for L in layers:        # the survival card owns the top-left corner (to y 28 %), the gauge the right edge: a callout never sits under them
        if L["type"] != "tm_metric":
            continue
        if L.get("anchor") == "upper_right" and any(x["type"] == "tm_gauge" and x["start"] < L["end"] and L["start"] < x["end"] for x in survival + gauge):
            L["anchor"] = "mid"
    # more graphics from the narration (whatif/engage.py): dated captions, part headers, question cards, odds dials, the counted number look
    if auto:
        from .engage import engage

        shots, plate_budget = engage(shots, layers, words, sn, metrics, duration, notes, carve=carve, shot_cls=Shot, plate_budget=plate_budget,
                                     span_text=nr.span_text, hook_s=HOOK_S)
        for i, x in enumerate(shots, 1):
            x.id = f"s{i}"
            x.text = " ".join(w.text for w in words if x.start - 0.05 <= w.start < x.end - 0.05)
    # a death or a silence: into black in the pause, out when the next words start
    fades = 0
    for a, b in (sn if auto else []):
        if fades >= nr.FADE_MAX:
            break
        if not re.search(nr.SILENCE, nr.span_text(words, a, b), re.I):
            continue
        t0, nxt = words[b].end + 0.05, (words[b + 1].start if b + 1 < len(words) else duration)
        if nxt - t0 < 0.05 or on_plate(t0, t0 + 1.6) or t0 > duration - 1.5:
            continue
        fi = min(0.6, max(0.3, nxt - t0))
        layers.append({"type": "tm_fade", "start": round(t0, 3), "end": round(min(max(t0 + fi + 0.5, nxt + 0.4), duration), 3), "fade_in": round(fi, 2), "fade_out": 0.45, "z": 20})
        fades += 1

    # a stretch of a shot longer than MAX_HOLD_S with nothing new: a context lockup on a clause start
    def changes() -> List[float]:
        out = [s.start for s in shots] + [duration]
        for L in layers:
            if L["type"] in ("tm_metric", "tm_caption", "tm_title", "tm_fade") or L["type"] in ("tm_logaxis", "tm_compare", "tm_composition", "tm_bars", "tm_curve", "tm_dial", "tm_wave", "tm_section", "tm_grid", "tm_orbitmap", "tm_phase", "tm_timeline", "tm_discmap", "tm_annotate"):
                out.append(float(L["start"]))
            for key in ("states", "keys"):
                if L["type"] in ("tm_survival", "tm_gauge") and L.get(key):
                    out += [float(k["t"]) for k in L[key]]
        return sorted(set(round(x, 2) for x in out))
    fills = 0
    ts = changes()
    for x, y in zip(ts, ts[1:]):
        t = x
        while y - t > MAX_HOLD_S:
            want = t + min(4.4, (y - t) / 2)
            starts = [(words[a].start, a, b) for a, b in cl if t + 2.8 <= words[a].start <= y - 2.2]
            if not starts:
                break
            ts0, a, b = min(starts, key=lambda s: abs(s[0] - want))
            phrase = [re.sub(r"[^\w'°%.\-]", "", w.text).strip(".-") for w in words[a:b + 1]]
            phrase = [p for p in phrase if p]
            while phrase and phrase[0].lower() in nr.FILLER:
                phrase.pop(0)
            cut = phrase[:6]
            while len(cut) > 2 and (cut[-1].lower() in nr.FILLER or cut[-1].lower() in nr.TAIL_WORDS):
                cut.pop()
            if len(cut) < 2 or on_plate(ts0, ts0 + 2.0) or any(L["type"] in ("tm_caption", "tm_title") and L["start"] < ts0 + 4.2 and ts0 - LEAD_S < L["end"] for L in layers):
                t = ts0 + 0.01
                continue
            subj = shot_at(ts0).place
            layers.append({"type": "tm_caption", "auto": True, "text": " ".join(cut).upper(), **({"sub": subj.upper()} if subj and subj.upper() not in " ".join(cut).upper() else {}),
                           "start": round(ts0 - LEAD_S, 3), "end": round(min(y - 0.2, ts0 + 5.5), 3), "fade_in": 0.05, "fade_out": 0.3, "z": 5})
            fills += 1
            t = ts0
    # text on every picture: a picture shot still bare gets the narrator's key words (whatif/engage.py), held to its end
    from .engage import direct, readout_card, count_up

    if auto:
        readout_card(layers, metrics, duration, notes, title=title)   # a card pinned top-right that updates as the narration gives values
    count_up(layers)                                          # every number counts up to its value
    direct(shots, layers, words, duration, notes)            # authored lines in varied text layouts, never the same layout within a minute
    # a world followed by something else: the camera pushes into its disc, once a minute at most
    last_push = -60.0
    for s, nx in zip(shots, shots[1:]):
        if s.kind == "globe" and nx.kind != "globe" and s.end - last_push >= 60.0 and s.length >= 4.0:
            s.exit, last_push = "push", s.end
    shots = breathe_black(shots, words, layers, notes)
    show_lone_instruments(shots, layers, notes)
    shots = merge_bare_plates(shots, layers, notes)
    for i, s in enumerate(shots, 1):
        s.id = f"s{i}"
    fill_empty_plates(shots, words, layers, mode, notes)      # first: a plate given its diagram is never cut by the opening rule
    shots = hook(shots, words, layers, mode, notes)
    shots = moving_open(shots, words, mode, notes)
    for i, s in enumerate(shots, 1):
        s.id = f"s{i}"
    # the reference's information block for the names and terms the narration says (whatif/typeset.py), once the shots are final
    if auto:
        from .typeset import typeset

        typeset(shots, layers, words, metrics, duration, notes)
    mix_flow(shots, mode, notes)
    shots = split_long_videos(shots, words, layers, notes)
    limit_flow(shots, notes)
    for i, s in enumerate(shots, 1):
        s.id = f"s{i}"
    shots = merge_beats(shots, notes)
    shots = absorb_short(shots, notes)
    for i, s in enumerate(shots, 1):
        s.id = f"s{i}"
    changed = vary(shots)
    notes.append(f"plan: {len(shots)} shots (median {sorted(x.length for x in shots)[len(shots) // 2]:.1f} s), "
                 f"{sum(1 for s in shots if s.kind == 'plate')} diagram plate(s), {sum(1 for L in layers if L['type'] == 'tm_metric')} callout(s), "
                 f"{fills} context lockup(s), {changed} repeat(s) re-framed")
    for s in empty_plates(shots, layers):
        notes.append(f"WARNING shot {s.id} ({s.start:.1f}-{s.end:.1f}s) is an empty plate: nothing is drawn on most of it")
    from .engage import coverage
    notes.append(f"plan: text or graphics on screen {100 * coverage(shots, layers, duration):.0f}% of the video")
    return ShotPlan(shots=shots, layers=layers, duration=duration, title=title, notes=notes, words=words)


def report(p: ShotPlan) -> Dict[str, Any]:
    """Numbers to hold against docs/whatif/reference_targets.json (and the check a plan must pass)."""
    import statistics

    lens = [s.length for s in p.shots]
    gaps = {w.end: (nxt.start - w.end) for w, nxt in zip(p.words, p.words[1:])}
    inside = 0
    for s in p.shots[1:]:
        # a cut is in a pause when the words around it are 0.12 s or more apart (as the audio measurement of the references counts it), else in speech
        prev = [w for w in p.words if w.end <= s.start + 0.06]
        nxt = [w for w in p.words if w.start >= s.start - 0.06]
        gap = (nxt[0].start - prev[-1].end) if prev and nxt else 1.0
        if gap < 0.12:
            inside += 1
    times = sorted({round(s.start, 1) for s in p.shots} | {round(float(L["start"]), 1) for L in p.layers if L["type"] in
                   ("tm_metric", "tm_caption", "tm_title", "tm_logaxis", "tm_compare", "tm_composition", "tm_fade")})
    gap_list = [b - a for a, b in zip(times, times[1:])]
    return {"shots": len(p.shots), "median_shot_s": round(statistics.median(lens), 2), "mean_shot_s": round(sum(lens) / len(lens), 2),
            "hard_cuts_per_min": round(len(p.shots) / p.duration * 60, 1), "cuts_inside_speech": inside,
            "cuts_inside_speech_share": round(inside / max(1, len(p.shots) - 1), 2),
            "visual_changes_per_min": round(len(times) / p.duration * 60, 1), "max_gap_between_changes_s": round(max(gap_list or [0]), 1),
            "plate_share": round(sum(s.length for s in p.shots if s.kind == "plate") / p.duration, 2),
            "empty_plates": len(empty_plates(p.shots, p.layers)),
            "longest_black_s": round(max([s.length for s in p.shots if s.kind == "black"] or [0.0]), 2),
            "kinds": {k: sum(1 for s in p.shots if s.kind == k) for k in sorted({s.kind for s in p.shots})}}
