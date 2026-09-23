import { chromium } from "playwright";
import fs from "node:fs";
import crypto from "node:crypto";

const PROFILE = "/Users/muhammadnabil/.semantic-automator-desktop/profiles/0edfb022-bcda-4691-a7dc-4a8d9a4c4b0d";
const RESULTS_FILE = "/private/tmp/claude-501/-Users-muhammadnabil-Downloads-video-generator-main/eaed1ba5-c127-43c6-acf7-244ff63af7ec/scratchpad/v4-extended-results.json";

// Exactly v4's config: bundled Chromium (no channel), same args/ignoreDefaultArgs, same profile.
const launchOpts = {
  headless: false,
  viewport: { width: 1280, height: 900 },
  args: ["--disable-blink-features=AutomationControlled", "--no-first-run", "--no-default-browser-check"],
  ignoreDefaultArgs: ["--enable-automation", "--metrics-recording-only"],
};

const observations = [];
const startedAt = Date.now();

function hashValue(v) {
  return crypto.createHash("sha256").update(v).digest("hex").slice(0, 12);
}

function domainCategory(url) {
  try {
    const u = new URL(url);
    return u.hostname;
  } catch {
    return "?";
  }
}

function recordHeaders(req) {
  try {
    const url = req.url();
    if (!/\.google\.com\//.test(url) && !/^https:\/\/google\.com\//.test(url)) return;
    req.allHeaders().then((h) => {
      const xcd = h["x-client-data"];
      observations.push({
        tMs: Date.now() - startedAt,
        domain: domainCategory(url),
        xClientDataPresent: !!xcd,
        xClientDataLength: xcd ? xcd.length : null,
        xClientDataHash: xcd ? hashValue(xcd) : null,
      });
    }).catch(() => {});
  } catch {}
}

console.log("[v4-extended] launching bundled Chromium, no channel, same profile/args as v4");
const context = await chromium.launchPersistentContext(PROFILE, launchOpts);
const page = context.pages()[0] || (await context.newPage());
page.on("request", recordHeaders);

const urls = [
  "https://www.google.com/",
  "https://myaccount.google.com/",
  "https://www.google.com/search?q=test",
  "https://mail.google.com/",
  "https://drive.google.com/",
  "https://www.google.com/",
  "https://myaccount.google.com/",
];

const DURATION_MS = 3 * 60 * 1000; // ~3 minutes
const deadline = Date.now() + DURATION_MS;
let i = 0;
while (Date.now() < deadline) {
  const url = urls[i % urls.length];
  i++;
  try {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 20000 });
  } catch (e) {
    console.log("[v4-extended] nav error (continuing):", e.message);
  }
  await page.waitForTimeout(8000);
  const elapsedS = Math.round((Date.now() - startedAt) / 1000);
  const presentCount = observations.filter((o) => o.xClientDataPresent).length;
  console.log(`[v4-extended] t=${elapsedS}s nav#${i} url=${url} totalObs=${observations.length} presentSoFar=${presentCount}`);
}

await context.close().catch(() => {});

fs.writeFileSync(RESULTS_FILE, JSON.stringify(observations, null, 2));

const present = observations.filter((o) => o.xClientDataPresent);
const absent = observations.filter((o) => !o.xClientDataPresent);
console.log("\n[v4-extended] SUMMARY");
console.log("total observations:", observations.length);
console.log("present:", present.length, "absent:", absent.length);
if (present.length) {
  const lengths = [...new Set(present.map((o) => o.xClientDataLength))];
  const hashes = [...new Set(present.map((o) => o.xClientDataHash))];
  console.log("distinct lengths seen:", lengths);
  console.log("distinct value-hashes seen:", hashes.length, hashes);
  console.log("first present at tMs:", present[0].tMs, "domain:", present[0].domain);
  console.log("last present at tMs:", present[present.length - 1].tMs);
}
console.log("[v4-extended] done");
