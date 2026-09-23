import { chromium } from "playwright";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";

const FRESH_PROFILE = path.join(os.tmpdir(), "flow-two-launch-test-" + Date.now());
fs.mkdirSync(FRESH_PROFILE, { recursive: true });

const OUT_DIR = "/private/tmp/claude-501/-Users-muhammadnabil-Downloads-video-generator-main/eaed1ba5-c127-43c6-acf7-244ff63af7ec/scratchpad/two-launch";
fs.mkdirSync(OUT_DIR, { recursive: true });

const launchOpts = {
  headless: false,
  viewport: { width: 1280, height: 900 },
  args: ["--disable-blink-features=AutomationControlled", "--no-first-run", "--no-default-browser-check"],
  ignoreDefaultArgs: ["--enable-automation", "--metrics-recording-only", "--disable-field-trial-config", "--disable-background-networking"],
  channel: "chrome",
};

function grepLines(text, patterns) {
  return text.split("\n").filter((l) => patterns.some((p) => p.test(l))).map((l) => l.trim()).filter(Boolean);
}
function hashValue(v) { return crypto.createHash("sha256").update(v).digest("hex").slice(0, 12); }
function fileStat(p) { try { return fs.statSync(p).size; } catch { return null; } }

async function runLaunch(label) {
  console.log(`\n[two-launch] === ${label} starting ===`);
  const context = await chromium.launchPersistentContext(FRESH_PROFILE, launchOpts);
  const page = context.pages()[0] || (await context.newPage());

  await page.goto("chrome://version", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1000);
  const versionTextEarly = await page.evaluate(() => document.body.innerText);
  fs.writeFileSync(path.join(OUT_DIR, `${label}-version-early.txt`), versionTextEarly);

  const observations = [];
  page.on("request", (req) => {
    const url = req.url();
    if (!/\.google\.com\//.test(url)) return;
    req.allHeaders().then((h) => {
      const xcd = h["x-client-data"];
      observations.push({ present: !!xcd, length: xcd ? xcd.length : null, hash: xcd ? hashValue(xcd) : null });
    }).catch(() => {});
  });

  const urls = ["https://www.google.com/", "https://myaccount.google.com/", "https://www.google.com/search?q=test"];
  const deadline = Date.now() + 90 * 1000;
  let i = 0;
  while (Date.now() < deadline) {
    const url = urls[i % urls.length];
    i++;
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 20000 }).catch((e) => console.log("nav err:", e.message));
    await page.waitForTimeout(8000);
  }

  await page.goto("chrome://version", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1000);
  const versionTextLate = await page.evaluate(() => document.body.innerText);
  fs.writeFileSync(path.join(OUT_DIR, `${label}-version-late.txt`), versionTextLate);

  console.log(`[two-launch] ${label} closing`);
  await context.close();

  const seedSize = fileStat(path.join(FRESH_PROFILE, "VariationsSeedV2"));
  const safeSeedSize = fileStat(path.join(FRESH_PROFILE, "VariationsSafeSeedV2"));
  const featureStateSize = fileStat(path.join(FRESH_PROFILE, "ChromeFeatureState"));

  const present = observations.filter((o) => o.present);
  const distinctLengths = [...new Set(present.map((o) => o.length))];
  const distinctHashes = [...new Set(present.map((o) => o.hash))];

  const relevantEarly = grepLines(versionTextEarly, [/variations/i, /field.?trial/i, /background.?networking/i]);
  const relevantLate = grepLines(versionTextLate, [/variations/i, /field.?trial/i, /background.?networking/i]);

  return {
    label,
    relevantEarly,
    relevantLate,
    filesAfterClose: { VariationsSeedV2: seedSize, VariationsSafeSeedV2: safeSeedSize, ChromeFeatureState: featureStateSize },
    xClientData: {
      totalObservations: observations.length,
      presentCount: present.length,
      distinctLengths,
      distinctHashCount: distinctHashes.length,
      hashes: distinctHashes,
    },
  };
}

// Check seed file state BEFORE launch 1 (should not exist yet - fresh profile)
console.log("[two-launch] seed file BEFORE launch 1:", fileStat(path.join(FRESH_PROFILE, "VariationsSeedV2")));

const launch1 = await runLaunch("launch1");

console.log("[two-launch] seed file AFTER launch 1 / BEFORE launch 2:", fileStat(path.join(FRESH_PROFILE, "VariationsSeedV2")));

const launch2 = await runLaunch("launch2");

const result = { freshProfile: FRESH_PROFILE, launch1, launch2 };
fs.writeFileSync(path.join(OUT_DIR, "summary.json"), JSON.stringify(result, null, 2));
console.log("\n[two-launch] FULL SUMMARY:\n" + JSON.stringify(result, null, 2));

// Preserve raw chrome://version text files in OUT_DIR (not deleted).
// Only the throwaway Chrome profile itself is removed.
fs.rmSync(FRESH_PROFILE, { recursive: true, force: true });
console.log("[two-launch] done, temp Chrome profile removed (raw version text preserved in", OUT_DIR, ")");
