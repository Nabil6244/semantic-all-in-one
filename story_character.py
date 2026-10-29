"""One protagonist that looks the same in every picture of a story video (Agent C of the story build).

Everything here is machinery plus dry-run planning. Nothing in this module talks to Flow by itself: the one place that could,
`make_flow_generator`, takes a client object from the caller (providers.flow.client in a live run, a fake in tests).

Pieces
  character_sheet(p)            the fixed, verbatim sentence put in EVERY prompt that shows the character
  reference_prompts(p)          3-4 reference pictures (3/4 front, full body, side walk, hands/props) on plain cream
  select_references(...)        Flow takes at most 3 reference images per request: which 3 for a given shot
  build_character_request(...)  the Flow image request (SceneRow fields + reference paths + engine settings) for one shot
  ReferenceStore                project/state/story/character/<reference_key>/ + manifest.json (resume without regenerating)
  ensure_references(...)        make missing references with an injected generator, cached by prompt hash
  consistency_check(...)        cheap palette comparison + contact sheet. NOT a proof of consistency; judge by eye.
  plan_generation(...)          which pictures to generate, in what order, batched like the app's agent mode, dry-run report
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

# --- limits that mirror the Flow engine (flow-engine/lib/flow-references.js, flow-engine/config.js agent block) ---
MAX_REFERENCES = 3                      # flow-references.js MAX_REFERENCES (a request with more is refused)
MAX_REFERENCE_BYTES = 10 * 1024 * 1024  # flow-references.js MAX_REFERENCE_BYTES
OK_EXT = (".png", ".jpg", ".jpeg", ".webp")
AGENT_MAX_BATCH = 24                    # config.js agent.maxBatch: scenes per agent request
AGENT_MAX_CHARS = 12000                 # config.js agent.maxMessageChars
ASPECT_LANDSCAPE = "IMAGE_ASPECT_RATIO_LANDSCAPE"   # app.py FLOW_IMAGE_ASPECT_RATIOS
MIN_REFERENCE_SIDE = 256

STYLE = ("engraved sepia paper-collage illustration, ink outlines with fine cross-hatching, hand-cut paper edges, "
         "palette of sepia brown, terracotta, rust and warm cream, aged paper texture")
# Reference kinds, in priority order. The first two are always attached; the third slot is picked per shot.
REFERENCE_KINDS = ("front34", "fullbody", "sidewalk", "hands")
_KIND_TEXT = {
    "front34": "three-quarter view from the front, head to knees, standing relaxed, looking slightly to the side",
    "fullbody": "full body from head to feet, standing straight, facing forward, both feet visible on a thin floor line",
    "sidewalk": "full body in side view, walking to the right with a natural stride, both feet visible on a thin floor line",
    "hands": "close-up of the hands holding the character's usual props, the sleeves and cuffs of the clothing visible",
}

DEFAULT_PROTAGONIST: Dict[str, Any] = {
    "name": "the traveller",
    "age": "middle-aged",
    "gender": "man",
    "era": "present day",
    "clothing": "a rust-coloured knee-length coat over a cream shirt, dark sepia trousers and plain boots",
    "silhouette": "medium build, slightly stooped shoulders, short hair, no hat",
    "props": "a small satchel",
    "face": "face-less engraved look: the face is only a soft sepia shadow with a hint of nose and brow line, no eyes, no mouth",
}


# ----------------------------------------------------------------------------------------------------------------------
# character sheet and prompts
# ----------------------------------------------------------------------------------------------------------------------
def _norm_protagonist(protagonist: Optional[dict]) -> dict:
    p = dict(DEFAULT_PROTAGONIST)
    for k, v in (protagonist or {}).items():
        if v not in (None, ""):
            p[k] = v
    if not p.get("reference_key"):
        slug = re.sub(r"[^a-z0-9]+", "-", str(p["name"]).lower()).strip("-") or "protagonist"
        p["reference_key"] = slug
    p["reference_key"] = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(p["reference_key"])).strip("-") or "protagonist"
    return p


def character_sheet(protagonist: Optional[dict] = None) -> dict:
    """The verbatim character sentence. `sentence` is inserted unchanged in every prompt with the character; `key` changes when
    any wording changes (so cached references are not reused for a different character)."""
    p = _norm_protagonist(protagonist)
    sentence = (f"The same recurring character in every picture: {p['age']} {p['gender']}, {p['era']}, wearing {p['clothing']}, "
                f"{p['silhouette']}, carrying {p['props']}; {p['face']}; drawn in the {STYLE}.")
    sentence = " ".join(sentence.split())
    return {"sentence": sentence, "style": STYLE, "reference_key": p["reference_key"],
            "key": hashlib.sha1(sentence.encode("utf-8")).hexdigest()[:12], "protagonist": p}


def reference_prompts(protagonist: Optional[dict] = None, kinds: Sequence[str] = REFERENCE_KINDS) -> List[dict]:
    """The reference pictures to make: [{kind, prompt, depends_on}]. `front34` is made first without references; the rest are
    made with it attached (the ones that follow look like it)."""
    sheet = character_sheet(protagonist)
    out = []
    for kind in kinds:
        if kind not in _KIND_TEXT:
            raise ValueError(f"unknown reference kind {kind!r}")
        prompt = (f"{sheet['sentence']} Character reference picture: {_KIND_TEXT[kind]}. Plain flat cream paper background, nothing else "
                  f"in the picture, no scenery, no text, no captions, no frame, soft even light, centered, 16:9.")
        out.append({"kind": kind, "prompt": " ".join(prompt.split()), "depends_on": [] if kind == kinds[0] else [kinds[0]]})
    return out


def prompt_hash(prompt: str, ref_hashes: Sequence[str] = ()) -> str:
    h = hashlib.sha1((prompt + "||" + ",".join(ref_hashes)).encode("utf-8")).hexdigest()
    return h[:16]


# ----------------------------------------------------------------------------------------------------------------------
# which references, and the request
# ----------------------------------------------------------------------------------------------------------------------
_WALK = re.compile(r"\b(walk\w*|run\w*|ran|travel\w*|journey|march\w*|leav\w*|arriv\w*|enter\w*|go(?:es|ing)?|went|moves?|moving)\b", re.I)
_HANDS = re.compile(r"\b(hold\w*|carr\w*|pick\w*|hand\w*|grab\w*|open\w*|take\w*|took|giv\w*|put|place\w*|touch\w*)\b", re.I)


def select_references(shot: dict, references: Dict[str, str], limit: int = MAX_REFERENCES) -> List[str]:
    """At most `limit` (Flow's maximum is 3) paths from {kind: path}: front34 and fullbody always, then sidewalk for movement shots,
    hands for handling shots, else sidewalk. Order is stable so the engine's reference key (and ledger dedupe) is stable."""
    limit = max(0, min(int(limit), MAX_REFERENCES))
    text = " ".join(str(shot.get(k) or "") for k in ("prompt_en", "text", "subject"))
    third = "hands" if (_HANDS.search(text) and not _WALK.search(text)) else "sidewalk"
    order = ["front34", "fullbody", third, "hands" if third == "sidewalk" else "sidewalk"]
    picked = []
    for kind in order:
        p = references.get(kind)
        if p and p not in picked:
            picked.append(str(p))
        if len(picked) >= limit:
            break
    return picked


def composition_hint(shot: dict, ordinal: int = 0) -> str:
    side = str(shot.get("character_side") or shot.get("side") or "").lower()
    if side not in ("left", "right"):
        side = "left" if ordinal % 2 == 0 else "right"
    return (f"Composition: the character stands on the {side} third of the frame, full figure with both feet visible on a clear floor "
            f"line in the lower part of the picture, the rest of the frame is open scenery so the figure can walk in or out sideways; "
            f"the character is small to medium in the frame, never cropped.")


def build_character_request(shot: dict, protagonist: Optional[dict] = None, references: Optional[Dict[str, str]] = None, *,
                            ordinal: int = 0, aspect: str = ASPECT_LANDSCAPE, base_settings: Optional[dict] = None) -> dict:
    """The Flow image request for one shot, in the shape the existing path takes: SceneRow fields (scene_number is the shot_id,
    asset_type image) plus `settings` for providers.flow / client.generate. A shot without the character is returned with its
    prompt unchanged and no references."""
    sid = str(shot.get("shot_id") if shot.get("shot_id") is not None else shot.get("scene_no"))
    base = str(shot.get("prompt_en") or "").strip()
    settings = {"mediaKind": "image", "aspectRatio": aspect, **(base_settings or {})}
    settings.pop("referenceImages", None)
    req = {"shot_id": sid, "scene_number": sid, "script_segment": str(shot.get("text") or ""), "asset_type": "image",
           "prompt": base, "reference_images": [], "uses_character": False, "settings": settings, "prompt_key": sid}
    if not shot.get("character"):
        return req
    sheet = character_sheet(protagonist)
    refs = select_references(shot, references or {})
    if refs and not all(os.path.isabs(r) for r in refs):
        refs = [str(Path(r).resolve()) for r in refs]
    req["prompt"] = " ".join(f"{sheet['sentence']} {base} {composition_hint(shot, ordinal)}".split())
    req["reference_images"] = refs
    req["uses_character"] = True
    if refs:
        settings["referenceImages"] = list(refs)
    return req


def to_scene_row(req: dict):
    """providers.base.SceneRow for a request (what the app's FlowProvider.resolve_batch takes)."""
    from providers.base import SceneRow
    return SceneRow.from_csv_row({"scene_number": req["scene_number"], "script_segment": req.get("script_segment", ""),
                                  "asset_type": req["asset_type"], "prompt": req["prompt"]})


# ----------------------------------------------------------------------------------------------------------------------
# reference store
# ----------------------------------------------------------------------------------------------------------------------
def _decode(path: Path) -> tuple:
    from PIL import Image
    with Image.open(path) as im:
        im.load()
        return im.size


class ReferenceStore:
    """project/state/story/character/<reference_key>/{front34.png,...,manifest.json}."""

    def __init__(self, root, reference_key: str = "protagonist"):
        self.reference_key = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(reference_key)) or "protagonist"
        self.dir = Path(root) / self.reference_key
        self.manifest_path = self.dir / "manifest.json"

    @classmethod
    def for_project(cls, project_dir, protagonist: Optional[dict] = None) -> "ReferenceStore":
        return cls(Path(project_dir) / "state" / "story" / "character", _norm_protagonist(protagonist)["reference_key"])

    def _read(self) -> dict:
        try:
            m = json.loads(self.manifest_path.read_text("utf-8"))
            if isinstance(m, dict) and isinstance(m.get("items"), dict):
                return m
        except (OSError, ValueError):
            pass
        return {"reference_key": self.reference_key, "items": {}}

    def _write(self, m: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(m, indent=2, sort_keys=True), "utf-8")
        os.replace(tmp, self.manifest_path)

    def add(self, kind: str, src, prompt_hash_: str, sheet_key: str = "") -> Path:
        src = Path(src)
        if src.suffix.lower() not in OK_EXT:
            raise ValueError(f"reference must be PNG, JPEG or WebP, got {src.suffix!r}")
        self.dir.mkdir(parents=True, exist_ok=True)
        dst = self.dir / f"{kind}{src.suffix.lower()}"
        if src.resolve() != dst.resolve():
            shutil.copyfile(src, dst)
        for other in self.dir.glob(f"{kind}.*"):      # a changed extension must not leave a stale twin
            if other != dst and other.suffix.lower() in OK_EXT:
                other.unlink()
        m = self._read()
        m["items"][kind] = {"file": dst.name, "prompt_hash": prompt_hash_, "sheet_key": sheet_key, "bytes": dst.stat().st_size,
                            "sha1": hashlib.sha1(dst.read_bytes()).hexdigest(), "created": int(time.time())}
        self._write(m)
        return dst

    def list(self) -> Dict[str, str]:
        """{kind: absolute path} of manifest entries whose file exists."""
        out = {}
        for kind, it in self._read()["items"].items():
            f = self.dir / it.get("file", "")
            if f.is_file():
                out[kind] = str(f.resolve())
        return out

    def entry(self, kind: str) -> Optional[dict]:
        return self._read()["items"].get(kind)

    def validate(self, kind: Optional[str] = None) -> List[str]:
        """Problems (empty = fine): file missing, empty, too big, not decodable, too small, changed since recorded."""
        problems = []
        items = self._read()["items"]
        for k, it in items.items():
            if kind and k != kind:
                continue
            f = self.dir / it.get("file", "")
            if not f.is_file():
                problems.append(f"{k}: file missing ({f.name})")
                continue
            size = f.stat().st_size
            if size == 0:
                problems.append(f"{k}: file is empty")
                continue
            if size > MAX_REFERENCE_BYTES:
                problems.append(f"{k}: {size / 1048576:.1f} MB is over Flow's {MAX_REFERENCE_BYTES // 1048576} MB limit")
            try:
                w, h = _decode(f)
                if min(w, h) < MIN_REFERENCE_SIDE:
                    problems.append(f"{k}: {w}x{h} is smaller than {MIN_REFERENCE_SIDE}px")
            except Exception as e:  # noqa: BLE001 - any decode failure is a problem to report
                problems.append(f"{k}: not a readable picture ({type(e).__name__})")
            if it.get("sha1") and hashlib.sha1(f.read_bytes()).hexdigest() != it["sha1"]:
                problems.append(f"{k}: file changed since it was recorded (replaced by hand? update the manifest by add())")
        if kind and kind not in items:
            problems.append(f"{kind}: not in the store")
        return problems

    def is_current(self, kind: str, phash: str) -> bool:
        it = self.entry(kind)
        return bool(it and it.get("prompt_hash") == phash and not self.validate(kind))


