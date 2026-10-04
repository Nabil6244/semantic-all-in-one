"""The AI router: a task (director / critic / repair / utility) is tried on its routes in order. A failure is classified and the router
acts on the class: wait and retry a few times for a busy service, rest a route that is rate limited, retire a route that is denied or
exhausted for the day, and move to the next route; it never retries a hard quota, and never moves on for a request that is itself wrong.
Accepted answers are cached by request identity so a repeat costs nothing. Nothing here knows about maps or beats."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .errors import (AUTH, BAD_MODEL, BAD_REQUEST, DENIED, MALFORMED, NETWORK, QUOTA_HARD, RATE_TEMP, SERVER, AllRoutesUnavailable, Failure, ProviderError, classify)

TASKS = ("director", "critic", "repair", "utility")
RETRY_SAME_DELAYS = (3.0, 9.0)          # a busy service or a dropped connection: this many more tries on the same route, no more
MAX_WAIT_FOR_COOLDOWN_S = 75.0          # when the only route left is rate limited for less than this, wait for it once


@dataclass(frozen=True)
class Route:
    provider: str      # "gemini" | "groq"
    model: str
    thinking: str = "low"
    max_output: int = 16384
    timeout: float = 180.0

    @property
    def key(self) -> str:
        return f"{self.provider}/{self.model}"


@dataclass
class RouterResult:
    text: str
    route: Optional[Route]
    from_cache: bool = False
    attempts: int = 1


class Usage:
    """What was asked of whom. Counts only: no prompts, no keys."""

    def __init__(self) -> None:
        self.calls: Dict[str, Dict[str, int]] = {}
        self.fails: Dict[str, int] = {}
        self.local: Dict[str, int] = {}
        self.cache_hits = 0
        self.retries = 0
        self.fallbacks = 0
        self.tokens = {"input": 0, "output": 0, "reasoning": 0}

    def call(self, provider: str, task: str) -> None:
        self.calls.setdefault(provider, {}).setdefault(task, 0)
        self.calls[provider][task] += 1

    def note_local(self, what: str, n: int = 1) -> None:
        self.local[what] = self.local.get(what, 0) + n

    def to_dict(self) -> dict:
        return {"calls": self.calls, "failed_attempts": self.fails, "local": self.local, "cache_hits": self.cache_hits, "retries": self.retries,
                "fallbacks": self.fallbacks, "tokens": self.tokens}

    def summary(self) -> str:
        lines = ["Planning AI usage"]
        for prov in sorted(self.calls):
            lines.append(f"  {prov.capitalize()}: " + ", ".join(f"{t} {n}" for t, n in sorted(self.calls[prov].items())))
        if not self.calls:
            lines.append("  no AI requests")
        lines.append("  Local: " + (", ".join(f"{k} {v}" for k, v in sorted(self.local.items())) or "nothing yet"))
        if self.cache_hits:
            lines.append(f"  Reused from saved results: {self.cache_hits}")
        if self.retries or self.fallbacks:
            lines.append(f"  Retries {self.retries}, fallbacks {self.fallbacks}")
        return "\n".join(lines)


class AIRouter:
    def __init__(self, routes: Dict[str, List[Route]], providers: Dict[str, Any], *, state_dir: "str | Path | None" = None, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.time):
        self.routes, self.providers = routes, providers
        self.usage = Usage()
        self._sleep, self._clock = sleep, clock
        self._until: Dict[str, float] = {}     # route key -> epoch seconds the route is available again (resting or exhausted)
        self._dead: Dict[str, str] = {}        # route key -> why it was retired for this session (denied, invalid, bad model)
        self._lock = threading.Lock()
        self.state_dir = Path(state_dir) if state_dir else None
        self.last: Dict[str, Any] = {}
        self._load_state()

    # ---- state ----------------------------------------------------------------------------------------------------
    def _state_file(self) -> Optional[Path]:
        return self.state_dir / "route_state.json" if self.state_dir else None

    def _load_state(self) -> None:
        f = self._state_file()
        try:
            data = json.loads(f.read_text(encoding="utf-8")) if f and f.is_file() else {}
        except (OSError, ValueError):
            data = {}
        now = self._clock()
        self._until = {k: float(v) for k, v in (data.get("until") or {}).items() if float(v) > now}   # a daily quota still counts after a restart

    def _save_state(self) -> None:
        f = self._state_file()
        if not f:
            return
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps({"until": {k: v for k, v in self._until.items() if v > self._clock() + 90}}), encoding="utf-8")
        except OSError:
            pass

    def status(self) -> List[dict]:
        """Every route of every task with its state, for the Settings page and the logs."""
        now = self._clock()
        seen, out = set(), []
        for task, routes in self.routes.items():
            for r in routes:
                if r.key in seen:
                    continue
                seen.add(r.key)
                if r.key in self._dead:
                    state, note = "UNAVAILABLE", self._dead[r.key]
                elif self._until.get(r.key, 0) > now:
                    state, note = "RESTING", f"back in {int(self._until[r.key] - now)}s"
                elif not self.providers.get(r.provider) or not self.providers[r.provider].configured():
                    state, note = "NOT CONFIGURED", ""
                else:
                    state, note = "READY", ""
                out.append({"task": task, "provider": r.provider, "model": r.model, "state": state, "note": note})
        return out

    def available(self, route: Route) -> bool:
        prov = self.providers.get(route.provider)
        return bool(prov and prov.configured()) and route.key not in self._dead and self._until.get(route.key, 0) <= self._clock()

    # ---- cache ----------------------------------------------------------------------------------------------------
    def _cache_path(self, task: str, system: str, user: str) -> Optional[Path]:
        if not self.state_dir:
            return None
        norm = re.sub(r"\s+", " ", user).strip()
        ident = hashlib.sha1(f"{task}\0{hashlib.sha1(system.encode()).hexdigest()}\0{norm}".encode("utf-8")).hexdigest()[:24]
        return self.state_dir / "cache" / f"{task}_{ident}.json"

    def _cache_get(self, path: Optional[Path], accept: Optional[Callable[[str], bool]]) -> Optional[str]:
        try:
            text = json.loads(path.read_text(encoding="utf-8"))["text"] if path and path.is_file() else None
        except (OSError, ValueError, KeyError):
            return None
        return text if text and (accept is None or accept(text)) else None

    def _cache_put(self, path: Optional[Path], text: str, route: Route) -> None:
        if not path:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"text": text, "route": route.key, "at": int(self._clock())}), encoding="utf-8")
        except OSError:
            pass

    def _log(self, row: dict) -> None:
        self.last = row
        if not self.state_dir:
            return
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            with (self.state_dir / "ai_calls.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            pass

    # ---- the request ----------------------------------------------------------------------------------------------
    def run(self, task: str, system: str, user: str, *, label: str = "", accept: Optional[Callable[[str], bool]] = None,
            say: Optional[Callable[[str], None]] = None, cache: bool = True) -> RouterResult:
        say = say or (lambda m: None)
        path = self._cache_path(task, system, user) if cache else None
        hit = self._cache_get(path, accept)
        if hit is not None:
            self.usage.cache_hits += 1
            self._log({"task": task, "label": label, "provider": "cache", "model": "", "ok": True, "cache": True, "t": int(self._clock())})
            return RouterResult(hit, None, from_cache=True, attempts=0)
        routes = list(self.routes.get(task) or [])
        if not routes:
            raise AllRoutesUnavailable(f"no AI route is configured for the {task} task")
        tried: List[str] = []
        failed_here: set = set()      # routes that already failed THIS request: never asked twice for one answer
        rate_limited: set = set()     # routes that said "too fast": one short wait, then one more try
        waited = False
        while True:
            usable = [r for r in routes if self.available(r) and r.key not in failed_here]
            if not usable:
                # only a route that said "too fast" is worth waiting for (once); an exhausted, denied or unreadable one is not
                soon = [(self._until[r.key] - self._clock(), r) for r in routes if r.key in rate_limited and r.key not in self._dead and r.key not in failed_here
                        and self._until.get(r.key, 0) > self._clock()]
                if soon and not waited and min(s for s, _ in soon) <= MAX_WAIT_FOR_COOLDOWN_S:
                    delay = max(0.0, min(s for s, _ in soon)) + 0.5
                    say(f"All {task} routes are resting; waiting {delay:.0f}s for the first to clear…")
                    self._sleep(delay)
                    waited = True
                    continue
                raise AllRoutesUnavailable(self._why_none(task, routes), retry_in_s=min((s for s, _ in soon), default=None))
            route = usable[0]
            if tried and route.key not in tried:
                self.usage.fallbacks += 1
            tried.append(route.key)
            outcome = self._attempt(task, route, system, user, label, accept, say)
            if isinstance(outcome, RouterResult):
                self._cache_put(path, outcome.text, route)
                return outcome
            if outcome == BAD_REQUEST:
                raise ProviderError(f"the {task} request was refused by {route.provider}: it would be refused by any provider", status=400)
            if outcome == RATE_TEMP:
                rate_limited.add(route.key)       # may be asked again after a short wait (once)
            else:
                failed_here.add(route.key)        # resting, exhausted, retired or unreadable: not again for this answer

    def run_task(self, task: str, system: str, user: str, say: Optional[Callable[[str], None]] = None, accept: Optional[Callable[[str], bool]] = None,
                 label: str = "") -> str:
        """The interface Hybrid's planner uses: the answer text for a task (the route that gave it is in `self.last`)."""
        return self.run(task, system, user, label=label, accept=accept, say=say).text

    def _why_none(self, task: str, routes: List[Route]) -> str:
        parts = []
        for r in routes:
            if r.key in self._dead:
                parts.append(f"{r.key}: {self._dead[r.key]}")
            elif self._until.get(r.key, 0) > self._clock():
                parts.append(f"{r.key}: resting for {int(self._until[r.key] - self._clock())}s")
            elif not self.providers.get(r.provider) or not self.providers[r.provider].configured():
                parts.append(f"{r.provider}: no key")
        return f"No AI route can answer the {task} request right now (" + "; ".join(parts) + "). Progress is saved; try again later or add another provider key in Settings."

    def _attempt(self, task: str, route: Route, system: str, user: str, label: str, accept: Optional[Callable[[str], bool]], say: Callable[[str], None]):
        provider = self.providers[route.provider]
        tries = 0
        malformed = 0
        while True:
            tries += 1
            t0 = self._clock()
            row = {"task": task, "label": label, "provider": route.provider, "model": route.model, "attempt": tries, "cache": False}
            try:
                done = provider.complete(system, user, model=route.model, thinking=route.thinking, max_output=route.max_output, timeout=route.timeout)
            except ProviderError as exc:
                f = classify(exc.status, str(exc), exc.retry_after, exc.quota_id)
                self.usage.fails[route.key] = self.usage.fails.get(route.key, 0) + 1
                row.update(ok=False, failure=f.kind, ms=int((self._clock() - t0) * 1000), t=int(t0))
                if f.kind == BAD_REQUEST:
                    self._log({**row, "next": "stop"})
                    return BAD_REQUEST
                if f.retry_same and tries <= len(RETRY_SAME_DELAYS):
                    self.usage.retries += 1
                    delay = RETRY_SAME_DELAYS[tries - 1]
                    self._log({**row, "next": f"retry {route.key} in {delay:.0f}s"})
                    say(f"{route.provider} {route.model}: {f.summary}; trying again in {delay:.0f}s")
                    self._sleep(delay)
                    continue
                self._rest(route, f)
                self._log({**row, "next": "another route"})
                say(f"{route.provider} {route.model}: {f.summary}; moving to the next route")
                return f.kind
            self.usage.call(route.provider, task)
            for k in ("input", "output", "reasoning"):
                self.usage.tokens[k] += int((done.usage or {}).get(k) or 0)
            text = done.text
            if accept is not None and not accept(text):
                malformed += 1
                self.usage.fails[route.key] = self.usage.fails.get(route.key, 0) + 1
                self._log({**row, "ok": False, "failure": MALFORMED, "ms": int((self._clock() - t0) * 1000), "t": int(t0), "next": "retry" if malformed < 2 else "another route"})
                if malformed < 2:
                    self.usage.retries += 1
                    user = user + "\n\nYour previous answer could not be used. Answer again with ONLY the JSON described, complete and valid."
                    continue
                self._until[route.key] = self._clock() + 5.0
                return MALFORMED
            self._log({**row, "ok": True, "ms": int((self._clock() - t0) * 1000), "t": int(t0), "usage": done.usage, "limits": done.limits})
            if done.limits.get("remaining_requests") == "0" or done.limits.get("remaining_tokens") == "0":
                self._until[route.key] = self._clock() + 20.0     # the service says this route has nothing left this window
            return RouterResult(text, route, attempts=tries)

    def _rest(self, route: Route, f: Failure) -> None:
        with self._lock:
            if f.disables_route:
                self._dead[route.key] = f.summary
            else:
                self._until[route.key] = self._clock() + max(f.cooldown_s, 5.0)
                if f.kind == QUOTA_HARD:
                    self._save_state()
