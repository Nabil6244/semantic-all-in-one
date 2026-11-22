// Stickman Meme look: paint rooms with Flow (pictures only), once each. Called by stickman/backgrounds.py:
//   FLOW_ALLOW_REAL_CREDITS=1 node ../stickman/paint_places.mjs <job.json>      (run from flow-engine/, server up)
// job.json = {id, aspect: "landscape"|"portrait", out: dir, prompts: {place: prompt}}. Writes <out>/<place>.png.
import WebSocket from "../flow-engine/node_modules/ws/wrapper.mjs";
import fs from "node:fs";
import path from "node:path";

const job = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const names = Object.keys(job.prompts).filter(n => !fs.existsSync(path.join(job.out, `${n}.png`)));
if (!names.length) { console.log("all rooms painted"); process.exit(0); }
// each run downloads into its own folder: the server names files 001.png... per run
const raw = path.join(job.out, "raw", `run-${Date.now()}`);
fs.mkdirSync(raw, { recursive: true });
const prompts = names.map(n => job.prompts[n].replace(/\s+/g, " "));
console.log("painting", names.join(", "));

const accountIds = ["3ff7a20e-2884-42f2-896f-105be8ea4568", "a6d0b7d3-89f6-4cc3-855d-cfd5983064f4", "8829896c-1428-4f06-96fb-d2c24f3d791c"];
const ws = new WebSocket("ws://127.0.0.1:8787/ws");
let done = false;
const got = {}, seen = {};
ws.on("message", d => {
  let m; try { m = JSON.parse(String(d)); } catch { return; }
  fs.appendFileSync(path.join(raw, "events.jsonl"), JSON.stringify({ type: m.type, status: m.status, index: m.index, path: m.path, paths: m.paths, msg: String(m.message || m.generateError || m.error || "").slice(0, 300) }) + "\n");
  if (m.type === "PROMPT_RESULT" && Number.isInteger(m.index)) {
    seen[m.index] = true;
    const p = m.path || (m.paths || [])[0];
    if (p && !got[m.index]) got[m.index] = p;
  }
  // a stale GENERATE_DONE from an earlier batch can arrive first: only stop once this run has its results
  if (m.type === "GENERATE_DONE" && Object.keys(seen).length >= names.length) done = true;
  if (Object.keys(got).length >= names.length) done = true;
  if (m.generateError) console.log("ERROR", String(m.generateError).slice(0, 200));
});
await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
ws.send(JSON.stringify({ type: "GENERATE", prompts: prompts.join("\n"), accountIds, settings: {
  mediaKind: "image", model: "BELUGA", aspectRatio: job.aspect === "portrait" ? "IMAGE_ASPECT_RATIO_PORTRAIT" : "IMAGE_ASPECT_RATIO_LANDSCAPE",
  imageCount: 1, autoDownload: true, outputDir: raw, folder: job.id, generationMode: "rpc", delayMin: 2, delayMax: 4, refreshFrequency: 50 } }));
const deadline = Date.now() + 14 * 60 * 1000;
while (!done && Date.now() < deadline) await new Promise(r => setTimeout(r, 1000));
ws.close();
let ok = 0;
names.forEach((n, i) => {
  const p = got[i];
  if (p && fs.existsSync(p)) { fs.copyFileSync(p, path.join(job.out, `${n}.png`)); ok++; console.log("PLACE", n); }
  else console.log("MISSING", n);
});
process.exit(ok === names.length ? 0 : 3);
