"""A sentence -> a 3D scene spec (whatif-engine/lib/scene_gen.mjs draws it). From the sentence's own properties, not from a model list:
what kind of world (gas, rock, ice, ocean, lava, sun, haze), its colours, rings, storms, a craft and its kind, the air around it (clouds, rain,
dust), how it moves (falling, orbiting, approaching) and the camera. Named real worlds only supply default colours; any other name or an
invented world is built from the words around it, and a hash of the sentence seeds the details so two scenes never match.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable, Dict, Optional, Tuple

# real worlds: only DEFAULT looks (a sentence's own colour/property words override them)
KNOWN = {
    "jupiter": ("gas", ["#e6c9a0", "#b5703d", "#f3e6cf", "#c88a5a"], {"storm": 0.8, "bands": 11, "atmosphere": "#e8b878"}),
    "saturn": ("gas", ["#e8d8a8", "#c8a868", "#f4ecd0", "#b89858"], {"bands": 14, "rings": {"inner": 1.35, "outer": 2.4, "tilt": 18}, "atmosphere": "#e8d8a8"}),
    "uranus": ("ice", ["#a8dce4", "#7cc0cc", "#d8f2f4"], {"atmosphere": "#8fe0ee"}), "neptune": ("gas", ["#2f55c8", "#4a78e8", "#9ab8ff", "#1c3a9a"], {"atmosphere": "#6a8ae8", "bands": 6}),
    "mars": ("rock", ["#a8552e", "#c97a4a", "#5e3320"], {"craters": 0.4, "atmosphere": "#e8a070"}), "venus": ("haze", ["#e8c88a", "#d0a060", "#f4e2b8"], {"atmosphere": "#f0c890"}),
    "mercury": ("rock", ["#8a8680", "#b9b4ab", "#5d5953"], {"craters": 0.9}), "moon": ("rock", ["#8a8a88", "#bdbdbb", "#5a5a58"], {"craters": 0.8}),
    "earth": ("ocean", ["#1f4f86", "#3e7a3c", "#c9b98a", "#f4f4f4"], {"clouds": 0.55, "atmosphere": "#7fb0ff"}), "europa": ("ice", ["#e8e2d4", "#b89a78", "#f6f2ea"], {}),
    "io": ("lava", ["#2a2410", "#d8b020", "#ff7a1a"], {}), "titan": ("haze", ["#d89a3c", "#b87828", "#e8b860"], {"atmosphere": "#e8a040"}),
    "pluto": ("ice", ["#d8c0a8", "#a88060", "#f2e6da"], {}), "ganymede": ("rock", ["#7a6e60", "#a89c8c", "#4a4238"], {"craters": 0.6}), "callisto": ("rock", ["#55493e", "#7a6c5c", "#352d26"], {"craters": 1.0}),
    "enceladus": ("ice", ["#f4f8ff", "#cfe0f2", "#ffffff"], {}), "ceres": ("rock", ["#7a7670", "#a8a49c", "#4a4642"], {"craters": 0.7}), "sun": ("sun", ["#ff9a1f", "#ffd36b", "#fff2c4"], {"atmosphere": "#ffb347"}),
}
TYPE_WORDS = (("sun", r"\b(sun|star|stellar|sunlike|solar surface|photosphere)\b"), ("lava", r"\b(lava|molten|magma|volcan\w*|volcano\w*|fiery|inferno)\b"),
              ("ocean", r"\b(ocean\w*|seas?|water world|blue planet|continents?|oceans)\b"), ("gas", r"\b(gas giant|gas planet|storms?|bands?|swirl\w*|jovian|hydrogen)\b"),
              ("ice", r"\b(ice|icy|frozen|glacier\w*|snow\w*|frost\w*|cold world|ice giant)\b"), ("haze", r"\b(thick atmosphere|haze|hazy|smog|cloud tops?|cloud deck|dense air)\b"),
              ("rock", r"\b(rock\w*|crater\w*|desert|barren|dusty|regolith|asteroid|moon|dead world|surface)\b"))
COLOURS = {"red": "#b8402a", "orange": "#d9793a", "yellow": "#e0c050", "green": "#4f9a5a", "blue": "#2f62c8", "purple": "#7a4ab8", "violet": "#7a4ab8", "pink": "#d878a0",
           "white": "#e8eaee", "black": "#16161a", "grey": "#8a8d92", "gray": "#8a8d92", "brown": "#7a5236", "gold": "#d8b050", "golden": "#d8b050", "crimson": "#a8203a", "teal": "#2a9a9a"}
CRAFTS = (("capsule", r"\b(capsule|re-?entry|heat ?shield|crew module)\b"), ("lander", r"\b(lander|touch(?:ed)? down|landing (?:craft|gear))\b"), ("rover", r"\b(rover|wheels?)\b"),
          ("rocket", r"\b(rocket|launch\w*|booster|liftoff|lift-?off|stage separation)\b"), ("telescope", r"\b(telescope|observatory|mirror)\b"), ("satellite", r"\b(satellite|orbiter|space station)\b"),
          ("probe", r"\b(probe|spacecraft|craft|vessel|ship|capsule|machine|robot\w*)\b"))
PARTICLES = (("rain", r"\b(rain\w*|downpour|acid)\b"), ("snow", r"\b(snow\w*|blizzard|ice crystals?)\b"), ("embers", r"\b(embers?|sparks?|fire|burn\w*|inferno)\b"),
             ("dust", r"\b(dust\w*|sandstorm|ash|debris|particles?)\b"), ("streaks", r"\b(rush\w*|plung\w*|fall\w*|hurtl\w*|speed\w*|fast)\b"))
FALL = re.compile(r"\b(fall\w*|fell|descen\w*|plung\w*|sink\w*|sank|dive\w*|dropp\w*|parachut\w*|crush\w*|deeper|drift\w* down)\b", re.I)
SKY = re.compile(r"\b(clouds?|atmospher\w*|sky|haze|air|storm\w*|wind\w*|rain\w*)\b", re.I)
CAMS = (("pullback", r"\b(pull\w* back|move\w* away|leav\w*|recede\w*|zoom\w* out|farther|further away|shrink\w*)\b"), ("push", r"\b(approach\w*|closer|zoom\w* in|toward\w*|towards|heads? (?:for|into)|nearing|reach\w*)\b"),
        ("flyby", r"\b(fl[yi]\w* (?:past|by)|flyby|swing\w* by|pass\w* (?:by|close))\b"), ("orbit", r"\b(orbit\w*|circl\w*|around|revolv\w*|spin\w*|rotat\w*)\b"))
CUT = re.compile(r"\b(inside|interior|core|layers?|beneath the surface|cross.?section|cut.?away|deep below|mantle|crust|within the (?:planet|world|moon|star))\b", re.I)
FIELD = re.compile(r"\b(magnetic|magnetosphere|magnetism|field lines?|radiation belts?|aurora\w*|magnet)\b", re.I)
LAYERS = {
    "rock": [(1.0, "#7a6a5a", "CRUST"), (0.9, "#b06a30", "MANTLE"), (0.55, "#e0902a", "OUTER CORE"), (0.25, "#ffe060", "INNER CORE")],
    "ocean": [(1.0, "#6a5a4a", "CRUST"), (0.9, "#b06a30", "MANTLE"), (0.55, "#e0902a", "OUTER CORE"), (0.25, "#ffe060", "INNER CORE")],
    "lava": [(1.0, "#3a2418", "CRUST"), (0.88, "#c43c0e", "MOLTEN MANTLE"), (0.55, "#ff8a1e", "OUTER CORE"), (0.25, "#fff2a0", "INNER CORE")],
    "ice": [(1.0, "#dce8f2", "ICE SHELL"), (0.88, "#2f62c8", "OCEAN"), (0.6, "#7a6a5a", "ROCKY MANTLE"), (0.22, "#e0902a", "CORE")],
    "gas": [(1.0, "#d9a066", "CLOUD DECK"), (0.82, "#c4623a", "LIQUID HYDROGEN"), (0.55, "#8d3b2a", "METALLIC HYDROGEN"), (0.22, "#e8e0d0", "CORE")],
    "haze": [(1.0, "#d9b070", "CLOUD DECK"), (0.85, "#b8683a", "DENSE ATMOSPHERE"), (0.55, "#8d3b2a", "DEEP LAYER"), (0.22, "#e8e0d0", "CORE")],
    "sun": [(1.0, "#ffb347", "PHOTOSPHERE"), (0.7, "#ff8a1e", "CONVECTION ZONE"), (0.35, "#ffd36b", "RADIATIVE ZONE"), (0.15, "#ffffff", "CORE")]}
ABSTRACT = re.compile(r"\b(percent|billion|million|times|years?|history|money|price|vote|law|decid\w*|why|because|however|think|believe)\b", re.I)


def _seed(text: str) -> int:
    return int(hashlib.sha1(text.lower().encode("utf-8", "ignore")).hexdigest()[:6], 16) % 9973 + 1


def _mix(a: str, b: str, k: float) -> str:
    ca, cb = [int(a[i:i + 2], 16) for i in (1, 3, 5)], [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{int(x + (y - x) * k):02x}" for x, y in zip(ca, cb))


def _palette(tp: str, words: str, base: Optional[list]) -> list:
    cols = [COLOURS[w] for w in re.findall(r"[a-z]+", words.lower()) if w in COLOURS]
    if not cols:
        return base or []
    c = cols[0]
    return [_mix(c, "#000000", 0.25), c, _mix(c, "#ffffff", 0.5), _mix(c, "#ffffff", 0.2)]


def scene_for(text: str) -> Optional[Tuple[Dict[str, Any], float]]:
    """(scene spec, confidence 0..1) for what the sentence describes, or None when it describes nothing drawable (an abstract claim, no world, craft or place)."""
    low = (text or "").lower()
    seed = _seed(text)
    world_name = next((n for n in KNOWN if re.search(rf"\b{n}\b", low)), None)
    low_t = re.sub(r"\b(?:from|near|around|orbit\w*|of|by|like|than|toward\w*|away from|light of) (?:the |any |a |its |their |our |another )?(?:sun|star|stars)\b", " ", low)   # a star named as a reference is not the subject
    counts = [(len(re.findall(rx, low_t)), -i, t) for i, (t, rx) in enumerate(TYPE_WORDS)]
    best = max(counts)
    tp = best[2] if best[0] else None
    craft_kind = next((k for k, rx in CRAFTS if re.search(rx, low)), None)
    sky = bool(SKY.search(low))
    falling = bool(FALL.search(low))
    structural = bool(FIELD.search(low) or (CUT.search(low) and re.search(r"\b(planet|world|moon|star|earth|sun)\b", low)))
    if not (world_name or tp or craft_kind or structural) or (ABSTRACT.search(low) and not (world_name or craft_kind or structural)):
        return None
    spec: Dict[str, Any] = {"seed": seed, "env": {"sky": "space"}, "motion": {}, "light": {}}
    conf = 0.55
    inside = falling and sky          # the narration is inside an atmosphere: clouds streaming past a falling craft
    if world_name or tp:
        base = KNOWN.get(world_name or "", (None, None, {}))
        wt = tp if (tp and not world_name) else (base[0] or tp or "rock")
        w: Dict[str, Any] = {"type": wt, "seed": seed % 97, **{k: v for k, v in (base[2] or {}).items()}}
        pal = _palette(wt, low, base[1])
        if pal:
            w["palette"] = pal
        if wt == "gas" and "storm" not in w and re.search(r"\bstorm", low):
            w["storm"] = 0.7
        if re.search(r"\brings?\b", low) and "rings" not in w:
            w["rings"] = {"inner": 1.35, "outer": 2.3, "tilt": 15 + seed % 30}
        if wt == "ocean" and re.search(r"\b(city|cities|lights?|night)\b", low):
            w["city"] = 0.8
        if wt in ("gas", "ice", "ocean", "haze", "rock") and "atmosphere" not in w and re.search(r"\batmospher\w*|\bair\b|\bglow", low):
            w["atmosphere"] = (w.get("palette") or ["#9fb8ff", "#9fb8ff"])[1]
        spec["world"] = w
        conf = 0.9 if world_name else 0.65
    if craft_kind:
        spec["craft"] = {"kind": craft_kind, "scale": 1.0, "parachute": bool(re.search(r"\bparachut\w*", low))}
        if spec["craft"]["parachute"] and craft_kind == "probe":
            spec["craft"]["kind"] = "capsule"
        conf = max(conf, 0.8)
    spec["layout"] = "craft_over_planet" if ("world" in spec and "craft" in spec) else "craft" if "craft" in spec else "planet"
    if inside or (spec["layout"] == "craft" and (sky or falling)):
        w = spec.get("world", {})
        pal = w.get("palette") or ["#9aa3b2", "#cfd6e0"]
        top, hor = _mix(pal[0], "#000000", 0.45), _mix(pal[min(2, len(pal) - 1)], "#8a8f99", 0.35)
        if re.search(r"\b(hot|heat\w*|fire|burn\w*|scorch\w*|molten|boil\w*|inferno)\b", low):
            top, hor, pal = "#3a0f08", "#c8581c", ["#6a2410", "#d8742c", "#ffb060", "#a8401c"]
        spec["env"] = {"sky": f"{top},{hor}", "haze": _mix(hor, "#000000", 0.2),
                       "clouds": [{"y": -2.5 - 6.5 * i, "color": _mix(pal[min(i + 1, len(pal) - 1)], "#ffffff", 0.45 - 0.1 * i), "density": 0.85, "scale": 1 + 0.4 * i} for i in range(3)]}
        spec["layout"] = "craft" if "craft" in spec else "planet"
        spec["motion"] = {"fall": 3.5 + seed % 4}
        spec["camera"] = {"path": "orbit", "dist": 11 if (spec.get("craft") or {}).get("parachute") else 8, "el": 10, "az0": -14, "az1": 14}
        spec.pop("world", None) if "craft" in spec else None
        conf = max(conf, 0.75)
    part = next((m for m, rx in PARTICLES if re.search(rx, low)), None)
    if part and (sky or inside or part in ("snow", "rain", "embers", "dust")):
        spec["env"]["particles"] = {"mode": part, "count": 700, "speed": 5 if part in ("rain", "streaks") else 1.5,
                                    "color": "#dfe6ee" if part in ("rain", "snow") else "#ffb060" if part == "embers" else "#d8c8a8"}
    if "world" not in spec and ("craft" not in spec) and (CUT.search(low) and re.search(r"\b(planet|world|moon|star|earth|sun)\b", low) or FIELD.search(low)):
        spec["world"] = {"type": "gas" if FIELD.search(low) else "rock", "seed": seed % 97}
        spec["layout"], conf = "planet", max(conf, 0.65)
    w = spec.get("world")
    if w and spec["layout"] == "planet" and not inside:
        if CUT.search(low) and not FIELD.search(low):
            w["cutaway"] = {"layers": [{"r": r, "color": c, "label": lb} for r, c, lb in LAYERS.get(w["type"], LAYERS["rock"])]}
            if w.get("palette") and w["type"] in ("gas", "haze"):
                w["cutaway"]["layers"][0]["color"] = w["palette"][0]
            spec["camera"] = {"path": "orbit", "dist": 3.8, "az0": 30, "az1": 52, "el": 24}
            conf = max(conf, 0.8)
        if FIELD.search(low):
            w["field"] = {"lines": 12, "color": "#7fd0ff", "tilt": 8 + seed % 12, "reach": 3.4}
            w.pop("rings", None)
            spec["camera"] = {"path": "pullback", "dist": 5.0, "d1": 6.8, "el": 10, "az0": -10, "az1": 10}
            conf = max(conf, 0.8)
    cam = next((c for c, rx in CAMS if re.search(rx, low)), None)
    if "camera" not in spec:
        spec["camera"] = {"path": cam or ("push" if seed % 3 == 0 else "orbit" if seed % 3 == 1 else "drift"), "az0": -25 + seed % 20, "az1": 15 + seed % 25, "el": 6 + seed % 14}
        if spec["layout"] == "craft_over_planet":
            spec["world"]["radius"] = 6
            spec["camera"].update({"dist": 6.5})
        elif spec["layout"] == "planet":
            spec["camera"].update({"dist": 3.6})
    spec["light"] = {"dir": [-4 + seed % 3, 1.5 + (seed % 4) * 0.5, 3]}
    return spec, conf


# ---- an AI model as the author (for sentences the rules cannot read) -----------------------------------------------------------------------------
WORLD_T = {"gas", "rock", "ice", "ocean", "lava", "sun", "haze"}
CRAFT_K = {"probe", "capsule", "lander", "satellite", "rocket", "telescope", "rover", "parts"}
LAYOUTS = {"planet", "craft", "craft_over_planet"}
CAM_P = {"orbit", "push", "pullback", "descend", "flyby", "drift"}
HEXC = re.compile(r"^#[0-9a-fA-F]{6}$")
AUTHOR_SYSTEM = (
    "You design ONE short 3D scene for one narration sentence of a documentary, as JSON (a procedural renderer draws it; there are no model files). "
    "Reply with ONLY a JSON object with these optional keys: "
    '{"layout":"planet|craft|craft_over_planet","world":{"type":"gas|rock|ice|ocean|lava|sun|haze","palette":["#hex","#hex","#hex"],"storm":0-1,"bands":1-40,"craters":0-1,'
    '"clouds":0-1,"city":0-1,"atmosphere":"#hex","radius":0.5-8,"rings":{"inner":1.2,"outer":2.4,"tilt":20},'
    '"cutaway":{"layers":[{"r":1.0,"color":"#hex","label":"CRUST"},{"r":0.6,"color":"#hex","label":"CORE"}]},"field":{"lines":12,"color":"#hex","tilt":10,"reach":3.4}},'
    '"craft":{"kind":"probe|capsule|lander|satellite|rocket|telescope|rover","scale":0.3-3,"parachute":true|false},'
    '"env":{"sky":"space|#topHex,#horizonHex","clouds":[{"y":-3,"color":"#hex","density":0.1-1}],"haze":"#hex","particles":{"mode":"rain|dust|snow|embers|streaks","count":100-2000,"color":"#hex","speed":1-10}},'
    '"motion":{"fall":0-20,"spin":-45-45},"camera":{"path":"orbit|push|pullback|descend|flyby|drift","dist":2-12,"el":-20-60},"light":{"dir":[-4,2,3]}}. '
    "Choose what the sentence is about, colours that fit it, and a camera that suits the action. Invent no text. If the sentence cannot be drawn as a world or a craft, reply {}.")


def problems(spec: Any) -> list:
    """Why an AI model's scene cannot be used (the engine repairs small slips; this rejects what would draw something else or nothing)."""
    if not isinstance(spec, dict) or not spec:
        return ["empty"]
    p = []
    if spec.get("layout") not in LAYOUTS:
        p.append("layout")
    w, c = spec.get("world"), spec.get("craft")
    if spec.get("layout") != "craft" and not (isinstance(w, dict) and w.get("type") in WORLD_T):
        p.append("world.type")
    if spec.get("layout") != "planet" and not (isinstance(c, dict) and c.get("kind") in CRAFT_K):
        p.append("craft.kind")
    if isinstance(w, dict):
        for col in (w.get("palette") or []):
            if not HEXC.match(str(col)):
                p.append("palette colour")
    cam = spec.get("camera")
    if isinstance(cam, dict) and cam.get("path") not in CAM_P:
        p.append("camera.path")
    if len(json.dumps(spec)) > 4000:
        p.append("too large")
    return p


def author(text: str, run: Callable[[str, str], str]) -> Optional[Tuple[Dict[str, Any], float]]:
    """(spec, 0.7) from run(system, user) -> text, only if it validates; else None (the rules' answer, or no scene, stays)."""
    try:
        raw = run(AUTHOR_SYSTEM, f"Sentence: {text}")
        m = re.search(r"\{.*\}", raw or "", re.S)
        spec = json.loads(m.group(0)) if m else None
    except Exception:
        return None
    if problems(spec):
        return None
    spec.setdefault("env", {"sky": "space"})
    spec["seed"] = _seed(text)
    return spec, 0.7
