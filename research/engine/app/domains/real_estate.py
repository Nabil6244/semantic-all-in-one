"""Real Estate domain adapter.

Extends the generic rule-based facts with structured (JSON-LD) and
text-heuristic extraction of listing-specific fields, worldwide (no
hard-coded US-only address/unit assumptions in the core patterns — the US
state gazetteer used for locations lives in `research/planner.py` and is
just one heuristic input among several here).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.extraction.facts import RuleBasedFactExtractor
from app.extraction.webpage import PageExtraction
from app.models.entity import EntityType, Location, NormalizedEntity
from app.models.fact import Fact
from app.models.media import MediaAsset, MediaType

_CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR"}

# (key, regex, canonical_unit) — each captures a numeric value plus the unit
# actually used in the text, preserved in `original_text` per-fact.
#
# Acres/sqft are already covered (with original_text) by the generic
# RuleBasedFactExtractor's text patterns — extending it here would just
# produce duplicate facts. This adapter only adds the worldwide units the
# generic extractor doesn't know about (hectares, square meters).
_AREA_PATTERNS = [
    ("lot_size", re.compile(r"(\d+(?:\.\d+)?)\s*[-\s]?hectares?\b", re.I), "hectares"),
    ("lot_size", re.compile(r"(\d+(?:\.\d+)?)\s*[-\s]?ha\b", re.I), "hectares"),
    ("square_footage", re.compile(r"([\d,]+(?:\.\d+)?)\s*(?:m²|m2|sq\.?\s?m\.?|square\s+met(?:er|re)s?)\b", re.I), "sqm"),
]

_PROPERTY_TYPES = [
    "farmhouse", "single family home", "single-family", "condominium", "condo",
    "townhouse", "town house", "apartment", "villa", "cottage", "ranch",
    "bungalow", "duplex", "mobile home", "cabin", "land", "lot", "estate",
    "manor", "penthouse", "loft",
]

_LISTING_STATUS_PATTERNS = [
    "off market", "under contract", "pending", "sold", "price reduced",
    "new listing", "for rent", "for sale",
]

_AMENITY_KEYWORDS = [
    "pool", "garage", "fireplace", "barn", "pond", "pasture", "fenced yard",
    "fenced", "workshop", "deck", "patio", "basement", "waterfront",
    "solar panels", "guest house", "wraparound porch", "porch",
]

_LISTING_ID_PATTERNS = [
    re.compile(r"\bMLS\s*#?\s*:?\s*([A-Za-z0-9-]{4,})\b", re.I),
    re.compile(r"\bListing\s*ID\s*:?\s*([A-Za-z0-9-]{3,})\b", re.I),
]

_HERO_KEYWORDS = re.compile(r"(front|exterior|hero|main)", re.I)
_FLOORPLAN_KEYWORDS = re.compile(r"(floor\s?plan|site\s?plan|blueprint)", re.I)
_MAP_KEYWORDS = re.compile(r"\bmap\b", re.I)
_AERIAL_KEYWORDS = re.compile(r"(aerial|drone|overhead|bird'?s?[-\s]?eye)", re.I)

# --- Granular role vocabulary -------------------------------------------
# Finer roles so a consumer can ask for a specific authentic shot (the
# driveway approach, the creek, a construction close-up) instead of getting
# an undifferentiated "gallery" pile and falling back to generic stock.
# The coarse roles above (hero/gallery/floor_plan/map/aerial) are preserved
# exactly — these are assigned *within* what would otherwise be "gallery",
# and `role_group` keeps the old coarse value available.
_ROLE_PATTERNS = (
    # Ordered most-specific first; first match wins. Every alternative is
    # word-bounded: without \b, "land" matches inside "Portland"/"Highland"
    # and a listing in Portland was being labelled land — an invented role
    # from a city name in a CDN path is exactly what must not happen here.
    ("floor_plan", re.compile(r"\b(floor\s?plans?|floorplans?|site\s?plans?|blueprints?)\b", re.I)),
    ("boundary_map", re.compile(
        r"\b(parcels?|boundary|boundaries|plat|surveys?|lot\s?lines?)\b", re.I)),
    ("map", re.compile(r"\b(maps?|satellite\s?views?)\b", re.I)),
    ("aerial", re.compile(r"\b(aerials?|drones?|overhead|bird'?s?[-\s]?eye|birdseye)\b", re.I)),
    ("construction_detail", re.compile(
        r"\b(hand[-\s]?hewn|chinking|chinked|log\s?walls?|beams?|rafters?|trusses|truss|joists?|"
        r"planks?|masonry|stonework|shingles?|siding|craftsmanship|close[-\s]?ups?|"
        r"foundations?|framing|subfloors?|drywall|insulation|hvac|plumbing|wiring|"
        r"electrical\s?panels?|septic|crawl\s?space|studs?)\b", re.I)),
    ("approach", re.compile(
        r"\b(driveways?|drive\s?ways?|gates?|gated|entrances?|entry\s?roads?|"
        r"lanes?|approach|walkways?|pathways?|access\s?roads?)\b", re.I)),
    ("waterfront", re.compile(
        r"\b(waterfront|water\s?front|frontage|shorelines?|docks?|piers?|lakefront|riverfront)\b", re.I)),
    ("water", re.compile(
        r"\b(creeks?|rivers?|streams?|ponds?|lakes?|brooks?|waterfalls?|spring\s?fed|springs?|"
        r"marsh|wetlands?)\b", re.I)),
    ("recreation", re.compile(
        r"\b(fishing|fish|muskie|bass|trout|kayaks?|canoes?|hunting|trails?|atv|campfires?|"
        r"fire\s?pits?|firepits?|swimming\s?pools?|pools?|hot\s?tubs?|jacuzzi|saunas?|"
        r"playgrounds?|tennis\s?courts?|basketball\s?courts?|pickleball|golf|"
        r"putting\s?greens?|game\s?rooms?|home\s?gyms?)\b", re.I)),
    ("interior", re.compile(
        r"\b(interiors?|kitchens?|bathrooms?|bedrooms?|living\s?rooms?|dining\s?rooms?|"
        r"family\s?rooms?|hallways?|closets?|pantry|basements?|attics?|laundry|"
        r"staircases?|stairwells?|primary\s?suite|master\s?suite|en\s?suite|"
        r"breakfast\s?nooks?|fireplaces?)\b", re.I)),
    ("exterior", re.compile(
        r"\b(exteriors?|facades?|curb\s?appeal|porch(?:es)?|decks?|patios?|lawns?|"
        r"gardens?|landscaping|back\s?yards?|backyards?|front\s?yards?|"
        r"front\s?elevation|rear\s?elevation)\b", re.I)),
    ("structure", re.compile(
        r"\b(barns?|sheds?|garages?|workshops?|outbuildings?|silos?|stables?|greenhouses?|"
        r"carports?|guest\s?houses?|guest\s?cottages?|pole\s?barns?|storage\s?buildings?|"
        r"chicken\s?coops?|cabins?)\b", re.I)),
    # `interior`/`exterior` deliberately precede `structure`: a caption
    # naming the SHOT TYPE ("front exterior of the cabin") is describing the
    # view, not the outbuilding, so the shot type wins over a building noun
    # that merely appears in the same sentence.
    ("land", re.compile(
        r"\b(acres?|acreage|pastures?|meadows?|fields?|woods|wooded|timber|clearings?|"
        r"paddocks?|land)\b", re.I)),
)


def _flatten_name(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("name") or value.get("legalName")
    if isinstance(value, list) and value:
        return _flatten_name(value[0])
    return None


def _to_number(raw: str) -> Optional[float]:
    cleaned = raw.replace(",", "").strip()
    try:
        val = float(cleaned)
        return int(val) if val.is_integer() else val
    except ValueError:
        return None


def _find_listing_entities(json_ld: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from app.extraction.structured_data import find_entities_by_type

    return find_entities_by_type(
        json_ld, "RealEstateListing", "House", "SingleFamilyResidence",
        "Apartment", "Accommodation", "Residence", "Product",
    ) or json_ld


def _extract_currency(text: str, offers: Optional[Dict[str, Any]]) -> Optional[str]:
    if offers and offers.get("priceCurrency"):
        return str(offers["priceCurrency"])
    for symbol, code in _CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code
    return None


def _extract_geo(entity: Dict[str, Any]) -> Optional[tuple]:
    geo = entity.get("geo")
    if isinstance(geo, dict):
        lat, lon = geo.get("latitude"), geo.get("longitude")
        if lat is not None and lon is not None:
            try:
                return float(lat), float(lon)
            except (TypeError, ValueError):
                return None
    return None


def _address_fields(entity: Dict[str, Any]) -> Dict[str, str]:
    address = entity.get("address")
    if not isinstance(address, dict):
        return {}
    mapping = {
        "streetAddress": "address_street",
        "addressLocality": "address_city",
        "addressRegion": "address_state",
        "postalCode": "address_postal_code",
        "addressCountry": "address_country",
    }
    out = {}
    for schema_field, fact_key in mapping.items():
        val = address.get(schema_field)
        if isinstance(val, dict):
            val = val.get("name")
        if val:
            out[fact_key] = str(val)
    return out


class RealEstateAdapter:
    domain = "real_estate"

    def extract_facts(self, page: PageExtraction, source_id: str) -> List[Fact]:
        if not page.accessible:
            return []
        facts = RuleBasedFactExtractor().extract(page, source_id)
        facts.extend(self._structured_facts(page, source_id))
        facts.extend(self._text_facts(page, source_id))
        return facts

    def _structured_facts(self, page: PageExtraction, source_id: str) -> List[Fact]:
        facts: List[Fact] = []
        for entity in _find_listing_entities(page.json_ld):
            offers = entity.get("offers")
            if isinstance(offers, list) and offers:
                offers = offers[0]
            offers = offers if isinstance(offers, dict) else None

            currency = _extract_currency(page.visible_text[:500], offers)
            if currency:
                facts.append(Fact(key="currency", value=currency, normalized_value=currency, source_id=source_id, confidence=0.85))

            for fact_key, value in _address_fields(entity).items():
                facts.append(Fact(key=fact_key, value=value, source_id=source_id, confidence=0.9))

            geo = _extract_geo(entity)
            if geo:
                lat, lon = geo
                facts.append(Fact(key="latitude", value=str(lat), normalized_value=lat, source_id=source_id, confidence=0.9))
                facts.append(Fact(key="longitude", value=str(lon), normalized_value=lon, source_id=source_id, confidence=0.9))

            for agent_field in ("agent", "broker", "provider", "seller"):
                name = _flatten_name(entity.get(agent_field))
                if name:
                    facts.append(Fact(key="agent", value=name, source_id=source_id, confidence=0.8))
                    break

            for id_field in ("sku", "productID", "identifier"):
                val = entity.get(id_field)
                if isinstance(val, (str, int)):
                    facts.append(Fact(key="listing_id", value=str(val), source_id=source_id, confidence=0.85))
                    break

            amenities = entity.get("amenityFeature")
            if isinstance(amenities, list):
                for item in amenities:
                    name = item.get("name") if isinstance(item, dict) else item
                    if name:
                        facts.append(Fact(key="feature", value=str(name), source_id=source_id, confidence=0.85))
        return facts

    def _text_facts(self, page: PageExtraction, source_id: str) -> List[Fact]:
        facts: List[Fact] = []
        text = page.visible_text or ""
        lowered = text.lower()
        title = (page.title or "")

        for key, pattern, unit in _AREA_PATTERNS:
            for match in pattern.finditer(text):
                raw_value = match.group(1)
                facts.append(
                    Fact(
                        key=key, value=f"{raw_value} {unit}", normalized_value=_to_number(raw_value),
                        unit=unit, original_text=match.group(0).strip(),
                        source_id=source_id, confidence=0.55,
                    )
                )

        for ptype in _PROPERTY_TYPES:
            if ptype in lowered:
                facts.append(Fact(key="property_type", value=ptype, source_id=source_id, confidence=0.5, original_text=ptype))
                break

        for status in _LISTING_STATUS_PATTERNS:
            if status in lowered:
                facts.append(Fact(key="listing_status", value=status, source_id=source_id, confidence=0.5))
                break

        for pattern in _LISTING_ID_PATTERNS:
            match = pattern.search(text)
            if match:
                facts.append(Fact(key="listing_id", value=match.group(1), source_id=source_id, confidence=0.6, original_text=match.group(0)))
                break

        for amenity in _AMENITY_KEYWORDS:
            if re.search(rf"\b{re.escape(amenity)}\b", lowered):
                facts.append(Fact(key="feature", value=amenity, source_id=source_id, confidence=0.4))

        return facts

    def build_entity(
        self, entity_id: str, facts: List[Fact], page: PageExtraction, source_ids: List[str]
    ) -> Optional[NormalizedEntity]:
        if not page.accessible:
            return None
        # Prefer the highest-confidence fact per key (JSON-LD over regex),
        # and prefer its normalized_value over the display-formatted value
        # string (e.g. 20 rather than "20 acres") so downstream numeric
        # comparisons (property matching) don't have to re-parse text.
        best_facts: Dict[str, Fact] = {}
        for fact in facts:
            current = best_facts.get(fact.key)
            if current is None or fact.confidence > current.confidence:
                best_facts[fact.key] = fact
        by_key: Dict[str, object] = {
            key: (fact.normalized_value if fact.normalized_value is not None else fact.value)
            for key, fact in best_facts.items()
        }

        location = None
        if any(k in by_key for k in ("address_city", "address_state", "address_country", "address")):
            lat = by_key.get("latitude")
            lon = by_key.get("longitude")
            location = Location(
                street=by_key.get("address_street"),
                city=by_key.get("address_city"),
                state=by_key.get("address_state"),
                country=by_key.get("address_country"),
                postal_code=by_key.get("address_postal_code"),
                latitude=float(lat) if lat is not None else None,
                longitude=float(lon) if lon is not None else None,
            )

        attributes = {k: v for k, v in by_key.items() if not k.startswith("address_")}
        return NormalizedEntity(
            entity_id=entity_id,
            entity_type=EntityType.PROPERTY,
            name=by_key.get("title") or page.title,
            location=location,
            attributes=attributes,
            source_ids=source_ids,
        )

    @staticmethod
    def _detail_role(haystack: str) -> Optional[str]:
        """First matching granular role, or None when nothing matches —
        an unknown shot is left unlabelled rather than guessed at."""
        for name, pattern in _ROLE_PATTERNS:
            if pattern.search(haystack):
                return name
        return None

    def classify_media(self, assets: List[MediaAsset], page: PageExtraction) -> List[MediaAsset]:
        hero_assigned = False
        for asset in assets:
            haystack = " ".join(filter(None, [asset.title, asset.alt, asset.caption, asset.source_url])).lower()

            # Granular role is independent of the coarse one: a hero image is
            # still usually *also* an exterior, and a gallery photo is the
            # kitchen or the creek. Assigned for videos too.
            asset.role_detail = self._detail_role(haystack)

            if asset.media_type == MediaType.VIDEO:
                asset.role = "aerial_video" if _AERIAL_KEYWORDS.search(haystack) else "video"
                continue

            if _FLOORPLAN_KEYWORDS.search(haystack):
                asset.role = "floor_plan"
            elif _MAP_KEYWORDS.search(haystack):
                asset.role = "map"
            elif _AERIAL_KEYWORDS.search(haystack):
                asset.role = "aerial"
                # An aerial that also reads as a parcel/boundary diagram is
                # the shot acreage narration wants.
                if asset.role_detail is None:
                    asset.role_detail = "aerial"
            elif not hero_assigned and (asset.provider == "og_image" or _HERO_KEYWORDS.search(haystack) or asset.page_position == 0):
                asset.role = "hero"
                hero_assigned = True
            else:
                asset.role = "gallery"
        return assets
