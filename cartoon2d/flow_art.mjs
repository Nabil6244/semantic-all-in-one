// Makes the cartoon2d art with Flow images (pictures only). Run from flow-engine/: FLOW_ALLOW_REAL_CREDITS=1 node ../cartoon2d/flow_art.mjs chars|bg|props <outDir>
import WebSocket from "../flow-engine/node_modules/ws/wrapper.mjs";
import fs from "node:fs";
import path from "node:path";
const [,, kind, outDir] = process.argv;
const STYLE = "2D cartoon character for a preschool TV show, modern children's animation style, flat bright colors, soft simple cel shading, clean bold dark-brown outlines, friendly big expressive eyes, vector illustration";
const POSE = "full body from head to shoes, standing straight and facing the viewer, arms hanging down slightly away from the body with a clear gap between each arm and the torso, open relaxed hands, feet slightly apart, closed-mouth gentle smile, eyes open looking at the viewer, centered, plain pure white background, no shadow, no text, no other characters";
const P = {
  chars: [
    `${STYLE}. A friendly young woman named Molly, the show's host, with wavy shoulder-length red hair, green eyes, light freckles, wearing a coral short-sleeve t-shirt under blue denim overalls with two buttons, and white sneakers. ${POSE}`,
    `${STYLE}. A cheerful 6-year-old girl named Lily with light skin, brown hair in a high ponytail, a pink headband with a small bow, wearing a pink t-shirt under a blue denim pinafore dress, white socks and white sneakers. ${POSE}`,
    `${STYLE}. A cheeky 4-year-old boy named Ollie, chubby cheeks, light skin, freckles, short messy light-brown hair, wearing a yellow t-shirt with a red star, green shorts, and blue sneakers. ${POSE}`,
  ],
  bg: [
    "2D cartoon background for a preschool TV show, modern children's animation style, flat bright colors, clean outlines, vector illustration. Inside a bright rainbow soft-play room: pastel sky mural with a rainbow and clouds on the back wall, a colourful ball pit on the left, a small slide on the right, soft padded floor in big tiles, toy blocks and balloons along the walls. Wide shot, eye level, the middle of the floor is empty open space for characters to stand. No characters, no people, no text.",
  ],
  bobo: [
    `${STYLE}. A big friendly round teddy bear named Bobo, honey-brown fur, cream round tummy and muzzle, small round ears, a little red bow tie, big kind smiling eyes, goofy and cuddly, not scary, cartoon proportions. ${POSE.replace("from head to shoes", "from head to feet")}`,
  ],
  garden: [
    "2D cartoon background for a preschool TV show, modern children's animation style, flat bright colors, clean outlines, vector illustration. A sunny garden: bright blue sky with a few white clouds, green grass lawn, two round trees at the sides, a flower bed with red, yellow and blue flowers along the back, a small white picket fence. Wide shot, eye level, the middle of the lawn is empty open space for characters to stand. No characters, no people, no animals, no text.",
  ],
  ep1props: [
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a single shiny red party balloon with a short curly string hanging down",  // balloon_red
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a single shiny blue party balloon with a short curly string hanging down",  // balloon_blue
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a single shiny yellow party balloon with a short curly string hanging down",  // balloon_yellow
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a happy shiny red apple with a green leaf",  // apple
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a happy red strawberry with green leaves",  // strawberry
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a cute red toy fire truck with a ladder, side view",  // firetruck
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a shiny blue bouncy ball",  // ball
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a happy little blue bird, standing",  // bird
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a happy yellow banana",  // banana
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a happy yellow lemon with a leaf",  // lemon
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a smiling yellow sun with rays",  // sun
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: three open paint pots, red, blue and yellow, with a paintbrush",  // paint
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a silly BLUE banana with a surprised face",  // banana_blue
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a silly PURPLE sun with rays and a surprised face",  // sun_purple
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a cute honey pot with dripping golden honey and the word-free label",  // honey
  ],
  hands: [
    "2D cartoon sticker for a preschool TV show, flat bright colors, soft simple cel shading, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow, no arm, only the hand cut off at the wrist, the wrist at the bottom edge of the hand: a single small cartoon child's RIGHT hand with light peach skin and four fingers and a thumb, seen from the front, thumbs up, the thumb pointing straight up, fingers curled",  // human_thumb
    "2D cartoon sticker for a preschool TV show, flat bright colors, soft simple cel shading, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow, no arm, only the hand cut off at the wrist, the wrist at the bottom edge of the hand: a single small cartoon child's RIGHT hand with light peach skin and four fingers and a thumb, seen from the front, making a fist, fingers curled closed",  // human_fist
    "2D cartoon sticker for a preschool TV show, flat bright colors, soft simple cel shading, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow, no arm, only the hand cut off at the wrist, the wrist at the bottom edge of the hand: a single small cartoon child's RIGHT hand with light peach skin and four fingers and a thumb, seen from the front, pointing straight up with the index finger, the other fingers curled",  // human_point
    "2D cartoon sticker for a preschool TV show, flat bright colors, soft simple cel shading, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow, no arm, only the hand cut off at the wrist, the wrist at the bottom edge of the hand: a single small cartoon child's RIGHT hand with light peach skin and four fingers and a thumb, seen from the front, open palm facing the viewer, fingers spread, waving hello",  // human_open
    "2D cartoon sticker for a preschool TV show, flat bright colors, soft simple cel shading, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow, no arm, only the hand cut off at the wrist, the wrist at the bottom edge of the hand: a single big honey-brown cartoon teddy bear paw (RIGHT paw) with a cream paw pad, chubby short fingers, seen from the front, thumbs up, the thumb pointing straight up, fingers curled",  // bear_thumb
    "2D cartoon sticker for a preschool TV show, flat bright colors, soft simple cel shading, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow, no arm, only the hand cut off at the wrist, the wrist at the bottom edge of the hand: a single big honey-brown cartoon teddy bear paw (RIGHT paw) with a cream paw pad, chubby short fingers, seen from the front, making a fist, fingers curled closed",  // bear_fist
    "2D cartoon sticker for a preschool TV show, flat bright colors, soft simple cel shading, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow, no arm, only the hand cut off at the wrist, the wrist at the bottom edge of the hand: a single big honey-brown cartoon teddy bear paw (RIGHT paw) with a cream paw pad, chubby short fingers, seen from the front, pointing straight up with the index finger, the other fingers curled",  // bear_point
    "2D cartoon sticker for a preschool TV show, flat bright colors, soft simple cel shading, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow, no arm, only the hand cut off at the wrist, the wrist at the bottom edge of the hand: a single big honey-brown cartoon teddy bear paw (RIGHT paw) with a cream paw pad, chubby short fingers, seen from the front, open palm facing the viewer, fingers spread, waving hello",  // bear_open
  ],
  ep34props: [
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a big plain bright red circle shape with a cute smiling face",  // shape_circle
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a big plain bright blue square shape with a cute smiling face",  // shape_square
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a big plain bright yellow triangle shape with a cute smiling face",  // shape_triangle
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a big plain bright orange five-pointed star shape with a cute smiling face",  // shape_star
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a round chocolate chip cookie",  // cookie
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a round red wall clock with big numbers-free face and two hands",  // clock
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: one triangle slice of cheese pizza with round pepperoni",  // pizza
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a square house window with four square panes and a blue frame",  // window
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a square gift box wrapped in green paper with a red ribbon bow",  // present
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a triangle sandwich half with lettuce and cheese",  // sandwich
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a little house with a square red front, a triangle roof, a round window and a door",  // house
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a happy cute brown puppy dog, full body standing, facing the viewer",  // dog
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a happy cute pink pig, full body standing, facing the viewer",  // pig
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a happy cute fluffy white sheep, full body standing, facing the viewer",  // sheep
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a happy cute brown horse, full body standing, facing the viewer",  // horse
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a happy cute white hen chicken with a red comb, full body standing, facing the viewer",  // chicken
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a happy cute green frog sitting, facing the viewer",  // frog
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a happy cute tiny fluffy yellow baby chick",  // chick
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a happy cute tiny fluffy baby lamb",  // lamb
    "2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: a white dog bone",  // puppy_bone
  ],
  farm: [
    "2D cartoon background for a preschool TV show, modern children's animation style, flat bright colors, clean outlines, vector illustration. A sunny happy farm: a big red barn with white trim on the left, a wooden fence, green grass, a small pond with lily pads on the right, a few round trees, hay bales, blue sky with white clouds. Wide shot, eye level, the middle of the grass is empty open space for characters to stand. No characters, no people, no animals, no text.",
  ],
  props: [
    "2D cartoon sticker of a happy cute cow for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, full body standing, facing the viewer, centered, plain pure white background, no text",
    "2D cartoon sticker of a happy cute yellow duck for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, full body standing, facing the viewer, centered, plain pure white background, no text",
    "2D cartoon sticker of a happy cute orange cat for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, full body sitting, facing the viewer, centered, plain pure white background, no text",
  ],
};
// places: one new background per place of an episode, painted for depth (clear near / middle / far) and an open floor.
// PLACES_FILE = JSON list of short place descriptions, e.g. ["a sunny beach with a red lighthouse far away", ...]
const PLACE_STYLE = "2D cartoon background for a preschool TV show, modern children's animation style, flat bright vibrant colors, clean outlines, vector illustration";
const PLACE_DEPTH = "Wide shot, eye level, with clear depth: a few big details close to the camera at the bottom corners, the main scene in the middle, and far hills, buildings or sky in the distance; a sunny day with a bright blue sky and a few separate white clouds floating free of the trees if outdoors. The middle of the ground is empty open flat space for characters to stand. No characters, no people, no animals, no text.";
if (kind === "places") P.places = JSON.parse(fs.readFileSync(process.env.PLACES_FILE, "utf8")).map(d => `${PLACE_STYLE}. ${d}. ${PLACE_DEPTH}`);
// side: the same character seen from the side (profile) for walking / running, made with the character's own picture as the
// reference. CHAR = molly|lily|ollie|bobo; the reference is cartoon2d/cast/<CHAR>/source.png.
const SIDE_LOOK = {
  molly: "the young woman Molly with wavy shoulder-length red hair, coral t-shirt, blue denim overalls and white sneakers",
  lily: "the 6-year-old girl Lily with a brown high ponytail, pink headband, pink t-shirt, blue denim pinafore dress, white socks and white sneakers",
  ollie: "the 4-year-old boy Ollie with short messy light-brown hair, yellow t-shirt with a red star, green shorts and blue sneakers",
  bobo: "Bobo the big round honey-brown teddy bear with a cream tummy and muzzle, small round ears and a red bow tie",
};
const SIDE_POSE = "Full body seen from the side in profile, facing to the right, standing straight, both arms hanging straight down at the sides, legs straight and together, from head to feet, eyes open, gentle smile, centered, plain pure white background, no shadow, no text, no other characters";
if (kind === "side" && process.env.NOREF) P.side = Object.values(SIDE_LOOK).map(l => `${STYLE}. ${l}. ${SIDE_POSE}.`);
else if (kind === "side") P.side = [`${STYLE}. Exactly the same character as the reference picture: ${SIDE_LOOK[process.env.CHAR]}. Full body seen from the side in profile, facing to the right, standing straight, both arms hanging straight down at the sides, legs straight and together, from head to feet, eyes open, gentle smile, centered, plain pure white background, no shadow, no text, no other characters. Same colors, same outfit, same proportions and the same drawing style as the reference.`];
// charsfile: cast concepts from a JSON list of character descriptions (CHARS_FILE), same style + pose as the Ch1 cast
if (kind === "charsfile") P.charsfile = JSON.parse(fs.readFileSync(process.env.CHARS_FILE, "utf8")).map(d => `${STYLE}. ${d.replace(/^[^:]+: /, "")}. ${POSE.replace("from head to shoes", "from head to feet")}`);
// propsfile: stickers from a JSON list of short descriptions (PROPS_FILE), same sticker style as the other props
if (kind === "propsfile") P.propsfile = JSON.parse(fs.readFileSync(process.env.PROPS_FILE, "utf8")).map(d => `2D cartoon sticker for a preschool TV show, flat bright colors, clean bold dark-brown outlines, vector illustration, centered, plain pure white background, no text, no shadow: ${d}`);
// photos: realistic first-words pictures for the baby speech channel (PHOTOS_FILE = JSON list of short descriptions)
if (kind === "photos") P.photos = JSON.parse(fs.readFileSync(process.env.PHOTOS_FILE, "utf8")).map(d => `A bright, clean, realistic studio photo of ${d}, centered, the whole object in view, on a plain pure white background, soft even light, vivid natural colors, sharp focus, no text, no people, no hands, no shadow`);
let prompts = P[kind];
if (process.env.ONLY) { const keep = process.env.ONLY.split(",").map(Number); prompts = prompts.filter((_, i) => keep.includes(i)); }
const accountIds = ["3ff7a20e-2884-42f2-896f-105be8ea4568", "a6d0b7d3-89f6-4cc3-855d-cfd5983064f4", "8829896c-1428-4f06-96fb-d2c24f3d791c"];
fs.mkdirSync(outDir, { recursive: true });
const ws = new WebSocket("ws://127.0.0.1:8787/ws");
let done = false; const res = [];
ws.on("message", d => { let m; try { m = JSON.parse(String(d)); } catch { return; } fs.appendFileSync(path.join(outDir, "events.jsonl"), JSON.stringify({type: m.type, status: m.status, index: m.index, path: m.path, msg: String(m.message || m.generateError || m.error || m.log || "").slice(0, 300)}) + "\n");
  if (["PROMPT_RESULT", "GENERATE_DONE"].includes(m.type) || m.generateError) {
    console.log(JSON.stringify({ t: m.type, s: m.status, i: m.index, p: m.path, paths: m.paths, e: String(m.message || m.generateError || m.error || "").slice(0, 200) }));
    if (m.type === "PROMPT_RESULT") res.push(m); if (m.type === "GENERATE_DONE") done = true; } });
