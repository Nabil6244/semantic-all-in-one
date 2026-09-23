import { openAccountBrowser, closeAccountBrowser } from "./lib/accounts.js";
import { flowGoto, urls, waitForFlowReady } from "./lib/flow-api.js";
import { generateImageViaFlowUI } from "./lib/flow-ui-experiment.js";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const ACCOUNT_ID = "0edfb022-bcda-4691-a7dc-4a8d9a4c4b0d";
const PROJECT_ID = "0d9a9a2f-d36f-4742-8949-9f9ec4d0a5d5"; // existing test project, SAME page for all 10
const OUT_DIR = "/private/tmp/claude-501/-Users-muhammadnabil-Downloads-video-generator-main/eaed1ba5-c127-43c6-acf7-244ff63af7ec/scratchpad/ten-generation-validation";
fs.mkdirSync(OUT_DIR, { recursive: true });

function sha256File(p) {
  return crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex").slice(0, 16);
}

async function isImageModeAlreadySelected(page) {
  return page.evaluate(() => {
    const radios = Array.from(document.querySelectorAll('button[role="radio"]'));
    const imageRadio = radios.find((r) => (r.textContent || "").includes("Image"));
    if (!imageRadio) return null; // panel not open / not visible right now
    return imageRadio.getAttribute("aria-checked") === "true";
  }).catch(() => null);
}

console.log("[10gen] opening account browser");
const { page } = await openAccountBrowser(ACCOUNT_ID);

console.log("[10gen] navigating to existing test project (SAME page for all 10 generations)");
await flowGoto(page, urls.flowProject(PROJECT_ID), "ten-generation-validation", { waitUntil: "domcontentloaded", timeout: 60000 });
await waitForFlowReady(page);
await page.waitForTimeout(3000);

const prompts = [
  "a wooden chair on a porch",
  "a striped cat sleeping on a windowsill",
  "a cup of coffee on a marble counter",
  "a lighthouse on a rocky coast",
  "a pair of sneakers on grass",
  "a stack of books on a desk",
  "a hot air balloon over hills",
  "a bowl of fruit on a table",
  "a vintage bicycle in a park",
  "a wooden boat on calm water",
];

const results = [];
const allPathnamesSoFar = new Set();
const allHashesSoFar = new Set();

for (let i = 0; i < prompts.length; i++) {
  const genNum = i + 1;
  console.log(`\n[10gen] === generation ${genNum}/10 ===`);

  // Best-effort pre-check: is the settings panel currently showing Image already selected?
  // (Panel may not be open at all between generations — that's expected/normal, reported as null.)
  const imageModeAlreadySelected = await isImageModeAlreadySelected(page);

  const startedAt = Date.now();
  let genResult;
  try {
    genResult = await generateImageViaFlowUI(page, prompts[i], {
      outputDir: OUT_DIR,
      mode: "image",
      generationTimeoutMs: 120000,
    });
  } catch (e) {
    genResult = { ok: false, savedPath: null, mediaUrl: null, diag: { outcome: "thrown_exception", error: e?.message || String(e), stage: "unknown" } };
  }
  const durationMs = Date.now() - startedAt;

  const mediaPathname = genResult.mediaUrl ? (() => { try { return new URL(genResult.mediaUrl).pathname; } catch { return null; } })() : null;

  let fileSize = null;
  let fileHash = null;
  let isDuplicatePathname = false;
  let isDuplicateHash = false;
  if (genResult.ok && genResult.savedPath) {
    try {
      fileSize = fs.statSync(genResult.savedPath).size;
      fileHash = sha256File(genResult.savedPath);
      isDuplicatePathname = mediaPathname ? allPathnamesSoFar.has(mediaPathname) : false;
      isDuplicateHash = fileHash ? allHashesSoFar.has(fileHash) : false;
      if (mediaPathname) allPathnamesSoFar.add(mediaPathname);
      if (fileHash) allHashesSoFar.add(fileHash);
    } catch (e) {
      fileSize = null;
    }
  }

  const entry = {
    generationNumber: genNum,
    imageModeAlreadySelectedBefore: imageModeAlreadySelected,
    outcome: genResult.diag?.outcome || "unknown",
    stage: genResult.diag?.stage || null,
    error: genResult.diag?.error || null,
    preExistingMediaCount: genResult.diag?.preExistingMediaCount ?? null,
    detectedMediaPathname: mediaPathname,
    genuinelyNew: genResult.ok ? !isDuplicatePathname : null,
    fileSizeBytes: fileSize,
    sha256_16: fileHash,
    isDuplicatePathname,
    isDuplicateHash,
    totalDurationMs: durationMs,
  };
  results.push(entry);
  console.log(JSON.stringify(entry, null, 2));

  fs.writeFileSync(path.join(OUT_DIR, "results-partial.json"), JSON.stringify(results, null, 2));
  // No retry on failure — proceed to the next prompt regardless.
}

const successes = results.filter((r) => r.outcome === "success");
const modeSelectFailures = results.filter((r) => r.stage === "selecting_mode");
const timeouts = results.filter((r) => r.outcome === "timeout_no_media_detected");
const staleDetections = results.filter((r) => r.genuinelyNew === false);
const duplicates = results.filter((r) => r.isDuplicatePathname || r.isDuplicateHash);
const durations = successes.map((r) => r.totalDurationMs).sort((a, b) => a - b);
const avg = durations.length ? durations.reduce((a, b) => a + b, 0) / durations.length : null;
const median = durations.length ? durations[Math.floor(durations.length / 2)] : null;

const summary = {
  totalGenerations: results.length,
  successes: successes.length,
  imageModeSelectorFailures: modeSelectFailures.length,
  timeoutNoMediaDetected: timeouts.length,
  staleMediaDetections: staleDetections.length,
  duplicateOutputs: duplicates.length,
  averageSuccessfulDurationMs: avg,
  medianSuccessfulDurationMs: median,
  failurePatterns: results.filter((r) => r.outcome !== "success").map((r) => ({ generationNumber: r.generationNumber, outcome: r.outcome, stage: r.stage, error: r.error })),
  fullResults: results,
};

fs.writeFileSync(path.join(OUT_DIR, "summary.json"), JSON.stringify(summary, null, 2));
console.log("\n[10gen] FULL SUMMARY:\n" + JSON.stringify(summary, null, 2));

console.log("[10gen] closing");
await closeAccountBrowser(ACCOUNT_ID);
console.log("[10gen] done");
