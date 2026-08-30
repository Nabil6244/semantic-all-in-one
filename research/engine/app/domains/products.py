"""Products domain adapter — stub.

Registered now so the adapter architecture and registry are exercised for a
second domain, but intentionally not deepened in V2 (per the brief: "Do NOT
implement every domain deeply yet"). Falls back entirely to the generic
rule-based extraction; a future pass can add product-specific structured
fields (price, brand, SKU, rating, availability) the same way
`real_estate.py` does for listings.
"""
from __future__ import annotations

from app.domains.general import GeneralAdapter


class ProductsAdapter(GeneralAdapter):
    domain = "products"
