"""Weather: US weather videos (Forecast first; Weather News and Post-Event later) from free government data.

A Weather video is a Hybrid Map video with weather layers on it. The plan is an ordinary Hybrid beat CSV (beats.csv, read by
hybrid.beat_csv unchanged) plus Weather's own sidecar (weather_layers.csv, read by weather.sidecar): the weather layers never enter
the Hybrid or pakMap CSV contracts. The data comes from the National Weather Service (weather.nws) through a cache
(weather.cache); every number keeps where it came from (weather.provenance). Rendering goes through Hybrid's generator with
Weather's own renderer (weather.render -> weather-engine/), passed in through the generator's existing `render=` option.

Nothing here is imported when the app starts; Weather is off unless it is switched on (docs/weather/phase1_proposal.md)."""