def ensure_references(protagonist: Optional[dict], generator: Callable[[dict], Any], store: ReferenceStore, *,
                      kinds: Sequence[str] = REFERENCE_KINDS, log: Callable[[str], None] = lambda m: None) -> Dict[str, str]:
    """Make the missing or stale references. `generator(request)` gets {"kind","prompt","reference_images":[paths],"prompt_key",
    "settings"} and returns the path of the picture it made. front34 is made alone first; the rest get it attached so they look like it.
    A reference whose prompt hash is unchanged and whose file still validates is not generated again (resume after a stop)."""
    sheet = character_sheet(protagonist)
    prompts = {r["kind"]: r["prompt"] for r in reference_prompts(protagonist, kinds)}
    first = kinds[0]
    first_hash = ""
    for kind in kinds:
        refs: List[str] = []
        parent_hash = []
        if kind != first:
            fp = store.list().get(first)
            if fp:
                refs = [fp]
                parent_hash = [first_hash]
        ph = prompt_hash(prompts[kind], parent_hash)
        if kind == first:
            first_hash = ph
        if store.is_current(kind, ph):
            log(f"[character] reference {kind}: kept (prompt unchanged)")
            continue
        log(f"[character] reference {kind}: generating")
        req = {"kind": kind, "prompt": prompts[kind], "reference_images": refs, "prompt_key": f"{store.reference_key}_{kind}",
               "settings": {"mediaKind": "image", "aspectRatio": ASPECT_LANDSCAPE, **({"referenceImages": refs} if refs else {})}}
        made = generator(req)
        if not made or not Path(made).is_file():
            raise RuntimeError(f"reference {kind}: the generator returned no picture")
        store.add(kind, made, ph, sheet["key"])
        bad = store.validate(kind)
        if bad:
            raise RuntimeError("; ".join(bad))
        if kind == first:
            first_hash = ph
    return store.list()


