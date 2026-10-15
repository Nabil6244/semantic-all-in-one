"""News Doc — a footage-first editing option for Weather, built from its reference video (docs/weather/news_footage_plan.md §5b).

Reference: a 19-minute coastal-storm news documentary (~/Downloads/videoplayback (6).mp4), measured frame by frame
(docs/weather/news_doc_ref_every10s_*.jpg): ~83 % footage (local TV news runs with the station's own lower third, drone and
b-roll), ~16 % full-screen graphics on dark navy / black, a few map shots. Hard cuts, a 0.3 s fade into full-screen graphics, a
glitch + white/cyan flash where a new part starts; place tags, yellow tags, big numbers, keyword / quote cards with red boxes,
checklists, side panels and navy charts.

News Doc has its own code for every look and edit decision (this package): nothing here restyles a Weather or Weather Teamplate
piece. Shared with the other styles is only the plumbing — reading the story and finding the storm data (weather.intel), fetching
clips (providers.youtube, the stock providers), and the renderer that draws footage and map frames (hybrid / weather-engine).
Map shots (the satellite map with the event's data) are at most MAP_SHARE of the video.

Entry point: weather.newsdoc.generate.generate_newsdoc_video."""

KEY = "newsdoc"
NAME = "News Doc"
MAP_SHARE = 0.25   # raised from 0.10 (owner, 2026-10-15): Weather's map graphics are adopted into News Doc's map shots
