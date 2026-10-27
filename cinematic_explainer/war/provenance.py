"""Provenance for War Documentary assets: only what the existing providers actually record; nothing is invented, nothing is verified by default.

Manifest record keys read (asset_manager._record_from_result): source, provider, provider_asset_id, author, source_url, license (YouTube
only: the uploader-reported string), video_title, channel, local_path, width, height, duration. The Openverse licence is NOT saved in the
manifest, so an Openverse asset has licence 'unknown' here until it is supplied another way.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional

STATUSES = ("confirmed", "attributed", "disputed", "unverified", "illustrative")
UNKNOWN = "unknown"


@dataclass
class Provenance:
    asset_id: str = ""
    category: str = ""             # footage | image | map | equipment | figure | statistic | document | graphic
    description: str = ""
    source_url: str = ""
    provider: str = ""
    provider_asset_id: str = ""
    event_date: str = ""           # when the thing happened (never filled from upload dates)
    captured_date: str = ""        # when the footage was recorded
    published_date: str = ""       # when the source published it
    location: str = ""
    licence: str = UNKNOWN
    attribution: str = ""
    status: str = "unverified"
    caveats: List[str] = field(default_factory=list)
    recycled: bool = False
    mismatch: bool = False
    disputed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Provenance":
        names = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        p = cls(**{k: v for k, v in (d or {}).items() if k in names})
        if p.status not in STATUSES:
            p.status = "unverified"
        return p


def from_manifest_record(record: Optional[Dict[str, Any]], asset_id: str = "") -> Provenance:
    """Map an app manifest record to Provenance without claiming verification."""
    r = dict(record or {})
    provider = str(r.get("provider") or r.get("source") or "").strip()
    author = str(r.get("author") or r.get("channel") or "").strip()
    url = str(r.get("source_url") or "").strip()
    lic = str(r.get("license") or r.get("licence") or "").strip() or UNKNOWN
    title = str(r.get("video_title") or "").strip()
    p = Provenance(asset_id=asset_id or str(r.get("provider_asset_id") or ""), category="footage" if str(r.get("type") or "").startswith("video") else "image",
                   description=title or str(r.get("stock_query") or r.get("prompt") or "")[:120], source_url=url, provider=provider,
                   provider_asset_id=str(r.get("provider_asset_id") or ""), licence=lic, attribution=author)
    p.caveats.append("dates and place not verified")
    if lic == UNKNOWN:
        p.caveats.append("licence unknown")
    if author and url:
        p.status = "attributed"       # only 'published by <author> at <url>'; says nothing about what the footage shows
    return p


def usable_as_evidence(p: Provenance) -> bool:
    """Evidence of a real event: never for unverified or illustrative assets, never when flagged."""
    if p.recycled or p.mismatch:
        return False
    return p.status in ("confirmed", "attributed")   # disputed only inside a two-sided frame, so not plain evidence


def requires_label(p: Provenance) -> Optional[str]:
    """The on-screen label the asset needs, or None."""
    if p.status == "illustrative":
        return "ILLUSTRATIVE"
    if p.recycled:
        return "FILE FOOTAGE"
    if p.mismatch:
        return "ILLUSTRATIVE FOOTAGE"
    if p.disputed or p.status == "disputed":
        return "DISPUTED"
    if p.status == "unverified":
        return "UNVERIFIED"
    if p.status == "attributed":
        return "ATTRIBUTED"
    return None


def credits_lines(items: Iterable[Provenance]) -> List[str]:
    """One credit line per attributable asset; assets with no author and no source are skipped; no duplicates."""
    seen = set()
    out: List[str] = []
    for p in items:
        who = (p.attribution or "").strip()
        src = (p.provider or "").strip()
        if not who and not src:
            continue
        bits = [who or src]
        if who and src and src.lower() not in who.lower():
            bits.append(f"via {src}")
        if p.source_url:
            bits.append(p.source_url)
        if p.licence and p.licence != UNKNOWN:
            bits.append(f"licence: {p.licence}")
        line = " | ".join(bits)
        if line not in seen:
            seen.add(line)
            out.append(line)
    return out


# ----------------------------------------------------------------------------------------------------------------------------
# how a manifest record is treated as footage (honest classification; nothing here verifies anything)
# ----------------------------------------------------------------------------------------------------------------------------

_USER_SOURCES = ("local", "manual")
_STOCK_MARKS = ("stock", "pexels", "pixabay", "openverse", "nasa", "archive", "commons", "wikimedia", "research", "map")
_GENERATED_MARKS = ("flow", "ai_", "generated")


def classify_record(record: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """What kind of source a manifest record is and what that allows. Returns
    {kind: user|youtube|stock|generated|unknown, generic (bool: not footage of a specific event), user_supplied, rights (short text),
     rights_known (bool: an explicit licence string or the user's own statement exists), licence, source_chip (show a source chip)}.
    Stock, archive, NASA, Commons and generated clips are generic b-roll: they are never labelled as footage of a specific event.
    A YouTube clip is a third party's: never treated as reusable; its uploader-reported licence string is carried, clearance stays open."""
    r = dict(record or {})
    src = str(r.get("source") or "").strip().lower()
    prov = str(r.get("provider") or "").strip().lower()
    lic = str(r.get("license") or r.get("licence") or "").strip()
    tag = f"{src} {prov}"
    if src in _USER_SOURCES or prov in _USER_SOURCES:
        return {"kind": "user", "generic": False, "user_supplied": True, "rights": "user-supplied; rights stated by the user", "rights_known": True,
                "licence": lic or "user-supplied", "source_chip": False}
    if "youtube" in tag:
        note = f"uploader-reported licence '{lic}'; clearance needed" if lic else "licence unknown; clearance needed"
        return {"kind": "youtube", "generic": False, "user_supplied": False, "rights": note, "rights_known": False,
                "licence": lic or UNKNOWN, "source_chip": True}
    if any(m in tag for m in _GENERATED_MARKS):
        return {"kind": "generated", "generic": True, "user_supplied": False, "rights": "generated image/video; illustrative only", "rights_known": False,
                "licence": lic or UNKNOWN, "source_chip": False}
    if any(m in tag for m in _STOCK_MARKS):
        note = f"licence '{lic}' as recorded" if lic else "licence not recorded in the project; provider terms apply"
        return {"kind": "stock", "generic": True, "user_supplied": False, "rights": note, "rights_known": bool(lic), "licence": lic or UNKNOWN,
                "source_chip": False}
    return {"kind": "unknown", "generic": True, "user_supplied": False, "rights": "source not recorded", "rights_known": False,
            "licence": lic or UNKNOWN, "source_chip": False}


def credits_text(entries: Iterable[Dict[str, Any]]) -> str:
    """The credits / description text for the assets actually used. entries: {scene_no, prov (Provenance), kind, rights, rights_known, file}.
    Nothing is skipped silently: an asset with no attributable author or provider, or whose licence is not established, is listed under
    'Rights not established'; user-supplied files are listed under their own heading."""
    ents = list(entries)
    out: List[str] = ["Footage and image credits (from the project's own asset records; nothing here is verified or invented)", ""]
    credited = credits_lines([e["prov"] for e in ents if e.get("kind") != "user"])
    out.append("Credits:")
    out += [f"- {line}" for line in credited] or ["- (none recorded)"]
    out.append("")
    user = [e for e in ents if e.get("kind") == "user"]
    if user:
        out.append("User-supplied files (rights are the user's responsibility):")
        out += [f"- scene {e.get('scene_no')}: {e.get('file') or 'file'}" for e in user]
        out.append("")
    unresolved = []
    for e in ents:
        if e.get("kind") == "user":
            continue
        p = e["prov"]
        if p.licence == UNKNOWN or not e.get("rights_known") or not (p.attribution or p.provider):
            what = " ".join(x for x in (p.provider, p.provider_asset_id) if x) or (e.get("file") or "clip")
            unresolved.append(f"- scene {e.get('scene_no')}: {what}" + (f" ({p.source_url})" if p.source_url else "") + f" - {e.get('rights') or 'rights not established'}")
    out.append("Rights not established (licence unknown or clearance needed before publishing):")
    out += unresolved or ["- (none)"]
    return "\n".join(out) + "\n"
