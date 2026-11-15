# Sky Sim quality spec: matching the competitor (Lightbound)

Measured 2026-11-14 on 97 full-HD frames from 9 Lightbound videos (TON 618, Night Sky Elsewhere, Smallest vs Largest
Star, Sun Replaced by Stars, Planets Replaced the Moon, Sun From Every Planet, Earth With Rings, Sunset on Every Planet,
Miller's Planet). Every render is checked against these numbers by `python -m skysim.tools.quality_check <video|frames>`.

## 1. What their picture is made of

| Look | Where it is used | How it is made (as it reads on screen) |
|---|---|---|
| **Silhouette lake** | Night Sky Elsewhere, Smallest vs Largest, TON 618 (night), Planets Replaced the Moon | A dark mountain ridge as a pure silhouette, a still lake mirroring the sky, a smooth sky gradient. Almost no texture. The sky object is the only bright thing. |
| **Landmark photo + sky object** | Sun Replaced by Stars, Earth With Rings, Planets Replaced the Moon | Real stock photos (New York, London, Paris, Tokyo, Dubai, Sydney, Singapore, Giza, an Iceland aurora) with the sky replaced and the object composited in, lit and reflected in the water. |
| **Space** | Sun From Every Planet, Smallest vs Largest, Miller's Planet | Black, a fine dense star field, one glowing object, dashed scale rings and leader lines. |
| **Simple 3D horizon in thick air** | Sunset on Every Planet, Miller's Planet | Flat sea or cloud deck, a far low ridge, strong haze and colour cast. Very little detail. |
| **Detailed 3D valley** | TON 618 only | Game-engine valley with forest and beach; it is hazy and soft, never crisp. |

Most of their quality comes from **restraint**: dark frames, real blacks, clean skies, haze and silhouettes instead of
texture. The detailed valley is the exception, not the rule.

## 2. The numbers (median, competitor vs our TON 618 v2 test)

| Metric | Competitor | Ours (v2) | Means |
|---|---|---|---|
| Brightness (lum) | **0.24** | 0.36 | ours is milky; theirs is dark |
| Near-black share | **19 %** | 0 % | they keep real blacks (silhouettes, night, space) |
| Sky roughness (top third) | **1.46** | 3.12 | their skies are clean gradients; ours are noisy (render noise, busy ridge) |
| Fine detail | **2.21** | 4.60 | theirs is soft and simple; ours is busy texture |
| Contrast | 0.16 | 0.13 | similar; ours slightly flat |
| Colour strength | 0.24 | 0.26 | similar |

Allowed range per metric (their 20th-80th percentile) lives in `skysim/tools/quality_check.py` `TARGETS`.
A render passes when at most a quarter of its sampled frames fall outside any range.

## 3. Rules for our renders (from the above)

1. **Dark first.** Night and dusk frames sit at 0.06-0.25 brightness; keep silhouettes truly black (exposure, not haze, lifts nothing in the shadows).
2. **Clean sky.** The sky is a smooth physical gradient (dark zenith, lighter horizon, warm or cold cast by the light source). No visible noise: enough samples plus denoise on the sky, no busy ridge detail against it.
3. **Simple ground.** Prefer silhouette or hazy forms over texture. Detail only where the camera is close, and soft.
4. **Haze carries depth.** Far ridges fade toward the sky colour; this is what makes theirs read as real.
5. **One bright thing.** The sky object is the brightest element and glows softly (bloom), its reflection in the water too.
6. **Real places by default.** Silhouette ridges from real elevation data (skysim/tools/fetch_terrain.py); landmark looks from a once-sourced photo library with sky masks (docs/skysim/PLAN.md 3.3).
7. **Text stays as it is.** Thin light caps for big values, small tracked labels, small centred subtitles: our sk_* layers already match.

## 4. Build order to match

1. Silhouette-lake look (the most used): real-DEM ridge silhouette + mirror lake + physical sky gradient, in Blender or 2D (cheap, clean).
2. Sky gradient + glow pass shared by every look (fixes sky roughness and brightness everywhere).
3. Landmark photo library (CC0/free-licence photos, sky masks made once) + compositing of the sky object and its reflection.
4. Detailed valley (TON 618-type stories): darker grade, more haze, softer ground, denoised; checked with quality_check before showing.
