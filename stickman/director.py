"""Director: script + spoken word times -> a stickman plan (the same JSON the renderer reads).

All local rules, no AI calls:
  * captions: short one-line chunks cut at sentence/clause ends, each at most MAX_WORDS
    words, MAX_CHARS characters and MAX_BEAT seconds; one chunk = one beat;
  * action: keyword scores per beat pick one of the poses; a variety guard stops the
    same action coming back within VARIETY beats;
  * cast: a lead ("you" or the main name) and a second figure who walks in the first
    time the script talks about someone else; the other figure reacts;
  * hook: the lead runs in on the first beat while the title writes on;
  * camera: wide for big moves, close on the actor for small ones, never the same three times;
  * sound: an effect on big actions (spaced out), a calm music bed under the voice.
"""
import re

from . import places, poses

MAX_WORDS = 6
MAX_CHARS = 32
MAX_BEAT = 2.8
MIN_BEAT = 0.8
VARIETY = 3
TAIL = 0.8
PLACE_HOLD = 8.0

STOP = set("""a an the and or but so to of in on at for with is are was were be been it its it's this that these those
you your you're i me my we our he him his she her they them their there here as if then than just like very too not no
do does did done have has had will would can could should up out off over into from by about all any some one""".split())

LEXICON = {
    "think": "think thinks thought wonder why how what ideas question maybe imagine remember consider plan learn know reason",
    "point": "this here see first second third notice fact because number truth rule step",
    "shrug": "but however unsure sure doesn't don't nobody confused simple weird strange whatever normal anyway",
    "cheer": "great win wins success happy love best finally works amazing awake free easy better good perfect",
    "facepalm": "mistake wrong fail fails oops forgot bad regret waste worse problem sorry",
    "scared": "scary afraid danger fear panic risk worst death warning terrible shock bright late",
    "run": "run rush hurry fast escape chase quick racing flying speed",
    "walk": "walk go goes move moving start step leave come journey travel",
    "jump": "jump boom burst wow huge massive explode pop",
    "wave": "hello hi hey bye goodbye welcome",
    "clap": "congrats congratulations applause bravo",
    "dance": "party dance celebrate celebration fun music",
    "laugh": "funny laugh joke hilarious ridiculous",
    "cry": "cry crying tears heartbreak",
    "sad": "sad alone lonely depressed unhappy lost",
    "angry": "angry mad hate furious annoying annoyed rage",
    "tired": "tired exhausted sleepy drained weak shallow",
    "yawn": "yawn boring bored",
    "arms_crossed": "never refuse won't nope stubborn swears",
    "hands_hips": "ready confident proud",
    "present": "here's fix answer solution introducing meet secret pattern",
    "stop": "stop wait careful avoid quit no",
    "look": "look find search discover spot looking watch",
    "phone": "phone screen scrolling call text message app",
    "type": "email laptop computer typing work working online",
    "carry": "carry bring heavy bag deliver",
    "push": "push harder effort force try trying",
    "pull": "pull drag",
    "lift": "lift strong strength gym weights stronger",
    "sit": "sit sitting couch rest relax",
    "sleep": "sleep sleeps slept asleep bed dream",
    "fall": "fall falls fell crash collapse",
    "kneel": "please beg",
    "crouch": "hide hiding",
    "sneak": "sneak sneaky quietly secretly creep stealing",
    "bow": "thank thanks respect",
    "fist_up": "yes victory power motivated change",
    "idea": "idea realize realized suddenly genius trick hack",
    "shiver": "cold freezing winter shiver ice",
}
WORD_ACT = {}
for _act, _words in LEXICON.items():
    for _w in _words.split():
        WORD_ACT.setdefault(_w, []).append(_act)

ALT = {"cheer": "jump", "jump": "cheer", "facepalm": "shrug", "think": "idea", "point": "present",
       "scared": "crouch", "shrug": "think", "walk": "run", "run": "walk", "sad": "cry", "cry": "sad",
       "laugh": "clap", "clap": "laugh", "angry": "stop", "stop": "arms_crossed", "tired": "yawn", "yawn": "tired",
       "sleep": "tired", "wave": "present", "present": "point", "idea": "think", "phone": "type", "type": "phone",
       "look": "point", "fist_up": "cheer", "sneak": "crouch", "dance": "clap", "fall": "sad"}
