import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const PROFILE = "/Users/muhammadnabil/.semantic-automator-desktop/profiles/0edfb022-bcda-4691-a7dc-4a8d9a4c4b0d";
const RESULTS_FILE = "/private/tmp/claude-501/-Users-muhammadnabil-Downloads-video-generator-main/eaed1ba5-c127-43c6-acf7-244ff63af7ec/scratchpad/variant-results.json";

// One variable changed at a time from the CURRENT accounts.js production baseline:
//   headless:false, viewport 1280x900,
//   args: ["--disable-blink-features=AutomationControlled","--no-first-run","--no-default-browser-check"]
//   ignoreDefaultArgs: ["--enable-automation","--metrics-recording-only"]
//   channel: "chrome" (darwin)
const BASE_ARGS = ["--disable-blink-features=AutomationControlled", "--no-first-run", "--no-default-browser-check"];
const BASE_IGNORE = ["--enable-automation", "--metrics-recording-only"];

const VARIANTS = {
  v0_baseline: { args: BASE_ARGS, ignoreDefaultArgs: BASE_IGNORE, channel: "chrome", persistent: true },
  v1_restore_metrics_recording_only: { args: BASE_ARGS, ignoreDefaultArgs: ["--enable-automation"], channel: "chrome", persistent: true },
  v2_restore_enable_automation: { args: BASE_ARGS, ignoreDefaultArgs: ["--metrics-recording-only"], channel: "chrome", persistent: true },
  v3_no_ignoreDefaultArgs: { args: BASE_ARGS, ignoreDefaultArgs: [], channel: "chrome", persistent: true },
  v4_no_channel_chrome: { args: BASE_ARGS, ignoreDefaultArgs: BASE_IGNORE, channel: undefined, persistent: true },
  v5_no_disable_blink_automation: { args: ["--no-first-run", "--no-default-browser-check"], ignoreDefaultArgs: BASE_IGNORE, channel: "chrome", persistent: true },
  v6_add_no_sandbox: { args: [...BASE_ARGS, "--no-sandbox"], ignoreDefaultArgs: BASE_IGNORE, channel: "chrome", persistent: true },
  v7_add_disable_dev_shm: { args: [...BASE_ARGS, "--disable-dev-shm-usage"], ignoreDefaultArgs: BASE_IGNORE, channel: "chrome", persistent: true },
  v8_add_disable_extensions: { args: [...BASE_ARGS, "--disable-extensions"], ignoreDefaultArgs: BASE_IGNORE, channel: "chrome", persistent: true },
  v9_add_disable_sync: { args: [...BASE_ARGS, "--disable-sync"], ignoreDefaultArgs: BASE_IGNORE, channel: "chrome", persistent: true },
  v10_non_persistent_context: { args: BASE_ARGS, ignoreDefaultArgs: BASE_IGNORE, channel: "chrome", persistent: false },
};

const variantName = process.argv[2];
const variant = VARIANTS[variantName];
if (!variant) {
  console.error("Unknown variant. Options:", Object.keys(VARIANTS).join(", "));
  process.exit(1);
}

const launchOpts = {
  headless: false,
  viewport: { width: 1280, height: 900 },
  args: variant.args,
  ignoreDefaultArgs: variant.ignoreDefaultArgs,
};
if (variant.channel) launchOpts.channel = variant.channel;

console.log(`[variant-test] running ${variantName}`);
console.log(`[variant-test] args:`, variant.args);
console.log(`[variant-test] ignoreDefaultArgs:`, variant.ignoreDefaultArgs);
console.log(`[variant-test] channel:`, variant.channel || "(bundled chromium)");
console.log(`[variant-test] persistent:`, variant.persistent);

let context, page, browser;
const headerObservations = [];

function recordHeaders(req) {
  try {
    const url = req.url();
    if (!/\.google\.com\//.test(url)) return;
    req.allHeaders().then((h) => {
      headerObservations.push({
        url: (() => { try { const u = new URL(url); return u.hostname + u.pathname; } catch { return "?"; } })(),
        xClientDataPresent: !!h["x-client-data"],
        xClientDataLength: h["x-client-data"] ? h["x-client-data"].length : null,
      });
    }).catch(() => {});
  } catch {}
}

try {
  if (variant.persistent) {
    context = await chromium.launchPersistentContext(PROFILE, launchOpts);
    page = context.pages()[0] || (await context.newPage());
  } else {
    browser = await chromium.launch(launchOpts);
    context = await browser.newContext();
    page = await context.newPage();
  }

  page.on("request", recordHeaders);

  await page.goto("https://www.google.com/", { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForTimeout(3000);
  // A second passive google-domain navigation for more header samples
  await page.goto("https://myaccount.google.com/", { waitUntil: "domcontentloaded", timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(2000);

  const anyPresent = headerObservations.some((o) => o.xClientDataPresent);
  const result = {
    variant: variantName,
    args: variant.args,
    ignoreDefaultArgs: variant.ignoreDefaultArgs,
    channel: variant.channel || null,
    persistent: variant.persistent,
    observationCount: headerObservations.length,
    xClientDataPresentAnywhere: anyPresent,
    sampleObservations: headerObservations.slice(0, 5),
  };

  let existing = [];
  try { existing = JSON.parse(fs.readFileSync(RESULTS_FILE, "utf8")); } catch {}
  existing.push(result);
  fs.writeFileSync(RESULTS_FILE, JSON.stringify(existing, null, 2));

  console.log(`[variant-test] RESULT: x-client-data present anywhere = ${anyPresent} (${headerObservations.length} google.com requests observed)`);
} finally {
  if (context) await context.close().catch(() => {});
  if (browser) await browser.close().catch(() => {});
}
console.log("[variant-test] done");
