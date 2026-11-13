"""Balance director v2 (docs/aviation/J11_REFERENCE_STUDY.md section 4): the Aviation style now mixes looks from four references;
this measures a plan's screen time per look against the target bands and fixes what it can before render.

    LOOKS / TARGETS                         footage 35-45 %, sticker stage 20-30 %, dossier 15-20 %, full-screen photos +
                                            Flow pictures 10-15 %, maps 5-10 %, blue news cards ~5 % (+ anything else 'other')
    shares(plan, total) -> {look: seconds}  stage cutaways (photo_full) count as photos, not stage
    report(plan, total) -> {shares %, out_of_band: [(look, pct, lo, hi)], repeats}
    apply(plan, scenes) -> report           fixes: the same card template twice in a row -> the second becomes the other skin's
                                            card for its line (dossier <-> blue news graphic) when that line has one
Shares are not forced by inventing pictures: a film with no real photos stays under the photo band, and the report says so.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

TARGETS = {"footage": (35, 45), "stage": (20, 30), "dossier": (15, 20), "photos": (10, 15), "maps": (5, 10), "news cards": (0, 8)}


def look_of(shot: Dict[str, Any]) -> str:
    if shot.get("kind") == "footage":
        return "footage"
    lay = str(shot.get("layer") or "")
    if lay == "stage.lay_stage":
        return "stage"
    if lay.startswith("dossier."):
        return "dossier"
    if lay in ("flightmap.lay_flight_map",):
        return "maps"
    if lay.startswith(("cards.", "gfx_air.")):
        return "news cards"
    return "other"


def _base(plan: Any) -> List[Dict[str, Any]]:
    return sorted([s for s in plan.shots if s.get("kind") == "footage" or s.get("full_frame")], key=lambda s: float(s["start"]))


def shares(plan: Any, total: float) -> Dict[str, float]:
    out = {k: 0.0 for k in list(TARGETS) + ["other"]}
    for s in _base(plan):
        d = float(s["end"]) - float(s["start"])
        lk = look_of(s)
        if lk == "stage":
            cut = sum(max(0.0, float(e.get("t1") or 0) - float(e["t0"])) for e in (s.get("params") or {}).get("elements") or []
                      if e.get("kind") == "photo_full")
            out["photos"] += min(cut, d)
            out["stage"] += max(0.0, d - cut)
        else:
            out[lk] += d
    return out


def repeats(plan: Any) -> List[Tuple[int, str]]:
    """Index pairs of full-frame cards whose template repeats back to back (footage between them breaks the run)."""
    base = _base(plan)
    out = []
    for i in range(1, len(base)):
        a, b = base[i - 1], base[i]
        la, lb = str(a.get("layer") or ""), str(b.get("layer") or "")
        if la and la == lb and la != "stage.lay_stage" and abs(float(a["end"]) - float(b["start"])) < 0.05:
            out.append((i, lb))
    return out


def report(plan: Any, total: float) -> Dict[str, Any]:
    sh = shares(plan, total)
    pct = {k: round(100.0 * v / max(1e-6, total), 1) for k, v in sh.items()}
    oob = [(k, pct[k], lo, hi) for k, (lo, hi) in TARGETS.items() if not (lo <= pct[k] <= hi)]
    return {"shares": pct, "out_of_band": oob, "repeats": [x[1] for x in repeats(plan)]}


def apply(plan: Any, scenes: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    from . import dossier as DZ
    from . import planner as P
    from . import router as R
    by_no = {s.get("scene_no"): s for s in scenes}
    fixed = []
    base = _base(plan)
    for i, lay in repeats(plan):
        sh = base[i]
        sc = by_no.get(sh.get("scene"))
        if not sc:
            continue
        c = R.classify(str(sc.get("text") or ""))
        if lay.startswith("dossier."):
            alt = next((g for g in P._air_graphics(c, {}) if g[0] != lay), None)
        else:
            dz = DZ.pick(c, {})
            alt = dz if dz and dz[0] != lay else None
        if alt:
            sh["layer"], sh["params"] = alt[0], dict(alt[1])
            fixed.append({"scene": sh.get("scene"), "from": lay, "to": alt[0]})
    total = max([float(s["end"]) for s in scenes] + [0.0])
    rep = report(plan, total)
    rep["fixed"] = fixed
    return rep
