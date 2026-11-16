"""Toon Tales plan checker: rules every story must pass before anything renders, with auto-repair.

Run: python3 -m toontales.plan.check <plan.json> [--fix]      (--fix writes the repaired plan back)
Library: report = check(plan, fix=True) -> {"ok", "plan", "issues": [{level, rule, shot, msg}]}
  level: error (must be fixed by the writer), warn (allowed but weak), fixed (auto-repaired)

Rules (ids are stable, tests use them):
  text          every shot has a sentence and a speaker
  cast_known    speakers and cast exist in cast.json (the series cast) / plan cast list
  set_known     set kit (or plan place) exists and marks/spots/props are in that kit
  places        a story moves through places: at least MIN_PLACES, never more than PLACE_RUN shots in one
  show_line     every narrator line is shown, not just gestured: a prop, overlay, a move/grab/throw/fall,
                or a new place (talking gestures alone are not a picture of what is said)
  library       actions, eyes and mouths exist in the library (close typos are repaired)
  props         prop types are known; text props carry text; overlays/sfx/camera/move names are known
  speaker_seen  a speaking character is in the shot (or the shot says offscreen)
  one_mark      two characters never share a mark in one shot
  shot_len      every shot lasts SHOT_MIN..SHOT_MAX s (long shots split at a natural break, short ones merge)
  camera_repeat no two shots in a row use the same camera
  visual        every shot shows something happen (an action, prop or overlay)
  still         nothing stands still longer than STILL_MAX s
  act_time      actions start inside their shot
  dissolve      dissolves only on time jumps
  hook_first    the first shot is the hook and shows a strong image
  payoff_last   the story ends on its twist/payoff
  beat_order    beats follow the story formula order
  length        whole story is STORY_MIN..STORY_MAX s
  topic_repeat  the topic has not been made before
  hook_title    the plan has a short hook_title (big card over the first shot)
  hook_question the hook asks a question the story answers (a hook line ends with "?")
  loop          the last shot is in the first shot's place, so the Short loops back into its opening
  break         one freeze ("WAIT..."-style pattern break) lands 35-65% into the story
  twist_hold    the shot before the twist freezes (a held beat, music stops) - auto-added
  rhythm        the con/escalate stretch has quick cuts (at least 2 shots under FAST s)
  (a shot with "screen": {...} is a trading-platform chart drawn by edit/chart.py: no set kit or cast needed)
  prop_seen     a held prop with words is not lost in a wide shot (camera tightened to medium)
"""
import copy
import difflib
import json
import re
import sys
from pathlib import Path

from toontales.plan import schema as S

TT = S.TT
sys.path[:0] = [str(TT / "library")]
import actions as A  # noqa: E402
from toontales.diorama.actor_acts import ACTS as ACTOR_ACTS  # noqa: E402

STRONG = {"jump", "fall", "bonk", "throw", "run", "celebrate", "shock", "cheer", "point", "point_you",
          "money", "laugh", "pick_up", "tremble", "cower", "facepalm", "dizzy"}
QUIET = {"idle"}
CAM_NEXT = {"wide": "medium", "medium": "close", "two_shot": "close", "close": "medium", "insert": "medium",
            "low": "medium", "high": "medium", "pov": "medium", "over_shoulder": "close"}
GESTURES = {"explain", "nod", "shake_head", "laugh", "look_around", "scratch_head", "sigh", "idle", "hips",
            "cross", "think", "point", "point_you", "present", "shrug", "wave", "scratch", "nod"}
MIN_PLACES, PLACE_RUN = 4, 5
FAST = 1.6
SPLIT_WORDS = (" and ", " but ", " so ", " then ", " because ", " until ", " while ", " which ")


def _faces():
    sys.path.insert(0, str(TT / "cast"))
    import faces
    return set(faces.EYES), set(faces.MOUTHS)


class _Report:
    def __init__(self):
        self.issues = []

    def add(self, level, rule, shot, msg):
        self.issues.append({"level": level, "rule": rule, "shot": shot, "msg": msg})


def _sid(shot, i):
    return shot.get("id") or f"s{i + 1:02d}"


def _renumber(shots):
    for i, s in enumerate(shots):
        s["id"] = f"s{i + 1:02d}"