def make_flow_generator(client, out_dir, *, timeout_s: float = 900.0) -> Callable[[dict], str]:
    """A generator for ensure_references / shot pictures from a Flow engine client (providers.flow.client.FlowClient). Same
    protocol as product_trailer.scenepack.generate_scene_pack: client.generate(prompts, settings, prompt_keys) then wait for
    GENERATE_DONE. One request = one picture. Not used in tests except with a fake client; a live run is approved separately."""
    out_dir = Path(out_dir)

    def gen(req: dict) -> str:
        run_dir = out_dir / f"flow_{req['prompt_key']}"
        run_dir.mkdir(parents=True, exist_ok=True)
        settings = {"outputDir": str(run_dir.resolve()), **req["settings"]}
        events: List[dict] = []
        unsub = client.subscribe(events.append)
        try:
            client.generate([req["prompt"]], settings=settings, prompt_keys=[req["prompt_key"]])
            client.wait_for(lambda m: m.get("type") in ("GENERATE_DONE", "BATCH_DONE") or bool(m.get("generateError")), timeout=timeout_s)
        finally:
            unsub()
        for m in events:
            if m.get("type") == "PROMPT_RESULT" and m.get("status") == "done" and m.get("path"):
                return str(m["path"])
        err = next((m.get("error") or m.get("generateError") for m in events if m.get("error") or m.get("generateError")), "no picture")
        raise RuntimeError(f"Flow made no picture for {req['prompt_key']}: {err}")

    return gen


