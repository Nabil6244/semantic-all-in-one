import { openAccountBrowser, closeAccountBrowser } from "./lib/accounts.js";
import { flowGoto, urls, waitForFlowReady } from "./lib/flow-api.js";
import fs from "node:fs";
import path from "node:path";

const ACCOUNT_A = "0edfb022-bcda-4691-a7dc-4a8d9a4c4b0d";
const PROJECT_A = "0d9a9a2f-d36f-4742-8949-9f9ec4d0a5d5"; // long-used project, Settings trigger works
const ACCOUNT_B = "fcb499ce-f99b-41ec-87ee-5acc1c244357";
const PROJECT_B = "9515bfad-d0d2-4d34-8d7f-4d166667768e"; // fresh project created in prior test, Settings trigger hidden
const OUT_DIR = "/private/tmp/claude-501/-Users-muhammadnabil-Downloads-video-generator-main/eaed1ba5-c127-43c6-acf7-244ff63af7ec/scratchpad/fresh-project-diag";
fs.mkdirSync(OUT_DIR, { recursive: true });

async function inspect(page, label) {
  const data = await page.evaluate(() => {
    const trigger = document.querySelector('button[aria-label="Settings trigger"]');
    const editor = document.querySelector("div.ProseMirror");
    const genBtn = document.querySelector('button[aria-label="Start generation"]');

    function describe(el) {
      if (!el) return null;
      const rect = el.getBoundingClientRect();
      return {
        exists: true,
        hidden: el.hasAttribute("hidden"),
        disabled: el.disabled ?? null,
        ariaHidden: el.getAttribute("aria-hidden"),
        className: el.className,
        rect: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
        visible: el.offsetParent !== null,
      };
    }

    // Look for any dialogs / overlays / onboarding elements
    const dialogs = Array.from(document.querySelectorAll('[role="dialog"], [role="alertdialog"], .cdk-overlay-container > *')).map((d) => ({
      role: d.getAttribute("role"),
      className: d.className,
      text: (d.textContent || "").slice(0, 200),
      visible: d.offsetParent !== null,
    }));

    // All buttons currently in the toolbar area near the prompt editor, for comparison
    const allButtons = Array.from(document.querySelectorAll("button")).map((b) => ({
      ariaLabel: b.getAttribute("aria-label"),
      hidden: b.hasAttribute("hidden"),
      visible: b.offsetParent !== null,
      text: (b.textContent || "").trim().slice(0, 30),
    })).filter((b) => b.ariaLabel || b.text);

    // Editor container's toolbar siblings, to see structural placement
    let editorToolbarSiblings = null;
    if (editor) {
      let container = editor.closest('[class*="container"], [class*="toolbar"], [class*="composer"]') || editor.parentElement?.parentElement;
      if (container) {
        editorToolbarSiblings = Array.from(container.querySelectorAll("button")).map((b) => ({
          ariaLabel: b.getAttribute("aria-label"),
          hidden: b.hasAttribute("hidden"),
          visible: b.offsetParent !== null,
        }));
      }
    }

    return {
      url: location.href,
      title: document.title,
      settingsTrigger: describe(trigger),
      promptEditor: describe(editor),
      generateButton: describe(genBtn),
      dialogCount: dialogs.length,
      dialogs,
      totalButtonCount: allButtons.length,
      buttonsWithAriaLabelOrText: allButtons.slice(0, 60),
      editorToolbarSiblings,
    };
  });
  console.log(`\n[fresh-diag] === ${label} ===`);
  console.log(JSON.stringify(data, null, 2));
  return data;
}

console.log("[fresh-diag] opening both accounts");
const [{ page: pageA }, { page: pageB }] = await Promise.all([
  openAccountBrowser(ACCOUNT_A),
  openAccountBrowser(ACCOUNT_B),
]);

await flowGoto(pageA, urls.flowProject(PROJECT_A), "fresh-diag-A", { waitUntil: "domcontentloaded", timeout: 60000 });
await waitForFlowReady(pageA);
await pageA.waitForTimeout(3000);

await flowGoto(pageB, urls.flowProject(PROJECT_B), "fresh-diag-B", { waitUntil: "domcontentloaded", timeout: 60000 });
await waitForFlowReady(pageB);
await pageB.waitForTimeout(3000);

const resultA = await inspect(pageA, "Account A (working project)");
const resultB = await inspect(pageB, "Account B (fresh project, trigger hidden)");

fs.writeFileSync(path.join(OUT_DIR, "compare.json"), JSON.stringify({ resultA, resultB }, null, 2));

console.log("\n[fresh-diag] closing");
await Promise.all([closeAccountBrowser(ACCOUNT_A), closeAccountBrowser(ACCOUNT_B)]);
console.log("[fresh-diag] done");
