"""War Documentary plan guard: what three fixed scripts plan today is recorded in test_fixtures/war_plan_guard.json. A later change may ADD
cards; an existing card or shot that disappears or moves fails here unless it is named in ALLOWED (with the owner's reason).

Regenerate the fixture only on purpose:  python3 test_war_plan_guard.py --record"""

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cinematic_explainer.war import planner

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "test_fixtures" / "war_plan_guard.json"
SCENES = ROOT / "test_fixtures" / "war_guard_scenes.csv"
ALLOWED: dict = {          # {"variant:kind@start": "why it changed"}
    "no_footage:tac_map@0.0": "2026-11-11 Stage B.2 owner: one 94 s map split where the geography changes (Kyiv/north 0-42, south/east "
                              "42-83.2, Zaporizhzhia NPP 83.2-93.92); same total time, pins reset per map",
    "csv:kit_title@0.0": "2026-11-08 owner: too much text on the dark plate; CSV title / date / kinetic cards hold at most 4.5 s",
    "csv:tac_map@6.8": "2026-11-08 the map now starts when the shorter title card ends (same end time)",
    "all_footage:kit_tag@83.2": "2026-11-09 owner: pictures follow the narration; 'A report by the Institute for the Study of War found' is now "
                                "read as a citation, so the institute's own card replaces the small tag",
    "all_footage:kit_kinetic@78.8": "2026-11-09 the generic kinetic filler under 'Russian forces captured Avdiivka' gives way to the place's "
                                    "label and the ISW card that now follows",
    "all_footage:bc_label@115.12": "2026-11-09 the label rate (about one per 15 s) is spent on AVDIIVKA at 81 s instead",
    "csv:kicker@93.92": "2026-11-10 a kicker ends with its card: 'Key figure' stops at 99.6 with the chart, not 0.3 s over the next map",
    "csv:tac_map@30.0": "2026-11-10 a dimming layout card now counts as a cover: the map ends at 37.08 where the figure card starts (was 0.7 s under it)",
    "all_footage:tac_map@99.6": "2026-11-10 same: the map ends at 106.28 where the timeline starts (was 0.1 s under it)",
}
SKIP_KINDS = {"kit_grain"}  # film grain spans the whole timeline and follows the length, not a decision


def _clip(d: str) -> str:
    c = str(Path(d, "guard.mp4"))
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=320x180:d=10", "-r", "25", c], check=True)
    return c


def variants(clip: str) -> dict:
    rows = list(csv.DictReader(SCENES.open(encoding="utf-8")))
    out = {}
    for name, use_graphic, foot in (("csv", True, "csv"), ("no_footage", False, "none"), ("all_footage", False, "all")):
        t, sc = 0.0, []
        for i, r in enumerate(rows):
            d = max(4.0, len(r["script_segment"].split()) * 0.4)
            has = foot == "all" or (foot == "csv" and r["asset_type"] != "none")
            sc.append({"text": r["script_segment"], "start": round(t, 2), "end": round(t + d, 2), "scene_no": i + 1,
                       "graphic": r["graphic"] if use_graphic else "", "footage": clip if has else None, "footage_meta": {}})
            t += d
        out[name] = sc
    return out


def snapshot(sc: list) -> dict:
    plan = planner.plan(sc, config={})
    return {"layers": sorted([[ly.kind, round(ly.start, 2), round(ly.end, 2)] for ly in plan.layers if ly.kind not in SKIP_KINDS]),
            "shots": sorted([[round(s.start, 2), round(s.end, 2)] for s in plan.shots])}


class PlanGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.now = {k: snapshot(v) for k, v in variants(_clip(cls.tmp.name)).items()}
        cls.then = json.loads(FIXTURE.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_no_existing_card_disappears_or_moves(self):
        for name, snap in self.then.items():
            now = self.now[name]["layers"]
            for kind, a, b in snap["layers"]:
                key = f"{name}:{kind}@{a}"
                if key in ALLOWED:
                    continue
                with self.subTest(card=key):
                    self.assertTrue(any(k == kind and abs(x - a) <= 0.05 and abs(y - b) <= 0.05 for k, x, y in now),
                                    f"{key}-{b} is gone or moved")

    def test_shots_unchanged(self):
        for name, snap in self.then.items():
            with self.subTest(variant=name):
                self.assertEqual(self.now[name]["shots"], snap["shots"])


if __name__ == "__main__":
    if "--record" in sys.argv:
        with tempfile.TemporaryDirectory() as d:
            data = {k: snapshot(v) for k, v in variants(_clip(d)).items()}
        FIXTURE.write_text(json.dumps(data, indent=0), encoding="utf-8")
        print({k: (len(v["layers"]), len(v["shots"])) for k, v in data.items()})
    else:
        unittest.main()
