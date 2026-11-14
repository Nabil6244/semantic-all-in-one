"""Real clips for Ocean Predators (docs/ocean/PATTERNS.md section 3, plan step 6): about one shot in six is a short real
clip (3-6 s), graded into the blue world (less colour, cooler, vignette) with a small credit line bottom-left, used for the
"this is real" moments. Everything is fetched through the app's own stock sources into the Visuals tab (visual_bridge
owner "ocean"), so the user reviews, retries or swaps clips there before Render; Render uses exactly what the tab holds.

    choose(scenes, layers, total)      -> [slot]   slot = {"scene_no", "start", "end", "query", "text", "why"}
    query_for(features, set_name)      -> str      a stock search from the animals the sentence names (+ the set's place)
    visual_scenes(slots)               -> [scene]  rows for fetch_csv_footage / the Visuals tab (asset_type stock_video)
    credit(meta)                       -> str      "Footage: <author> / <provider>" from the clip's own record
    grade(src, dst, seek, seconds)     -> dst      ffmpeg: fit 1280 x 720, desaturate, cool, vignette, no audio
    apply(plan, found, black, work)    -> (shots, layers)   the timeline with clip shots cut in and the stage hidden there

Slot rules (by sentence shape, never topic): a sentence that names an animal the kit knows is a candidate; "filmed /
footage / camera / drone / spotted / photographed / real / first time / caught" make it a strong one; a sentence with a
full-screen or text card is never used (the card is the point there); slots keep CLIP_GAP_S apart and number about one per
CLIP_EVERY_S of film. A slot whose clip is missing or failed simply keeps the drawn stage: a clip never leaves a hole.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import reader as R

CLIP_MIN_S, CLIP_MAX_S = 3.0, 5.5
CLIP_GAP_S = 12.0
CLIP_EVERY_S = 22.0
OPENING_S, OPENING_GAP_S = 60.0, 6.0        # the reference cold open is ~1/3 real footage: clips come much closer there
REAL = re.compile(r"\b(film(ed|ing|s)?|footage|camera|cameras|drones?|spotted|photograph(ed|s)?|caught|real|really|actually|"
                  r"first time|first ever|for the first|seen|recorded|observed|witness(ed)?|video)\b", re.I)
QUERY = {
    "great_white": "great white shark underwater", "shark": "shark swimming underwater", "megalodon": "great white shark underwater",
    "orca": "orca killer whale swimming", "humpback": "humpback whale underwater", "sperm_whale": "sperm whale underwater",
    "dolphin": "dolphins swimming underwater", "seal": "sea lion seal underwater", "squid": "squid deep sea",
    "colossal_squid": "giant squid deep sea", "diver": "scuba diver underwater", "boat": "boat ocean aerial",
}
PLACE = {"surface": "surface", "seafloor": "sea floor", "abyss": "deep sea dark", "kelp": "kelp forest", "depth_column": "deep"}
SKIP_ANIMALS = ("cage", "tooth")
GRADE = ("eq=saturation=0.58:contrast=1.06:brightness=-0.035,"
         "colorbalance=rs=-0.06:gs=-0.01:bs=0.10:rm=-0.04:bm=0.06:rh=-0.02:bh=0.03,vignette=PI/4.6")


# ---------------------------------------------------------------------------------------------------------------- choose

def query_for(f: R.Features, set_name: str = "") -> str:
    names = [a for a in f.animals if a[0] not in SKIP_ANIMALS]
    if not names:
        return ""
    a = names[0]
    q = QUERY.get(a[0], "")
    if not q:                                                 # any catalogue animal: "tiger shark", "manta ray", "vampire squid"
        word = re.sub(r"(?<!s)s$", "", a[4].lower().strip())
        from . import species as _SP
        if _SP.family(a[0]) in ("land", "bird"):          # a land story: the animal in the wild, not underwater
            q = f"{word} wildlife"
        else:
            q = f"{word} {'deep sea' if 'squid' in word else 'underwater'}"
    if a[1] and a[0] in ("orca", "dolphin", "seal"):
        q += " group"
    place = PLACE.get(set_name)
    if a[0] == "boat":
        return q
    if place == "surface":
        pass                                     # the drawn surface set is the frame, not the subject: keep the animal underwater
    elif place and not any(w in q for w in place.split()):
        q += " " + place
    return re.sub(r"\s+", " ", q).strip()


def _busy(layers: Sequence[Dict[str, Any]]) -> List[Tuple[float, float]]:
    """Absolute windows where a full-screen or text card is up (no clip there)."""
    from .planner import FULL

    out = []
    for ly in layers:
        if ly.get("name") != "ocean.lay_ocean":
            continue
        s0 = float(ly["start"])
        for e in (ly.get("params") or {}).get("elements") or []:
            k = e.get("kind", "")
            if k.startswith("ocean_") and k[6:] in FULL:          # small number cards are drawn over the clip instead
                t1 = e.get("t1")
                out.append((s0 + float(e["t0"]), s0 + float(t1 if t1 is not None else float(ly["end"]) - s0)))
    return out


def _shot_at(layers: Sequence[Dict[str, Any]], t: float) -> Optional[Dict[str, Any]]:
    for ly in layers:
        if ly.get("name") == "ocean.lay_ocean" and float(ly["start"]) <= t < float(ly["end"]):
            return ly
    return None


def choose(scenes: Sequence[Dict[str, Any]], layers: Sequence[Dict[str, Any]], total: float,
           shots: Sequence[Dict[str, Any]] = ()) -> List[Dict[str, Any]]:
    busy = _busy(layers)
    want = (max(1, int(round(total / CLIP_EVERY_S))) + (2 if total >= 60 else 1)) if total >= 20 else 0
    cands: List[Tuple[float, Dict[str, Any]]] = []
    set_at = {round(float(s["start"]), 3): s.get("set", "") for s in shots}
    last_f = None
    for i, sc in enumerate(scenes):
        a, b = float(sc["start"]), float(sc["end"])
        f0 = R.read(str(sc.get("text", "")))
        if query_for(f0, ""):
            last_f = f0
        if b - a < CLIP_MIN_S - 0.6 or a < 1.5 or b > total - 6.0:
            continue
        f = R.read(str(sc.get("text", "")))
        ly = _shot_at(layers, a + 0.05)
        set_name = next((v for k, v in sorted(set_at.items()) if k <= a + 0.05), "") if set_at else ""
        q = query_for(f, set_name)
        carried = False
        if q:
            last_f = f
        elif last_f is not None:                       # "It has about 300 teeth": the story's animal is still the subject
            q, carried = query_for(last_f, set_name), True
        if not q or ly is None:
            continue
        start = a + 0.15
        end = min(b, start + CLIP_MAX_S, float(ly["end"]))
        if end - start < CLIP_MIN_S:
            if i + 1 < len(scenes) and float(ly["end"]) - start >= CLIP_MIN_S:
                end = min(start + CLIP_MIN_S + 0.5, float(ly["end"]))      # a short line runs on into the next one
            else:
                continue
        if any(min(end, y) - max(start, x) > 0 for x, y in busy):
            continue
        score = (2.0 if REAL.search(f.text) else 0.0) + 1.0 + (0.5 if f.group else 0.0) + (0.3 if set_name == "surface" else 0.0) \
            + (1.0 if a < OPENING_S else 0.0) - (0.6 if carried else 0.0)   # the cold open leans on real footage
        cands.append((score, {"scene_no": str(sc.get("scene_no", i + 1)), "start": round(start, 3), "end": round(end, 3),
                              "query": q, "text": str(sc.get("text", "")), "why": "real" if score >= 3 else "animal"}))
    cands.sort(key=lambda c: (-c[0], c[1]["start"]))
    picked: List[Dict[str, Any]] = []
    used_q: Dict[str, int] = {}
    for score, s in cands:
        if len(picked) >= want:
            break
        gap = OPENING_GAP_S if s["start"] < OPENING_S and all(p["start"] < OPENING_S for p in picked
                                                               if abs(s["start"] - p["start"]) < CLIP_GAP_S) else CLIP_GAP_S
        if any(abs(s["start"] - p["start"]) < gap for p in picked):
            continue
        if used_q.get(s["query"], 0) >= 4 and score < 3:
            continue                                  # the same search at most four times unless the line says it is real footage
        picked.append(s)
        used_q[s["query"]] = used_q.get(s["query"], 0) + 1
    return sorted(picked, key=lambda s: s["start"])


PHOTO_SLOT_BASE = 9000                         # polaroid photo rows sit after the film's own scene numbers in the Visuals tab


def photo_slots(layers: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One Visuals-tab row per polaroid print in the plan (its `photo_slot` is written into the card's args): the tab
    fetches a short real clip and Render prints one still frame of it; no clip -> the painted animal in the print."""
    out: List[Dict[str, Any]] = []
    for ly in layers:
        if ly.get("name") != "ocean.lay_ocean":
            continue
        s0 = float(ly["start"])
        for e in (ly.get("params") or {}).get("elements") or []:
            if e.get("kind") != "ocean_polaroid":
                continue
            a = e.setdefault("args", {})
            slot = str(PHOTO_SLOT_BASE + len(out) + 1)
            a["photo_slot"] = slot
            q = str(a.get("query") or str(a.get("animal", "shark")).replace("_", " ")).replace(" photo", "") + " underwater"
            t0 = s0 + float(e.get("t0", 0.0))
            out.append({"scene_no": slot, "start": round(t0, 3), "end": round(t0 + 4.0, 3), "query": q,
                        "text": str(a.get("caption", "")), "why": "photo"})
    return out


