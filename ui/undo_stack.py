"""Lightweight command-pattern undo/redo (Semantic YT Studio 2.0 — Phase 2).

Stores small (do, undo) closures, not full-project snapshots — a timeline
edit captures only the handful of numbers it changed, not the whole plan.
In-memory / per-session only (never persisted, never touches background
generation state — the pipeline reads editorial_plan.json fresh each run).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class Command:
    label: str
    do: Callable[[], None]
    undo: Callable[[], None]


class UndoStack:
    def __init__(self, max_depth: int = 200) -> None:
        self._undo: List[Command] = []
        self._redo: List[Command] = []
        self._max_depth = max_depth
        self._on_change: Optional[Callable[[], None]] = None

    def bind_on_change(self, callback: Callable[[], None]) -> None:
        """Called after any push/undo/redo — a view uses this to repaint
        and to refresh a save-state indicator, without this module knowing
        anything about Tk."""
        self._on_change = callback

    def push(self, command: Command, *, run: bool = True) -> None:
        """Record a command. `run=True` (default) also executes command.do()
        — pass False if the caller already applied the change and only
        wants it recorded for undo."""
        if run:
            command.do()
        self._undo.append(command)
        if len(self._undo) > self._max_depth:
            self._undo.pop(0)
        self._redo.clear()
        self._notify()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> Optional[str]:
        if not self._undo:
            return None
        cmd = self._undo.pop()
        cmd.undo()
        self._redo.append(cmd)
        self._notify()
        return cmd.label

    def redo(self) -> Optional[str]:
        if not self._redo:
            return None
        cmd = self._redo.pop()
        cmd.do()
        self._undo.append(cmd)
        self._notify()
        return cmd.label

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
        self._notify()

    def _notify(self) -> None:
        if self._on_change is not None:
            try:
                self._on_change()
            except Exception:
                pass
