"""Flow pictures for Rules Horror: the subject's poses (flat white shapes on pure black) and the reveal close-ups.

`requests(data)` lists what the CSV needs, one numbered request per (subject, pose) and per close-up row that has a `prompt`. They become the Visuals
tab's rows (visual_bridge) so Retry, Change source and Local clip work. `make(...)` asks Flow (images only): the first pose alone, then the rest with it
attached as a reference so the subject keeps its look. A picture that is missing or failed is never a stop: the render draws the code figure instead.
`picture_map(...)` is what the render reads: {"deer:stand_side": path, "closeup:12": path}."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

STYLE = ("Flat solid pure white silhouette illustration with a few thin black inner detail lines only. Pure black background (#000000), completely empty: "
         "no floor, no ground line, no shadow, no gradient, no texture, no text, no other objects. The whole subject inside the frame with margin. "
         "The same subject with the same proportions in every pose. ")
POSE_TEXT = {
    "stand_side": "Pose: standing still, side view, facing left, head level, all legs visible.",
    "stand_front": "Pose: standing still, seen straight from the front, head facing the viewer, symmetrical.",
    "head_turned": "Pose: standing, body in side view, head turned sharply to look toward the viewer.",
    "stare": "Pose: head-on, staring directly into the camera, head raised, body seen from the front.",
    "walk": "Pose: mid-stride walking, side view facing right, one front leg lifted.",
    "head_low": "Pose: standing in side view with the neck bent and the head lowered close to the ground.",
    "close_up_face": "Pose: close-up of the head and upper neck only, filling the frame, facing the viewer.",
    "look_back": "Pose: walking away to the right, body in side view, head turned back over its shoulder looking at the viewer.",
}
REFERENCE_POSE = "stand_side"
SETS_WITH_PICTURES = ("closeup",)


def key_of(subject: str, pose: str) -> str:
    return f"{subject}:{pose or REFERENCE_POSE}"


def requests(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """[{n, kind, key, subject, pose, row, prompt}] in a stable order; n counts from 1. The reference pose of each subject comes first."""
    meta = data.get("meta", {})
    desc = meta.get("subject")
    sub_desc = (desc[1] if isinstance(desc, list) and len(desc) > 1 else "") or ""
    out: List[Dict[str, Any]] = []
    seen = set()
    rows = data.get("rows", [])
    wanted: Dict[str, List[str]] = {}
    for r in rows:
        if r["subject"] and r["set"] != "closeup":      # a close-up row is its own picture (its prompt), not a pose of the subject
            wanted.setdefault(r["subject"], [])
            pose = r["pose"] or REFERENCE_POSE
            if pose not in wanted[r["subject"]]:
                wanted[r["subject"]].append(pose)
    for subject, poses in wanted.items():
        order = list(poses)
        poses.sort(key=lambda p: (p != REFERENCE_POSE, order.index(p)))
        if REFERENCE_POSE not in poses and len(poses) > 1:
            poses.insert(0, REFERENCE_POSE)       # the reference everything else is attached to
        for pose in poses:
            k = key_of(subject, pose)
            if k in seen:
                continue
            seen.add(k)
            text = POSE_TEXT.get(pose, f"Pose: {pose.replace('_', ' ')}.")
            out.append({"n": len(out) + 1, "kind": "pose", "key": k, "subject": subject, "pose": pose, "row": None,
                        "prompt": f"{STYLE}Subject: {sub_desc or subject}. {text}"})
    for i, r in enumerate(rows):
        if r["set"] == "closeup" and r["prompt"]:
            out.append({"n": len(out) + 1, "kind": "closeup", "key": f"closeup:{i}", "subject": r["subject"], "pose": "", "row": i,
                        "prompt": f"{STYLE}{r['prompt']}"})
    return out


def save_index(folder: Path, reqs: List[Dict[str, Any]]) -> None:
    Path(folder).mkdir(parents=True, exist_ok=True)
    (Path(folder) / "requests.json").write_text(json.dumps(reqs, indent=1), encoding="utf-8")


def load_index(folder: Path) -> List[Dict[str, Any]]:
    try:
        return json.loads((Path(folder) / "requests.json").read_text(encoding="utf-8"))
    except Exception:
        return []


def make(reqs: List[Dict[str, Any]], out_dir: Path, client, *, log: Callable[[str], None] = print, cancel: Callable[[], bool] = lambda: False,
         timeout_s: float = 300.0, skip: Optional[Dict[int, str]] = None) -> Dict[int, Dict[str, Any]]:
    """Ask Flow (images only) one request at a time; the first pose of each subject is the reference for the rest. -> {n: {"status", "path"|"error"}}.
    `skip` = {n: path} of pictures that already exist (not made again). Stops cleanly when cancel() is true."""
    from story_character import make_flow_generator

    out_dir = Path(out_dir)
    gen = make_flow_generator(client, out_dir, timeout_s=timeout_s)
    res: Dict[int, Dict[str, Any]] = {}
    refs: Dict[str, str] = {}
    for r in reqs:
        if skip and r["n"] in skip and Path(skip[r["n"]]).is_file():
            res[r["n"]] = {"status": "done", "path": skip[r["n"]]}
            if r["kind"] == "pose" and r["pose"] == REFERENCE_POSE:
                refs[r["subject"]] = skip[r["n"]]
            continue
    for r in reqs:
        if r["n"] in res:
            continue
        if cancel():
            res[r["n"]] = {"status": "failed", "error": "Stopped."}
            continue
        ref = refs.get(r["subject"]) if r["subject"] and not (r["kind"] == "pose" and r["pose"] == REFERENCE_POSE) else None
        req = {"prompt": r["prompt"], "prompt_key": f"rh_{r['n']:03d}_{re.sub(r'[^a-z0-9]+', '_', r['key'])}",
               "settings": {"mediaKind": "image", "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE", **({"referenceImages": [ref]} if ref else {})}}
        log(f"Flow picture {r['n']}/{len(reqs)}: {r['key']}{' (with the reference)' if ref else ''}")
        try:
            made = gen(req)
            dst = out_dir / "images" / f"rh_{r['n']:03d}{Path(str(made)).suffix or '.png'}"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(made, dst)
            res[r["n"]] = {"status": "done", "path": str(dst)}
            if r["kind"] == "pose" and r["pose"] == REFERENCE_POSE:
                refs[r["subject"]] = str(dst)
        except Exception as exc:  # noqa: BLE001 -- one failed picture never stops the rest: the render draws the code figure for it
            res[r["n"]] = {"status": "failed", "error": str(exc)[:300]}
            log(f"Flow picture {r['n']} failed: {str(exc)[:160]}")
            if sum(1 for v in res.values() if v["status"] == "failed") >= 3 and not any(v["status"] == "done" for v in res.values()):
                log("Flow made no picture in three tries; stopping here (the code figure is used for the rest).")
                for rr in reqs:
                    res.setdefault(rr["n"], {"status": "failed", "error": "not tried after three failures"})
                break
    return res


def picture_map(reqs: List[Dict[str, Any]], records: Dict[int, Dict[str, Any]]) -> Dict[str, str]:
    """{key: path} for the requests whose picture exists (records = visual_bridge.records: {n: {"path": ...}})."""
    out = {}
    for r in reqs:
        p = (records.get(r["n"]) or {}).get("path")
        if p and Path(p).is_file():
            out[r["key"]] = p
    return out
