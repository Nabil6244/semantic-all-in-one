"""Product Trailer style: a feature CSV + a music track -> a What If engine spec (kind "product" shots, pt_* text layers) -> mp4.
Plan: docs/product_trailer/PLAN.md. Rendering reuses whatif.engine_runner; nothing here edits the engine."""

from .csv_io import read_csv
from .planner import build_spec, plan_spec
from .render import render

__all__ = ["read_csv", "build_spec", "plan_spec", "render"]