def still(src: str, dst: str, at: float = 1.0) -> str:
    """One graded still frame of a clip for a polaroid print."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, at):.2f}", "-i", src, "-frames:v", "1",
                    "-vf", "scale=960:-2," + GRADE.split(",vignette")[0], str(dst)], check=True, timeout=120)
    return dst


def visual_scenes(slots: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Visuals-tab rows: a beat picture is a Flow picture row (made by ocean/beat_flow.py), everything else a stock clip."""
    return [{"scene_no": s["scene_no"], "text": s["text"],
             "asset_type": "flow_image" if s.get("kind") in ("picture", "act") else "stock_video",
             "prompt": s["query"], "stock": "" if s.get("kind") in ("picture", "act") else s["query"], "start": s["start"], "end": s["end"]}
            for s in slots]


GRADES = {"ocean": GRADE, "neutral": "eq=saturation=0.92:contrast=1.05:brightness=-0.02,vignette=PI/5", "none": "null"}
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
MOTION_ALT = ("pull_out", "pan_left", "push_in_up", "pan_right")


def motion(src: str, dst: str, seconds: float, move: str = "push_in", fps: int = 25) -> str:
    """A still picture as a smooth camera move (sub-pixel, eased): push_in / pull_out / pan_left / pan_right /
    push_in_up. Frames are drawn with an affine transform, so the move never steps like a resized sprite."""
    from PIL import Image
    from cinematic_explainer.render import H, W

    im = Image.open(src).convert("RGB")
    s0 = max(W / im.width, H / im.height)
    base = im.resize((max(W, int(im.width * s0 * 1.2)), max(H, int(im.height * s0 * 1.2))), Image.LANCZOS)
    bw, bh = base.size
    n = max(2, int(round(seconds * fps)))
    zoom = {"push_in": (1.0, 1.12), "pull_out": (1.12, 1.0), "pan_left": (1.1, 1.1), "pan_right": (1.1, 1.1),
            "push_in_up": (1.0, 1.1)}.get(move, (1.0, 1.1))
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps),
                             "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", dst],
                            stdin=subprocess.PIPE)
    try:
        for i in range(n):
            k = i / (n - 1)
            e = k * k * (3 - 2 * k)                               # ease in-out
            z = zoom[0] + (zoom[1] - zoom[0]) * e
            vw, vh = bw / 1.2 / z, bh / 1.2 / z                    # the visible window in base pixels
            cx, cy = bw / 2, bh / 2
            room_x, room_y = (bw - vw) / 2, (bh - vh) / 2
            if move == "pan_left":
                cx += room_x * (0.8 - 1.6 * e)
            elif move == "pan_right":
                cx += room_x * (-0.8 + 1.6 * e)
            elif move == "push_in_up":
                cy += room_y * (0.5 - 1.0 * e)
            x0, y0 = cx - vw / 2, cy - vh / 2
            fr = base.transform((W, H), Image.AFFINE, (vw / W, 0, x0, 0, vh / H, y0), resample=Image.BICUBIC)
            proc.stdin.write(fr.tobytes())
    finally:
        proc.stdin.close()
        proc.wait(timeout=600)
    return dst


