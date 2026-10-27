# Health Cinema 3D: architecture benchmark and landscape proof (updated 2026-10-27)

Format: **16:9 landscape only.** Default export 1920x1080 @ 24 fps; preview 1280x720. The CLI refuses non-16:9 sizes (tested).
Machine: Apple M2, 16 GB. Blender 4.5.15 LTS (official dmg, sha256 verified). Model: Z-Anatomy `Startup.blend`.

## Decision
Three.js (Chromium/Metal) is the default renderer; Blender is an optional offline asset-prep and premium-render backend (not updated for the
new look; the benchmark below for Blender is from the first comparison). Both read the same asset and the same per-frame samples
(`health_cinema/journey.py`).

## Asset (measured)
Source: 7,183 objects, 3.66 M polygons, 307 MB. Heart split into 4 chambers, valves and papillary muscles; great vessels/coronaries are curves;
lungs, ribs, sternum, diaphragm separate. **No skin mesh and no real face**: the body shell is derived (voxel remesh of the muscle union) and its
head is replaced by a smooth faceless head blank. Neither is real anatomy; both are labelled derived. Lean chest asset ~570 k polygons, 8 layers
(`Layer_Skin/Muscle/Skeleton/Lungs/Vessels/Heart/HeartInner/HeartCut`), `chest.glb` ~27 MB. Heart cut-away = chambers bisected on a coronal plane,
caps removed, valves and papillary muscles in their own layer, chamber wall rendered double-sided. Vessels farther than 0.30 m from the heart and
the carotid/subclavian branches are trimmed. Prep is a 7 min one-off (Blender, 2 GB RAM).

## Renderer comparison (first benchmark, unchanged)
| | Three.js (Metal) | Blender EEVEE | Blender Cycles (CPU) |
|---|---|---|---|
| 960x540, 14 s clip | 4.3 s | 1,428 s | ~8.4 s/frame (1 frame, 128 spp) |
| Memory | node ~324 MB (+ Chromium, not measured) | 1.8 GB | 1.0 GB |

## Landscape proof, current implementation (measured, 336 frames, 14 s)
| | 1920x1080 | 1280x720 |
|---|---|---|
| Full pipeline (render + labels + encode), cold | 25 s | 12 s |
| Cached repeat | 0 s (cache hit) | 0 s |
| Decoded frames / blank frames | 336 / 0 | 336 / 0 |
| Largest isolated pop (frame vs neighbours) | 2.5x (first benchmark 9.8x) | 2.5x |
| Peak RSS of the Python driver run | ~760 MB (cold 1080p, incl. ffmpeg child accounting) | n/m |
Peak memory for Chromium/GPU was not measured separately.

## Defects: before and after
| Defect | Before | After |
|---|---|---|
| Glow | weak halo, white sparkles | silhouette-following fresnel rim on the active layer + restrained bloom (muscle chest, heart, cut heart, vessels, x-ray rim on skin); specular sparkles reduced (roughness floor) but a few small white glints remain at vessel tops |
| Chest highlight | flat blue disc | the real chest-wall muscles (pectorals, serratus, intercostals, diaphragm) glow red through a translucent body, then the skin fades |
| Face artefact | dark hole | faceless head blank (explicit stand-in) |
| Framing | heart low, vessels clipped | heart centred; close-up offsets tuned; vessel tops/bottom still cut in the tightest close-up (by design) |
| Camera | stop/start at keys, rushing zoom | PCHIP + log-distance, no spirals (az within +/-14 deg), final push to the left ventricle |
| Layer sorting | milky stacked lungs/muscle, pops | per-layer depth pre-pass, inner-first order, staged reveals |
| Cut-away | solid ball | open chamber: valve leaflets, papillary muscles, chordae-like structures visible |
| Labels | 20 px at 540p | 40 px at 1080p, short-side scaling, 26 px floor, clamped to a 3% safe margin, gated by layer visibility |

## Remaining limitations
- Skin ghost looks dark/charcoal for ~1 s during its fade before the x-ray rim takes over; layered fades at the lung/skeleton hand-off are the
  least refined moment.
- The label-presence detector in `validate_video.py` is unreliable (reports ~58 false mismatches); labels were judged by eye on decoded frames.
- Temporal checks are frame-difference statistics plus visual review of ~100 decoded frames, not a frame-by-frame review.
- The Blender path was not updated for the new look; Windows and macOS packaging not tested; GPU use confirmed only as ANGLE/Metal on this Mac.
- Heart colours (blue right, red left) are a stylised convention, not model data. No blood-flow or disease animation exists.

