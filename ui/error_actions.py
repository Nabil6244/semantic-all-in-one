"""What the "Generation failed" dialog offers, decided from the error text.

Real logs showed the same CSV problem hit three Generate presses in a row ("row 31: vo_anchor ... is only spoken before the
previous row's words"): the dialog's only action was Retry, which re-runs Generate on the unchanged CSV. A plan/CSV error is
fixed in the CSV, so for those the dialog offers a ready-to-paste fix prompt instead of Retry.
"""

from __future__ import annotations

import re
from typing import Iterable, List

# A line that names a CSV row / beat / shot / anchor: the plan itself must change.
_PLAN_LINE = re.compile(
    r"^\s*(?:row\s+\d+\b|beat\s+[\w.-]+\b|shot\s+[\w.-]+\b|layer\s+[\w.-]+\b|footage\s+[\w.-]+\b|vo_anchor\b|[\w ]*\.csv\b)"
    r"|\bvo_anchor\b|\bbeats?\.csv\b|\bthe plan (?:has|does not)\b",
    re.IGNORECASE,
)


def plan_problems(errors: Iterable[str]) -> List[str]:
    """The error lines that are about the CSV/plan (empty when the failure is something else: network, disk, engine)."""
    out: List[str] = []
    for raw in errors or ():
        for line in str(raw or "").splitlines():
            line = line.strip()
            if line and _PLAN_LINE.search(line):
                out.append(line)
    return out


def is_plan_error(errors: Iterable[str]) -> bool:
    """True when every non-empty error line is a plan/CSV problem: Retry would only fail the same way."""
    lines = [l.strip() for raw in (errors or ()) for l in str(raw or "").splitlines() if l.strip()]
    return bool(lines) and len(plan_problems(lines)) == len(lines)


def fix_prompt(style: str, errors: Iterable[str], limit: int = 40) -> str:
    """A prompt to paste into the AI that wrote the CSV, next to that CSV."""
    problems = plan_problems(errors)[:limit]
    more = max(0, len(plan_problems(errors)) - limit)
    lines = [
        f"The {style or 'video'} CSV you wrote does not pass the app's checks. Fix ONLY these problems and return the complete corrected CSV",
        "(same columns, same header, every other row unchanged). Every vo_anchor must be words the narrator really says, in script order.",
        "",
        "Problems:",
        *[f"- {p}" for p in problems],
    ]
    if more:
        lines.append(f"- ... and {more} more of the same kind")
    lines += ["", "The CSV:", "(paste the CSV here)"]
    return "\n".join(lines)
