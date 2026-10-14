Recorded official answers for the Weather Intelligence tests (test_weather_intel.py; no network in tests).
Fetched 2026-10-14 (UTC) by running the engine on copies of the test projects; index.json maps each URL to its file.
NOAA / NWS / NHC / SPC / WPC / IEM data are public domain (IEM asks for attribution, which Weather gives).

  storm_list_subset.txt   https://ftp.nhc.noaa.gov/atcf/index/storm_list.txt, TRIMMED to the lines of IAN, HARVEY, ISAIAS,
                          ARTHUR, BERTHA, INVEST, GENESIS024 in a few seasons (the full list is 288 kB)
  hurdat_index.html       https://www.nhc.noaa.gov/data/hurdat/ (folder listing)
  hurdat2_al092022_only.txt  the newest HURDAT2 file named there, TRIMMED to Ian's block (the full file is 7 MB)
  ian_advisory_index_al09_2022.html  NHC GIS advisory archive listing of AL092022
  al092022_5day_*.zip     the advisories the advisory search opened (their ADVDATE gives the issue time)
  ian_radar_list_*.json, ian_warnings_*.geojson, ian_wpc_ero_*.zip   IEM radar scan list, IEM storm-based warnings, WPC ERO
  tornado_*               the October 11, 2026 Newberry County, SC tornado: IEM radar scan list and SC warnings 08-13 UTC
  tornado_*_0955_1025*    the same, for the radar loop fitted to the warning (09:55-10:25 UTC)
  spc_261010_rpts_filtered.csv  SPC storm reports of the convective day 2026-10-10 (12 UTC Oct 10 to 12 UTC Oct 11), which
                          holds the 1005 UTC Newberry report
  al092026_best_track.zip NHC working best track of Isaias (AL092026), fetched 2026-10-14 while the storm is listed as active
  dat_tracks_sc_*         NWS Damage Assessment Toolkit tornado tracks (layer 1) in SC's envelope, Oct 10 12Z - Oct 12 12Z 2026
  tornado_warnings_1011T0905_1011T1105_SC.geojson  IEM warnings an hour either side of the Newberry touchdown (coverage check)
