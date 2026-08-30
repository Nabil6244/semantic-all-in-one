"""Science domain adapter — stub. See products.py for the pattern; falls
back to generic extraction until deepened (journal/authors/DOI fields, per
README)."""
from __future__ import annotations

from app.domains.general import GeneralAdapter


class ScienceAdapter(GeneralAdapter):
    domain = "science"
