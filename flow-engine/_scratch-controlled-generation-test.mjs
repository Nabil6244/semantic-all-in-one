import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { flowGoto, urls, waitForFlowReady, generateOneImage, downloadMedia } from "./lib/flow-api.js";

const PROFILE = "/Users/muhammadnabil/.semantic-automator-desktop/profiles/0edfb022-bcda-4691-a7dc-4a8d9a4c4b0d";
const PROJECT_ID = "0d9a9a2f-d36f-4742-8949-9f9ec4d0a5d5"; // existing test project, reused — no new project
const OUT_DIR = "/private/tmp/claude-501/-Users-muhammadnabil-Downloads-video-generator-main/eaed1ba5-c127-43c6-acf7-244ff63af7ec/scratchpad/controlled-generation-test";
fs.mkdirSync(OUT_DIR, { recursive: true });

// EXACT production launchOpts() from accounts.js, with ONLY these two extra
// ignoreDefaultArgs suppressions. accounts.js itself is untouched.
const launchOpts = {
  headless: false,
  viewport: { width: 1280, height: 900 },
  args: ["--disable-blink-features=AutomationControlled", "--no-first-run", "--no-default-browser-check"],
  ignoreDefaultArgs: ["--enable-automation", "--metrics-recording-only", "--disable-field-trial-config", "--disable-background-networking"],
  channel: "chrome",
};

function hashValue(v) { return crypto.createHash("sha256").update(v).digest("hex").slice(0, 12); }
function grepLines(text, patterns) {
  return text.split("\n").filter((l) => patterns.some((p) => p.test(l))).map((l) => l.trim()).filter(Boolean);
}

console.log("[controlled-test] launching with Variations fix applied");
const context = await chromium.launchPersistentContext(PROFILE, launchOpts);
const page = context.pages()[0] || (await context.newPage());

console.log("[controlled-test] checking active Variations state BEFORE generation");
await page.goto("chrome://version", { waitUntil: "domcontentloaded" });
await page.waitForTimeout(1000);
const versionText = await page.evaluate(() => document.body.innerText);
const variationsState = grepLines(versionText, [/variations/i]);
console.log("[controlled-test] Variations state:", variationsState);

// Capture x-client-data presence specifically on the ogiZ0b request.
let ogiZ0bXClientData = { present: false, length: null, hash: null };
page.on("requestfinished", async (req) => {
  try {
    const url = req.url();
    if (url.includes("/data/batchexecute") && url.includes("rpcids=ogiZ0b")) {
      const h = await req.allHeaders();
      const xcd = h["x-client-data"];
      ogiZ0bXClientData = { present: !!xcd, length: xcd ? xcd.length : null, hash: xcd ? hashValue(xcd) : null };
    }
  } catch {}
});

console.log("[controlled-test] navigating to existing test project (no new project)");
await flowGoto(page, urls.flowProject(PROJECT_ID), "controlled-generation-test", { waitUntil: "domcontentloaded", timeout: 60000 });
await waitForFlowReady(page);

console.log("[controlled-test] calling generateOneImage (direct RPC ogiZ0b) — ONE controlled attempt");
const prompt = "a single orange traffic cone on wet pavement";
let result = null;
let genError = null;
try {
  result = await generateOneImage(page, PROJECT_ID, prompt, { model: "NARWHAL", outputDir: OUT_DIR }, 0);
} catch (e) {
  genError = { name: e?.constructor?.name, message: e?.message };
}

console.log("[controlled-test] generation outcome:", result ? "SUCCESS" : "FAILURE", genError || "");

let downloadResult = null;
if (result && result.mediaId) {
  console.log("[controlled-test] attempting downstream media download");
  try {
    const destPath = path.join(OUT_DIR, `test-image-${Date.now()}.png`);
    await downloadMedia(page, result.mediaId, destPath, result.fifeUrl || null);
    const stat = fs.statSync(destPath);
    const buf = fs.readFileSync(destPath, { encoding: null }).subarray(0, 8);
    const isPng = buf[0] === 0x89 && buf[1] === 0x50 && buf[2] === 0x4e && buf[3] === 0x47;
    const isJpeg = buf[0] === 0xff && buf[1] === 0xd8;
    downloadResult = { ok: true, path: destPath, sizeBytes: stat.size, looksLikePng: isPng, looksLikeJpeg: isJpeg };
  } catch (e) {
    downloadResult = { ok: false, error: e?.message };
  }
}

console.log("[controlled-test] closing browser");
await context.close();

// Read the diagnostic log this run wrote (via existing writeGenerationDiagnostic machinery)
let diagEntry = null;
try {
  const diagPath = path.join(OUT_DIR, "generation-diagnostic.log");
  const lines = fs.readFileSync(diagPath, "utf8").trim().split("\n").filter(Boolean);
  diagEntry = JSON.parse(lines[lines.length - 1]);
} catch (e) {
  diagEntry = { error: "could not read diagnostic log: " + e.message };
}

const summary = {
  variationsStateBeforeGeneration: variationsState,
  ogiZ0bXClientData,
  generation: {
    outcome: result ? "success" : "failure",
    error: genError,
    mediaId: result ? result.mediaId : null,
    fifeUrlPresent: result ? !!result.fifeUrl : null,
  },
  download: downloadResult,
  diagnostic: diagEntry,
};

fs.writeFileSync(path.join(OUT_DIR, "summary.json"), JSON.stringify(summary, null, 2));
console.log("\n[controlled-test] FULL SUMMARY:\n" + JSON.stringify(summary, null, 2));
console.log("[controlled-test] done");
