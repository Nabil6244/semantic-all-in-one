"""Variety: so two What If videos do not look like one video (project 288, Voyager, 18 min: 88 stock/NASA pictures, 20 3D shots, 90 plain text
cards among 142 graphics, one grade, one camera drift). Every rule here follows the narration (what it names, what it says), never the
template's sample data, and every change is written to the plan notes.

    upgrade_3d      a picture/clip shot whose narration names a craft or world with a 3D model becomes that model (never next to another 3D shot)
    trim_text       plain text cards are held to a share of the graphics: the excess goes (cards over a 3D shot first), a percent becomes a ring
    vary_motion     the camera on a picture is not always the same 4 % drift: push, pull, wide pull, pan; real photos alternate letterbox / full frame
    pick_look       the grade and the information colour follow the topic (heat, cold, danger, history ...) and the title seeds the small differences
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

TEXT_IDS = {"kicker_headline", "lower_third", "side_note", "key_word", "underline_title", "two_tone_headline", "typewriter_line", "boxed_fact", "statement"}
THREE_D_MAX = 0.32           # at most this share of the shots is a 3D model or globe (the rest stays real footage and pictures)
TEXT_SHARE_MAX = 0.28        # plain text cards, of all the graphics
GRAPHIC_TYPES = ("tm_template", "tm_caption", "tm_metric", "tm_annotate", "tm_bars", "tm_compare", "tm_timeline", "tm_logaxis", "tm_composition")
_CARRY = re.compile(r"\b(the (probe|spacecraft|craft|machine|lander|rover|telescope|satellite|orbiter)|this (probe|spacecraft|craft|machine))\b", re.I)
SAME_MODEL_GAP_S = 6.0       # the same model or globe is not drawn again within this many seconds (the same shot over and over is the bug)
SAME_MODEL_MAX = 6           # nor more than this many times in one video (its angle changes each time, planner.vary)


class _Carry:
    """"the probe ..." continues the craft the story is about -- unless the sentence is about what happens inside a world (a descent, a parachute,
    pressure), where the orbiter's model is the wrong picture. Same .search() as the plain pattern, so callers need no change."""

    def search(self, text: str):
        from . import planner as pl

        if pl.INSIDE.search(text or ""):
            return None
        return _CARRY.search(text or "")


CARRY = _Carry()


# ---- 3D instead of a stock picture ----------------------------------------------------------------------------------------------------
def upgrade_3d(shots: List[Any], notes: List[str]) -> int:
    """A picture or clip shot (not Flow, not a hero or plate) about a craft or world that has a model/texture in the engine is drawn as it."""
    from . import planner as pl

    if not shots:
        return 0
    def is3d(s: Any) -> bool:
        return s.kind in ("craft", "globe")

    count = sum(1 for s in shots if is3d(s))
    done, topic, topic_end = 0, "", 0.0
    seen: Dict[str, List[float]] = {}
    for s in shots:
        if is3d(s) and (s.model or s.texture):
            seen.setdefault(s.model or s.texture, []).append(s.start)
    for i, s in enumerate(shots):
        if is3d(s):
            topic, topic_end = s.name or topic, s.end
            continue
        if s.kind not in ("image", "video") or s.length < 3.0 or s.asset.lower().startswith(("flow_", "file:")):
            continue
        if (i and is3d(shots[i - 1])) or (i + 1 < len(shots) and is3d(shots[i + 1])):
            continue                                            # neighbours alternate: a 3D shot is followed by real footage
        if count >= 2 and (count + 1) / len(shots) > THREE_D_MAX:
            break
        text = s.text or ""
        if pl.PHOTO.search(text):                               # "the photo showed ..." stays the photograph
            continue
        named = bool(pl._craft(text) or pl._world(text))
        if not named and not (CARRY.search(text) and topic and s.start - topic_end <= 20.0):
            continue                                            # "the probe ..." is still the craft the story is about (just seen), else nothing is named
        got = pl.classify(text if named else f"{topic} {text}", flow_video=False)
        if got.get("kind") not in ("craft", "globe"):
            continue
        key = got.get("model") or got.get("texture") or ""
        prior = seen.get(key, [])
        if len(prior) >= SAME_MODEL_MAX or any(abs(s.start - t) < SAME_MODEL_GAP_S for t in prior):
            continue                                            # the same model again and again is a generic shot, not an illustration
        for k in pl._LOOK:
            if k in got:
                setattr(s, k, got[k])
        s.kind, s.asset, s.file, s.credit = got["kind"], "", "", ""
        s.extra.pop("full_bleed", None)
        seen.setdefault(key, []).append(s.start)
        if is3d(s):
            topic, topic_end = s.name or topic, s.end
        count += 1
        done += 1
    if done:
        notes.append(f"plan: variety: {done} picture shot(s) drawn as their 3D model/globe ({100 * count // len(shots)}% of the shots are 3D)")
    return done


