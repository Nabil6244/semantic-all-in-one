"""Weather News (phase 3): the data behind radar loops, hurricane tracks and cones, SPC/WPC outlooks, archived warnings,
storm reports and counters (weather/layers/radar.py, storms.py, severe.py, counters.py), and the event footage pool
(public-domain and Creative Commons clips, approved per clip before a video may use them).

Each source has its own small parser here, tested on recorded real answers in weather/testdata/news/:
    shapefile.py        zipped ESRI shapefiles (NHC, WPC archives), standard library only
    radar_providers.py  radar tile providers (IEM default, NOAA map services live only, none) and loop frame picking
    nhc.py              NHC advisory cone / forecast track / coastal watches and warnings, and the best track
    spc.py              SPC categorical outlooks and storm reports (preliminary)
    wpc.py              WPC excessive rainfall outlooks
    iem_warnings.py     storm-based warnings archive (IEM)
    timeline.py         event time (UTC) -> narration time inside a layer's window; UTC windows; places -> time zone
    sources.py, footage_pool.py, approval.py   event footage: search, relevance and licence rules, approval and hand-off"""
