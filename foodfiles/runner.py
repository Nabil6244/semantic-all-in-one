"""Food Files runner: what the app page, make_video and the command line call.

plan(...)   = Generate: voice + word times, director, checker, then Flow makes what is missing (the host pack on the
              first run, scene / photo pictures, icon stickers, the thumbnail picture) and, if asked, the host's talking clips.
render(...) = Render: draw every shot, mix voice + effects + music, write the mp4 and a thumbnail .jpg next to it.
No Gemini. Flow pictures are free; talking clips use Flow video credits (made once, kept in the library).

talking:
  False   the host's set picture with a slow push (no credits)
  "stills" 8 Flow pictures of the host in different poses, cycled on the host shots (no credits: for tests)
  True    3 silent talking loops of the host, reused on every host shot (lips don't follow the words)
  "flow"  every host line spoken by its own Flow clip in his Flow voice (lips match; one clip per <=18 words)

  python -m foodfiles.runner my.csv [--voice file.mp3] [--preview] [--no-flow] [--talking | --flow-voice] [--out video.mp4]
"""
import json
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from prepper_host import flow  # noqa: E402
from foodfiles import check as _check, csvplan, director, host as _host, render as _render, sources  # noqa: E402

EDGE_VOICES = ("en-US-AndrewNeural", "en-US-BrianNeural", "en-US-ChristopherNeural", "en-US-EricNeural", "en-US-GuyNeural")
OUT = ROOT / "out" / "foodfiles"
Stopped = _render.Stopped
TALK_LINES = (
    "Okay, so this one sounds completely made up, but I promise you it is real, and it gets so much worse.",
    "And here's the part nobody tells you, because the company really hoped you would never find out.",
    "So yeah, that actually happened. But believe it or not, this next one is even crazier.",
)
EXTRA_COLS = ("item", "title", "name", "year", "place", "stamp", "note", "rows", "source", "visual")


def size_for(preview):
    return (1280, 720) if preview else (1920, 1080)


def _rows_from_script(text):
    from prepper_host import director as PD
    return [dict({c: "" for c in csvplan.COLS}, line=s, n=i + 1) for i, s in enumerate(PD.sentences(text))]


def _voice(body, voice_file, edge_voice, log):
    from prepper_host import voice as pv
    return pv.from_file(voice_file, log=log) if voice_file else pv.edge(body, edge_voice or EDGE_VOICES[0], log=log)


def _flow_voice(rows, spec, meta, edge_voice, size, title, use_flow, log, cancel, budget=None):
    """Host lines spoken by his own Flow clips (Prepper Host's Flow voice), the rest by Edge or his cloned voice.
    budget: at most this many Flow clips, spent mostly at the start (front_load)."""
    from prepper_host import flowvoice as fv
    rows2 = fv.split_rows(rows, spec)
    prev_n = None
    for r in rows2:                       # pieces after the first keep only the words (cards stay on the first piece)
        if r.get("say") and r.get("n") == prev_n:
            r.update({c: "" for c in EXTRA_COLS})
            r["shot"] = "host"
        elif r.get("say") and r.get("shot") == "split" and not r.get("visual"):
            r["shot"] = "host"
        prev_n = r.get("n")
    if budget is not None:
        rows2 = front_load(rows2, rows, spec, budget, log=log)
    jobs = {fv.clip_key(meta, r["line"]): fv.clip_prompt(meta, r["line"]) for r in rows2 if r.get("say")}
    missing = {k: p for k, p in jobs.items() if not flow.have(k, "mp4")}
    log(f"food files: Flow voice: {len(jobs)} host line(s), {len(jobs) - len(missing)} already spoken, {len(missing)} to make")
    if missing and use_flow and not (cancel and cancel()):
        try:
            with flow.Session(log=log) as fs:
                fs.clips(missing, refs=_host.refs(meta), cancel=cancel, voice=fv.flow_voice(meta))
        except Exception as e:  # noqa: BLE001 - a missing clip leaves its line on the Edge voice
            log(f"food files: Flow trouble ({type(e).__name__}: {e}); those lines keep the Edge voice")
    clips = {k: flow.have(fv.clip_key(meta, r["line"]), "mp4") for k, r in enumerate(rows2) if r.get("say")}
    clips = {k: v for k, v in clips.items() if v}
    left = sum(1 for r in rows2 if r.get("say")) - len(clips)
    if left:
        log(f"food files: {left} host line(s) on the Edge voice (no Flow clip yet; Generate again to retry)")
    cloned = {}
    sample = fv.voice_sample(meta, list(clips.values()))
    if sample:
        try:
            cloned = fv.clone_lines([r["line"] for k, r in enumerate(rows2) if k not in clips], sample, log=log, cancel=cancel)
        except Exception as e:  # noqa: BLE001
            log(f"food files: voice clone not used ({e}); the other lines use the Edge voice")
    # no dead air (owner, 2026-11-22): pauses squeezed, each one inside a clip jump-cut on screen; a pause whose cut would
    # leave a sliver of picture is spared and the voice is built again without cutting it
    spare = {}
    for _pass in range(3):
        vo = fv.build(rows2, clips, edge_voice, log=log, cloned=cloned, tight=True, spare=spare)
        spec = director.direct(rows2, vo["words"], vo["duration"], size=size, host_meta=meta, title=title or "")
        fv.attach(spec, rows2, vo["said"])
        bad = sliver_cuts(spec, vo.get("cuts") or {})
        if not bad:
            break
        for k, n in bad:
            spare.setdefault(k, set()).add(n)
    n_cuts = jump_cuts(spec, vo["said"], vo.get("cuts") or {})
    if n_cuts:
        log(f"food files: {n_cuts} long pause(s) inside host clips cut out as jump cuts (lips stay in sync)")
    spec["flow_voice"] = {"lines": len(jobs), "spoken": len(clips), "cloned": len(cloned)}
    return rows2, spec, vo


