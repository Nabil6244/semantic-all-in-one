"""Minimal LLM provider interface. Uses `requests` only — no vendor SDK."""

from __future__ import annotations

import json
import os
import re
import threading
import time
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
    """A Gemini failure. `status` is the HTTP status when there was one, `retry_after` the seconds the service asked us to wait, and
    `quota_id` which limit was hit (for example one that names PerDay or PerMinute): the AI router classifies failures from these."""

    def __init__(self, message: str = "", status: Optional[int] = None, retry_after: Optional[float] = None, quota_id: str = ""):
        super().__init__(message)
        self.status, self.retry_after, self.quota_id = status, retry_after, quota_id


def _error_details(body: str) -> tuple:
    """(retry_after seconds, quota id text) from a Gemini error body, when it carries them."""
    retry, quota = None, ""
    m = re.search(r'"retryDelay"\s*:\s*"([\d.]+)s"', body or "")
    if m:
        retry = float(m.group(1))
    q = re.findall(r'"quotaId"\s*:\s*"([^"]+)"', body or "")
    if q:
        quota = " ".join(q)
    return retry, quota


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


MAX_NUMBERED_KEYS = 4


def resolve_gemini_api_keys(settings: Optional[Mapping[str, Any]] = None) -> list:
    """Every configured Gemini key, primary first: GEMINI_API_KEY / settings gemini_api_key, then GEMINI_API_KEY_1..4 / gemini_api_key_1..4.
    Duplicates are dropped. A single-key setup gives a one-item list and behaves exactly as before."""
    out: list = []

    def add(value: Any) -> None:
        v = str(value or "").strip()
        if v and v not in out:
            out.append(v)

    add(os.environ.get("GEMINI_API_KEY"))
    if settings:
        add(settings.get("gemini_api_key"))
    for i in range(1, MAX_NUMBERED_KEYS + 1):
        add(os.environ.get(f"GEMINI_API_KEY_{i}"))
        if settings:
            add(settings.get(f"gemini_api_key_{i}"))
    return out


class GeminiCredentialPool:
    """The keys one process may use, and which of them is resting. Used by every Gemini caller (Director, critic, repair, ...) through
    GeminiLLM, so a quota hit on one key is known to all of them. Key values are never logged or exposed: only their position."""

    COOLDOWN_QUOTA_S = 60.0
    COOLDOWN_BUSY_S = 10.0

    def __init__(self, keys: list):
        self.keys = list(keys)
        self._until = [0.0] * len(self.keys)
        self._dead: set = set()      # keys that are permanently refused (denied project, invalid or revoked key): skipped for the rest of this session
        self.rotations = 0
        self.notes: list = []
        self._lock = threading.Lock()

    def order(self) -> list:
        """Indices in the order to try: keys that are not resting first (in configured order), then the ones that rest least."""
        now = time.monotonic()
        with self._lock:
            live = [i for i in range(len(self.keys)) if i not in self._dead]
            ready = [i for i in live if self._until[i] <= now]
            rest = sorted((i for i in live if self._until[i] > now), key=lambda i: self._until[i])
        return ready + rest

    def retire(self, index: int, why: str) -> bool:
        """Stop using a key for this session because it is refused for good. The only key of a one-key setup is never retired (every call
        tries it, exactly as before). Returns whether it was retired."""
        with self._lock:
            if len(self.keys) < 2:
                return False
            self._dead.add(index)
            self.notes.append(f"Gemini key {index + 1} of {len(self.keys)}: {why} — not used again this session")
            return True

    @property
    def usable(self) -> int:
        return len(self.keys) - len(self._dead)

    def rest(self, index: int, seconds: float, why: str) -> None:
        with self._lock:
            self._until[index] = max(self._until[index], time.monotonic() + seconds)
            self.notes.append(f"Gemini key {index + 1} of {len(self.keys)}: {why}")

    def rotated(self, frm: int, to: int) -> None:
        with self._lock:
            self.rotations += 1
            self.notes.append(f"switching from Gemini key {frm + 1} to key {to + 1}")


_POOLS: dict = {}


def pool_for(keys: list) -> GeminiCredentialPool:
    k = tuple(keys)
    if k not in _POOLS:
        _POOLS[k] = GeminiCredentialPool(keys)
    return _POOLS[k]


def _retryable_status(status: int, message: str) -> Optional[float]:
    """Seconds a key should rest for a failure that another key may not share, or None for a failure that rotating cannot help
    (a malformed request, a bad or revoked key, a missing model)."""
    lower = (message or "").lower()
    if status == 429 or "quota" in lower or "rate limit" in lower or "rate_limit" in lower or "resource_exhausted" in lower:
        return GeminiCredentialPool.COOLDOWN_QUOTA_S
    if status in (408, 500, 502, 503, 504) or "high demand" in lower or "overloaded" in lower or "unavailable" in lower and status >= 500:
        return GeminiCredentialPool.COOLDOWN_BUSY_S
    return None


def _key_refused(status: int, message: str) -> bool:
    """A failure that belongs to THIS key or its project and will not go away (the project was denied access, the key is invalid, revoked or
    expired): another key may well work. Not the same as a bad request, which every key would refuse."""
    lower = (message or "").lower()
    if status in (401, 403):
        return "quota" not in lower and "rate" not in lower
    return status == 400 and ("api key not valid" in lower or "api_key_invalid" in lower or "api key expired" in lower or "key has been" in lower)


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