# ---- fewer plain text cards -------------------------------------------------------------------------------------------------------------
def _is_text(L: Dict[str, Any]) -> bool:
    return (L.get("type") == "tm_template" and (L.get("template") or {}).get("id") in TEXT_IDS) or \
           (L.get("type") == "tm_caption" and not L.get("auto") and L.get("size", "small") == "small" and not L.get("anchor"))


def _shot_at(shots: Sequence[Any], t: float) -> Optional[Any]:
    return next((s for s in shots if s.start - 1e-6 <= t < s.end), None)


def trim_text(shots: Sequence[Any], layers: List[Dict[str, Any]], notes: List[str]) -> int:
    """Hold the plain text cards to TEXT_SHARE_MAX of the graphics. Dropped first: a card over a 3D shot (its name is already on screen),
    then every second card in the busiest stretch. A picture still long and left bare keeps its card (nothing is left empty)."""
    graphics = [L for L in layers if L.get("type") in GRAPHIC_TYPES]
    text = [L for L in graphics if _is_text(L)]
    allowed = int(TEXT_SHARE_MAX * len(graphics))
    if len(text) <= allowed:
        return 0

    def bare_without(L: Dict[str, Any]) -> bool:
        s = _shot_at(shots, float(L["start"]))
        if s is None or s.kind in ("plate", "craft", "globe"):       # a 3D shot is never "bare": the model is the picture
            return False
        others = [x for x in graphics if x is not L and float(x["start"]) < s.end and s.start < float(x["end"])]
        return not others and s.length >= 5.0

    removed = 0
    order = sorted(text, key=lambda L: (0 if (_shot_at(shots, float(L["start"])) or shots[0]).kind in ("craft", "globe") else 1,
                                         float(L["start"])))
    over_3d = [L for L in order if (_shot_at(shots, float(L["start"])) or shots[0]).kind in ("craft", "globe")]
    rest = [L for L in order if L not in over_3d]
    for L in over_3d + rest[::2]:
        if len(text) - removed <= allowed:
            break
        if bare_without(L):
            continue
        layers.remove(L)
        removed += 1
    if removed:
        notes.append(f"plan: variety: {removed} plain text card(s) removed (text was {len(text)} of {len(graphics)} graphics, held to {int(100 * TEXT_SHARE_MAX)}%)")
    return removed


# ---- the camera ---------------------------------------------------------------------------------------------------------------------------
MOTIONS = (
    {"from": 1.0, "to": 1.09},                         # push in
    {"from": 1.07, "to": 1.0},                         # pull out
    {"from": 1.0, "to": 1.04, "fx": 0.3, "fy": 0.5},   # slow drift, left
    {"from": 1.12, "to": 1.0},                         # wide pull out
    {"from": 1.0, "to": 1.06, "fx": 0.7, "fy": 0.4},   # slow drift, right
)


def vary_motion(shots: Sequence[Any], notes: List[str]) -> int:
    """No two picture shots in a row move the same way; every third real photograph is shown full frame instead of letterboxed."""
    n = last = real = 0
    for s in shots:
        if s.kind not in ("image", "video"):
            continue
        k = n % len(MOTIONS)
        if k == last and n:
            k = (k + 1) % len(MOTIONS)
        s.extra["drift"] = dict(MOTIONS[k])
        last, n = k, n + 1
        if s.kind == "image" and s.cite and s.cite[0] == "REAL IMAGE":
            real += 1
            if real % 3 == 0:
                s.extra["full_bleed"] = True
    if n:
        notes.append(f"plan: variety: camera moves rotate over {n} picture shot(s) ({len(MOTIONS)} kinds)")
    return n