FALLBACK = ("point", "present", "think", "hands_hips", "shrug", "arms_crossed", "look", "stop", "idea", "wave")
MOVES = ("walk", "run", "sneak")
LYING = ("sleep", "fall", "sit", "kneel", "crouch")

# props the words call for: word -> (prop, where)
_PROP_WORDS = {
    "phone": "phone phones screen", "laptop": "laptop computer email", "cup": "coffee tea cup caffeine",
    "clock": "clock time hours o'clock hour minutes", "alarm": "alarm", "calendar": "weekend weekends saturday sunday monday week calendar",
    "moon": "midnight night tonight", "sun": "daytime morning sunlight", "bed": "bed", "zzz": "sleep asleep sleepy",
    "bulb": "idea", "brain": "brain mind memory", "heart": "love heart health", "money": "money cash dollars salary pay",
    "moneybag": "rich wealth savings", "house": "home house", "car": "car drive traffic", "plane": "flying fly plane flight",
    "globe": "country world countries", "book": "book read study", "chart_up": "grow growth increase",
    "chart_down": "decrease drop", "question": "why question", "exclaim": "wow warning important", "check": "fix works done",
    "cross": "wrong mistake", "battery_low": "tired exhausted drained", "battery_full": "awake energy charged",
    "drop": "blood water", "pill": "medicine pill", "burger": "food eat lunch dinner breakfast", "apple": "healthy fruit",
    "barbell": "gym exercise", "trophy": "win winner best", "target": "goal goals focus", "hourglass": "wait waiting",
    "lock": "lock locked", "key": "key secret", "gift": "gift free bonus", "fire": "fire hot burning", "bolt": "power",
    "rocket": "launch boost", "magnifier": "search closer", "speech": "say says said tells", "thought": "imagine",
    "star": "star famous", "hourglass_": "",
}
ABOVE = ("question", "exclaim", "check", "cross", "zzz", "bulb", "heart", "thought", "star", "speech")
PROP_WORD = {}
for _p, _ws in _PROP_WORDS.items():
    for _w in _ws.split():
        PROP_WORD.setdefault(_w, _p)
YOU_WORDS = set("you your you're yourself".split())
OTHER_WORDS = set("friend friends he him his she her they them their people someone others boss partner".split())
BIG = ("run", "walk", "sneak", "jump", "cheer", "dance", "fall", "sleep", "push", "pull")
SFX = {"run": ("whoosh", 0.0, -2), "jump": ("boing", 0.25, 0), "cheer": ("sparkle", 0.1, -3),
       "scared": ("burst", 0.05, -4), "facepalm": ("pop", 0.15, -6), "point": ("pop", 0.1, -9),
       "idea": ("chime", 0.05, -6), "fall": ("burst", 0.2, -3), "clap": ("pop", 0.0, -8), "dance": ("sparkle", 0.0, -4),
       "fist_up": ("success", 0.0, -8), "wave": ("pop", 0.1, -10), "present": ("pop", 0.1, -10)}
SFX_GAP = 1.6
SPEED = {"walk": 0.16, "run": 0.40, "sneak": 0.08}      # screen widths per second at figure height 0.4 (see poses._GAITS)


def _travel(act, dist):
    return 0.3 + abs(dist) / SPEED[act]


def norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower().replace("’", "'"))