def plan(csv_path=None, script=None, voice_file=None, edge_voice=None, host="theo", talking=False, preview=False,
         sound="music", use_flow=True, title=None, log=print, cancel=None, clip_budget=15, wall_pct=10.0):
    problems, rows, thumb_row, text = [], None, None, ""
    if script:
        sp = Path(str(script))
        text = sp.read_text(encoding="utf-8-sig") if "\n" not in str(script) and sp.is_file() else str(script)
        lines = [l.strip() for l in text.strip().splitlines()]
        if title is None and len(lines) > 1 and lines[0] and lines[0][-1] not in ".?!":
            title, text = lines[0], " ".join(lines[1:])
    if csv_path:
        rows, problems = csvplan.read(csv_path)
        thumb_row = next((r for r in rows if r["shot"] == "thumbnail"), None)
        rows = [r for r in rows if r["shot"] != "thumbnail"]
        if title is None:
            title = Path(str(csv_path)).stem.replace("_", " ")
    if not rows:
        if not text.strip():
            raise ValueError("no narration: choose a Food Files CSV or a script")
        rows = _rows_from_script(text)
    meta = _host.load(host or "theo")
    size = size_for(preview)

    # the host pack comes first: every host picture and clip is made from it
    if (not meta.get("portrait") or not meta.get("set_image")) and use_flow and not (cancel and cancel()):
        try:
            with flow.Session(log=log) as fs:
                meta = _host.make_pack(meta, fs, log=log, cancel=cancel)
        except Exception as e:  # noqa: BLE001
            log(f"food files: Flow could not make the host pack yet ({type(e).__name__}: {e})")
    stills = talking == "stills"
    budgeted = talking == "budget"
    if stills:
        talking = False                # no clips at all; the free Edge voice reads every line
    poses = stills or budgeted         # host shots without a clip show his still poses
    if talking and not meta.get("portrait"):
        log("food files: no host portrait yet, so no talking clips this run (host shots use a stand-in)")
        talking = False

    vo = _voice(csvplan.script_of(rows), voice_file, edge_voice, log)
    spec = director.direct(rows, vo["words"], vo["duration"], size=size, host_meta=meta, title=title or "")
    if talking in ("flow", "budget"):
        if voice_file:
            log("food files: Flow voice needs the Edge voice for the other lines; your voice file is used as it is")
        else:
            rows, spec, vo = _flow_voice(rows, spec, meta, edge_voice or EDGE_VOICES[0], size, title, use_flow, log, cancel,
                                         budget=clip_budget if budgeted else None)
    if talking not in (True, "stills"):
        n_still = no_host_stills(spec, meta)
        if n_still:
            log(f"food files: {n_still} host shot(s) without a talking clip show a Flow picture of the line instead of a still of him")
    rep = _check.check(spec)
    for m in rep["repaired"]:
        log(f"  check: {m}")
    for m in rep["problems"]:
        log(f"  check: {m}")
    spec["check"] = rep
    spec["voice_path"] = vo["path"]
    spec["sound"] = sound
    spec["host"] = {k: meta.get(k) for k in ("name", "tagline", "look", "set_image", "portrait", "dir")}

    # thumbnail picture
    if thumb_row:
        tprompt = thumb_row["visual"] or "{host} looking shocked, holding a strange old candy up to the camera"
        tlines = [x.strip() for x in (thumb_row["title"] or title or "").split("|")]
    else:
        tprompt = "{host} looking shocked at the camera, holding up a strange old snack, his studio shelves behind him"
        words = re.sub(r"(?i)^the\s+", "", title or "").split()
        tlines = [" ".join(words[:1]).upper(), " ".join(words[1:3]).upper()] if words else ["", ""]
    tfull = _host.expand(tprompt, meta) + ". Photorealistic, bright, high contrast YouTube thumbnail photo, no text."
    tkey = director.key_of(f"{meta['name']}|{tfull}")
    spec["pictures"][tkey] = {"prompt": tfull, "host": True}
    spec["thumbnail"] = {"pic": tkey, "lines": tlines, "visual": tprompt}

    if poses and meta.get("portrait"):
        for k, prompt in _host.pose_jobs(meta).items():
            spec["pictures"].setdefault(k, {"prompt": prompt, "host": True, "pose": True})
    for p in spec["pictures"].values():
        if p.get("prompt"):
            p["prompt"] = _host.expand(p["prompt"], meta)
    real = fetch_real(spec, use_net=use_flow, log=log, cancel=cancel)
    # Flow paints only what has no real source: not pages / clips, not optional photos, not what Commons found
    missing = {k: p for k, p in spec["pictures"].items()
               if p.get("prompt") and not p.get("optional") and not p.get("page") and not p.get("clip") and not flow.have(k)}
    clips = list(meta.get("talk_clips") or [])
    want_loops = talking is True and len(clips) < 3
    if use_flow and (missing or want_loops) and not (cancel and cancel()):
        try:
            with flow.Session(log=log) as fs:
                hosty = {k: p["prompt"] for k, p in missing.items() if p.get("host")}
                plain = {k: p["prompt"] for k, p in missing.items() if not p.get("host")}
                if hosty and meta.get("portrait"):
                    fs.pictures(hosty, refs=_host.refs(meta), cancel=cancel)
                if plain:
                    fs.pictures(plain, refs=None, cancel=cancel)
                if want_loops:
                    jobs = {f"ff_talk_{meta['name'].lower()}_{i}": (
                        f"Photorealistic video, static medium shot on a tripod. The man from the reference pictures {meta['set']}. "
                        f"He looks straight into the camera and talks with lively natural hand gestures. He says: \"{line}\" "
                        "No music, quiet room tone. No text, no subtitles, no logos.")
                        for i, line in enumerate(TALK_LINES[len(clips):3], len(clips) + 1)}
                    made = fs.clips(jobs, refs=_host.refs(meta), cancel=cancel)
                    for i, (_k, pth) in enumerate(sorted(made.items()), 1):
                        dst = Path(meta["dir"]) / f"talk_{len(clips) + i}.mp4"
                        if not dst.exists():
                            dst.write_bytes(Path(pth).read_bytes())
                    clips = [str(p) for p in sorted(Path(meta["dir"]).glob("talk_*.mp4"))]
        except Exception as e:  # noqa: BLE001 - the video never stops for Flow
            log(f"food files: Flow trouble ({type(e).__name__}: {e}); stand-ins are used for what is missing")
    have = {k: flow.have(k) for k in spec["pictures"] if flow.have(k)}
    clips = {k: flow.have(k, "mp4") for k, p in spec["pictures"].items() if p.get("clip") and flow.have(k, "mp4")}
    left = [k for k, p in spec["pictures"].items() if k not in have and k not in clips and not p.get("optional")]
    credits(spec)
    if poses:
        assign_stills(spec, sorted(k for k, p in spec["pictures"].items() if p.get("pose") and k in have))
    if talking is True and clips:
        rnd = random.Random(11)
        for s in spec["shots"]:
            if s["kind"] in ("host", "split", "pip") and not s.get("talk"):
                s["talk"] = clips[rnd.randrange(len(clips))]
                s["talk_at"] = round(rnd.uniform(0, 1.0), 2)
    spec["assets"] = {"pictures": have, "clips": clips, "fallback": meta.get("set_image") or meta.get("portrait") or _stand_in(size)}
    spec["real"] = real
    try:   # Wall Moments (as in War / Aviation): about 10 % of the film on the evidence wall, where numbers and twists pile up
        from . import wall_moments as _wall
        _wall.plan(spec, vo["words"], pct=wall_pct, log=log)
    except Exception as e:  # noqa: BLE001 - the video never stops for the wall
        spec.pop("wall", None)
        log(f"food files: wall moments skipped ({type(e).__name__}: {e})")
    for p in problems:
        log(f"  CSV: {p}")
    if left:
        log(f"food files: {len(left)} picture(s) not made by Flow yet: stand-ins used (Generate again to retry)")
    kinds = {}
    for s in spec["shots"]:
        kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
    return {"spec": spec, "title": title or "", "seconds": spec["duration"], "shots": len(spec["shots"]), "kinds": kinds,
            "pictures": len(have), "missing": len(left), "problems": problems + rep["problems"], "check": rep["stats"],
            "talking": bool(talking and (clips or spec.get("flow_voice")))}


