"""Embedded JavaScript state extraction — `window.X = {...}`, `var X = {...}`,
and `JSON.parse("...")` inside plain `<script>` tags.

`<script type="application/json">` (which is how Next.js ships
`__NEXT_DATA__`) is already handled by structured_data.parse_embedded_json_blocks.
This module covers the other major hydration convention: state assigned to a
JS variable in an ordinary script tag, where the payload is frequently NOT
valid JSON at all — unquoted keys, single-quoted strings, trailing commas,
`undefined`/`NaN`, leading-dot floats. A brace-counter plus `json.loads`
fails on all of those.

Parsing is delegated to chompjs (https://github.com/Nykakin/chompjs), MIT,
a C tokenizer that normalizes JS/JSON5 object literals into Python objects.
It is the approach Scrapy's own "dynamically-loaded content" documentation
recommends. `JSON.parse("...")` is handled separately before chompjs runs,
because there the payload is an *escaped string literal* that must be
unescaped first — feeding it to a JS-object parser directly yields keys
like '\\"url\\"' rather than 'url'.

Bounded by design (see the MAX_* constants): a listing page carries hundreds
of KB of unrelated inline script, and this must not become the slow part of
a scrape. Never raises — a script that cannot be parsed is skipped.
"""
from __future__ import annotations

import json
import re
from typing import Any, List

# Only scripts that look like they assign state are scanned at all.
_STATE_HINT_RE = re.compile(
    r"(?:window|self|globalThis)\s*[\.\[]|(?:\bvar|\blet|\bconst)\s+[A-Za-z_$][\w$]*\s*=\s*[\{\[]"
    r"|JSON\.parse\s*\(",
)
_JSON_PARSE_RE = re.compile(r"JSON\.parse\(\s*(['\"])(.*?)(?<!\\)\1\s*\)", re.S)

MAX_SCRIPT_BYTES = 4_000_000
"""Skip absurdly large inline scripts outright — past this size the payload
is a bundle, not page state."""
MAX_OBJECTS_PER_SCRIPT = 200
MAX_TOTAL_OBJECTS = 800
MIN_INTERESTING_KEYS = 1


def _is_interesting(obj: Any) -> bool:
    """Filter out the noise chompjs finds in ordinary code (`{}`, `{a:1}`
    from a config call, etc.). We only want containers big enough to
    plausibly be page state."""
    if isinstance(obj, dict):
        return len(obj) >= MIN_INTERESTING_KEYS
    if isinstance(obj, list):
        return len(obj) > 0
    return False


def _json_parse_payloads(text: str) -> List[Any]:
    """Objects from `JSON.parse("<escaped json>")`. The captured group is a
    JS string literal, so it is unescaped as a JSON string first, then the
    resulting text is parsed as JSON."""
    out: List[Any] = []
    for quote, inner in _JSON_PARSE_RE.findall(text):
        try:
            if quote == "'":
                inner = inner.replace('\\"', '"').replace("\\'", "'")
                unescaped = inner
            else:
                unescaped = json.loads('"' + inner + '"')
        except (json.JSONDecodeError, ValueError):
            continue
        try:
            parsed = json.loads(unescaped)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if _is_interesting(parsed):
            out.append(parsed)
    return out


def _chompjs_objects(text: str) -> List[Any]:
    try:
        import chompjs
    except ImportError:
        return []
    out: List[Any] = []
    try:
        for obj in chompjs.parse_js_objects(text):
            if _is_interesting(obj):
                out.append(obj)
            if len(out) >= MAX_OBJECTS_PER_SCRIPT:
                break
    except Exception:  # noqa: BLE001 - unparseable script, skip it entirely
        return out
    return out


def script_state_blocks(soup) -> List[Any]:
    """Every plausible state object assigned in an inline `<script>`.

    Shaped like the other embedded-JSON block lists so the existing generic
    image walker (structured_data.embedded_json_images) can consume it with
    no special-casing. Returns [] on a page with no inline state."""
    if soup is None:
        return []
    blocks: List[Any] = []
    try:
        scripts = soup.find_all("script")
    except Exception:  # noqa: BLE001
        return []

    for tag in scripts:
        if len(blocks) >= MAX_TOTAL_OBJECTS:
            break
        # Typed scripts (application/json, ld+json) are other modules' jobs.
        script_type = (tag.get("type") or "").lower()
        if script_type and script_type not in ("text/javascript", "application/javascript", "module"):
            continue
        text = tag.string or tag.get_text() or ""
        if not text or len(text) > MAX_SCRIPT_BYTES:
            continue
        if not _STATE_HINT_RE.search(text):
            continue

        blocks.extend(_json_parse_payloads(text))
        blocks.extend(_chompjs_objects(text))

    return blocks[:MAX_TOTAL_OBJECTS]
