"""The authoritative sources the engine may choose, and what each one really is.

Every source here is one Weather already reads through a tested client (weather/news, weather/post, weather/resolve), or an index
the engine reads to resolve an event (the NHC storm list and advisory archive). Capabilities were checked against the providers'
documentation, the fixtures in weather/testdata and controlled live requests (2026-10-13/14); nothing here is assumed from a
provider offering "similar" products. The engine never asks a source for something outside its coverage; when it must (an
archive that may not hold a date), a 404 is recorded as "not archived", never as a network failure.

`SOURCES[id]` -> Source; the report and the evidence name sources by these ids."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    measures: str
    coverage: str
    history: str
    updates: str
    times: str  # which times the product carries (issue / observation / valid)
    units: str
    license: str
    attribution: str
    limits: str
    caveats: str
    kind: str  # observed | forecast | warning | preliminary | best_track | index | imagery | derived

    def to_dict(self) -> dict:
        return asdict(self)


_S = [
    Source("nhc_storm_list", "NHC ATCF storm list", "identity of every numbered Atlantic / Pacific system: name, basin, number, year, "
           "first and last times, status (ARCHIVE / WARNING / GENESIS / METWATCH)", "Atlantic, eastern and central Pacific",
           "1851 to the current season", "while a system is active", "first / last fix times (UTC, YYYYMMDDHH)", "-",
           "US government work, public domain", "NOAA National Hurricane Center", "one small text file; cached 6 h",
           "a current-season storm has an open end time (9999999999) and its last status, not its peak", "index"),
    Source("nhc_gis_advisory", "NHC GIS advisory archive", "an advisory's 5-day cone, forecast track and points, coastal watches / "
           "warnings", "storms NHC advised on", "about 2008 to the current season", "every 6 h (03/09/15/21 UTC) plus intermediate "
           "A advisories", "ADVDATE (issue, local), forecast points VALIDTIME (UTC)", "wind kt (shown as mph rounded to 5)",
           "public domain", "NOAA National Hurricane Center", "zip files of tens of kB; cached",
           "a forecast, not what happened; advisory numbers have no times in the archive listing (the engine reads each file's ADVDATE)",
           "forecast"),
    Source("nhc_gis_best_track", "NHC GIS best track", "analysed positions and intensity every 6 h, track coloured by strength",
           "Atlantic, Pacific", "archive seasons; the current season's working best track while active", "after each analysis",
           "fix times (UTC)", "wind kt", "public domain", "NOAA National Hurricane Center", "zip; cached",
           "the working best track of a current storm is revised after the season; no landfall flags", "best_track"),
    Source("nhc_hurdat2", "NHC HURDAT2", "the final reviewed best track, with landfall (L) records", "Atlantic 1851-, NE Pacific 1949-",
           "up to the previous season (updated each spring)", "yearly", "fix times (UTC)", "wind kt, pressure mb", "public domain",
           "NOAA National Hurricane Center", "one ~6 MB text file per basin; cached", "the current season is not in it yet", "best_track"),
    Source("iem_radar", "IEM NEXRAD composite (N0Q)", "base reflectivity mosaic of NWS radars", "CONUS", "every 5 min since 2010-11-13 "
           "(N0R since 1995)", "5 min", "scan time (UTC)", "dBZ", "public domain (IEM); NOAA/NWS data",
           "Radar: NOAA/NWS NEXRAD via Iowa Environmental Mesonet", "tiles; IEM asks for modest use (cached, few parallel requests)",
           "a mosaic made by IEM, not an official NWS product; since 2022 N0Q is a downscaled N0B", "observed"),
    Source("iem_warnings", "IEM storm-based warnings archive", "NWS warning polygons (tornado, severe thunderstorm, flash flood, "
           "extreme wind ...)", "US", "2002 onward (polygons since 2008)", "as issued", "issue / expire (UTC)", "-", "public domain",
           "National Weather Service via IEM", "GeoJSON per window; cached", "a polygon may be re-issued (one warning, many polygons): "
           "counts use one per event id", "warning"),
    Source("spc_reports", "SPC storm reports", "tornado / wind / hail reports of a convective day", "US",
           "2004 onward (filtered files)", "through the day; filtered next morning", "report time (UTC); the day runs 12 UTC to 11:59 UTC",
           "hail inches, wind mph/kt", "public domain", "NOAA Storm Prediction Center", "one CSV per day; cached",
           "PRELIMINARY reports, not survey results; a report is not one tornado; a morning event (before 12 UTC) belongs to the "
           "previous day's file", "preliminary"),
    Source("nws_dat", "NWS Damage Assessment Toolkit", "tornado tracks surveyed by NWS teams: EF rating, peak wind, path length and "
           "width, start/end times, injuries and fatalities; damage points and EF swaths", "US", "surveys since about 2011",
           "as surveys are entered (days after an event)", "start / end of each track (UTC)", "mph, miles, yards", "public domain",
           "NOAA National Weather Service Damage Assessment Toolkit", "ArcGIS query per envelope and window; cached",
           "PRELIMINARY by the service's own statement; the official record is NCEI Storm Data, months later", "official_record"),
    Source("spc_outlook", "SPC convective outlook", "categorical severe-weather risk areas", "CONUS", "archive by issuance",
           "day 1: 01, 12/13, 1630, 20 UTC", "issue and valid period", "category", "public domain", "NOAA Storm Prediction Center",
           "GeoJSON; cached", "a forecast of risk, not what happened", "forecast"),
    Source("wpc_ero", "WPC excessive rainfall outlook", "risk of rain exceeding flash-flood guidance", "CONUS", "archive by issuance",
           "several times a day", "issue and valid period", "category", "public domain", "NOAA Weather Prediction Center", "KML/zip; cached",
           "a forecast of risk", "forecast"),
    Source("mrms", "NOAA MRMS 24 h radar estimate (IEM archive)", "radar-estimated rainfall, summed day by day", "CONUS",
           "about 2014 onward", "daily (12 UTC endings)", "accumulation period (UTC)", "inches", "public domain",
           "NOAA MRMS via Iowa Environmental Mesonet", "large PNGs, cropped; cached", "an ESTIMATE, not gauge data", "observed"),
    Source("acis", "NOAA RCC-ACIS station data", "daily observed precipitation, temperature, snow; records and ranks", "US stations",
           "each station's period of record", "daily (quality control runs for ~90 days)", "observation day (local)", "inches, °F",
           "public domain", "NOAA Regional Climate Centers (RCC-ACIS)", "JSON; cached", "data under 90 days old is PRELIMINARY; a trace "
           "counts as 0; missing days are never filled", "observed"),
    Source("usgs_iv", "USGS instantaneous values", "river gage height (00065) every 15 min", "USGS gauges", "about 2007 onward "
           "(instantaneous)", "15 min", "observation time (UTC)", "feet", "public domain", "U.S. Geological Survey",
           "JSON; cached", "recent values are PROVISIONAL; gaps around flood peaks happen", "observed"),
    Source("usgs_site", "USGS site service", "gauge names, numbers and positions", "US", "-", "as gauges change", "-", "-",
           "public domain", "U.S. Geological Survey", "RDB text; cached", "a name search can match several gauges on one river",
           "index"),
    Source("nwps", "NWS water prediction service", "flood categories (action/minor/moderate/major) and historic crests of a gauge",
           "NWS forecast points", "current categories; crest history", "as revised", "-", "feet", "public domain",
           "National Weather Service", "JSON; cached", "categories are today's, not the event's", "official_record"),
    Source("gibs_daily", "NASA GIBS daily true / false colour", "one VIIRS / MODIS picture a day", "global", "years (VIIRS 2012-, "
           "MODIS 2000-)", "daily", "acquisition day", "-", "NASA open data", "NASA GIBS", "tiles; cached",
           "clouds can hide the ground; a day, not a moment", "imagery"),
    Source("gibs_geocolor", "NASA GIBS GOES-East GeoColor", "geostationary picture every 10 min", "Americas", "about two months",
           "10 min", "scan time (UTC)", "-", "NOAA/NESDIS via NASA GIBS", "GOES-East GeoColor (NOAA/NESDIS), NASA GIBS",
           "tiles; cached", "older dates are not kept", "imagery"),
    Source("nws_api", "NWS API (api.weather.gov)", "forecasts, observations, active alerts", "US", "current only", "hourly / as issued",
           "updateTime / observation time / alert onset-expires", "°F, %, mph", "public domain", "National Weather Service",
           "needs a contact (User-Agent); cached", "current products only: never for a past event", "forecast"),
]
SOURCES: Dict[str, Source] = {s.id: s for s in _S}

# data_source provider:product -> source id (what a graphic's data comes from)
PRODUCT_SOURCE = {
    ("nhc", "cone"): "nhc_gis_advisory", ("nhc", "track"): "nhc_gis_advisory", ("iem", "radar"): "iem_radar",
    ("iem", "warnings"): "iem_warnings", ("spc", "reports"): "spc_reports", ("spc", "outlook"): "spc_outlook", ("wpc", "ero"): "wpc_ero",
    ("mrms", "total"): "mrms", ("acis", "pcpn_total"): "acis", ("acis", "snow_total"): "acis", ("acis", "record"): "acis", ("usgs", "crest"): "usgs_iv",
    ("gibs", "truecolor_loop"): "gibs_daily", ("gibs", "geocolor_loop"): "gibs_geocolor", ("gibs", "truecolor"): "gibs_daily",
    ("gibs", "falsecolor"): "gibs_daily", ("gibs", "geocolor"): "gibs_geocolor", ("nws", "forecast"): "nws_api", ("nws", "obs"): "nws_api",
    ("nws", "alerts"): "nws_api", ("post", "timeline"): "nhc_hurdat2",
}


def source_of(ds) -> str:
    """The source id of a parsed data_source (weather.sidecar.DataSource); best tracks are their own source."""
    if ds is None:
        return ""
    if (ds.provider, ds.product) == ("nhc", "track") and ds.selector == "best":
        return "nhc_gis_best_track"
    return PRODUCT_SOURCE.get((ds.provider, ds.product), f"{ds.provider}:{ds.product}")
