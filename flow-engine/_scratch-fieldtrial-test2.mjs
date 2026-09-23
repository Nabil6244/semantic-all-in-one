import { chromium } from "playwright";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";

const FRESH_PROFILE = path.join(os.tmpdir(), "flow-fieldtrial-test2-" + Date.now());
fs.mkdirSync(FRESH_PROFILE, { recursive: true });

const launchOpts = {
  headless: false,
  viewport: { width: 1280, height: 900 },
  args: ["--disable-blink-features=AutomationControlled", "--no-first-run", "--no-default-browser-check"],
  ignoreDefaultArgs: [
    "--enable-automation",
    "--metrics-recording-only",
    "--disable-field-trial-config",
    "--disable-background-networking",
  ],
  channel: "chrome",
};

console.log("[fieldtrial-test2] fresh profile:", FRESH_PROFILE);
console.log("[fieldtrial-test2] ignoreDefaultArgs:", launchOpts.ignoreDefaultArgs);

const context = await chromium.launchPersistentContext(FRESH_PROFILE, launchOpts);
const page = context.pages()[0] || (await context.newPage());

function grepLines(text, patterns) {
  return text.split("\n").filter((l) => patterns.some((p) => p.test(l))).map((l) => l.trim()).filter(Boolean);
}

console.log("[fieldtrial-test2] checking chrome://version immediately");
await page.goto("chrome://version", { waitUntil: "domcontentloaded" });
await page.waitForTimeout(1000);
const versionTextEarly = await page.evaluate(() => document.body.innerText);
const earlyRelevant = grepLines(versionTextEarly, [/variations/i, /field.?trial/i, /background.?networking/i, /command line/i]);
const earlyHasDisableFT = /--disable-field-trial-config/.test(versionTextEarly);
const earlyHasDisableBGNet = /--disable-background-networking/.test(versionTextEarly);
console.log("[fieldtrial-test2] EARLY relevant lines:\n" + earlyRelevant.join("\n"));

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

console.log("[fieldtrial-test2] re-checking chrome://version after observation window");
await page.goto("chrome://version", { waitUntil: "domcontentloaded" });
await page.waitForTimeout(1000);
const versionTextLate = await page.evaluate(() => document.body.innerText);
const lateRelevant = grepLines(versionTextLate, [/variations/i, /field.?trial/i, /background.?networking/i, /command line/i]);
const lateHasDisableFT = /--disable-field-trial-config/.test(versionTextLate);
const lateHasDisableBGNet = /--disable-background-networking/.test(versionTextLate);
const lateHasSeedVersionFlag = /--variations-seed-version=/.test(versionTextLate);
console.log("[fieldtrial-test2] LATE relevant lines:\n" + lateRelevant.join("\n"));

console.log("[fieldtrial-test2] closing");
await context.close();

function fileStat(p) {
  try { return fs.statSync(p).size; } catch { return null; }
}
const seedSize = fileStat(path.join(FRESH_PROFILE, "VariationsSeedV2"));
const safeSeedSize = fileStat(path.join(FRESH_PROFILE, "VariationsSafeSeedV2"));
const featureStateSize = fileStat(path.join(FRESH_PROFILE, "ChromeFeatureState"));

const present = observations.filter((o) => o.present);
const distinctLengths = [...new Set(present.map((o) => o.length))];
const distinctHashes = [...new Set(present.map((o) => o.hash))];

const result = {
  freshProfile: FRESH_PROFILE,
  early: { relevantLines: earlyRelevant, disableFieldTrialConfigPresent: earlyHasDisableFT, disableBackgroundNetworkingPresent: earlyHasDisableBGNet },
  late: { relevantLines: lateRelevant, disableFieldTrialConfigPresent: lateHasDisableFT, disableBackgroundNetworkingPresent: lateHasDisableBGNet, hasVariationsSeedVersionFlag: lateHasSeedVersionFlag },
  files: { VariationsSeedV2: seedSize, VariationsSafeSeedV2: safeSeedSize, ChromeFeatureState: featureStateSize },
  xClientData: {
    totalObservations: observations.length,
    presentCount: present.length,
    distinctLengths,
    distinctHashCount: distinctHashes.length,
    hashes: distinctHashes,
  },
};

fs.writeFileSync(
  "/private/tmp/claude-501/-Users-muhammadnabil-Downloads-video-generator-main/eaed1ba5-c127-43c6-acf7-244ff63af7ec/scratchpad/fieldtrial-test2-results.json",
  JSON.stringify(result, null, 2)
);
console.log(JSON.stringify(result, null, 2));

fs.rmSync(FRESH_PROFILE, { recursive: true, force: true });
console.log("[fieldtrial-test2] done, temp profile removed");
