"""One place that decides which AI provider and model answers which kind of request, and what to do when one cannot."""

from .errors import AllRoutesUnavailable, Failure, ProviderError, classify
from .router import AIRouter, Route, RouterResult
from .config import MISSING_AI_KEY, default_routes, providers_configured, router_from_settings

__all__ = ["AIRouter", "AllRoutesUnavailable", "Failure", "ProviderError", "Route", "RouterResult", "classify", "default_routes", "providers_configured", "router_from_settings", "MISSING_AI_KEY"]