# ------------------------------------------------------------------ words
def align(script, words):
    """Script tokens (with punctuation) matched to the voice's word times, in order."""
    toks = script.split()
    out, j = [], 0
    for i, tok in enumerate(toks):
        n = norm(tok)
        hit = None
        for k in range(j, min(j + 4, len(words))):
            if norm(words[k]["word"]) == n or (n and norm(words[k]["word"]).startswith(n[:4])):
                hit = k
                break
        if hit is not None:
            out.append({"text": tok, "start": words[hit]["start"], "end": words[hit]["end"]})
            j = hit + 1
        else:
            out.append({"text": tok, "start": None, "end": None})
    # fill words the voice timings missed by spreading them between known neighbours
    known = [i for i, w in enumerate(out) if w["start"] is not None]
    if not known:
        raise ValueError("the voice's word timings don't match the script")
    for i, w in enumerate(out):
        if w["start"] is None:
            prev = max([k for k in known if k < i], default=None)
            nxt = min([k for k in known if k > i], default=None)
            a = out[prev]["end"] if prev is not None else 0.0
            b = out[nxt]["start"] if nxt is not None else a + 0.4
            w["start"] = w["end"] = a + (b - a) * 0.5
    return out


def chunks(tokens, max_words=MAX_WORDS, max_chars=MAX_CHARS):
    """One-line caption chunks; each becomes a beat. A CSV row always starts a new chunk."""
    MAX_WORDS, MAX_CHARS = max_words, max_chars
    res, cur = [], []
    for k, tok in enumerate(tokens):
        if cur:
            text = " ".join(t["text"] for t in cur + [tok])
            prev = cur[-1]["text"]
            if (tok.get("row") != cur[-1].get("row") or prev[-1] in ".?!" or len(cur) >= MAX_WORDS or len(text) > MAX_CHARS
                    or tok["end"] - cur[0]["start"] > MAX_BEAT
                    or (prev[-1] in ",;:" and len(cur) >= 2)):
                res.append(cur)
                cur = []
        cur.append(tok)
    if cur:
        res.append(cur)
    # no one-word orphan line: take a word from the line before (same sentence) when it has words to spare
    for k in range(1, len(res)):
        a, b = res[k - 1], res[k]
        if len(b) == 1 and len(a) >= 3 and a[-1]["text"][-1] not in ".?!,;:" and a[-1].get("row") == b[0].get("row"):
            res[k - 1], res[k] = a[:-1], a[-1:] + b
    # merge chunks too short to act in, when the merged line still fits
    merged = []
    for c in res:
        if merged:
            m = merged[-1]
            short = (c[-1]["end"] - c[0]["start"] < MIN_BEAT) or (m[-1]["end"] - m[0]["start"] < MIN_BEAT)
            text = " ".join(t["text"] for t in m + c)
            if (short and len(m + c) <= MAX_WORDS and len(text) <= MAX_CHARS and c[-1]["end"] - m[0]["start"] <= MAX_BEAT
                    and m[0].get("row") == c[0].get("row")):
                merged[-1] = m + c
                continue
        merged.append(c)
    return merged


# ------------------------------------------------------------------ picks
def pick_action(words, recent, allowed, i=0):
    score = {}
    for w in words:
        for a in WORD_ACT.get(norm(w), []):
            if a in allowed:
                score[a] = score.get(a, 0) + 1
    ranked = sorted(score, key=lambda a: -score[a])
    for a in ranked:                     # a keyword match only has to differ from the last beat
        if not recent or a != recent[-1]:
            return a, True
        alt = ALT.get(a)
        if alt in allowed and alt not in recent[-1:]:
            return alt, True
    k = (i * 3) % len(FALLBACK)          # no keyword: rotate through calm talking poses
    for a in FALLBACK[k:] + FALLBACK[:k]:
        if a in allowed and a not in recent:
            return a, False
    return "stand", False


def pick_prop(words, act, last):
    held = {n for n, _, _ in poses.POSE_PROPS.get(act, ())}
    above_busy = any(w == "above" for _, w, _ in poses.POSE_PROPS.get(act, ()))
    for w in words:
        p = PROP_WORD.get(norm(w))
        if p and p != last and p not in held:
            at = "above" if p in ABOVE and not above_busy else "side"
            return {"name": p, "at": at, "size": 0.3 if at == "above" else 0.5}, w
    return None, None


