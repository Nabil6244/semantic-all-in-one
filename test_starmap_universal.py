"""Universal StarMap: datasets are found, not selected; every beat is resolved deterministically (CSV + local datasets + the
project's reference date, no network, no AI) into its datasets, qualified ids and temporal context -- historical, current,
planned, projected or hypothetical, with its geometry basis kept separate -- and one video may mix them all.

The datasets: the six production mission packs plus the architectural fixtures in test_fixtures/starmap_datasets (Voyager 1/2,
New Horizons, Pioneers, Mars rovers and orbiters, Juno, Galileo, Europa Clipper, JUICE, Cassini, Parker, Solar Orbiter, SOHO,
asteroid and comet missions, ISS, Hubble, JWST, Tiangong, Landsat 9, LRO, SLIM, Artemis III, a projected cargo flight, a
hypothetical Moon base and a hypothetical crewed Mars flight)."""

import csv
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from starmap import Catalog, CatalogError, DatasetIndex, check_csv, compile_plan, read_plan, resolve, strip_private
from starmap.beat_csv import COLUMNS
from starmap.catalog import PACKS, base_body_ids
from starmap.temporal import parse_iso

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "test_fixtures" / "starmap_datasets"
NOW = "2026-10-08"
SIX = ["apollo8", "apollo11", "apollo13", "artemis1", "chandrayaan3", "change4"]


def library(*extra):
    return DatasetIndex([PACKS, FIXTURES, *extra], base_body_ids=base_body_ids())


def csv_of(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(COLUMNS), lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: (json.dumps(v) if k == "extra" and isinstance(v, dict) else v) for k, v in r.items()})
    return buf.getvalue()


def beat(b, start, mode, place="", frame="", date="", extra=None, text=""):
    r = dict(beat=b, row="beat", start=str(start), mode=mode, place=place, frame=frame, date=date, text=text or f"beat {b}")
    if extra:
        r["extra"] = extra
    return r


def layer(b, t, typ, **k):
    return dict(beat=b, row="layer", t=str(t), type=typ, **k)


def clip(b, asset="file:x.jpg"):
    return dict(beat=b, row="clip", asset=asset)


# a documentary that goes 1969 -> today -> 2027 (planned) -> 2050 (hypothetical), across many kinds of spacecraft
MIXED = [
    dict(beat="plan", row="plan", label="ACROSS TIME", date=NOW),
    beat("b1", 0, "map", "tranquility base", "surface", "apollo11.landing-00:05"),
    layer("b1", 0.5, "craft", id="apollo11.lm"), layer("b1", 0.5, "path", id="apollo11.descent"),
    beat("b2", 8, "map", "sun", "heliosphere", "now"),
    layer("b2", 8.5, "craft", id="voyager1.voyager1"), layer("b2", 8.5, "path", id="voyager1.outbound"),
    beat("b3", 14, "map", "sun", "heliosphere", "now", extra={"mission": "voyager2"}),
    layer("b3", 14.5, "craft", id="voyager2"),
    beat("b4", 20, "map", "jupiter", "system", "juno.observed_pass"),
    layer("b4", 20.5, "craft", id="juno.juno"), layer("b4", 20.5, "orbit", id="juno.polar_orbit"),
    beat("b5", 26, "map", "sun", "inner", "parker_solar_probe.closest_approach"),
    layer("b5", 26.5, "craft", id="parker"), layer("b5", 26.5, "path", id="parker_solar_probe.solar_passes"),
    beat("b6", 32, "map", "earth", "system", "now"),
    layer("b6", 32.5, "craft", id="jwst.jwst"),
    beat("b7", 38, "map", "perseverance.jezero landing site", "surface", "perseverance.landing"),
    layer("b7", 38.5, "craft", id="perseverance.lander"),
    beat("b8", 44, "map", "bennu", "body", "osiris_rex.sample_collection"),
    layer("b8", 44.5, "marker", place="bennu@0,0", label="SAMPLE SITE"),
    beat("b9", 50, "footage"), clip("b9"),
    beat("b10", 56, "map", "earth+moon", "system", "artemis3.landing-24:00"),
    layer("b10", 56.5, "craft", id="artemis3.orion"), layer("b10", 56.5, "path", id="artemis3.outbound"),
    beat("b11", 64, "map", "moon_base_2050.shackleton base", "surface", "moon_base_2050.founding"),
    layer("b11", 64.5, "craft", id="moon_base_2050.supply_ship"), layer("b11", 64.5, "path", id="moon_base_2050.supply_route"),
    beat("b12", 72, "map", "mars", "body", "2060-01-01T00:00:00Z", extra={"status": "hypothetical"}),
]
MEDIA = {"file:x.jpg": {"file": "x.jpg"}}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.idx = library()
        cls.cat = Catalog(index=cls.idx)

    def plan(self, rows, duration=80.0):
        return read_plan(csv_of(rows), duration=duration)

    def resolved(self, rows, now=None, duration=80.0):
        return resolve(self.plan(rows, duration), Catalog(index=self.idx), reference_now=now)

    def compiled(self, rows, now=None, duration=80.0):
        return compile_plan(self.plan(rows, duration), Catalog(index=self.idx), media=MEDIA, reference_now=now)


