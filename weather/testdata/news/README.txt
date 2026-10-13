Recorded responses for the Weather News tests (phase 3; no network in tests). Fetched 2026-10-12/13 (UTC). NOAA/NWS (NHC, SPC,
WPC), NASA and IEM data are public domain.
  al092022_5day_030.zip                 https://www.nhc.noaa.gov/gis/forecast/archive/al092022_5day_030.zip (Hurricane Ian, advisory 30)
  al092022_best_track_pts_lin.zip       https://www.nhc.noaa.gov/gis/best_track/al092022_best_track.zip, trimmed to the pts and lin
                                        layers (the radii/windswath layers and .xml metadata dropped to keep the repo small)
  sbw_ian_fl.geojson                    https://mesonet.agron.iastate.edu/geojson/sbw.geojson?sts=2022-09-28T12:00:00Z&ets=2022-09-29T00:00:00Z&states=FL
  iem_radar_list_ian.json               https://mesonet.agron.iastate.edu/json/radar?operation=list&product=N0Q&radar=USCOMP&start=2022-09-28T14:00Z&end=2022-09-28T22:01Z
  iem_n0q_latest.json                   https://mesonet.agron.iastate.edu/data/gis/images/4326/USCOMP/n0q_0.json
  iem_radar_list_latest.json            the json/radar list for the two hours before that latest scan
  spc_day1otlk_20240506_1630_cat.geojson https://www.spc.noaa.gov/products/outlook/archive/2024/day1otlk_20240506_1630_cat.nolyr.geojson
  spc_day1otlk_latest.geojson           https://www.spc.noaa.gov/products/outlook/day1otlk_cat.nolyr.geojson
  spc_240506_rpts_filtered.csv          https://www.spc.noaa.gov/climo/reports/240506_rpts_filtered.csv
  ero_94e_2022092809.zip                https://www.wpc.ncep.noaa.gov/archives/ero/20220928/shp_94e_2022092809.zip
  wpc_ero_day1_latest.geojson           https://www.wpc.ncep.noaa.gov/exper/eromap/geojson/Day1_Latest.geojson
  nasa_ian.json                         https://images-api.nasa.gov/search?q=hurricane%20ian&media_type=video&year_start=2022&year_end=2022
HAND-MADE (not recorded), in the documented shape of the real answers:
  commons_search_SYNTHETIC.json         MediaWiki API generator=search + imageinfo/extmetadata. commons.wikimedia.org cannot be
                                        reached from the build machine (and is not on the contract's download list), so the licence
                                        rules are tested on this hand-written answer; the files and authors in it are invented.
  youtube_info_SYNTHETIC.json           the yt-dlp info fields Weather reads (title, channel, upload_date, license); no YouTube
                                        request is ever made in tests. Video ids are placeholders.