# ---------------------------------------------------------------------------------------------------------------- render

def credit(meta: Optional[Dict[str, Any]]) -> str:
    m = meta or {}
    if m.get("user_supplied") and not m.get("author"):
        return ""
    who = str(m.get("author") or m.get("channel") or "").strip()
    src = str(m.get("provider") or m.get("source") or "").strip()
    src = {"pexels": "Pexels", "pixabay": "Pixabay", "youtube": "YouTube", "nasa": "NASA", "noaa": "NOAA", "coverr": "Coverr",
           "videvo": "Videvo", "mixkit": "Mixkit"}.get(src.lower(), src.title() if src.islower() else src)
    lic = str(m.get("license") or "").strip()
    if not who and not src:
        return ""
    text = "Footage: " + " / ".join(x for x in (who, src) if x)
    if lic and re.search(r"cc|creative|public", lic, re.I):
        text += f" ({lic})"
    return text[:90]


def _duration(path: str) -> float:
    try:
        return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                             timeout=30).strip())
    except Exception:  # noqa: BLE001
        return 0.0


def grade(src: str, dst: str, seek: float, seconds: float, look: str = "ocean", stretch: float = 1.0) -> str:
    """Fit, colour-grade (look: ocean = the cool blue world, neutral = natural land footage) and, for a clip a bit short for
    its beat, slow it down (stretch <= 1.8)."""
    from cinematic_explainer.render import H, W

    slow = f"setpts={stretch:.3f}*PTS," if stretch > 1.01 else ""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, seek):.3f}", "-t", f"{seconds / max(1.0, stretch) + 0.6:.3f}",
                    "-i", src, "-an",
                    "-vf", f"{slow}scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30,setsar=1,"
                           f"{GRADES.get(look, GRADE)}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", dst], check=True, timeout=600)
    return dst


