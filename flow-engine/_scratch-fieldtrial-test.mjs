import { chromium } from "playwright";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";

const FRESH_PROFILE = path.join(os.tmpdir(), "flow-fieldtrial-test-" + Date.now());
fs.mkdirSync(FRESH_PROFILE, { recursive: true });

// Exact production baseline from accounts.js's launchOpts(), with ONLY
// --disable-field-trial-config added to ignoreDefaultArgs. Nothing else touched.
const launchOpts = {
  headless: false,
  viewport: { width: 1280, height: 900 },
  args: ["--disable-blink-features=AutomationControlled", "--no-first-run", "--no-default-browser-check"],
  ignoreDefaultArgs: ["--enable-automation", "--metrics-recording-only", "--disable-field-trial-config"],
  channel: "chrome",
};

console.log("[fieldtrial-test] fresh profile:", FRESH_PROFILE);
console.log("[fieldtrial-test] ignoreDefaultArgs:", launchOpts.ignoreDefaultArgs);

const context = await chromium.launchPersistentContext(FRESH_PROFILE, launchOpts);
const page = context.pages()[0] || (await context.newPage());

console.log("[fieldtrial-test] checking chrome://version immediately");
await page.goto("chrome://version", { waitUntil: "domcontentloaded" });
await page.waitForTimeout(1000);
const versionTextEarly = await page.evaluate(() => document.body.innerText);

function extractField(text, label) {
  const line = text.split("\n").find((l) => l.trim().startsWith(label));
  return line ? line.replace(label, "").trim() : null;
}

const earlySeedType = extractField(versionTextEarly, "Variations Seed Type");
const earlySource = extractField(versionTextEarly, "Variations Source");
const cmdLine = text => (text.split("\n").find(l => l.trim().startsWith("Command Line")) || "");
const earlyHasDisableFT = /--disable-field-trial-config/.test(versionTextEarly);

console.log("[fieldtrial-test] early Variations Seed Type:", earlySeedType);
console.log("[fieldtrial-test] early Variations Source:", earlySource);
console.log("[fieldtrial-test] --disable-field-trial-config still present in cmdline?", earlyHasDisableFT);

// Passive observation window on ordinary google.com pages, collecting x-client-data presence.
const observations = [];
function hashValue(v) { return crypto.createHash("sha256").update(v).digest("hex").slice(0, 12); }
page.on("request", (req) => {
  const url = req.url();
  if (!/\.google\.com\//.test(url)) return;
  req.allHeaders().then((h) => {
    const xcd = h["x-client-data"];
    observations.push({ present: !!xcd, length: xcd ? xcd.length : null, hash: xcd ? hashValue(xcd) : null });
  }).catch(() => {});
});

const urls = ["https://www.google.com/", "https://myaccount.google.com/", "https://www.google.com/search?q=test"];
const DURATION_MS = 90 * 1000;
const deadline = Date.now() + DURATION_MS;
let i = 0;
while (Date.now() < deadline) {
  const url = urls[i % urls.length];
  i++;
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 20000 }).catch((e) => console.log("nav err:", e.message));
  await page.waitForTimeout(8000);
}

console.log("[fieldtrial-test] re-checking chrome://version after observation window");
await page.goto("chrome://version", { waitUntil: "domcontentloaded" });
await page.waitForTimeout(1000);
const versionTextLate = await page.evaluate(() => document.body.innerText);
const lateSeedType = extractField(versionTextLate, "Variations Seed Type");
const lateSource = extractField(versionTextLate, "Variations Source");
const lateHasSeedVersionFlag = /--variations-seed-version=/.test(versionTextLate);
const lateHasDisableFT = /--disable-field-trial-config/.test(versionTextLate);

console.log("[fieldtrial-test] closing");
await context.close();

function fileStat(p) {
  try { const s = fs.statSync(p); return s.size; } catch { return null; }
}
const seedSize = fileStat(path.join(FRESH_PROFILE, "VariationsSeedV2"));
const safeSeedSize = fileStat(path.join(FRESH_PROFILE, "VariationsSafeSeedV2"));
const featureStateSize = fileStat(path.join(FRESH_PROFILE, "ChromeFeatureState"));

const present = observations.filter((o) => o.present);
const distinctLengths = [...new Set(present.map((o) => o.length))];
const distinctHashes = [...new Set(present.map((o) => o.hash))];

const result = {
  freshProfile: FRESH_PROFILE,
  early: { seedType: earlySeedType, source: earlySource, disableFieldTrialConfigInCmdline: earlyHasDisableFT },
  late: { seedType: lateSeedType, source: lateSource, hasVariationsSeedVersionFlag: lateHasSeedVersionFlag, disableFieldTrialConfigInCmdline: lateHasDisableFT },
  files: { VariationsSeedV2: seedSize, VariationsSafeSeedV2: safeSeedSize, ChromeFeatureState: featureStateSize },
  xClientData: {
    totalObservations: observations.length,
    presentCount: present.length,
    distinctLengths,
    distinctHashCount: distinctHashes.length,
  },
};

fs.writeFileSync(
  "/private/tmp/claude-501/-Users-muhammadnabil-Downloads-video-generator-main/eaed1ba5-c127-43c6-acf7-244ff63af7ec/scratchpad/fieldtrial-test-results.json",
  JSON.stringify(result, null, 2)
);
console.log(JSON.stringify(result, null, 2));

// Cleanup the fresh temp profile (this is our own throwaway test dir, safe to remove)
fs.rmSync(FRESH_PROFILE, { recursive: true, force: true });
console.log("[fieldtrial-test] done, temp profile removed");
