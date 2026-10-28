"""Feature list + beats -> What If spec (kind "product" shots + pt_* layers). Deterministic for a seed.

Acts (docs/product_trailer/PLAN.md): cold open (~16 %, no text, 2-2.6 s cuts, a new move each) -> features (one per ~3 s, text opposite the phone) -> second, faster
pass (2-2.6 s, big type for the display) -> reveal ("Introducing" + name) -> disclaimer card (last ~3 s). Every interior cut is on a beat."""

from __future__ import annotations

import json
import random
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .beats import MAX_LEN_S, BeatInfo, detect, grid
from .csv_io import read_csv

LOOK = {"saturate": 0.95, "contrast": 1.06, "lift": "#05070B", "vignette": 0.3, "grain": 0.02}
MOVES = ["island", "monolith", "hero", "profile", "orbit", "screen", "edge", "chip", "chip_macro", "flip", "rise", "port", "buttons", "reveal"]
# what the viewer mostly sees (checked on rendered stills): flip ends on the lit front, rise settles front-on, orbit shows the screen.
# "reveal" (back -> turn -> front, screen powers on) is led by the back and counts as a back shot for the front cap.
FACE = {"island": "back", "monolith": "back", "reveal": "back", "flip": "front", "rise": "front", "hero": "front", "screen": "front", "orbit": "front",
        "profile": "side", "edge": "side", "port": "side", "buttons": "side", "chip": "chip", "chip_macro": "chip"}
FRONT_CAP = 0.30                                                                         # front-facing product shots <= 30 %: the camera island is the star
COLD_OPEN = ["island", "monolith", "profile", "edge", "orbit"]          # cycled from the first: a macro glide across the lens island opens the film; no crop-prone front moves
COLD_LEN = (2.6, 3.6)                                                    # cold-open shot length (s): long, steady shots like the reference's opening (about 1 cut in 4 s, not 4 in 6 s)
SECOND_PASS = ["profile", "island", "screen", "buttons", "flip", "port", "hero", "edge", "monolith", "orbit", "rise"]
FILL_FRAME = {"island", "edge", "port", "buttons", "profile", "screen", "chip_macro"}   # phone fills the frame: no feature text on these
TEXT_MOVES = ["hero", "monolith", "orbit", "flip", "rise"]                              # phone offset to one side: room for text
BIGTYPE_MOVES = ["screen", "monolith"]                                                  # screen only with the clock hidden; never over a lit front
RECENT = 3                                                                              # no move repeats within the last 3 shots
FAST = (2.0, 2.6)                                                                        # cold open + second pass shot length (s)
FEATURE_S = 3.0                                                                          # feature shot length target (s)
WASH = {"red": "#ff4a1f", "orange": "#ff7a1a", "purple": "#7a3cff", "blue": "#2f6bff", "gold": "#ffb340", "green": "#22c27a", "pink": "#ff4f9a"}
COLOURS = {"navy": "#1f2a44", "sky": "#9cc3e6", "pink": "#e8b4c4", "titanium": "#8fa3b5", "black": "#2a2d33", "silver": "#c9ced6", "blue": "#3d5a80", "gray": "#7d838c", "grey": "#7d838c",
           "violet": "#6b5b95", "green": "#4f6b58", "gold": "#c8a46a", "white": "#e8e8ea"}

KIND_RULES = [  # (keywords, moves, backdrop, wash_style, default wash colour, extra)
    (("camera", "lens", "photo", "zoom", "sensor"), ["monolith", "rise", "flip"], "stars", None, None, None),
    (("frame", "build", "titanium", "aluminum", "aluminium", "glass", "material"), ["flip", "rise", "monolith"], "wash", "swoosh", "red", None),
    (("os", "software", "android", "ios", "ai", "ui"), ["hero", "orbit"], "wash", "aurora", "purple", None),
    (("chip", "performance", "processor", "cpu", "gpu", "soc"), ["chip", "chip_macro"], "stars", None, None, "badge"),
    (("display", "screen", "hz", "brightness"), ["screen", "monolith"], "stars", None, None, "bigtype"),
    (("battery", "charging", "charge", "usb", "power", "magnet", "magnets", "qi2", "wireless"), ["rise", "orbit"], "horizon", None, None, None),
    (("thin", "design", "slim", "light", "weight"), ["monolith", "rise", "hero"], "horizon", None, None, None),
]


