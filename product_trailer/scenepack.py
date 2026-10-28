"""Scene pack: the AI scenes of a product film, planned from a feature list and made in Flow with the phone's 3D references.

    features (product_trailer.csv_io)  ->  plan_scene_pack()  ->  scene_pack.json (what, which references, what it costs)
                                       ->  generate_scene_pack()  ->  one picture per AI scene (images are free; clips are only planned)

Rules (docs/product_trailer/TOOL_PLAN.md): AI never draws text, numbers or the chip, so those features stay 3D; a scene type never repeats
back to back; the setting rotates; every prompt says "no text, no logo" and points at the reference pictures; clips (Veo, credits) are
chosen only as a few hero moments and are never generated here, only counted.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

CLIP_CREDITS = 10          # Veo 3.1 Lite, 8 s, as quoted by Flow's agent on 2026-10-27
DAILY_CREDITS = 50         # the allowance seen on the account; it refreshes daily
CLIP_SECONDS = 8
FLOW_REF_LIMIT = 3

NO_BRAND = "no text and no logo on the phones"
DESIGN = ("The phones must look exactly like the phones in the reference images: same camera module, same lenses and lens positions, "
          "same flash, same frame and proportions")

# scene type -> reference file stems (from product_trailer.references), a prompt template, the features it suits
SCENE_TYPES: Dict[str, Dict[str, Any]] = {
    "hands_fan": {
        "refs": ["ref1_fan_backs", "ref4_one_three_quarter"], "features": ["design", "other", "durability"],
        "prompt": "Photorealistic photo. Two hands holding four smartphones fanned out, backs facing the camera, in {setting}. "
                  "Colours left to right: {colours}. {design}; {nobrand}. Natural light, shallow depth of field, 35mm lens, eye-level, realistic skin, 16:9."},
    "row_fronts": {
        "refs": ["ref2_row_fronts", "ref3_row_backs"], "features": ["display", "os", "design", "other", "battery", "charging"],
        "prompt": "Photorealistic photo. Four smartphones standing upright side by side on a table in {setting}. Screens facing the camera, each with a "
                  "glowing ripple wallpaper in its own colour ({colours}), exactly like the front reference image. {design}; {nobrand}. "
                  "Soft light, gentle reflections on the table, shallow depth of field, 35mm lens at table height, 16:9."},
    "row_backs": {
        "refs": ["ref3_row_backs", "ref4_one_three_quarter"], "features": ["design", "camera", "other"],
        "prompt": "Photorealistic photo. Four smartphones standing upright side by side on a table in {setting}, backs facing the camera. "
                  "Colours left to right: {colours}. {design}; {nobrand}. Soft light, shallow depth of field, 35mm lens at table height, 16:9."},
    "macro_camera": {
        "refs": ["ref5_camera_macro", "ref4_one_three_quarter"], "features": ["camera"],
        "prompt": "Photorealistic macro photo of the back of a {one_colour} smartphone standing on a table in {setting}. Show the raised camera module "
                  "exactly as in the reference images: same lens sizes, same positions, same flash. {nobrand}. Very shallow depth of field, soft window light "
                  "with a gentle highlight along the metal edge, blurred bright background, 85mm macro look, 16:9."},
    "single_table": {
        "refs": ["ref4_one_three_quarter", "ref5_camera_macro"], "features": ["battery", "charging", "design", "other"],
        "prompt": "Photorealistic photo. One {one_colour} smartphone standing on a table in {setting}, seen from the back at a three-quarter angle. "
                  "{design}; {nobrand}. Soft light, shallow depth of field, 50mm lens, 16:9."},
    "hands_screen": {
        "refs": ["ref2_row_fronts", "ref4_one_three_quarter"], "features": ["display", "os", "ai", "battery", "charging"],
        "prompt": "Photorealistic photo. A hand holding one {one_colour} smartphone with its glowing ripple-wallpaper screen facing the camera, in {setting}. "
                  "{design}; {nobrand}. Natural light, shallow depth of field, 35mm lens, realistic skin, 16:9."},
}

SETTINGS = [
    "a bright modern living room with a wooden shelf and a warm table lamp softly out of focus behind",
    "a bright industrial loft with large steel-frame windows and a soft city view behind",
    "a bright minimalist white gallery room with a skylight",
    "a sunlit workshop desk with tools and a pegboard softly out of focus",
    "a calm lakeside glass terrace with soft overcast daylight",
    "a modern studio with a softbox light and a blurred camera stand behind",
]

# features the AI must not carry: numbers, text, the chip -> 3D shots
THREE_D_ONLY = {"chip", "performance", "processor", "cpu", "gpu", "soc"}
CLIP_TYPES = ["hands_fan", "macro_camera", "row_fronts"]      # the hero moments a clip is worth 10 credits on


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "scene"


def _pick_type(feature: str, used: Sequence[str]) -> Optional[str]:
    """The scene type for a feature that suits it, the one used least recently first; None when the feature stays 3D."""
    f = _norm(feature).lower()
    if f in THREE_D_ONLY:
        return None
    fits = [t for t, d in SCENE_TYPES.items() if f in d["features"]] or [t for t, d in SCENE_TYPES.items() if "other" in d["features"]]
    last = used[-1] if used else None

    def age(t: str) -> int:
        idx = max((i for i, u in enumerate(used) if u == t), default=-1)
        return idx

    fits = [t for t in fits if t != last] or fits
    return min(fits, key=lambda t: (age(t), list(SCENE_TYPES).index(t)))


def plan_scene_pack(features: Sequence[Dict[str, Any]], phone: str, colours: Sequence[str], *, max_clips: int = 3,
                    settings: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """The plan for every feature row: an AI still, an AI clip (a few hero moments) or a 3D shot. Pure and deterministic."""
    cols = [c for c in colours if c] or ["Black", "Sky Blue", "Pink", "White"]
    one = cols[1] if len(cols) > 1 else cols[0]
    rooms = list(settings) if settings else SETTINGS
    scenes: List[Dict[str, Any]] = []
    used: List[str] = []
    n_ai = 0
    for i, row in enumerate(features):
        n = i + 1
        feature = _norm(row.get("feature")) or "other"
        caption = _norm(row.get("value")) or _norm(row.get("kicker")) or feature
        stype = _pick_type(feature, used)
        base = {"n": n, "feature": feature, "caption": caption}
        if stype is None:
            scenes.append({**base, "source": "3d", "type": None, "reason": "numbers, text and chips stay 3D"})
            continue
        d = SCENE_TYPES[stype]
        setting = rooms[n_ai % len(rooms)]
        prompt = d["prompt"].format(setting=setting, colours=", ".join(c.lower() for c in cols), one_colour=one.lower(), design=DESIGN, nobrand=NO_BRAND)
        used.append(stype)
        n_ai += 1
        scenes.append({**base, "source": "ai_still", "type": stype, "setting": setting, "prompt": prompt, "refs": list(d["refs"][:FLOW_REF_LIMIT]),
                       "key": f"{_slug(phone)}-{n:03d}-{stype}"})
    # a few hero moments become clips: the earliest scenes of the preferred types, never two in a row
    clips = 0
    for want in CLIP_TYPES:
        if clips >= max_clips:
            break
        for k, s in enumerate(scenes):
            prev_clip = k > 0 and scenes[k - 1].get("source") == "ai_clip"
            if s["source"] == "ai_still" and s["type"] == want and not prev_clip:
                s["source"] = "ai_clip"
                clips += 1
                break
    return {"phone": phone, "colours": cols, "scenes": scenes, "estimate": estimate(scenes)}


def estimate(scenes: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    images = sum(1 for s in scenes if s["source"] in ("ai_still", "ai_clip"))
    clips = sum(1 for s in scenes if s["source"] == "ai_clip")
    credits = clips * CLIP_CREDITS
    return {"ai_images": images, "ai_clips": clips, "three_d_shots": sum(1 for s in scenes if s["source"] == "3d"), "image_credits": 0,
            "clip_credits": credits, "clip_seconds": clips * CLIP_SECONDS, "daily_allowance": DAILY_CREDITS,
            "days_needed": max(1, -(-credits // DAILY_CREDITS)) if credits else 0}


def describe(pack: Dict[str, Any]) -> str:
    e = pack["estimate"]
    lines = [f"Scene pack for {pack['phone']}: {e['ai_images']} AI images (0 credits), {e['ai_clips']} clips ({e['clip_credits']} credits, "
             f"{e['days_needed']} day(s) of the {e['daily_allowance']}-credit allowance), {e['three_d_shots']} 3D shots."]
    for s in pack["scenes"]:
        tag = {"3d": "3D", "ai_still": "AI still", "ai_clip": "AI clip"}[s["source"]]
        lines.append(f"  {s['n']:>2}. {tag:8} {s['feature']:<10} {s['caption'][:28]:<28} {s.get('type') or '-'}")
    return "\n".join(lines)


def write_pack(pack: Dict[str, Any], out_dir) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    p = out / "scene_pack.json"
    p.write_text(json.dumps(pack, indent=1, ensure_ascii=False), encoding="utf-8")
    return p


def resolve_refs(scene: Dict[str, Any], refs_dir) -> List[str]:
    """Absolute reference file paths for a scene, from the folder product_trailer.references wrote; raises when one is missing."""
    out = []
    for stem in scene["refs"]:
        f = Path(refs_dir) / f"{stem}.jpg"
        if not f.is_file():
            raise FileNotFoundError(f"reference image missing: {f} (run python -m product_trailer.references first)")
        out.append(str(f.resolve()))
    return out


def generate_scene_pack(pack: Dict[str, Any], refs_dir, out_dir, client, *, log: Callable[[str], None] = print, timeout_s: float = 900.0,
                        base_settings: Optional[dict] = None) -> Dict[int, Dict[str, Any]]:
    """Make every AI scene's picture in Flow (images only; clips are never generated here). Scenes with the same references go in one
    request. `client` is a Flow engine client (providers.flow.client). Returns {scene n: {"status": "done"|"failed", "path"?, "error"?}}."""
    out_dir = Path(out_dir)
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for s in pack["scenes"]:
        if s["source"] in ("ai_still", "ai_clip"):
            groups.setdefault(tuple(s["refs"]), []).append(s)
    results: Dict[int, Dict[str, Any]] = {}
    for gi, (_refs, scenes) in enumerate(groups.items()):
        ref_paths = resolve_refs(scenes[0], refs_dir)
        run_dir = out_dir / f"flow_run_{gi + 1}"
        run_dir.mkdir(parents=True, exist_ok=True)
        settings = {"mediaKind": "image", "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE", "outputDir": str(run_dir), **(base_settings or {}),
                    "referenceImages": ref_paths}
        prompts = [s["prompt"] for s in scenes]
        events: List[dict] = []
        unsubscribe = client.subscribe(events.append)
        try:
            log(f"Flow request {gi + 1}/{len(groups)}: {len(prompts)} scene(s) with {len(ref_paths)} reference image(s)")
            client.generate(prompts, settings=settings, prompt_keys=[s["key"] for s in scenes])
            client.wait_for(lambda m: m.get("type") in ("GENERATE_DONE", "BATCH_DONE") or bool(m.get("generateError")), timeout=timeout_s)
        finally:
            unsubscribe()
        by_index = {m.get("index"): m for m in events if m.get("type") == "PROMPT_RESULT"}
        errors = [m.get("generateError") for m in events if m.get("generateError")]
        for k, s in enumerate(scenes):
            m = by_index.get(k)
            if m and m.get("status") == "done" and m.get("path"):
                dst = out_dir / "images" / f"scene_{s['n']:03d}_{s['type']}{Path(str(m['path'])).suffix or '.png'}"
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(Path(m["path"]).read_bytes())
                results[s["n"]] = {"status": "done", "path": str(dst)}
            else:
                results[s["n"]] = {"status": "failed", "error": (m or {}).get("error") or (errors[0] if errors else "Flow returned no picture for this scene")}
    return results


def main(argv: Optional[Sequence[str]] = None) -> int:
    """python -m product_trailer.scenepack <features.csv> --out <folder> [--phone NAME] [--clips N]: plan only (nothing is sent to Flow)."""
    import argparse

    from . import references
    from .csv_io import read_csv

    ap = argparse.ArgumentParser(prog="python -m product_trailer.scenepack", description="Plan the AI scenes of a product film (no Flow call, no credits).")
    ap.add_argument("csv", help="feature CSV (docs/product_trailer/samples/*.csv)")
    ap.add_argument("--out", required=True, help="folder for scene_pack.json")
    ap.add_argument("--phone", help="preset name (default: the CSV's phone or product)")
    ap.add_argument("--clips", type=int, default=3, help="how many hero clips to plan (10 credits each; never generated here)")
    a = ap.parse_args(argv)
    data = read_csv(a.csv)
    phone = a.phone or data["product"].get("phone") or data["product"].get("name") or "phone"
    pack = plan_scene_pack(data["features"], phone, references.preset_colours(phone), max_clips=a.clips)
    print(describe(pack))
    print(write_pack(pack, a.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
