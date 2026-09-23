import { openAccountBrowser, closeAccountBrowser } from "./lib/accounts.js";
import { execSync } from "node:child_process";
import fs from "node:fs";

const ACCOUNT_ID = "0edfb022-bcda-4691-a7dc-4a8d9a4c4b0d";
const OUT = "/private/tmp/claude-501/-Users-muhammadnabil-Downloads-video-generator-main/eaed1ba5-c127-43c6-acf7-244ff63af7ec/scratchpad/chrome-diagnostics.json";

console.log("[diag] opening automation account browser (production path)");
const { page } = await openAccountBrowser(ACCOUNT_ID);

await page.waitForTimeout(2000);

console.log("[diag] checking process command lines for variations-seed-version / field-trial-handle");
let psOut = "";
try {
  psOut = execSync(`ps aux | grep "${ACCOUNT_ID}" ; ps aux | grep -i "semantic-automator-desktop" `).toString();
} catch (e) {
  psOut = e.stdout ? e.stdout.toString() : "";
}
const hasSeedVersion = /variations-seed-version=/.test(psOut);
const hasFieldTrialHandle = /field-trial-handle=/.test(psOut);
const seedVersionMatch = psOut.match(/variations-seed-version=([^\s]+)/);

console.log("[diag] navigating to chrome://version");
await page.goto("chrome://version", { waitUntil: "domcontentloaded" }).catch((e) => console.log("nav error:", e.message));
await page.waitForTimeout(1000);
const versionText = await page.evaluate(() => document.body.innerText).catch(() => "");

console.log("[diag] navigating to chrome://policy");
await page.goto("chrome://policy", { waitUntil: "domcontentloaded" }).catch((e) => console.log("nav error:", e.message));
await page.waitForTimeout(1500);
const policyText = await page.evaluate(() => document.body.innerText).catch(() => "");

console.log("[diag] navigating to chrome://flags (checking for variations-related overrides only)");
await page.goto("chrome://flags", { waitUntil: "domcontentloaded" }).catch((e) => console.log("nav error:", e.message));
await page.waitForTimeout(1500);
// Only pull flags whose state is not "Default" - most flags panels support this via query, but as a
// passive fallback just note whether any non-default flags exist by checking the "Reset all" button state.
const flagsSummary = await page.evaluate(() => {
  const resetBtn = document.querySelector("#reset-all") || document.querySelector("[role='button'][aria-label*='Reset']");
  const experimentEls = document.querySelectorAll(".experiment");
  let nonDefaultCount = 0;
  experimentEls.forEach((el) => {
    const select = el.querySelector("select");
    if (select && select.selectedIndex !== 0) nonDefaultCount++;
  });
  return { totalExperiments: experimentEls.length, nonDefaultCount };
}).catch((e) => ({ error: e.message }));

console.log("[diag] closing browser");
await closeAccountBrowser(ACCOUNT_ID);

// Extract only variations/field-trial/metrics-relevant lines from chrome://version and chrome://policy,
// never full raw dumps (avoids any incidental sensitive content).
function grepLines(text, patterns) {
  return text.split("\n").filter((l) => patterns.some((p) => p.test(l))).map((l) => l.trim()).filter(Boolean);
}
const versionRelevant = grepLines(versionText, [/variations/i, /field.?trial/i, /command.?line/i, /profile path/i, /revision/i, /google chrome/i]);
const policyRelevant = grepLines(policyText, [/variations/i, /metrics/i, /field.?trial/i, /no policies/i, /policy name/i]);

const result = {
  processCommandLine: {
    hasVariationsSeedVersionFlag: hasSeedVersion,
    seedVersionValue: seedVersionMatch ? seedVersionMatch[1] : null,
    hasFieldTrialHandle: hasFieldTrialHandle,
  },
  chromeVersionRelevantLines: versionRelevant,
  chromePolicyRelevantLines: policyRelevant.slice(0, 30),
  chromePolicyLooksEmpty: /no policies/i.test(policyText),
  chromeFlagsSummary: flagsSummary,
};

fs.writeFileSync(OUT, JSON.stringify(result, null, 2));
console.log("[diag] written to", OUT);
console.log(JSON.stringify(result, null, 2));
