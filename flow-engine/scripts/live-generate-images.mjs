import WebSocket from "ws";
import path from "node:path";
import fs from "node:fs";
// Spends REAL Flow credits. Manual use only, never part of `npm test` / CI.
if (process.env.FLOW_ALLOW_REAL_CREDITS !== "1") {
  console.error("Refusing to run: this script generates real Flow media. Set FLOW_ALLOW_REAL_CREDITS=1 to run it on purpose.");
  process.exit(2);
}


const outDir =
  process.env.FLOW_OUT ||
  path.join(
    process.env.HOME,
    "Downloads/Semantic YT Studio/Video_2026-10-05_005_test_flow/flow/runs",
    "live_cdp_" + Date.now(),
  );
fs.mkdirSync(outDir, { recursive: true });

const prompts = [
  "Time-lapse dynamic shot of a sprawling futuristic smart city skyline at twilight with rapid light trails of traffic",
  "engineers working on robotic arm modern laboratory",
  "Close-up cinematic shot of an advanced metallic humanoid robot fluidly moving its articulate fingers with glowing micro-circuits",
  "electric vehicle charging plug connected modern ev car",
  "sleek modern electric car driving coastal highway sunset",
].join("\n");

const accountIds = [
  "fcb499ce-f99b-41ec-87ee-5acc1c244357",
  "70a4ee5e-6004-4f5d-9b41-9f467e7f1847",
  "0fb8c358-2f3e-4f54-bc1e-2831337d5755",
];

const mode = process.env.FLOW_GENERATION_MODE || "rpc";
const ws = new WebSocket("ws://127.0.0.1:8787/ws");
const results = [];
let done = false;

ws.on("message", (data) => {
  let msg;
  try {
    msg = JSON.parse(String(data));
  } catch {
    return;
  }
  if (
    ["BATCH_PROGRESS", "PROMPT_RESULT", "GENERATE_DONE"].includes(msg.type) ||
    msg.generateError
  ) {
    console.log(
      JSON.stringify({
        type: msg.type,
        status: msg.status,
        index: msg.index,
        message: String(msg.message || msg.generateError || msg.error || "").slice(0, 220),
        path: msg.path,
      }),
    );
    fs.appendFileSync(path.join(outDir, "events.jsonl"), JSON.stringify(msg) + "\n");
    if (msg.type === "PROMPT_RESULT") results.push(msg);
    if (msg.type === "GENERATE_DONE") done = true;
  }
});

await new Promise((r, j) => {
  ws.on("open", r);
  ws.on("error", j);
});
console.log("SENDING", { outDir, mode, accounts: accountIds.length });
ws.send(
  JSON.stringify({
    type: "GENERATE",
    prompts,
    accountIds,
    settings: {
      mediaKind: "image",
      model: "BELUGA",
      aspectRatio: "IMAGE_ASPECT_RATIO_LANDSCAPE",
      imageCount: 1,
      autoDownload: true,
      outputDir: outDir,
      folder: "batch",
      generationMode: mode,
      delayMin: 2,
      delayMax: 4,
      refreshFrequency: 50,
    },
  }),
);

const deadline = Date.now() + 12 * 60 * 1000;
while (!done && Date.now() < deadline) await new Promise((r) => setTimeout(r, 1000));
ws.close();

const pngs = [];
function walk(d) {
  for (const n of fs.readdirSync(d)) {
    const p = path.join(d, n);
    if (fs.statSync(p).isDirectory()) walk(p);
    else if (/\.png$/i.test(n)) pngs.push(p);
  }
}
walk(outDir);
console.log(
  "SUMMARY",
  JSON.stringify({ done, pngCount: pngs.length, pngs, results }, null, 2),
);

// Copy into project assets as 001.png … for scenes
const assets = path.join(
  process.env.HOME,
  "Downloads/Semantic YT Studio/Video_2026-10-05_005_test_flow/assets",
);
fs.mkdirSync(assets, { recursive: true });
const doneResults = results
  .filter((r) => r.status === "done" && r.path && fs.existsSync(r.path))
  .sort((a, b) => a.index - b.index);
for (const r of doneResults) {
  const dest = path.join(assets, String(r.index + 1).padStart(3, "0") + ".png");
  fs.copyFileSync(r.path, dest);
  console.log("COPIED", dest);
}
process.exit(pngs.length ? 0 : 2);
