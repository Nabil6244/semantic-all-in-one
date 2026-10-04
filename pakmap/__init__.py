"""pakMap: turn a one-row-per-event CSV plus the narration's word timestamps into a render spec
for pakmap-engine (the Node renderer). Pure Python (stdlib) apart from map_scene's place data;
checks that belong to the renderer are run through the renderer's own validator so the rules live
in one place. See docs/pakmap/ for the plan and the specification."""

from .compile import CompileError, CompileResult, compile_csv, compile_rows
from .schema import CsvError, parse_csv

__all__ = ["CompileError", "CompileResult", "CsvError", "compile_csv", "compile_rows", "parse_csv"]
