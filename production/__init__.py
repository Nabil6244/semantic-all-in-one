"""Production orchestration layer: one thin layer ABOVE the existing pipeline, never a second pipeline.

  events     append-only production event log (what actually happened) — the source of Production Analytics
  jobs       the job ledger: one status model for every unit of production work (asset, align, plan, render, ...)
  recovery   failure classification, retry policy and the project recovery scan
  graph      the dependency graph over the existing state (CSV, asset manifest, render cache, editorial plan)
  analytics  production metrics computed from the event log and the existing state files
  map_director  decides WHEN a beat earns a map and WHAT it shows, then hands a prompt to the existing map renderers

The executors stay where they were: AssetManager (and its Flow / stock / YouTube / map providers), video_generator's
renderer, the editorial engine, the graphics engine, pakMap / Hybrid. This package only records, explains, decides
and retries around them.
"""