class Discovery(Base):
    def test_every_dataset_is_found_with_no_registry(self):
        self.assertEqual(self.idx.problems, [])
        files = {p.stem for p in list(PACKS.glob("*.json")) + list(FIXTURES.glob("*.json"))}
        self.assertEqual(set(self.idx.datasets), files)
        self.assertGreaterEqual(len(self.idx.datasets), 46)
        for did in SIX:
            ds = self.idx.datasets[did]
            self.assertEqual((ds.status, {t.basis for t in ds.trajectories.values()}), ("historical", {"illustrated"}), did)

    def test_a_brand_new_dataset_is_used_with_data_only(self):
        """Dropped into a folder: discovered, indexed, resolved with its temporal metadata and trajectory, merged into the
        catalogue (its own body joins the world), detected by Check plan, compiled, built by the engine, and credited."""
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "comet_interceptor.json").write_text(json.dumps({
                "id": "comet_interceptor", "name": "Comet Interceptor", "kind": "comet_mission", "names": ["the interceptor"],
                "temporal": {"status": "planned", "as_of": "2026-06-01", "source": "ESA mission page", "date_precision": "year"},
                "met_zero": "2029-06-01T00:00:00Z",
                "events": {"launch": {"utc": "2029-06-01T00:00:00Z", "net": True}, "encounter": "2033-06-01T00:00:00Z"},
                "world": [{"id": "pristine_comet", "parent": "sun", "kind": "body", "label": "A PRISTINE COMET", "radius": {"km": 3},
                           "color": "#9fb4d8", "offset": {"orbit": {"au": 1.2}, "angle_deg": 75}}],
                "trajectories": [{"type": "trajectory", "id": "ci_cruise", "frame": "earth", "basis": "modelled", "draw": False,
                                  "generate": [{"kind": "transfer", "from": "earth", "to": "pristine_comet", "from_utc": "2029-06-01T00:00:00Z",
                                                "to_utc": "2033-06-01T00:00:00Z", "samples": 60}]}],
                "craft": {"probe": {"type": "spacecraft", "label": "COMET INTERCEPTOR", "trajectory": "ci_cruise",
                                    "parts": [{"shape": "box", "size_m": [2, 2, 2], "at_m": 0}]}},
                "paths": {"cruise": {"of": "ci_cruise", "from": "launch", "to": "encounter"}}}), encoding="utf-8")
            idx = library(tmp)
            self.assertIn("comet_interceptor", idx.datasets)                                  # 1 discovered
            self.assertEqual(idx.candidates("dataset", "the interceptor"), {"comet_interceptor"})   # 2 aliases indexed
            rows = [dict(beat="plan", row="plan", date=NOW), beat("b1", 0, "map", "pristine_comet", "body", "comet_interceptor.encounter-240:00"),
                    layer("b1", 0.5, "craft", id="comet_interceptor.probe"), layer("b1", 0.5, "path", id="comet_interceptor.cruise")]
            cat = Catalog(index=idx)
            res = resolve(self.plan(rows, 10), cat, reference_now=NOW)
            self.assertEqual(res.errors, [])
            c = res.contexts["b1"]
            self.assertEqual((c.datasets, c.status, c.basis), (["comet_interceptor"], "planned", ["modelled"]))   # 3, 4 resolved
            comp = compile_plan(self.plan(rows, 10), cat, resolution=res)
            spec = strip_private(comp.spec)
            self.assertTrue(any(L.get("id") == "ci_cruise" for L in spec["layers"]))          # 5 trajectory
            self.assertIn("pristine_comet", [b["id"] for b in spec["world"]])                # 6 catalogue merged
            rep = check_csv(csv_of(rows), duration=10, catalog=Catalog(index=idx))
            self.assertTrue(rep.ok, rep.to_text())
            self.assertIn("Comet Interceptor (comet_interceptor)", rep.to_text())            # 7 Check plan detects it
            self.assertTrue(any(L.get("text", "").startswith("PLANNED") for L in spec["layers"] if L["type"] == "status_badge"))   # 8 compiled
            self.assertEqual(engine_build(spec), "ok")                                      # 9 the engine builds it
            from starmap.app_integration import dataset_credits

            self.assertTrue(any(line.startswith("Comet Interceptor: planned") and "ESA mission page" in line
                                for line in dataset_credits(cat, res)))                     # 10 credited
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def engine_build(spec) -> str:
    """The compiled spec through the engine's own modules (no browser): its world, every trajectory, every layer type known."""
    node = shutil.which("node") or str(HERE / "bin" / "node")
    tmp = Path(tempfile.mkdtemp())
    (tmp / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    eng = (HERE / "starmap-engine").as_posix()
    script = f"""
import fs from 'node:fs';
const {{ buildWorld }} = await import('file://{eng}/lib/world.mjs');
const {{ createTrajectory }} = await import('file://{eng}/lib/paths.mjs');
const {{ BUILTIN_LAYERS }} = await import('file://{eng}/layers/index.mjs');
const spec = JSON.parse(fs.readFileSync({json.dumps(str(tmp / "spec.json"))}, 'utf8'));
const known = new Set(BUILTIN_LAYERS.map((l) => l.type));
for (const L of spec.layers) if (!known.has(L.type)) throw new Error('unknown layer ' + L.type);
const world = buildWorld(spec.world, {{ date: new Date(spec.clock.keys ? spec.clock.keys[0].utc : spec.clock.utc) }});
for (const L of spec.layers) if (L.type === 'trajectory' && !L.of) {{ const t = createTrajectory(world, L); if (!t.at((t.t0 + t.t1) / 2).position.every(Number.isFinite)) throw new Error(L.id); }}
console.log('ok');
"""
    (tmp / "check.mjs").write_text(script, encoding="utf-8")
    r = subprocess.run([node, str(tmp / "check.mjs")], capture_output=True, text=True, cwd=str(HERE / "starmap-engine"))
    shutil.rmtree(tmp, ignore_errors=True)
    return r.stdout.strip() if r.returncode == 0 else (r.stderr.strip()[-600:] or "failed")


class Collisions(Base):
    def lookup_error(self, kind, name, ctx=()):
        with self.assertRaises(CatalogError) as cm:
            self.cat.lookup(kind, name, ctx)
        return str(cm.exception)

    def test_voyager_alone_is_ambiguous(self):
        msg = self.lookup_error("craft", "Voyager")
        self.assertIn("ambiguous", msg)
        self.assertIn("voyager1.voyager1", msg)
        self.assertIn("voyager2.voyager2", msg)
        self.assertEqual(self.cat.lookup("craft", "Voyager", ["voyager2"])[0], "voyager2.voyager2", "a beat about Voyager 2 settles it")

    def test_apollo_is_never_guessed(self):
        self.assertIn("unknown craft 'apollo'", self.lookup_error("craft", "Apollo").lower())
        rows = [beat("b1", 0, "map", "moon", "body", "launch"), layer("b1", 0.5, "craft", id="csm")]
        res = self.resolved(rows, duration=10)
        self.assertTrue(any("ambiguous" in e and "apollo11" in e and "apollo8" in e for e in res.errors), res.errors)

    def test_spacecraft_launch_and_orbit_are_scoped(self):
        self.assertIn("ambiguous", self.lookup_error("craft", "spacecraft"))
        self.assertEqual(self.cat.lookup("craft", "spacecraft", ["change4"])[0], "change4.spacecraft")
        self.assertIn("ambiguous", self.lookup_error("event", "launch"))
        self.assertIn("ambiguous", self.lookup_error("orbit", "lunar_orbit"))
        self.assertEqual(self.cat.lookup("orbit", "lunar_orbit", ["artemis3"])[0], "artemis3.lunar_orbit")
        self.assertEqual(self.cat.date("apollo8.launch"), "1968-12-21T12:51:00Z")
        self.assertEqual(self.cat.date("artemis1.launch"), "2022-11-16T06:47:44Z")

    def test_invalid_qualified_ids_and_unknown_datasets(self):
        self.assertIn("invalid qualified id", self.lookup_error("craft", "apollo11.orion"))
        self.assertIn("unknown dataset 'apolo11'", self.lookup_error("craft", "apolo11.lm"))
        res = self.resolved([beat("b1", 0, "map", "moon", "body", "", extra={"mission": "voyager3"})], duration=5)
        self.assertTrue(any("unknown dataset 'voyager3'" in e for e in res.errors), res.errors)

    def test_repeated_names_never_cross_missions(self):
        """Two missions with a craft called csm in one video: two layers, two trajectories, no mix-up."""
        rows = [beat("b1", 0, "map", "moon", "body", "apollo8.loi"), layer("b1", 0.5, "craft", id="apollo8.csm"),
                beat("b2", 6, "map", "moon", "body", "apollo11.loi"), layer("b2", 6.5, "craft", id="apollo11.csm")]
        spec = self.compiled(rows, duration=12).spec
        craft = {L["id"]: L["trajectory"] for L in spec["layers"] if L["type"] == "spacecraft"}
        self.assertEqual(craft, {"apollo8.csm": "apollo8_csm", "apollo11.csm": "apollo11_csm"})


class Temporal(Base):
    def test_the_mixed_documentary_keeps_every_beats_context(self):
        res = self.resolved(MIXED, now=None)
        self.assertEqual(res.errors, [])
        self.assertEqual(res.reference_now, "2026-10-08T12:00:00Z", "the plan row's date is the reference now")
        c = res.contexts
        want = {
            "b1": (["apollo11"], "historical", ["illustrated"], "1969-07-20"),
            "b2": (["voyager1"], "current", ["observed"], "2026-10-08"),
            "b3": (["voyager2"], "current", ["observed"], "2026-10-08"),
            "b4": (["juno"], "current", ["modelled"], "2026-10-08"),
            "b5": (["parker_solar_probe"], "historical", ["observed"], "2024-12-24"),
            "b6": (["jwst"], "current", ["illustrated"], "2026-10-08"),
            "b7": (["perseverance"], "historical", ["illustrated"], "2021-02-18"),
            "b8": (["osiris_rex"], "historical", [], "2020-10-20"),
            "b10": (["artemis3"], "planned", ["modelled"], "2027-09-21"),
            "b11": (["moon_base_2050"], "hypothetical", ["illustrative"], "2050-07-01"),
            "b12": ([], "hypothetical", ["illustrative"], "2060-01-01"),
        }
        for b, (ds, status, basis, day) in want.items():
            self.assertEqual((c[b].datasets, c[b].status, c[b].basis, c[b].utc[:10]), (ds, status, basis, day), b)
        self.assertEqual(sorted(res.used), sorted({d for v in want.values() for d in v[0]}))
        # historical vs future dates never confused: universe dates follow the beats exactly
        years = [parse_iso(c[b].utc).year for b in ("b1", "b2", "b10", "b11")]
        self.assertEqual(years, [1969, 2026, 2027, 2050])
        # labels
        self.assertEqual(c["b1"].badge, "")
        self.assertEqual(c["b2"].badge, "ESTIMATED · DATA TO JUN 2026")
        self.assertEqual(c["b10"].badge, "PLANNED · SEP 2027")
        self.assertEqual(c["b11"].badge, "HYPOTHETICAL · 2050")
        self.assertEqual(c["b12"].badge, "HYPOTHETICAL · 2060")
        self.assertEqual(c["b2"].estimated_from[:10], "2026-06-01")
        # transitions: new timelines jump; the jump into Artemis III is hidden by the footage
        kinds = {(t.a, t.b): (t.kind, t.hidden_by_footage, t.label) for t in res.transitions}
        self.assertEqual(kinds[("b1", "b2")], ("jump", False, "1969 → 2026 · TODAY"))
        self.assertEqual(kinds[("b8", "b10")][:2], ("jump", True))
        self.assertEqual(kinds[("b10", "b11")], ("jump", False, "2027 → 2050 · HYPOTHETICAL"))

    def test_the_compiled_video_labels_clocks_and_jumps(self):
        comp = self.compiled(MIXED)
        spec = comp.spec
        clocks = [L for L in spec["layers"] if L["type"] == "mission_clock"]
        zeros = {L.get("met_zero") for L in clocks}
        for did, zero in (("apollo11", "1969-07-16T13:32:00Z"), ("voyager1", "1977-09-05T12:56:00Z"), ("voyager2", "1977-08-20T14:29:00Z"),
                          ("artemis3", "2027-09-15T12:00:00Z")):
            self.assertIn(zero, zeros, f"{did} keeps its own mission clock")
        a3 = next(L for L in clocks if L.get("met_zero") == "2027-09-15T12:00:00Z")
        self.assertEqual((a3.get("prefix"), a3.get("date_precision")), ("PLANNED", "month"))
        self.assertNotIn("met_zero", spec["clock"], "no single global T-zero")
        badges = [L["text"] for L in spec["layers"] if L["type"] == "status_badge"]
        self.assertIn("PLANNED · SEP 2027", badges)
        self.assertIn("HYPOTHETICAL · 2050", badges)
        self.assertIn("ESTIMATED · DATA TO JUN 2026", badges)
        notes = [L["text"] for L in spec["layers"] if L["type"] == "footnote"]
        self.assertIn("FLIGHT PATH ILLUSTRATED", notes)
        orion = next(L for L in spec["layers"] if L["type"] == "spacecraft" and L["id"] == "artemis3.orion")
        self.assertEqual(orion["label"], "ORION · PLANNED")
        path = next(L for L in spec["layers"] if L["type"] == "trajectory" and L.get("of") == "artemis3_orion")
        self.assertTrue(path["style"]["dash"], "a planned path is dashed")
        lm = next(L for L in spec["layers"] if L["type"] == "spacecraft" and L["id"] == "apollo11.lm")
        self.assertEqual(lm["label"], "EAGLE", "history is not labelled")
        jumps = [L for L in spec["layers"] if L["type"] == "time_jump"]
        self.assertEqual({L["text"] for L in jumps} >= {"1969 → 2026 · TODAY", "2027 → 2050 · HYPOTHETICAL"}, True)
        assert_no_visible_fast_forward(self, spec)
        self.assertEqual(engine_build(strip_private(spec)), "ok")

    def test_mission_time_counts_down_before_launch(self):
        self.assertEqual(self.cat.date("artemis3.T-01:00:00"), "2027-09-15T11:00:00Z")
        self.assertEqual(self.cat.date("apollo11.T+102:45:40"), "1969-07-20T20:17:40Z")
        res = self.resolved([beat("b1", 0, "map", "earth", "body", "T+01:00")], duration=5)
        self.assertTrue(any("invalid mission clock" in e for e in res.errors), res.errors)

    def test_the_csv_may_lower_certainty_never_raise_it(self):
        res = self.resolved([beat("b1", 0, "map", "earth+moon", "system", "artemis3.launch", extra={"status": "historical"})], duration=5)
        self.assertTrue(any("conflicting status" in e for e in res.errors), res.errors)
        res = self.resolved([beat("b1", 0, "map", "moon", "body", "apollo11.landing", extra={"status": "hypothetical"})], duration=5)
        self.assertEqual((res.errors, res.contexts["b1"].status), ([], "hypothetical"))

    def test_status_and_basis_stay_separate(self):
        c = self.resolved(MIXED).contexts
        self.assertEqual((c["b1"].status, c["b1"].basis), ("historical", ["illustrated"]))
        self.assertEqual((c["b2"].status, c["b2"].basis), ("current", ["observed"]))
        self.assertEqual((c["b10"].status, c["b10"].basis), ("planned", ["modelled"]))
        self.assertEqual((c["b11"].status, c["b11"].basis), ("hypothetical", ["illustrative"]))

    def test_projected_data_is_labelled(self):
        res = self.resolved([beat("b1", 0, "map", "earth+moon", "system", "lunar_cargo_2031.launch"),
                             layer("b1", 0.5, "craft", id="lunar_cargo_2031.cargo_lander")], duration=6)
        self.assertEqual((res.errors, res.contexts["b1"].status, res.contexts["b1"].badge), ([], "projected", "PROJECTED · 2031"))


class Freshness(Base):
    def test_past_the_extrapolation_limit_is_an_error(self):
        rows = [dict(beat="plan", row="plan", date=NOW), beat("b1", 0, "map", "sun", "heliosphere", "2033-01-01T00:00:00Z"),
                layer("b1", 0.5, "craft", id="voyager1.voyager1")]
        self.assertTrue(any("unsupported extrapolation" in e for e in self.resolved(rows, duration=5).errors))

    def test_no_extrapolation_rule_means_no_invented_position(self):
        rows = [dict(beat="plan", row="plan", date=NOW), beat("b1", 0, "map", "perseverance.jezero landing site", "surface", "now"),
                layer("b1", 0.5, "craft", id="perseverance.rover")]
        errs = self.resolved(rows, duration=5).errors
        self.assertTrue(any("unavailable observed data" in e and "2026-06-01" in e for e in errs), errs)
        rows = [beat("b1", 0, "map", "sun", "heliosphere", "2010-01-01T00:00:00Z"), layer("b1", 0.5, "craft", id="pioneer10.pioneer10")]
        self.assertTrue(any("unavailable observed data" in e for e in self.resolved(rows, duration=5).errors))

    def test_inside_the_observed_data_is_observed(self):
        rows = [beat("b1", 0, "map", "sun", "heliosphere", "voyager1.heliopause"), layer("b1", 0.5, "craft", id="voyager1.voyager1")]
        c = self.resolved(rows, duration=5).contexts["b1"]
        self.assertEqual((c.status, c.basis, c.estimated_from, c.badge), ("historical", ["observed"], None, ""))

    def test_an_estimated_position_extends_the_path_in_the_spec(self):
        spec = self.compiled(MIXED).spec
        v1 = next(L for L in spec["layers"] if L["type"] == "trajectory" and L.get("id") == "voyager1_path")
        last = parse_iso(v1["samples"][-1]["utc"])
        self.assertGreater(last, parse_iso("2026-10-08T00:00:00Z"))
        self.assertTrue(v1["samples"][-1].get("estimated"))

    def test_now_needs_a_reference_date(self):
        res = self.resolved([beat("b1", 0, "map", "earth", "body", "now")], duration=5)
        self.assertTrue(any("reference date" in e for e in res.errors), res.errors)

    def test_historical_after_the_reference_date_is_an_error(self):
        rows = [beat("b1", 0, "map", "moon", "body", "apollo11.landing")]
        errs = self.resolved(rows, now="1960-01-01", duration=5).errors
        self.assertTrue(any("unsupported date" in e for e in errs), errs)


def assert_no_visible_fast_forward(tc, spec):
    """Between consecutive clock keys, more than a year of universe time may pass only while the map is hidden: under
    footage, or at a time-jump card's dark moment."""
    keys = spec["clock"]["keys"]
    jumps = [L["at"] for L in spec["layers"] if L["type"] == "time_jump"]
    for a, b in zip(keys, keys[1:]):
        days = abs((parse_iso(b["utc"]) - parse_iso(a["utc"])).total_seconds()) / 86400
        if days <= 400:
            continue
        hidden = any(f["start"] - 0.01 <= a["t"] and b["t"] <= f["end"] + 0.01 for f in spec["footage"])
        at_jump = any(abs(b["t"] - j) < 1e-3 and b["t"] - a["t"] <= 0.05 for j in jumps)
        tc.assertTrue(hidden or at_jump, f"{days / 365.25:.0f} years would run on screen between {a['t']}s and {b['t']}s")


class FootageAndTime(Base):
    def test_a_jump_under_footage_is_hidden_and_the_map_returns_at_the_new_date(self):
        rows = [beat("b1", 0, "map", "moon", "body", "apollo11.landing"), layer("b1", 0.5, "craft", id="apollo11.lm"),
                beat("b2", 6, "footage"), clip("b2"),
                beat("b3", 12, "map", "earth+moon", "system", "artemis1.launch"), layer("b3", 12.5, "craft", id="artemis1.orion")]
        spec = self.compiled(rows, duration=18).spec
        keys = {k["t"]: k["utc"] for k in spec["clock"]["keys"]}
        self.assertTrue(keys[6.0].startswith("1969-07-20"), "the 1969 date holds in real time until the footage")
        self.assertEqual(keys[12.0], "2022-11-16T06:47:44Z", "the map comes back already in 2022")
        self.assertTrue(all(u.startswith("1969") for t, u in keys.items() if t < 12) and all(u.startswith("2022") for t, u in keys.items() if t >= 12))
        self.assertFalse([L for L in spec["layers"] if L["type"] == "time_jump"], "footage hides the jump: no card")
        assert_no_visible_fast_forward(self, spec)
        clocks = [(L.get("met_zero"), L["start"], L["end"]) for L in spec["layers"] if L["type"] == "mission_clock"]
        self.assertEqual([c[0] for c in clocks], ["1969-07-16T13:32:00Z", "2022-11-16T06:47:44Z"])

    def test_same_mission_beats_stay_continuous(self):
        res = self.resolved([beat("b1", 0, "map", "earth", "body", "apollo11.tli"), beat("b2", 6, "map", "moon", "body", "apollo11.loi")], duration=12)
        self.assertEqual([(t.kind, t.hidden_by_footage) for t in res.transitions], [("continuous", False)])
        res = self.resolved([beat("b1", 0, "map", "earth", "body", "apollo11.tli"),
                             beat("b2", 6, "map", "moon", "body", "apollo11.loi", extra={"continuous": False})], duration=12)
        self.assertEqual(res.transitions[0].kind, "jump")
        res = self.resolved([beat("b1", 0, "map", "earth", "body", "apollo11.tli"),
                             beat("b2", 6, "map", "moon", "body", "artemis1.launch", extra={"continuous": True})], duration=12)
        self.assertTrue(any("invalid temporal transition" in e for e in res.errors), res.errors)


class SixMissions(Base):
    def test_all_six_production_missions_in_one_video(self):
        rows, t = [], 0.0
        events = {"apollo8": "loi", "apollo11": "landing", "apollo13": "explosion", "artemis1": "dro_insertion",
                  "chandrayaan3": "landing", "change4": "landing"}
        for i, did in enumerate(SIX):
            craft = sorted(self.idx.datasets[did].craft)[0]
            rows += [beat(f"b{i + 1}", t, "map", "earth+moon", "system", f"{did}.{events[did]}"), layer(f"b{i + 1}", t + 0.5, "craft", id=f"{did}.{craft}")]
            t += 6
        comp = self.compiled(rows, duration=t)
        res = comp.resolution
        self.assertEqual((res.errors, sorted(res.used)), ([], sorted(SIX)))
        spec = comp.spec
        ids = [L["id"] for L in spec["layers"] if L["type"] == "spacecraft"]
        self.assertEqual(len(ids), len(set(ids)), "no layer id collides")
        self.assertTrue(all(i.split(".", 1)[0] in SIX for i in ids))
        trajs = {L["id"] for L in spec["layers"] if L["type"] == "trajectory" and L.get("id")}
        for L in spec["layers"]:
            if L["type"] == "spacecraft":
                self.assertIn(L["trajectory"], trajs)
                self.assertTrue(L["trajectory"].startswith(L["id"].split(".", 1)[0]))
        zeros = [L.get("met_zero") for L in spec["layers"] if L["type"] == "mission_clock"]
        self.assertEqual(zeros, [self.idx.datasets[d].met_zero for d in SIX], "each mission its own T-zero, in order")
        self.assertEqual(sum(1 for t in res.transitions if t.kind == "jump"), 5)
        assert_no_visible_fast_forward(self, spec)

    def test_the_old_single_pack_view_still_works(self):
        cat = Catalog("apollo11")
        self.assertEqual(cat.date("landing"), "1969-07-20T20:17:40Z")
        self.assertEqual(cat.craft_id("Eagle"), "apollo11.lm")
        with self.assertRaises(CatalogError):
            cat.craft_id("Orion")


class DeterminismAndIsolation(Base):
    def test_the_same_csv_resolves_and_compiles_identically(self):
        a, b = self.resolved(MIXED), self.resolved(MIXED)
        self.assertEqual(json.dumps(asdict(a), sort_keys=True), json.dumps(asdict(b), sort_keys=True))
        s1, s2 = self.compiled(MIXED).spec, self.compiled(MIXED).spec
        self.assertEqual(json.dumps(s1, sort_keys=True), json.dumps(s2, sort_keys=True))

    def test_no_wall_clock_in_resolution(self):
        """The machine's clock and time zone never reach the resolved plan: another process, another time zone, same spec."""
        code = ("import json,sys; sys.path.insert(0, %r); import test_starmap_universal as t; "
                "print(json.dumps(t.compile_mixed(), sort_keys=True))") % str(HERE)
        outs = []
        for tz in ("UTC", "Asia/Tokyo"):
            env = dict(os.environ, TZ=tz)
            r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=str(HERE))
            self.assertEqual(r.returncode, 0, r.stderr[-800:])
            outs.append(r.stdout)
        self.assertEqual(outs[0], outs[1])
        for f in ("resolve.py", "compile.py", "catalog.py", "datasets.py", "temporal.py", "check.py"):
            src = (HERE / "starmap" / f).read_text(encoding="utf-8")
            self.assertFalse(re.search(r"\b(datetime\.now|datetime\.utcnow|time\.time|date\.today)\(", src), f)

    def test_resolution_and_compilation_need_no_network(self):
        real_connect, real_create = socket.socket.connect, socket.create_connection

        def blocked(*a, **k):
            raise AssertionError("StarMap resolution tried to use the network")

        socket.socket.connect, socket.create_connection = blocked, blocked
        try:
            rep = check_csv(csv_of(MIXED), duration=80, media=MEDIA, catalog=Catalog(index=self.idx))
            self.assertEqual(rep.errors, [])
            self.compiled(MIXED)
        finally:
            socket.socket.connect, socket.create_connection = real_connect, real_create

    def test_no_runtime_ai(self):
        """Check plan and compilation of the mixed documentary load no AI client of any kind, and the StarMap package imports none."""
        code = ("import sys, json; sys.path.insert(0, %r); import test_starmap_universal as t; t.compile_mixed(); "
                "print(json.dumps(sorted(sys.modules)))") % str(HERE)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(HERE))
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        mods = json.loads(r.stdout.strip().splitlines()[-1])
        bad = [m for m in mods if re.search(r"(^|\.)(anthropic|openai|gemini|generativeai|genai|ai_router|llm|langchain)", m, re.I)]
        self.assertEqual(bad, [])
        for f in sorted((HERE / "starmap").glob("*.py")):
            src = f.read_text(encoding="utf-8")
            self.assertFalse(re.search(r"^\s*(import|from)\s+(anthropic|openai|google\.generativeai|google\.genai|ai_router|gemini)", src, re.M), f.name)


