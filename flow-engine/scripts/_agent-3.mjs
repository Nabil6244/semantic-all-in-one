// Manual live check of agent mode (or the standard path) against a running engine. Generates REAL Flow images on one
// account; manual use only, never part of `npm test` / CI.
//   FLOW_ALLOW_REAL_CREDITS=1  required
//   FLOW_OUT                   output folder (required)        FLOW_ACCOUNT      account id (required)
//   FLOW_PROMPTS_FILE          one prompt per line (default: 3 built-in scenes)
//   FLOW_GENERATION_MODE       agent (default) | rpc           FLOW_MODEL        default BELUGA
//   SA_PORT                    engine port (default 8787)
import WebSocket from "ws";
import fs from "node:fs";
import path from "node:path";
if (process.env.FLOW_ALLOW_REAL_CREDITS !== "1") {
  console.error("Refusing to run: this script generates real Flow media. Set FLOW_ALLOW_REAL_CREDITS=1 to run it on purpose.");
  process.exit(2);
}
const outDir = process.env.FLOW_OUT;
fs.mkdirSync(outDir, { recursive: true });
const fromFile = process.env.FLOW_PROMPTS_FILE ? fs.readFileSync(process.env.FLOW_PROMPTS_FILE, "utf8").split("\n").map((l) => l.trim()).filter(Boolean) : null;
const prompts = fromFile || [
  "A coal power plant at dawn with steam rising from cooling towers",
  "Engineers in hard hats inspecting a large steam turbine in a factory hall",
  "A river polluted by industrial runoff flowing past old warehouses",
];
const ws = new WebSocket(`ws://127.0.0.1:${process.env.SA_PORT || 8787}/ws`);
let done = false; const t0 = Date.now();
ws.on("message", (d) => {
  let m; try { m = JSON.parse(String(d)); } catch { return; }
  if (["BATCH_PROGRESS","PROMPT_RESULT","GENERATE_DONE","ACCOUNT_STATUS","LOG"].includes(m.type) || m.generateError) {
    console.log(((Date.now()-t0)/1000).toFixed(1)+"s", JSON.stringify({ type: m.type, status: m.status, index: m.index, mediaIds: m.mediaIds, agentModel: m.agentModel, needsAction: m.needsAction,
      message: String(m.message || m.generateError || m.error || "").slice(0, 300), path: m.path }));
    fs.appendFileSync(path.join(outDir, "events.jsonl"), JSON.stringify(m) + "\n");
  }
  if (m.type === "GENERATE_DONE" || m.generateError) done = true;
});
await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
ws.send(JSON.stringify({ type: "GENERATE", prompts: prompts.join("\n"), promptList: prompts, accountIds: [process.env.FLOW_ACCOUNT],
  promptKeys: prompts.map((_, i) => String(i + 1)),
  settings: { mediaKind: "image", model: process.env.FLOW_MODEL || "BELUGA", aspectRatio: "IMAGE_ASPECT_RATIO_LANDSCAPE", imageCount: 1, autoDownload: true,
    outputDir: outDir, folder: "agent", generationMode: process.env.FLOW_GENERATION_MODE || "agent", delayMin: 1, delayMax: 2, refreshFrequency: 50 } }));
const deadline = Date.now() + 15 * 60 * 1000;
while (!done && Date.now() < deadline) await new Promise((r) => setTimeout(r, 1000));
console.log("FINISHED", done ? "done" : "TIMEOUT", ((Date.now()-t0)/1000).toFixed(1)+"s");
ws.close(); process.exit(0);
