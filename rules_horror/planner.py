"""Rows + voice alignment -> beats. A beat is one shot: [start, end), a set, figures, marks, an optional rule card or glitch, caption phrases
and a camera move. Cuts follow the row timing; a row longer than MAX_BEAT_S is cut into equal parts with alternating camera moves, so something
changes every few seconds. A missing subject (no Flow picture yet) is a code-drawn tall figure with red eyes, reported in `notes`."""
from __future__ import annotations

import math
import statistics
import re

from .mood import moods_for
from typing import Any, Dict, List, Optional, Sequence

MAX_BEAT_S = 5.0
MIN_GAP_S = 0.35
CAPTION_WORDS = 5
SETS = ("bedroom", "hallway", "house_section", "yard", "door", "window", "classroom", "stairs", "hall_lit", "street", "cutaway", "cabin", "store", "bathroom", "kitchen", "hall_mirror")
FULL_SETS = ("prop", "crowd", "cinema")      # the whole frame is one object (a paper, a phone, a crowd grid)
PROPS = ("paper", "report", "note", "clock", "phone", "eye", "cctv", "door_feet", "ring_hand", "handprint", "phone_black", "floorboards", "hair_part")
ANIMALS = {"deer": "deer", "stag": "deer", "doe": "deer", "dog": "dog", "wolf": "dog", "coyote": "dog", "fox": "dog"}
APOSE = {"stand_side": "stand", "stand_front": "stand", "stand": "stand", "head_turned": "stand", "look_back": "stand", "stare": "stare", "close_up_face": "stare",
         "closeup_face": "stare", "walk": "walk", "head_low": "head_low", "raise_paw": "raise_paw", "paw": "raise_paw"}
CAM = {"wide": 0.015, "push_in": 0.07, "pull_out": -0.05, "static": 0.0}
# per set: figure size / ground (fractions of H), x of the person and of the subject
STAGE = {"bedroom": dict(size=0.30, ground=None, xp=0.29, xs=0.72), "hallway": dict(size=0.40, ground=0.80, xp=0.30, xs=0.70),
         "house_section": dict(size=0.20, ground=0.83, xp=0.33, xs=0.78), "yard": dict(size=0.34, ground=0.80, xp=0.60, xs=0.52),
         "door": dict(size=0.46, ground=0.88, xp=0.20, xs=0.78), "window": dict(size=0.36, ground=0.88, xp=0.18, xs=0.82),
         "classroom": dict(size=0.22, ground=0.69, xp=0.50, xs=0.80),
         "stairs": dict(size=0.34, ground=0.84, xp=0.82, xs=0.07, asize=0.5), "hall_lit": dict(size=0.42, ground=0.88, xp=0.24, xs=0.66),
         "street": dict(size=0.34, ground=0.80, xp=0.36, xs=0.74), "cabin": dict(size=0.42, ground=0.90, xp=0.50, xs=0.50, asize=0.5),
         "store": dict(size=0.40, ground=0.90, xp=0.34, xs=0.62, asize=0.5),
         "bathroom": dict(size=0.40, ground=0.84, xp=0.30, xs=0.50), "kitchen": dict(size=0.38, ground=0.84, xp=0.34, xs=0.66),
         "hall_mirror": dict(size=0.42, ground=0.88, xp=0.30, xs=0.62), "cutaway": dict(size=0.17, ground=0.83, xp=0.30, xs=0.955, asize=0.36)}
POSE_OF = {"stand_side": "stand", "stand_front": "stand", "head_turned": "look", "stare": "stand", "walk": "walk", "head_low": "look",
           "close_up_face": "stand", "closeup_face": "stand", "look_back": "look", "stand": "stand", "look": "look", "run": "run", "sit": "sit"}
FIGURE_POSES = ("stand", "look", "flinch", "sit", "sleep", "walk", "run")


