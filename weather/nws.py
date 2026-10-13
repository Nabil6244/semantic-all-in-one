"""The National Weather Service API (api.weather.gov): point lookups, forecasts, observations and alerts.

The NWS asks every caller to identify itself with contact details in the User-Agent. Weather sends the contact the user typed
in Weather settings and refuses to fetch without one; it never fills one in by itself. Server trouble (5xx, 429, a dropped
connection) is retried with a growing pause; a 4xx is reported at once, with the URL."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .cache import HttpCache, Response

API = "https://api.weather.gov"
APP_UA = "SemanticYTStudio-Weather/1.0"
DEFAULT_MAX_AGE_S = 3600.0
RETRIES = 3


class NwsError(RuntimeError):
    pass


def check_contact(contact: str) -> str:
    """The contact the NWS asks for: an email address or a web address. Empty or anything else is refused."""
    c = (contact or "").strip()
    if not c:
        raise NwsError("Weather needs a contact for the National Weather Service (an email address or a website), which the NWS "
                       "asks every app to send. Type it in Weather settings; Weather never fills one in by itself.")
    if not (re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", c) or re.fullmatch(r"https?://\S+", c)):
        raise NwsError(f"the NWS contact {c!r} is not an email address or a web address (https://...)")
    return c


Fetcher = Callable[[str, Dict[str, str]], Response]


def urllib_fetch(url: str, headers: Dict[str, str]) -> Response:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return Response(r.status, r.read(), {k.lower(): v for k, v in r.headers.items()}, datetime.now(timezone.utc))
    except urllib.error.HTTPError as e:
        return Response(e.code, e.read() or b"", {k.lower(): v for k, v in (e.headers or {}).items()}, datetime.now(timezone.utc))


class NwsClient:
    def __init__(self, contact: str, *, cache: Optional[HttpCache] = None, fetch: Fetcher = urllib_fetch,
                 sleep: Callable[[float], None] = time.sleep, retries: int = RETRIES):
        self.contact = check_contact(contact)
        self.cache = cache if cache is not None else HttpCache()
        self.fetch, self.sleep, self.retries = fetch, sleep, retries

    @property
    def headers(self) -> Dict[str, str]:
        return {"User-Agent": f"{APP_UA} ({self.contact})", "Accept": "application/geo+json"}

    def get(self, url: str) -> Response:
        hit = self.cache.get(url)
        if hit is not None:
            return hit
        last = ""
        for attempt in range(self.retries + 1):
            try:
                resp = self.fetch(url, self.headers)
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                last = f"network error: {exc}"
            else:
                if resp.status == 200:
                    self.cache.put(url, resp, DEFAULT_MAX_AGE_S)
                    return resp
                if resp.status == 429 or resp.status >= 500:
                    last = f"HTTP {resp.status}"
                    wait = resp.headers.get("retry-after")
                    if attempt < self.retries:
                        self.sleep(min(30.0, float(wait)) if wait and wait.replace(".", "", 1).isdigit() else 2.0 ** attempt)
                    continue
                raise NwsError(f"{url} answered HTTP {resp.status}: {_detail(resp.body)}")
            if attempt < self.retries:
                self.sleep(2.0 ** attempt)
        raise NwsError(f"{url} could not be fetched after {self.retries + 1} tries ({last}). Check the connection and try again.")

    def get_json(self, url: str) -> "tuple[Dict[str, Any], Response]":
        resp = self.get(url)
        try:
            return json.loads(resp.body.decode("utf-8")), resp
        except ValueError as exc:
            raise NwsError(f"{url} did not answer with JSON ({exc})") from None

    # ---- products ----------------------------------------------------------------------------------------------------
    def point(self, lat: float, lon: float) -> "tuple[Dict[str, Any], Response]":
        d, r = self.get_json(f"{API}/points/{lat:.4f},{lon:.4f}")
        return d.get("properties") or {}, r

    def forecast(self, forecast_url: str) -> "tuple[Dict[str, Any], Response]":
        d, r = self.get_json(forecast_url)
        return d.get("properties") or {}, r

    def stations(self, stations_url: str) -> List[str]:
        d, _ = self.get_json(stations_url)
        return [f["properties"]["stationIdentifier"] for f in d.get("features", []) if f.get("properties", {}).get("stationIdentifier")]

    def latest_observation(self, station: str) -> "tuple[Dict[str, Any], Response, str]":
        url = f"{API}/stations/{station}/observations/latest"
        d, r = self.get_json(url)
        return d.get("properties") or {}, r, url

    def alerts(self, area: str) -> "tuple[Dict[str, Any], Response, str]":
        """Active alerts for a state (two letters) or the whole country ('US')."""
        url = f"{API}/alerts/active?status=actual" + ("" if area == "US" else f"&area={area}")
        d, r = self.get_json(url)
        return d, r, url


def _detail(body: bytes) -> str:
    try:
        d = json.loads(body.decode("utf-8"))
        return str(d.get("detail") or d.get("title") or "")[:300]
    except (ValueError, UnicodeDecodeError, AttributeError):
        return body[:200].decode("utf-8", "replace")
