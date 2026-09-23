import { openAccountBrowser, gotoFlow, closeAccountBrowser } from "./lib/accounts.js";
import { flowGoto, urls, waitForFlowReady } from "./lib/flow-api.js";
import { generateImageViaFlowUI } from "./lib/flow-ui-experiment.js";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const ACCOUNT_ID = "0edfb022-bcda-4691-a7dc-4a8d9a4c4b0d";
const PROJECT_ID = "0d9a9a2f-d36f-4742-8949-9f9ec4d0a5d5"; // existing test project, reused, SAME page across all 3
const OUT_DIR = "/private/tmp/claude-501/-Users-muhammadnabil-Downloads-video-generator-main/eaed1ba5-c127-43c6-acf7-244ff63af7ec/scratchpad/multi-image-batch-test";
fs.mkdirSync(OUT_DIR, { recursive: true });

function sha256File(p) {
  return crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex").slice(0, 16);
}

async function countExistingFlowContentMedia(page) {
  return page.evaluate(() => {
    const els = Array.from(document.querySelectorAll("img[src], video[src]"));
    return els.filter((el) => el.src && el.src.includes("flow-content.google")).length;
  });
}

console.log("[multi-batch] opening account browser");
const { page } = await openAccountBrowser(ACCOUNT_ID);

console.log("[multi-batch] navigating to existing test project (SAME page reused for all 3 generations)");
await flowGoto(page, urls.flowProject(PROJECT_ID), "multi-image-batch-test", { waitUntil: "domcontentloaded", timeout: 60000 });
await waitForFlowReady(page);
await page.waitForTimeout(3000);

const prompts = [
  "a red bicycle leaning against a brick wall",
  "a green apple sitting on a wooden table",
  "a blue kite flying in a cloudy sky",
];

const results = [];
for (let i = 0; i < prompts.length; i++) {
  const genNum = i + 1;
  console.log(`\n[multi-batch] === generation ${genNum}/3 ===`);
  const preCount = await countExistingFlowContentMedia(page);
  console.log(`[multi-batch] pre-existing flow-content.google media count: ${preCount}`);

  const startedAt = Date.now();
  const genResult = await generateImageViaFlowUI(page, prompts[i], {
    outputDir: OUT_DIR,
    mode: "image",
    generationTimeoutMs: 120000,
  });
  const durationMs = Date.now() - startedAt;

  const mediaPathname = genResult.mediaUrl ? (() => { try { return new URL(genResult.mediaUrl).pathname; } catch { return null; } })() : null;

  let fileValid = null;
  let fileHash = null;
  if (genResult.ok && genResult.savedPath) {
    try {
      const stat = fs.statSync(genResult.savedPath);
      const buf = fs.readFileSync(genResult.savedPath).subarray(0, 8);
      const isPng = buf[0] === 0x89 && buf[1] === 0x50 && buf[2] === 0x4e && buf[3] === 0x47;
      fileValid = { sizeBytes: stat.size, isPng };
      fileHash = sha256File(genResult.savedPath);
    } catch (e) {
      fileValid = { error: e.message };
    }
  }

  const entry = {
    generationNumber: genNum,
    preExistingFlowContentMediaCount: preCount,
    outcome: genResult.diag?.outcome,
    detectedMediaPathname: mediaPathname,
    generationDurationMs: durationMs,
    fileValid,
    fileHash,
  };
  results.push(entry);
  console.log(JSON.stringify(entry, null, 2));
}

// Distinctness check: are all 3 detected pathnames different? Are all 3 file hashes different?
const pathnames = results.map((r) => r.detectedMediaPathname).filter(Boolean);
const distinctPathnames = new Set(pathnames);
const hashes = results.map((r) => r.fileHash).filter(Boolean);
const distinctHashes = new Set(hashes);

const summary = {
  results,
  allThreeSucceeded: results.every((r) => r.outcome === "success"),
  distinctPathnameCount: distinctPathnames.size,
  totalGenerations: results.length,
  distinctHashCount: distinctHashes.size,
  allOutputsDistinct: distinctPathnames.size === results.length && distinctHashes.size === results.length,
  anyTimeout: results.some((r) => r.outcome === "timeout_no_media_detected"),
};

fs.writeFileSync(path.join(OUT_DIR, "summary.json"), JSON.stringify(summary, null, 2));
console.log("\n[multi-batch] FULL SUMMARY:\n" + JSON.stringify(summary, null, 2));

console.log("[multi-batch] closing");
await closeAccountBrowser(ACCOUNT_ID);
console.log("[multi-batch] done");
