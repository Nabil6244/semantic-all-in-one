"""Effect budget (phase F of the upgrade plan; opt-in with DirectorOptions.budget): one place that decides how often each motion effect may appear in a whole video, and which variant comes next.

Without it every pass only keeps its own minimum gap (15 s between stamps, 12 s between count-ups ...), which is fine for a minute and a habit over thirty. With it each effect also has a window:
at most one stamp per 120 s, one plate per 180 s, one count-up per 90 s, one cross-out per 180 s and one map line per 150 s, counted over the whole video in spoken order. Variants rotate in order
(stamp: slam, drop, soft press; plate: slide down, slide in from the right, fade and rise), so the same entrance is never used twice running.
Everything is a function of the plan's own times and order: no clock, no randomness."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

WINDOW_S: Dict[str, float] = {"stamp": 120.0, "plate": 180.0, "count": 90.0, "cross": 180.0, "line": 150.0}
VARIANTS: Dict[str, int] = {"stamp": 3, "plate": 3}


class Budget:
    def __init__(self, windows: Optional[Dict[str, float]] = None) -> None:
        self.windows = dict(WINDOW_S if windows is None else windows)
        self.used: Dict[str, List[float]] = {k: [] for k in self.windows}
        self.refused: List[Dict[str, Any]] = []

    def allow(self, kind: str, t: float) -> Tuple[bool, str]:
        last = self.used[kind][-1] if self.used[kind] else None
        if last is not None and t - last < self.windows[kind] - 1e-9:
            why = f"{kind}: {t - last:.0f} s after the previous one (budget: one per {self.windows[kind]:.0f} s)"
            self.refused.append({"kind": kind, "t": round(t, 3), "why": why})
            return False, why
        return True, ""

    def variant(self, kind: str) -> int:
        return len(self.used[kind]) % VARIANTS.get(kind, 1)

    def commit(self, kind: str, t: float) -> None:
        self.used[kind].append(round(float(t), 3))

    def summary(self) -> Dict[str, Any]:
        return {"windows_s": dict(self.windows), "used": {k: list(v) for k, v in self.used.items()}, "counts": {k: len(v) for k, v in self.used.items()}, "refused": list(self.refused)}