def classify(feature: Dict[str, Any]) -> Dict[str, Any]:
    kind = (feature.get("feature") or "").lower()
    look = feature.get("look") or ""                    # case kept: image file names
    rule = {"moves": ["orbit", "hero"], "backdrop": "stars", "wash_style": None, "wash": None, "extra": None, "image": None}
    for keys, moves, backdrop, style, wash, extra in KIND_RULES:
        if any(k == kind or k in kind.split() for k in keys) or any(kind.startswith(k) for k in keys if len(k) > 3):
            rule = {"moves": list(moves), "backdrop": backdrop, "wash_style": style, "wash": wash, "extra": extra, "image": None}
            break
    for raw in [p.strip() for p in look.replace(";", " ").split() if p.strip()]:
        part, _, arg = raw.partition(":")
        part = part.lower()
        if part == "wash":                                 # wash, wash:red, wash:#00aaff, wash:blue:swoosh
            colour, _, style = arg.partition(":")
            colour = colour.lower() or rule["wash"] or "red"
            rule["backdrop"] = "wash"
            rule["wash"] = colour
            rule["wash_style"] = style.lower() if style.lower() in ("swoosh", "aurora") else (
                rule["wash_style"] or ("aurora" if colour in ("purple", "blue", "green") else "swoosh"))
        elif part == "gradient":                           # gradient, gradient:blue, gradient:#3355ff
            rule["backdrop"] = "gradient"
            rule["wash"] = arg.lower() or rule["wash"] or "blue"
        elif part == "image" and arg:                      # image:skyline.jpg (next to the CSV, or a full path)
            rule["backdrop"] = "image"
            rule["image"] = arg
        elif part in ("badge", "bigtype"):
            rule["extra"] = part
        elif part in ("stars", "horizon", "studio"):
            rule["backdrop"] = part
    return rule


def _snap(beats: Sequence[float], target: float, after: float, min_len: float, limit: float) -> float:
    """The beat closest to target that leaves at least min_len after `after` and before `limit`."""
    ok = [b for b in beats if b >= after + min_len - 1e-6 and b <= limit + 1e-6]
    if not ok:                                   # nothing in the window: the nearest beat after `after` that is still before the end
        ok = [b for b in beats if b > after + 0.5] or [b for b in beats if b > after] or [limit]
    return min(ok, key=lambda b: abs(b - target))


class _Variety:
    """Picks the first candidate not used in the last RECENT shots, preferring a different face from the previous shot.
    Front-facing moves are only allowed while they stay within FRONT_CAP of the product shots so far (counting this one)."""

    def __init__(self, rng: random.Random):
        self.rng, self.recent, self.prev_face, self.cam_side = rng, [], None, rng.choice([-1, 1])
        self.n = self.front = 0

    def pick(self, candidates: Sequence[str], fallback: Sequence[str] = SECOND_PASS, strict: bool = False) -> str:
        """strict: only candidates/fallback (text needs room beside the phone); the front cap may then bend for one shot."""
        no_front = (self.front + 1) / (self.n + 1) > FRONT_CAP + 1e-9
        both = list(candidates) + list(fallback)
        stages = [(candidates, True), (fallback, True), (MOVES, True)]
        if strict:
            stages = [(candidates, True), (fallback, True), (both, False)]
        alt: List[str] = []
        for pool, cap in stages:
            fresh = [m for m in pool if m not in self.recent and not (cap and no_front and FACE.get(m) == "front")]
            alt = [m for m in fresh if FACE.get(m) != self.prev_face] or fresh
            if alt:
                break
        move = alt[0]
        self.recent = (self.recent + [move])[-RECENT:]
        self.prev_face = FACE.get(move)
        self.cam_side = -self.cam_side
        self.n += 1
        self.front += FACE.get(move) == "front"
        return move


def _tone(colour: str) -> str:
    if colour.startswith("#"):
        return colour
    return next((COLOURS[w] for w in reversed(colour.lower().split()) if w in COLOURS), "#8fa3b5")   # "Titanium White" -> white


