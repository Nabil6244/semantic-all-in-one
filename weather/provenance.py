"""Every number on screen keeps where it came from: the product, the place (grid point or station), when the source issued it
and when we fetched it. The numbers report lists each one, so a video can be checked against its sources line by line."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class Sourced:
    value: Any
    unit: str  # "F", "%", "" (text)
    product: str  # "NWS forecast", "NWS observation", "NWS alert", "GOES-East GeoColor"
    url: str  # the exact URL the value was read from
    where: str  # "FWD 89,104" (grid point), "KDFW" (station), "TX" (alert area)
    issued: str  # ISO time the source says it was issued/updated
    fetched: str  # ISO time we fetched it

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Sourced":
        return Sourced(**{k: d[k] for k in ("value", "unit", "product", "url", "where", "issued", "fetched")})


@dataclass
class NumbersReport:
    """What appears on screen, and where each number came from."""

    lines: List[Dict[str, Any]] = field(default_factory=list)

    def add(self, layer_id: str, label: str, shown: str, src: Sourced) -> None:
        self.lines.append({"layer": layer_id, "label": label, "shown": shown, **src.to_dict()})

    def to_text(self) -> str:
        out = ["Weather numbers report: every number on screen and its source", ""]
        for ln in self.lines:
            out.append(f"[{ln['layer']}] {ln['label']}: {ln['shown']}")
            out.append(f"    {ln['product']} at {ln['where']}, issued {ln['issued']}, fetched {ln['fetched']}")
            out.append(f"    {ln['url']}")
        return "\n".join(out) + "\n"
