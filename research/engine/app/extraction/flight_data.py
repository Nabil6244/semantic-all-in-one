"""Next.js / React Server Components ("Flight") payload extraction.

Modern listing sites (Zillow and Redfin among them) are Next.js App Router
apps: the gallery is streamed to the browser as an RSC Flight payload inside
`self.__next_f.push(...)` script tags and assembled by React on the client.
It is frequently never present as an `<img>`, a `srcset`, or even a
`<script type="application/json">` — so a scraper that only reads the DOM
sees the hero image and nothing else. This module recovers that payload.

Algorithm adapted from njsparser (https://github.com/novitae/njsparser),
MIT-licensed, Copyright (c) 2024 novitae — reimplemented here against the
stdlib + BeautifulSoup so the engine does not take on that project's
dependency tree (pythonmonkey/orjson/typer/rich), none of which the flight
parsing itself needs. Segment semantics follow Next.js's own client:
https://github.com/vercel/next.js/blob/canary/packages/next/src/client/app-index.tsx

Four details a naive `push([1,"..."])` regex gets wrong, all handled here:

1. Segment types. The pushed tuple's first element is a segment kind:
   0 = bootstrap (RESETS the buffer), 1 = append, 2 = form state,
   3 = binary (base64-encoded). Dropping 0 and 3 loses real data.
2. The bootstrap call uses a different shape entirely —
   `(self.__next_f = self.__next_f || []).push([...])`.
3. Chunks are split at ARBITRARY offsets, frequently mid-JSON-string, and
   must be concatenated with nothing between them. Joining on "\\n" injects
   separators into string literals and corrupts the payload.
4. Rows are `<hexindex>:<CLASS><payload>`, and a `T<hexlen>,<text>` row
   declares its length in BYTES — so row splitting has to happen on bytes,
   or any non-ASCII character (a °, an é, a — in a listing description)
   shifts every subsequent offset.

Everything degrades gracefully: a malformed payload yields fewer rows, never
an exception, so RSC parsing failing can never take down JSON-LD/DOM
discovery below it.
"""
from __future__ import annotations

import base64
import json
import re
from typing import Any, Dict, List, Optional

# `(self.__next_f = self.__next_f || []).push([0])` — the bootstrap call.
_RE_INIT = re.compile(
    r"\(\s*self\.__next_f\s*=\s*self\.__next_f\s*\|\|\s*\[\]\s*\)\.push\(\s*(\[.*?\])\s*\)",
    re.S,
)
# `self.__next_f.push([1, "..."])` — subsequent data calls.
_RE_PUSH = re.compile(r"self\.__next_f\.push\(\s*(\[.*)\)\s*;?\s*$", re.S)

# Row boundary: an unescaped newline followed by `<hex>:`.
_SPLIT_POINTS = re.compile(rb"(?<!\\)\n[a-f0-9]*:")

SEG_BOOTSTRAP = 0
SEG_APPEND = 1
SEG_FORM_STATE = 2
SEG_BINARY = 3


def _script_texts(soup) -> List[str]:
    if soup is None:
        return []
    out: List[str] = []
    for tag in soup.find_all("script"):
        text = tag.string or tag.get_text() or ""
        if text and "__next_f" in text:
            out.append(text.strip())
    return out


def has_flight_data(soup) -> bool:
    return any(_RE_INIT.search(t) or _RE_PUSH.match(t) for t in _script_texts(soup))


def raw_flight_segments(soup) -> List[list]:
    """The `self.__next_f` array as the browser would have built it."""
    segments: List[list] = []
    for text in _script_texts(soup):
        match = _RE_INIT.search(text)
        if match:
            try:
                segments.append(json.loads(match.group(1)))
            except (json.JSONDecodeError, TypeError):
                pass
        match = _RE_PUSH.match(text)
        if match:
            try:
                segments.append(json.loads(match.group(1)))
            except (json.JSONDecodeError, TypeError):
                pass
    return segments


def decode_segments(segments: List[list]) -> str:
    """Reassemble the streamed chunks into one payload string.

    Concatenated with NOTHING between chunks — Next.js splits them at
    arbitrary offsets, often inside a JSON string literal."""
    buffer: List[str] = []
    for seg in segments:
        if not isinstance(seg, list) or not seg:
            continue
        kind = seg[0]
        if kind == SEG_BOOTSTRAP:
            buffer = []
            # A bootstrap segment may also carry an initial payload.
            if len(seg) > 1 and isinstance(seg[1], str):
                buffer.append(seg[1])
        elif kind == SEG_APPEND:
            if len(seg) > 1 and isinstance(seg[1], str):
                buffer.append(seg[1])
        elif kind == SEG_BINARY:
            if len(seg) > 1 and isinstance(seg[1], str):
                try:
                    buffer.append(base64.b64decode(seg[1].encode()).decode("utf-8", "replace"))
                except Exception:  # noqa: BLE001 - malformed base64 chunk, skip it
                    pass
        # SEG_FORM_STATE carries no model data we need.
    return "".join(buffer)


def parse_flight_rows(payload: str) -> Dict[Optional[int], Any]:
    """Split the payload into `<hexindex>:<CLASS><value>` rows and JSON-parse
    each. Returns index -> value. Unparseable rows are skipped, never fatal.

    Operates on bytes because `T<hexlen>,` declares a BYTE length."""
    if not payload:
        return {}
    data = payload.encode("utf-8", "replace")
    rows: Dict[Optional[int], Any] = {}
    pos = 0
    guard = 0

    while pos < len(data):
        guard += 1
        if guard > 100_000:  # pathological input; stop rather than spin
            break

        colon = data.find(b":", pos)
        if colon == -1:
            break
        index_raw = data[pos:colon]
        try:
            index = int(index_raw, 16) if index_raw else None
        except ValueError:
            # Not a row header — skip past this colon and resynchronize.
            pos = colon + 1
            continue
        pos = colon + 1
        if pos >= len(data):
            break

        # Row class: leading uppercase letters (T, I, HL, E, ...).
        value_class = ""
        while pos < len(data):
            char = chr(data[pos])
            if char.isalpha() and char.isupper():
                value_class += char
                pos += 1
            else:
                break

        if value_class == "T":
            comma = data.find(b",", pos)
            if comma == -1:
                break
            try:
                text_length = int(data[pos:comma], 16)
            except ValueError:
                pos = comma + 1
                continue
            start = comma + 1
            raw_value = data[start:start + text_length]
            pos = start + text_length
            rows[index] = raw_value.decode("utf-8", "replace")
            continue

        match = _SPLIT_POINTS.search(data, pos)
        if match:
            raw_value = data[pos:match.start()]
            pos = match.start() + 1
        else:
            raw_value = data[pos:]
            pos = len(data)

        if not raw_value.strip():
            continue
        try:
            rows[index] = json.loads(raw_value)
        except (json.JSONDecodeError, TypeError, ValueError):
            # A hint/module row (`I`, `HL`, ...) or a chunk that never
            # completed — nothing to model here, keep going.
            continue

    return rows


def flight_data_blocks(soup) -> List[Any]:
    """Parsed RSC rows for this page, shaped like the other embedded-JSON
    block lists so the existing generic image walker can consume them
    directly. Returns [] when the page is not a Flight app."""
    try:
        segments = raw_flight_segments(soup)
        if not segments:
            return []
        rows = parse_flight_rows(decode_segments(segments))
        return list(rows.values())
    except Exception:  # noqa: BLE001 - optional layer, must never break discovery
        return []
