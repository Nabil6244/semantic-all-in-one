# Health Cinema visual sources: stage 1 audit and fixes (2026-10-28)

## Findings
1. **3D models were never found by the app.** `assets.asset_dir()` defaulted to `~/.semantic_yt_studio/health_cinema/assets`, which does not exist. The prepped
   models (`chest.glb`, `head.glb` + anchors) live in `~/HealthCinemaTools/bench/`. Only the tests set `HEALTH_CINEMA_ASSET_DIR`, so in the real app
   `template_ready()` was False for all four journeys (heart, chest, brain, eye) and every anatomy scene became a text card, silently.
   Replay of the stroke script through the real engine: 6 of 15 scenes were text cards (all 5 brain/eye scenes + the close).
2. The directed planner's last resort was a text card whenever the director's asset type was not a stock/YouTube type (`video`, `image`, ...), i.e. exactly
   the scenes that wanted a 3D/anatomy visual. A failed footage search went straight to a card; no retry.
3. The app's own visual QA (`visual_qa` in the manifest) already scored mismatched clips low, but Health Cinema ignored it.
4. Timeline card: the heading overlapped upper event labels.
5. Only 4 journeys exist (heart, chest, brain, eye) built on 2 models (chest, head). Everything else (knee, liver, kidney, pancreas, gut, cells, disease) has no 3D.

## Fixed in stage 1
- `assets.py`: searches the per-user folder, then the local model library; env var stays authoritative; `anatomy_status()` for the report.
- `engine.py`: logs loudly when 3D is unavailable; report gets `anatomy` and `kind_counts`; failed footage -> `_retry_footage` (Gemini visual direction asks for
  other queries, 2 rounds, never repeats a tried query, last round may use YouTube when ticked); visual-QA weak match -> retry, else a review flag; card only as last resort.
- `planner.py`: anatomy topic or generated-type scene with no 3D model -> footage searched with the organ named (`osteoarthritis` added to joints).
- `acquire.py`: the planner's own short query is what gets searched; QA result carried back; `is_weak()`.
- `graphics.py`: timeline heading no longer overlaps labels (long labels end with an ellipsis).
- Tests: `test_health_cinema_visual_sources.py` (10 tests).

## Licences (from the records in the repo and the model folder)
- Z-Anatomy `License.txt`: CC BY-SA 4.0 over BodyParts3D (CC BY-SA 2.1 JP). Commercial use, redistribution and derivatives are allowed with attribution and
  share-alike on the *model derivative*. Videos with the credit line in `engine.CREDIT_Z` satisfy attribution.
- Excluded components (same file): inner ear (CC BY-NC-SA 4.0) and **kidney (CC BY-NC 4.0, Lissie Cowley)**: not usable commercially. The chest and head
  GLBs were prepared from other structures; the kidney is the one organ that needs a different source.
- The "do not distribute until licence review" wording is the project's own caution in `3d_architecture_benchmark.md` / `packaging.py` (the open question is
  share-alike scope for a *bundled* GLB, not whether commercial use is allowed). Nothing in the records forbids commercial use of rendered videos.

# Stage 2 (2026-10-29): relevance, CSV direction, 3D library