def plan_spec(data: Dict[str, Any], beats: BeatInfo, *, width: int = 1920, height: int = 1080, fps: int = 30, seed: int = 0,
              music_path: Optional[str] = None, pace: Optional[str] = None) -> Dict[str, Any]:
    pace = (pace or data.get("product", {}).get("pace") or "trailer").lower()
    if pace == "reveal":
        return plan_reveal(data, beats, width=width, height=height, fps=fps, seed=seed, music_path=music_path)
    rng = random.Random(seed)
    prod = data.get("product", {})
    feats = list(data.get("features") or [])
    D = round(float(beats.duration), 3)
    bl = sorted(b for b in beats.beats if 0.5 < b < D - 0.5)
    phone = prod.get("phone") or prod.get("name", "phone").lower()
    colour = prod.get("colour") or "titanium"
    tone = _tone(colour)
    var = _Variety(rng)
    shots: List[Dict[str, Any]] = []
    layers: List[Dict[str, Any]] = []

    card_len = 3.0 if D >= 20 else max(1.5, D * 0.12)
    card_at = _snap(bl, D - card_len, D * 0.8, 0.5, D - 1.5)
    reveal_at = _snap(bl, card_at - 4.5, D * 0.7, 0.5, card_at - 2.5)
    cold_end = _snap(bl, D * 0.16, 0, 4.0, D * 0.25)
    want = min(FEATURE_S * len(feats) + 0.5, (reveal_at - cold_end) * 0.75)      # every feature gets ~3 s; the fast pass gets the rest
    feat_end = _snap(bl, cold_end + want, cold_end + 3.0, 0, max(cold_end + 3.0, min(reveal_at - 3.0, reveal_at - 6.0 if reveal_at - cold_end > 12 else reveal_at - 3.0))) if feats else cold_end

    def shot(start, end, move, *, backdrop="stars", wash=None, wash_style=None, phone_side=None, screen_on=False, clock=True, image=None):
        side = phone_side or rng.choice(["left", "right"])
        s = {"id": f"s{len(shots) + 1:02d}", "start": round(start, 3), "end": round(end, 3), "kind": "product",
             "object": "chip" if FACE.get(move) == "chip" else "phone", "phone": phone, "color": colour, "tone": tone, "move": move,
             "backdrop": backdrop, "seed": rng.randrange(1, 10_000), "cam_side": var.cam_side, "frame_side": side, "exit": "cut"}
        if backdrop == "wash":
            s["wash"] = WASH.get(wash or "red", wash or "#ff4a1f")
            s["wash_style"] = wash_style or "swoosh"
        elif backdrop == "gradient":
            s["wash"] = WASH.get(wash or "blue", wash or "#2f6bff")
        elif backdrop == "image":
            s["backdrop_file"] = image                     # build_spec copies it into the spec's media folder
        if screen_on or FACE.get(move) == "front":
            s["screen"] = {"time": prod.get("time", "09:41"), "date": prod.get("date", "Tue 27 Oct")}
            if not clock:
                s["screen"]["clock"] = False                   # big type over the screen: the renderer hides the big digits
        if prod.get("wordmark"):
            s["label"] = prod["wordmark"]
        shots.append(s)
        return s

    def cuts(a: float, b: float, lo: float, hi: float) -> List[float]:
        """Even pieces of ~(lo+hi)/2 s, each cut snapped to a beat (small jitter so the rhythm is not mechanical)."""
        n = max(1, int(round((b - a) / ((lo + hi) / 2 - 0.05))))
        out, t = [a], a
        for k in range(1, n):
            target = a + k * (b - a) / n + rng.uniform(-0.15, 0.15)
            nxt = _snap(bl, target, t, min(lo, 1.5), b - min(lo, 1.5))
            if nxt <= t + 1e-6 or nxt >= b - 0.5:
                break
            out.append(nxt)
            t = nxt
        out.append(b)
        return out

    # act 1: cold open, no text
    c = cuts(0.0, cold_end, *COLD_LEN)
    off = 0
    for i in range(len(c) - 1):
        k = (off + i) % len(COLD_OPEN)
        shot(c[i], c[i + 1], var.pick(COLD_OPEN[k:] + COLD_OPEN[:k]))

    # act 2: one feature per 3-4 s
    if feats:
        span = feat_end - cold_end
        per = max(2.0, min(4.0, span / len(feats)))
        t = cold_end
        for k, f in enumerate(feats):
            if t >= feat_end - 1.0:
                break
            per = max(2.5, min(4.0, (feat_end - t) / (len(feats) - k)))
            end = feat_end if k == len(feats) - 1 else _snap(bl, t + per, t, min(2.5, per * 0.8), feat_end - 1.0)
            if end <= t + 0.5 or end > feat_end:
                end = feat_end
            rule = classify(f)
            if rule["extra"] == "bigtype":
                move = var.pick(BIGTYPE_MOVES, ["monolith", "island"])
            elif rule["extra"] == "badge":
                move = var.pick(rule["moves"])
            else:                                          # feature / tagline text: the phone must leave room for it
                move = var.pick([m for m in rule["moves"] if m not in FILL_FRAME] or TEXT_MOVES, ["monolith"] + TEXT_MOVES, strict=True)
            text_side = "right" if k % 2 == 0 else "left"
            s = shot(t, end, move, backdrop=rule["backdrop"], wash=rule["wash"], wash_style=rule["wash_style"],
                     phone_side="left" if text_side == "right" else "right", clock=rule["extra"] != "bigtype", image=rule.get("image"))
            a, b = s["start"] + 0.05, s["end"] - 0.05          # the text lives for the whole shot (0.7 s blur-in): never a ghost
            if rule["extra"] == "badge":
                layers.append({"type": "pt_badge", "title": f.get("value") or f.get("feature", "").upper(), "subtitle": f.get("sub") or f.get("kicker", ""),
                               "color": "#ffb340", "start": a, "end": b})
            elif rule["extra"] == "bigtype":
                layers.append({"type": "pt_bigtype", "text": f.get("value") or f.get("feature", ""), "y": 0.5, "start": a, "end": b})
            elif f.get("value") and not (f.get("kicker") or f.get("sub")) and len(f["value"]) <= 24:
                layers.append({"type": "pt_tagline", "text": f["value"], "side": text_side, "start": a, "end": b})
            else:
                layers.append({"type": "pt_feature", "kicker": f.get("kicker", ""), "value": f.get("value") or f.get("feature", "").title(),
                               "sub": f.get("sub", ""), "side": text_side, "start": a, "end": b})
            t = end

    # act 3: second, faster pass
    c = cuts(feat_end, reveal_at, *FAST)
    display = [f for f in feats if classify(f)["extra"] == "bigtype"]
    for i in range(len(c) - 1):
        cands = SECOND_PASS[i % len(SECOND_PASS):] + SECOND_PASS[:i % len(SECOND_PASS)]
        if display and i == 2 % max(1, len(c) - 1):
            s = shot(c[i], c[i + 1], var.pick(["screen", "monolith"], ["monolith", "island"]), clock=False)
            layers.append({"type": "pt_bigtype", "text": display[0].get("value") or "120Hz", "y": 0.5,
                           "start": s["start"] + 0.1, "end": s["end"] - 0.1})
        else:
            shot(c[i], c[i + 1], var.pick(cands))

    # act 4: reveal, then the card
    card_lines = [ln for ln in str(prod.get("disclaimer", "")).split("|") if ln.strip()]
    s = shot(reveal_at, card_at if card_lines else D, var.pick(["hero", "monolith", "orbit"], TEXT_MOVES), phone_side="right")   # no disclaimer: the reveal holds to the end
    layers.append({"type": "pt_reveal", "kicker": prod.get("intro", "Introducing"), "name": prod.get("name", ""), "side": "left",
                   "start": s["start"] + 0.3, "end": s["end"] - 0.1})
    if card_lines:
        shots.append({"id": f"s{len(shots) + 1:02d}", "start": round(card_at, 3), "end": D, "kind": "black", "exit": "cut"})
        layers.append({"type": "pt_card", "lines": card_lines, "start": round(card_at + 0.2, 3), "end": D})
    for L in layers:
        L["start"], L["end"] = round(L["start"], 3), round(L["end"], 3)

    spec = {"width": int(width), "height": int(height), "fps": int(fps), "duration": D, "look": dict(LOOK), "shots": shots, "layers": layers,
            "whatif": {"title": prod.get("name", "Product Trailer"), "notes": []},
            "product_trailer": {"seed": seed, "tempo": round(beats.tempo, 2), "beat_source": beats.source, "beats": [round(b, 3) for b in beats.beats],
                                "music": str(music_path) if music_path else None, "product": prod}}
    return spec


