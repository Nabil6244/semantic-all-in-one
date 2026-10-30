"""Semantic Intelligence Engine: decides, per planning decision, between a cached answer, Gemini, and the deterministic rules, and never lets
rendering depend on Gemini. See core.py (cache, batches, telemetry, the ai_planning setting), editorial.py, ambience.py, sfx.py."""
from .core import (  # noqa: F401
    DecisionCache, Telemetry, TELEMETRY, ai_mode, ai_allowed, run_batches, stable_key,
)
