import { openAccountBrowser, gotoFlow, closeAccountBrowser } from "./lib/accounts.js";
import { flowGoto, urls, waitForFlowReady } from "./lib/flow-api.js";
import { generateImageViaFlowUI } from "./lib/flow-ui-experiment.js";
import fs from "node:fs";
import path from "node:path";

const ACCOUNT_ID = "0edfb022-bcda-4691-a7dc-4a8d9a4c4b0d";
const PROJECT_ID = "0d9a9a2f-d36f-4742-8949-9f9ec4d0a5d5"; // existing test project, reused
const OUT_DIR = "/private/tmp/claude-501/-Users-muhammadnabil-Downloads-video-generator-main/eaed1ba5-c127-43c6-acf7-244ff63af7ec/scratchpad/ui-dom-investigation";
fs.mkdirSync(OUT_DIR, { recursive: true });

function sanitizeUrl(u) {
  try {
    const url = new URL(u);
    return { origin: url.origin, pathname: url.pathname, queryParamNames: Array.from(url.searchParams.keys()) };
  } catch { return { raw_unparseable: true }; }
}

async function snapshotMedia(page) {
  return page.evaluate(() => {
    const els = Array.from(document.querySelectorAll("img[src], video[src]"));
    return els.map((el, idx) => {
      const rect = el.getBoundingClientRect();
      return {
        index: idx,
        tag: el.tagName,
        srcHost: (() => { try { return new URL(el.src).hostname; } catch { return null; } })(),
        srcPathname: (() => { try { return new URL(el.src).pathname; } catch { return null; } })(),
        alt: el.getAttribute("alt"),
        classList: Array.from(el.classList || []),
        parentClassList: el.parentElement ? Array.from(el.parentElement.classList || []) : [],
        visible: rect.width > 0 && rect.height > 0,
        widthPx: Math.round(rect.width),
        heightPx: Math.round(rect.height),
        domOrderPosition: idx,
      };
    });
  });
}

console.log("[ui-dom] opening account browser");
const { page } = await openAccountBrowser(ACCOUNT_ID);

console.log("[ui-dom] navigating to existing test project");
await flowGoto(page, urls.flowProject(PROJECT_ID), "ui-dom-investigation", { waitUntil: "domcontentloaded", timeout: 60000 });
await waitForFlowReady(page);
await page.waitForTimeout(3000); // let any lazy-loaded gallery thumbnails settle

console.log("[ui-dom] taking BEFORE snapshot of all media elements in DOM");
const beforeSnapshot = await snapshotMedia(page);
fs.writeFileSync(path.join(OUT_DIR, "before-snapshot.json"), JSON.stringify(beforeSnapshot, null, 2));
console.log(`[ui-dom] BEFORE: ${beforeSnapshot.length} media elements found`);
console.log(JSON.stringify(beforeSnapshot, null, 2));

// Passive network capture around the generation window (structural only).
const networkLog = [];
page.on("requestfinished", async (req) => {
  try {
    const url = req.url();
    if (!url.includes("/data/batchexecute")) return;
    const u = new URL(url);
    const rpcids = u.searchParams.get("rpcids");
    const resp = await req.response();
    networkLog.push({
      ts: Date.now(),
      rpcids,
      status: resp ? resp.status() : null,
      method: req.method(),
    });
  } catch {}
});

console.log("[ui-dom] running ONE real UI generation (generateImageViaFlowUI)");
const prompt = "a single yellow umbrella standing upright in the sand";
const genResult = await generateImageViaFlowUI(page, prompt, { outputDir: OUT_DIR, mode: "image", generationTimeoutMs: 120000 });

console.log("[ui-dom] generation result:", JSON.stringify(genResult, null, 2));

console.log("[ui-dom] taking AFTER snapshot of all media elements in DOM");
const afterSnapshot = await snapshotMedia(page);
fs.writeFileSync(path.join(OUT_DIR, "after-snapshot.json"), JSON.stringify(afterSnapshot, null, 2));
console.log(`[ui-dom] AFTER: ${afterSnapshot.length} media elements found`);
console.log(JSON.stringify(afterSnapshot, null, 2));

// Diff: which pathnames are new (not in before snapshot)?
const beforePaths = new Set(beforeSnapshot.map((e) => e.srcPathname));
const newElements = afterSnapshot.filter((e) => !beforePaths.has(e.srcPathname));
console.log(`[ui-dom] NEW elements not present before generation: ${newElements.length}`);
console.log(JSON.stringify(newElements, null, 2));

// Was the element our detector actually picked present in the BEFORE snapshot? (i.e. did it pick an old one?)
let detectorPickedStale = null;
if (genResult.mediaUrl) {
  const pickedPathname = (() => { try { return new URL(genResult.mediaUrl).pathname; } catch { return null; } })();
  detectorPickedStale = beforePaths.has(pickedPathname);
}

const summary = {
  beforeCount: beforeSnapshot.length,
  afterCount: afterSnapshot.length,
  newElementsCount: newElements.length,
  newElements,
  generationResult: { ok: genResult.ok, mediaUrl: sanitizeUrl(genResult.mediaUrl || ""), diag: genResult.diag },
  detectorPickedAnElementThatExistedBeforeGeneration: detectorPickedStale,
  networkLogDuringGeneration: networkLog.map((n) => ({ rpcids: n.rpcids, status: n.status, method: n.method })),
};

fs.writeFileSync(path.join(OUT_DIR, "summary.json"), JSON.stringify(summary, null, 2));
console.log("\n[ui-dom] FULL SUMMARY:\n" + JSON.stringify(summary, null, 2));

console.log("[ui-dom] closing");
await closeAccountBrowser(ACCOUNT_ID);
console.log("[ui-dom] done");