EDGE = 0.6   # a cut this close to a shot's edge moves the edge instead of making a sliver


ZONE_A = (150.0, 0.18)    # the opening: the first 150 s (or 18 %) - most of the clip budget goes here
ZONE_C = 0.60             # the last 40 %: almost no clips
SHARES = (0.6, 0.3, 0.1)  # how the budget is split between the opening, the middle and the end
GRAVE = re.compile(r"\b(died|dead|death|deaths|dying|killed|kill|sick|ill|poison\w*|hospital\w*|cancer|paraly\w*|"
                   r"suicide|life|lives|coffin|agony|kidney|failure|jaw|skull|choked|funeral|murder\w*|damage\w*|harm\w*|hurt|"
                   r"injur\w*|victim\w*|tragic|tragedy|blind\w*|burn\w*|toxic|ruin\w*|suffer\w*|lost|crippl\w*|"
                   r"vomit\w*|seizure\w*|scar\w*|disaster|outbreak|epidemic|grief|mourn\w*|buried|bury)\b", re.I)
TWIST = re.compile(r"(here'?s the|it gets worse|but then|turned out|weird|nobody knew|shock|!)", re.I)


def front_load(rows2, rows, spec, budget, log=print):
    """Spend at most `budget` Flow clips, mostly at the start (owner, 2026-11-22: fewest Flow videos, more at the start,
    less at the end). Opening lines in order, then the shortest punchiest lines of the middle and the end. A host line
    without a clip keeps his voice (copied from his clips); in the second half it becomes a free Flow picture of what the
    line says, earlier it shows a still pose of him."""
    dur = max(1.0, float(spec.get("duration") or 1.0))
    t_of_n = {}
    for s in spec["shots"]:
        n = rows[s["row"]].get("n") if s.get("row") is not None and s["row"] < len(rows) else None
        if n is not None:
            t_of_n.setdefault(n, s["t0"])
    last_t = 0.0                                  # a line whose shot was merged into its neighbour: the time before it
    for r in rows:
        if r.get("n") in t_of_n:
            last_t = t_of_n[r["n"]]
        else:
            t_of_n[r.get("n")] = last_t
    lines = {}                                    # one choice per spoken line (all of its clip pieces together)
    for i, r in enumerate(rows2):
        if r.get("say"):
            lines.setdefault(r.get("n"), []).append(i)
    a_end = max(ZONE_A[0], dur * ZONE_A[1])

    def zone(n):
        t = t_of_n.get(n, 0.0)
        return 0 if t < a_end else (2 if t > dur * ZONE_C else 1)

    quota = [int(round(budget * x)) for x in SHARES]
    quota[0] += budget - sum(quota)
    chosen, spent = set(), 0
    for z in (0, 1, 2):
        cands = [n for n in lines if zone(n) == z]
        cands.sort(key=(lambda n: t_of_n.get(n, 0)) if z == 0 else (lambda n: (len(lines[n]), len(" ".join(
            rows2[i]["line"] for i in lines[n]).split()))))
        room = quota[z] + (budget - spent - sum(quota[z:]))      # what an earlier zone did not use rolls forward
        for n in cands:
            cost = len(lines[n])
            if cost <= room and spent + cost <= budget:
                chosen.add(n)
                room -= cost
                spent += cost
    late = 0
    for n, idx in lines.items():
        if n in chosen:
            continue
        z = zone(n)
        for i in idx:
            rows2[i]["say"] = False
        if z == 2 or (z == 1 and late % 2):       # the second half (and every other middle line): a picture of the words
            first = rows2[idx[0]]
            if not first.get("visual") and first.get("shot") in ("", "host", "split", "pip"):
                for i in idx:
                    rows2[i]["shot"] = "scene"
        if z >= 1:
            late += 1
    log(f"food files: Flow clip budget {budget}: {spent} clip(s) for {len(chosen)} of {len(lines)} host line(s) "
        f"(opening first); the other host lines keep his voice")
    return rows2


