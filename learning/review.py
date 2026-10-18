"""Human review of candidate rules: approve / reject / defer, disable an approved rule, roll a style back.

Approved rules live ONLY in the existing package store (``learning.packages``), per exact style scope; every approval, disable and
rollback publishes a new local package version, so ``packages.rollback`` can always return to the previous one. Decisions are also
logged as append-only ``rule_decision`` ledger events (local only; never uploaded). Nothing is ever approved automatically.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import analysis, events as ev, ledger as _ledger, packages

_EVENT_TYPES = ("csv_analysis", "render_outcome", "video_rating", "scene_failure")
_DECISION = "rule_decision"


def _led(led):
    return led or _ledger.default_ledger()


def _decisions(led: _ledger.Ledger) -> Dict[tuple, str]:
    state: Dict[tuple, str] = {}
    for e in led.events(event_type=_DECISION, limit=100000):
        p = e.get("payload") or {}
        state[(e["style_scope"], p.get("rule_id"))] = p.get("action")
    return state


def suggestions(led: Optional[_ledger.Ledger] = None, root=None) -> List[Dict[str, Any]]:
    """Candidates not yet approved/rejected (deferred ones stay listed), strongest first. Re-running adds nothing."""
    led = _led(led)
    evs: List[Dict[str, Any]] = []
    for t in _EVENT_TYPES:
        evs += led.events(event_type=t, limit=100000)
    evs.sort(key=lambda e: e["seq"])
    decided = _decisions(led)
    out = []
    for scope, cands in analysis.discover(evs).items():
        live = {r["id"] for r in (packages.active_package(scope, root) or {}).get("rules", [])}
        for c in cands:
            if c["id"] in live or decided.get((scope, c["id"])) in ("approve", "reject"):
                continue
            out.append({**c, "decision": decided.get((scope, c["id"])) or "new"})
    return sorted(out, key=lambda c: (-c["confidence"], c["style_scope"], c["id"]))


def _log(led, scope, rule_id, action, version=0) -> None:
    ev.record_event(_DECISION, style_scope=scope, payload={"rule_id": rule_id, "action": action, "version": version}, ledger=led)


def _publish(scope: str, rules: List[Dict[str, Any]], root) -> packages.Result:
    prev = packages.latest_version(scope, root)
    pkg = packages.build_package(scope, rules, version=prev + 1, previous_version=prev or None)
    return packages.install(pkg, expected_scope=scope, root=root)


def decide(candidate: Dict[str, Any], action: str, led: Optional[_ledger.Ledger] = None, root=None) -> packages.Result:
    """approve | reject | defer. Only approve changes anything the generator can see."""
    led = _led(led)
    scope, cid = candidate["style_scope"], candidate["id"]
    if action not in ("approve", "reject", "defer"):
        return packages.Result(False, "bad_action")
    res = packages.Result(True)
    if action == "approve":
        current = list((packages.active_package(scope, root) or {}).get("rules", []))
        new = analysis.approved_rules([candidate], [cid])
        res = _publish(scope, [r for r in current if r["id"] != cid] + new, root)
        if not res.ok:
            return res
    _log(led, scope, cid, action, res.version)
    return res


def approved(root=None) -> Dict[str, List[Dict[str, Any]]]:
    return {sc: (packages.active_package(sc, root) or {}).get("rules", []) for sc in packages.known_scopes(root)}


def disable(scope: str, rule_id: str, led: Optional[_ledger.Ledger] = None, root=None) -> packages.Result:
    led = _led(led)
    rules = [r for r in (packages.active_package(scope, root) or {}).get("rules", []) if r["id"] != rule_id]
    res = _publish(scope, rules, root)
    if res.ok:
        _log(led, scope, rule_id, "disable", res.version)
    return res


def rollback(scope: str, led: Optional[_ledger.Ledger] = None, root=None) -> packages.Result:
    res = packages.rollback(scope, root)
    if res.ok:
        _log(_led(led), scope, "*", "rollback", res.version)
    return res
