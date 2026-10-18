"""Local, offline CSV Generator: script -> scene plan -> CSV in the exact schema an existing workflow accepts.

No external AI API, no network. The backend is rule-based (``engine.RuleBasedBackend``); ``engine.Backend`` is the seam where a
packaged local language model could be added later. See engine.py for what the rule-based planner can and cannot do.
"""

from .engine import (GenerationOptions, GenerationResult, SUPPORTED_STYLES, UNSUPPORTED_STYLES, generate, style_scope_mode,
                     to_csv_text)
from .validate import Issue, validate_rows

__all__ = ["GenerationOptions", "GenerationResult", "SUPPORTED_STYLES", "UNSUPPORTED_STYLES", "generate", "to_csv_text", "Issue",
           "validate_rows", "style_scope_mode"]
