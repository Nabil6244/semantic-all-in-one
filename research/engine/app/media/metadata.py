"""Media metadata/license helpers.

We never claim media is free to reuse without evidence. License detection is
a conservative heuristic:
- a `rel="license"` link or anchor pointing at a recognized Creative Commons
  / public-domain URL is the only thing that yields anything but "unknown"
  in the reuse-friendly direction.
- an explicit copyright notice ("All rights reserved", "©") with no such
  license evidence is recorded as "restricted" — that's still *evidence*,
  just evidence pointing the other way.
- everything else stays "unknown". Discovery is not a reuse grant.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from app.extraction.webpage import PageExtraction
from app.models.media import LicenseStatus, MediaAsset

_CC_PATTERN = re.compile(r"creativecommons\.org/(licenses|publicdomain)/[\w./-]+", re.I)
_COPYRIGHT_PATTERN = re.compile(r"(all rights reserved|©|\(c\)\s*\d{4})", re.I)


def detect_page_license(page: PageExtraction) -> Tuple[LicenseStatus, Optional[str]]:
    if not page.accessible or page.soup is None:
        return LicenseStatus.UNKNOWN, None

    license_link = page.soup.find("link", rel="license")
    if license_link and license_link.get("href"):
        href = license_link["href"]
        cc_match = _CC_PATTERN.search(href)
        if cc_match:
            status = LicenseStatus.PUBLIC_DOMAIN if cc_match.group(1) == "publicdomain" else LicenseStatus.CREATIVE_COMMONS
            return status, href
        return LicenseStatus.OBSERVED_LICENSE, href

    for anchor in page.soup.find_all("a", href=True):
        cc_match = _CC_PATTERN.search(anchor["href"])
        if cc_match:
            status = LicenseStatus.PUBLIC_DOMAIN if cc_match.group(1) == "publicdomain" else LicenseStatus.CREATIVE_COMMONS
            return status, anchor["href"]

    footer_text = " ".join(
        tag.get_text(" ", strip=True) for tag in page.soup.find_all(["footer", "small"])
    )
    copyright_match = _COPYRIGHT_PATTERN.search(footer_text) or _COPYRIGHT_PATTERN.search(page.visible_text[-500:])
    if copyright_match:
        return LicenseStatus.RESTRICTED, copyright_match.group(0)

    return LicenseStatus.UNKNOWN, None


def apply_license_info(assets: List[MediaAsset], page: PageExtraction) -> List[MediaAsset]:
    status, evidence = detect_page_license(page)
    for asset in assets:
        asset.license_status = status
        asset.license_evidence = evidence
    return assets
