"""Explainer director (Milestone 4a): turns timed narration (and an optional script) into a Hybrid plan whose board beats are explainer clips, with maps and archive
pictures where the narration supports them. Deterministic rules, no network, no AI at plan time. See docs/explainer/explainer_director_spec.md."""
from .options import DirectorOptions
from .plan import direct

__all__ = ["DirectorOptions", "direct"]