REVEAL_SLOW = ["monolith", "hero", "island", "orbit", "rise"]                           # slow studio moves between the reveals
REVEAL_SHOT = (5.5, 6.5)                                                                 # reveal pace shot length (s)
REVEAL_EVERY = 4                                                                         # the back->front "reveal" move every ~4 shots


def _colours(prod: Dict[str, Any]) -> List[str]:
    cols = [c for c in prod.get("colors") or [] if c]
    if not cols:
        raw = str(prod.get("colour") or "titanium")
        cols = [c.strip() for c in raw.replace("/", "|").split("|") if c.strip()] or ["titanium"]
    return cols


def plan_reveal(data: Dict[str, Any], beats: BeatInfo, *, width: int = 1920, height: int = 1080, fps: int = 30, seed: int = 0,
                music_path: Optional[str] = None) -> Dict[str, Any]:
    """Slow studio product film: ~6 s shots on beats, phone centred, charcoal fog, one caption per feature, the phone's colours cycled."""
    rng = random.Random(seed)
    prod = data.get("product", {})
    feats = list(data.get("features") or [])
    D = round(float(beats.duration), 3)
    bl = sorted(b for b in beats.beats if 0.5 < b < D - 0.5)
    phone = prod.get("phone") or prod.get("name", "phone").lower()
    cols = _colours(prod)
    var = _Variety(rng)
    shots: List[Dict[str, Any]] = []
    layers: List[Dict[str, Any]] = []
    card_lines = [ln for ln in str(prod.get("disclaimer", "")).split("|") if ln.strip()]
    card_at = _snap(bl, D - 3.0, D * 0.8, 0.5, D - 1.5) if card_lines else D
    reveal_at = _snap(bl, card_at - 6.0, D * 0.6, 0.5, card_at - 4.0)

    def cut_after(t: float) -> float:
        ok = [b for b in bl if REVEAL_SHOT[0] - 1e-6 <= b - t <= REVEAL_SHOT[1] + 1e-6]
        return min(ok, key=lambda b: abs(b - t - 6.0)) if ok else t + 6.0

    edges, t = [0.0], 0.0
    while True:
        nxt = cut_after(t)
        if nxt > reveal_at - REVEAL_SHOT[0] + 1e-6:
            break
        edges.append(nxt)
        t = nxt
    edges.append(reveal_at)                      # the last body shot absorbs the remainder (it stays on a beat: reveal_at is one)
    if len(edges) > 2 and edges[-1] - edges[-2] < 3.0:
        edges.pop(-2)

    def shot(i: int, start: float, end: float, move: str, *, side: str = "center") -> Dict[str, Any]:
        colour = cols[(i + i // REVEAL_EVERY) % len(cols)]          # cycled; the offset keeps every reveal from landing on one colour
        face = FACE.get(move)
        bd = "studio" if i % 5 == 3 else "gradient" if i % 7 == 5 else "charcoal"
        s = {"id": f"s{len(shots) + 1:02d}", "start": round(start, 3), "end": round(end, 3), "kind": "product", "object": "phone",
             "phone": phone, "color": colour, "tone": _tone(colour), "move": move, "backdrop": bd, "seed": rng.randrange(1, 10_000),
             "cam_side": var.cam_side, "frame_side": side, "exit": "cut"}
        if bd == "gradient":
            s["wash"] = _tone(colour)
        if i % 4 != 3:
            s["fog"] = True
        if face == "back":
            s["streak"] = True
        if face == "front" or move == "reveal":
            s["glow"] = True
        if i % 3 == 2:
            s["dim_out"] = 0.6
        if move == "reveal" or face == "front":
            s["screen"] = {"time": prod.get("time", "09:41"), "date": prod.get("date", "Tue 27 Oct"),
                           "wallpaper": "liquid" if (i // REVEAL_EVERY) % 2 == 0 else "wave", "tint": _tone(colour)}
        if move == "reveal":
            s["turn_at"] = 0.45
            s["screen"]["power_on"] = round((end - start) * 0.45 + 0.4, 2)
        if prod.get("wordmark"):
            s["label"] = prod["wordmark"]
        shots.append(s)
        return s

    for i in range(len(edges) - 1):
        if i % REVEAL_EVERY == 0:
            move = "reveal"
            var.recent = (var.recent + ["reveal"])[-RECENT:]
            var.prev_face, var.n = "back", var.n + 1
        else:
            k = i % len(REVEAL_SLOW)
            move = var.pick(REVEAL_SLOW[k:] + REVEAL_SLOW[:k], REVEAL_SLOW)
        s = shot(i, edges[i], edges[i + 1], move)
        if i < len(feats):
            f = feats[i]
            text = " ".join(p for p in (f.get("kicker"), f.get("value") or f.get("feature", "").title(), f.get("sub")) if p)
            layers.append({"type": "pt_caption", "text": text, "start": round(s["start"] + 0.6, 3), "end": round(s["end"] - 0.4, 3)})
    notes = [] if len(feats) <= len(edges) - 1 else [f"{len(feats) - len(edges) + 1} feature(s) did not fit the music; add length or trim the CSV"]

    i = len(edges) - 1
    s = shot(i, reveal_at, card_at, "hero", side="right")
    s.pop("dim_out", None)
    layers.append({"type": "pt_reveal", "kicker": prod.get("intro", "Introducing"), "name": prod.get("name", ""), "side": "left",
                   "start": round(s["start"] + 0.3, 3), "end": round(s["end"] - 0.1, 3)})
    if card_lines:
        shots.append({"id": f"s{len(shots) + 1:02d}", "start": round(card_at, 3), "end": D, "kind": "black", "exit": "cut"})
        layers.append({"type": "pt_card", "lines": card_lines, "start": round(card_at + 0.2, 3), "end": D})
    return {"width": int(width), "height": int(height), "fps": int(fps), "duration": D, "look": dict(LOOK), "shots": shots, "layers": layers,
            "whatif": {"title": prod.get("name", "Product Trailer"), "notes": notes},
            "product_trailer": {"seed": seed, "pace": "reveal", "tempo": round(beats.tempo, 2), "beat_source": beats.source,
                                "beats": [round(b, 3) for b in beats.beats], "music": str(music_path) if music_path else None, "product": prod}}


def _copy_backdrops(spec: Dict[str, Any], csv_dir: Path, media: Path) -> None:
    """Copy each image:<file> background beside the spec (the renderer serves <spec dir>/media); a missing file falls back to the star field."""
    for s in spec["shots"]:
        name = s.get("backdrop_file")
        if not name:
            continue
        src = Path(name).expanduser()
        src = src if src.is_absolute() else csv_dir / src
        if not src.is_file():
            spec["whatif"]["notes"].append(f"background image not found: {name}; star field used")
            s["backdrop"] = "stars"
            s.pop("backdrop_file", None)
            continue
        media.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, media / src.name)
        s["backdrop_file"] = src.name


def build_spec(csv_path, music_path=None, out_dir=None, width: int = 1920, height: int = 1080, fps: int = 30, seed: int = 0,
               phone: Optional[str] = None, colour: Optional[str] = None, disclaimer: Optional[str] = None, disclaimer_on: bool = True,
               pace: Optional[str] = None) -> str:
    """phone / colour / disclaimer from the app page win over the CSV's #product and #disclaimer lines; disclaimer_on=False drops the card."""
    data = read_csv(csv_path)
    prod = data.setdefault("product", {})
    if phone:
        prod["phone"] = phone
        if not prod.get("name"):
            prod["name"] = phone
    if colour:
        prod["colour"] = colour
    if disclaimer:
        prod["disclaimer"] = disclaimer
    if not disclaimer_on:
        prod["disclaimer"] = ""
    seed = 0 if seed is None else seed
    pace = (pace or prod.get("pace") or "trailer").lower()
    if pace == "reveal" and not music_path:          # no music: a 6 s grid, long enough for one shot per feature + the reveal + the card
        beats = grid(min(MAX_LEN_S, 6.0 * (len(data.get("features") or []) + 1) + 3.0), bpm=10.0)
    else:
        beats = detect(str(music_path) if music_path else None)
    spec = plan_spec(data, beats, width=width, height=height, fps=fps, seed=seed, music_path=music_path, pace=pace)
    out = Path(out_dir or Path(csv_path).parent)
    out.mkdir(parents=True, exist_ok=True)
    _copy_backdrops(spec, Path(csv_path).parent, out / "media")
    path = out / "product_trailer_spec.json"
    path.write_text(json.dumps(spec, indent=1), encoding="utf-8")
    return str(path)
