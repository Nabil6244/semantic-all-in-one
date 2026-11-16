Continue the Toon Tales "5 channels" work in /Users/muhammadnabil/Downloads/video_generator-main. Stay lean on credits: no subagents, no extra preview renders, ask before every commit or push.

STATE (2026-11-16)
- 3D toon world engine built: toontales/sets/world.py (Kenney CC0 packs in assets/toon_world/kenney/, cel shading,
  outlines, sky, movers with moves/tilt_to, LIGHT bands), toontales/sets/make_worlds.py writes toontales/sets/worlds/*.json
  (highway, town, suburb, room, office, kitchen, mountain_road, desert_road, forest, farm, frontier_town,
  frontier_desert, frontier_office, frontier_laundry, jail = frontier_jail). Run: python3 -m toontales.sets.make_worlds
- Plan places: {"world": "<layout>", "add": [...], "clear": [[x,y]], "remove": [ids], "prompt": "<Flow picture>"}.
  Shots may have "moves" [{id, from?, to, t0, t1, ease, tilt_to?, tilt_from?}] and "look" {at, to?, dist, yaw, pitch, lens}.
  World camera framing: WORLD_CAM in toontales/shots/compile.py.
- Channel layer: toontales/channels/<name>.json (cast file, look, backgrounds "3d"|"flow", paint_style, formula).
  Plan "channel": "channel2"; plan "backgrounds" overrides. schema.channel / cast_file_for / bg_mode / is_world;
  TT_CAST env var feeds voice.py; paint_places.mjs skips 3D places.
- Channel 2 (ref: Downloads/Shorts Slot 1/Channel 2, "Claude Knows My API Key" style) done: channel2.json,
  channel2_cast.json (bart, driver, hume, sheriff), new hats cowboy/tophat/bowler (cast/puppet.py),
  outfits vest/duster/suit (cast/faces.py).
- Test Shorts: stories/bridge_gaps (3D v2, in ~/Downloads/Toon Tales Shorts), stories/black_bart (Channel 2 test,
  was rendering: check toontales/build/queue_black_bart.log, output out/toontales_black_bart.mp4; if done copy to
  ~/Downloads/Toon Tales Shorts/ and send it to the user; if Edge TTS failed just re-run the edit step).
- Render: python3 -m toontales.shots.build_story <plan> && python3 -m toontales.edit.edit <plan>
  (Edge TTS is flaky: retry the edit). Check: python3 -m toontales.plan.check <plan> --fix. Tests: test_toontales_plan.py.
- Channel 4 (ZerryCars, ref Downloads/Shorts Slot 1/Channel 4) built 2026-11-16: channel4.json (length 28-45 s) +
  channel4_cast.json (narrator only, en-US-BrianNeural). sets/parts.py = car parts from shapes ("@engine" cyl/layout
  I|V/induction/cutaway with pumping pistons, "@turbo" spinning wheel, "@supercharger" (electric), "@stand", "@tiles",
  "@pegboard", "@strip", "@start_tree", "@finish"); shot moves {"id", "run_to"} rev parts. Worlds garage + drag_strip.
  edit/hud.py: shot "hud" (animated meter + rival tick) and "callout" (label on a line). Checker: look-shots with
  hud/callout/moves count as alive; short shots with their own hud are not merged. Tint "tint_mode": "color" keeps
  cars bright; tinted copies now start from the model's original material (was: second tinted copy came out dark).
  Engine fix: room shell walls pinned to furniture-kit (fantasy-town-kit "wall" was being used: sideways walls in
  room/office/kitchen/frontier interiors). Test Short: stories/f1_engine (out/toontales_f1_engine.mp4).
- Channel 4 test RENDERED + sent (out/toontales_f1_engine.mp4, 34.8 s, also in ~/Downloads/Toon Tales Shorts/).
  Issues seen, NOT fixed (await user notes): opening wide shot engines tiny + callout overlaps hook title;
  "More spins, more bangs" close-up too close (grey slab); electric motor shots badly framed; drag-race start camera
  too close. Meter "60.0" decimal bug fixed in edit/hud.py (VERSION h2).
- Black Bart (Channel 2) RENDERED + sent (52.8 s), made before the wall fix (old sideways interior walls).
- Channel 1 (Wobbly Tales) built 2026-11-16, NOT rendered yet: channel1.json (length 55-80) + channel1_cast.json
  (vic_pike stationmaster: conductor cap + railway uniform; vic_alder alderman: tophat + frock; vic_ned: bowler + suit;
  all peach "skin" + big "nose"). New rig bits: puppet cfg "skin", face trait "nose", hats "conductor"/"shako",
  outfits "frock"/"railway"/"redcoat". New "@clock" part (hour, min, min2 red hand, run sweeps hands); world pieces
  "ride": <mover id> follow a mover (train carriages). Worlds: victorian_square (clock id "clock"), station (loco),
  railway_line (loco), clock_shop. Story: stories/two_minute_hands (Bristol Corn Exchange two minute hands), 24 shots
  ~56 s, checker OK. Voice lines: Edge TTS kept failing mid-run (16/24 shot jsons written); just re-run
  `python3 -m toontales.shots.build_story toontales/stories/two_minute_hands/plan.json --draft --only none` until all
  24 exist, then draft-check 2-3 cast frames (peach skin/nose/hats look right?), then full render + edit + copy to
  ~/Downloads/Toon Tales Shorts/ and send. Ned's voice changed to en-IE-ConnorNeural (en-GB-OliverNeural does not exist).
  Rough spot: Victorian places sparser than Wobbly's dense sets.
- Channel 1 test RENDERED + sent 2026-11-16 (out/toontales_two_minute_hands.mp4, 46.8 s, in ~/Downloads/Toon Tales Shorts/).
  Fixes made on the way: default nose bigger (faces.py nose_size 62 -> 92, ny 615); compile.frame(): narrated
  "medium" shot with 2+ people now frames as two_shot (was cutting the second person out). Short of the 55-80 s
  channel1 length (voice only fills 45.5 s); await user notes.
- Disk filled up once (render died with "No space left"): keep an eye on df before long renders.
- NOTHING of the 3D world / channels / 16 new stories is committed yet (ask the user first).

NEXT
1. Show the user the Channel 2 test, fix what they flag (fix the engine, not the one video).
2. Channel 4: show the f1_engine test, fix what the user flags. Rough spots: turbo hot side reads as a brown blob,
   colour tint also colours tyres. Then channels in order:
   3 (World In A Box: realistic cut-open house dioramas, realistic man, water),
   5 (Trial & Eureka: realistic close-up objects, glass/metal; fetch Poly Haven CC0 assets via its API).
   Reference videos + channel screenshots: ~/Downloads/Shorts Slot 1/Channel 1..5/.
3. Each channel: preset json + cast (if any) + worlds + one original test Short for approval.
4. Known rough spots: room interiors plain; tinted pieces sometimes render dark (cliffs); buckle reads as a slab.

CHANNEL 3 (World In A Box) — started 2026-11-16
- Reference studied (4 videos, 63-71 s each, ~/Downloads/Shorts Slot 1/Channel 3): realistic 3D diorama sliced side-on
  (grass / soil / gravel / rock bands, stone well shaft, open-front houses with clean white rooms), one realistic
  builder (hard hat + orange jacket or green hoodie, jeans) doing each step, water rising/draining, car/neighbour
  for scale, one-word captions centre. Story shape: "How an ordinary X becomes a secret/survival Y".
- Preset written: toontales/channels/channel3.json ("engine": "diorama"). Nothing else built yet.
- Build plan (needs a NEW realistic path, not the cel-shaded toon world):
  1. sets/diorama.py: ground slice builder (layer bands with PBR textures, cut faces, shaft/room holes), Eevee
     realistic look (HDRI sky, soft shadows, AO), no outlines. PBR textures fetched once from Poly Haven CC0 API
     into assets/diorama/textures/ (shared with Channel 5).
  2. Realistic builder: MPFB 2.0.18 + CC0 makehuman_system_assets already installed (see memory project_mpfb_host);
     export one rigged man GLB (hard hat, jacket, jeans) + a small action set (walk, dig, hammer, carry, climb,
     point, look). Body poses by armature actions, not the 2D puppet rig.
  3. Water: animated plane with level keys (fill/drain), glass-like shader, cut face showing the water body.
  4. Shot compiler: reuse plan schema (places/world/look/moves); "build steps" = pieces that appear/slide in at t0.
  5. First test Short (original topic, not one of the 4 reference stories).

FIXES 2026-11-16 (late, NOT re-rendered, NOT committed)
- compile.frame(): piece-aware framing. look {"fit": [piece ids]} aims at their middle and sizes the shot to them;
  any look aimed at an "@" part never gets closer than the part's size allows (no grey slabs), push/crash zoom
  included (piece_size() table in compile.py; schema.kit_for puts the place's pieces in kit["pieces"]).
- Garage stands moved to x +-0.75 (two engines now share a 9:16 frame); f1_engine plan uses fit + new @motor.
- parts.py: turbo hot side cast iron + glowing rim (was brown blob); new "@motor" (blue can, fins, copper window,
  spinning shaft, orange HV cable). world.py: tinted cars keep wheel/tyre colours (UNTINTED).
- edit.py: on the hook-title shot a callout hangs below the title card.
- Voice speed calibrated from real renders: channel1 narrator base_wpm 222, channel2 200, channel4 168
  (checker length estimate now matches real length within ~2 s).
- two_minute_hands: +5 shots (s11b, s16b, s18b, s19b, s21b, ids renumbered by --fix), ~60 s.
- Denser Victorian worlds: lamp posts, barrels, crates, stalls, fountain, iron fences (square); canopy, luggage,
  chimneys, lit windows (station); fence row, hay, signal (railway_line); wall of clocks, grandfather clocks,
  workbench (clock_shop).
- Black Bart interiors already use furniture-kit walls: only a re-render needed.

CHANNEL 3 STAGE 1 DONE 2026-11-16 (not committed): realistic diorama engine
- toontales/sets/diorama.py (Blender): layouts with "engine": "diorama" are built here instead of world.py
  (shot.py picks the engine; build_story ENGINE_FILES includes it). Pieces @slice (layered ground + boolean cuts),
  @shaft (lined well, front half cut away), @water (origin at bottom; move "level_to" fills/drains; round water is
  cut flat at the face), @room / @house (open front, pitched tile roof, gable, soft ceiling light), @beam, @box
  ("tilt"), "ph:<id>" Poly Haven models, pack models. Any piece: "show_at" (build step appears), move "grow".
  AgX view, HDRI sky, sun, Eevee raytracing/AO. Materials: box-projected PBR, metre-true TILE sizes, GRADE
  (rock graded to grey bedrock, lusher grass, brighter plaster).
- toontales/diorama/fetch_polyhaven.py: 17 CC0 texture sets + 2 HDRIs + 8 small models (fir_sapling, shrub_01,
  wooden_bucket_01, wooden_ladder, sofa_02, wooden_bookshelf_worn, wooden_crate_01, dead_tree_trunk) in
  assets/diorama/ (~100 MB). Full Poly Haven trees are 0.5-1 GB: not used.
- toontales/diorama/layouts.py writes worlds dio_field_well, dio_riverside_house (each has its own "marks";
  schema.kit_for now uses layout marks). schema.DIORAMA_KINDS + ph: models pass the plan checker.
- Still frames checked (well cut-away, wide field, riverside house): match the reference look.
NEXT (stage 2): realistic builder from MPFB (CC0 makehuman assets installed): hard hat, orange jacket, jeans; GLB +
  action set (walk, dig, hammer, carry, climb, point, look); cast puppets in diorama shots must be this rig, not the
  2D puppet. Then channel3_cast.json (narrator voice matched to the reference), more layouts (apartment section,
  beach slice), and the first original test Short.

CHANNEL 3 STAGE 2 DONE 2026-11-16 (not committed): realistic builder
- toontales/diorama/build_actor.py (run: blender -b -noaudio --python toontales/diorama/build_actor.py; needs MPFB,
  so NOT --factory-startup) -> assets/diorama/cast/builder.blend: male 1.67 m, MPFB game_engine rig (UE-style bone
  names), male_casualsuit05 (grey-green jacket + jeans), shoes02, short02 hair, yellow hard hat on the head bone
  (cast "hat": false hides it). All CC0 MakeHuman assets.
- toontales/sets/actor.py: poses written as limb directions in his own space (faces -y, left +x), solved per frame
  (matrix_basis from M_child = M_parent @ R_parent^-1 @ R_child @ basis; verified exact). Acts (diorama/actor_acts.py):
  idle walk carry dig hammer drill climb crouch point look look_down explain nod cheer shock wipe; tools shovel /
  hammer / drill / crate appear in hand; walk/carry params to=[dx,dy] move + face travel; climb params up=dz;
  0.3 s blends between acts. shot.py builds cast entries with "actor" in diorama shots via actor.py.
- channel3_cast.json: builder "Sam" (en-US-ChristopherNeural) + narrator. faces.py skips actor entries; checker
  validates actor acts against ACTOR_ACTS; build_story engine hash includes assets/diorama/cast/*.blend.
- Tests: act contact sheet + 3.4 s motion test (out/channel3_builder_motion_test.mp4): walk good; dig pose too
  upright and the shovel hangs at his side (tune dig + tool offsets in actor.py); hat ridge slightly lumpy.
NEXT: tune dig/shovel, then layouts apartment_section + beach_slice, then first original test Short.

CHANNEL 3 TEST SHORT 2026-11-17 (not committed): stories/rain_tank "How a Backyard Becomes a Hidden Rain Tank"
- Original topic (not one of the 4 reference stories). Plan is generated by stories/rain_tank/make_plan.py
  (edit that, not plan.json), 21 shots ~57 s, narrator only (en-US-ChristopherNeural -5%, base_wpm 211).
- Layout dio_backyard_tank: house + lawn + pit cut in the slice; build stages are named pieces (turf, plug_soil,
  plug_gravel, tank_*, lid, turf2, pipe_a/b/c, pump, pump_pipe, water) and story places remove what is not built yet.
- Engine additions: diorama moves {"id","show":t}/{"id","hide":t}, grow from/to (soil dug away), @box origin on its
  bottom face; world.step only gets list-valued "to". Actor: dig rewritten (two hands on one handle, shovel laid
  through both palms), head pitch sign fixed (+ = chin up).
- Checker: channel "shot_max" (channel3 4.6 s) and "place_run" (8); shots with timed moves are never auto-split.
  faces.py skips actor entries (build + board).
- Render log: toontales/build/queue_rain_tank.log -> out/toontales_rain_tank.mp4 (copy to ~/Downloads/Toon Tales Shorts/).

RAIN_TANK FIXES 2026-11-17: water under 2 cm hidden (diorama._water_seen); compile._fit_people: look shots with
cast slide sideways / pull back so every person fits (aim area keeps its height), pushes clamped too; mark A moved
to the pump; s10 camera. Re-render started (queue_rain_tank.log).

CHANNEL 5 (Trial & Eureka) STARTED 2026-11-17 (not committed)
- References (5 videos, 75-78 s, ~/Downloads/Shorts Slot 1/Channel 5): photoreal close-ups of everyday objects
  (glass bottles + liquid, cork, crown caps, brass coins, magnets, glossy red vending machine, gumballs), dark teal
  subway tiles over a walnut bar counter OR a mint studio backdrop, shallow depth of field, warm studio light;
  'Why X' engineering-history stories; no characters; short phrase captions in small white text.
- channels/channel5.json (+ "captions": "phrase" - NOT yet supported by edit.py), channel5_cast.json (narrator only).
- sets/objects.py: @bottle (crown/torpedo/codd/cork styles, glass tint, fill + liquid), @lathe, @cap (crimped crown
  cork), @cork, @coin (+hole = washer), @magnet, @ball, @wall (procedural subway tiles or flat backdrop), named
  finishes (brass, steel, chrome, gold, copper, silver, rubber, red_paint, ...). Glass and liquids are alpha-blended
  (Eevee cannot refract through glass AND liquid: a refractive bottle hid its drink).
- diorama.py: studio "lights" list, "sun": null, layout "dof" -> shot.py focuses at the camera target distance.
- Layouts dio_bar_counter (walnut counter z 0.9, teal tiles, warm key + cool rim) and dio_mint_studio.
- Textures walnut/oak + studio HDRI fetched. Test still: bottles/caps/coins read right; liquids still a bit opaque.
NEXT: phrase captions in edit.py (channel "captions": "phrase"), gumball machine / coin mechanism parts (rails,
  slots), liquid tuning, then the first original 'Why X' test Short.
