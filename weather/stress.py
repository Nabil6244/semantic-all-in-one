#!/usr/bin/env python3
"""Stress test for Weather: hundreds of broken versions of real projects through the dry run (weather/preflight.py).

    python -m weather.stress ~/Downloads/VideoGenerator/Video_*_weather* --mutants 300
    python -m weather.stress PROJECT --words PROJECT=transcript.json     (a project with no saved transcript)

Each project is cut into slices of a few beats (the matching cost grows with the narration, so a slice checks in a second or two),
then every slice is broken on purpose in the ways an AI-written plan, a re-recorded voiceover or old data break it (wrong words,
unknown places, bad modes, broken JSON, missing rows, stale data ...). Every slice goes through every stage Generate runs before
the render. The report groups the stops by what they say, with one broken plan per group saved for reproducing it.
Nothing is fetched, nothing is rendered, the projects themselves are never changed (each slice is a copy in a temp folder)."""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import re
import shutil
import sys
import tempfile
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path


FAKE_PLACES = ["Southern Plainsland", "Upper Zorbia", "Coastal Nowhere Region", "North Fakeshire County", "Zzyzx Basin"]
FAKE_WORDS = "zebra crossing blue piano"


# ---- the CSV as rows ---------------------------------------------------------------------------------------------------------

def read_rows(text: str):
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    return rows[0], [r for r in rows[1:] if any(c.strip() for c in r)]


def write_rows(head, rows) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(head)
    w.writerows(rows)
    return buf.getvalue()


class Csv:
    def __init__(self, text: str):
        self.head, self.rows = read_rows(text)
        self.col = {h.strip().lower(): i for i, h in enumerate(self.head)}

    def get(self, r, name):
        i = self.col.get(name)
        return r[i] if i is not None and i < len(r) else ""

    def put(self, r, name, value):
        i = self.col.get(name)
        if i is None:
            return
        while len(r) <= i:
            r.append("")
        r[i] = value

    def kind(self, r):
        return self.get(r, "row").strip().lower()

    def of(self, *kinds):
        return [r for r in self.rows if self.kind(r) in kinds]

    def text(self):
        return write_rows(self.head, self.rows)


# ---- the ways a plan breaks --------------------------------------------------------------------------------------------------
# beats mutations: fn(c: Csv, rng) -> optional description; text mutations: fn(text, rng) -> text

def _pick(rng, rows):
    return rng.choice(rows) if rows else None


def m_anchor_unspoken(c, rng):
    r = _pick(rng, c.of("beat", "layer", "camera", "clip"))
    if r: c.put(r, "vo_anchor", FAKE_WORDS)


def m_anchor_swap(c, rng):
    b = c.of("beat")
    if len(b) > 2:
        x, y = rng.sample(b[1:], 2)
        ax, ay = c.get(x, "vo_anchor"), c.get(y, "vo_anchor")
        c.put(x, "vo_anchor", ay); c.put(y, "vo_anchor", ax)


def m_anchor_partial(c, rng):
    r = _pick(rng, c.of("beat", "layer"))
    if r:
        words = c.get(r, "vo_anchor").split()
        c.put(r, "vo_anchor", " ".join(words[1:] + ["indeed"]) if len(words) > 1 else "indeed " + " ".join(words))


def m_anchor_one_common_word(c, rng):
    r = _pick(rng, c.of("beat")[1:])
    if r: c.put(r, "vo_anchor", "the")


def m_anchor_empty(c, rng):
    r = _pick(rng, c.of("beat")[1:])
    if r: c.put(r, "vo_anchor", "")


def m_curly(c, rng):
    for r in c.rows:
        for k in ("vo_anchor", "text", "label"):
            c.put(r, k, c.get(r, k).replace("'", "’").replace(" - ", " — ").replace('"', "“"))


def m_place_unknown(c, rng):
    r = _pick(rng, [r for r in c.of("beat", "camera", "layer") if c.get(r, "place")])
    if r: c.put(r, "place", rng.choice(FAKE_PLACES))


def m_place_first_unknown(c, rng):
    b = c.of("beat")
    if b: c.put(b[0], "place", rng.choice(FAKE_PLACES))


def m_places_all_unknown(c, rng):
    for r in c.of("beat", "camera"):
        if c.get(r, "place"):
            c.put(r, "place", rng.choice(FAKE_PLACES))


def m_mode_bad(c, rng):
    r = _pick(rng, c.of("beat"))
    if r: c.put(r, "mode", rng.choice(["mapp", "Map", " map ", "", "video", "MAP_FOOTAGE", "footage"]))