DEPTH_MOVE = {  # action -> (parallax mode, amount): the near layer (the animal) moves against its own painted background
    "walk": ("lateral", 1.7), "run": ("lateral", 2.3), "flee": ("lateral", 2.3), "swim": ("lateral", 1.7),
    "attack": ("push", 1.6), "approach": ("push", 2.0), "fall": ("push", 1.2), "idle": ("lateral", 1.1), "": ("lateral", 1.0),
}


def docu_still(src: str, dst: str) -> str:
    """The reference's look on a painted picture: less colour, darker, a little more contrast, heavy dark edges."""
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
    if Path(dst).is_file() and Path(dst).stat().st_mtime >= Path(src).stat().st_mtime:
        return dst
    im = Image.open(src).convert("RGB")
    im = ImageEnhance.Color(im).enhance(0.72)
    im = ImageEnhance.Brightness(im).enhance(0.78)
    im = ImageEnhance.Contrast(im).enhance(1.08)
    w, h = im.size
    vig = Image.new("L", (w, h), 0)
    ImageDraw.Draw(vig).ellipse((-w * 0.12, -h * 0.16, w * 1.12, h * 1.16), fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(max(w, h) * 0.09))
    im = Image.composite(im, Image.new("RGB", (w, h), (4, 6, 9)), vig)
    im.save(dst)
    return dst


def depth_move(src: str, dst: str, seconds: float, action: str = "", seed: int = 0) -> bool:
    """One painted scene moved in real depth layers (health_cinema/puppet/layers.py: Depth Anything, far / mid / near cut-outs
    of the same picture, the gaps filled): the animal travels against its own background, lit and painted with it.
    False when the picture has no usable depth (a flat diagram): the caller moves the picture as a whole."""
    try:
        from cinematic_explainer.render import H, W
        from health_cinema.puppet import layers as PL
        mode, amount = DEPTH_MOVE.get(action, DEPTH_MOVE[""])
        out = PL.render_parallax(src, dst, seconds, fps=25, size=(W, H), seed=seed, params={"amount": amount, "mode": mode})
        return bool(out) and Path(dst).is_file()
    except Exception:  # noqa: BLE001
        return False


