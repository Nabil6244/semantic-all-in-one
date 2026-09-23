import { openAccountBrowser, closeAccountBrowser } from "./lib/accounts.js";
import { flowGoto, urls, waitForFlowReady } from "./lib/flow-api.js";
import { generateImageViaFlowUI } from "./lib/flow-ui-experiment.js";
import fs from "node:fs";
import path from "node:path";

const ACCOUNT_ID = "0edfb022-bcda-4691-a7dc-4a8d9a4c4b0d";
const PROJECT_ID = "0d9a9a2f-d36f-4742-8949-9f9ec4d0a5d5";
const OUT_DIR = "/private/tmp/claude-501/-Users-muhammadnabil-Downloads-video-generator-main/eaed1ba5-c127-43c6-acf7-244ff63af7ec/scratchpad/scenario-a";
fs.mkdirSync(OUT_DIR, { recursive: true });

console.log("[scenario-a] opening account browser");
const { page } = await openAccountBrowser(ACCOUNT_ID);
await flowGoto(page, urls.flowProject(PROJECT_ID), "scenario-a", { waitUntil: "domcontentloaded", timeout: 60000 });
await waitForFlowReady(page);
await page.waitForTimeout(3000);

const prompts = [
  "a red kettle on a stove",
  "a folded map on a table",
  "a clay pot with a plant",
  "a pair of glasses on a book",
  "a candle burning on a shelf",
  "a woven basket of oranges",
];

const results = [];
for (let i = 0; i < prompts.length; i++) {
  const genNum = i + 1;
  console.log(`[scenario-a] generation ${genNum}/6`);
  const startedAt = Date.now();
  let genResult;
  try {
    genResult = await generateImageViaFlowUI(page, prompts[i], { outputDir: OUT_DIR, mode: "image", generationTimeoutMs: 120000 });
  } catch (e) {
    genResult = { ok: false, diag: { outcome: "thrown_exception", error: e?.message || String(e), stage: "unknown" } };
  }
  const entry = {
    generationNumber: genNum,
    outcome: genResult.diag?.outcome,
    stage: genResult.diag?.stage,
    error: genResult.diag?.error || null,
    durationMs: Date.now() - startedAt,
    mediaUrl: genResult.mediaUrl || null,
  };
  results.push(entry);
  console.log(JSON.stringify(entry));
}

const successes = results.filter((r) => r.outcome === "success").length;
const modeFailures = results.filter((r) => r.stage === "selecting_mode").length;
const summary = { totalGenerations: results.length, successes, modeSelectFailures: modeFailures, results };
fs.writeFileSync(path.join(OUT_DIR, "summary.json"), JSON.stringify(summary, null, 2));
console.log("\n[scenario-a] SUMMARY:\n" + JSON.stringify(summary, null, 2));

await closeAccountBrowser(ACCOUNT_ID);
console.log("[scenario-a] done");
