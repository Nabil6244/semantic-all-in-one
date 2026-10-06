import WebSocket from "ws";
import path from "node:path";
import fs from "node:fs";

const outDir = process.env.FLOW_OUT;
const accountId = process.env.FLOW_ACCOUNT;
const model = process.env.FLOW_MODEL || "BELUGA";
const mediaKind = process.env.FLOW_KIND || "image";
const prompt = process.env.FLOW_PROMPT || "A single red apple on a wooden table, soft daylight, simple still photo";
fs.mkdirSync(outDir, { recursive: true });

const ws = new WebSocket("ws://127.0.0.1:8787/ws");
const results = [];
let done = false;
let generateError = null;

ws.on("message", (data) => {
  let msg;
  try { msg = JSON.parse(String(data)); } catch { return; }
  if (["BATCH_PROGRESS","PROMPT_RESULT","GENERATE_DONE","ACCOUNT_STATUS"].includes(msg.type) || msg.generateError) {
    console.log(JSON.stringify({
      type: msg.type, status: msg.status, index: msg.index, accountId: msg.accountId,
      message: String(msg.message || msg.generateError || msg.error || "").slice(0, 320),
      path: msg.path,
    }));
    fs.appendFileSync(path.join(outDir, "events.jsonl"), JSON.stringify(msg) + "\n");
  }
  if (msg.type === "PROMPT_RESULT") results.push(msg);
  if (msg.type === "GENERATE_DONE") done = true;
  if (msg.generateError) { generateError = msg.generateError; done = true; }
});

await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
console.log("SENDING", { outDir, accountId, model, mediaKind, prompt });
const settings = {
  mediaKind,
  aspectRatio: "IMAGE_ASPECT_RATIO_LANDSCAPE",
  imageCount: 1,
  autoDownload: true,
  outputDir: outDir,
  folder: "probe",
  generationMode: "rpc",
  delayMin: 1,
  delayMax: 2,
  refreshFrequency: 50,
};
if (mediaKind === "image") {
  settings.model = model;
} else {
  settings.videoModel = process.env.FLOW_VIDEO_MODEL || "abra";
  settings.videoDuration = 4;
  settings.videoResolution = "360p";
  settings.videoAspectRatio = "VIDEO_ASPECT_RATIO_LANDSCAPE";
}
ws.send(JSON.stringify({
  type: "GENERATE",
  prompts: prompt,
  promptList: [prompt],
  accountIds: [accountId],
  settings,
}));

const deadline = Date.now() + (mediaKind === "video" ? 10 : 6) * 60 * 1000;
while (!done && Date.now() < deadline) await new Promise((r) => setTimeout(r, 1000));
ws.close();

const files = [];
(function walk(d) {
  for (const n of fs.readdirSync(d)) {
    const p = path.join(d, n);
    if (fs.statSync(p).isDirectory()) walk(p);
    else if (/\.(png|jpe?g|webp|mp4)$/i.test(n)) files.push(p);
  }
})(outDir);

// Collect diagnostics
const diags = [];
(function walk(d) {
  for (const n of fs.readdirSync(d)) {
    const p = path.join(d, n);
    if (fs.statSync(p).isDirectory()) walk(p);
    else if (/diagnostic|ogiz0b|yhhmef/i.test(n)) {
      try { diags.push({ file: p, tail: fs.readFileSync(p, "utf8").trim().split("\n").slice(-1)[0] }); } catch {}
    }
  }
})(outDir);

const ok = results.some((r) => r.status === "done" && r.path && fs.existsSync(r.path));
const summary = {
  ok, done, generateError, accountId, model, mediaKind,
  fileCount: files.length, files,
  results: results.map(r => ({ status: r.status, path: r.path, error: r.error || r.message, submission: r.submission })),
  diags,
};
console.log("SUMMARY", JSON.stringify(summary, null, 2));
fs.writeFileSync(path.join(outDir, "summary.json"), JSON.stringify(summary, null, 2));
process.exit(ok ? 0 : 1);