def pose_for(line, poses, last=None, near=""):
    """A host pose that fits the line: never laughing on deaths or illness. `near` = the lines around it: a short line
    inside a grave story ("Still, the damage was done.") is grave too, even with no grave word of its own."""
    by = {int(re.search(r"(\d+)$", k).group(1)) - 1: k for k in poses if re.search(r"(\d+)$", k)}
    if not by:
        return poses[0] if poses else None
    l = str(line or "")
    grave = bool(GRAVE.search(l) or GRAVE.search(str(near or "")))
    if grave:
        pref = [1, 7, 0]                 # leaning in serious, arms crossed, plain talking
    elif TWIST.search(l):
        pref = [2, 4, 1]                 # shocked, pointing, leaning in
    elif l.strip().endswith("?"):
        pref = [5, 0, 2]                 # shrug, talking, shocked
    elif len(l.split()) <= 8:
        pref = [3, 4, 0]                 # a short dry line: laughing, pointing, talking
    else:
        pref = [0, 6, 4, 1]              # talking, holding the bottle, pointing, leaning in
    opts = [by[i] for i in pref if i in by]
    if not grave:                          # any other pose before repeating one (never a laugh on a grave line)
        opts += [k for i, k in sorted(by.items()) if k not in opts]
    else:
        opts += [k for i, k in sorted(by.items()) if k not in opts and i != 3]
    opts = opts or list(by.values())
    for k in opts:
        if k != last:
            return k
    return opts[0]


