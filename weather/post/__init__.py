"""Post-Event Report (phase 4): what happened, observed after the fact.

Data (every number from a public archive, with its URL in the numbers report):
  acis.py       NOAA Regional Climate Centers (RCC-ACIS): station rainfall totals, records against the period of record
  usgs.py       USGS Water Services (gage height) and NWS water (flood categories, historic crests): river crests
  mrms.py       NOAA MRMS radar rainfall estimates (24-hour PNG rasters archived by the Iowa Environmental Mesonet): rain maps
  gibs.py       NASA GIBS daily MODIS/VIIRS pictures: before / after
  besttrack.py  NHC HURDAT2 best track: landfall times
  timeline.py   the dated marks of the event timeline, each read from one of the products above
  suggest.py    "a post-event report is ready to make": warnings over, reports in
  fmt.py        dates and numbers as they are shown

The layer types live in weather/layers/ (totals.py, rivers.py, rainmap.py, beforeafter.py, timeline.py); the graphics in
weather-engine/lib/layers/post_*.mjs. Observed data only; values the source marks provisional are labelled so on screen."""
