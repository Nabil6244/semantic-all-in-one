"""The one diagnostic record every ancient_texts check returns.

severity:
  hard    a Required rule is broken (accuracy, fabricated content, invalid reference, paid call, protected file ...)
  soft    a style target is missed (proportions, rhythm, loudness band ...): reported, never silently repaired
  review  something only a person can judge (an interpretation, an attribution, whether a picture fits)
"""

from __future__ import annotations

import dataclasses
from typing import Iterable, List

SEVERITIES = ("hard", "soft", "review")


@dataclasses.dataclass(frozen=True)
class Issue:
    code: str
    severity: str
    message: str
    ref: str = ""            # the record it is about: a claim id, a sentence id, a scene number, a file

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f"unknown severity {self.severity!r}")

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class ValidationError(ValueError):
    """Raised when input cannot be used at all (malformed file, wrong types). Carries every problem found, not just the first."""

    def __init__(self, what: str, problems: Iterable[str]):
        self.problems = list(problems)
        super().__init__(f"{what}: " + "; ".join(self.problems))


def split(issues: Iterable[Issue]) -> dict:
    out: dict = {s: [] for s in SEVERITIES}
    for i in issues:
        out[i.severity].append(i)
    return out


def summary(issues: List[Issue]) -> str:
    s = split(issues)
    return f"{len(s['hard'])} hard failure(s), {len(s['soft'])} soft deviation(s), {len(s['review'])} item(s) for review"