def no_host_stills(spec, meta=None):
    """Owner (2026-11-23, said many times): never a still picture of the host, it looks fake. He is on screen only in his own
    talking clips; every other host shot shows a Flow picture of what the line says."""
    rows = spec.get("rows") or []
    n = 0
    for s in spec["shots"]:
        if s["kind"] in ("host", "split", "pip") and not s.get("talk"):
            r = rows[s["row"]] if s.get("row") is not None and s["row"] < len(rows) else None
            if r is None:
                continue
            s["kind"] = "scene"
            s["pic"] = director.narration_pic(r, spec.setdefault("pictures", {}), meta)
            s.pop("punch", None)
            s.pop("still", None)
            n += 1
    return n


def assign_stills(spec, poses):
    """Host shots without a talking clip show one of the host's pose pictures, matched to the line's mood and never the
    same one twice in a row."""
    if not poses:
        return 0
    rows = spec.get("rows") or []
    last, n = None, 0
    for s in spec["shots"]:
        if s["kind"] in ("host", "split", "pip") and not s.get("talk"):
            r = s.get("row")
            line = rows[r]["line"] if r is not None and r < len(rows) else ""
            near = " ".join(str(rows[j].get("line") or "") for j in ((r - 1, r + 1) if r is not None else ())
                            if 0 <= j < len(rows))
            k = pose_for(line, poses, last, near)
            s["still"] = k
            last = k
            n += 1
    return n