def _usage_of(payload: dict) -> dict:
    u = (payload or {}).get("usageMetadata") or {}
    return {"input": u.get("promptTokenCount"), "output": u.get("candidatesTokenCount"), "reasoning": u.get("thoughtsTokenCount")}


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


_TASK_BY_MODULE = {
    "visual_director.director": "script_analysis",
    "editorial.reasoner": "editorial_reasoner",
    "smart_editing": "smart_editing",
    "map_scene.ai_places": "map_place_lookup",
    "hybrid.director": "hybrid_director",
    "hybrid.critic": "hybrid_critic",
    "hybrid.pipeline": "hybrid_director",
    "scene_graph.generator": "overscaled_planner",
    "style_engine.detect": "style_detect",
    "visual_qa.semantic": "vision_qa",
}


def _calling_module() -> str:
    """Which part of the app asked (the first caller outside the LLM plumbing), as a short task name."""
    import sys

    try:
        frame = sys._getframe(2)
    except ValueError:
        return "gemini"
    for _ in range(12):
        if frame is None:
            break
        mod = str(frame.f_globals.get("__name__") or "")
        if mod and not mod.startswith(("visual_director.llm", "ai_router", "production.")):
            return _TASK_BY_MODULE.get(mod, mod.rsplit(".", 1)[-1])
        frame = frame.f_back
    return "gemini"


def _record_ai_call(model: str, started: float, *, ok: bool, usage: Optional[dict] = None, error: Any = None,
                    task: str = "") -> None:
    try:
        from production import events
        from production.recovery import classify_failure

        usage = usage or {}
        events.emit("ai_call", task=task or _calling_module(), model=model,
                    duration_s=round(time.monotonic() - started, 3), ok=ok, cached=False,
                    tokens_in=usage.get("input"), tokens_out=usage.get("output"),
                    error_class=None if ok else classify_failure(error).kind)
    except Exception:
        pass


class GeminiLLM:
    """Gemini generateContent over HTTP. Default model: gemini-3.6-flash."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 300.0,
        settings: Optional[Mapping[str, Any]] = None,
        credentials: Optional[GeminiCredentialPool] = None,
    ):
        if credentials is not None:
            self.credentials = credentials
        elif api_key is None:
            self.credentials = pool_for(resolve_gemini_api_keys(settings))
        else:
            self.credentials = pool_for([str(api_key).strip()] if str(api_key).strip() else [])
        self.api_key = self.credentials.keys[0] if self.credentials.keys else (resolve_gemini_api_key(settings) if api_key is None else str(api_key).strip())
        self.model = model or os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
        self.base_url = (base_url or os.environ.get("GEMINI_BASE_URL") or DEFAULT_GEMINI_BASE).rstrip("/")
        self.timeout = timeout
        self.last_usage: dict = {}

    def complete(
        self,
        system: str,
        user: str,
        *,
        thinking_level: str = "medium",
        max_output_tokens: int = 65536,
    ) -> str:
        """One Gemini call. Every call is recorded as a production ``ai_call`` event (task, model, time, tokens, outcome)
        so analytics can show what AI was used for — the request itself is unchanged."""
        started = time.monotonic()
        try:
            text = self._complete(system, user, thinking_level=thinking_level, max_output_tokens=max_output_tokens)
        except BaseException as exc:
            _record_ai_call(self.model, started, ok=False, error=exc)
            raise
        _record_ai_call(self.model, started, ok=True, usage=self.last_usage)
        return text

    def _complete(
        self,
        system: str,
        user: str,
        *,
        thinking_level: str = "medium",
        max_output_tokens: int = 65536,
    ) -> str:
        if not self.credentials.keys and not self.api_key:
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
        keys = self.credentials.keys or [self.api_key]
        order = self.credentials.order() if self.credentials.keys else [0]
        if not order:
            raise LLMError("Gemini API error: every configured API key has been refused (denied or invalid) — check the keys in Settings")
        last_error: Optional[LLMError] = None
        for position, idx in enumerate(order):
            try:
                resp = requests.post(
                    url,
                    headers={
                        "Content-Type": "application/json",
                        "x-goog-api-key": keys[idx],
                    },
                    data=json.dumps(payload),
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = LLMError(f"Gemini request failed: {exc}", status=None)
                rest = GeminiCredentialPool.COOLDOWN_BUSY_S   # a timeout or a dropped connection: another key may get through
            else:
                if resp.status_code < 400:
                    try:
                        data = resp.json()
                    except ValueError as exc:
                        raise LLMError("Gemini returned non-JSON") from exc
                    self.last_usage = _usage_of(data)
                    return extract_gemini_text(data)
                message = format_gemini_api_error(resp.status_code, resp.text or "", self.model)
                retry_after, quota_id = _error_details(resp.text or "")
                last_error = LLMError(message, status=resp.status_code, retry_after=retry_after, quota_id=quota_id)
                rest = _retryable_status(resp.status_code, message)
                if rest is None and _key_refused(resp.status_code, message):
                    # this key (or its project) is refused for good: retire it and try the next one
                    if not self.credentials.retire(idx, "access refused"):
                        raise last_error
                    if position + 1 < len(order):
                        self.credentials.rotated(idx, order[position + 1])
                    continue
                if rest is None:
                    raise last_error   # malformed request, missing model: another key will not help
            if self.credentials.keys:
                self.credentials.rest(idx, rest, "rate-limited or busy")
            if position + 1 < len(order):
                self.credentials.rotated(idx, order[position + 1])
        assert last_error is not None
        raise last_error