def compile_mixed():
    """For the subprocess tests: the mixed documentary, compiled with the full library."""
    idx = library()
    plan = read_plan(csv_of(MIXED), duration=80.0)
    return strip_private(compile_plan(plan, Catalog(index=idx), media=MEDIA).spec)


class CheckPlanReport(Base):
    def test_detected_lists_every_dataset_with_status_and_freshness(self):
        rep = check_csv(csv_of(MIXED), duration=80, media=MEDIA, catalog=Catalog(index=self.idx))
        text = rep.to_text()
        self.assertTrue(rep.ok, text)
        for line in ("Apollo 11 (apollo11)  Historical · 1969 · illustrated geometry",
                     "Voyager 1 (voyager1)  Current · 2026 · observed geometry · observed data through JUN 2026",
                     "Artemis III (artemis3)  Planned · 2027 · modelled geometry · as of JUN 2026",
                     "Moon Base 2050 (moon_base_2050)  Hypothetical · 2050 · illustrative geometry"):
            self.assertIn(line, text)
        self.assertIn("Time jumps:", text)
        self.assertNotIn("mission pack", text.lower())

    def test_errors_are_named_never_repaired(self):
        rows = [beat("b1", 0, "map", "moon", "body", "launch"), layer("b1", 0.5, "craft", id="voyager"),
                layer("b1", 0.5, "path", id="apollo11.nowhere")]
        rep = check_csv(csv_of(rows), duration=6, catalog=Catalog(index=self.idx))
        self.assertFalse(rep.ok)
        text = rep.to_text()
        self.assertIn("'voyager' is ambiguous", text)
        self.assertIn("invalid qualified id 'apollo11.nowhere'", text)


if __name__ == "__main__":
    unittest.main()
