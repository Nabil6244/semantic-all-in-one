"""Visual rhythm tracker — soft anti-monotony across neighboring scenes."""

from __future__ import annotations

import dataclasses
from typing import List


@dataclasses.dataclass
class RhythmState:
    recent_kinds: List[str] = dataclasses.field(default_factory=list)
    recent_needs: List[str] = dataclasses.field(default_factory=list)
    recent_flow: int = 0
    window: int = 5

    def video_streak(self) -> int:
        streak = 0
        for k in reversed(self.recent_kinds):
            if k == "video":
                streak += 1
            else:
                break
        return streak

    def image_streak(self) -> int:
        streak = 0
        for k in reversed(self.recent_kinds):
            if k == "image":
                streak += 1
            else:
                break
        return streak

    def rhythm_video_adjustment(self) -> float:
        """Negative = push toward image; positive = toward video."""
        adj = 0.0
        vs = self.video_streak()
        ims = self.image_streak()
        if vs >= 4:
            adj -= 0.22
        elif vs >= 3:
            adj -= 0.12
        if ims >= 4:
            adj += 0.18
        elif ims >= 3:
            adj += 0.1
        return adj

    def record(self, visual_kind: str, visual_need: str, is_flow: bool) -> None:
        self.recent_kinds.append(visual_kind)
        self.recent_needs.append(visual_need)
        if len(self.recent_kinds) > self.window:
            self.recent_kinds.pop(0)
        if len(self.recent_needs) > self.window:
            self.recent_needs.pop(0)
        if is_flow:
            self.recent_flow += 1
        else:
            self.recent_flow = max(0, self.recent_flow - 1)
