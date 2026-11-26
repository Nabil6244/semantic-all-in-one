# Video Kit guide: make the video yourself

You are the editor and the motion designer. The owner gives a **script** and a **voiceover**; you make `final.mp4`.
There is no template engine: you write each graphic scene as a small HTML page and pick footage or photos for the rest.
**The owner's main rule: lots of graphics and a hook in every graphic, so the audience never gets bored.**

## Steps
1. **align** the voice (pass the script too, for spelling). You get every sentence with its start and end time.
2. **Story pass** (before any scene): read the whole script and write down in `plan.json` → `"story"`:
   the one question the video answers, its beats (hook, setup, problem, turns, payoff), the recurring visual threads
   (the main character/animal/object, the map, the globe) and how each comes back.
3. **Plan** in `<project>/plan.json` (format below): every scene with start, end, kind, what it `shows` and its hooks.
   Scenes are **2.5–6 s** (8 s only for a dense graphic that keeps changing). Each scene's start = its first word's time,
   end = the next scene's start; the last one ends at the voice's end + 1 s. Then run **check_plan** and fix every
   problem it lists before making any scene.
3. **Pick a look pack** (below) or write one look and use it everywhere, so the whole film matches.
4. **Make each scene**: write `scenes/<name>.html` → **look** at stills (pass `at` so word times work) → fix → **scene**
   (always pass `at` = the scene's start). For footage/photos: **find** → **scene** with `media` + `overlay_html`.
5. **join** all clips in order with the voice, music and sound effects on the hooks. **look** at final.mp4.

## Follow the narration: the picture tells the same story (most important)
- **What is said is what is seen.** When the narrator names an animal, a person, a place, an object, a number or an event,
  that exact thing is on screen within 0.5 s of the word: footage or a photo of THAT animal (not a generic one), a pin on
  THAT place, THAT number counting up, a card for THAT person. List them in each scene's `shows`.
- **Same subject, same look.** The main animal/person/object keeps one identity through the film (the same footage
  source, the same photo, the same drawn icon and colour), so the viewer follows one character.
- **Literal first, then meaning.** "The walrus dives 80 metres" → walrus footage, then a depth gauge counting to 80 m
  over it. "Its heart slows" → a heart icon with a beat line slowing. Never a mood shot where a concrete thing was named.
- **Cause and effect are shown as a chain**: when the narration says because / so / then / which means, the graphic links
  the two things (an arrow, a before → after, a split screen).
- **Searches use the narration's words**: `find` with the exact animal/place/object named (add the action: "walrus diving",
  "lion hunting at night"). Look at what came back; if it is not that thing, search again with other words or draw it.
- **The story arc is visible**: the hook asks the question on screen; each beat moves it on; the end answers it, ideally
  calling back to the opening image (the same globe, the same animal, now changed).

## plan.json
```json
{"story": {"question": "...", "beats": ["hook: ...", "setup: ...", "turn: ...", "payoff: ..."], "threads": ["the globe", "Budyko"]},
 "scenes": [
  {"name": "s01_hook", "start": 0.0, "end": 6.02, "kind": "graphic", "shows": ["717 million", "globe", "ice", "equator"],
   "hooks": ["slam:seventeen", "shake:ice", "highlight:equator"]},
  {"name": "s03_crack", "start": 12.86, "end": 14.74, "kind": "footage", "media": "glacier crack", "overlay": true,
   "shows": ["ice cracking"], "hooks": ["punch:frightening"]}]}
```
kind: graphic | footage | photo. `shows`: every concrete thing the scene puts on screen, in the narration's words.

## 3D first, little text, animals (the owner's taste: follow it)
- **3D first.** At least half of the graphic time is 3D. Use the 3D pieces in `agent_kit/looks/doc_teal/`:
  - `terrain3d.js` + the `terrain` tool: any sea, coast, valley, mountain range or country as real 3D relief, land and
    seafloor. Move the camera (dolly, orbit, tilt), raise or lower `water` to flood or drain it, pin places with `T.screen`.
  - `block3d.js`: anything underground or underwater as a 3D cut-away block (rock layers, a seafloor, a buried canyon,
    a river cutting down, water and sediment). Animate its params (carve, sea, fill) and orbit the camera.
  - `globe.js`: the whole planet (ice, oceans, a place on Earth).
  - three.js directly for anything else (objects, simple models, particles). A flat 2D diagram only when 3D adds nothing.
- **Little text.** At most 6 words on screen at once, except a quote or the big questions. Never write out what the
  narrator is saying. Labels are 1–3 words; numbers are counters, not sentences. One text element at a time.