def pick_place(sentence_words):
    sc = places.score([norm(w) for w in sentence_words])
    return max(sc, key=lambda p: sc[p]) if sc else None


def key_word(chunk, act, matched):
    words = [t["text"] for t in chunk]
    if matched:
        for w in words:
            if act in WORD_ACT.get(norm(w), []):
                return w
    content = [w for w in words if norm(w) not in STOP and len(norm(w)) > 3]
    return max(content, key=lambda w: len(norm(w))) if content else None


def caption(chunk, key):
    parts, done = [], False
    for t in chunk:
        w = t["text"]
        if not done and key and w == key:
            m = re.match(r"^(\W*)(.*?)(\W*)$", w)
            parts.append(f"{m.group(1)}*{m.group(2)}*{m.group(3)}")
            done = True
        else:
            parts.append(w)
    return " ".join(parts)


def _shot(kind, x):
    if kind == "wide":
        return {"zoom": 1.0, "x": 0.5, "kind": "wide"}
    if kind == "medium":
        return {"zoom": 1.08, "x": round(0.5 + (x - 0.5) * 0.5, 3), "kind": "medium"}
    return {"zoom": 1.18, "x": round(min(0.68, max(0.32, x)), 3), "kind": "close"}


# ------------------------------------------------------------------ plan
SHORTS_LAYOUT = {"ground": 0.70, "caption_y": 0.79, "caption_size": 0.040, "title_y": 0.15, "title_size": 0.060,
                 "place_scale": 0.62, "wall_min": 0.31, "spread": 1.18}


