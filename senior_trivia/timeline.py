"""The show's timeline: voice pieces (Edge, one sentence at a time, cached) laid out with the countdowns, reveals and
host clips -> spec {segs, voice, sfx, duration}. Question rhythm from the reference study: the announcer reads the question
and every option (each option pops in as it is read), a short air, the silent countdown (default 6 s, a tick per second),
the chime and "The answer is B, …" with the fun fact, a short hold. Old-item rows: no voice, 7 s timer, the name bar."""
import subprocess
from concurrent.futures import ThreadPoolExecutor

from prepper_host import voice as pv

from senior_trivia import csvplan

LETTERS = "ABCD"
DEFAULT_VOICE = "en-US-AndrewNeural"
NUM_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
_DUR = {}
_SPOKEN = {}


def duration(path):
    p = str(path)
    if p not in _DUR:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                             capture_output=True, text=True, timeout=120)
        _DUR[p] = float(out.stdout.strip() or 0)
    return _DUR[p]


def spoken(path):
    """Seconds until the last spoken word ends (Edge pads each piece with silence): from its .words.json, else its length."""
    p = str(path)
    if p not in _SPOKEN:
        end = 0.0
        try:
            import json
            w = json.loads(open(p + ".words.json", encoding="utf-8").read())
            end = max(float(x["end"]) for x in w) + 0.12 if w else 0.0
        except (OSError, ValueError, KeyError):
            pass
        d = duration(p)
        _SPOKEN[p] = min(d, end) if end > 0.3 else d
    return _SPOKEN[p]


def clip_window(path):
    """(start, end) seconds of a host clip worth showing: from just before his first word to half a second after his last,
    and never into the clip's own ending (2026-11-26, ep01 5:08: a Flow clip dissolved into a ghost of another shot in its
    last 0.3 s, and he sat silent for 3 s after speaking). The shot change is found as the first frame (after 1 s) that
    differs from the clip's settled look far more than his talking ever does."""
    import numpy as np
    from prepper_host import flowvoice as fv
    total = duration(path)
    start, end = 0.0, total
    try:
        a, b = fv.speech_span(fv._read(path))
        start = max(0.0, a - 0.2) if a > 0.6 else 0.0
        end = min(total, b + 0.5)
    except Exception:  # noqa: BLE001 - no sound: keep the whole clip
        pass
    try:
        fps, w, h = 12, 64, 36
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-an", "-vf", f"fps={fps},scale={w}:{h},format=gray",
                              "-f", "rawvideo", "-"], capture_output=True, check=True, timeout=120).stdout
        fr = np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(np.float32)
        k0 = min(len(fr) - 1, fps)                      # the look one second in
        mad = np.abs(fr - fr[k0]).mean(axis=(1, 2))
        calm = mad[k0:max(k0 + 1, int(end * fps))]
        limit = max(14.0, 2.5 * float(np.percentile(calm, 90)))
        jump = np.where((np.arange(len(fr)) > k0) & (mad > limit))[0]
        if len(jump):
            end = min(end, max(start + 1.0, jump[0] / fps - 0.1))
    except Exception:  # noqa: BLE001 - keep the sound-based window
        pass
    end = min(end, total - 0.4)        # Flow clips often turn into a transition in their last moments
    return round(float(start), 3), round(float(max(end, start + 1.0)), 3)


def _say(text):
    return [s for s in pv.sentences(text) if s.strip()]


def scripts(rows):
    """Every sentence the announcer says, per row: {row index: {"q": [...], "opts": [...], "a": [...], "line": [...]}}."""
    out, qn = {}, 0
    for i, r in enumerate(rows):
        t = r["type"]
        if t in ("question", "bonus"):
            if t == "question":
                qn += 1
            head = "Bonus question." if t == "bonus" else f"Question {qn}."
            opts = csvplan.options_of(r)
            ai = csvplan.answer_index(r)
            ans = (f"The answer is {LETTERS[ai]}, {opts[ai]}." if ai is not None else f"The answer is {r['answer']}.")
            out[i] = {"q": _say(f"{head} {r['question']}"), "opts": [f"{LETTERS[k]}, {o}." for k, o in enumerate(opts)],
                      "a": _say(f"{ans} {r['fact']}")}
        elif t == "round":
            out[i] = {"line": _say(r["line"] or f"Round {NUM_WORDS[min(10, sum(1 for x in rows[:i + 1] if x['type'] == 'round'))]}. "
                                                 f"{r['round'].split('|')[0].strip()}.")}
        elif t in ("intro", "check", "outro", "host") and r["line"]:
            out[i] = {"line": _say(r["line"])}
    return out


def voice_all(rows, voice=DEFAULT_VOICE, speed=1.06, skip_host=(), log=print, workers=6):
    """-> {sentence: mp3 path}. Host rows that have a Flow clip (skip_host) are not voiced by Edge."""
    sc = scripts(rows)
    want = []
    for i, parts in sc.items():
        if i in skip_host:
            continue
        for k in ("q", "opts", "a", "line"):
            want += parts.get(k, [])
    want = list(dict.fromkeys(want))
    log(f"senior trivia: Edge voice {voice}, {len(want)} sentence(s)")

    def one(s):
        try:
            return s, str(pv._one(s, voice, speed))
        except Exception:  # noqa: BLE001 - Edge refuses some exact sentences; read them in halves
            return s, str(pv._one_in_halves(s, voice, speed))

    with ThreadPoolExecutor(max_workers=workers) as ex:
        got = dict(ex.map(one, want))
    for p in got.values():
        duration(p)
    return sc, got


