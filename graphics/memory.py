"""Graphics memory — recent roles/concepts for repetition & density control."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set


@dataclass
class MemoryEntry:
    graphic_id: str
    role: str
    concept_key: str
    start: float
    importance: str
    scene_number: str = ""


@dataclass
class GraphicsMemory:
    """Rolling memory of recently planned graphics (deterministic)."""

    entries: List[MemoryEntry] = field(default_factory=list)
    window_s: float = 45.0
    max_entries: int = 24

    def concept_key(self, *, role: str, text: str, secondary: str = "") -> str:
        primary = (text or "").strip().lower()
        sec = (secondary or "").strip().lower()
        blob = f"{role}|{primary}|{sec}".strip("|")
        return blob[:120]

    def prune(self, now: float) -> None:
        cut = float(now) - float(self.window_s)
        self.entries = [e for e in self.entries if e.start >= cut]
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries :]

    def record(
        self,
        *,
        graphic_id: str,
        role: str,
        text: str,
        secondary: str = "",
        start: float,
        importance: str = "medium",
        scene_number: str = "",
    ) -> None:
        self.prune(start)
        self.entries.append(
            MemoryEntry(
                graphic_id=graphic_id,
                role=str(role or "").upper(),
                concept_key=self.concept_key(role=role, text=text, secondary=secondary),
                start=float(start),
                importance=str(importance or "medium").lower(),
                scene_number=str(scene_number or ""),
            )
        )

    def recent_roles(self, now: float, *, within_s: float = 30.0) -> Set[str]:
        self.prune(now)
        return {e.role for e in self.entries if now - e.start <= within_s}

    def concept_seen_recently(
        self,
        *,
        role: str,
        text: str,
        secondary: str = "",
        now: float,
        within_s: float = 40.0,
    ) -> bool:
        key = self.concept_key(role=role, text=text, secondary=secondary)
        primary = key.split("|")[1] if "|" in key else ""
        self.prune(now)
        for e in self.entries:
            if now - e.start > within_s:
                continue
            if e.concept_key == key:
                return True
            parts = e.concept_key.split("|")
            if e.role == str(role or "").upper() and len(parts) > 1 and parts[1] == primary and primary:
                return True
        return False

    def consecutive_graphic_scenes(self, scene_numbers: List[str]) -> int:
        seen = {e.scene_number for e in self.entries if e.scene_number}
        run = 0
        for sn in reversed(scene_numbers):
            if sn in seen:
                run += 1
            else:
                break
        return run

    def graphics_in_window(self, now: float, *, within_s: float = 30.0) -> int:
        self.prune(now)
        return sum(1 for e in self.entries if now - e.start <= within_s)

    def should_suppress(
        self,
        *,
        role: str,
        text: str,
        secondary: str = "",
        start: float,
        importance: str = "medium",
        priority: int = 2,
        consecutive_scenes: int = 0,
    ) -> Optional[str]:
        """Return reason string if this graphic should be dropped."""
        imp = str(importance or "medium").lower()
        if imp in ("high", "critical"):
            if self.concept_seen_recently(
                role=role, text=text, secondary=secondary, now=start, within_s=12.0
            ):
                return "repeated_concept_too_soon"
            return None

        if self.concept_seen_recently(
            role=role, text=text, secondary=secondary, now=start, within_s=40.0
        ):
            return "repeated_concept"

        if self.graphics_in_window(start, within_s=30.0) >= 3 and imp not in (
            "high",
            "critical",
        ):
            return "density_window"

        if consecutive_scenes >= 2 and imp not in ("high", "critical"):
            return "consecutive_scenes"

        recent_same = [
            e
            for e in self.entries
            if e.role == str(role or "").upper() and start - e.start <= 20.0
        ]
        if len(recent_same) >= 2 and imp == "low":
            return "role_repetition"

        return None
