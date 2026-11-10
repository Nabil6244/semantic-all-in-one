# iPhone Duo animated model: verification report (Phase 2C.2, 2026-11-06)

Models: `iphone_duo_fold_star_white.glb`, `iphone_duo_fold_night_sky.glb` (extraakash, Sketchfab; git-ignored). The models were **not modified**.
Official reference used: Apple's iPhone Duo Tech Specs page, https://www.apple.com/iphone-duo/specs/ (read as text and viewed in the in-app browser;
nothing saved), Apple's iPhone Duo product page https://www.apple.com/iphone-duo/ (image alt texts and one screenshot), and Apple's Newsroom
press release of Sept 9, 2026. My stills of the model are in the session scratchpad (earlier phase), not in the project.

Limits of this check: the official rear-view picture on the specs page renders small (about 250 px wide); the larger rear-view images on the product
page are lazy-loaded scroll animations I could not capture. Apple's own alt text was used for the details the small picture cannot show.

## Result by item

| Item | Apple (official) | Model | Verdict |
|---|---|---|---|
| Open size | 164.6 x 117.8 x 5.2 mm (1.397:1) | about 166 x 118 mm (1.41:1) | **Matches** (within ~1%) |
| Closed size | 84.1 x 117.8 x 11.3 mm (0.714:1, portrait) | about 83 x 118 mm (0.70:1) | **Matches** width and height. Thickness not measured |
| Closed orientation | Portrait. Product page screenshot: portrait slab with a punch-hole top right; Apple press release: "similar in size to a passport" | portrait when closed | **Matches** |
| Fold motion | Book-style, hinge in the middle | `open-close` animation: open at t=0, near-closed at t=1.5 s | **Plausible, not compared frame-by-frame**; engine cannot play it yet |
| Rear cameras: count | Two lenses (Apple alt text: "48MP Dual Fusion rear cameras in top corner, two lenses, microphone, flash"; specs: 48MP Fusion Main + 48MP Fusion Ultra Wide) | two lenses in one module | **Matches** (your decision confirmed by Apple) |
| Rear cameras: arrangement | Specs-page picture, closed phone seen from the back: two round lenses **side by side horizontally** in the top corner | near-closed pose: two lenses side by side in a horizontal pill. Open pose: two lenses **stacked vertically** in a pill at the edge of the panel | **UNRESOLVED**: the horizontal pair matches in the near-closed pose; whether the vertical pair in the open pose is only a rotation or a different layout cannot be settled from the small picture |
| Module shape | Specs picture: Night Sky has a raised dark module; Star White module reads flatter. Exact outline not legible at this size | a raised, pill-shaped module | **UNRESOLVED** (outline, height) |
| Flash | Apple says a flash exists (alt text; specs list True Tone flash). Its position is not legible in the small picture | small sensor dots next to the lenses; which one is the flash is not identifiable | **UNRESOLVED** |
| Microphone / sensors | alt text: microphone | not identified | **UNRESOLVED** |
| Front camera | punch-hole in the right-hand corner of the outer display (product page); 12MP Center Stage | punch-hole top right on the outer screen | **Matches** |
| Materials | Titanium frame, Ceramic Shield 2 front, Ceramic Shield back; Night Sky and Star White | titanium-like frame; the Star White back rendered **dark** in my earlier lighting (Apple's is white) | **UNRESOLVED**: could be my lighting or the material; the Night Sky look matches Apple's |
| Apple logo | centred on the back panel | present | Matches |
| Hinge | Not visible in Apple's rear view; Apple press release: precision hinge | hinge line present | Not verifiable from the sources used |

## Other models
- `iphone_duo.glb` (Pikkme): a multi-device showcase scene; not a single phone; not compared.
- `iphone_duo_nc.glb` (zhe_kan): non-commercial licence; not compared; barred from a monetised film.

## What this means
- **Safe to state:** proportions (open and closed), portrait closed orientation, two rear cameras, punch-hole front camera.
- **Not safe to state as final:** lens arrangement in each pose, module shape and height, flash and microphone position, Star White back colour, thickness.
- **`DESIGN.md`:** updated in Phase 2C.3: open about 1.40:1 landscape, closed about 0.71:1 portrait (Apple's published dimensions). Camera geometry,
  flash position and materials remain UNRESOLVED there too.
- **To close the camera questions:** a larger official rear-view image (the product page's "back exterior" animation frames, or an
  Apple Newsroom press image of the back), compared against stills of each model's back at the closed pose. Both need a decision on Apple image use
  (see the register): viewing is fine, saving or publishing them is not cleared.

## Model licence (verified this phase)
- Model page text (Star White): "Non-official, fan-made visualization. Perfect for: Product animations, 3D product showcases, Motion graphics, VFX and
  visualization project. **License: Free Standard** ... **NoAI**: may not be used in datasets for, in the development of, or as inputs to generative AI programs."
  Published Sept 12, 2026. The Night Sky page lists the same licence.
- Sketchfab's license agreement (https://sketchfab.com/licenses): "Editorial" licences bar commercial or promotional use; "Standard" licences do not carry that
  restriction but forbid distributing the asset as a standalone file, sublicensing or selling it, and any use that violates third-party IP (copyrights,
  trademarks, rights of publicity). The agreement says the asset is not warranted to be accurate.
- **Unresolved:** I did not locate the page for the **free** Standard licence itself ("Learn more" link) or any sentence that says "monetised video allowed".
  The agreement I read governs *purchased* licences. The earlier `LICENSE.txt` note ("use in videos is allowed, no credit needed") is the earlier
  summary, not a quotation I could confirm. Also open: a fan-made model of Apple's product design still sits under Apple's trademark and design rights
  (the Sketchfab terms say the licensee may not violate them). Status: **licence label verified, monetised use NOT verified**.

## Phase 2C.3: rear-camera mismatch, stated plainly (2026-11-06)

**Apple's rear-camera image vs the animated model: they do not demonstrably match.**
- Apple (specs-page rear view, closed phone, Night Sky and Star White): two round lenses placed **side by side horizontally** in a top corner of the back;
  Apple's alt text adds a microphone and a flash in the same area. The Night Sky module is a raised dark block; the Star White module looks flatter.
- Model, near-closed pose (t = 1.5 s): two lenses side by side in a wide, raised **pill** with sensor dots to the right. This pose resembles Apple's pair.
- Model, open pose (t = 0): the module is a **vertical** pill with the two lenses **stacked**, at the edge of the back panel. In Apple's picture the pair is
  horizontal when the closed phone stands portrait. Whether the model's vertical pair is just that horizontal pair seen with the half rotated, or a
  different layout, **is not established**; the check needs the same pose and viewpoint in a larger official image.
- Module outline and height: Apple's picture is too small to show them; the model's pill is pronounced. **Unresolved.**
- Flash and microphone: Apple says both exist; the model has small dots whose roles are unknown. **Unresolved.**
- Star White back: white in Apple's picture, dark in my render of the model. **Unresolved** (lighting or material).

Status: dimensions and orientation are matched; **camera module, flash and materials are unresolved discrepancies**. The model stays a labelled illustrative
asset, is **not integrated into any pipeline**, and nothing in this report changes it.