await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
ws.send(JSON.stringify({ type: "GENERATE", prompts: prompts.join("\n"), accountIds, settings: {
  mediaKind: "image", model: "BELUGA", aspectRatio: (kind === "bg" || kind === "garden" || kind === "farm" || kind === "places") ? "IMAGE_ASPECT_RATIO_LANDSCAPE" : (kind === "props" || kind === "ep1props" || kind === "hands" || kind === "ep34props" || kind === "propsfile" || kind === "photos") ? "IMAGE_ASPECT_RATIO_SQUARE" : "IMAGE_ASPECT_RATIO_PORTRAIT",
  imageCount: (kind === "ep1props" || kind === "ep34props" || kind === "propsfile" || kind === "photos") ? 1 : 2, autoDownload: true, ...(kind === "side" && !process.env.NOREF ? { referenceImages: [path.resolve("..", "cartoon2d", "cast", process.env.CHAR, "source.png")] } : {}), outputDir: outDir, folder: kind, generationMode: "rpc", delayMin: 2, delayMax: 4, refreshFrequency: 50 } }));
const deadline = Date.now() + 10 * 60 * 1000;
while (!done && Date.now() < deadline) await new Promise(r => setTimeout(r, 1000));
fs.writeFileSync(path.join(outDir, `${kind}_results.json`), JSON.stringify(res, null, 1));
ws.close(); process.exit(done ? 0 : 3);