- **Animals.** When the narration names an animal, show real footage of THAT animal (find kind=video, e.g. "dolphins
  jumping", "camel walking desert"), at least 2 s. When it talks about the sea, life, nature, a coast or a river in
  general, prefer footage WITH animals in it (fish, dolphins, birds, turtles, herds) over empty landscapes.

## Keep them watching (follow every rule)
- **Graphics first: at least 70 % of the runtime is graphics.** Footage and photos are never shown bare for more than
  2.5 s: put a label, a number, a map pin, a quote or a caption on them with `overlay_html`.
- **The first 3 seconds are a hook**: the most surprising number, image or question of the whole video, big, with a
  punch or slam on the first key word. Never open on a slow title or an empty frame.
- **Something new every 2–3 seconds**, inside a scene too: a new element, a number that counts, a line that draws on,
  a camera push, a highlight on a word. A still frame for more than 1 s is a failure.
- **Every graphic has at least two hook moves on spoken words** (`K.when('word')`): one entry and one reveal. Hook moves
  in `kit.js`: `punch` (zoom bump), `slam` (lands from big), `shake` (impact), `flash` (hard reveal), `wipe` (reveal from a
  side or a circle), `highlight` (marker under a word), `countUp`, `drawOn`, `drift` + `parallax` (camera always moving),
  `stagger` (lists arrive one by one), `typed` (typewriter).
- **Show, don't write**: a number becomes a counter, a bar or a scale comparison; a place becomes a map pin; a process
  becomes arrows that draw on; a time becomes a timeline; a person becomes a photo card with name and role. Text alone is
  only for a quote or a question, and then large.
- **Open loops**: every 30–60 s put a question or a teaser on screen ("but the rocks disagreed…", "why didn't life die?")
  and pay it off later.
- **Variety**: never the same kind of graphic twice in a row; change layout side (left/right/centre), colour emphasis and
  camera move from scene to scene. Use the 3D globe or a 3D object at least once a minute in science/geography videos.
- **Contrast** makes hooks: before/after, small vs huge, then vs now, ocean vs ice. Split screens and side-by-side numbers.
- **Sound on the hooks**: a whoosh on every wipe or big move, an impact on every slam/shake, a ui/text tick on counters and
  pins, a riser before a big reveal. About one effect every 3–6 s.

## Look packs (in `agent_kit/looks/`)
- **doc_teal**: teal-black documentary, serif titles, orange accent, grain and vignette.
  `<link rel="stylesheet" href="/agent_kit/looks/doc_teal/look.css">`; classes `serif title kicker label small accent
  chip card caption flash hl grain vignette abs`. 3D Earth: `import { makeGlobe } from '/agent_kit/looks/doc_teal/globe.js'`,
  then `globe.render({ iceLat, spin, scale })` each frame (iceLat 90 = no ice, 0 = frozen).
- **doodle_dark**: flat 2D survival story at night (zombie / end-of-the-world day-by-day stories). Everything is drawn,
  no footage. `<link rel="stylesheet" href="/agent_kit/looks/doodle_dark/look.css">`. Read
  `agent_kit/looks/doodle_dark/README.md` before the first scene: it lists the mascot, poses, items, light tools
  and the rules below.
  - **Draw what THIS sentence says, new for every sentence.** There is no place library: each scene is drawn fresh in
    SVG from the narration ("he barricaded the back door with the fridge" → that kitchen, that door, that fridge being
    pushed). The example places in `places.js` show the style, not sets to reuse.
  - The mascot is **Scout** (`hero.js`): same look every scene; pose + face + item from the sentence.
  - Light every place (`light.js`: shafts, glow, dust, haze, character tint) — the light is what makes it look expensive.
  - `dayTag(n)` top-left on every scene once the story has a day.
  - About half the scenes are explainer cards in one system: near-black, faint dot grid, thin amber line icons drawn on,
    small spaced CAPS labels (see README).
- A new look: copy a pack's folder, change colours and fonts, keep the class names.

## Scene page rules (the renderer depends on these)
```html
<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/agent_kit/looks/doc_teal/look.css"></head>
<body><div id="cam" class="abs" style="inset:0">...</div><div class="flash" id="fl"></div>
<div class="vignette"></div><div class="grain"></div>
<script type="module">
import * as K from '/agent_kit/lib/kit.js';
// import * as THREE from '/agent_kit/lib/three.module.js';   // 3D (r170)
window.sceneReady = K.imagesReady();
const hit = K.when('frozen', 1.2);                    // scene time of a spoken word (window.WORDS comes from `at`)
window.renderAt = async (t) => {
  const [dx, dy] = K.shake(t, hit);
  cam.style.transform = `${K.drift(t, 5)} translate(${dx}px,${dy}px) scale(${K.punch(t, hit)})`;
  fl.style.opacity = K.flash(t, hit) * 0.6;
};
</script></body></html>
```
- **Every frame is a pure function of t.** No `setTimeout`, no `requestAnimationFrame` loops, no `Date.now()`, no
  `Math.random()` (use `K.rand(seed)`). CSS animations are allowed (they are seeked to t).
- 1920×1080. Text inside 96 px margins. Body text ≥ 34 px, labels ≥ 26 px.
- Local files: `K.file('/abs/path/photo.jpg')`; files next to the scene: `/@scene/name.ext`; repo files: `/path/from/repo`.
- Overlay pages (over footage/photos) must have a transparent body (`<body class="over">` in doc_teal).
- three.js: render into a canvas inside renderAt (`renderer.render(scene, camera)` once per call), `preserveDrawingBuffer: true`.
- `window.WORDS` = this scene's words `[{w, s, e}]`, times from the scene start. `K.when(word, fallback)` finds one.

## Motion that looks professional
- Ease everything (`easeOutExpo` for snaps, `easeOutCubic` for entries, `easeInOutSine` for drifts); stagger 0.08–0.15 s.
- Enter in the first 0.5 s; leave or settle in the last 0.3 s; the cut is the transition (a whoosh + flash for big ones).
- One idea per screen. Big type, few words. Photos get frames, captions and a source line.

## Checks before join
- `look` every scene at 3–4 times including right after each hook: cut-off text? overlap? too small? empty or dark
  frames? a still stretch? Fix, then render.
- Scene durations add up to the voice length (+ tail). `join` warns when the picture is shorter than the voice.

## Sound
`join(sfx=[{"at": film_seconds, "sound": "whoosh", "db": -14}])`: whoosh, impact, riser, transition, ui, text, cinematic,
technology, ambience, or a file. Music: a calm file from `assets/music`, `music_db` about −20.
