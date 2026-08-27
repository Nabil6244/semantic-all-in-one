"""Minimal LLM provider interface. Uses `requests` only — no vendor SDK."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Mapping, Optional, Protocol

import requests

MISSING_GEMINI_KEY = (
    "Gemini API key is not configured. Add GEMINI_API_KEY to enable AI Script mode."
)

DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
DEFAULT_GEMINI_BASE = "https://generativelanguage.googleapis.com"

_SECRET_RE = re.compile(
    r"(?:AIza[0-9A-Za-z_-]{20,}|x-goog-api-key\s*[:=]\s*\S+|api[_-]?key\s*[:=]\s*\S+)",
    re.IGNORECASE,
)


class LLMError(RuntimeError):
    pass


class LLMProvider(Protocol):
    def complete(self, system: str, user: str) -> str:
        ...


class StaticLLM:
    """Test/double: returns a fixed string."""

    def __init__(self, response: str):
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.response


def resolve_gemini_api_key(settings: Optional[Mapping[str, Any]] = None) -> str:
    env = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if env:
        return env
    if settings:
        return str(settings.get("gemini_api_key") or "").strip()
    return ""


def gemini_configured(settings: Optional[Mapping[str, Any]] = None) -> bool:
    return bool(resolve_gemini_api_key(settings))


def _redact_secrets(text: str) -> str:
    return _SECRET_RE.sub("[redacted]", text or "")


def format_gemini_api_error(status_code: int, body: str, model: str) -> str:
    """Turn a Gemini HTTP error into a short UI-safe message (never includes the API key)."""
    cleaned = _redact_secrets((body or "").strip())
    message = ""
    status = ""
    try:
        data = json.loads(cleaned)
        err = data.get("error") if isinstance(data, dict) else None
        if isinstance(err, dict):
            message = str(err.get("message") or "").strip()
            status = str(err.get("status") or "").strip()
        elif isinstance(data, dict):
            message = str(data.get("message") or "").strip()
    except ValueError:
        message = cleaned.splitlines()[0] if cleaned else ""

    message = _redact_secrets(message)
    lower = f"{message} {status}".lower()
    model_gone = (
        status_code == 404
        or status.upper() == "NOT_FOUND"
        or "no longer available" in lower
        or "not found" in lower
        or "is not found" in lower
    )
    if model_gone and ("model" in lower or status_code == 404):
        return f"Gemini API error: model {model} unavailable"
    if message:
        short = message.replace("\n", " ")
        if len(short) > 240:
            short = short[:237] + "..."
        return f"Gemini API error: {short}"
    return f"Gemini API error: HTTP {status_code}"


def extract_gemini_text(payload: dict) -> str:
    """Pull concatenated text parts from a generateContent JSON body.

    Gemini 3.x may prepend thought parts; those are skipped so structured JSON stays intact.
    """
    if not isinstance(payload, dict):
        raise LLMError("Gemini returned an unexpected payload")
    prompt_fb = ((payload.get("promptFeedback") or {}).get("blockReason")) if isinstance(
        payload.get("promptFeedback"), dict
    ) else None
    candidates = payload.get("candidates")
    if not candidates:
        if prompt_fb:
            raise LLMError(f"Gemini blocked the prompt ({prompt_fb})")
        raise LLMError("Gemini returned no candidates")
    first = candidates[0] if isinstance(candidates[0], dict) else {}
    finish = str(first.get("finishReason") or "")
    parts = ((first.get("content") or {}).get("parts")) or []
    texts = []
    for p in parts:
        if not isinstance(p, dict):
            continue
        if p.get("thought"):
            continue
        t = str(p.get("text") or "")
        if t:
            texts.append(t)
    text = "".join(texts).strip()
    if not text:
        if finish and finish not in ("STOP", "FINISH_REASON_UNSPECIFIED"):
            raise LLMError(f"Gemini returned empty content ({finish})")
        raise LLMError("Gemini returned empty content")
    return text


class GeminiLLM:
    """Gemini generateContent over HTTP. Default model: gemini-3.6-flash."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 300.0,
        settings: Optional[Mapping[str, Any]] = None,
    ):
        self.api_key = resolve_gemini_api_key(settings) if api_key is None else str(api_key).strip()
        self.model = model or os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
        self.base_url = (base_url or os.environ.get("GEMINI_BASE_URL") or DEFAULT_GEMINI_BASE).rstrip("/")
        self.timeout = timeout

    def complete(
        self,
        system: str,
        user: str,
        *,
        thinking_level: str = "medium",
        max_output_tokens: int = 65536,
    ) -> str:
        if not self.api_key:
            raise LLMError(MISSING_GEMINI_KEY)
        url = f"{self.base_url}/v1beta/models/{self.model}:generateContent"
        # Gemini 3.6 Flash ignores custom temperature/top_p/top_k (and future
        # versions may reject them). Structured JSON is requested via MIME type.
        # thinkingLevel replaces the older thinkingBudget field.
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "maxOutputTokens": max(1024, int(max_output_tokens)),
                "thinkingConfig": {
                    "thinkingLevel": thinking_level,
                },
            },
        }
        try:
            resp = requests.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key,
                },
                data=json.dumps(payload),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise LLMError(f"Gemini request failed: {exc}") from exc
        if resp.status_code >= 400:
            raise LLMError(format_gemini_api_error(resp.status_code, resp.text or "", self.model))
        try:
            data = resp.json()
        except ValueError as exc:
            raise LLMError("Gemini returned non-JSON") from exc
        return extract_gemini_text(data)