def m_frame_bad(c, rng):
    r = _pick(rng, c.of("beat", "camera"))
    if r: c.put(r, "frame", rng.choice(["city", "Region", "national", "huge", "local "]))


def m_move_bad(c, rng):
    r = _pick(rng, c.of("beat", "camera"))
    if r: c.put(r, "type", rng.choice(["zoom", "fly", "pan", "PUSH_IN", "push in"]))


def m_dup_beat_id(c, rng):
    b = c.of("beat")
    if len(b) > 2:
        i = rng.randrange(1, len(b))
        old, new = c.get(b[i], "beat"), c.get(b[i - 1], "beat")
        for r in c.rows:
            if c.get(r, "beat") == old:
                c.put(r, "beat", new)


def m_drop_beat_row(c, rng):
    b = c.of("beat")
    if len(b) > 2:
        c.rows.remove(rng.choice(b[1:]))


def m_drop_first_beat_row(c, rng):
    b = c.of("beat")
    if len(b) > 1:
        c.rows.remove(b[0])


def m_empty_text(c, rng):
    r = _pick(rng, c.of("beat"))
    if r: c.put(r, "text", "")


def m_layer_type_bad(c, rng):
    r = _pick(rng, c.of("layer"))
    if r: c.put(r, "type", rng.choice(["title", "bolt", "", "HUD_TITLE", "lower_third"]))


def m_layer_dup_id(c, rng):
    ls = [r for r in c.of("layer") if c.get(r, "id")]
    if len(ls) > 1:
        a, b = rng.sample(ls, 2)
        c.put(b, "id", c.get(a, "id"))


def m_extra_bad(c, rng):
    r = _pick(rng, c.rows)
    if r: c.put(r, "extra", rng.choice(["{bad json", "[1,2]", '{"foo": 1}', "{'text': 'x'}", "null"]))


def m_numbers_text(c, rng):
    r = _pick(rng, c.rows)
    if r: c.put(r, rng.choice(["hold", "dur", "t", "start", "value_to"]), rng.choice(["2s", "five", "abc", "-3", "1.2 million", "1e9"]))


def m_until_bad(c, rng):
    r = _pick(rng, c.of("layer"))
    if r: c.put(r, "until", rng.choice(["forever", "after", "-3", "99999", "until the end", "END"]))


def _add_clip(c, rng, asset):
    b = _pick(rng, c.of("beat"))
    if b is None:
        return
    row = [""] * len(c.head)
    c.put(row, "beat", c.get(b, "beat")); c.put(row, "row", "clip"); c.put(row, "asset", asset); c.put(row, "dur", "4")
    c.rows.insert(c.rows.index(b) + 1, row)


def m_clip_flow(c, rng): _add_clip(c, rng, "flow_video:a storm over a city")
def m_clip_youtube(c, rng): _add_clip(c, rng, "youtube_video:hurricane landfall news")
def m_clip_missing_file(c, rng): _add_clip(c, rng, "media/nope_does_not_exist.mp4")
def m_clip_bad_source(c, rng): _add_clip(c, rng, rng.choice(["stok_video:rain", "video:rain", "https://example.com/a.mp4", ""]))


def m_footage_no_clips(c, rng):
    r = _pick(rng, c.of("beat")[1:])
    if r is None:
        return
    c.put(r, "mode", "footage")
    bid = c.get(r, "beat")
    c.rows = [x for x in c.rows if not (c.kind(x) == "clip" and c.get(x, "beat") == bid)]


def m_orphan_first(c, rng):
    r = _pick(rng, c.of("layer", "camera", "clip"))
    if r:
        c.rows.remove(r); c.rows.insert(0, r)


def m_move_child(c, rng):
    r = _pick(rng, c.of("layer"))
    if r:
        c.rows.remove(r); c.rows.insert(rng.randrange(len(c.rows) + 1), r)


def m_row_short(c, rng):
    r = _pick(rng, c.rows)
    if r: del r[rng.randrange(3, max(4, len(r))):]


def m_row_long(c, rng):
    r = _pick(rng, c.rows)
    if r: r.extend(["x", "y"])


def m_unknown_column(c, rng):
    c.head.append("notes")
    for r in c.rows:
        r.append("note")


def m_stat_text(c, rng):
    r = _pick(rng, [r for r in c.of("layer") if c.get(r, "type") == "stat"]) or _pick(rng, c.of("layer"))
    if r: c.put(r, "value_to", rng.choice(["1.2 million", "about 40", "$3B", "40%"]))