def phrases(text: str, span, words: Sequence[Any], rng, ok: bool, size: int = CAPTION_WORDS) -> List[dict]:
    parts = str(text).split()
    if not parts:
        return []
    n = max(1, round(len(parts) / size))
    per_g = -(-len(parts) // n)
    groups = [parts[i:i + per_g] for i in range(0, len(parts), per_g)]
    W = []
    if ok and words and rng and rng[1] > rng[0]:
        for w in words:
            W.append((float(w["start"]), float(w["end"])) if isinstance(w, dict) else (float(w[1]), float(w[2])))
    out, k = [], 0
    for g in groups:
        if W:
            i0, i1 = min(rng[1], rng[0] + k), min(rng[1], rng[0] + k + len(g) - 1)
            a, b = W[i0][0], W[i1][1]
        else:
            per = (span[1] - span[0]) / len(parts)
            a, b = span[0] + k * per, span[0] + (k + len(g)) * per
        out.append({"start": round(a, 3), "end": round(max(b, a + 0.3), 3), "text": " ".join(g)})
        k += len(g)
    return out


def CHARACTER_LOOK(name: str):
    """A creature that is a person, not an animal: a grinning one, or a blank mannequin; anything else stays the tall dark figure with red eyes."""
    n = str(name or "").lower()
    if re.search(r"hazmat|suit|inspector|mask|lens", n):
        return "hazmat"
    if re.search(r"smil|grin|laugh|audience|usher|crowd", n):
        return "grin"
    if re.search(r"mannequin|doll|dummy|statue", n):
        return "mannequin"
    return None


def CHARACTER_OUTFIT(name: str):
    n = str(name or "").lower()
    return "attendant" if re.search(r"attendant|stewardess|flight crew|cabin crew", n) else ("usher" if "usher" in n else None)


def _signature(b: Dict[str, Any]):
    return (b["set"], tuple(sorted(bool(f.get("subject")) for f in b["figures"])), tuple(sorted(f.get("animal") or "person" for f in b["figures"])),
            tuple((L["type"], L.get("kind")) for L in b.get("layers", [])), bool(b["card"]))


def vary(beats: List[Dict[str, Any]]) -> int:
    """The same picture on screen again and again is the one thing the references never do. Where two or more beats in a row show the same set and the
    same figures, the repeats get a new angle: a zoom into the subject, then a zoom into the person, then a wide reverse. Returns how many were changed."""
    run, changed, prev = 0, 0, None
    for b in beats:
        sig = _signature(b)
        run = run + 1 if (sig == prev and not b["card"]) else 0
        prev = sig
        if run == 0 or b["card"] or b["set"] == "none" or b["cam"].get("focus"):
            continue
        subj = next((f for f in b["figures"] if f.get("subject")), None)
        pers = next((f for f in b["figures"] if not f.get("subject")), None)
        pick = [subj, pers, subj][(run - 1) % 3] or subj or pers
        if pick is None:
            continue
        top = (pick.get("ground") or 0.8) - pick["size"] * (0.55 if pick.get("animal") else 0.7)
        b["cam"].update(focus=[round(pick["x"], 3), round(max(0.2, top), 3)], zoom=1.55 if (run % 3) != 0 else 1.0, push=-0.05 if run % 2 else 0.08)
        changed += 1
    return changed


STAB_S = 0.35
REACH = {"deer": (0.30, 0.45), "dog": (0.36, 0.58)}       # how far an animal reaches behind / in front of its x, in units of its size


def separate(figs: List[Dict[str, Any]], aspect: float = 9 / 16) -> None:
    """The subject never covers the person: when an animal's body overlaps a person standing in the same shot, the person steps clear
    (to the side the animal faces, else behind it), and the animal moves only when neither side has room."""
    animal = next((f for f in figs if f.get("animal")), None)
    if not animal:
        return
    back, front = REACH.get(animal["animal"], (0.35, 0.5))
    face = -1 if animal.get("facing") == "left" else 1
    sz = animal["size"] * aspect
    lo, hi = sorted((animal["x"] - face * back * sz, animal["x"] + face * front * sz))
    for p in figs:
        if p is animal or p.get("animal") or p.get("mode") == "full" or p.get("size", 0) >= 1.0:
            continue
        half, gap = max(0.03, p["size"] * 0.12), 0.03
        if p["x"] + half + gap <= lo or p["x"] - half - gap >= hi:
            continue
        ahead = hi + half + gap if face > 0 else lo - half - gap
        behind = lo - half - gap if face > 0 else hi + half + gap
        new = next((x for x in (ahead, behind) if 0.06 <= x <= 0.94), None)
        if new is None:                                    # no room either side: put the person at the nearer edge and slide the animal away
            new = 0.08 if p["x"] < animal["x"] else 0.92
            shift = (lo - (new + half + gap)) if new < animal["x"] else ((new - half - gap) - hi)
            animal["x"] = round(animal["x"] + shift, 3)
            if animal.get("walk_to") is not None:
                animal["walk_to"] = round(animal["walk_to"] + shift, 3)
        d = new - p["x"]
        p["x"] = round(new, 3)
        if p.get("walk_to") is not None:
            p["walk_to"] = round(min(0.96, max(0.04, p["walk_to"] + d)), 3)


def add_stabs(beats: List[Dict[str, Any]], per_min: float, duration: float) -> int:
    """Quick cuts like the references (0.3-0.45 s): the first STAB_S of a shot becomes its own hard punch-in on the same picture, then the shot
    cuts back to its normal framing. Spread evenly over the film at the profile's measured rate; rule cards are never cut."""
    want = int(round(per_min * duration / 60.0))
    cand = [i for i, b in enumerate(beats) if not b["card"] and b["end"] - b["start"] >= 1.2]
    if want <= 0 or not cand:
        return 0
    step = len(cand) / min(want, len(cand))
    picks = sorted({cand[int(k * step)] for k in range(min(want, len(cand)))}, reverse=True)
    for i in picks:
        b = beats[i]
        cut = round(b["start"] + STAB_S, 3)
        cam = dict(b["cam"], start=b["start"], end=cut, push=0.0, zoom=round((b["cam"].get("zoom") or 1.0) * 1.35, 3))
        head = dict(b, end=cut, cam=cam, stab=True,
                    captions=[dict(c, end=min(c["end"], cut)) for c in b["captions"] if c["start"] < cut])
        tail = dict(b, start=cut, cam=dict(b["cam"], start=cut),
                    captions=[dict(c, start=max(c["start"], cut)) for c in b["captions"] if c["end"] > cut])
        beats[i:i + 1] = [head, tail]
    return len(picks)


def plan(data: Dict[str, Any], align: Dict[str, Any], words: Sequence[Any], duration: float, pictures: Optional[Dict[str, str]] = None,
         profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """profile: one of rules_horror.profiles (its measured longest shot and quick-cut rate); None keeps the old fixed pacing."""
    pictures = pictures or {}
    max_beat = float((profile or {}).get("max_beat") or MAX_BEAT_S)
    rows, notes = data["rows"], list(data.get("notes", []))
    spans, ranges, ok = align["spans"], align["ranges"], align["ok"]
    if not ok:
        notes.append("the voice-over words did not follow the script lines; rows were spread by word count")
    n = len(rows)
    starts = [max(0.0, float(spans[i][0])) for i in range(n)]
    if starts:
        starts[0] = 0.0
    for i in range(1, n):                      # strictly forward, never two rows on the same instant
        starts[i] = max(starts[i], starts[i - 1] + MIN_GAP_S)
    ends = [min(float(duration), starts[i + 1]) if i + 1 < n else float(duration) for i in range(n)]
    last = max([i for i in range(n) if starts[i] < float(duration) - 0.3] or [0]) if n else 0     # a cut-short film keeps only the rows it reaches
    if n:
        ends[last] = float(duration)
    if n and ends[-1] <= starts[-1] + 0.5:
        ends[-1] = starts[-1] + 0.5
    row_moods = moods_for(rows)
    st = {"set": "yard", "figure": None, "subject": None}
    beats: List[Dict[str, Any]] = []
    fallback_subjects = set()
    used_pictures = set()
    fallback_closeups = 0
    for i, r in enumerate(rows):
        if n and i > last:
            break
        a, b = starts[i], min(float(duration), ends[i])
        if b <= a:
            continue
        acts = [a for a in r["action"].split("+") if a]
        card = r["set"] == "card" or "rule_card" in acts
        prop = next((a[5:] for a in acts if a.startswith("prop_")), "")
        if prop and prop not in PROPS:
            notes.append(f"row {i + 1}: prop '{prop}' is not known ({', '.join(PROPS)}); skipped")
            prop = ""
        if r["set"] == "prop" and not prop:
            notes.append(f"row {i + 1}: set 'prop' needs an action prop_<kind> ({', '.join(PROPS)}); the previous set kept")
        full = "crowd" if (r["set"] in ("crowd", "cinema") or any(a.startswith("crowd") for a in acts)) else (prop if prop and prop != "cctv" else "")
        if r["set"] and r["set"] not in ("card", "closeup") + FULL_SETS:
            if r["set"] not in SETS:
                notes.append(f"row {i + 1}: set '{r['set']}' is not known; '{st['set']}' kept")
            elif r["set"] != st["set"]:
                st = {"set": r["set"], "figure": None, "subject": None}     # a new set starts empty: nothing is carried into a new room
        closeup = r["set"] == "closeup"
        fa = next((a for a in acts if a.startswith("figure_")), "")
        if fa:
            pose = fa[len("figure_"):]
            if pose in ("off", "none", "clear"):
                st["figure"] = None
            elif pose in FIGURE_POSES:
                st["figure"] = {"pose": pose}
            else:
                notes.append(f"row {i + 1}: figure pose '{pose}' is not known; 'stand' used")
                st["figure"] = {"pose": "stand"}
        if r["subject"] and not closeup:
            pose = POSE_OF.get(r["pose"], None) or (st["subject"] or {}).get("pose") or "stand"
            key = f"{r['subject']}:{r['pose'] or 'stand_side'}"
            animal = next((v for k, v in ANIMALS.items() if k in r["subject"]), None)
            st["subject"] = {"name": r["subject"], "pose": pose, "stare": r["pose"] in ("stare", "close_up_face", "closeup_face"), "key": key, "animal": animal,
                             "apose": APOSE.get(r["pose"]) or (st["subject"] or {}).get("apose") or "stand"}
            if key in pictures:
                used_pictures.add(key)
            elif not animal and not CHARACTER_LOOK(r["subject"]):
                fallback_subjects.add(r["subject"])
        tag = r["tag"].upper() if r["tag"] else ""
        stage = STAGE[st["set"]]
        figs: List[Dict[str, Any]] = []
        marks: List[Dict[str, Any]] = []
        if closeup:
            ck = f"closeup:{i}"
            if ck in pictures:
                figs.append({"picture": pictures[ck], "mode": "full", "subject": True})
                used_pictures.add(ck)
            elif (lambda nm: next((v for k, v in ANIMALS.items() if k in nm), None))(r["subject"] or (st["subject"] or {}).get("name", "")):       # an animal close-up: the code-drawn head, filled to the frame
                nm = r["subject"] or (st["subject"] or {}).get("name", "")
                figs.append({"animal": next(v for k, v in ANIMALS.items() if k in nm), "pose": "stare", "x": 0.4, "size": 1.0, "ground": 1.0, "facing": "right", "subject": True,
                             "cam_focus": [round(0.4 + 0.38 * 0.5625, 3), 0.17], "cam_zoom": 2.3})
            else:
                fallback_closeups += 1
                look = CHARACTER_LOOK(r["subject"] or (st["subject"] or {}).get("name", ""))
                big = {"pose": "stand", "x": 0.5, "size": 3.0, "ground": 3.0, "facing": "right", "subject": True}
                figs.append({**big, "look": look} if look else {**big, "eyes": "red", "stare": True, "hollow": True})
        elif full or card:
            pass
        elif not card:
            if st["figure"]:
                pose = st["figure"]["pose"]
                f = {"pose": pose, "x": stage["xp"] if st["subject"] else min(0.5, stage["xp"] + 0.1), "size": stage["size"], "facing": "right"}
                if st["set"] == "bedroom" and pose == "sleep":
                    f.update(size=0.30, ground=0.60)
                elif st["set"] == "cutaway" and pose in ("sleep", "sit"):
                    f.update(x=0.24, ground=0.50, size=0.17)
                elif stage["ground"] is not None:
                    f["ground"] = stage["ground"]
                if st["set"] == "classroom" and pose != "sit":
                    f["ground"] = 0.80
                if pose in ("walk", "run"):
                    f["walk_to"] = round(f["x"] + 0.14, 3)
                if tag and tag not in ("PREY",):
                    f["tag"] = tag
                figs.append(f)
            if st["subject"]:
                s = st["subject"]
                if s.get("animal") and s.get("key") not in pictures:
                    f = {"animal": s["animal"], "pose": s["apose"], "x": stage["xs"] if st["figure"] else min(0.7, stage["xs"]), "size": round(min(0.64, stage.get("asize") or stage["size"] * 1.75), 3),
                         "facing": "left" if (not st["figure"] or stage["xs"] > stage["xp"]) else "right", "subject": True,
                         "ground": stage["ground"] if stage["ground"] is not None else 0.80}
                    if "red_eyes" in acts:
                        f["eye"] = "red"
                    if s["apose"] == "walk":
                        f["walk_to"] = round(f["x"] + (-0.12 if f["facing"] == "left" else 0.12), 3)
                    if tag == "PREY" or (tag and not st["figure"]):
                        f["tag"] = tag
                    figs.append(f)
                else:
                    look = CHARACTER_LOOK(s["name"])
                    f = {"pose": s["pose"], "x": stage["xs"] if st["figure"] else min(0.7, stage["xs"]), "size": round(stage["size"] * 1.28, 3), "facing": "left",
                         "eyes": "red", "subject": True, "tag_color": "red", "hollow": True}
                    outfit = CHARACTER_OUTFIT(s["name"])
                    if look or outfit:
                        f.update(hollow=False)
                        f.pop("eyes")
                        if look:
                            f["look"] = look
                        if outfit:
                            f["outfit"] = outfit
                    if s.get("stare"):
                        f["stare"] = True
                    if stage["ground"] is not None:
                        f["ground"] = stage["ground"]
                    elif st["set"] == "bedroom":
                        f["ground"] = 0.80
                    if tag == "PREY" or (tag and not st["figure"]):
                        f["tag"] = tag
                    if s.get("key") in pictures:
                        f["picture"] = pictures[s["key"]]
                        f["mode"] = "subject"
                    figs.append(f)
        separate(figs)
        layers: List[Dict[str, Any]] = []
        used_value = False
        if "sight_line" in acts and not card and not full:
            subj = next((f for f in figs if f.get("subject")), None)
            pers = next((f for f in figs if not f.get("subject")), None)
            if subj:
                gy = subj.get("ground") or 0.8
                y = round(gy - subj["size"] * 0.85, 3)
                tx = pers["x"] if pers else 0.5
                ty = round((pers.get("ground") or 0.8) - (pers["size"] * 0.85 if pers else 0.3), 3) if pers else y
                marks.append({"kind": "sight", "from": [round(subj["x"] - 0.04, 3), y], "to": [round(tx + 0.04, 3), ty]})
        if "countdown" in acts and not card:
            marks.append({"kind": "ring", "x": 0.88, "y": 0.18, "seconds": float(r["value"] or 3) if str(r["value"]).replace(".", "").isdigit() else 3.0}); used_value = True
        if "cross" in acts and not card:
            marks.append({"kind": "cross", "x": 0.5, "y": 0.25})
        if "bubble" in acts and r["value"] and not card and not full:
            who = next((f for f in figs if not f.get("subject")), None) or (figs[0] if figs else None)
            if who:
                top = (who.get("ground") or 0.8) - who["size"] * (1.0 if who.get("animal") else 1.28)
                marks.append({"kind": "bubble", "text": r["value"], "x": round(min(0.85, max(0.15, who["x"])), 3), "y": round(max(0.1, top - 0.1), 3),
                              "to": [round(who["x"], 3), round(max(0.2, top - 0.02), 3)]})
            else:
                marks.append({"kind": "bubble", "text": r["value"], "x": 0.5, "y": 0.25, "to": [0.5, 0.4]})
            used_value = True
        if "banner" in acts and r["value"] and not card:
            marks.append({"kind": "banner", "text": r["value"], "x": 0.5, "y": 0.12}); used_value = True
        if r["value"] and not card and not used_value and not full and not prop and not marks:
            marks.append({"kind": "tag", "text": r["value"], "x": 0.5, "y": 0.1, "color": "red"})
        if any(x.startswith("mirror") or x == "water" for x in acts) and not card and not full:
            if st["set"] in ("bathroom", "hall_mirror"):
                fpose = (st["figure"] or {}).get("pose", "stand")
                lay = {"type": "rh_mirror", "set": st["set"], "pose": fpose if fpose in FIGURE_POSES else "stand", "lead": 0.5 if "mirror_early" in acts else 0.0}
                if "mirror_smile" in acts:
                    lay["smile_at"] = round(a + min(0.6, (b - a) * 0.2), 3)
                if "mirror_press" in acts:
                    lay["press_at"] = round(a + (b - a) * 0.5, 3)
                if "water" in acts:
                    lay["water"] = True
                layers.append(lay)
            else:
                notes.append(f"row {i + 1}: mirror actions need the set bathroom or hall_mirror (set is '{st['set']}'); skipped")
        # whole-frame objects: a prop or a crowd grid, with the layer dicts the compiler adds as they are
        if prop and not card:
            lay: Dict[str, Any] = {"type": "rh_prop", "kind": prop}
            if prop in ("paper", "report") and r["prompt"]:
                lay["lines"] = [x.strip() for x in r["prompt"].split("|") if x.strip()]
            if prop in ("paper", "report", "note") and r["value"]:
                lay["title" if prop != "note" else "text"] = r["value"]
            if prop == "phone" and r["prompt"]:
                lay["messages"] = [[("me" if x.lower().startswith("me:") else "them"), x.split(":", 1)[-1].strip()] for x in r["prompt"].split("|") if x.strip()]
            if prop == "clock" and re.match(r"^\d{1,2}[:.]\d{2}$", r["value"] or ""):
                h, m = re.split(r"[:.]", r["value"]); lay["hour"], lay["minute"] = int(h) % 12, int(m)
            val = str(r["value"] or "").lower().replace(" ", "")
            if prop in ("ring_hand", "hair_part"):                      # value "left>right": it starts on the left and swaps to the right at the middle of the shot
                first, _, second = val.partition(">")
                lay["side"] = first if first in ("left", "right") else "left"
                if second in ("left", "right") and second != lay["side"]:
                    lay["flip_at"] = round(a + (b - a) * 0.5, 3)
            if prop == "floorboards":                                   # value "11" or "11>12": count the boards; ">12" adds a twelfth that should not exist
                m = re.match(r"^(\d+)(>(\d+))?$", val)
                if m:
                    lay["count"] = int(m.group(1))
                    lay["extra"] = bool(m.group(3) and int(m.group(3)) > int(m.group(1)))
            if prop == "phone_black":
                lay["text"] = r["value"]
                if "mirror_smile" in acts:
                    lay["smile_at"] = round(a + 0.6, 3)
            if prop == "cctv" and r["value"]:
                lay["label"] = r["value"].upper()
            if prop == "eye" and "red_eyes" in acts:
                lay["color"] = "red"
            layers.append(lay)
        if full == "crowd" and r["subject"] and not card and not ANIMALS.get(r["subject"]):
            look = CHARACTER_LOOK(r["subject"])
            figs.append({"pose": "stand", "x": 0.9, "size": 0.7, "ground": 1.0, "facing": "left", "subject": True, **({"look": look} if look else {"eyes": "red", "hollow": True})})
        if full == "crowd" and not card:
            cinema = r["set"] == "cinema" or "cinema" in "+".join(acts)
            lay = {"type": "rh_crowd", "kind": "cinema" if cinema else "classroom", "rows": 4, "cols": 9, "mark": [1 + i % 2, 2 + (i * 5) % 5]}
            lab = r["value"] or (tag if tag not in ("PREY",) else "")
            if lab:
                lay["label"] = lab
            if "red_eyes" in acts:
                lay["eyes_red"] = True
            if any(a == "crowd_turn" for a in acts):
                lay["turn"] = round(a + (b - a) * 0.4, 3)
            layers.append(lay)
        beat_base = {"row": i, "mood": row_moods[i], "section": r["section"], "set": ("none" if (closeup or (full and not card)) else st["set"]), "figures": figs, "marks": marks, "card": None, "layers": layers,
                     "glitch": "glitch" in acts, "flow_prompt": r["prompt"], "shot": r["shot"]}
        if card:
            num = r["value"] if str(r["value"]).isdigit() else None
            beat_base.update(set="card", card={"number": int(num) if num else None, "text": r["line"]})
        # equal parts when the row runs long; alternating camera so each part reads as a new angle
        k = max(1, math.ceil((b - a) / max_beat))
        cap = [] if card else phrases(r["line"], spans[i], words, ranges[i], ok)
        for j in range(k):
            s0, s1 = a + (b - a) * j / k, a + (b - a) * (j + 1) / k
            shot = r["shot"] if j % 2 == 0 else ("pull_out" if r["shot"] in ("push_in", "wide") else "push_in")
            cam = {"push": CAM[shot], "start": round(s0, 3), "end": round(s1, 3)}
            fz = next((f for f in figs if f.get("cam_focus")), None)
            if fz:
                cam.update(focus=fz["cam_focus"], zoom=fz["cam_zoom"], push=0.12 if j % 2 == 0 else -0.08)
            beat = dict(beat_base, start=round(s0, 3), end=round(s1, 3), cam=cam, shot=shot)
            beat["captions"] = [dict(c, start=max(c["start"], s0), end=min(c["end"], s1)) for c in cap if c["end"] > s0 and c["start"] < s1]
            beats.append(beat)
    if fallback_subjects:
        notes.append(f"subject picture(s) not available yet ({', '.join(sorted(fallback_subjects))}): drawn as a tall figure with red eyes")
    if fallback_closeups:
        notes.append(f"{fallback_closeups} close-up picture(s) not available: a big red-eyed head is drawn instead")
    if used_pictures:
        notes.append(f"{len(used_pictures)} Flow picture(s) used")
    vary(beats)
    stabs = add_stabs(beats, float((profile or {}).get("stabs") or 0.0), float(duration))
    lens = [bt["end"] - bt["start"] for bt in beats]
    stats = {"moods": {m: sum(1 for b in beats if b.get("mood") == m) for m in sorted({b.get("mood") for b in beats if b.get("mood")})}, "shots": len(beats), "median_shot_s": round(statistics.median(lens), 2) if lens else 0.0, "longest_shot_s": round(max(lens), 2) if lens else 0.0,
             "cuts_per_min": round(60.0 * len(beats) / max(1.0, float(duration)), 1), "punch_ins": stabs}
    return {"beats": beats, "notes": notes, "stats": stats, "duration": float(duration), "max_beat": max_beat}