# ---- the look -----------------------------------------------------------------------------------------------------------------------------
# (name, words that call for it, grade, lift colour, accent colour for "information"). The first match with most hits wins; none -> the house look.
LOOKS: List[Tuple[str, str, Dict[str, Any]]] = [
    ("heat", r"\b(hot|heat|burn\w*|fire|lava|molten|furnace|venus|mercury|scorch\w*|melt\w*|flare|temperatures?)\b",
     {"saturate": 0.95, "contrast": 1.07, "lift": "#120A06", "vignette": 0.38, "accent": "#FFB347"}),
    ("cold", r"\b(cold|ice|icy|frozen|freez\w*|ocean|europa|neptune|uranus|titan|void|silent|abyss)\b",
     {"saturate": 0.78, "contrast": 1.05, "lift": "#060C14", "vignette": 0.36, "accent": "#5BD0FF"}),
    ("danger", r"\b(die|dies|death|dead|crush\w*|kill\w*|collapse\w*|explod\w*|radiation|lethal|survive|survival|disaster|impact|crash\w*)\b",
     {"saturate": 0.88, "contrast": 1.1, "lift": "#10070A", "vignette": 0.42, "accent": "#FF5D73"}),
    ("history", r"\b(19\d\d|18\d\d|history|historic|archive|decades?|golden record|engineers?|jpl|ancient|century|centuries)\b",
     {"saturate": 0.74, "contrast": 1.03, "lift": "#0C0B08", "vignette": 0.34, "accent": "#F2C879"}),
    ("life", r"\b(life|living|alive|oxygen|forest|biosphere|breathe|breathing|lungs?|body|bodies)\b",
     {"saturate": 0.9, "contrast": 1.04, "lift": "#060D0B", "vignette": 0.33, "accent": "#46E6B0"}),
    ("cosmic", r"\b(galax\w*|nebula|universe|light[- ]years?|black holes?|cosmic|interstellar|milky way)\b",
     {"saturate": 0.84, "contrast": 1.06, "lift": "#090812", "vignette": 0.37, "accent": "#A58BFF"}),
]


def pick_look(title: str, text: str) -> Tuple[str, Dict[str, Any]]:
    """The grade for this video: the topic words that dominate the narration choose a family, a hash of the title shifts it a little
    (so two videos on the same topic still differ). No clear topic -> the house look with only the small shift."""
    low = (text or "").lower()
    best, hits = None, 0
    for name, pat, look in LOOKS:
        n = len(re.findall(pat, low))
        if n > hits:
            best, hits = (name, look), n
    seed = int(hashlib.sha1((title or text[:200] or "x").encode("utf-8", "ignore")).hexdigest()[:8], 16)
    wob = lambda k, span: ((seed >> (k * 5)) % 11 - 5) / 5 * span          # noqa: E731  -5..+5 steps -> -span..+span
    if best is None or hits < max(3, len(low.split()) // 400):
        name, look = "house", {}
    else:
        name, look = best[0], dict(best[1])
    out = dict(look)
    if "saturate" in out:
        out["saturate"] = round(out["saturate"] + wob(0, 0.03), 3)
        out["vignette"] = round(out["vignette"] + wob(1, 0.025), 3)
        out["grain"] = round(0.03 + (seed >> 12) % 3 * 0.005, 3)
    else:
        out = {"saturate": round(0.82 + wob(0, 0.04), 3), "vignette": round(0.34 + wob(1, 0.03), 3), "grain": round(0.03 + (seed >> 12) % 3 * 0.005, 3)}
    return name, out


def apply(shots: List[Any], layers: List[Dict[str, Any]], title: str, text: str, notes: List[str]) -> Dict[str, Any]:
    """The whole pass (called from planner.plan once the shots are nearly final). -> the look for the spec."""
    upgrade_3d(shots, notes)
    trim_text(shots, layers, notes)
    vary_motion(shots, notes)
    name, look = pick_look(title, text)
    notes.append(f"plan: variety: look '{name}' ({', '.join(f'{k} {v}' for k, v in look.items())})")
    return look
