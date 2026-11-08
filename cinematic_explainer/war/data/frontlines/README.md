# Front-line snapshots (War Documentary)

This folder ships **empty on purpose**. The app never invents a front line; a line is drawn only from a snapshot file that names its
source, licence and date. With no snapshot, maps stay exactly as before (places, routes, "ILLUSTRATIVE MAP" badge).

Add snapshots you are entitled to use here, or in the per-user folder `<War registry folder>/frontlines/` (preferred: survives updates).

Convert a GeoJSON export:

```python
from cinematic_explainer.war import frontline as FL
FL.import_geojson("export.geojson", "<folder>", as_of="2024-03-12",
                  source="Institute for the Study of War and AEI's Critical Threats Project",
                  licence="<the terms you have, e.g. permission email of 2026-11-10>",
                  source_url="https://understandingwar.org/...", status="assessed", side="russia")
```

Required: `as_of` (the date the assessment describes), `source`, `licence`, at least one area. Claimed or disputed areas
(`status`: claimed / disputed) are hatched with a dashed edge. See docs/war/FRONTLINE_PLAN.md for which sources are suitable.
