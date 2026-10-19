"""The production job every style shares with the Export page: what is rendering, how far it is, and the verified output.

Normal video always led the user to the Export page and showed its progress there. Overscaled / Exp Solar, pakMap, Hybrid,
StarMap, What If and Weather each kept their own status line and left the user on whatever page they were on, and the Export
page said "Idle" during their renders. One ExportJob, started and finished by the app's generation tracking (which every
style already calls), gives every style the same production-to-export experience. Rendering engines stay separate.

`verify_output` is the one check before a run may say "video ready": the file exists, is not empty and was written by this run.
"""

from __future__ import annotations

import dataclasses
import os
import time
from pathlib import Path
from typing import Any, Optional

# A finished video is never this small; an empty or truncated container is.
MIN_OUTPUT_BYTES = 1024
# File-system timestamps can lag the clock slightly (network drives, FAT): tolerate it.
MTIME_SLACK_S = 5.0

STYLE_LABELS = {
    "normal": "Normal video", "overscaled": "Overscaled", "exp_solar": "Exp Solar", "pakmap": "pakMap", "hybrid": "Hybrid Map",
    "starmap": "StarMap", "whatif": "What If", "weather": "Weather",
}


@dataclasses.dataclass
class ExportJob:
    style: str
    started_at: float = dataclasses.field(default_factory=time.time)
    running: bool = True
    fraction: float = 0.0
    message: str = ""
    outcome: str = ""              # "", "completed", "failed", "cancelled"
    output_path: str = ""          # set only when verified
    problem: str = ""              # why a reported success was not accepted, or the failure message

    @property
    def label(self) -> str:
        return STYLE_LABELS.get(self.style, self.style.replace("_", " ").title())

    def progress(self, fraction: Any, message: str = "") -> None:
        try:
            f = float(fraction)
        except (TypeError, ValueError):
            return
        self.fraction = max(self.fraction if self.running else 0.0, min(1.0, max(0.0, f)))
        if message:
            self.message = str(message)

    def status_text(self) -> str:
        if self.running:
            pct = f" ({int(self.fraction * 100)}%)" if self.fraction > 0 else ""
            return f"{self.label}: {self.message or 'working'}{pct}"
        if self.outcome == "completed" and self.output_path:
            return f"{self.label}: done"
        if self.outcome == "cancelled":
            return f"{self.label}: cancelled, nothing exported"
        if self.outcome == "failed":
            return f"{self.label}: failed" + (f" ({self.problem})" if self.problem else "")
        return f"{self.label}: idle"


def verify_output(path: Any, started_at: Optional[float] = None) -> Optional[str]:
    """None when `path` is a usable finished video of this run; otherwise why not, in plain words."""
    if not path:
        return "the render reported no output file"
    p = Path(str(path))
    if not p.is_file():
        return f"the output file is missing ({p.name})"
    try:
        st = p.stat()
    except OSError as exc:
        return f"the output file cannot be read ({exc})"
    if st.st_size < MIN_OUTPUT_BYTES:
        return f"the output file is empty or cut short ({st.st_size} bytes)"
    if started_at is not None and st.st_mtime < float(started_at) - MTIME_SLACK_S:
        return "the output file is from an earlier render, not this one"
    if not os.access(p, os.R_OK):
        return "the output file cannot be read"
    return None


def failed_copy(result: Any, problem: str) -> Any:
    """The style's own result object, turned into a failure that names the problem (so the style's failure branch runs:
    its log line, status and error dialog), instead of a "video ready" for a file that is not there."""
    msg = f"The render finished but {problem}. Nothing was exported; Generate again."
    errors = [msg] + [str(e) for e in (getattr(result, "errors", None) or [])]
    if dataclasses.is_dataclass(result) and not isinstance(result, type):
        kw = {"ok": False}
        names = {f.name for f in dataclasses.fields(result)}
        if "errors" in names:
            kw["errors"] = errors
        return dataclasses.replace(result, **kw)
    try:
        result.ok = False
        result.errors = errors
    except Exception:
        pass
    return result