GENERIC_OK = re.compile(r"\b(landscape|savann?ah?|bush|grassland|plain|sky|sunset|forest|ocean|sea|underwater|desert|river|"
                        r"aerial|night|people|city|road)\b", re.I)


def clip_matches(query: str, record: Optional[Dict[str, Any]]) -> bool:
    """A stock clip is kept only when its own page names the animal it was searched for ('honey badger attack' must not
    be a buffalo on a road). Searches with no animal in them (a landscape) are taken as they are."""
    rec = record or {}
    f = R.read(str(query or ""))
    names = [a for a in f.animals if a[0] not in ("diver", "boat", "cage", "tooth")]
    if not names:
        return True
    text = " ".join(str(rec.get(k) or "") for k in ("source_url", "page_url", "url", "title", "tags", "description", "alt", "name"))
    text = re.sub(r"[-_/]+", " ", text.lower())
    for a in names[:1]:                                  # the animal the search is about (the first one named) must be there
        w = re.sub(r"(?<!s)s$", "", a[4].lower().strip())
        keys = {w} if " " in w else {w, w.split()[-1]}           # "honey badger" must say honey badger, not just badger
        if any(re.search(r"\b" + re.escape(k) + r"s?\b", text) for k in keys if len(k) > 2):
            return True
    return False


def green_screen(path: str) -> bool:
    """True for a picture still on its green screen (a cut-out source, never a finished scene)."""
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB").resize((64, 36))
        px = list(im.getdata())
        border = [px[i] for i in range(64)] + [px[i] for i in range(64 * 35, 64 * 36)]
        return sum(1 for r, g, b in border if g > 150 and g > r + 60 and g > b + 60) > 0.6 * len(border)
    except Exception:  # noqa: BLE001
        return False


def tab_pictures(plan: Dict[str, Any], images_dir: str) -> Dict[str, Dict[str, Any]]:
    """{beat: {"path"}} for the beat pictures the Visuals tab holds, read from its own records (relative paths resolved,
    green-screen sources left out)."""
    from asset_manager import AssetManifest
    d = Path(images_dir)
    man = AssetManifest(d)
    out: Dict[str, Dict[str, Any]] = {}
    for s in plan.get("clips") or []:
        if s.get("kind") not in ("picture", "act"):
            continue
        rec = man.get(str(s["scene_no"])) or {}
        lp = rec.get("local_path") or ""
        cands = [Path(lp), Path.cwd() / lp, d / Path(lp).name] if lp else []
        pic = next((str(c.resolve()) for c in cands if c.is_file()), None) or _picture_of(str(d / "x"), str(s["scene_no"]))
        if pic and str(pic).lower().endswith(IMAGE_EXT) and not green_screen(pic):
            out[str(s["scene_no"])] = {"path": pic, "meta": {"provider": "flow"}}
    return out


def _picture_of(path: str, scene_no: str) -> Optional[str]:
    """The still picture filed for a beat (NNN.png / .jpg next to the tab's own copy, or the manifest's local_path)."""
    d = Path(path).parent
    names = [f"{int(scene_no):03d}" if scene_no.isdigit() else scene_no, scene_no]
    for n in names:
        for ext in IMAGE_EXT:
            if (d / f"{n}{ext}").is_file():
                return str(d / f"{n}{ext}")
    try:
        from asset_manager import AssetManifest
        lp = (AssetManifest(d).get(scene_no) or {}).get("local_path")
        if lp and str(lp).lower().endswith(IMAGE_EXT) and Path(lp).is_file():
            return str(lp)
    except Exception:  # noqa: BLE001
        pass
    return None