MIN_PIECE = 1.2   # no jump-cut piece of the host shorter than this


def sliver_cuts(spec, cuts):
    """[(row, pause index)] of cuts that would leave a host piece between EDGE and MIN_PIECE long (a flicker)."""
    bad = []
    for k, row_cuts in cuts.items():
        last = {}
        for tc, _skip, n in row_cuts:
            s = next((s for s in spec["shots"] if s.get("row") == k and s.get("talk") and s["t0"] < tc < s["t1"]), None)
            if s is None:
                continue
            if id(s) in last and tc - last[id(s)] < MIN_PIECE:   # two cuts too close inside one shot: a flicker between them
                bad.append((k, n))
            else:
                last[id(s)] = tc
    return bad


def jump_cuts(spec, said, cuts):
    """Pauses squeezed out of a host clip's sound are cut out of its picture too: the host shot splits at each cut, the
    piece after it starts the clip that much later and is framed tighter (a jump cut), so his lips match his words."""
    shots = spec["shots"]
    made = 0
    for k, row_cuts in cuts.items():
        if k not in said:
            continue
        _clip, at, row_t0 = said[k]
        for tc, _skip, *_n in row_cuts:
            i = next((j for j, s in enumerate(shots) if s.get("row") == k and s.get("talk") and s["t0"] < tc < s["t1"]), None)
            if i is None:
                continue
            s = shots[i]
            if tc - s["t0"] < MIN_PIECE and i > 0:     # near the start: the shot before runs on to the cut
                shots[i - 1]["t1"] = round(tc, 3)
                s["t0"] = round(tc, 3)
            elif s["t1"] - tc < MIN_PIECE and i + 1 < len(shots):   # near the end: the next shot starts at the cut
                shots[i + 1]["t0"] = round(tc, 3)
                s["t1"] = round(tc, 3)
            else:
                tail = dict(s, t0=round(tc, 3), punch=not s.get("punch"))
                tail["caps"] = [c for c in s.get("caps", []) if c["t1"] > tc]
                s["caps"] = [c for c in s.get("caps", []) if c["t0"] < tc]
                s["t1"] = round(tc, 3)
                shots.insert(i + 1, tail)
            made += 1
        # every talking shot of the row plays its clip from where the squeezed sound is
        for s in shots:
            if s.get("row") == k and s.get("talk"):
                skipped = sum(c[1] for c in row_cuts if c[0] <= s["t0"] + 1e-3)
                s["talk_at"] = round(max(0.0, at + (s["t0"] - row_t0) + skipped), 3)
    return made


def fetch_real(spec, use_net=True, log=print, cancel=None):
    """Real imagery first (Phase 1): Commons photos, page screenshots, news / TV clips; each kept in the library."""
    got = {"commons": 0, "pages": 0, "clips": 0, "misses": 0}
    if not use_net:
        return got
    for k, p in spec["pictures"].items():
        if cancel and cancel():
            break
        r = None
        if p.get("page"):
            r = sources.page(k, p["page"], log=log)
            got["pages" if r else "misses"] += 1
        elif p.get("clip"):
            r = sources.clip(k, p["clip"], p.get("words", ""), log=log)
            got["clips" if r else "misses"] += 1
        elif p.get("find"):
            r = sources.commons(k, p["find"], log=log)
            got["commons" if r else "misses"] += 1
    log(f"food files: real imagery: {got['commons']} Commons photo(s), {got['pages']} page(s), {got['clips']} clip(s); "
        f"{got['misses']} not found (Flow or the typed card stands in)")
    return got


def credits(spec):
    """Each shot that shows a real photo / page / clip carries its credit line (unless the CSV wrote one)."""
    for s in spec["shots"]:
        if s.get("source"):
            continue
        for key, ext in ((s.get("clip"), "mp4"), (s.get("page"), "png"), (s.get("pic"), "png"),
                         ((s.get("card") or {}).get("pic"), "png")):
            m = sources.meta(key, ext) if key else None
            if m and m.get("credit") and flow.have(key, ext):
                s["source"] = m["credit"]
                break


