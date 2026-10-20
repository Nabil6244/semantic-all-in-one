// Live check: one UI Agent request of 24 real-length scenes on one account. Spends REAL Flow credits. Manual use only.
// FLOW_ALLOW_REAL_CREDITS=1 SA_PORT=8790 node scripts/live-ui-agent-24.mjs <visual_plan.csv> <accountId> [count]
import WebSocket from "ws";
import path from "node:path";
import fs from "node:fs";

if (process.env.FLOW_ALLOW_REAL_CREDITS !== "1") {
  console.error("Refusing to run: this script generates real Flow media. Set FLOW_ALLOW_REAL_CREDITS=1 to run it on purpose.");
  process.exit(2);
}
const [csvPath, accountId, countArg] = process.argv.slice(2);
const count = Number(countArg || 24);

function parseCsv(text) {
  const rows = [];
  let row = [], cur = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"' && text[i + 1] === '"') { cur += '"'; i++; } else if (c === '"') q = false; else cur += c;
    } else if (c === '"') q = true;
    else if (c === ",") { row.push(cur); cur = ""; }
    else if (c === "\n") { row.push(cur); rows.push(row); row = []; cur = ""; }
    else if (c !== "\r") cur += c;
  }
  if (cur || row.length) { row.push(cur); rows.push(row); }
  return rows;
}
const rows = parseCsv(fs.readFileSync(csvPath, "utf8").replace(/^﻿/, ""));
const col = rows[0].indexOf("prompt");
const prompts = rows.slice(1).map((r) => String(r[col] || "").replace(/\s+/g, " ").trim()).filter(Boolean).slice(0, count);

const stamp = new Date().toISOString().replace(/[-:]/g, "").replace("T", "_").slice(0, 15);
const outDir = path.resolve(process.env.FLOW_OUT || `../out/flow_ui_agent_live${count}_${stamp}`);
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, "prompts.txt"), prompts.join("\n"));

const port = Number(process.env.SA_PORT || 8787);
const ws = new WebSocket(`ws://127.0.0.1:${port}/ws`);
const t0 = Date.now();
const results = [];
let done = false;
const log = (s) => { const line = `${((Date.now() - t0) / 1000).toFixed(1)}s ${s}`; console.log(line); fs.appendFileSync(path.join(outDir, "run.log"), line + "\n"); };
ws.on("message", (data) => {
  let msg;
  try { msg = JSON.parse(String(data)); } catch { return; }
  if (!["BATCH_PROGRESS", "PROMPT_RESULT", "GENERATE_DONE", "status"].includes(msg.type) && !msg.generateError) return;
  fs.appendFileSync(path.join(outDir, "events.jsonl"), JSON.stringify(msg) + "\n");
  if (msg.type === "PROMPT_RESULT") {
    results.push(msg);
    log(JSON.stringify({ index: msg.index, status: msg.status, match: msg.agentMatch, path: msg.path, error: msg.error && String(msg.error).slice(0, 160) }));
  } else if (msg.type === "status" || msg.generateError) {
    log(`status: ${String(msg.message || msg.generateError).slice(0, 200)}`);
  }
  if (msg.type === "GENERATE_DONE") done = true;
});
await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
log(`SENDING ${prompts.length} prompts (median ${prompts.map((p) => p.length).sort((a, b) => a - b)[prompts.length >> 1]} chars) to ${accountId} -> ${outDir}`);
ws.send(JSON.stringify({
  type: "GENERATE",
  prompts: prompts.join("\n"),
  accountIds: [accountId],
  settings: {
    mediaKind: "image", model: "BELUGA", aspectRatio: "IMAGE_ASPECT_RATIO_LANDSCAPE", imageCount: 1, autoDownload: true,
    outputDir: outDir, folder: "batch", generationMode: "agent", agentViaUi: true, agentFallback: false,
    delayMin: 2, delayMax: 4, refreshFrequency: 50,
  },
}));
const deadline = Date.now() + 25 * 60 * 1000;
while (!done && Date.now() < deadline) await new Promise((r) => setTimeout(r, 1000));
ws.close();
const ok = results.filter((r) => r.status === "done");
log(`SUMMARY done=${done} saved=${ok.length}/${prompts.length} elapsed=${((Date.now() - t0) / 1000).toFixed(0)}s`);
process.exit(0);
