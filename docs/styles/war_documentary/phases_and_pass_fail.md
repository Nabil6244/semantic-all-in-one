# Prioritized phases with pass/fail criteria

Numbers come from the measurements in `performance_plan_bounded_memory.md`; gates marked [proposal] are mine and open to change. No phase starts without your approval; nothing is committed or pushed.

| Phase | Work | Pass criteria (all required) | Fail means |
|---|---|---|---|
| **0 Approval (now)** | review this folder; answer the open decisions | you approve scope, fonts, sources, front-line policy | no implementation |
| **1 Foundations** | `segments.py` renderer; `war_documentary/schema.py`, `registry.py`, `policy.py`; fixtures | peak ffmpeg memory ≤ 1.0 GB at 25 s, 3 min and 10 min (measured 0.59–0.62 GB); ≥ 2.0x real time (measured about 3.5x); segment joins frame-exact, audio offset 0 frames on a real voiceover; ≥ 95 % segment cache reuse on a repeat render; policy refuses every planted violation (fabricated position, unlabelled illustration, unverified portrait, recycled clip); all existing-style tests unchanged | memory or sync gate missed → fix before anything else |
| **2 Treatments** | map reveal, portrait+statement, stat/compare, equipment card, evidence highlight, trajectory (illustrative), chapter, recap | each renders deterministically, stays in frame, fades in/out, has a failure fallback; frame review against reference grammar; claimant chip on contested figures; ILLUSTRATIVE label present on every trajectory | any treatment can show unsourced facts or is non-deterministic |
| **3 Planner** | narration-to-visual rules, density limits, arbitration, report | on a real script: card share 25–35 % [proposal], clean footage ≥ 55 % [proposal], no two cards at once, no map/portrait from a bare name or country, "no visual" chosen where nothing is justified, every shown claim has provenance, decision log complete | a fabricated or mismatched visual reaches the render list |
| **4 Integration** | one `app.py` hook (additions only), settings, style switch | selecting and deselecting the style leaves every other style's output unchanged (frame hashes); repeated exports identical; pack off by default; packaged app unaffected | any existing-style change |
| **5 Demonstration and acceptance** | the sequence in `demonstration_sequence.md` | weighted scorecard ≥ 4.0, no category < 3, all hard gates in the scorecard, your visual sign-off | below threshold → list of defects, no release |

## Order and critical path
1 → 2 → 3 → 4 → 5. Phase 1 first because the memory defect and the provenance gate are prerequisites for everything. Phases 2 and 3 can partly overlap once Phase 1 passes.

## Open decisions that gate phases (full lists are at the end of each agent document)
- Gate Phase 1: segmented renderer replaces the single-graph one (not bit-identical to the Phase 1 demo; mean difference 46.4 dB, worst frame 38.4 dB, not isolated); registry location; new test files only.
- Gate Phase 2: fonts; equipment photo and diagram sources; satellite base map; front-line source; trajectory graphics allowed or pins only.
- Gate Phase 3: portrait source and rights rule; contested-figure policy; card-share target; real script and voiceover for the sync gate.
- Gate Phase 4: the single `app.py` hook and namespaced settings.