def _stand_in(size):
    """A plain studio-coloured frame used where a picture is missing (so the video never stops)."""
    p = OUT / "stand_in.png"
    if not p.is_file():
        from foodfiles import cards
        OUT.mkdir(parents=True, exist_ok=True)
        cards.background(size, "dark").convert("RGB").save(p)
    return str(p)


def save(spec, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(spec, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def refresh_assets(spec):
    pics = spec.setdefault("assets", {}).setdefault("pictures", {})
    clips = spec["assets"].setdefault("clips", {})
    for k, p in spec.get("pictures", {}).items():
        if k not in pics and flow.have(k):
            pics[k] = flow.have(k)
        if p.get("clip") and k not in clips and flow.have(k, "mp4"):
            clips[k] = flow.have(k, "mp4")
    credits(spec)
    return spec


def render(spec, out, progress=None, cancel=None, log=print, workers=None):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    say = progress or (lambda f, m="": None)
    spec = refresh_assets(spec)
    with tempfile.TemporaryDirectory() as wd:
        silent, wav = Path(wd) / "picture.mp4", Path(wd) / "mix.wav"
        _render.render_picture(spec, spec["assets"], silent, workers=workers, cancel=cancel,
                               progress=lambda f, m: say(0.02 + 0.9 * f, m))
        if cancel and cancel():
            raise Stopped("Stopped.")
        say(0.93, "mixing the sound")
        rep = _render.mix(spec, wav, sound=spec.get("sound", "music"))
        log(f"food files: mix peak {rep['peak_db']} dBFS")
        say(0.97, "writing the video")
        part = out.with_name(out.stem + ".part.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(wav), "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(part)],
                       check=True, timeout=3600)
        part.replace(out)
    th = spec.get("thumbnail") or {}
    tp = spec["assets"]["pictures"].get(th.get("pic"))
    thumb = None
    try:
        thumb = str(_render.thumbnail(tp, th.get("lines") or [], out.with_suffix(".jpg")))
    except Exception as e:  # noqa: BLE001
        log(f"food files: thumbnail not made ({e})")
    say(1.0, "done")
    return {"video": str(out), "seconds": spec["duration"], "thumbnail": thumb}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Food Files video from a CSV or a script")
    ap.add_argument("source")
    ap.add_argument("--voice")
    ap.add_argument("--edge", default=EDGE_VOICES[0])
    ap.add_argument("--host", default="theo")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--talking", action="store_true", help="3 silent talking loops on host shots")
    ap.add_argument("--flow-voice", action="store_true", help="host lines spoken by his own Flow clips (lips match)")
    ap.add_argument("--stills", action="store_true", help="free test mode: Flow pictures of the host instead of clips")
    ap.add_argument("--clips", type=int, help="Flow voice with at most this many clips, most of them at the start")
    ap.add_argument("--no-flow", action="store_true")
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument("--sound", default="music", choices=("voice", "fx", "music"))
    ap.add_argument("--out")
    ap.add_argument("--wall", type=float, default=10.0, help="Wall Moments share of the film in %% (0 = off)")
    a = ap.parse_args(argv)
    src = Path(a.source)
    is_csv = src.suffix.lower() == ".csv"
    r = plan(csv_path=str(src) if is_csv else None, script=None if is_csv else str(src), voice_file=a.voice, edge_voice=a.edge,
             host=a.host, talking=("budget" if a.clips else "flow") if (a.flow_voice or a.clips) else ("stills" if a.stills else a.talking),
             clip_budget=a.clips or 15, preview=a.preview, sound=a.sound,
             use_flow=not a.no_flow, wall_pct=a.wall)
    print(json.dumps({k: v for k, v in r.items() if k != "spec"}))
    out = a.out or str(OUT / f"{re.sub(r'[^A-Za-z0-9]+', '_', src.stem)}.mp4")
    save(r["spec"], Path(out).with_suffix(".plan.json"))
    if a.plan_only:
        return
    res = render(r["spec"], out, progress=lambda f, m="": print(f"{int(f * 100)}% {m}", flush=True))
    print(json.dumps(res))


if __name__ == "__main__":
    main()