## Stock relevance (`health_cinema/relevance.py`)
Stock search returned heart/brain/coronavirus clips for "knee cartilage" and the app's QA passed them (metadata-only QA). Now each clip is judged by its own page title
(Pexels slug) or its Pixabay tags (one API call with the user's key): for a scene about a named body part the title/tags must name that part (generic words such as
"anatomy"/"medical" do not count); for any other scene they must share at least one content word or plain synonym with the search. A QA "FAIL" is also weak.
A weak clip triggers the retry chain (CSV `footage_alt` first, then Gemini visual direction if available, then the planner's own words). A clip of the wrong body
part is never shown as an explanation: the scene becomes footage-less (card) and is flagged. Gemini vision on frames is optional and skipped without quota (it was
429 during these runs). No model is needed for the check.

## CSV directs the visuals
New columns: `visual` (footage|3d|text|chapter|counter|bar|timeline|flow|youtube), `organ`, `shot` (orbit|zoom|peel|isolate), `footage_alt` (` | ` separated), `source`
(stock|youtube|flow). When any row fills one, `direction.dscenes_from_rows` plans the scenes from the CSV with NO Gemini planning call; empty rows get plain-rule
defaults. Explicit rows are honoured (3D is not capped to once per video; 3D is never extended over a directed row; consecutive 3D rows of one organ merge).
Prompt updated: `CSV_GENERATOR_PROMPT.md`.

## 3D library (`health_cinema/library.py`)
Model = GLB with `Layer_*` groups + anchors file; organ = registry entry (anchor, hero layers, context layers, labels, aliases); shot = reusable camera/layer behaviour.
`auto:<organ>:<shot>` journeys are generated from the model's own anchors (distance from the organ's size), so adding an organ is data. Prepared from Z-Anatomy with
`bench/prep_regions.py` (Blender, ~3-7 min each):
- `abdomen`: liver + gallbladder, pancreas, spleen, stomach + oesophagus, duodenum/jejunum/colon/appendix, bladder, abdominal vessels, lower ribs/lumbar spine/pelvis (context).
- `msk`: whole skeleton (277 bones), 23 intervertebral discs, 77 ligaments, 4 menisci; anchors for knee/hip/shoulder/elbow/wrist (both sides) and spine.
Coverage now: heart, lungs, brain, eye (authored) + liver, gallbladder, pancreas, stomach, intestines, spleen, bladder, abdomen, knee, hip, shoulder, elbow, spine, skeleton.
Not covered: kidneys (Z-Anatomy credits the kidney CC BY-NC: excluded, needs another source), cells/microscopy, pathology (plaque, clots, tumours, fatty liver look),
blood-flow particles, reproductive anatomy, muscles, an articular-cartilage layer (the source has none: the knee shows bones, menisci, cruciate ligaments).

# Stage 3 (2026-10-29): pathology and cell scenes
Procedural illustrations (`health_cinema/threejs/procedural.js`, templates `micro:<kind>:<shot>`, no model file, anchors in `templates/micro_anchors.json`):
- `blood_flow`: red blood cells tumbling through a vessel; `plaque`: lipid deposit grows on the far wall and narrows the channel; `clot`: platelets + fibrin pack the vessel,
  upstream cells stack up, downstream flow thins; `cell` / `fatty_cell`: nucleus, mitochondria, and lipid droplets that grow until the cell is full.
- Everything is deterministic (seeded; positions are functions of time and 0..1 `tracks`), so renders are repeatable and cacheable. They are labelled illustrations, not anatomy.
Organ condition shots (`auto:<organ>:fatty|inflamed`): the organ's own colour drifts from healthy toward the condition (liver/pancreas can be fatty; any prepared digestive
organ can be inflamed) with a label. `tracks` and `tints` are part of the spec, scaled with the scene length (`clips.scale_spec`) and sampled per frame (`journey.sample`).
Selection: explicit via the CSV (`visual=3d`, `organ=plaque|clot|blood flow|cell|fat droplets`, `shot=fatty|inflamed`); from narration only on specific phrases
(atherosclerosis, plaque, clogged/narrowed arteries, blood clot, thrombosis, fat/lipid droplets) so existing scripts keep their plans.
Not done: kidneys (CC BY-NC in Z-Anatomy), tumours, kidney stones, osteoporosis/arthritis bone changes, medication mechanisms, immune cells, DNA/proteins.

## Kidney (2026-10-29)
Z-Anatomy's kidney is CC BY-NC and stays excluded. Added the original BodyParts3D kidneys (FMA7204/FMA7205), ureters (FMA15571/15572) and adrenal glands (FMA15629/15630)
from `partof_BP3D_4.0_obj_99.zip` (64,888,505 bytes, sha256 9fbc713f...1c97, https://dbarchive.biosciencedbc.jp/data/bodyparts3d/LATEST/). Licence page now says **CC BY 4.0**,
attribution "BodyParts3D, (c) The Database Center for Life Science licensed under CC Attribution 4.0 International" (no share-alike; Z-Anatomy quotes the older CC BY-SA 2.1 JP).
`bench/prep_kidney.py` places them by matching BodyParts3D's liver to Z-Anatomy's liver (24 orientations scored by mean vertex distance, refuses when the best is not clearly
ahead) and centres the pair on the midline. Check: kidney 10.5 cm tall, ureters end at the bladder (z 0.875 vs bladder 0.83-0.88), adrenals sit on top. Files: ~/HealthCinemaTools/bp3d/ (zip, parts lists), model in
~/HealthCinemaTools/bench/abdomen.glb (previous copy in bench/_before_kidney/). Library organ: `kidney` (aliases kidneys, renal, kidney stones, dialysis, urinary system).
