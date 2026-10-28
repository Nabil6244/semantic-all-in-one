"""Feature CSV reader (lenient). Format (docs/product_trailer/PLAN.md):

    product,colour,wordmark,date,time,disclaimer        <- optional header/product block (any of these keys)
    Galaxy S27 Ultra,titanium,SAMSUNG,Tue 27 Oct,09:41,Conceptual trailer...
    order,feature,kicker,value,sub,look                 <- feature table
    1,camera,The next-gen,200MP,main sensor,

The product block may also be given as `key,value` rows (product,Galaxy S27 Ultra) or as `#product: ...` lines. Missing columns,
a BOM, extra spaces and blank lines are fine. Returns {"product": {...}, "features": [...]}."""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any, Dict, List

PRODUCT_KEYS = {"product": "name", "name": "name", "phone": "phone", "preset": "phone", "model": "phone", "colour": "colour", "color": "colour",
                "wordmark": "wordmark", "brand": "wordmark", "date": "date", "time": "time", "disclaimer": "disclaimer", "tagline": "tagline",
                "intro": "intro", "kicker": "intro"}
FEATURE_COLS = ("order", "feature", "kicker", "value", "sub", "look")
DEFAULT_DISCLAIMER = "Concept trailer. Not affiliated with the brand. Logos belong to their owners."


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").replace("﻿", "")).strip()


def _key(s: Any) -> str:
    return _norm(s).lower().lstrip("#").strip().rstrip(":")


def read_csv(path) -> Dict[str, Any]:
    if isinstance(path, io.StringIO):
        return parse_csv_text(path.getvalue())
    data = parse_csv_text(Path(path).read_text(encoding="utf-8-sig", errors="replace"))
    if data["product"].get("_default_name"):
        data["product"]["name"] = Path(path).stem.replace("_", " ").replace("-", " ").title()
        data["product"]["phone"] = data["product"]["name"].lower()
    data["product"].pop("_default_name", None)
    return data


def parse_csv_text(text: str) -> Dict[str, Any]:
    text = text.replace("﻿", "")
    product: Dict[str, Any] = {}
    lines = []
    for line in text.splitlines():
        raw = line.strip()
        if raw.lower().startswith("#product,") or raw.lower().startswith("#product "):
            vals = [_norm(v) for v in next(csv.reader([raw[len("#product"):].lstrip(", ")]), [])]
            for k, v in zip(("name", "colour", "wordmark", "time", "date"), vals):
                if v:
                    product[k] = v
            continue
        low = raw.lower()
        if low.startswith("#pace"):                        # #pace,reveal  (default trailer)
            rest = _norm(raw[len("#pace"):].lstrip(",: ")).split(",")[0].strip().lower()
            if rest:
                product["pace"] = rest
            continue
        if low.startswith("#colors") or low.startswith("#colours"):   # #colors,Navy,Sky Blue,Pink,White -> cycled across shots
            vals = [_norm(v) for v in next(csv.reader([raw.split(",", 1)[1] if "," in raw else ""]), [])]
            product["colors"] = [v for v in vals if v]
            continue
        if raw.lower().startswith("#disclaimer"):
            rest = _norm(raw[len("#disclaimer"):].lstrip(",: "))
            if rest:
                product["disclaimer"] = rest
            continue
        m = re.match(r"\s*#\s*([A-Za-z_]+)\s*:\s*(.*)$", line)
        if m and _key(m.group(1)) in PRODUCT_KEYS:
            product[PRODUCT_KEYS[_key(m.group(1))]] = _norm(m.group(2))
            continue
        if line.strip() and not line.strip().startswith("#"):
            lines.append(line)
    rows = [[_norm(c) for c in r] for r in csv.reader(lines)]
    rows = [r for r in rows if any(r)]
    features: List[Dict[str, Any]] = []
    header: List[str] = []
    i = 0
    while i < len(rows):
        r = rows[i]
        keys = [_key(c) for c in r]
        if "feature" in keys or ("value" in keys and "kicker" in keys):
            header = keys
            i += 1
            continue
        if not header and keys and all(k in PRODUCT_KEYS for k in keys if k) and i + 1 < len(rows):
            for k, v in zip(keys, rows[i + 1]):        # a product header row + its value row
                if k and v:
                    product[PRODUCT_KEYS[k]] = v
            i += 2
            continue
        if not header and len(r) >= 2 and keys[0] in PRODUCT_KEYS and not any(keys[2:]):
            product[PRODUCT_KEYS[keys[0]]] = r[1]          # key,value form
            i += 1
            continue
        cols = header or list(FEATURE_COLS)
        rec = {c: (r[j] if j < len(r) else "") for j, c in enumerate(cols) if c}
        f = {c: _norm(rec.get(c, "")) for c in FEATURE_COLS}
        if f["value"] or f["feature"] or f["kicker"]:
            features.append(f)
        i += 1
    for n, f in enumerate(features):
        try:
            f["order"] = float(f["order"])
        except (TypeError, ValueError):
            f["order"] = float(n + 1)
        f["feature"] = f["feature"].lower()
    features.sort(key=lambda f: f["order"])
    if "name" not in product:
        product["name"], product["_default_name"] = "New Phone", True
    product.setdefault("phone", product["name"].lower())
    product.setdefault("disclaimer", DEFAULT_DISCLAIMER)
    product.setdefault("wordmark", product["name"])
    return {"product": product, "features": features}