def _fix_name(name, known):
    m = difflib.get_close_matches(name, list(known), n=1, cutoff=0.75)
    return m[0] if m else None


def _free_mark(kit, used):
    for m in kit["marks"]:
        if m not in used and not m.startswith("enter") and m != "deep":
            return m
    return None


def _split_point(text):
    """Index to split a long sentence: the natural break nearest the middle."""
    mid = len(text) / 2
    cands = [m.end() for m in re.finditer(r"[,;:]\s+", text)]
    for w in SPLIT_WORDS:
        cands += [m.start() + 1 for m in re.finditer(re.escape(w), text)]
    cands = [c for c in cands if 0.25 * len(text) < c < 0.75 * len(text)]
    if cands:
        return min(cands, key=lambda c: abs(c - mid))
    # no comma/conjunction: break before a preposition so each half stays a phrase
    preps = [m.start() + 1 for m in re.finditer(r"\s(?:on|in|at|with|for|to|from|into|onto|over|under|after|before|by)\s", text)]
    preps = [c for c in preps if 0.25 * len(text) < c < 0.8 * len(text)]
    if preps:
        return min(preps, key=lambda c: abs(c - mid))
    ws = [m.start() for m in re.finditer(r"\s+", text)]
    return min(ws, key=lambda c: abs(c - mid)) if ws else None


def _acts(shot):
    return [(c["id"], a) for c in shot.get("cast", []) for a in c.get("acts", [])]


def _still_gap(acts, d):
    """Longest stretch of the shot in which no action is moving (a held pose only moves while it blends in)."""
    spans = []
    for _, a in acts:
        name = a.get("do")
        if name not in A.ACTIONS or name in QUIET:
            continue
        t0 = float(a.get("at", 0))
        moving = 0.35 if name in A.HOLDS else float(a.get("dur", A.ACTIONS[name][1]))
        spans.append((t0, t0 + moving))
    spans.sort()
    t, gap = 0.0, 0.0
    for a, b in spans:
        gap = max(gap, a - t)
        t = max(t, b)
    return max(gap, d - t)