def keyed_backdrop(path: str, length: float = 0.0, share: float = 0.22) -> bool:
    """True for a green- or blue-screen clip (a cut-out render, not real footage): in 3 sampled frames more than `share`
    of the pixels are one flat, saturated key colour."""
    from PIL import Image
    import io
    hits = 0
    for k in (0.2, 0.5, 0.8):
        try:
            out = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, length * k):.2f}", "-i", path, "-frames:v", "1",
                                  "-vf", "scale=96:54", "-f", "image2pipe", "-vcodec", "png", "-"],
                                 capture_output=True, timeout=60).stdout
            im = Image.open(io.BytesIO(out)).convert("RGB")
        except Exception:  # noqa: BLE001
            continue
        px = list(im.getdata())
        green = sum(1 for r, g, b in px if g > 120 and g > r + 50 and g > b + 50)
        blue = sum(1 for r, g, b in px if b > 170 and b > r + 90 and b > g + 40 and g < 120)
        if max(green, blue) > share * len(px):
            hits += 1
    return hits >= 2


def apply(plan: Dict[str, Any], found: Dict[str, Dict[str, Any]], black: str, work: str,
          log=lambda m: None) -> Tuple[List[Any], List[Any], List[Dict[str, Any]]]:
    """(shots, layers, used) with every slot whose clip was found cut in; `found` = {scene_no: {"path", "meta"}}."""
    from cinematic_explainer.render import Layer, Shot

    total = float(plan["total"])
    used: List[Dict[str, Any]] = []
    pics: Dict[str, str] = {}
    wd = Path(work)
    for s in plan.get("clips") or []:
        f = found.get(str(s["scene_no"]))
        if not f or not f.get("path") or not Path(f["path"]).is_file():
            continue
        a, b = float(s["start"]), float(s["end"])
        if s.get("kind") in ("picture", "act") and not str(f["path"]).lower().endswith(IMAGE_EXT):
            pic = _picture_of(f["path"], str(s["scene_no"]))     # the tab may hand back its own moving copy: use the picture
            if pic:
                f = dict(f, path=pic)
        if s.get("kind") in ("picture", "act") and green_screen(f["path"]):
            log(f"beat {s['scene_no']}: its picture is still on a green screen; remake it in the Visuals tab")
            continue
        if s.get("kind") in ("picture", "act") or str(f["path"]).lower().endswith(IMAGE_EXT):
            dst = wd / f"pic_{s['scene_no']}.mp4"
            if plan.get("mode") == "beats":               # every painted picture in the reference's dark documentary grade
                try:
                    f = dict(f, path=docu_still(f["path"], str(wd / f"docu_{s['scene_no']}.png")))
                except Exception:  # noqa: BLE001 - the picture as it was made
                    pass
            pics[str(s["scene_no"])] = str(f["path"])
            try:
                if not depth_move(f["path"], str(dst), b - a, str(s.get("action") or ""),
                                  int(s["scene_no"]) if str(s["scene_no"]).isdigit() else 0):
                    motion(f["path"], str(dst), b - a, str(s.get("move") or "push_in"))
            except Exception as ex:  # noqa: BLE001 - the stage stand-in shows instead
                log(f"picture for beat {s['scene_no']} skipped ({ex})")
                continue
            used.append({**s, "start": a, "end": b, "path": str(dst), "credit": ""})
            continue
        if s.get("kind") == "clip" and not clip_matches(str(s.get("query", "")), f.get("meta")):
            log(f"clip for beat {s['scene_no']} skipped: it does not show '{s.get('query')}'")
            continue
        src_len = _duration(f["path"])
        if src_len < 1.0:
            continue
        if keyed_backdrop(f["path"], src_len):
            log(f"clip for scene {s['scene_no']} skipped: green / blue screen (not real footage) - swap it in the Visuals tab")
            continue
        stretch = 1.0
        if s.get("kind") == "clip" and src_len - 0.2 < b - a:          # a beat clip a little short: slow it to fill its beat
            stretch = min(1.8, (b - a) / max(0.5, src_len - 0.2))
        b = min(b, a + max(1.0, (src_len - 0.2) * stretch))
        seek = 0.0 if src_len < (b - a) / stretch + 2.0 else min(1.5, src_len - (b - a) / stretch - 0.5)
        dst = wd / f"clip_{s['scene_no']}.mp4"
        try:
            grade(f["path"], str(dst), seek, b - a, str(s.get("grade") or "ocean"), stretch)
        except Exception as ex:  # noqa: BLE001 - a clip that cannot be graded keeps the drawn stage
            log(f"clip for scene {s['scene_no']} skipped ({ex})")
            continue
        used.append({**s, "start": a, "end": b, "path": str(dst), "credit": credit(f.get("meta"))})
    prints: Dict[str, str] = {}
    for s in plan.get("photos") or []:            # polaroid prints: one still frame of the clip the tab found
        f = found.get(str(s["scene_no"]))
        if not f or not f.get("path") or not Path(f["path"]).is_file():
            continue
        try:
            src_len = _duration(f["path"])
            if keyed_backdrop(f["path"], src_len):
                continue
            prints[str(s["scene_no"])] = still(f["path"], str(wd / f"photo_{s['scene_no']}.jpg"), min(1.5, src_len / 2))
        except Exception as ex:  # noqa: BLE001 - the print keeps its painted animal
            log(f"photo for print {s['scene_no']} skipped ({ex})")
    for s in plan.get("drawn") or []:                    # flat library animals acting on legs (ocean/act.animate_cast)
        a, b = float(s["start"]), float(s["end"])
        dst = wd / f"drawn_{s['scene_no']}.mp4"
        try:
            from . import act as ACT
            ACT.animate_cast(list(s["names"]), str(dst), b - a, str(s.get("action") or "idle"), str(s.get("set") or "savanna_night"),
                             str(s.get("facing") or "right"), int(s.get("seed") or 0), list(s.get("widths") or []) or None)
            used.append({**s, "start": a, "end": b, "path": str(dst), "credit": "", "kind": "drawn"})
        except Exception as ex:  # noqa: BLE001 - the plain set shows instead
            log(f"beat {s['scene_no']}: animal animation skipped ({ex})")
    if plan.get("mode") == "beats" and pics:             # a beat with no picture / clip: the nearest painted scene again,
        have = {str(u["scene_no"]) for u in used}         # with another move (never the drawn stand-in set)
        order = [str(x["scene_no"]) for x in plan.get("clips") or []]
        for s in plan.get("clips") or []:
            no = str(s["scene_no"])
            if no in have:
                continue
            i = order.index(no)
            near = next((pics[order[j]] for d in range(1, len(order)) for j in (i - d, i + d)
                         if 0 <= j < len(order) and order[j] in pics), None)
            if not near:
                continue
            a, b = float(s["start"]), float(s["end"])
            dst = wd / f"pic_{no}_near.mp4"
            try:
                motion(near, str(dst), b - a, MOTION_ALT[int(no) % len(MOTION_ALT)] if no.isdigit() else "pull_out")
            except Exception as ex:  # noqa: BLE001
                log(f"beat {no}: no stand-in picture ({ex})")
                continue
            used.append({**s, "start": a, "end": b, "path": str(dst), "credit": ""})
            log(f"beat {no}: no picture of its own; the nearest painted scene stands in")
    used.sort(key=lambda u: u["start"])
    shots: List[Any] = []
    t = 0.0
    for u in used:
        if u["start"] > t + 1e-3:
            shots.append(Shot(black, t, u["start"], t))
        shots.append(Shot(u["path"], u["start"], u["end"], 0.0))
        t = u["end"]
    if t < total - 1e-3 or not shots:
        shots.append(Shot(black, t, total, t))
    layers: List[Any] = []
    for ly in plan.get("layers") or []:
        p = dict(ly.get("params") or {})
        a, b = float(ly["start"]), float(ly["end"])
        if ly.get("name") == "ocean.lay_ocean":
            holes = [[u["start"] - a, u["end"] - a, u["credit"]] for u in used if u["end"] > a and u["start"] < b]
            if holes:
                p["holes"] = holes
            if prints:
                p["elements"] = [dict(e, args=dict(e.get("args") or {}, photo=prints[str((e.get("args") or {}).get("photo_slot"))]))
                                 if str((e.get("args") or {}).get("photo_slot")) in prints else e
                                 for e in p.get("elements") or []]
        layers.append(Layer(ly["name"], a, b, p))
    return shots, layers, used
