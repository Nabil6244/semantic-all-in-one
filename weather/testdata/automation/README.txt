Recorded data for the phase-2 (forecast automation) tests. Real answers from api.weather.gov and NASA GIBS (public domain);
tests pass their own "now", so these never go stale. Fetched with the placeholder contact https://example.invalid.
  coverage_20261012.json     weather.automation.fetch.fetch_coverage() snapshot of the 20 metros + national alerts, 2026-10-12 22:46 UTC
  prep_recording.json.gz     every NWS and GIBS answer of one real prep (gzip JSON: {"now", "responses": {url: [status, body]}})
