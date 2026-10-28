# Real phone models (GLB)

Put one `.glb` file per phone here, named by its id in `whatif-engine/data/phones.json`:

| Phone | File name |
|---|---|
| Galaxy S27 Ultra | `galaxy_s27_ultra.glb` |
| Galaxy S25 Ultra | `galaxy_s25_ultra.glb` |
| iPhone 17 Pro | `iphone_17_pro.glb` |
| Pixel 10 Pro | `pixel_10_pro.glb` |

(Every id is listed in `phones.json`.) A trailer for that phone then uses the real model in every shot, with the trailer's lighting,
motion blur and camera moves. No file means the code-built phone is used, as before.

The model can face any way. It is turned upright automatically: longest side = height, the side with the camera bump = back,
camera at the top. If a model still comes out wrong, put a `<same name>.json` beside it:

```json
{ "flip_front": true, "flip_up": true, "screen_mesh": "Screen", "env": 0.8 }
```

- `flip_front`: shows the back where the front should be (or the other way round).
- `flip_up`: upside down.
- `rotate`: `[x, y, z]` in degrees, replaces the automatic turning completely.
- `screen_mesh`: the name of the screen part, so the trailer's lock screen is shown on it. A part named `Screen` or `Display` is found by itself.
- `env`: reflection strength (0.8 default; lower if the metal looks blown out).

Downloaded `.gltf` + `.bin` + textures: convert to a single `.glb` first (Sketchfab offers "glTF Binary (.glb)" directly; otherwise
https://gltf.report or Blender: File > Export > glTF Binary).

## Free models (Sketchfab, CC-BY, downloadable — checked 2026-10-27; re-check the licence badge before downloading)

| Save as | Model | Author |
|---|---|---|
| `galaxy_s25_ultra.glb` (also usable as `galaxy_s27_ultra.glb`) | https://sketchfab.com/3d-models/9cdcd5cff5e9496e88820d306acf4455 | vmmaniac |
| `galaxy_s24_ultra.glb` | https://sketchfab.com/3d-models/c72bf52bc9bb4cdfa033ccba8ef3b140 | betasaur |
| `iphone_17_pro.glb` | https://sketchfab.com/3d-models/4541aa8a28324b33a2baaf81d263aaec | Ranguel |
| `iphone_17_pro_max.glb` | https://sketchfab.com/3d-models/87fc1df741384124a8ce0226d2b2058d | MG990 |
| `iphone_16_pro.glb` | https://sketchfab.com/3d-models/96be8c7e49fa4f949855db3e7f2e64e0 | tranminhluan |
| `pixel_10_pro.glb` (Pixel 9 Pro, low poly) | https://sketchfab.com/3d-models/4533d22cd0d9473ba6a26fa1d20d76da | s12311061 |
| `oneplus_13.glb` (OnePlus 12) | https://sketchfab.com/3d-models/5e2281b99366462188415209beb24dfd | me_blender |

Download needs a free Sketchfab account; pick "glTF Binary (.glb)". No recent Xiaomi or Pixel 10 model was found.

Licence: only CC0 or CC-BY models for monetised videos. CC-BY needs a credit line in the video description
("Phone model by <author>, CC BY 4.0, <link>"). Never CC-BY-NC. Keep the licence note next to the file
(`galaxy_s25_ultra.LICENSE.txt`).
