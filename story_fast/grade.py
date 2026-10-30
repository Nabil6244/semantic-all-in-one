"""One colour grade / vignette / grain per Story Motion project, measured ONCE from the stills so pictures from different Flow batches match.

    g = compute_project_grade(list_of_still_paths)          # ~1 s for 250 stills (64 px thumbnails), JSON-serialisable (g.to_dict())
    g.filter_for(still_path)                                 # ffmpeg filter chain for one shot (per-still correction + the shared finish)
    g.color_filter(still_path) / g.finish_filter()           # the two halves separately

What is measured per still (on a 64 px thumbnail, sRGB): mean R/G/B, luma percentiles, mean saturation. The project reference is the MEDIAN of
those over all stills (robust against a few odd pictures). Each still then gets a small, clamped correction toward the reference:
per-channel gamma (white balance / cast), luma gamma (exposure) and saturation. The correction is clamped (+-8% exposure, +-6% cast, +-12%
saturation) so a deliberately dark or colourful picture stays itself; it is also scaled down when the still is already close.
The finish (identical for every shot): a light contrast curve, one vignette (much weaker on white-background pictures, so they do not get
grey corners) and one temporal grain. All filters are per-pixel and cheap (eq, vignette, noise), no extra inputs.

Wired: runner.plan_clips puts filter_for(still) on every shot job (job['grade_vf']); compose._build_graph uses it in place of the fixed vignette/noise tail, and job_key covers it."""
from __future__ import annotations

import json, math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence

THUMB = 64
CLAMP_EXPOSURE, CLAMP_CAST, CLAMP_SAT = 0.08, 0.06, 0.12


def _stats(path: str) -> Optional[dict]:
    """Per-picture numbers. White-background cartoons are most of a Flow explainer, so the picture is split in a PAPER part (near-white pixels:
    the white point / background tint) and a CONTENT part (everything else: exposure and saturation of the drawing itself)."""
    import numpy as np
    from PIL import Image
    try:
        im = Image.open(path).convert("RGB")
        im.thumbnail((THUMB, THUMB))
        a = np.asarray(im, dtype=np.float32) / 255.0
    except Exception:
        return None
    px = a.reshape(-1, 3)
    mean = px.mean(0)
    luma = px @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    mx, mn = px.max(1), px.min(1)
    sat_all = (mx - mn) / np.maximum(mx, 1e-3)
    content = mn < 0.88
    if content.sum() < 12:
        content = np.ones_like(content)
    wp = np.percentile(px, 90, axis=0)
    return {"rgb": [float(x) for x in mean], "luma": float(luma.mean()), "wp": [float(x) for x in wp], "highkey": bool(float(wp @ np.array([0.2126, 0.7152, 0.0722])) >= 0.9),
            "clum": float(np.median(luma[content])), "csat": float(sat_all[content].mean()), "paper": float(1.0 - content.mean())}


def _gamma_to(src: float, dst: float) -> float:
    """eq gamma g so that src ** (1/g) == dst  (eq applies out = in ** (1/g))."""
    src, dst = min(max(src, 0.02), 0.98), min(max(dst, 0.02), 0.98)
    return math.log(src) / math.log(dst)


