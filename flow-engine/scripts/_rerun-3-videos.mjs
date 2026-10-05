import WebSocket from "ws";
import path from "node:path";
import fs from "node:fs";
// Spends REAL Flow credits. Manual use only, never part of `npm test` / CI.
if (process.env.FLOW_ALLOW_REAL_CREDITS !== "1") {
  console.error("Refusing to run: this script generates real Flow media. Set FLOW_ALLOW_REAL_CREDITS=1 to run it on purpose.");
  process.exit(2);
}


const outDir = process.env.FLOW_OUT;
fs.mkdirSync(outDir, { recursive: true });

const prompts = [
  "Time-lapse dynamic shot of a sprawling futuristic smart city skyline at twilight with rapid light trails of traffic",
  "engineers working on robotic arm modern laboratory",
  "Close-up cinematic shot of an advanced metallic humanoid robot fluidly moving its articulate fingers with glowing micro-circuits",
].join("\n");

const accountIds = [
  "7e5d3e93-06e8-4527-b2a2-895307619bc3", // Account 5
  "45e97c53-f691-440a-a54a-660cc818f0a1", // Account 6
  "3ff7a20e-2884-42f2-896f-105be8ea4568", // Account 7
];

const mode = "rpc";
const ws = new WebSocket("ws://127.0.0.1:8787/ws");
const results = [];
let done = false;

ws.on("message", (data) => {
  let msg;
  try { msg = JSON.parse(String(data)); } catch { return; }
  if (["BATCH_PROGRESS", "PROMPT_RESULT", "GENERATE_DONE"].includes(msg.type) || msg.generateError) {
    console.log(JSON.stringify({
      type: msg.type, status: msg.status, index: msg.index, accountId: msg.accountId,
      message: String(msg.message || msg.generateError || msg.error || "").slice(0, 280),
      path: msg.path,
    }));
    fs.appendFileSync(path.join(outDir, "events.jsonl"), JSON.stringify(msg) + "\n");
    if (msg.type === "PROMPT_RESULT") results.push(msg);
    if (msg.type === "GENERATE_DONE") done = true;
  }
});

await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
console.log("SENDING VIDEO", { outDir, mode, accounts: accountIds.length, prompts: 3 });
ws.send(JSON.stringify({
  type: "GENERATE",
  prompts,
  accountIds,
  settings: {
    mediaKind: "video",
    videoModel: "abra",
    aspectRatio: "IMAGE_ASPECT_RATIO_LANDSCAPE",
    videoDuration: 8,
    videoResolution: "360p",
    imageCount: 1,
    autoDownload: true,
    outputDir: outDir,
    folder: "batch",
    generationMode: mode,
    delayMin: 3,
    delayMax: 6,
    refreshFrequency: 50,
  },
}));

const deadline = Date.now() + 25 * 60 * 1000;
while (!done && Date.now() < deadline) await new Promise((r) => setTimeout(r, 2000));
ws.close();

const mp4s = [];
function walk(d) {
  for (const n of fs.readdirSync(d)) {
    const p = path.join(d, n);
    if (fs.statSync(p).isDirectory()) walk(p);
    else if (/\.mp4$/i.test(n)) mp4s.push(p);
  }
}
walk(outDir);
console.log("SUMMARY", JSON.stringify({ done, mp4Count: mp4s.length, mp4s, results }, null, 2));

const assets = path.join(process.env.HOME, "Downloads/Semantic YT Studio/Video_2026-10-05_005_test_flow/assets");
fs.mkdirSync(assets, { recursive: true });
const doneResults = results
  .filter((r) => r.status === "done" && r.path && fs.existsSync(r.path))
  .sort((a, b) => a.index - b.index);
for (const r of doneResults) {
  const dest = path.join(assets, String(r.index + 1).padStart(3, "0") + ".mp4");
  fs.copyFileSync(r.path, dest);
  console.log("COPIED", dest);
}
process.exit(mp4s.length >= 3 ? 0 : mp4s.length ? 1 : 2);
