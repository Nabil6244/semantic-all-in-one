# pakmap (Python): script CSV + narration -> render spec

    python3 -m pakmap words narration.txt --out words.json        # estimated timing, before the voiceover exists
    python3 -m pakmap check   script.csv --words words.json       # the plan report only
    python3 -m pakmap compile script.csv --words words.json --out spec.json --watermark "My Channel"
    node pakmap-engine/render.mjs spec.json                       # render (after filling in output and cache_dir)

Modules: `schema` (CSV reading, every problem names its row), `anchor` (finding phrases in the Whisper word list), `geo` (names -> places, cities, camera framing), `compile` (the compiler and the plan report), `words` (loading and estimating word lists). Author guide: `docs/pakmap/csv-reference.md`. Tests: `python3 -m pytest test_pakmap_*.py`.
