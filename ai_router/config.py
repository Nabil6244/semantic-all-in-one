"""Which route serves which task, and where the settings live. The model names are data, not code: they come from the user's settings with
defaults here, so they can change when the providers change theirs."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Mapping, Optional

from .providers import GeminiProvider, GroqProvider
from .router import AIRouter, Route

DEFAULT_MODELS = {
    "gemini_director": "",            # empty = the app's Gemini default (GEMINI_MODEL or the built-in default)
    "gemini_second": "gemini-3.5-flash",
    "gemini_critic": "gemini-3.5-flash",
    "groq_director": "llama-3.3-70b-versatile",
    "groq_critic": "llama-3.3-70b-versatile",
    "groq_repair": "llama-3.3-70b-versatile",
}


def model_settings(settings: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    saved = (settings or {}).get("ai_models") or {}
    return {k: (str(saved.get(k) or "").strip() or v) for k, v in DEFAULT_MODELS.items()}


def _gemini_default() -> str:
    from visual_director.llm import DEFAULT_GEMINI_MODEL

    return os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL


def default_routes(settings: Optional[Mapping[str, Any]] = None) -> Dict[str, List[Route]]:
    m = model_settings(settings)
    gem_main = m["gemini_director"] or _gemini_default()
    groq_on = bool((settings or {}).get("groq_enabled", True))
    gem_on = bool((settings or {}).get("gemini_enabled", True))
    d = dict(thinking="auto")                     # sized to the request by the Gemini provider
    out: Dict[str, List[Route]] = {"director": [], "critic": [], "repair": [], "utility": []}
    if gem_on:
        out["director"] += [Route("gemini", gem_main, **d)]
        if m["gemini_second"] and m["gemini_second"] != gem_main:
            out["director"] += [Route("gemini", m["gemini_second"], **d)]
    if groq_on:
        out["director"] += [Route("groq", m["groq_director"], thinking="medium", max_output=8000, timeout=180.0)]
        out["critic"] += [Route("groq", m["groq_critic"], max_output=4096, timeout=120.0)]
        out["repair"] += [Route("groq", m["groq_repair"], max_output=8000, timeout=120.0)]
        out["utility"] += [Route("groq", m["groq_repair"], max_output=4096, timeout=90.0)]
    if gem_on:
        gc = m["gemini_critic"] or gem_main
        out["critic"] += [Route("gemini", gc, thinking="low", max_output=8192, timeout=150.0)]
        out["repair"] += [Route("gemini", gc, thinking="low", max_output=16384, timeout=180.0)]
        out["utility"] += [Route("gemini", gc, thinking="low", max_output=4096, timeout=90.0)]
    return out


def router_from_settings(settings: Optional[Mapping[str, Any]] = None, *, state_dir: Any = None) -> AIRouter:
    s = dict(settings or {})
    providers = {"gemini": GeminiProvider(s), "groq": GroqProvider(str(s.get("groq_api_key") or ""))}
    return AIRouter(default_routes(s), providers, state_dir=state_dir)


def providers_configured(settings: Optional[Mapping[str, Any]] = None) -> Dict[str, bool]:
    """Which providers have a key AND are switched on (a provider the user disabled is not counted)."""
    from visual_director.llm import gemini_configured

    s = dict(settings or {})
    return {"gemini": bool(s.get("gemini_enabled", True)) and gemini_configured(s),
            "groq": bool(s.get("groq_enabled", True)) and bool(str(s.get("groq_api_key") or os.environ.get("GROQ_API_KEY") or "").strip())}


MISSING_AI_KEY = "No AI provider is set up. Add a Gemini API key (or a Groq API key) in Settings."