BEAT_MUTATIONS = [m_anchor_unspoken, m_anchor_swap, m_anchor_partial, m_anchor_one_common_word, m_anchor_empty, m_curly,
                  m_place_unknown, m_place_first_unknown, m_places_all_unknown, m_mode_bad, m_frame_bad, m_move_bad, m_dup_beat_id,
                  m_drop_beat_row, m_drop_first_beat_row, m_empty_text, m_layer_type_bad, m_layer_dup_id, m_extra_bad, m_numbers_text,
                  m_until_bad, m_clip_flow, m_clip_youtube, m_clip_missing_file, m_clip_bad_source, m_footage_no_clips, m_orphan_first,
                  m_move_child, m_row_short, m_row_long, m_unknown_column, m_stat_text]


def l_type_bad(c, rng):
    r = _pick(rng, c.rows)
    if r: c.put(r, "type", rng.choice(["Satellite", "radar_loop", "bolt", "", "TEMP"]))


def l_source_bad(c, rng):
    r = _pick(rng, c.rows)
    if r: c.put(r, "data_source", rng.choice(["nws:forcast@Nowhere,ZZ", "garbage", "nws:alerts@", "spc:reports@2099-01-01#tornado", "gibs:@x"]))


def l_place_unknown(c, rng):
    r = _pick(rng, c.rows)
    if r: c.put(r, "place", rng.choice(["Girvin, TX", "Nowhere, ZZ", "Fort Stockton", "31.0", "Texas"]))


def l_dup_id(c, rng):
    if len(c.rows) > 1:
        a, b = rng.sample(c.rows, 2)
        c.put(b, "id", c.get(a, "id"))


def l_beat_missing(c, rng):
    r = _pick(rng, c.rows)
    if r: c.put(r, "beat", "b999")


def l_extra_bad(c, rng):
    r = _pick(rng, c.rows)
    if r: c.put(r, "extra", rng.choice(["{bad", '{"colour": "red"}', "[]", "{'text': 'x'}"]))


def l_until_bad(c, rng):
    r = _pick(rng, c.rows)
    if r: c.put(r, rng.choice(["until", "hold", "t"]), rng.choice(["forever", "-2", "abc", "99999"]))


def l_anchor_unspoken(c, rng):
    r = _pick(rng, c.rows)
    if r: c.put(r, "vo_anchor", FAKE_WORDS)


LAYER_MUTATIONS = [l_type_bad, l_source_bad, l_place_unknown, l_dup_id, l_beat_missing, l_extra_bad, l_until_bad, l_anchor_unspoken]


def t_bom_crlf(text, rng): return "﻿" + text.replace("\n", "\r\n")
def t_blank_lines(text, rng): return text.replace("\n", "\n\n", 3)
def t_header_case(text, rng):
    first, _, rest = text.partition("\n")
    return first.upper().replace(",", ", ") + "\n" + rest


TEXT_MUTATIONS = [t_bom_crlf, t_blank_lines, t_header_case]
# whole-project mutations (applied to the slice's inputs): stale data, a noisy transcript, a slightly different recording length
GLOBAL_MUTATIONS = ["stale_data", "words_noisy", "duration_short", "duration_long", "no_layers_file", "empty_layers_file"]


# ---- slices of a real project ------------------------------------------------------------------------------------------------

def load_project(path: Path, words_file=None):
    w = path / "weather"
    wf = Path(words_file) if words_file else w / "_work" / "voiceover_words.json"
    data = json.loads(wf.read_text(encoding="utf-8"))
    words = [tuple(x) for x in (data["words"] if isinstance(data, dict) else data)]
    return {"name": path.name, "dir": w, "words": words,
            "style": json.loads((w / "weather.json").read_text(encoding="utf-8")).get("edit_style", "classic")}


def make_slices(proj, size: int):
    """Groups of `size` beats, each with its own piece of the narration (times shifted to start at 0)."""
    from weather import generate as wg

    plan = wg.plan_layers(wg.WeatherProject(proj["dir"]), proj["words"], proj["words"][-1][2] + 1.0, notes=[], edit_style=proj["style"])[0]
    starts = {}
    for b in plan.beats:   # the beats as written (cutaway beats added by the edit have ids with a suffix)
        starts.setdefault(b.id.split("~")[0], b.start)
    bc = Csv((proj["dir"] / "beats.csv").read_text(encoding="utf-8"))
    ids = list(dict.fromkeys(bc.get(r, "beat") for r in bc.of("beat")))
    ids = [i for i in ids if i in starts]
    out = []
    for k in range(0, len(ids), size):
        group = ids[k:k + size]
        t0 = starts[group[0]]
        t1 = starts[ids[k + size]] if k + size < len(ids) else proj["words"][-1][2] + 1.0
        out.append({"beats": set(group), "t0": t0, "t1": t1})
    return out


