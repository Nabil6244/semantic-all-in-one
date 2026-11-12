"""Aviation website screenshots (docs/aviation/PLAN.md section 7, step 2): the cited article / report page for a card.

    shot(url, cache_dir, timeout_s=40) -> {ok, path, site, title, date ('Month D, YYYY'), headline_box [x, y, w, h], reason, cached}

Runs aviation/webshot.mjs (Node + the Playwright that flow-engine already has) in its own throwaway browser. Overlays are hidden with
CSS, never accepted. Only http(s) and local file URLs; each page is taken once and kept in cache_dir by its URL. A page that cannot be
had (paywall, block, timeout) returns ok False with the reason: the card then falls back to the typeset page.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict

HERE = Path(__file__).resolve().parent


def _date(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    try:
        d = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return f"{d:%B} {d.day}, {d.year}"
    except ValueError:
        return s[:40]


def shot(url: str, cache_dir: Any, timeout_s: float = 40.0, width: int = 1280, height: int = 1600) -> Dict[str, Any]:
    url = str(url or "").strip()
    if not url.lower().startswith(("http://", "https://", "file://")):
        return {"ok": False, "reason": "not a web address"}
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    png, meta = cache / f"{key}.png", cache / f"{key}.json"
    if png.is_file() and meta.is_file():
        try:
            r = json.loads(meta.read_text(encoding="utf-8"))
            if r.get("ok"):
                return dict(r, cached=True)
        except ValueError:
            pass
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump({"url": url, "out": str(png), "width": width, "height": height, "timeout_ms": int(timeout_s * 600)}, fh)
        spec = fh.name
    try:
        p = subprocess.run(["node", str(HERE / "webshot.mjs"), spec], capture_output=True, text=True, timeout=timeout_s + 20)
        lines = (p.stdout or "").strip().splitlines()
        r = json.loads(lines[-1]) if lines else {"ok": False, "reason": (p.stderr or "no output")[-300:]}
    except subprocess.TimeoutExpired:
        r = {"ok": False, "reason": "timed out"}
    except (OSError, ValueError) as exc:
        r = {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}
    finally:
        Path(spec).unlink(missing_ok=True)
    r["date"] = _date(r.get("date", ""))
    r["url"] = url
    if r.get("ok") and png.is_file():
        meta.write_text(json.dumps(r, indent=1), encoding="utf-8")
    else:
        r["ok"] = False
        r["reason"] = r.get("reason") or "no screenshot"
    r["cached"] = False
    return r
