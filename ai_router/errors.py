"""What a provider failure MEANS. "Retry" and "use another route" are different answers to different failures, so each failure is
classified once, here, and the router acts on the class: wait, switch route, disable the route, or give up on the request."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# failure kinds
RATE_TEMP = "rate_limit"      # a per-minute style limit: it clears soon
QUOTA_HARD = "quota"          # a daily / project quota: it will not clear for a long time
DENIED = "denied"             # the key or project is refused for good
AUTH = "auth"                 # the key is invalid
SERVER = "server"             # 5xx, overloaded
NETWORK = "network"           # timeouts, dropped connections
BAD_MODEL = "bad_model"       # the model does not exist for this provider
BAD_REQUEST = "bad_request"   # the request itself is wrong: no other route would accept it either
MALFORMED = "malformed"       # the answer arrived but could not be read
OTHER = "other"


class ProviderError(RuntimeError):
    """What a provider raises: the message plus whatever structure the service gave (status, wait hint, which quota)."""

    def __init__(self, message: str, status: Optional[int] = None, retry_after: Optional[float] = None, quota_id: str = ""):
        super().__init__(message)
        self.status, self.retry_after, self.quota_id = status, retry_after, quota_id


class AllRoutesUnavailable(RuntimeError):
    """No provider route can answer this request right now. Progress is saved by the caller; `retry_at_s` says when to try again."""

    def __init__(self, message: str, retry_in_s: Optional[float] = None):
        super().__init__(message)
        self.retry_in_s = retry_in_s


@dataclass
class Failure:
    kind: str
    cooldown_s: float = 0.0     # how long this ROUTE should rest (0 = none)
    retry_same: bool = False    # worth one more try on the same route after a short wait
    summary: str = ""

    @property
    def disables_route(self) -> bool:
        return self.kind in (DENIED, AUTH, BAD_MODEL)

    @property
    def route_specific(self) -> bool:
        """Would a different provider or model plausibly succeed?"""
        return self.kind != BAD_REQUEST


_TRY_AGAIN = re.compile(r"try again in\s*(?:(\d+)h)?\s*(?:(\d+)m(?![a-z]))?\s*(?:([\d.]+)s)?", re.I)


def _wait_hint(message: str) -> Optional[float]:
    m = _TRY_AGAIN.search(message or "")
    if m and any(m.groups()):
        h, mi, se = m.groups()
        return int(h or 0) * 3600 + int(mi or 0) * 60 + float(se or 0)
    return None


def classify(status: Optional[int], message: str, retry_after: Optional[float] = None, quota_id: str = "") -> Failure:
    """Turn (HTTP status, message, wait hint, quota id) into a Failure. Never looks at a key; messages are short and already redacted."""
    text = (message or "").lower()
    wait = retry_after if retry_after else _wait_hint(message)
    per_day = "perday" in (quota_id or "").lower().replace("_", "").replace(" ", "") or "per day" in text or "tokens per day" in text or "(tpd)" in text or "requests per day" in text or "(rpd)" in text
    if status == 429 or "quota" in text or "rate limit" in text or "rate_limit" in text or "resource_exhausted" in text or "resource has been exhausted" in text:
        if per_day:
            return Failure(QUOTA_HARD, cooldown_s=wait if wait and wait > 60 else 6 * 3600.0, summary="daily quota used up")
        if wait is not None and wait <= 180:
            return Failure(RATE_TEMP, cooldown_s=wait + 1.0, summary=f"rate limited, clears in about {wait:.0f}s")
        if "perminute" in (quota_id or "").lower().replace("_", "").replace(" ", "") or "per minute" in text or "(tpm)" in text or "(rpm)" in text:
            return Failure(RATE_TEMP, cooldown_s=65.0, summary="per-minute limit")
        # "You exceeded your current quota" with no detail: treat as a hard quota and look again later instead of retrying it six times
        return Failure(QUOTA_HARD, cooldown_s=wait if wait and wait > 60 else 30 * 60.0, summary="quota used up")
    if status in (401,) or "api key not valid" in text or "invalid api key" in text or "api_key_invalid" in text or "api key expired" in text:
        return Failure(AUTH, summary="invalid key")
    if status == 403 or "denied access" in text or "permission denied" in text or "permission_denied" in text:
        return Failure(DENIED, summary="access denied")
    if status == 404 or "is not found" in text or "model_not_found" in text or "does not exist" in text and "model" in text or "no longer available" in text or "model" in text and "unavailable" in text and status in (400, 404):
        return Failure(BAD_MODEL, summary="model not available")
    if status is not None and status >= 500 or "high demand" in text or "overloaded" in text or "try again later" in text:
        return Failure(SERVER, cooldown_s=10.0, retry_same=True, summary="service busy")
    if status is None and ("timed out" in text or "timeout" in text or "connection" in text or "request failed" in text):
        return Failure(NETWORK, cooldown_s=5.0, retry_same=True, summary="network problem")
    if status in (400, 413, 422):
        return Failure(BAD_REQUEST, summary="the request was refused")
    return Failure(OTHER, cooldown_s=5.0, retry_same=True, summary=(message or "")[:80])
