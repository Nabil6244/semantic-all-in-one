"""Before / after pictures from space: NASA GIBS daily corrected-reflectance layers (MODIS on Terra and Aqua, VIIRS), one
picture per day, served as XYZ tiles (GIBS numbers its tiles {z}/{y}/{x}).

`truecolor` is what the eye would see. `falsecolor` (MODIS bands 7-2-1) shows water as dark blue and land as green, so flooded
ground stands out from fields and cloud even where true colour looks grey: the layer NASA itself uses for flood pictures."""

from __future__ import annotations

from datetime import date
from typing import Dict

BASE = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best"
LAYERS = {
    "truecolor": ("MODIS_Terra_CorrectedReflectance_TrueColor", "MODIS Terra true colour"),
    "truecolor_aqua": ("MODIS_Aqua_CorrectedReflectance_TrueColor", "MODIS Aqua true colour"),
    "truecolor_viirs": ("VIIRS_SNPP_CorrectedReflectance_TrueColor", "VIIRS true colour"),
    "falsecolor": ("MODIS_Terra_CorrectedReflectance_Bands721", "MODIS Terra bands 7-2-1"),
    "falsecolor_aqua": ("MODIS_Aqua_CorrectedReflectance_Bands721", "MODIS Aqua bands 7-2-1"),
}
MAX_ZOOM = 9
CREDIT = "Before / after: NASA EOSDIS GIBS (MODIS / VIIRS corrected reflectance)."


def layer(product: str) -> "tuple[str, str]":
    if product not in LAYERS:
        raise ValueError(f"unknown GIBS picture {product!r} (use {', '.join(LAYERS)})")
    return LAYERS[product]


def tile_template(product: str, d: date) -> str:
    name, _title = layer(product)
    return f"{BASE}/{name}/default/{d.isoformat()}/GoogleMapsCompatible_Level{MAX_ZOOM}/{{z}}/{{y}}/{{x}}.jpg"


def provider(product: str, d: date) -> Dict:
    """A weather-engine tile provider; its id names the layer and the day (the tile cache is keyed by it)."""
    name, title = layer(product)
    return {"id": f"wx_gibs_{product}_{d:%Y%m%d}", "title": f"{title}, {d.isoformat()}", "urlTemplate": tile_template(product, d),
            "format": "jpg", "tileSize": 256, "maxNativeZoom": MAX_ZOOM}


def domain_url(product: str, d: date) -> str:
    name, _title = layer(product)
    return f"{BASE}/1.0.0/{name}/default/GoogleMapsCompatible_Level{MAX_ZOOM}/all/{d.isoformat()}--{d.isoformat()}.xml"


def has_day(domain_xml: str) -> bool:
    """True when GIBS's DescribeDomains answer lists a picture for the day asked (<Size>1</Size>)."""
    import re

    m = re.search(r"<Size>(\d+)</Size>", domain_xml)
    return bool(m and int(m.group(1)) > 0)
