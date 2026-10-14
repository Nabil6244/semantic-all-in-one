"""Weather Intelligence: the engine that reads a weather story and produces its data graphics without a hand-made layer file.

    understand.py  what the narration is about (category, storm, dates, times, places, claims, topics per beat)
    context.py     the event resolved against official indexes (storm identity, landfall, moment, convective day, focus)
    identity.py    the official indexes themselves (NHC storm list, advisory archive, HURDAT2, USGS gauges)
    sources.py     what each authoritative source measures, covers and promises
    catalog.py     every graphic the engine can propose: the narration it answers, the evidence it needs, how it is built
    planner.py     opportunity detection and narration-aligned placement (limits per beat, footage beats kept clear)
    evidence.py    the Weather Evidence Model (facts with provenance, every request and its outcome)
    engine.py      the run: understand -> resolve -> plan -> fetch -> verify -> intel/ files (+ entry points for the app and CLI)
    beats.py       beats from the narration when a project has no beat plan
    report.py      the production report ("Added for you", what was left out and why)

The user's files (beats.csv, weather_layers.csv, plan.csv, intel/overrides.json) are only ever read."""
