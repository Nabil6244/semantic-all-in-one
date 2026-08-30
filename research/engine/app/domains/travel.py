"""Travel domain adapter — stub. See products.py for the pattern; falls
back to generic extraction until deepened (itinerary/destination/price
fields, per README)."""
from __future__ import annotations

from app.domains.general import GeneralAdapter


class TravelAdapter(GeneralAdapter):
    domain = "travel"
