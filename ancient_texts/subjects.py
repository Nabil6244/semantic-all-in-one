"""Subject packs: the data that makes the core about one subject (Enoch, Jubilees, the Dead Sea Scrolls ...).

A pack is JSON in ancient_texts/packs/<pack_id>.json (or any path). Nothing in the code depends on a particular pack.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Union

from .issues import ValidationError

PACKS_DIR = Path(__file__).resolve().parent / "packs"
SCHEMA_VERSION = 1
_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
MOTIF_KINDS = ("document", "artwork", "place")


@dataclasses.dataclass(frozen=True)
class Scholar:
    name: str
    aliases: tuple = ()
    credential: Optional[str] = None
    credential_source_id: Optional[str] = None

    @property
    def names(self) -> tuple:
        return (self.name,) + tuple(self.aliases)


@dataclasses.dataclass(frozen=True)
class Motif:
    id: str
    concept_terms: tuple
    query: str
    kind: str


@dataclasses.dataclass(frozen=True)
class WatchItem:
    id: str
    topic: str
    prompt: str
    status: str


@dataclasses.dataclass(frozen=True)
class SubjectPack:
    pack_id: str
    subject: str
    style_id: str
    subject_terms: tuple
    document_terms: tuple
    place_terms: tuple
    scholars: tuple
    anchor_motifs: tuple
    source_notes: tuple
    research_watch_list: tuple

    def scholar_for(self, text: str) -> Optional[Scholar]:
        low = (text or "").lower()
        for s in self.scholars:
            if any(_has_term(low, n.lower()) for n in s.names):
                return s
        return None


def _has_term(low_text: str, term: str) -> bool:
    return bool(term) and re.search(r"(?<![\w'])" + re.escape(term) + r"(?![\w'])", low_text) is not None


def has_term(text: str, term: str) -> bool:
    """Whole-word, case-insensitive match (accents kept as written)."""
    return _has_term((text or "").lower(), (term or "").lower())


def pack_from_dict(data: dict, *, where: str = "pack") -> SubjectPack:
    problems: List[str] = []
    if not isinstance(data, dict):
        raise ValidationError(where, ["a pack is a JSON object"])
    for key in ("pack_id", "schema_version", "subject", "style_id"):
        if key not in data:
            problems.append(f"missing '{key}'")
    if problems:
        raise ValidationError(where, problems)
    if data["schema_version"] != SCHEMA_VERSION:
        problems.append(f"schema_version {data['schema_version']!r} is not supported (expected {SCHEMA_VERSION})")
    if not isinstance(data["pack_id"], str) or not _ID_RE.match(data["pack_id"]):
        problems.append(f"pack_id {data['pack_id']!r} must be lowercase letters, digits and '_'")

    def terms(key: str) -> tuple:
        raw = data.get(key, [])
        if not isinstance(raw, list) or not all(isinstance(t, str) and t.strip() for t in raw):
            problems.append(f"'{key}' must be a list of non-empty strings")
            return ()
        bad = [t for t in raw if t != t.lower()]
        if bad:
            problems.append(f"'{key}' must be lowercase: {bad[:3]}")
        return tuple(raw)

    subject_terms, document_terms, place_terms = terms("subject_terms"), terms("document_terms"), terms("place_terms")

    scholars = []
    for i, s in enumerate(data.get("scholars", []) or []):
        if not isinstance(s, dict) or not str(s.get("name") or "").strip():
            problems.append(f"scholars[{i}] needs a name")
            continue
        cred, src = s.get("credential"), s.get("credential_source_id")
        if cred and not src:
            problems.append(f"scholars[{i}] ({s['name']}): a credential needs credential_source_id (never store an unbacked credential)")
        scholars.append(Scholar(name=s["name"].strip(), aliases=tuple(s.get("aliases") or ()), credential=cred or None,
                                credential_source_id=src or None))

    motifs, seen = [], set()
    for i, m in enumerate(data.get("anchor_motifs", []) or []):
        if not isinstance(m, dict):
            problems.append(f"anchor_motifs[{i}] must be an object")
            continue
        mid = str(m.get("id") or "")
        if not _ID_RE.match(mid):
            problems.append(f"anchor_motifs[{i}].id {mid!r} is malformed")
        if mid in seen:
            problems.append(f"anchor_motifs: duplicate id {mid!r}")
        seen.add(mid)
        if m.get("kind") not in MOTIF_KINDS:
            problems.append(f"anchor_motifs[{i}].kind must be one of {MOTIF_KINDS}")
        if not str(m.get("query") or "").strip() or not m.get("concept_terms"):
            problems.append(f"anchor_motifs[{i}] needs a query and concept_terms")
        motifs.append(Motif(id=mid, concept_terms=tuple(t.lower() for t in m.get("concept_terms") or ()),
                            query=str(m.get("query") or "").strip(), kind=str(m.get("kind") or "")))

    watch, wseen = [], set()
    for i, w in enumerate(data.get("research_watch_list", []) or []):
        if not isinstance(w, dict) or not all(str(w.get(k) or "").strip() for k in ("id", "topic", "prompt", "status")):
            problems.append(f"research_watch_list[{i}] needs id, topic, prompt and status")
            continue
        if w["status"] != "to_verify":
            problems.append(f"research_watch_list[{i}] ({w['id']}): a pack only carries open questions (status 'to_verify'); "
                            "findings belong in a claims ledger")
        if w["id"] in wseen:
            problems.append(f"research_watch_list: duplicate id {w['id']!r}")
        wseen.add(w["id"])
        watch.append(WatchItem(id=w["id"], topic=w["topic"], prompt=w["prompt"], status=w["status"]))

    if problems:
        raise ValidationError(where, problems)
    return SubjectPack(pack_id=data["pack_id"], subject=str(data["subject"]), style_id=str(data["style_id"]),
                       subject_terms=subject_terms, document_terms=document_terms, place_terms=place_terms,
                       scholars=tuple(scholars), anchor_motifs=tuple(motifs),
                       source_notes=tuple(str(n) for n in data.get("source_notes", []) or ()), research_watch_list=tuple(watch))


def load_pack(pack: Union[str, Path]) -> SubjectPack:
    """A pack by id ("enoch") or by path."""
    path = Path(pack)
    if not path.suffix:
        path = PACKS_DIR / f"{pack}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValidationError(str(path), ["pack file not found"]) from None
    except json.JSONDecodeError as exc:
        raise ValidationError(str(path), [f"not valid JSON: {exc}"]) from None
    return pack_from_dict(data, where=str(path))


def pack_for_style(style_id: str) -> Optional[SubjectPack]:
    """The first built-in pack that names this style, or None."""
    for path in sorted(PACKS_DIR.glob("*.json")):
        try:
            p = load_pack(path)
        except ValidationError:
            continue
        if p.style_id == style_id:
            return p
    return None


def term_hits(text: str, terms) -> List[str]:
    return [t for t in terms if has_term(text, t)]


def all_terms(pack: SubjectPack) -> Dict[str, tuple]:
    return {"subject": pack.subject_terms, "document": pack.document_terms, "place": pack.place_terms}