# ----------------------------------------------------------------------------------------------------------------------
# consistency check (cheap, honest)
# ----------------------------------------------------------------------------------------------------------------------
def palette_histogram(path, bbox: Optional[Sequence[float]] = None, bins: int = 4, ignore_paper: bool = True) -> List[float]:
    """Normalised colour histogram (bins^3) of the picture or of bbox=(x0,y0,x1,y1) as 0..1 fractions. With ignore_paper the
    cream background (all channels > 180 and low saturation) is left out so the figure's colours decide, not the paper."""
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        if bbox:
            w, h = im.size
            x0, y0, x1, y1 = bbox
            im = im.crop((int(x0 * w), int(y0 * h), max(int(x0 * w) + 1, int(x1 * w)), max(int(y0 * h) + 1, int(y1 * h))))
        im.thumbnail((160, 160))
        px = list(im.get_flattened_data() if hasattr(im, 'get_flattened_data') else im.getdata())
    step = 256 // bins
    hist = [0.0] * (bins ** 3)
    n = 0
    for r, g, b in px:
        if ignore_paper and min(r, g, b) > 180 and max(r, g, b) - min(r, g, b) < 80:
            continue
        hist[(r // step) * bins * bins + (g // step) * bins + (b // step)] += 1
        n += 1
    if n == 0:
        return hist
    return [v / n for v in hist]


def _intersect(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(min(x, y) for x, y in zip(a, b))


def _median(v: List[float]) -> float:
    s = sorted(v)
    n = len(s)
    return 0.0 if not n else (s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2)


def consistency_check(images: Sequence, bboxes: Optional[Sequence[Optional[Sequence[float]]]] = None, *, min_score: float = 0.35,
                      outlier_mads: float = 3.0, sheet_path=None, labels: Optional[Sequence[str]] = None) -> dict:
    """Compare the colour palette of each picture (or its bbox) with the mean palette of all the OTHER pictures (histogram
    intersection, 1 = identical). A picture is flagged when its score is below min_score, or far below the median of the scores
    (median - outlier_mads * MAD, with a floor on the MAD so a tight group does not flag everything). With fewer than 3 pictures
    only min_score applies. This catches a wrong palette (a blue coat, a missing coat), NOT a different face, outfit cut, age or
    pose: real consistency is judged by eye on the contact sheet. Returns {scores, flagged, median, threshold, sheet}."""
    images = [Path(i) for i in images]
    bboxes = list(bboxes) if bboxes else [None] * len(images)
    labels = list(labels) if labels else [p.stem for p in images]
    hists = [palette_histogram(p, bboxes[i] if i < len(bboxes) else None) for i, p in enumerate(images)]
    scores: List[float] = []
    for i, h in enumerate(hists):
        others = [x for j, x in enumerate(hists) if j != i]
        if not others:
            scores.append(1.0)
            continue
        mean = [sum(col) / len(others) for col in zip(*others)]
        scores.append(round(_intersect(h, mean), 4))
    med = _median(scores)
    thr = min_score
    if len(scores) >= 3:
        mad = max(_median([abs(s - med) for s in scores]), 0.03)
        thr = max(min_score, med - outlier_mads * mad)
    flagged = [i for i, s in enumerate(scores) if s < thr]
    sheet = None
    if sheet_path is not None and images:
        sheet = str(contact_sheet(images, sheet_path, labels=labels, flagged=flagged, scores=scores))
    return {"scores": scores, "flagged": flagged, "flagged_labels": [labels[i] for i in flagged], "median": round(med, 4),
            "threshold": round(thr, 4), "sheet": sheet,
            "note": "palette only; look at the contact sheet to judge face, outfit and proportions"}


def contact_sheet(images: Sequence, out_path, *, labels: Optional[Sequence[str]] = None, flagged: Sequence[int] = (),
                  scores: Optional[Sequence[float]] = None, cols: int = 4, thumb: int = 320) -> Path:
    """One picture with every image as a thumbnail, a label under each, and a red frame on the flagged ones."""
    from PIL import Image, ImageDraw
    images = [Path(i) for i in images]
    cols = max(1, min(cols, len(images) or 1))
    rows = (len(images) + cols - 1) // cols
    th = int(thumb * 9 / 16)
    cell_h = th + 22
    sheet = Image.new("RGB", (cols * (thumb + 8) + 8, max(1, rows) * (cell_h + 8) + 8), (238, 226, 200))
    d = ImageDraw.Draw(sheet)
    for i, p in enumerate(images):
        x, y = 8 + (i % cols) * (thumb + 8), 8 + (i // cols) * (cell_h + 8)
        try:
            with Image.open(p) as im:
                im = im.convert("RGB")
                im.thumbnail((thumb, th))
                sheet.paste(im, (x + (thumb - im.width) // 2, y + (th - im.height) // 2))
        except Exception:  # noqa: BLE001 - an unreadable picture shows as an empty cell
            d.text((x + 4, y + 4), "unreadable", fill=(150, 0, 0))
        if i in flagged:
            d.rectangle([x - 2, y - 2, x + thumb + 1, y + th + 1], outline=(200, 30, 30), width=3)
        cap = (labels[i] if labels and i < len(labels) else p.stem)[:34]
        if scores is not None and i < len(scores):
            cap += f"  {scores[i]:.2f}"
        d.text((x, y + th + 4), cap, fill=(70, 40, 20))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)
    return out_path


# ----------------------------------------------------------------------------------------------------------------------
# generation plan (dry run)
# ----------------------------------------------------------------------------------------------------------------------
def _chunks(reqs: List[dict], max_batch: int = AGENT_MAX_BATCH, max_chars: int = AGENT_MAX_CHARS) -> List[List[dict]]:
    out: List[List[dict]] = []
    cur: List[dict] = []
    chars = 0
    for r in reqs:
        n = len(r["prompt"])
        if cur and (len(cur) >= max_batch or chars + n > max_chars):
            out.append(cur)
            cur, chars = [], 0
        cur.append(r)
        chars += n
    if cur:
        out.append(cur)
    return out


def plan_generation(shots: Sequence[dict], protagonist: Optional[dict] = None, budget: Optional[dict] = None, *,
                    store: Optional[ReferenceStore] = None, references: Optional[Dict[str, str]] = None,
                    done_shot_ids: Sequence = (), aspect: str = ASPECT_LANDSCAPE) -> dict:
    """Dry-run plan. Pictures to make: every shot with picture == "new" or character == true (a character shot always needs its own
    picture). Order: missing references (front34 first, the others after it), then character shots, then other new pictures.
    `budget` = {"max_images": N} cuts the tail (references are never cut; deferred shots are listed). Already-made shot ids in
    `done_shot_ids` are skipped. If no references exist yet (store empty, none passed) the character requests are planned with the
    paths the references WILL have, `refs_pending` is true, and the live run must make the references before those requests.
    Image generation is free in Flow (flow-engine orchestrator: only VIDEO consumes credits), so cost = counts; the app has no
    per-image credit constant."""
    budget = budget or {}
    p = _norm_protagonist(protagonist)
    sheet = character_sheet(p)
    have = dict(references or (store.list() if store else {}))
    need = [k for k in REFERENCE_KINDS if k not in have]
    if store:                                    # stale prompts count as missing
        pr = {r["kind"]: r["prompt"] for r in reference_prompts(p)}
        front_hash = prompt_hash(pr["front34"])
        need = []
        for k in REFERENCE_KINDS:
            ph = front_hash if k == "front34" else prompt_hash(pr[k], [front_hash])
            if not store.is_current(k, ph):
                need.append(k)
    pending = bool(need)
    ref_paths = dict(have)
    for k in need:                               # where they will be
        base = store.dir if store else Path("<store>")
        ref_paths.setdefault(k, str(base / f"{k}.png"))
    done = {str(x) for x in done_shot_ids}
    char_reqs, other_reqs, skipped = [], [], []
    ordinal = 0
    for s in shots:
        sid = str(s.get("shot_id") if s.get("shot_id") is not None else s.get("scene_no"))
        if sid in done:
            skipped.append((sid, "already made"))
            continue
        if s.get("character"):
            char_reqs.append(build_character_request(s, p, ref_paths, ordinal=ordinal, aspect=aspect))
            ordinal += 1
        elif str(s.get("picture") or "").lower() == "new":
            other_reqs.append(build_character_request(s, p, None, aspect=aspect))
        else:
            skipped.append((sid, "existing picture, no character"))
    max_images = budget.get("max_images")
    ordered = char_reqs + other_reqs
    deferred: List[str] = []
    if max_images is not None:
        room = max(0, int(max_images) - len(need))
        deferred = [r["shot_id"] for r in ordered[room:]]
        ordered = ordered[:room]
    ref_reqs = [{"kind": r["kind"], "prompt": r["prompt"], "depends_on": r["depends_on"]} for r in reference_prompts(p) if r["kind"] in need]
    # runs: one GENERATE per identical reference set (the app attaches ONE reference set per run, see docs/story/character.md)
    groups: Dict[tuple, List[dict]] = {}
    for r in ordered:
        groups.setdefault(tuple(r["reference_images"]), []).append(r)
    runs = []
    for refs, reqs in groups.items():
        chunks = _chunks(reqs)
        runs.append({"references": list(refs), "shot_ids": [r["shot_id"] for r in reqs], "count": len(reqs),
                     "agent_requests": len(chunks), "batches": [[r["shot_id"] for r in c] for c in chunks]})
    n_images = len(need) + len(ordered)
    # references: front34 alone, then the others together (same attached reference) = at most 2 runs
    ref_runs = (1 if "front34" in need else 0) + (1 if any(k != "front34" for k in need) else 0)
    plan = {"protagonist": p["reference_key"], "sheet_key": sheet["key"], "references_needed": need, "reference_requests": ref_reqs,
            "refs_pending": pending, "character_requests": [r for r in ordered if r["uses_character"]],
            "other_requests": [r for r in ordered if not r["uses_character"]], "runs": runs, "skipped": skipped, "deferred": deferred,
            "counts": {"reference_images": len(need), "character_shots": sum(1 for r in ordered if r["uses_character"]),
                       "other_new_shots": sum(1 for r in ordered if not r["uses_character"]), "images": n_images,
                       "flow_runs": len(runs) + ref_runs, "agent_requests": sum(x["agent_requests"] for x in runs) + ref_runs,
                       "deferred": len(deferred), "skipped": len(skipped)},
            "cost": {"flow_image_credits": 0, "note": "Flow image generation costs no credits; count is the cost"}}
    plan["report"] = plan_report(plan)
    return plan


def plan_report(plan: dict) -> str:
    c = plan["counts"]
    L = [f"Story character plan (dry run) - protagonist '{plan['protagonist']}', sheet {plan['sheet_key']}",
         f"  images to generate: {c['images']}  (references {c['reference_images']}, character shots {c['character_shots']}, other new {c['other_new_shots']})",
         f"  Flow runs: {c['flow_runs']}, agent requests (<= {AGENT_MAX_BATCH} scenes each): {c['agent_requests']}; deferred by budget: {c['deferred']}; skipped: {c['skipped']}",
         f"  cost: {plan['cost']['note']}"]
    if plan["refs_pending"]:
        L.append("  step 1: references " + ", ".join(plan["references_needed"]) + " (front34 alone, the rest with front34 attached)")
    else:
        L.append("  step 1: references already in the store - nothing to make")
    for i, r in enumerate(plan["runs"], 2):
        refs = [Path(x).stem for x in r["references"]]
        L.append(f"  step {i}: {r['count']} picture(s), references {refs or 'none'}, {r['agent_requests']} agent request(s): shots {', '.join(r['shot_ids'][:12])}{' ...' if r['count'] > 12 else ''}")
    if plan["deferred"]:
        L.append("  deferred: " + ", ".join(plan["deferred"][:20]))
    return "\n".join(L)