def check(plan, fix=True, cast_file=S.CAST_FILE, kits_file=S.KITS_FILE, stories=S.STORIES):
    plan = copy.deepcopy(plan)
    rep = _Report()
    if cast_file == S.CAST_FILE:
        cast_file = S.cast_file_for(plan)
    cast, narrator = S.load_cast(cast_file)
    kits = S.load_kits(kits_file)
    eyes_ok, mouths_ok = _faces()
    shots = plan.setdefault("shots", [])
    if not shots:
        rep.add("error", "text", None, "plan has no shots")
        return _out(plan, rep)
    plan_cast = set(plan.get("cast") or cast)
    for i, s in enumerate(shots):
        s.setdefault("id", f"s{i + 1:02d}")

    # ---- per-shot content rules
    for i, s in enumerate(shots):
        sid = _sid(s, i)
        if not str(s.get("text", "")).strip():
            rep.add("error", "text", sid, "shot has no sentence")
        sp = s.setdefault("speaker", "narrator")
        if sp != "narrator" and sp not in cast:
            rep.add("error", "cast_known", sid, f"speaker '{sp}' is not in the cast")
        kit = S.kit_for(plan, s.get("set"), kits)
        if kit is None and not s.get("screen"):
            known = [k for k, v in kits.items() if v.get("kind") != "backdrop"] + list(plan.get("places") or {})
            rep.add("error", "set_known", sid, f"set '{s.get('set')}' is not a set kit or place ({', '.join(known)})")
        cam = s.setdefault("camera", "medium")
        if cam not in S.CAMERAS:
            rep.add("error", "props", sid, f"camera '{cam}' unknown")
        if s.setdefault("move", "drift") not in S.MOVES:
            rep.add("error", "props", sid, f"move '{s['move']}' unknown")
        for c in s.setdefault("cast", []):
            if c.get("id") not in cast or c["id"] not in plan_cast:
                rep.add("error", "cast_known", sid, f"cast member '{c.get('id')}' is not in the story cast")
            if kit and c.get("mark") not in kit["marks"]:
                rep.add("error", "set_known", sid, f"mark '{c.get('mark')}' is not in set '{s.get('set')}'")
            lib = ACTOR_ACTS if (cast.get(c.get("id")) or {}).get("actor") else A.ACTIONS  # realistic actor acts
            for a in c.setdefault("acts", []):
                if a.get("do") not in lib:
                    new = _fix_name(str(a.get("do")), lib)
                    if fix and new:
                        rep.add("fixed", "library", sid, f"action '{a.get('do')}' -> '{new}'")
                        a["do"] = new
                    else:
                        rep.add("error", "library", sid, f"action '{a.get('do')}' is not in the library")
            for key, ok in (("eyes", eyes_ok), ("mouth", mouths_ok)):
                v = c.get(key)
                if v and v not in ok:
                    new = _fix_name(v, ok)
                    if fix and new:
                        rep.add("fixed", "library", sid, f"{key} '{v}' -> '{new}'")
                        c[key] = new
                    else:
                        rep.add("error", "library", sid, f"{key} '{v}' is not a face picture")
        for p in s.setdefault("props", []):
            t = p.get("type")
            if t not in S.PROP_TYPES:
                rep.add("error", "props", sid, f"prop type '{t}' unknown")
            elif S.PROP_TYPES[t] and not str(p.get("text", "")).strip():
                rep.add("error", "props", sid, f"{t} prop needs its text")
            for hk in ("held_by", "picked_by"):
                if p.get(hk) and p[hk] not in [c.get("id") for c in s["cast"]]:
                    rep.add("error", "props", sid, f"{t} is {hk} '{p[hk]}' who is not in the shot")
            spot = p.get("spot")
            if kit and spot and spot not in kit["spots"] and spot not in kit["marks"] and spot not in kit["props"]:
                rep.add("error", "set_known", sid, f"spot '{spot}' is not in set '{s.get('set')}'")
        ov = s.get("overlay")
        if ov and ov.get("type") not in S.OVERLAYS:
            rep.add("error", "props", sid, f"overlay '{ov.get('type')}' unknown")
        for fx in s.setdefault("sfx", []):
            if fx.get("name") not in S.SFX:
                rep.add("warn", "props", sid, f"sound '{fx.get('name')}' is not in the sound map")
        if s.setdefault("transition", "cut") not in S.TRANSITIONS:
            rep.add("error", "props", sid, f"transition '{s['transition']}' unknown")

        # staging: speaker on screen, one character per mark
        here = [c["id"] for c in s["cast"]]
        if sp != "narrator" and sp in cast and sp not in here and not s.get("offscreen"):
            m = _free_mark(kit, {c.get("mark") for c in s["cast"]}) if kit else None
            if fix and m:
                s["cast"].append({"id": sp, "mark": m, "acts": [{"do": "explain", "at": 0.0}]})
                rep.add("fixed", "speaker_seen", sid, f"{sp} speaks, added on mark {m}")
            else:
                rep.add("error", "speaker_seen", sid, f"{sp} speaks but is not in the shot")
        used = {}
        for c in s["cast"]:
            m = c.get("mark")
            if m in used:
                new = _free_mark(kit, set(used) | {m}) if kit else None
                if fix and new:
                    rep.add("fixed", "one_mark", sid, f"{c['id']} moved from mark {m} to {new} ({used[m]} is there)")
                    c["mark"] = new
                    m = new
                else:
                    rep.add("error", "one_mark", sid, f"{c['id']} and {used[m]} share mark {m}")
            used[m] = c["id"]

        if s["transition"] == "dissolve" and not s.get("time_jump"):
            if fix:
                s["transition"] = "cut"
                rep.add("fixed", "dissolve", sid, "dissolve without a time jump -> cut")
            else:
                rep.add("warn", "dissolve", sid, "dissolve without a time jump")

    # ---- shot length: split long, merge short
    out = []
    i = 0
    shot_max = S.channel(plan).get("shot_max", S.SHOT_MAX)  # a channel may hold shots longer (slow build shots)
    while i < len(shots):
        s = shots[i]
        d = S.shot_dur(s, cast, narrator)
        if d > shot_max and not s.get("dur") and s.get("moves"):  # timed moves would replay in both halves
            rep.add("error", "shot_len", _sid(s, i), f"{d:.1f}s is longer than {shot_max}s; it has timed moves, "
                    f"so split the line by hand")
        elif d > shot_max and not s.get("dur"):
            cut = _split_point(s["text"])
            if fix and cut:
                a, b = copy.deepcopy(s), copy.deepcopy(s)
                a["text"], b["text"] = s["text"][:cut].strip(), s["text"][cut:].strip()
                b["camera"] = CAM_NEXT.get(s["camera"], "medium")
                b["props"] = [p for p in s.get("props", [])]
                for c in b["cast"]:
                    c["acts"] = [{"do": "nod" if c["id"] != s["speaker"] else "explain", "at": 0.1}]
                b.pop("overlay", None)
                b["transition"] = "cut"
                rep.add("fixed", "shot_len", _sid(s, i), f"{d:.1f}s is too long, split in two")
                shots[i:i + 1] = [a, b]
                continue
            rep.add("error", "shot_len", _sid(s, i), f"{d:.1f}s is longer than {shot_max}s")
        elif d > shot_max:
            rep.add("error", "shot_len", _sid(s, i), f"{d:.1f}s (real voice) is longer than {shot_max}s; split the line")
        if d < S.SHOT_MIN and i + 1 < len(shots):
            n = shots[i + 1]
            own = s.get("hud") or s.get("callout")  # a quick cut with its own meter/label: merging would lose it
            if fix and n.get("speaker") == s.get("speaker") and n.get("set") == s.get("set") and not s.get("dur") \
                    and not own:
                n["text"] = s["text"].rstrip() + " " + n["text"].lstrip()
                if s.get("beat") and not n.get("beat"):
                    n["beat"] = s["beat"]
                rep.add("fixed", "shot_len", _sid(s, i), f"{d:.1f}s is too short, merged into the next shot")
                i += 1
                continue
            rep.add("warn", "shot_len", _sid(s, i), f"{d:.1f}s is shorter than {S.SHOT_MIN}s")
        out.append(s)
        i += 1
    shots[:] = out
    if fix:
        _renumber(shots)

    # ---- rhythm and life
    total = 0.0
    for i, s in enumerate(shots):
        sid = _sid(s, i)
        d = S.shot_dur(s, cast, narrator)
        total += d
        # a world shot aimed at parts ("look") is alive when a meter/callout plays, a part moves or the camera moves
        alive = bool(s.get("look") and (s.get("hud") or s.get("callout") or s.get("moves")
                                        or s.get("move", "drift") != "drift"))
        if i and s["camera"] == shots[i - 1]["camera"] and s.get("set") == shots[i - 1].get("set") and not s.get("look"):
            new = CAM_NEXT.get(s["camera"], "medium")
            if new == shots[i - 1]["camera"]:
                new = "wide"
            if fix:
                rep.add("fixed", "camera_repeat", sid, f"same camera as before ({s['camera']}) -> {new}")
                s["camera"] = new
            else:
                rep.add("warn", "camera_repeat", sid, f"same camera as the shot before ({s['camera']})")
        acts = _acts(s)
        moving = [a for _, a in acts if a.get("do") not in QUIET]
        if not moving and not s.get("props") and not s.get("overlay") and not s.get("screen") and not alive:
            target = s["speaker"] if s["speaker"] in [c["id"] for c in s["cast"]] else (s["cast"][0]["id"] if s["cast"] else None)
            if fix and target:
                for c in s["cast"]:
                    if c["id"] == target:
                        c["acts"].append({"do": "explain", "at": 0.0})
                rep.add("fixed", "visual", sid, f"nothing happens; {target} gestures while it is said")
            else:
                rep.add("error", "visual", sid, "nothing happens on screen (no action, prop or overlay)")
        starts = sorted(float(a.get("at", 0)) for _, a in acts)
        gap = _still_gap(acts, d)
        if d > S.STILL_MAX and gap > S.STILL_MAX and not s.get("screen") and not alive:
            first = s["cast"][0] if s["cast"] else None
            if fix and first:
                at = round(min(d - 0.6, max(starts + [0.0]) + S.STILL_MAX * 0.6), 2)
                first["acts"].append({"do": "nod", "at": at})
                rep.add("fixed", "still", sid, f"{gap:.1f}s without movement; {first['id']} nods at {at}s")
            else:
                rep.add("warn", "still", sid, f"{gap:.1f}s without movement")
        for cid, a in acts:
            if not 0 <= float(a.get("at", 0)) < d:
                if fix:
                    a["at"] = round(max(0.0, min(float(a.get("at", 0)), d - 0.3)), 2)
                    rep.add("fixed", "act_time", sid, f"{cid} {a['do']} moved inside the shot ({a['at']}s)")
                else:
                    rep.add("error", "act_time", sid, f"{cid} {a['do']} starts outside the shot")

    # ---- 3D toon-world places: layout exists, every model is in the packs, shot moves name real pieces
    models = S.world_models()
    for pname, pv in (plan.get("places") or {}).items():
        if not S.is_world(plan, pname):
            continue
        try:
            lay = S.world_layout(plan, pname)
        except FileNotFoundError:
            rep.add("error", "world", None, f"place '{pname}': world layout '{pv['world']}' does not exist "
                    f"(have: {', '.join(S.world_names())})")
            continue
        names = [q["m"] for q in lay.get("pieces", [])] + [m for r in lay.get("rows", []) for m in
                                                            (r["m"] if isinstance(r["m"], list) else [r["m"]])]
        for n in sorted(set(names) - models):
            rep.add("error", "world", None, f"place '{pname}': model '{n}' is not in the toon world packs")
        ids = {q.get("id") for q in lay.get("pieces", []) if q.get("id")}
        for sh in shots:
            if sh.get("set") != pname:
                continue
            for mv in sh.get("moves", []):
                if mv.get("id") not in ids:
                    rep.add("error", "world", sh.get("id"), f"move of '{mv.get('id')}' but place '{pname}' has no "
                            f"piece with that id (have: {', '.join(sorted(ids)) or 'none'})")

    # ---- places: the story travels; every narrator line is acted, not just talked
    sets = [s.get("set") for s in shots]
    if len(set(sets)) < MIN_PLACES:
        rep.add("error", "places", None, f"the whole story happens in {len(set(sets))} place(s); "
                f"use at least {MIN_PLACES} (add plan places and move scenes there)")
    run, place_run = 1, S.channel(plan).get("place_run", PLACE_RUN)  # one diorama can carry a long build
    for i in range(1, len(shots)):
        run = run + 1 if sets[i] == sets[i - 1] else 1
        if run == place_run + 1:
            rep.add("error", "places", shots[i]["id"], f"{run} shots in a row in '{sets[i]}'; cut to another place")
    for i, s in enumerate(shots):
        if s.get("speaker") != "narrator":
            continue
        story_act = any(a.get("do") not in GESTURES for _, a in _acts(s))
        new_place = i == 0 or sets[i] != sets[i - 1]
        if not (story_act or s.get("props") or s.get("overlay") or new_place or s.get("screen") or s.get("moves")
                or s.get("hud") or s.get("callout")):
            rep.add("error", "show_line", s["id"], f"'{s['text'][:50]}' is only gestured; show it "
                    "(a prop, overlay, a move/grab/throw, or cut to the place it happens)")

    # ---- retention: hook card + question, loop, pattern break, twist hold, quick cuts, readable props
    ht = str(plan.get("hook_title", "")).strip()
    if not ht or len(ht.split()) > 7:
        rep.add("error", "hook_title", None, "add a hook_title of 2-7 words (the big card over the first shot)")
    hooks = [s for s in shots if s.get("beat") == "hook"]
    if not any(str(s.get("text", "")).rstrip().endswith("?") for s in hooks):
        rep.add("error", "hook_question", None, "a hook line must ask the question the story answers (end with '?')")
    if shots[-1].get("set") != shots[0].get("set"):
        rep.add("error", "loop", shots[-1]["id"], f"end in the opening place ('{shots[0].get('set')}') so the Short loops")
    tw = next((i for i, s in enumerate(shots) if s.get("beat") == "twist"), None)
    if tw:
        prev = shots[tw - 1]
        if prev.get("freeze") is None:
            if fix:
                prev["freeze"] = ""
                rep.add("fixed", "twist_hold", prev["id"], "held beat before the twist (freeze, music stops)")
            else:
                rep.add("warn", "twist_hold", prev["id"], "no held beat before the twist")
    t, ends = 0.0, []
    for s in shots:
        t += S.shot_dur(s, cast, narrator)
        ends.append(t)
    if not any(s.get("freeze") for s, e in zip(shots, ends) if 0.35 * total <= e <= 0.65 * total):
        mid = min(range(len(shots)), key=lambda i: abs(ends[i] - 0.5 * total))
        if fix and not shots[mid].get("freeze") and (tw is None or mid != tw - 1):
            shots[mid]["freeze"] = "WAIT..."
            rep.add("fixed", "break", shots[mid]["id"], "pattern break: WAIT... freeze mid-story")
        else:
            rep.add("error", "break", None, "add a mid-story pattern break: a shot with \"freeze\": \"WAIT...\" 35-65% in")
    quick = [s for s in shots if s.get("beat") in ("con", "escalate") and S.shot_dur(s, cast, narrator) < FAST]
    if not quick:
        rep.add("warn", "rhythm", None, f"no quick cuts in the con/escalate stretch (aim for 2+ lines under {FAST}s)")
    elif len(quick) < 2:
        rep.add("warn", "rhythm", quick[0]["id"], "only one quick cut in the con/escalate stretch")
    for s in shots:
        if s["camera"] in ("wide", "high") and any(p.get("text") and p.get("held_by") for p in s.get("props", [])) \
                and not any(a.get("do") in ("walk", "run", "sneak_walk") for _, a in _acts(s)):
            if fix:
                s["camera"] = "medium"
                rep.add("fixed", "prop_seen", s["id"], "held prop with words in a wide shot -> medium")
            else:
                rep.add("warn", "prop_seen", s["id"], "held prop with words is too small in a wide shot")

    # ---- story shape
    beats = [s.get("beat") for s in shots]
    if beats[0] != "hook":
        rep.add("warn", "hook_first", shots[0]["id"], "the first shot should be the hook")
    first_strong = any(a.get("do") in STRONG for _, a in _acts(shots[0])) or shots[0].get("props")
    if not first_strong:
        rep.add("warn", "hook_first", shots[0]["id"], "the first image should be strange/strong (big action or prop)")
    if beats[-1] not in ("twist", "payoff"):
        rep.add("warn", "payoff_last", shots[-1]["id"], "the story should end on its twist or payoff")
    last = -1
    for s, b in zip(shots, beats):
        if b is None:
            continue
        if b not in S.BEATS:
            rep.add("error", "beat_order", s["id"], f"beat '{b}' unknown")
            continue
        k = S.BEATS.index(b)
        if k < last:
            rep.add("warn", "beat_order", s["id"], f"beat '{b}' comes after '{S.BEATS[last]}'")
        last = max(last, k)
    lo, hi = S.channel(plan).get("length") or (S.STORY_MIN, S.STORY_MAX)  # a channel may set its own range
    if not lo <= total <= hi:
        rep.add("warn", "length", None, f"story is {total:.0f}s (aim {lo:.0f}-{hi:.0f}s)")
    topic = (plan.get("topic") or plan.get("title") or "").strip().lower()
    for old in S.used_topics(stories):
        if old.get("id") != plan.get("id") and topic and topic == str(old.get("topic", "")).strip().lower():
            rep.add("warn", "topic_repeat", None, f"topic already made in story '{old.get('id')}'")
    plan["est_total"] = round(total, 2)
    return _out(plan, rep)


def _out(plan, rep):
    return {"ok": not any(x["level"] == "error" for x in rep.issues), "plan": plan, "issues": rep.issues}


def format_report(r):
    lines = [f"{'OK' if r['ok'] else 'NOT READY'} — {len(r['plan'].get('shots', []))} shots, "
             f"~{r['plan'].get('est_total', 0):.0f}s"]
    for x in r["issues"]:
        lines.append(f"  [{x['level']:5}] {x['shot'] or '--'} {x['rule']}: {x['msg']}")
    return "\n".join(lines)


def main(argv):
    path = Path(argv[0])
    fix = "--fix" in argv
    r = check(S.load_plan(path), fix=fix)
    print(format_report(r))
    if fix:
        S.save_plan(r["plan"], path)
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
