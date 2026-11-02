"""Quality gate on the plan, before anything is drawn (render 053 audit: a third of the video on one plate, a text opening, 3D framed on the wrong body part).
It reads the scene list only (no rendering, no Flow, no network: a few milliseconds), so it costs no render time. `check` lists what is wrong; `repair` fixes what it can
in the plan itself (a scene that fails becomes a Flow picture of its own words when pictures are on, else the director's next look), then checks again.

Checks (fractions of the video's length):
  opening_text     the first scene is words, not a picture
  one_picture      one library picture (plate, figure, pose) fills more than ONE_PICTURE_MAX
  pictures         drawn pictures (Flow, pose, figure with a part lit, anatomy, 3D) under PICTURE_MIN
  text_only        scenes shown as words alone over TEXT_MAX
  plate_repeat     the same plate back within PLATE_GAP_S
  bad_3d           a 3D clip of a muscle group whose box is not on its limb (the 053 "forearm" that framed the thighs)"""
from __future__ import annotations
import json
from typing import Dict, List

ONE_PICTURE_MAX, PICTURE_MIN, TEXT_MAX, PLATE_GAP_S = 0.15, 0.50, 0.10, 30.0
TEXT_KINDS = {"callout", "takeaway"}
LIBRARY_KINDS = {"anatomy", "trainee", "pose", "prop", "hold"}
LIMB = {"forearm_flexors": ("forearm", "hand", "elbow"), "forearm_extensors": ("forearm", "hand", "elbow"), "biceps": ("upper_arm", "elbow", "shoulder"), "triceps": ("upper_arm", "elbow", "shoulder"),
        "calves": ("shin", "knee", "foot"), "shins": ("shin", "knee", "foot"), "quads": ("thigh", "knee", "hip"), "hamstrings": ("thigh", "knee", "hip"), "adductors": ("thigh", "hip")}      # muscle group -> the body parts its box must stay within

def _look(sc: dict) -> str:
    lk = sc.get("look") or sc["kind"]
    return sc["kind"] if lk == "stock" else lk

def _is_picture(sc: dict) -> bool:
    lk = _look(sc)
    return lk in ("flow", "illus", "pose", "anatomy", "3d", "clip3d", "prop", "hold", "sketch") or (lk == "trainee" and bool(sc.get("glows") or sc.get("morph")))

def _is_text(sc: dict) -> bool: return _look(sc) in TEXT_KINDS

_bad_groups = None

def bad_3d_groups() -> set:
    """Muscle groups whose anchor box reaches more than 15 cm past the bones of their limb (checked once from the shipped anchors; empty when there is no 3D model)."""
    global _bad_groups
    if _bad_groups is None:
        _bad_groups = set()
        try:
            from . import clip3d as C3
            A = json.loads(C3.ANCHORS.read_text(encoding="utf-8"))["anchors"] if C3.ANCHORS else {}
            for g, limb in LIMB.items():
                m = A.get(f"m_{g}_r") or A.get(f"m_{g}"); bones = [v for k, v in A.items() if k.startswith(limb) and "min" in v]
                if not m or not bones: continue
                lo = min(b["min"][2] for b in bones); hi = max(b["max"][2] for b in bones)
                if m["min"][2] < lo - 0.15 or m["max"][2] > hi + 0.15: _bad_groups.add(g)
        except Exception: pass
    return _bad_groups

def check(scenes: List[dict]) -> List[Dict]:
    """[{check, scenes: [no...], value}] for every rule the plan breaks; [] when it passes."""
    if not scenes: return []
    total = max(1e-6, scenes[-1]["end"] - scenes[0]["start"]); out: List[Dict] = []; dur = lambda sc: sc["end"] - sc["start"]
    if _is_text(scenes[0]) or (not _is_picture(scenes[0]) and _look(scenes[0]) not in ("tier", "equation")): out.append({"check": "opening_text", "scenes": [scenes[0]["no"]], "value": _look(scenes[0])})
    share: Dict[str, float] = {}; shows = lambda sc: sc["kind"] in LIBRARY_KINDS and sc.get("art") and _look(sc) not in ("flow", "3d") and sc["kind"] not in ("callout",)      # the scene really shows the picture
    for sc in scenes:
        if shows(sc): share[sc["art"]] = share.get(sc["art"], 0.0) + dur(sc)
    for art, s in share.items():      # only the scenes that show it are re-pictured: a card keeps the figure's art name but shows a card (1-minute render: the plan clipboard was replaced)
        if s / total > ONE_PICTURE_MAX: out.append({"check": "one_picture", "scenes": [sc["no"] for sc in scenes if sc.get("art") == art and shows(sc)], "value": round(s / total, 3), "art": art})
    pic = sum(dur(sc) for sc in scenes if _is_picture(sc)) / total
    if pic < PICTURE_MIN: out.append({"check": "pictures", "scenes": [sc["no"] for sc in scenes if not _is_picture(sc)], "value": round(pic, 3)})
    txt = sum(dur(sc) for sc in scenes if _is_text(sc)) / total
    if txt > TEXT_MAX: out.append({"check": "text_only", "scenes": [sc["no"] for sc in scenes if _is_text(sc)], "value": round(txt, 3)})
    seen: Dict[str, float] = {}; rep = []
    for sc in scenes:
        if _look(sc) == "anatomy" and sc.get("art"):
            if sc["start"] - seen.get(sc["art"], -1e9) < PLATE_GAP_S: rep.append(sc["no"])
            seen[sc["art"]] = sc["end"]
    if rep: out.append({"check": "plate_repeat", "scenes": rep, "value": len(rep)})
    bad = bad_3d_groups()
    if bad:
        from . import clip3d as C3
        b3 = [sc["no"] for sc in scenes if _look(sc) == "3d" and set(C3.groups_for(sc.get("muscle") or sc.get("text", ""))[0] or []) & bad]
        if b3: out.append({"check": "bad_3d", "scenes": b3, "value": sorted(bad)})
    return out