def build(rows, voiced, scripts_, clips=None, pics=None, size=(1920, 1080), fps=30, title="", gap=0.1):
    """-> spec. voiced: {sentence: mp3}; clips: {row index: host mp4}; pics: {row index: (pic key, fact pic key)}."""
    clips, pics = clips or {}, pics or {}
    segs, voice, sfx = [], [], []
    t = 0.0
    qn = itn = rn = 0
    n_q = sum(1 for r in rows if r["type"] in ("question", "item"))

    def speak(sents, at):
        for s in sents:
            p = voiced.get(s)
            if not p:
                continue
            voice.append({"t": round(at, 3), "path": p})
            at += spoken(p) + gap
        return at

    for i, r in enumerate(rows):
        typ = r["type"]
        sc = scripts_.get(i, {})
        pk, fk = pics.get(i, (None, None))
        seg = {"kind": typ, "row": i, "t0": round(t, 3), "pic": pk, "fact_pic": fk}
        if typ in ("question", "bonus"):
            if typ == "question":
                qn += 1
            opts = csvplan.options_of(r)
            seg.update(n=qn, total=n_q, question=r["question"], options=opts, answer=csvplan.answer_index(r),
                       answer_text=csvplan.answer_text(r), fact=r["fact"], round=_round_name(rows, i))
            at = speak(sc.get("q", []), t + 0.35)
            seg["opt_at"] = []
            for o in sc.get("opts", []):
                seg["opt_at"].append(round(at, 3))
                sfx.append({"name": "pop", "t": round(at, 3)})
                at = speak([o], at)
            if not opts:
                seg["opt_at"] = []
            secs = float(r["seconds"] or 6)
            seg["count_at"] = round(at + 0.2, 3)
            seg["seconds"] = secs
            for k in range(int(secs)):
                sfx.append({"name": "tick", "t": round(seg["count_at"] + k, 3)})
            seg["reveal_at"] = round(seg["count_at"] + secs, 3)
            sfx.append({"name": "chime", "t": seg["reveal_at"]})
            end = speak(sc.get("a", []), seg["reveal_at"] + 0.3)
            t = end + 0.8
        elif typ == "item":
            itn += 1
            secs = float(r["seconds"] or 7)
            seg.update(n=itn, total=n_q, answer_text=r["answer"], count_at=round(t + 0.5, 3), seconds=secs)
            for k in range(int(secs)):
                sfx.append({"name": "tick", "t": round(seg["count_at"] + k, 3)})
            seg["reveal_at"] = round(seg["count_at"] + secs, 3)
            sfx.append({"name": "chime", "t": seg["reveal_at"]})
            t = seg["reveal_at"] + 2.6
        elif typ == "round":
            rn += 1
            name, _, level = r["round"].partition("|")
            seg.update(n=rn, title=name.strip(), level=level.strip().lower(), pic=_next_pic(rows, pics, i))
            sfx.append({"name": "whoosh", "t": round(t + 0.1, 3)})
            t = max(t + 3.6, speak(sc.get("line", []), t + 0.7) + 1.0)
        elif typ == "host":
            clip = clips.get(i)
            seg.update(line=r["line"], clip=clip, first=not any(s["kind"] == "host" for s in segs))
            if clip:
                c0, c1 = clip_window(clip)
                seg.update(clip_audio=True, clip_start=c0, clip_end=c1)
                t += max(2.0, c1 - c0)
            else:
                t = speak(sc.get("line", []), t + 0.4) + 0.8
        elif typ in ("intro", "check", "outro"):
            seg.update(line=r["line"], title=title, total=n_q,
                       montage=[pics[j][0] for j in sorted(pics) if rows[j]["type"] in ("question", "item") and pics[j][0]][:3])
            if typ == "check":
                seg["round"] = _round_name(rows, i)
            seg["line_at"] = []
            at = t + 0.6
            for s in sc.get("line", []):
                seg["line_at"].append(round(at, 3))
                at = speak([s], at)
            t = at + (2.8 if typ == "outro" else 1.0)
        else:
            continue
        seg["t1"] = round(t, 3)
        segs.append(seg)
    return {"segs": segs, "voice": voice, "sfx": sfx, "duration": round(t, 3), "size": list(size), "fps": fps,
            "title": title, "mode": csvplan.mode_of(rows)}


def _round_name(rows, i):
    for r in reversed(rows[:i + 1]):
        if r["type"] == "round":
            return r["round"].split("|")[0].strip()
    return ""


def _next_pic(rows, pics, i):
    for j in range(i + 1, len(rows)):
        if pics.get(j, (None,))[0]:
            return pics[j][0]
    return None