## Cache and failure behaviour (tested, 28 tests)
Key = spec + anchors + model hash + size/fps + settings + code hash (sampler, overlay, page, render script). A hit skips rendering; a change to any
of those misses (unit-tested). Cancel, timeout, failed or incomplete renders leave no cache entry or temp folder (tested with fakes and real child
processes). A cancel during the real Chromium render was not exercised end to end.

## Licensing and deployment blockers
Z-Anatomy is CC BY-SA 4.0 over BodyParts3D (CC BY-SA 2.1 JP); inner-ear (CC BY-NC-SA) and kidney (CC BY-NC) components must be excluded. The
derived shell, head blank, GLB and renders are CC BY-SA derivatives. They stay local until a licence review clears commercial distribution and
the share-alike effect on a bundled model. Blender stays optional and unbundled; the app must fall back to Three.js (or non-3D scenes) without it.

## Final visual gate (2026-10-27)
- The 2.5x one-frame change was at t = 5.5 s: an **unintended pop**. The lungs' depth pre-pass switched on at ~1% opacity and instantly hid the back
  ribs/muscle behind them. Fixed: a layer below 50% opacity draws without its pre-pass; outer layers (skin, muscle, skeleton) always keep it.
  That first fix briefly created a pop of 10.8x at 2.6 s (skin pre-pass dropping out at 50% opacity), fixed by the always-on outer layers.
  Largest isolated pop now 1.6x (t = 5.75 s, the skeleton-to-lungs hand-off, an intended reveal).
- Skin fade: the charcoal look is replaced by a luminous pale-blue glass X-ray rim that lasts until the skin is gone; the last half second still reads
  as a smoky translucent body.
- Full 1920x1080 / 24 fps journey: 26.4 s cold (rendering + labels + encode), 0 s cached.

## Health Cinema foundation (this phase)
Opt-in "Health Cinema" style, `health_cinema/` package, 16:9 only (Final 1920x1080, Preview 1280x720, 24 fps; portrait sizes are rejected).
- Profiles (`profiles.py`): Medical Cinema, Human Story Documentary, Future Science, Anatomy Explainer, Health Investigative: weights, accent/glow, reading
  time, evidence label, motion, type scale. They configure one engine.
- Planner (`planner.py`) + evidence guard (`evidence.py`): sentence-aligned scenes; sourced statistics become stat cards, claims/studies become evidence cards,
  heart/lungs use the 3D journey when the local asset exists, other organs are flagged `no_anatomy_asset:<organ>` and shown as text, never faked.
- Clips (`clips.py`, `cards.py`) + engine (`engine.py`): per-scene cached clips, 3D via the Three.js renderer with automatic text-card fallback, footage
  trim/crop, concat + voiceover mux, report JSON with review flags and credits. Own compositor: War Documentary's renderer is fixed at 1280x720 @ 25 fps.
- App (`app_section.py`, `packaging.py`): additive hooks in app.py (about 57 added lines, 3 one-line extensions of existing lines).
Measured on the 27 s test narration (6 sentences, 4 scenes, one 13.6 s 3D heart journey): 720p preview 13.2 s cold / 0.4 s cached; 1080p 26.8 s cold.

## Cinematic pass: real footage, brain/eye 3D, data graphics, captions (2026-10-27)
Reuses the app's own machinery: `VisualDirector` (Gemini, with the app's deterministic fallback) for scene grouping and queries, and the app's
`_build_asset_manager` / `AssetManager` (Pexels, Pixabay, Openverse; YouTube and Flow only if their checkboxes are ticked) writing its manifest in
`<project>/state/health_cinema/assets`. Flow (credits) is never requested without the explicit checkbox; YouTube likewise.
New: `direction.py`, `acquire.py`, `graphics.py` (counter, percentage bar, timeline, captions), brain/eye templates over `head.glb`
(skull, neo-cortex gyri, cerebellum, brainstem, carotid/vertebral/basilar/cerebral arteries, eyeballs with cornea/lens/retina/optic nerves; all
Z-Anatomy, local only). Not modelled: eye interior cut-away, a complete circle of Willis (no anterior communicating artery in the source), any blockage.
Test render: 76.1 s stroke script, 12 scenes (counter, bar, 6 stock clips, brain+carotids 3D, eye 3D, timeline, closing text card). Measured:
1920x1080 @ 24, 1826 frames, audio 76.083 s vs video 76.083 s; cold (clips and 3D) 107 s, unchanged rerun 1.9 s; preview cold 91.8 s.
Narration: macOS "Samantha" TTS (the original recording was not found); captions are phrase-level estimates within each sentence.
