"""A problem in one row never stops a StarMap render.

Reading the plan, matching it to the catalog (resolve) and compiling it each report problems row by row ("row 214: ...").
They used to stop Generate at the first stage that found one, so an author fixed a row, generated again, and met the next
one. Here each problem is repaired in a copy of the CSV held in memory (the author's file is never changed) and the stage
runs again:

  - a layer, card or clip row with a problem is left out (a card or clip keeps its Visual Plan scene number: numbers come
    from the author's own CSV, see `media_numbers`);
  - a beat row with a problem gets the smallest repair first: its visual action (launch, flyby ...) is left out, then
    its date and extra (most resolve problems are about the date or data); if the problem stays the beat is left out with its rows (the beat before it runs on until the next one);
  - a map_footage beat with no cards becomes a map beat; an unknown plan id or column is ignored.

Every repair is written to the notes, so the author sees what was left out and can fix the CSV for the next render.
Problems that name no row (no beats at all, not a StarMap CSV) still stop, as there is nothing to render.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Callable, Dict, List, Optional, Tuple

ROW = re.compile(r"^row (\d+):")
COLUMN = re.compile(r"^unknown column '([^']*)'")


class HealedCsv:
    """The CSV as rows, repaired in place. `notes` says what was changed and why."""

    def __init__(self, text: str):
        self.original = text
        body = text.lstrip("﻿")
        first = next((ln for ln in body.splitlines() if ln.strip()), "")
        # a CSV saved with semicolons or tabs (a spreadsheet's regional setting) is read as the same table, written back with commas
        delim = ";" if first.count(";") > first.count(",") and first.count(";") >= 3 else "\t" if first.count("\t") >= 3 else ","
        self.rows: List[List[str]] = list(csv.reader(io.StringIO(body), delimiter=delim))
        self.head = [c.strip().lower() for c in (self.rows[0] if self.rows else [])]
        self.notes: List[str] = []
        if delim != ",":
            self.notes.append(f"the CSV used {'semicolons' if delim == ';' else 'tabs'} between columns; read as a normal CSV")
        self._beat_done: Dict[int, set] = {}
        self._plan_tries: Dict[int, int] = {}

    def text(self) -> str:
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(self.rows)
        return buf.getvalue()

    def _cell(self, n: int, col: str) -> str:
        r = self.rows[n - 1] if 0 < n <= len(self.rows) else []
        i = self.head.index(col) if col in self.head else -1
        return r[i].strip() if 0 <= i < len(r) else ""

    def _set(self, n: int, col: str, value: str) -> None:
        if col not in self.head or not (0 < n <= len(self.rows)):
            return
        i, r = self.head.index(col), self.rows[n - 1]
        r.extend([""] * (i + 1 - len(r)))
        r[i] = value

    def _blank(self, n: int) -> None:
        self.rows[n - 1] = [""] * len(self.head)          # kept as an empty line: every later row keeps its number

    def _drop_beat(self, n: int, why: str) -> None:
        beat = self._cell(n, "beat")
        gone = [n]
        for k in range(2, len(self.rows) + 1):
            if k != n and beat and self._cell(k, "beat") == beat and self._cell(k, "row").lower() in ("layer", "card", "clip"):
                gone.append(k)
        for k in gone:
            self._blank(k)
        self.notes.append(f"row {n}: beat {beat or '?'} is left out of this render ({why}); the beat before it runs on until the next one. "
                          f"Fix the row in the CSV to bring it back")

    def _repair_beat(self, n: int, why: str) -> None:
        """The smallest repair not tried yet for this beat: its visual action, then its date and extra, then the beat itself."""
        steps = []
        if "has no card rows" in why and self._cell(n, "mode").lower() == "map_footage":
            steps.append(("mode", lambda: self._set(n, "mode", "map"), "a map_footage beat with no cards is drawn as a map beat"))
        if "has no clip rows" not in why:
            from .beat_csv import VISUAL_ACTIONS

            if self._cell(n, "type").lower() in VISUAL_ACTIONS:
                steps.append(("type", lambda: self._set(n, "type", ""), f"its {self._cell(n, 'type')} animation is left out, the beat is a plain map shot"))
            if self._cell(n, "date") or self._cell(n, "extra"):
                steps.append(("date", lambda: (self._set(n, "date", ""), self._set(n, "extra", "")), "its date and extra are ignored"))
        steps = [s for s in steps if s[0] not in self._beat_done.setdefault(n, set())]
        if steps:
            key, act, what = steps[0]
            self._beat_done[n].add(key)
            act()
            self.notes.append(f"row {n}: {what} ({why})")
        else:
            self._drop_beat(n, why)

    def fix(self, problems: List[str]) -> bool:
        """Repair what the problems name. False when none of them can be repaired (the caller then stops)."""
        changed, beats_done = False, set()
        for p in problems:
            if m := COLUMN.match(p):
                if m[1] in self.head:
                    self.rows[0][self.head.index(m[1])] = ""
                    self.head[self.head.index(m[1])] = ""
                    self.notes.append(f"column {m[1]!r} is not a StarMap column and is ignored")
                    changed = True
                continue
            if p.startswith("plan row:"):
                n = next((k for k in range(2, len(self.rows) + 1) if self._cell(k, "row").lower() == "plan"), 0)
                if n and self._cell(n, "id"):
                    self._set(n, "id", "")
                    self.notes.append(f"row {n}: {p[len('plan row: '):]}; the plan's mission id is ignored")
                    changed = True
                continue
            m = ROW.match(p)
            if not m:
                continue
            n = int(m[1])
            if not (1 < n <= len(self.rows)) or not any(c.strip() for c in self.rows[n - 1]):
                continue
            why = p[m.end():].strip()
            kind = self._cell(n, "row").lower()
            if kind in ("layer", "card", "clip") or (kind not in ("beat", "plan") and "cells but the header" in why):
                self._blank(n)
                self.notes.append(f"row {n}: left out of this render ({why})")
                changed = True
            elif kind == "plan":
                # smallest repair first: its id and date, then its extra; a plan row still refused is left out (it is optional)
                tries = self._plan_tries[n] = self._plan_tries.get(n, 0) + 1
                if tries == 1:
                    for col in ("id", "date"):
                        self._set(n, col, "")
                    self.notes.append(f"row {n}: the plan row's id and date are ignored ({why})")
                elif tries == 2:
                    self._set(n, "extra", "")
                    self.notes.append(f"row {n}: the plan row's extra is ignored ({why})")
                else:
                    self._blank(n)
                    self.notes.append(f"row {n}: the plan row is left out ({why})")
                changed = tries <= 3
            elif kind == "beat" and n not in beats_done:
                beats_done.add(n)
                changed = True
                self._repair_beat(n, why)
            elif kind not in ("beat",):
                self._blank(n)
                self.notes.append(f"row {n}: left out of this render ({why})")
                changed = True
        return changed


def media_numbers(text: str) -> Dict[int, str]:
    """CSV row -> Visual Plan scene number, from the author's own CSV (so a row left out never renumbers the rest)."""
    from .media import media_rows_from_csv

    return {m.row: m.scene_number for m in media_rows_from_csv(text)}


def heal_until_clean(healed: HealedCsv, attempt: Callable[[str], Tuple[object, List[str]]], log: Callable[[str], None],
                     limit: Optional[int] = None):
    """attempt(csv text) -> (result, problems). Repairs and retries until there are no problems; returns the last result
    and problems (non-empty only when they could not be repaired)."""
    rounds = limit or (2 * len(healed.rows) + 5)
    seen = len(healed.notes)
    result, problems = None, []
    for _ in range(rounds):
        result, problems = attempt(healed.text())
        if not problems or not healed.fix(problems):
            break
    for n in healed.notes[seen:]:
        log(f"[StarMap] repaired: {n}")
    return result, problems
