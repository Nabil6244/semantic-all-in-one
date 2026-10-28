/**
 * Reference images for Flow image generation (2026-10-28): up to MAX_REFERENCES pictures (our 3D renders of a phone, a character
 * sheet...) attached to the Agent composer before the scene request is sent, so the generated scenes keep the same design.
 *
 * Transport: the Flow web UI (the only path that is verified to take reference images; the batchexecute upload RPC is configured but
 * was never exercised). Steps, as observed in the live UI: the composer's "Add ingredients to the prompt box" button opens the asset
 * picker; "Upload media" opens a file chooser; a listed asset is selected and "Add to prompt" attaches it. An attached asset leaves
 * the picker's list, so a second reference needs the picker opened again.
 *
 * Safety: a request that asked for references is never made without them (no silent fallback to the standard path), and the ledger
 * key includes the references, so the same prompt with other references is a different image and an identical one is still deduplicated.
 */
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

export const MAX_REFERENCES = 3;
export const MAX_REFERENCE_BYTES = 10 * 1024 * 1024;
const OK_EXT = new Set([".png", ".jpg", ".jpeg", ".webp"]);

const ADD_BUTTON = 'button[aria-label="Add ingredients to the prompt box"]';

/** Absolute, existing, supported picture files; throws one Error naming the first problem. */
export function validateReferenceImages(paths, { fsImpl = fs } = {}) {
  if (paths == null) return [];
  if (!Array.isArray(paths)) throw new Error("referenceImages must be a list of file paths");
  const list = paths.map((p) => String(p || "").trim()).filter(Boolean);
  if (list.length > MAX_REFERENCES) throw new Error(`Flow takes at most ${MAX_REFERENCES} reference images; got ${list.length}`);
  const seen = new Set();
  return list.map((p) => {
    const abs = path.resolve(p);
    if (seen.has(abs)) throw new Error(`Reference image listed twice: ${path.basename(abs)}`);
    seen.add(abs);
    if (!OK_EXT.has(path.extname(abs).toLowerCase())) throw new Error(`Reference image ${path.basename(abs)} must be a PNG, JPEG or WebP picture`);
    let st;
    try { st = fsImpl.statSync(abs); } catch { throw new Error(`Reference image not found: ${abs}`); }
    if (!st.isFile()) throw new Error(`Reference image is not a file: ${abs}`);
    if (st.size > MAX_REFERENCE_BYTES) throw new Error(`Reference image ${path.basename(abs)} is ${(st.size / 1048576).toFixed(1)} MB; the limit is ${MAX_REFERENCE_BYTES / 1048576} MB`);
    if (st.size === 0) throw new Error(`Reference image ${path.basename(abs)} is empty`);
    return abs;
  });
}

/** A short identity of a reference set: file names + sizes, order-independent. Empty set -> null. */
export function referenceKeyOf(paths, { fsImpl = fs } = {}) {
  const list = validateReferenceImages(paths, { fsImpl });
  if (!list.length) return null;
  const parts = list.map((p) => `${path.basename(p)}:${fsImpl.statSync(p).size}`).sort();
  return crypto.createHash("sha1").update(parts.join("|")).digest("hex").slice(0, 16);
}

/**
 * The settings of a run that asked for reference images: validated paths, a reference key for the ledger, and the agent route that is
 * able to attach them (UI agent, even for a single scene, never the standard path). Without references: the settings unchanged.
 */
export function withReferenceSettings(settings, { fsImpl = fs } = {}) {
  const asked = settings && Array.isArray(settings.referenceImages) && settings.referenceImages.length;
  if (!asked) return settings;
  const referenceImages = validateReferenceImages(settings.referenceImages, { fsImpl });
  return {
    ...settings,
    referenceImages,
    referenceKey: referenceKeyOf(referenceImages, { fsImpl }),
    generationMode: "agent",
    agentViaUi: true,
    agentFallback: false,
    agentMinScenes: 1,
  };
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function openPicker(page, timeoutMs) {
  const add = page.locator(ADD_BUTTON).first();
  await add.waitFor({ state: "visible", timeout: timeoutMs });
  await add.click();
  await page.getByRole("button", { name: /upload media/i }).first().waitFor({ state: "visible", timeout: timeoutMs });
}

async function listed(page, name, timeoutMs) {
  try {
    await page.getByText(name, { exact: false }).first().waitFor({ state: "visible", timeout: timeoutMs });
    return true;
  } catch {
    return false;
  }
}

/**
 * Attach the pictures to the open Agent composer. Returns { attached: [file names], uploaded: [file names] }.
 * Throws (nothing was sent to Flow) when a picture cannot be uploaded or attached.
 */
export async function attachReferenceImages(page, paths, { timeoutMs = 20000, probeMs = 2500, settleMs = 600 } = {}) {
  const files = validateReferenceImages(paths);
  const out = { attached: [], uploaded: [] };
  if (!files.length) return out;
  const names = files.map((f) => path.basename(f));

  // 1. Upload what the project does not have yet (one chooser for all of them).
  await openPicker(page, timeoutMs);
  const missing = [];
  for (let i = 0; i < files.length; i++) if (!(await listed(page, names[i], probeMs))) missing.push(i);
  if (missing.length) {
    const chooserWait = page.waitForEvent("filechooser", { timeout: timeoutMs });
    await page.getByRole("button", { name: /upload media/i }).first().click();
    const chooser = await chooserWait;
    await chooser.setFiles(missing.map((i) => files[i]));
    for (const i of missing) {
      if (!(await listed(page, names[i], timeoutMs))) throw new Error(`Flow did not list the uploaded reference image ${names[i]}`);
      out.uploaded.push(names[i]);
    }
  }

  // 2. Attach each one: select it in the picker, "Add to prompt"; the picker is reopened for the next.
  for (let i = 0; i < files.length; i++) {
    if (i > 0) await openPicker(page, timeoutMs);
    const item = page.getByText(names[i], { exact: false }).first();
    try { await item.waitFor({ state: "visible", timeout: timeoutMs }); } catch { throw new Error(`Reference image ${names[i]} is not in Flow's asset picker`); }
    await item.click();
    const addToPrompt = page.getByRole("button", { name: /add to prompt/i }).first();
    try { await addToPrompt.waitFor({ state: "visible", timeout: timeoutMs }); } catch { throw new Error(`Flow offered no "Add to prompt" for ${names[i]}`); }
    await addToPrompt.click();
    out.attached.push(names[i]);
    if (settleMs) await wait(settleMs);
  }
  return out;
}
