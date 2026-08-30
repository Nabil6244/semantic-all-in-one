"""Generic page metadata extraction (title, description, canonical, dates)."""
from __future__ import annotations

from typing import Dict, Optional

from bs4 import BeautifulSoup

from app.extraction.structured_data import parse_opengraph


def extract_title(soup: BeautifulSoup, og: Optional[Dict[str, str]] = None) -> Optional[str]:
    og = og or {}
    if og.get("og:title"):
        return og["og:title"]
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return None


def extract_description(soup: BeautifulSoup, og: Optional[Dict[str, str]] = None) -> Optional[str]:
    og = og or {}
    if og.get("og:description"):
        return og["og:description"]
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return meta["content"].strip()
    return None


def extract_canonical(soup: BeautifulSoup) -> Optional[str]:
    link = soup.find("link", rel="canonical")
    if link and link.get("href"):
        return link["href"].strip()
    return None


def extract_published_date(soup: BeautifulSoup) -> Optional[str]:
    for attrs in (
        {"property": "article:published_time"},
        {"name": "date"},
        {"itemprop": "datePublished"},
    ):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            return tag["content"].strip()
    time_tag = soup.find("time")
    if time_tag and time_tag.get("datetime"):
        return time_tag["datetime"].strip()
    return None


def extract_visible_text(soup: BeautifulSoup, max_chars: int = 20000) -> str:
    """Best-effort visible text extraction: strips script/style/nav/footer noise."""
    clone = BeautifulSoup(str(soup), "lxml")
    for tag in clone(["script", "style", "noscript", "nav", "footer", "header", "svg"]):
        tag.decompose()
    text = clone.get_text(separator=" ", strip=True)
    text = " ".join(text.split())
    return text[:max_chars]


def extract_page_metadata(html: str) -> Dict[str, object]:
    soup = BeautifulSoup(html, "lxml")
    og = parse_opengraph(soup)
    return {
        "title": extract_title(soup, og),
        "description": extract_description(soup, og),
        "canonical_url": extract_canonical(soup),
        "published_date": extract_published_date(soup),
        "opengraph": og,
        "visible_text": extract_visible_text(soup),
    }
