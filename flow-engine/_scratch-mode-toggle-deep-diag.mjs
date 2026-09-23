import { openAccountBrowser, closeAccountBrowser } from "./lib/accounts.js";
import { flowGoto, urls, waitForFlowReady } from "./lib/flow-api.js";
import fs from "node:fs";
import path from "node:path";

const ACCOUNT_ID = "0edfb022-bcda-4691-a7dc-4a8d9a4c4b0d";
const PROJECT_ID = "0d9a9a2f-d36f-4742-8949-9f9ec4d0a5d5";
const OUT_DIR = "/private/tmp/claude-501/-Users-muhammadnabil-Downloads-video-generator-main/eaed1ba5-c127-43c6-acf7-244ff63af7ec/scratchpad/mode-toggle-deep-diag";
fs.mkdirSync(OUT_DIR, { recursive: true });

const SETTINGS_TRIGGER_SELECTOR = 'button[aria-label="Settings trigger"]';
const PROMPT_EDITOR_SELECTOR = "div.ProseMirror";
const GENERATE_BUTTON_SELECTOR = 'button[aria-label="Start generation"]';

async function domState(page) {
  return page.evaluate(() => {
    const trigger = document.querySelector('button[aria-label="Settings trigger"]');
    const radios = Array.from(document.querySelectorAll('button[role="radio"]'));
    const imageRadio = radios.find((r) => (r.textContent || "").includes("Image"));
    const overlays = Array.from(document.querySelectorAll('[role="dialog"], [role="tooltip"], .cdk-overlay-container *, [class*="toast"], [class*="snackbar"], [class*="Toast"], [class*="Snackbar"]')).length;
    function rectOf(el) {
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
    }
    return {
      triggerExists: !!trigger,
      triggerRect: rectOf(trigger),
      triggerDisabled: trigger ? trigger.disabled : null,
      triggerAriaExpanded: trigger ? trigger.getAttribute("aria-expanded") : null,
      radioCount: radios.length,
      imageRadioExists: !!imageRadio,
      imageRadioRect: rectOf(imageRadio),
      imageRadioChecked: imageRadio ? imageRadio.getAttribute("aria-checked") : null,
      overlayElementCount: overlays,
      scrollY: window.scrollY,
      docHeight: document.documentElement.scrollHeight,
    };
  }).catch((e) => ({ evalError: e.message }));
}

console.log("[deep-diag] opening account browser");
const { page } = await openAccountBrowser(ACCOUNT_ID);
await flowGoto(page, urls.flowProject(PROJECT_ID), "mode-toggle-deep-diag", { waitUntil: "domcontentloaded", timeout: 60000 });
await waitForFlowReady(page);
await page.waitForTimeout(3000);

const prompts = ["a orange pumpkin on hay", "a blue teapot on a tray", "a green cactus in a pot", "a yellow rubber duck in water"];
const allEntries = [];

for (let i = 0; i < prompts.length; i++) {
  const genNum = i + 1;
  console.log(`\n[deep-diag] ===== attempt ${genNum}/4 =====`);

  const stateBeforeAnything = await domState(page);
  console.log("[deep-diag] state BEFORE any interaction:", JSON.stringify(stateBeforeAnything));

  // Replicate the exact fixed logic with heavy logging.
  const modeBtn = page.locator('button[role="radio"]').filter({ hasText: "Image" }).first();
  const panelAlreadyOpen = await modeBtn.isVisible().catch(() => false);
  console.log("[deep-diag] panelAlreadyOpen (modeBtn.isVisible()):", panelAlreadyOpen);

  let clickError = null;
  let waitError = null;
  if (!panelAlreadyOpen) {
    try {
      await page.locator(SETTINGS_TRIGGER_SELECTOR).first().click({ timeout: 10000 });
    } catch (e) {
      clickError = e.message;
    }
    const stateAfterTriggerClick = await domState(page);
    console.log("[deep-diag] state AFTER clicking trigger:", JSON.stringify(stateAfterTriggerClick));

    try {
      await modeBtn.waitFor({ state: "visible", timeout: 8000 });
    } catch (e) {
      waitError = e.message;
    }
  }

  const stateAfterWait = await domState(page);
  console.log("[deep-diag] state AFTER waitFor attempt:", JSON.stringify(stateAfterWait));

  const entry = {
    generationNumber: genNum,
    stateBeforeAnything,
    panelAlreadyOpen,
    clickError,
    waitError,
    stateAfterWait,
  };
  allEntries.push(entry);

  // If mode selection failed, we can't proceed with a real generation this
  // round — just move to next attempt's fresh page state (no reload, matches
  // production behavior of continuing on the same page after a failure).
  if (waitError) {
    console.log("[deep-diag] attempt failed at mode selection, skipping generation, continuing to next attempt");
    continue;
  }

  const alreadySelected = (await modeBtn.getAttribute("aria-checked").catch(() => null)) === "true";
  if (!alreadySelected) {
    await modeBtn.click().catch((e) => console.log("[deep-diag] modeBtn click error:", e.message));
  }
  if (!panelAlreadyOpen) {
    await page.keyboard.press("Escape");
  }

  // Quick real generation to complete the cycle (prompt + click generate + short poll)
  try {
    const editor = page.locator(PROMPT_EDITOR_SELECTOR).first();
    await editor.waitFor({ state: "visible", timeout: 10000 });
    await editor.click();
    await page.keyboard.press(process.platform === "darwin" ? "Meta+A" : "Control+A");
    await page.keyboard.press("Backspace");
    await editor.pressSequentially(prompts[i]);
    const genBtn = page.locator(GENERATE_BUTTON_SELECTOR).first();
    await genBtn.waitFor({ state: "visible", timeout: 10000 });
    await genBtn.click();
    console.log("[deep-diag] generate clicked, waiting briefly for completion (not full validation here)");
    let found = false;
    const deadline = Date.now() + 60000;
    while (Date.now() < deadline && !found) {
      found = await page.evaluate(() => {
        const els = Array.from(document.querySelectorAll("img[src]"));
        return els.some((el) => el.src.includes("flow-content.google"));
      });
      if (!found) await new Promise((r) => setTimeout(r, 2000));
    }
    entry.generationCompleted = found;
  } catch (e) {
    entry.generationError = e.message;
  }
}

fs.writeFileSync(path.join(OUT_DIR, "deep-diag.json"), JSON.stringify(allEntries, null, 2));
console.log("\n[deep-diag] FULL:\n" + JSON.stringify(allEntries, null, 2));

await closeAccountBrowser(ACCOUNT_ID);
console.log("[deep-diag] done");