def direct(script, words, duration, title=None, look="ink_paper", size=None, fps=30, rows=None, shorts=False):
    """rows: Stickman CSV rows (csvplan.read); their lines must make up the script. shorts: native 9:16 layout."""
    size = size or ((1080, 1920) if shorts else (1920, 1080))
    tokens = align(script, words)
    if rows:
        ids = [k for k, r in enumerate(rows) for _ in r["line"].split()]
        if len(ids) != len(tokens):
            raise ValueError("the CSV lines don't make up the script")
        for t, k in zip(tokens, ids):
            t["row"] = k
    cs = chunks(tokens, 4, 20) if shorts else chunks(tokens)
    starts = [0.0] + [c[0]["start"] for c in cs[1:]]
    end = max(duration, tokens[-1]["end"] + TAIL)
    row_start = {}
    for i, c in enumerate(cs):
        row_start.setdefault(c[0].get("row"), starts[i])
    csv_places = bool(rows) and any(r.get("place") for r in rows)

    lead, other = "lead", "other"
    fh = 0.26 if shorts else 0.40
    home = (0.30, 0.70) if shorts else (0.36, 0.68)
    figs = {lead: {"x": -0.08 if not shorts else -0.15, "facing": 1, "height": fh},
            other: {"x": 1.10 if not shorts else 1.15, "facing": -1, "height": fh}}
    pos = {lead: home[0], other: None}            # where each figure will be standing
    cards = []
    recent = {lead: [], other: []}
    busy = {lead: 0.0, other: 0.0}            # a figure still walking/jumping is not given a new action
    beats, sfx, last_sfx = [], [], -9.0
    shots = []
    place, place_t, last_prop = "void", 0.0, None
    for i, c in enumerate(cs):
        t0 = starts[i]
        t1 = starts[i + 1] if i + 1 < len(cs) else end
        words_i = [t["text"] for t in c]
        about_other = any(norm(w) in OTHER_WORDS for w in words_i)
        acts = {}
        if i == 0:                                         # hook: the lead runs in under the title
            act, matched = "run", False
            acts[lead] = {"do": "run", "to": home[0]}
            busy[lead] = _travel("run", home[0] - figs[lead]["x"])
            actor = lead
        else:
            about_you = any(norm(w) in YOU_WORDS for w in words_i)
            actor = other if (about_other or (pos[other] is not None and not about_you and i % 3 == 2)) else lead
            if busy[actor] > t0 + 0.05:
                alt = lead if actor == other else other
                actor = alt if (pos[alt] is not None and busy[alt] <= t0 + 0.05) else None
            if actor is None:                              # everyone is mid-move: the move itself is the change
                act, matched = beats[-1]["action"], False
                actor = beats[-1]["actor"]
            elif actor == other and pos[other] is None:    # first mention: walk in
                acts[other] = {"do": "walk", "to": home[1]}
                busy[other] = t0 + _travel("walk", figs[other]["x"] - home[1])
                pos[other] = home[1]
                act, matched = "walk", True
                if busy[lead] <= t0 + 0.05:
                    acts[lead] = {"do": "point", "face": 1}
            else:
                allowed = set(poses.ALL) - set(MOVES) if actor == other else set(poses.ALL)
                act, matched = pick_action(words_i, recent[actor][-VARIETY:], allowed, i)
                a = {"do": act}
                if act in MOVES:
                    lo, hi = (0.18, (pos[other] or 1.0) - 0.22) if actor == lead else (pos[lead] + 0.22, 0.82)
                    here = pos[actor]
                    to = here - 0.16 if here - 0.16 >= lo else min(hi, here + 0.16)
                    a["to"] = round(to, 3)
                    busy[actor] = t0 + _travel(act, to - here)
                    pos[actor] = to
                    a["then"] = {"walk": "point", "sneak": "crouch"}.get(act, "stand")
                else:
                    a["face"] = 1 if actor == lead else -1
                if act == "jump":
                    busy[actor] = t0 + poses.JUMP_DUR
                acts[actor] = a
                # the other figure reacts now and then so the frame never sits still
                buddy = lead if actor == other else (other if pos[other] is not None else None)
                if buddy and i % 2 == 0 and busy[buddy] <= t0 + 0.05:
                    react = "shrug" if act in ("cheer", "jump") else ("scared" if act == "scared" else "stand")
                    if react not in recent[buddy][-2:]:
                        acts[buddy] = {"do": react, "face": 1 if buddy == lead else -1}
                        recent[buddy].append(react)
        if acts.get(actor):
            recent[actor].append(act)

        row = rows[c[0]["row"]] if rows else {}
        first_of_row = bool(rows) and (i == 0 or cs[i - 1][0].get("row") != c[0].get("row"))
        locked = []
        if first_of_row and row.get("action") and i > 0:
            who = row.get("who") or ("other" if about_other and pos[other] is not None else lead)
            want = row["action"]
            moving_in = acts.get(who, {}).get("do") in MOVES and want in poses.STATIC
            if moving_in:                                      # already walking in this beat: the CSV pose comes when they arrive
                acts[who]["then"] = want
            else:
                acts = {k: v for k, v in acts.items() if k != who}
            if moving_in:
                pass
            elif who == other and pos[other] is None:            # the friend has to walk in first
                acts[other] = {"do": "walk", "to": home[1]}
                if want in poses.STATIC:
                    acts[other]["then"] = want
                pos[other] = home[1]
                busy[other] = t0 + _travel("walk", figs[other]["x"] - home[1])
            else:
                a = {"do": want}
                if want in MOVES:
                    lo, hi = (0.18, (pos[other] or 1.0) - 0.22) if who == lead else (pos[lead] + 0.22, 0.82)
                    here = pos[who]
                    to = here - 0.16 if here - 0.16 >= lo else min(hi, here + 0.16)
                    a["to"] = round(to, 3)
                    busy[who] = t0 + _travel(want, to - here)
                    pos[who] = to
                elif want == "jump":
                    busy[who] = t0 + poses.JUMP_DUR
                else:
                    a["face"] = 1 if who == lead else -1
                acts[who] = a
            actor, act, matched = who, want, True
            recent[who].append(want)
            locked.append("action")

        x = pos[actor] if pos[actor] is not None else 0.5
        kind = "wide" if (i == 0 or act in BIG) else ("close" if i % 2 else "medium")
        if len(shots) >= 2 and shots[-1] == shots[-2] == kind:
            kind = "medium" if kind != "medium" else "close"
        if first_of_row and row.get("camera"):
            kind = row["camera"]
            locked.append("camera")
        shots.append(kind)

        key = key_word(c, act, matched)
        beat = {
            "t": round(t0, 3), "dur": round(t1 - t0, 3), "caption": caption(c, key),
            "words": [{"w": t["text"], "t": round(t["start"], 3)} for t in c],
            "camera": _shot(kind, x), "acts": acts, "actor": actor, "action": act,
        }
        # a prop the words name pops up beside (or above) the actor
        prop, pw = pick_prop(words_i, act if acts.get(actor) else None, last_prop)
        if first_of_row and row.get("props"):
            beat["props"] = [{"name": q["name"], "fig": actor,
                              "at": q.get("at") or ("above" if q["name"] in ABOVE else "side"),
                              "size": 0.3 if (q.get("at") or ("above" if q["name"] in ABOVE else "side")) == "above" else 0.5}
                             for q in row["props"]]
            last_prop = beat["props"][-1]["name"]
            locked.append("props")
        elif prop and i > 0:
            prop["fig"] = actor
            beat["props"] = [prop]
            last_prop = prop["name"]
            if not matched and pw:
                beat["caption"] = caption(c, pw)
        else:
            last_prop = None
        # a new place when a sentence starts that clearly belongs somewhere else
        if first_of_row and row.get("place"):
            if row["place"] != place:
                beat["place"] = place = row["place"]
                place_t = t0
                if i > 0 and t0 - last_sfx >= SFX_GAP:
                    sfx.append({"t": round(t0, 3), "name": "whoosh", "gain_db": -8})
                    last_sfx = t0
            locked.append("place")
        elif not csv_places and (i == 0 or cs[i - 1][-1]["text"][-1] in ".?!"):
            sent = []
            for c2 in cs[i:]:
                sent += [t["text"] for t in c2]
                if c2[-1]["text"][-1] in ".?!":
                    break
            if i == 0:
                for c2 in cs[i + 1:i + 6]:
                    sent += [t["text"] for t in c2]
            want = pick_place(sent)
            if want and want != place and (i == 0 or t0 - place_t >= PLACE_HOLD):
                beat["place"] = want
                place, place_t = want, t0
                if i > 0 and t0 - last_sfx >= SFX_GAP:
                    sfx.append({"t": round(t0, 3), "name": "whoosh", "gain_db": -8})
                    last_sfx = t0
        if first_of_row and row.get("text"):
            k = c[0]["row"]
            t_end = row_start.get(k + 1, end)
            cards.append({"text": row["text"], "t0": round(t0, 3), "t1": round(min(t_end, t0 + 3.0), 3)})
        if first_of_row and row.get("sfx"):
            sfx.append({"t": round(t0, 3), "name": row["sfx"], "gain_db": -4})
            last_sfx = t0
        if locked:
            beat["locked"] = locked
        beats.append(beat)
        if act in SFX:
            name, delay, gain = SFX[act]
            at = t0 + delay
            if at - last_sfx >= SFX_GAP:
                sfx.append({"t": round(at, 3), "name": name, "gain_db": gain})
                last_sfx = at

    # beats must add up exactly
    for a, b in zip(beats, beats[1:]):
        a["dur"] = round(b["t"] - a["t"], 3)
    beats[-1]["dur"] = round(end - beats[-1]["t"], 3)
    total = round(beats[-1]["t"] + beats[-1]["dur"], 3)
    spec = {
        "look": look, "fps": fps, "size": list(size), "duration": total,
        "figures": figs, "beats": beats,
        "audio": {"sfx": sfx, "music": {"bed": "calm", "gap_db": -13, "duck_db": -11, "fade_in": 1.0, "fade_out": 2.0}},
    }
    if title:
        spec["title"] = {"text": title, "t1": min(3.0, total)}
    if cards:
        spec["cards"] = cards
    if shorts:
        spec["layout"] = dict(SHORTS_LAYOUT)
        spec["ground"] = SHORTS_LAYOUT["ground"]
        spec["shorts"] = True
    return spec
