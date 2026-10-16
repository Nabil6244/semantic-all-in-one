"""What If dry run: every stage Generate runs before the pictures and the render, with nothing fetched and nothing rendered.

    plan (the shot CSV repaired in memory, whatif/heal.py) -> compile the spec -> the page's own checks in node
    (whatif-engine/tools/check_spec.mjs: shot repairs, every layer made and drawn on a mock canvas)

`dry_run` returns what was repaired and what would stop. Nothing here may stop: the stress test (whatif/stress.py) runs this on
hundreds of broken plans and counts the stops, which must stay at zero. "Check plan" in the app shows the same report.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class DryRun:
    stops: List[str] = field(default_factory=list)          # stage: message -- anything that would end Generate
    repairs: List[str] = field(default_factory=list)        # what was fixed or left out on the way
    plan: Any = None
    spec: Optional[Dict[str, Any]] = None

    @property
    def ok(self) -> bool:
        return not self.stops


def engine_dir() -> Path:
    from .engine_runner import engine_dir as _ed

    return _ed()


def node_bin() -> str:
    try:
        from map_scene.render import _node

        return _node()
    except Exception:
        return "node"


def check_specs(paths: Sequence[Path], timeout: float = 600.0) -> Dict[str, Dict[str, Any]]:
    """Run the page's checks on spec files (one node process for all) -> path -> {"repairs": [...], "fatal": str | None}."""
    out: Dict[str, Dict[str, Any]] = {}
    if not paths:
        return out
    eng = engine_dir()
    r = subprocess.run([node_bin(), str(eng / "tools" / "check_spec.mjs"), *map(str, paths)], cwd=str(eng), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    for line in r.stdout.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        out[d["spec"]] = d
    for p in paths:
        if str(p) not in out:
            out[str(p)] = {"repairs": [], "fatal": f"the checker gave no answer ({(r.stderr or '').strip()[-300:] or f'exit {r.returncode}'})"}
    return out


def dry_run(words: Sequence[Any], script: str, duration: float, title: str = "", csv_text: str = "", *, flow_video: "bool | str" = "both",
            engine: bool = True) -> DryRun:
    from . import compile as wc
    from .app_integration import plan_from

    res = DryRun()
    try:
        res.plan = plan_from(words, script, duration, title, csv_text, flow_video=flow_video)
    except Exception as exc:       # noqa: BLE001
        res.stops.append(f"plan: {exc!r}")
        return res
    res.repairs += [n for n in res.plan.notes if "left out" in n or " read as " in n or "repaired" in n or "instead" in n]
    try:
        res.spec = wc.compile_spec(res.plan, media_dir=None, title=title)
    except Exception as exc:       # noqa: BLE001
        res.stops.append(f"compile: {exc!r}")
        return res
    if engine:
        with tempfile.TemporaryDirectory(prefix="whatif_check_") as tmp:
            p = Path(tmp) / "spec.json"
            p.write_text(json.dumps(res.spec), encoding="utf-8")
            try:
                got = check_specs([p])[str(p)]
            except Exception as exc:   # noqa: BLE001 -- no node here: the check is skipped, never a stop
                res.repairs.append(f"engine check skipped ({exc!r})")
                return res
            res.repairs += [f"renderer: {m}" for m in got.get("repairs", [])]
            if got.get("fatal"):
                res.stops.append(f"renderer: {got['fatal']}")
    return res