def slice_inputs(proj, sl):
    bc = Csv((proj["dir"] / "beats.csv").read_text(encoding="utf-8"))
    bc.rows = [r for r in bc.rows if bc.get(r, "beat") in sl["beats"]]
    layers = None
    lp = proj["dir"] / "weather_layers.csv"
    if lp.is_file():
        lc = Csv(lp.read_text(encoding="utf-8"))
        lc.rows = [r for r in lc.rows if lc.get(r, "beat") in sl["beats"]]
        layers = lc.text()
    words = [(w, round(a - sl["t0"], 3), round(b - sl["t0"], 3)) for w, a, b in proj["words"] if sl["t0"] - 0.01 <= a < sl["t1"]]
    return bc.text(), layers, words, round(sl["t1"] - sl["t0"], 3)


def mutate(beats, layers, words, duration, rng):
    applied = []
    now = None
    for _ in range(rng.choice([1, 1, 2, 3])):
        pick = rng.random()
        if pick < 0.6:
            f = rng.choice(BEAT_MUTATIONS)
            c = Csv(beats); f(c, rng); beats = c.text()
        elif pick < 0.8 and layers:
            f = rng.choice(LAYER_MUTATIONS)
            c = Csv(layers); f(c, rng); layers = c.text()
        elif pick < 0.9:
            f = rng.choice(TEXT_MUTATIONS)
            beats = f(beats, rng)
        else:
            g = rng.choice(GLOBAL_MUTATIONS)
            applied.append(g)
            if g == "stale_data":
                now = datetime.now(timezone.utc) + timedelta(days=40)
            elif g == "words_noisy":
                words = [(w if rng.random() > 0.05 else w[::-1], a, b) for w, a, b in words if rng.random() > 0.08]
            elif g == "duration_short":
                duration = max(1.0, duration - 3.0)
            elif g == "duration_long":
                duration += 5.0
            elif g == "no_layers_file":
                layers = None
            elif g == "empty_layers_file":
                layers = "beat,vo_anchor,t,id,type,place,data_source,hold,until,extra\n"
            continue
        applied.append(f.__name__)
    return beats, layers, words, duration, now, applied


_FAST = False


def _fast_places() -> None:
    """Test speed only: map_scene's place lookup scans every place on each call (2-5 s); the same name always gives the same answer,
    so this worker remembers them. The answers are the real ones."""
    global _FAST
    if _FAST:
        return
    _FAST = True
    import map_scene.places as mp

    real, memo = mp.find_place, {}

    def find_place(name, *, parent=None, ai=None):
        if parent is not None or ai is not None:
            return real(name, parent=parent, ai=ai)
        if name not in memo:
            try:
                memo[name] = ("ok", real(name))
            except Exception as exc:   # PlaceNotFound and friends: raised again each time, as the real one does
                memo[name] = ("err", exc)
        kind, val = memo[name]
        if kind == "err":
            raise val
        return val

    mp.find_place = find_place
    anchor, cache = mp.Place.anchor, {}
    keep = []   # the places stay alive, so an id is never reused

    def cached_anchor(self):
        if id(self) not in cache:
            keep.append(self)
            cache[id(self)] = anchor(self)
        return cache[id(self)]

    mp.Place.anchor = cached_anchor
    for mod in list(sys.modules.values()):   # modules that imported the name directly
        if getattr(mod, "find_place", None) is real:
            mod.find_place = find_place


