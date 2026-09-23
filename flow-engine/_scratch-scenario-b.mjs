import { openAccountBrowser, closeAccountBrowser } from "./lib/accounts.js";
import { flowGoto, urls, waitForFlowReady, openOrCreateProject } from "./lib/flow-api.js";
import { generateImageViaFlowUI } from "./lib/flow-ui-experiment.js";
import fs from "node:fs";
import path from "node:path";

const ACCOUNT_A = "0edfb022-bcda-4691-a7dc-4a8d9a4c4b0d";
const PROJECT_A = "0d9a9a2f-d36f-4742-8949-9f9ec4d0a5d5"; // existing, reused
const ACCOUNT_B = "fcb499ce-f99b-41ec-87ee-5acc1c244357"; // second real account
const OUT_DIR = "/private/tmp/claude-501/-Users-muhammadnabil-Downloads-video-generator-main/eaed1ba5-c127-43c6-acf7-244ff63af7ec/scratchpad/scenario-b";
fs.mkdirSync(OUT_DIR, { recursive: true });

console.log("[scenario-b] opening BOTH account browsers concurrently — two independent Page/context instances");
const [{ page: pageA }, { page: pageB }] = await Promise.all([
  openAccountBrowser(ACCOUNT_A),
  openAccountBrowser(ACCOUNT_B),
]);

console.log("[scenario-b] navigating account A to its existing project");
await flowGoto(pageA, urls.flowProject(PROJECT_A), "scenario-b-A", { waitUntil: "domcontentloaded", timeout: 60000 });
await waitForFlowReady(pageA);

console.log("[scenario-b] account B: getting/creating its own project (no shared state with A)");
const projectB = await openOrCreateProject(pageB);
console.log("[scenario-b] account B projectId:", projectB);

await Promise.all([pageA.waitForTimeout(3000), pageB.waitForTimeout(3000)]);

// Helper: inspect whether the Settings panel / Image-mode radio is currently
// visible+checked on a given page, WITHOUT touching it — pure read, used to
// verify no cross-instance leakage (each page's DOM is independent by
// construction, but we confirm it empirically rather than assuming).
async function panelState(page) {
  return page.evaluate(() => {
    const radios = Array.from(document.querySelectorAll('button[role="radio"]'));
    const imageRadio = radios.find((r) => (r.textContent || "").includes("Image"));
    return {
      radioVisible: imageRadio ? imageRadio.offsetParent !== null : false,
      radioChecked: imageRadio ? imageRadio.getAttribute("aria-checked") === "true" : null,
    };
  }).catch(() => ({ error: true }));
}

const sequence = [
  { label: "A#1", page: pageA, prompt: "a small brass compass on a map" },
  { label: "B#1", page: pageB, prompt: "a striped beach towel on sand" },
  { label: "A#2", page: pageA, prompt: "a copper watering can near flowers" },
  { label: "B#2", page: pageB, prompt: "a paper boat floating in a puddle" },
  { label: "A#3", page: pageA, prompt: "a leather journal with a pen" },
  { label: "B#3", page: pageB, prompt: "a ceramic mug of hot cocoa" },
];

const results = [];
for (const step of sequence) {
  console.log(`\n[scenario-b] === ${step.label} ===`);
  const beforeState = await panelState(step.page);
  const startedAt = Date.now();
  let genResult;
  try {
    genResult = await generateImageViaFlowUI(step.page, step.prompt, { outputDir: OUT_DIR, mode: "image", generationTimeoutMs: 120000 });
  } catch (e) {
    genResult = { ok: false, diag: { outcome: "thrown_exception", error: e?.message || String(e), stage: "unknown" } };
  }
  const afterState = await panelState(step.page);
  const mediaPathname = genResult.mediaUrl ? (() => { try { return new URL(genResult.mediaUrl).pathname; } catch { return null; } })() : null;

  const entry = {
    step: step.label,
    account: step.page === pageA ? "A" : "B",
    beforeState,
    outcome: genResult.diag?.outcome,
    stage: genResult.diag?.stage,
    error: genResult.diag?.error || null,
    durationMs: Date.now() - startedAt,
    mediaPathname,
    afterState,
  };
  results.push(entry);
  console.log(JSON.stringify(entry, null, 2));
}

// Cross-instance leakage check: every media pathname must be unique across
// BOTH accounts (no account should ever receive the other's image), and
// account A's outputs should differ from account B's project scope.
const pathnames = results.map((r) => r.mediaPathname).filter(Boolean);
const distinctPathnames = new Set(pathnames);
const crossLeakageDetected = distinctPathnames.size !== pathnames.length;

const successesA = results.filter((r) => r.account === "A" && r.outcome === "success").length;
const successesB = results.filter((r) => r.account === "B" && r.outcome === "success").length;
const modeFailures = results.filter((r) => r.stage === "selecting_mode").length;

const summary = {
  accountA: ACCOUNT_A,
  projectA: PROJECT_A,
  accountB: ACCOUNT_B,
  projectB,
  totalSteps: results.length,
  successesA,
  successesB,
  modeSelectFailures: modeFailures,
  distinctMediaPathnames: distinctPathnames.size,
  totalMediaPathnames: pathnames.length,
  crossInstanceLeakageDetected: crossLeakageDetected,
  results,
};

fs.writeFileSync(path.join(OUT_DIR, "summary.json"), JSON.stringify(summary, null, 2));
console.log("\n[scenario-b] FULL SUMMARY:\n" + JSON.stringify(summary, null, 2));

console.log("[scenario-b] closing both");
await Promise.all([closeAccountBrowser(ACCOUNT_A), closeAccountBrowser(ACCOUNT_B)]);
console.log("[scenario-b] done");