def _to_picture(sc: dict, why: str, flow: bool) -> bool:
    if sc["kind"] in ("tier", "equation"): return False
    if flow: sc["look"] = "flow"; sc["want_picture"] = True; sc["directed_look"] = True; sc.pop("want3d", None); sc["decisions"].append(f"quality gate: {why} -> its own Flow picture"); return True
    if sc.get("look") == "3d": sc["look"] = sc["kind"]; sc.pop("want3d", None); sc["decisions"].append(f"quality gate: {why} -> 3D clip dropped"); return True
    return False

def repair(scenes: List[dict], flow: bool) -> Dict:
    """Fixes the plan in place where it can, then checks again. Returns {before: [...], fixed: n, after: [...]} for the log. Never raises."""
    try:
        before = check(scenes); fixed = 0; by_no = {sc["no"]: sc for sc in scenes}
        for p in before:
            if p["check"] == "opening_text": fixed += _to_picture(scenes[0], "the opening was words", flow)
            elif p["check"] == "one_picture":      # keep the picture where it is first shown while it stays under the cap, give the rest their own
                total = max(1e-6, scenes[-1]["end"] - scenes[0]["start"]); kept = 0.0
                for no in p["scenes"]:
                    d = by_no[no]["end"] - by_no[no]["start"]
                    if kept + d <= ONE_PICTURE_MAX * total: kept += d; continue
                    fixed += _to_picture(by_no[no], f"{p['art']} filled {p['value']:.0%} of the video", flow)
            elif p["check"] in ("text_only", "plate_repeat", "bad_3d"):
                for no in p["scenes"]: fixed += _to_picture(by_no[no], p["check"].replace("_", " "), flow)
            elif p["check"] == "pictures" and flow:
                for no in p["scenes"]:
                    sc = by_no[no]
                    if _look(sc) in TEXT_KINDS or sc["kind"] in ("callout", "trainee"): fixed += _to_picture(sc, "too few pictures", flow)
        return {"before": before, "fixed": fixed, "after": check(scenes) if fixed else before}
    except Exception as ex: return {"before": [], "fixed": 0, "after": [], "error": f"{type(ex).__name__}: {ex}"}

def summary(res: Dict) -> str:
    fmt = lambda ps: ", ".join(f"{p['check']} ({p['value']})" for p in ps) or "none"
    return f"problems before: {fmt(res.get('before', []))}; fixed {res.get('fixed', 0)} scene(s); problems after: {fmt(res.get('after', []))}" + (f"; gate error {res['error']}" if res.get("error") else "")

THIN_MIN = 2      # developments a picture shot needs over its length (render final 3: 9 of 15 picture scenes were one headline and nothing else)

def picture_developments(sc: dict) -> int:
    """What happens on a picture shot after it opens: its headlines, chips and planned overlays (picture.plan_cues: labels, arrows, lines, badges, inset), glows, a stamp, a body change."""
    from . import cadence as C
    n = sum(1 for e in C.events([dict(sc, no=0)]) if e["meaningful"] and e["type"] == "secondary" and sc["start"] < e["t"] < sc["end"])
    try:
        from . import picture as PIC
        n += len(PIC.plan_cues(dict(sc)) or []) if hasattr(PIC, "plan_cues") else 0
    except Exception: pass
    return n

def thicken_pictures(scenes: List[dict]) -> int:
    """Run after the phrases are developed: a picture shot with fewer than THIN_MIN developments gets its sentence's key phrase as a chip at its own word (a phrase of the script,
    never a repeat of what is on screen). Plan-only, no render time. Returns how many shots were thickened."""
    from . import narrative as N
    n = 0
    for sc in scenes:
        if not (sc.get("look") == "flow" or sc["kind"] == "illus") or sc["end"] - sc["start"] < 2.0 or picture_developments(sc) >= THIN_MIN: continue
        key, pos = N.key_phrase(sc.get("text", ""), 3); key = N.phrase(key, sc.get("words") or []) if key else ""; shown = {pg.get("headline") for pg in sc.get("pages", [])} | {c["text"] for pg in sc.get("pages", []) for c in pg.get("chips", [])}
        if not key or key.upper() in shown: continue
        ws = sc.get("words") or []; i = pos if isinstance(pos, int) else len(ws) // 2      # key_phrase gives the word index
        at = float(ws[min(i, len(ws) - 1)]["t0"]) if ws else sc["start"] + 1.0
        at = min(max(at, sc["start"] + 0.6), sc["end"] - 0.8)
        if not sc.get("pages"): sc["pages"] = [{"at": sc["start"], "headline": "", "headline_at": sc["start"], "value": "", "chips": [], "kicker": ""}]
        sc["pages"][-1].setdefault("chips", []).append({"text": key.upper(), "at": at}); sc["decisions"].append(f"quality gate: a picture shot with one thing on it gets its key phrase '{key.upper()}'"); n += 1
    return n
