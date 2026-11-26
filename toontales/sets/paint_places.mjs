// Toon Tales: paint every place of a story plan with Flow (pictures only), once each.
// Run from flow-engine/ with the Flow server up (node server.js):
//   FLOW_ALLOW_REAL_CREDITS=1 node ../toontales/sets/paint_places.mjs ../toontales/stories/<id>/plan.json [--redo store,street]
// Writes toontales/stories/<id>/places/<place>.png (9:16). Places that already have a picture are skipped.
import WebSocket from "../../flow-engine/node_modules/ws/wrapper.mjs";
import fs from "node:fs";
import path from "node:path";

const [,, planPath, ...rest] = process.argv;
const redo = new Set(rest.includes("--redo") ? rest[rest.indexOf("--redo") + 1].split(",") : []);
const plan = JSON.parse(fs.readFileSync(planPath, "utf8"));
const dir = path.join(path.dirname(planPath), "places");
// each run downloads into its own folder: the server names files 001.png... per run and would hand back an
// older run's file of the same name instead of the new picture
const raw = path.join(dir, "raw", `run-${Date.now()}`);
fs.mkdirSync(raw, { recursive: true });

// Matches the puppets: flat cartoon, bold dark outlines, warm storybook colours. The lower part of the
// picture is the ground the puppets stand on (sets/backdrop.py lays it on the floor).
// channel preset: background mode (3d places are built in Blender, nothing to paint) and its own paint style
const chFile = plan.channel ? path.join(path.dirname(new URL(import.meta.url).pathname), "..", "channels", `${plan.channel}.json`) : null;
const ch = chFile && fs.existsSync(chFile) ? JSON.parse(fs.readFileSync(chFile, "utf8")) : {};
const mode = plan.backgrounds || ch.backgrounds || "3d";
const STYLE = plan.paint_style || ch.paint_style || "2D cartoon background painting for an animated history explainer show, flat colours with soft simple shading, clean bold dark-brown outlines, warm storybook palette, vector illustration";
const FRAME = plan.frame || "Vertical 9:16 picture, eye-level view. The bottom 40% of the picture is open, empty, flat ground or floor in the foreground seen from slightly above, where characters will stand; the scenery is behind it. Nothing in the foreground. No text, no letters, no signs with writing, no logos";
const isWorld = n => { const p = plan.places[n]; return p && p.world && (mode === "3d" || !p.prompt); };
const names = Object.keys(plan.places || {}).filter(n => !isWorld(n))  // 3D world places: nothing to paint
  .filter(n => redo.has(n) || !fs.existsSync(path.join(dir, `${n}.png`)));
if (!names.length) { console.log("all places painted"); process.exit(0); }
const prompts = names.map(n => {
  const p = plan.places[n];
  const body = typeof p === "string" ? p : p.prompt;
  // a plan with its own cast (Reddit Shorts) shows its people big in the picture; Toon Tales places stay empty
  if (plan.cast) return `${STYLE}. ${body}. ${FRAME}.`;
  return `${STYLE}. ${body}. Any people only small in the far background. ${FRAME}.`;
});
console.log("painting", names.join(", "));

const accountIds = ["3ff7a20e-2884-42f2-896f-105be8ea4568", "a6d0b7d3-89f6-4cc3-855d-cfd5983064f4", "8829896c-1428-4f06-96fb-d2c24f3d791c"];
const ws = new WebSocket("ws://127.0.0.1:8787/ws");
let done = false;
const got = {};
const seen = {};
ws.on("message", d => {
  let m; try { m = JSON.parse(String(d)); } catch { return; }
  fs.appendFileSync(path.join(raw, "events.jsonl"), JSON.stringify({ type: m.type, status: m.status, index: m.index, path: m.path, paths: m.paths, msg: String(m.message || m.generateError || m.error || "").slice(0, 300) }) + "\n");
  if (m.type === "PROMPT_RESULT" && Number.isInteger(m.index)) seen[m.index] = true;
  if (m.type === "PROMPT_RESULT") {
    const p = m.path || (m.paths || [])[0];
    if (p && Number.isInteger(m.index) && !got[m.index]) got[m.index] = p;
    console.log(JSON.stringify({ i: m.index, s: m.status, p }));
  }
  // a stale GENERATE_DONE from an earlier batch can arrive first: only stop once this run has its results
  if (m.type === "GENERATE_DONE" && Object.keys(seen).length >= names.length) done = true;
  if (Object.keys(got).length >= names.length) done = true;
  if (m.generateError) console.log("ERROR", m.generateError);
});
await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
ws.send(JSON.stringify({ type: "GENERATE", prompts: prompts.join("\n"), accountIds, settings: {
  mediaKind: "image", model: "BELUGA", aspectRatio: "IMAGE_ASPECT_RATIO_PORTRAIT", imageCount: 1,
  autoDownload: true, outputDir: raw, folder: plan.id, generationMode: "rpc", delayMin: 2, delayMax: 4, refreshFrequency: 50 } }));
const deadline = Date.now() + 15 * 60 * 1000;
while (!done && Date.now() < deadline) await new Promise(r => setTimeout(r, 1000));
ws.close();
let ok = 0;
names.forEach((n, i) => {
  const p = got[i];
  if (p && fs.existsSync(p)) { fs.copyFileSync(p, path.join(dir, `${n}.png`)); ok++; console.log("PLACE", n, "->", p); }
  else console.log("MISSING", n);
});
process.exit(ok === names.length ? 0 : 3);