def run_one(job):
    """One broken slice through the dry run, in its own temp copy of the project folder."""
    _fast_places()
    from weather import generate as wg
    from weather.preflight import preflight

    with tempfile.TemporaryDirectory(prefix="wx_stress_") as tmp:
        d = Path(tmp) / "weather"
        d.mkdir()
        for name in ("resolved.json", "weather.json"):
            shutil.copy2(Path(job["src"]) / name, d / name)
        if (Path(job["src"]) / "intel").is_dir() and job.get("intel", True):
            shutil.copytree(Path(job["src"]) / "intel", d / "intel")
        (d / "beats.csv").write_text(job["beats"], encoding="utf-8")
        if job["layers"] is not None:
            (d / "weather_layers.csv").write_text(job["layers"], encoding="utf-8")
        now = datetime.fromisoformat(job["now"]) if job["now"] else None
        try:
            rep = preflight(wg.WeatherProject(d), job["words"], job["duration"], edit_style=job["style"], now=now, engine=job["engine"])
            return {"stops": rep.stops, "id": job["id"]}
        except BaseException as exc:   # the dry run itself must never raise: report it as a stop of its own
            return {"stops": [("CRASH", f"{type(exc).__name__}: {exc}")], "id": job["id"]}


def signature(stage: str, msg: str) -> str:
    s = re.sub(r"'[^']*'|\"[^\"]*\"", "'…'", msg)
    s = re.sub(r"\d+(\.\d+)?", "N", s)
    s = re.sub(r"\b(b|w|s)N\w*", "ID", s)
    return f"[{stage}] {s[:160]}"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("projects", nargs="+")
    ap.add_argument("--mutants", type=int, default=200)
    ap.add_argument("--slice", type=int, default=6)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--no-engine", action="store_true")
    ap.add_argument("--style", choices=["classic", "teamplate"], help="check every project in this editing style")
    ap.add_argument("--words", action="append", default=[], help="PROJECT_NAME=transcript.json")
    ap.add_argument("--out", default=str(Path(tempfile.gettempdir()) / "weather_stress"))
    a = ap.parse_args(argv)
    _fast_places()
    wmap = dict(x.split("=", 1) for x in a.words)
    rng = random.Random(a.seed)
    jobs = []
    for p in a.projects:
        p = Path(p).expanduser()
        try:
            proj = load_project(p, wmap.get(p.name))
            if a.style:
                proj["style"] = a.style
        except (OSError, KeyError, ValueError) as exc:
            print(f"skip {p.name}: {exc}")
            continue
        slices = make_slices(proj, a.slice)
        print(f"{proj['name']}: {len(slices)} slices ({proj['style']})")
        for si, sl in enumerate(slices):
            beats, layers, words, dur = slice_inputs(proj, sl)
            base = {"src": str(proj["dir"]), "style": proj["style"], "engine": not a.no_engine}
            jobs.append({**base, "id": f"{proj['name']}#s{si}#clean", "beats": beats, "layers": layers, "words": words, "duration": dur,
                         "now": None, "applied": ["(none)"]})
        per = max(1, a.mutants // max(1, len(a.projects)))
        for k in range(per):
            si = rng.randrange(len(slices))
            beats, layers, words, dur = slice_inputs(proj, slices[si])
            beats, layers, words, dur, now, applied = mutate(beats, layers, words, dur, rng)
            jobs.append({"src": str(proj["dir"]), "style": proj["style"], "engine": not a.no_engine, "id": f"{proj['name']}#s{si}#m{k}",
                         "beats": beats, "layers": layers, "words": words, "duration": dur, "now": now.isoformat() if now else None,
                         "applied": applied})
    t = time.time()
    by_id = {j["id"]: j for j in jobs}
    groups = defaultdict(list)
    failed = 0
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for res in ex.map(run_one, jobs):
            if res["stops"]:
                failed += 1
                for stage, msg in res["stops"]:
                    groups[signature(stage, msg)].append((res["id"], msg))
    out = Path(a.out)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    print(f"\n{len(jobs)} plans ({sum(1 for j in jobs if j['id'].endswith('#clean'))} clean slices) in {time.time() - t:.0f}s: "
          f"{failed} would stop Generate, {len(groups)} different reasons\n")
    for n, (sig, hits) in enumerate(sorted(groups.items(), key=lambda kv: -len(kv[1])), start=1):
        jid, msg = hits[0]
        j = by_id[jid]
        case = out / f"case{n:02d}"
        case.mkdir()
        (case / "beats.csv").write_text(j["beats"], encoding="utf-8")
        if j["layers"] is not None:
            (case / "weather_layers.csv").write_text(j["layers"], encoding="utf-8")
        (case / "case.json").write_text(json.dumps({k: j[k] for k in ("id", "src", "style", "duration", "now", "applied")}
                                                   | {"words": j["words"], "message": msg}, indent=1), encoding="utf-8")
        print(f"{n:2d}. x{len(hits):3d}  {sig}\n        e.g. {jid}  (broken by: {', '.join(j['applied'])})\n        {msg[:220]}")
    print(f"\ncases saved in {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
