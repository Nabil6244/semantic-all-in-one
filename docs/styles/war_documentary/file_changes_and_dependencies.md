# Exact proposed file changes and dependencies

Everything is additive. Existing styles, `render_cache.py`, `video_generator.py`, `scene_graph/` and Doc Style files are not edited. A protected-manifest check (`test_fixtures/*_protected.json`) precedes any edit to `app.py`.

## New files (proposed, none created yet except the Phase 1 ones)

| Path | Purpose | Phase |
|---|---|---|
| `cinematic_explainer/` (exists) | Phase 1 cards, tokens, prototype renderer; kept as is | done |
| `cinematic_explainer/segments.py` | per-shot segment render (bounded memory), uses the existing `RenderCache` class with a new key function (includes portrait content hash) | 1 |
| `war_documentary/` (new package) | the war style, separate from the general pack | |
| `war_documentary/registry.py` | per-user JSON asset/provenance registry (no database), one record per `war_asset_id` | 1 |
| `war_documentary/schema.py` | metadata schema and verification states (see taxonomy) | 1 |
| `war_documentary/policy.py` | gates: provenance, dates, licence, recycled/disputed/mismatch flags, "never fabricate" refusals | 1 |
| `war_documentary/planner.py` | narration-to-visual rules, density limits, arbitration, "no visual" outcome, decision log | 3 |
| `war_documentary/treatments/` | map reveal, equipment card, portrait+statement, stat/compare, evidence highlight, trajectory (illustrative), chapter, recap | 2 |
| `war_documentary/report.py` | plan report: decisions, flags, provenance table, review list | 3 |
| `test_war_documentary_*.py` | unit, planner, policy, segment, isolation tests | each phase |
| `test_fixtures/war_documentary/` | invented fixture sentences, tiny placeholder media, golden frame hashes for the segmented renderer | 1 |
| `docs/styles/war_documentary/` | this design set | now |

## Existing files that would change (each needs your approval when reached)
| File | Change | Phase |
|---|---|---|
| `app.py` | additions only: one setting `cinematic_explainer.*` (off by default), one entry in the existing style/look selector, one call into `war_documentary` in the plan step; protected-manifest check first | 4 |

No other existing file.

## Dependencies
| Item | Needed? | Why / decision |
|---|---|---|
| New Python packages | **No** | PIL, ffmpeg already used |
| Fonts: condensed face + bold news serif (Oswald, Source Serif 4, OFL) | **Your decision** | the references use them; current bundled fonts only approximate |
| Satellite/base map provider | **Your decision** | none assumed; dark and natural styles exist |
| Front-line data | **Your decision** | only from a published, reusable, dated source you name; otherwise no drawn front line |
| Portrait / equipment photo sources | **Your decision** | licensed lookup cached once, or supplied by you |
| Database migration | **No** | provenance lives in a per-user JSON registry; the scene manifest gets one key `war_asset_id` |
| External service | **No new one** | any lookup uses existing providers |
