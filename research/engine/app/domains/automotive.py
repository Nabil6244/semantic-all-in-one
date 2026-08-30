"""Automotive domain adapter — stub. See products.py for the pattern; falls
back to generic extraction until deepened (make/model/year/mileage/price
fields, per README)."""
from __future__ import annotations

from app.domains.general import GeneralAdapter


class AutomotiveAdapter(GeneralAdapter):
    domain = "cars"
