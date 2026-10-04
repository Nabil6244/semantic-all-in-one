"""Providers behind one interface: complete(system, user, ...) -> Completion, or raise ProviderError. Provider differences end here: the
rest of Hybrid Map receives plain text (JSON) and never knows which service wrote it."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

import requests

from .errors import ProviderError

GROQ_BASE = "https://api.groq.com/openai/v1"


@dataclass
class Completion:
    text: str
    usage: Dict[str, Any] = field(default_factory=dict)      # input / output / reasoning tokens when the service reports them
    limits: Dict[str, Any] = field(default_factory=dict)     # remaining requests / tokens and reset hints when the service reports them


class GeminiProvider:
    name = "gemini"

    def __init__(self, settings: Optional[Mapping[str, Any]] = None):
        self.settings = dict(settings or {})

    def configured(self) -> bool:
        from visual_director.llm import gemini_configured

        return gemini_configured(self.settings)

    def complete(self, system: str, user: str, *, model: str, thinking: str = "low", max_output: int = 16384, timeout: float = 180.0) -> Completion:
        from visual_director.llm import GeminiLLM, LLMError

        if thinking == "auto":      # the same size-based tuning the app's Visual Director uses: a short script does not pay for heavy thinking
            from visual_director.director import gemini_plan_settings

            opts = gemini_plan_settings(len(user.split()) + len(system.split()))
            thinking, max_output, timeout = opts["thinking_level"], opts["max_output_tokens"], opts["timeout"]
        llm = GeminiLLM(settings=self.settings, model=model, timeout=timeout)   # the one Gemini client, with its key pool
        try:
            text = llm.complete(system, user, thinking_level=thinking, max_output_tokens=max_output)
        except LLMError as exc:
            raise ProviderError(str(exc), status=exc.status, retry_after=exc.retry_after, quota_id=exc.quota_id) from exc
        return Completion(text=text, usage=dict(llm.last_usage or {}))

    def test(self, model: str) -> list:
        """One tiny request per configured key. Returns [{alias, state, model, latency_ms, summary}] — aliases only, never key text."""
        from visual_director.llm import GeminiLLM, LLMError, resolve_gemini_api_keys

        out = []
        for n, key in enumerate(resolve_gemini_api_keys(self.settings), 1):
            llm = GeminiLLM(api_key=key, model=model, timeout=30.0)
            t0 = time.time()
            try:
                llm.complete("Reply with the JSON {\"ok\": true}.", "ping", thinking_level="low", max_output_tokens=1024)
                state, summary = "READY", "answered"
            except LLMError as exc:
                from .errors import AUTH, BAD_MODEL, DENIED, QUOTA_HARD, RATE_TEMP, classify

                f = classify(exc.status, str(exc), exc.retry_after, exc.quota_id)
                state = {RATE_TEMP: "RATE LIMITED", QUOTA_HARD: "QUOTA EXHAUSTED", DENIED: "ACCESS DENIED", AUTH: "INVALID", BAD_MODEL: "ERROR"}.get(f.kind, "ERROR")
                summary = f.summary if state != "ERROR" else (str(exc)[:90])
            out.append({"alias": f"key {n}", "state": state, "model": model, "latency_ms": int((time.time() - t0) * 1000), "summary": summary, "tested": time.strftime("%H:%M:%S")})
        return out


class GroqProvider:
    name = "groq"

    def __init__(self, api_key: str = "", base_url: str = ""):
        self.api_key = (api_key or os.environ.get("GROQ_API_KEY") or "").strip()
        self.base_url = (base_url or os.environ.get("GROQ_BASE_URL") or GROQ_BASE).rstrip("/")

    def configured(self) -> bool:
        return bool(self.api_key)

    def complete(self, system: str, user: str, *, model: str, thinking: str = "low", max_output: int = 8192, timeout: float = 120.0) -> Completion:
        if not self.api_key:
            raise ProviderError("Groq API key is not configured", status=401)
        body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "response_format": {"type": "json_object"}, "temperature": 0.3, "max_completion_tokens": int(max_output)}
        try:
            resp = requests.post(f"{self.base_url}/chat/completions", headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                                 data=json.dumps(body), timeout=timeout)
        except requests.RequestException as exc:
            raise ProviderError(f"Groq request failed: {exc}") from exc
        limits = _groq_limits(getattr(resp, "headers", {}) or {})
        if resp.status_code >= 400:
            message, retry = _groq_error(resp)
            raise ProviderError(message, status=resp.status_code, retry_after=retry)
        try:
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Groq returned an answer that could not be read", status=502) from exc
        u = data.get("usage") or {}
        return Completion(text=str(text or "").strip(), usage={"input": u.get("prompt_tokens"), "output": u.get("completion_tokens"), "reasoning": None}, limits=limits)

    def test(self, model: str) -> list:
        from .errors import AUTH, BAD_MODEL, DENIED, QUOTA_HARD, RATE_TEMP, classify

        t0 = time.time()
        try:
            self.complete("Reply with the JSON {\"ok\": true}.", "ping", model=model, max_output=64, timeout=30.0)
            state, summary = "READY", "answered"
        except ProviderError as exc:
            f = classify(exc.status, str(exc), exc.retry_after, exc.quota_id)
            state = {RATE_TEMP: "RATE LIMITED", QUOTA_HARD: "QUOTA EXHAUSTED", DENIED: "ACCESS DENIED", AUTH: "INVALID", BAD_MODEL: "ERROR"}.get(f.kind, "ERROR")
            summary = f.summary if state != "ERROR" else str(exc)[:90]
        return [{"alias": "Groq key", "state": state, "model": model, "latency_ms": int((time.time() - t0) * 1000), "summary": summary, "tested": time.strftime("%H:%M:%S")}]


def _groq_limits(headers: Mapping[str, Any]) -> Dict[str, Any]:
    keep = {"x-ratelimit-remaining-requests": "remaining_requests", "x-ratelimit-remaining-tokens": "remaining_tokens",
            "x-ratelimit-reset-requests": "reset_requests", "x-ratelimit-reset-tokens": "reset_tokens"}
    return {v: headers.get(k) for k, v in keep.items() if headers.get(k) is not None}


def _groq_error(resp: Any) -> tuple:
    message, retry = "", None
    try:
        message = str((resp.json().get("error") or {}).get("message") or "")
    except (ValueError, AttributeError):
        message = (getattr(resp, "text", "") or "")[:200]
    try:
        ra = (getattr(resp, "headers", {}) or {}).get("retry-after")
        retry = float(ra) if ra is not None else None
    except (TypeError, ValueError):
        retry = None
    return f"Groq API error: {message or 'HTTP ' + str(resp.status_code)}", retry
