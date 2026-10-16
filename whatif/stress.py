#!/usr/bin/env python3
"""Stress test for What If: hundreds of broken versions of real shot CSVs through the dry run (whatif/preflight.py).

    python -m whatif.stress ~/Downloads/VideoGenerator/Video_*      (projects with whatif/shots.csv and state/narration_words.json)
    python -m whatif.stress --mutants 600 --seed 3 --out /tmp/whatif_stress

Every base (each real project, plus a built-in black hole journey CSV that uses templates, the mission card and the black hole
scenes) is broken on purpose in the ways an AI-written CSV or a re-recorded voiceover breaks it: wrong delimiters, a missing header,
typos in row types, kinds, sources, scenes, models, templates; broken JSON; words instead of numbers; layers before shots; anchors
nobody says; a transcript that ends early ... Each broken plan goes through plan -> compile -> the page's checks in node. A STOP is
anything that would end Generate. The report groups stops by message and saves one broken CSV per group. Nothing is fetched, nothing
is rendered, no project is changed.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import re
import sys
import tempfile
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---- the built-in base: a short black hole journey (templates, mission card, black hole hero shots) ------------------------------
JOURNEY_SCRIPT = ("What would happen if you flew into a black hole? Our mission is Sagittarius A star, the black hole at the heart of our galaxy. "
                  "Stage one is the approach. From far away it looks calm, but light bends around it and even light falls in if it gets too close. "
                  "Stage two is the photon sphere. Here light itself can orbit, and you would see the back of your own head. "
                  "Down here gravity slows time. One hour for you is ten hours on Earth, and the gap keeps growing as you sink lower. "
                  "Then you cross the edge. Space itself flows inward like a walkway, faster than light, and nothing can turn back. "
                  "If you could ask a black hole one question, what would it be?")
JOURNEY_CSV = """row,shot,vo_anchor,kind,asset,model,texture,label,sub,text,type,id,value_from,value_to,format,anchor,until,hold,why,extra,t,end
plan,,,,,,,WHAT IF YOU FLEW INTO A BLACK HOLE,,,,,,,,,,,,"{""auto"": true}",,
shot,1,What would happen if,hero,,blackhole_disc,,,,,,,,,,,,,,,,
shot,2,Our mission is,hero,,blackhole_lensing,,,,,,,,,,,,,,,,
layer,2,Our mission is,,,,,Sagittarius A*,The black hole at the heart of our galaxy,,template,mission_intro,,,,,,,,,,
layer,2,Our mission is,,,,,Distance to the edge,from Earth,APPROACH,hud,mission,,27000,light-years,,,,,"{""kicker"": ""Mission · Sgr A*""}",,
shot,3,Stage one is,hero,,blackhole_top,,,,,,,,,,,,,,,,
layer,3,Stage one is,,,,,The approach,Stage 1,,template,stage_header,,,,,,,,,,
layer,3,light bends around,,,,,,,,template,light_bends,,,,,,7,,,,
layer,3,light bends around,,,,,Distance to the edge,falling,APPROACH,hud,mission,,208,million km,,,,,,,
layer,3,Stage two is,,,,,,,,template,photon_orbit,,,,,,8,,,,
layer,3,Down here gravity,,,,,,,,template,warp_well,,,,,,4,,,,
layer,3,One hour for,,,,,,,,template,two_clocks_ratio,2,10,,,,7,,,,
shot,4,Then you cross,hero,,blackhole_ring,,,,,,,,,,,,,,,,
layer,4,Space itself flows,,,,,,,,template,river_walkway,,,,,,7,,,,
layer,4,Then you cross,,,,,Distance to the centre,past the edge,INSIDE,hud,mission,,11,million km,,,,,,,
shot,5,If you could,hero,,blackhole_disc,,,,,,,,,,,,,,,,
layer,5,If you could,,,,,If you could ask a black hole,"One question, what would it be?",,template,end_question,,,,,,,,,,
"""


def timed(text: str, t: float = 0.0, step: float = 0.36) -> List[list]:
    out = []
    for w in text.split():
        out.append([w, round(t, 3), round(t + 0.3, 3)])
        t += step + (0.5 if w[-1] in ".?!," else 0.0)
    return out


def load_base(project: Path) -> Optional[Dict[str, Any]]:
    csv_p, words_p = project / "whatif" / "shots.csv", project / "state" / "narration_words.json"
    if not (csv_p.is_file() and words_p.is_file()):
        return None
    w = json.loads(words_p.read_text(encoding="utf-8"))
    words = w.get("words") if isinstance(w, dict) else w
    script_p = project / "script" / "narration.txt"
    script = script_p.read_text(encoding="utf-8") if script_p.is_file() else " ".join(str(x[0] if isinstance(x, (list, tuple)) else x.get("word", "")) for x in words)
    end = words[-1][2] if isinstance(words[-1], (list, tuple)) else words[-1].get("end", 0)
    return {"name": project.name, "csv": csv_p.read_text(encoding="utf-8"), "words": words, "script": script, "duration": float(end) + 1.5}


def journey_base() -> Dict[str, Any]:
    words = timed(JOURNEY_SCRIPT)
    return {"name": "builtin_black_hole_journey", "csv": JOURNEY_CSV, "words": words, "script": JOURNEY_SCRIPT, "duration": words[-1][2] + 1.5}


# ---- the CSV as rows --------------------------------------------------------------------------------------------------------------
def parse(text: str) -> Tuple[List[str], List[List[str]]]:
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    return rows[0], rows[1:]


def unparse(head: List[str], rows: List[List[str]], delim: str = ",") -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delim, lineterminator="\n")
    w.writerow(head)
    w.writerows(rows)
    return buf.getvalue()


class C:
    def __init__(self, text: str):
        self.head, self.rows = parse(text)
        self.ix = {h.strip().lower(): i for i, h in enumerate(self.head)}

    def get(self, r, k):
        i = self.ix.get(k)
        return r[i] if i is not None and i < len(r) else ""

    def put(self, r, k, v):
        i = self.ix.get(k)
        if i is None:
            return
        while len(r) <= i:
            r.append("")
        r[i] = v

    def of(self, kind, **match):
        return [r for r in self.rows if self.get(r, "row").lower() == kind and all(self.get(r, k).lower() == v for k, v in match.items())]

    def text(self, delim=","):
        return unparse(self.head, self.rows, delim)


def pick(rng, rows):
    return rng.choice(rows) if rows else None


# ---- the ways a plan breaks: fn(c, rng) -> description, or (for text mutations) fn(text, rng) -> (text, description) ---------------
def m_kind_alias(c, rng):
    r = pick(rng, c.of("shot"))
    if r is None:
        return None
    v = rng.choice(["photo", "Picture", "clip", "footage", "diagram", "3d", "planet", "scene", "xyz", ""])
    c.put(r, "kind", v); return f"kind {v!r}"

def m_row_typo(c, rng):
    r = pick(rng, c.rows)
    if r is None:
        return None
    v = rng.choice(["shots", "Scene", "LAYER", "graphic", "overlay", "beat", "row", "", "??"])
    c.put(r, "row", v); return f"row {v!r}"

def m_asset_no_source(c, rng):
    r = pick(rng, [x for x in c.of("shot") if c.get(x, "kind") in ("image", "video")])
    if r is None:
        return None
    a = c.get(r, "asset")
    c.put(r, "asset", rng.choice([a.split(":", 1)[-1], "", "google:" + a.split(":", 1)[-1], "nasa:" + a.split(":", 1)[-1], "flow_image:", "AI:a probe"]))
    return "asset source"

def m_hero_unknown(c, rng):
    r = pick(rng, c.of("shot"))
    if r is None:
        return None
    c.put(r, "kind", "hero"); c.put(r, "model", rng.choice(["blackhole", "black_hole_disc", "venera", "wormhole", "", "blackhole_rng"])); return "hero scene"

def m_craft_unknown(c, rng):
    r = pick(rng, c.of("shot"))
    if r is None:
        return None
    c.put(r, "kind", "craft"); c.put(r, "model", rng.choice(["enterprise", "", "voyagr", "starship.glb2"])); return "craft model"

def m_globe_unknown(c, rng):
    r = pick(rng, c.of("shot"))
    if r is None:
        return None
    c.put(r, "kind", "globe"); c.put(r, "texture", rng.choice(["pluto", "", "trappist-1e", "venus.tiff"])); return "globe texture"

def m_anchor_gibberish(c, rng):
    r = pick(rng, c.rows[1:])
    if r is None:
        return None
    c.put(r, "vo_anchor", rng.choice(["zebra crossing blue piano", "", "4.37 light years", "the", "THE THE THE", "über naïve café"])); return "anchor"

def m_anchor_duplicate(c, rng):
    shots = c.of("shot")
    if len(shots) < 3:
        return None
    a, b = rng.sample(shots, 2)
    c.put(b, "vo_anchor", c.get(a, "vo_anchor")); return "duplicate anchor"

def m_extra_broken(c, rng):
    r = pick(rng, c.rows)
    if r is None:
        return None
    c.put(r, "extra", rng.choice(["{auto: true", "{'tint': 'warm'}", "[1,2]", "not json", '{"cam": {"size": "big"}}', '{"slots": "x"}', '{"slots": {"ratio_to": "lots"}}',
                                  '{"x": "left", "y": 0.3}', '{"exit": 5}', "{,}"])); return "extra"

def m_number_units(c, rng):
    r = pick(rng, c.of("layer"))
    if r is None:
        return None
    k = rng.choice(["value_from", "value_to", "hold", "t", "end"])
    c.put(r, k, rng.choice(["4.2 km", "ten", "1,200", "-5", "9999", "nan", "inf", "1e400", "0"])); return f"number {k}"

def m_layer_type(c, rng):
    r = pick(rng, c.of("layer"))
    if r is None:
        return None
    c.put(r, "type", rng.choice(["number", "chart", "Template", "visual", "sparkle", "", "hud ", "annotation"])); return "layer type"

def m_template_id(c, rng):
    r = pick(rng, c.of("layer"))
    if r is None:
        return None
    c.put(r, "type", "template")
    c.put(r, "id", rng.choice(["two_clock_ratio", "warp well", "photonorbit", "made_up_visual", "", "squeeze_object", "deep_time_axis", "eht_pair",
                               "pov_split", "size_ladder", "myth_fact", "quote_card", "map_overlay", "annotated_photo_rings", "before_after"])); return "template id"

def m_template_slots(c, rng):
    r = pick(rng, c.of("layer", type="template"))
    if r is None:
        return None
    k = rng.choice(["label", "sub", "text", "value_from", "value_to", "format"])
    c.put(r, k, rng.choice(["", "lots and lots", "A=1; B", "=;=;=", "x" * 300, "−3", "10^67", "0.5,0.5"])); return f"template slot {k}"

def m_diagram(c, rng):
    r = pick(rng, c.of("layer"))
    if r is None:
        return None
    c.put(r, "type", "diagram")
    c.put(r, "id", rng.choice(["bars", "compare", "logaxis", "pie", "timeline", "", "discmap", "composition"]))
    c.put(r, "text", rng.choice(["A=1", "", "LEFT=1; RIGHT=x", "VENERA=year", "A=1;B=2;C=3", "MOON=1.3 light-seconds"])); return "diagram"

def m_hud(c, rng):
    r = pick(rng, c.of("layer"))
    if r is None:
        return None
    c.put(r, "type", "hud")
    c.put(r, "id", rng.choice(["mission", "survival", "gauge", "dual_clock", "light_clock", "date", "speedometer", ""]))
    c.put(r, "value_to", rng.choice(["", "12", "abc"])); return "hud"

def m_annotate(c, rng):
    r = pick(rng, c.of("layer"))
    if r is None:
        return None
    c.put(r, "type", "annotate"); c.put(r, "extra", rng.choice(["", '{"x": 0.5}', '{"x": 2, "y": -1}'])); return "annotate"

def m_layer_first(c, rng):
    lay = c.of("layer")
    if not lay:
        return None
    r = rng.choice(lay); c.rows.remove(r); c.rows.insert(0, r); return "layer before shots"

def m_drop_plan(c, rng):
    for r in c.of("plan"):
        c.rows.remove(r)
    return "no plan row"

def m_only_layers(c, rng):
    c.rows = [r for r in c.rows if c.get(r, "row").lower() != "shot"]; return "no shots"

def m_times(c, rng):
    r = pick(rng, c.rows)
    if r is None:
        return None
    c.put(r, "t", rng.choice(["-3", "99999", "0", "5"])); c.put(r, "end", rng.choice(["", "1", "-1", "100000"])); return "times"

def m_blank_cells(c, rng):
    for _ in range(rng.randint(1, 8)):
        r = pick(rng, c.rows)
        if r is not None and r:
            r[rng.randrange(len(r))] = ""
    return "blank cells"

def m_dupe_rows(c, rng):
    for _ in range(rng.randint(1, 5)):
        r = pick(rng, c.rows)
        if r is not None:
            c.rows.insert(c.rows.index(r), list(r))
    return "duplicate rows"

def m_shuffle_columns(c, rng):
    order = list(range(len(c.head)))
    rng.shuffle(order)
    c.head = [c.head[i] for i in order]
    c.rows = [[(r[i] if i < len(r) else "") for i in order] for r in c.rows]
    c.ix = {h.strip().lower(): i for i, h in enumerate(c.head)}
    return "columns shuffled"

def m_hold_huge(c, rng):
    r = pick(rng, c.of("layer"))
    if r is None:
        return None
    c.put(r, "hold", rng.choice(["9999", "0", "0.01", "-4"])); return "hold"

def m_junk_text(c, rng):
    r = pick(rng, c.rows)
    if r is None:
        return None
    c.put(r, rng.choice(["label", "sub", "text", "why"]), rng.choice(["😀🚀", "\x00\x01", "{label}", "{{", "@@@", "<script>", "=1+1", "'; DROP"])); return "junk text"

ROW_MUTATIONS: List[Callable] = [m_kind_alias, m_row_typo, m_asset_no_source, m_hero_unknown, m_craft_unknown, m_globe_unknown, m_anchor_gibberish,
                                 m_anchor_duplicate, m_extra_broken, m_number_units, m_layer_type, m_template_id, m_template_slots, m_diagram, m_hud,
                                 m_annotate, m_layer_first, m_drop_plan, m_only_layers, m_times, m_blank_cells, m_dupe_rows, m_shuffle_columns,
                                 m_hold_huge, m_junk_text]


def t_semicolons(text, rng):
    c = C(text); return c.text(";"), "semicolons"

def t_no_header(text, rng):
    return text.split("\n", 1)[1] if "\n" in text else text, "no header"

def t_bom_crlf(text, rng):
    return "﻿" + text.replace("\n", "\r\n"), "BOM + CRLF"

def t_truncate(text, rng):
    return text[: rng.randint(len(text) // 3, len(text))], "truncated"

def t_empty(text, rng):
    return rng.choice(["", "\n\n", "row,shot\n", "hello world"]), "empty / not a CSV"

TEXT_MUTATIONS = [t_semicolons, t_no_header, t_bom_crlf, t_truncate, t_empty]


def mutate(base: Dict[str, Any], seed: int) -> Tuple[str, List[list], List[str]]:
    rng = random.Random(seed)
    text, words, what = base["csv"], [list(w) if isinstance(w, (list, tuple)) else w for w in base["words"]], []
    c = C(text)
    for _ in range(rng.randint(1, 4)):
        d = rng.choice(ROW_MUTATIONS)(c, rng)
        if d:
            what.append(d)
    text = c.text()
    if rng.random() < 0.25:
        text, d = rng.choice(TEXT_MUTATIONS)(text, rng)
        what.append(d)
    if rng.random() < 0.12:                            # a transcript that ended early (StarMap #012)
        words = words[: max(5, int(len(words) * rng.uniform(0.2, 0.8)))]
        what.append("transcript ends early")
    return text, words, what


def run_one(job: Tuple[Dict[str, Any], int, str]) -> Dict[str, Any]:
    base, seed, out_dir = job
    from whatif import compile as wc
    from whatif.app_integration import plan_from

    text, words, what = mutate(base, seed)
    res: Dict[str, Any] = {"seed": seed, "base": base["name"], "what": what, "stop": None, "notes": 0}
    try:
        if base.get("strict"):            # --baseline: the reader as it was before whatif/heal.py (every bad row stops the plan)
            from whatif import planner
            from whatif.shot_csv import is_whatif_csv, layers_from_rows, read_shots

            if not is_whatif_csv(text):
                raise ValueError("not a What If CSV")
            shots, items, info, _ = read_shots(text, words, base["duration"])
            layers, plates = layers_from_rows(items, shots, words, base["script"])
            p = planner.plan(words, base["script"], base["duration"], "", shots=shots, extra_layers=layers, extra_plates=plates)
        else:
            p = plan_from(words, base["script"], base["duration"], "", text)
        res["notes"] = len(p.notes)
    except Exception as exc:          # noqa: BLE001
        res["stop"] = f"plan: {type(exc).__name__}: {str(exc)[:160]}"
        res["csv"] = text
        return res
    try:
        spec = wc.compile_spec(p, media_dir=None)
    except Exception as exc:          # noqa: BLE001
        res["stop"] = f"compile: {type(exc).__name__}: {str(exc)[:160]}"
        res["csv"] = text
        return res
    sp = Path(out_dir) / f"{base['name'][:40]}_{seed}.json"
    sp.write_text(json.dumps(spec), encoding="utf-8")
    res["spec"] = str(sp)
    res["csv"] = text
    return res


def group(msg: str) -> str:
    return re.sub(r"\d+(\.\d+)?", "N", re.sub(r"'[^']*'", "'…'", msg))[:140]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("projects", nargs="*", type=Path)
    ap.add_argument("--mutants", type=int, default=300, help="broken plans per base")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", type=Path, default=None, help="where the report and one broken CSV per stop group go")
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--baseline", action="store_true", help="measure the strict reader (before the repairs) for comparison")
    a = ap.parse_args(argv)
    bases = [b for b in (load_base(p) for p in a.projects) if b] + [journey_base()]
    for b in bases:
        b["strict"] = a.baseline
    out = a.out or Path(tempfile.mkdtemp(prefix="whatif_stress_"))
    out.mkdir(parents=True, exist_ok=True)
    specs = out / "specs"
    specs.mkdir(exist_ok=True)
    for f in specs.glob("*.json"):
        f.unlink()
    print(f"bases: {', '.join(b['name'] for b in bases)}; {a.mutants} broken plans each")
    jobs = [(b, a.seed * 100000 + i, str(specs)) for b in bases for i in range(a.mutants)]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=a.workers or None) as ex:
        results = list(ex.map(run_one, jobs, chunksize=8))
    print(f"planned and compiled in {time.time() - t0:.0f} s; checking the renderer…")
    from whatif.preflight import check_specs

    paths = [Path(r["spec"]) for r in results if r.get("spec")]
    checked: Dict[str, Dict[str, Any]] = {}
    for i in range(0, len(paths), 200):
        checked.update(check_specs(paths[i:i + 200]))
    repairs = Counter()
    for r in results:
        if r.get("spec"):
            got = checked.get(r["spec"], {})
            for m in got.get("repairs", []):
                repairs[group(m)] += 1
            if got.get("fatal"):
                r["stop"] = f"renderer: {got['fatal'][:200]}"
    stops = [r for r in results if r["stop"]]
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in stops:
        groups[group(r["stop"])].append(r)
    lines = [f"What If stress test: {len(results)} broken plans from {len(bases)} base(s), {len(stops)} stopped "
             f"({100 * len(stops) / max(1, len(results)):.1f} %)"]
    for g, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        ex_path = out / f"stop_{len(lines):02d}.csv"
        ex_path.write_text(rs[0]["csv"], encoding="utf-8")
        lines.append(f"  {len(rs):4d}  {g}   e.g. seed {rs[0]['seed']} ({', '.join(rs[0]['what'])}) -> {ex_path.name}")
    lines.append("renderer repairs (never stops), most common:")
    lines += [f"  {n:4d}  {m}" for m, n in repairs.most_common(8)]
    report = "\n".join(lines)
    (out / "report.txt").write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"report: {out / 'report.txt'}")
    return 1 if stops else 0


if __name__ == "__main__":
    sys.exit(main())