@dataclass
class ProjectGrade:
    ref: Dict[str, float] = field(default_factory=dict)       # reference means (r,g,b,luma,sat,p98)
    contrast: float = 1.04
    saturation: float = 1.0
    vignette_angle: float = 0.45                                # corners of a mid-tone picture ~ 70% (the fixed look PI/5 = 0.63 gave ~39%)
    grain: int = 3                                              # compose.py today: noise alls=3
    stills: int = 0
    per_still: Dict[str, dict] = field(default_factory=dict)    # {path: {"gr","gg","gb","gl","sat"}} (filled lazily/at compute time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ProjectGrade":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    # ---- per-still correction
    def correction(self, still: Optional[str]) -> dict:
        """{"gr","gg","gb","gl","sat"} for one still (neutral = all 1.0 when unknown / no reference)."""
        neutral = {"gr": 1.0, "gg": 1.0, "gb": 1.0, "gl": 1.0, "sat": 1.0}
        if not still or not self.ref:
            return neutral
        c = self.per_still.get(str(still))
        if c is None:
            s = _stats(str(still))
            if s is None:
                return neutral
            c = self._from_stats(s)
            self.per_still[str(still)] = c
        return {k: c[k] for k in neutral}

    def paper(self, still: Optional[str]) -> float:
        """Share of near-white pixels of a picture (0..1), from the same measurement."""
        self.correction(still)
        return float((self.per_still.get(str(still)) or {}).get("paper", 0.0))

    def _from_stats(self, s: dict) -> dict:
        r = self.ref["hi" if s["highkey"] else "lo"] if "hi" in self.ref else self.ref
        gl = 1.0 + max(-CLAMP_EXPOSURE, min(CLAMP_EXPOSURE, 0.5 * (_gamma_to(s["clum"], r["clum"]) - 1.0)))
        if s["highkey"]:       # white point -> the set's white point (a cream / blue-ish paper is pulled toward the common one)
            ch = [_gamma_to(s["wp"][i], r["wp"][i]) for i in range(3)]
        else:                  # no paper to read: correct half of the cast of the mean colour against the set's, at this picture's brightness
            ch = [_gamma_to(s["rgb"][i], r["rgb"][i] / max(r["luma"], 0.05) * s["luma"]) for i in range(3)]
            ch = [1.0 + 0.5 * (c - 1.0) for c in ch]
        gr, gg, gb = [1.0 + max(-CLAMP_CAST, min(CLAMP_CAST, c - 1.0)) for c in ch]
        sat = 1.0 + max(-CLAMP_SAT, min(CLAMP_SAT, 0.5 * (r["csat"] / max(s["csat"], 0.03) - 1.0)))
        return {"gr": round(gr, 4), "gg": round(gg, 4), "gb": round(gb, 4), "gl": round(gl, 4), "sat": round(sat, 4), "paper": round(s["paper"], 3), "hk": 1 if s["highkey"] else 0}

    # ---- filters
    def color_filter(self, still: Optional[str] = None) -> str:
        c = self.correction(still)
        if all(abs(c[k] - 1.0) < 0.004 for k in ("gr", "gg", "gb", "gl", "sat")):
            return ""
        return f"eq=gamma={c['gl']:.4f}:gamma_r={c['gr']:.4f}:gamma_g={c['gg']:.4f}:gamma_b={c['gb']:.4f}:saturation={c['sat']:.4f}"

    def finish_filter(self, still: Optional[str] = None) -> str:
        """NOTE ffmpeg's vignette angle: SMALLER = weaker (PI/5 = 0.63 already drops the corners of a white picture to grey 99/255)."""
        w = max(0.0, min(1.0, (self.paper(still) - 0.15) / 0.4)) if still else 0.0       # white-background picture: a vignette turns the paper grey at the corners, so it nearly disappears
        ang = max(0.05, self.vignette_angle * (1.0 - 0.65 * w))
        parts = [f"eq=contrast={self.contrast:.3f}:saturation={self.saturation:.3f}", f"vignette={ang:.4f}:eval=init"]
        if self.grain > 0:
            parts.append(f"noise=alls={int(self.grain)}:allf=t")
        return ",".join(parts)

    def filter_for(self, still: Optional[str] = None) -> str:
        """Per-still correction + the shared finish, one comma-joined chain (no leading/trailing comma, never empty)."""
        return ",".join(p for p in (self.color_filter(still), self.finish_filter(still)) if p)

    # ---- diagnostics
    def spread(self) -> dict:
        """How different the corrected stills still are (0 = identical): max cast/exposure/sat correction applied."""
        if not self.per_still:
            return {}
        v = list(self.per_still.values())
        return {k: round(max(abs(x[k] - 1.0) for x in v), 4) for k in ("gr", "gg", "gb", "gl", "sat")}


def compute_project_grade(stills: Sequence[str], max_n: int = 400, style: Optional[dict] = None) -> ProjectGrade:
    """Measure the stills once. `style` (optional) overrides contrast/saturation/vignette_angle/grain (project-wide looks)."""
    import numpy as np
    paths = [str(p) for p in dict.fromkeys(stills) if p]
    if len(paths) > max_n:
        step = len(paths) / float(max_n)
        paths = [paths[int(i * step)] for i in range(max_n)]
    st = {p: _stats(p) for p in paths}
    ok = {p: s for p, s in st.items() if s}
    g = ProjectGrade(stills=len(ok), **{k: v for k, v in (style or {}).items() if k in ("contrast", "saturation", "vignette_angle", "grain")})
    if not ok:
        return g
    def ref_of(vals):
        med = lambda f: float(np.median([f(v) for v in vals]))
        return {"rgb": [med(lambda v, i=i: v["rgb"][i]) for i in range(3)], "wp": [med(lambda v, i=i: v["wp"][i]) for i in range(3)],
                "luma": med(lambda v: v["luma"]), "clum": med(lambda v: v["clum"]), "csat": med(lambda v: v["csat"]), "n": len(vals)}
    allv = list(ok.values())
    hi = [v for v in allv if v["highkey"]] or allv
    lo = [v for v in allv if not v["highkey"]] or allv
    g.ref = {"hi": ref_of(hi), "lo": ref_of(lo), "luma": float(np.median([v["luma"] for v in allv])), "highkey_share": round(sum(v["highkey"] for v in allv) / len(allv), 3)}
    for p, s in ok.items():
        g.per_still[p] = g._from_stats(s)
    return g


def save(g: ProjectGrade, path: str) -> None:
    Path(path).write_text(json.dumps(g.to_dict(), indent=1), encoding="utf-8")


def load(path: str) -> Optional[ProjectGrade]:
    try:
        return ProjectGrade.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None
