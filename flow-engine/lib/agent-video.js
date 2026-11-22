/**
 * Several talking clips from ONE Flow agent message (owner, 2026-11-23: "use agent mode for video generation").
 *
 * Live test 2026-11-23 (account 3, _scratch-agent-video-2clips.mjs): one numbered message with the host's reference pictures and
 * his Flow voice attached gave both clips in ~50 s ("I'll generate 2 separate 8-second videos ... featuring the man from your
 * reference images and the Achird voice"), each saying its own line. Two things learnt:
 *   - asked plainly, the agent made them 360p (its video defaults have no resolution): the message asks for 720p;
 *   - the tiles appear at once as placeholders, so a tile only counts when its video bytes download; the order of the tiles is
 *     not the order of the prompts. Results are "unordered": the caller maps each clip to its line (the Python side by speech).
 *
 *   generateAgentVideos(page, { prompts, referenceImages, voice, outputDir, names, shouldStop, timeoutMs, log })
 *     -> { videos: [{ path, mediaId }], diag }      at most prompts.length videos, saved as names[k] (in arrival order)
 */
import fs from "node:fs";
import path from "node:path";
import { waitForFlowReady, downloadMedia } from "./flow-api.js";
import { ensureAgentMode, collectAllVideoUrls, mediaKey, writeUiAgentLog } from "./flow-ui-agent.js";
import { setAgentConfirmNever, resolveAsbVideo } from "./flow-ui-experiment.js";
import { attachReferenceImages, attachVoice, clearBlockingOverlay, closePicker } from "./flow-references.js";

export const AGENT_VIDEO_MAX = 4;          // clips per message (one Flow agent request)

export function agentVideoMessage(prompts) {
  return `Make ${prompts.length} separate videos, one for each numbered prompt below. Each one is its own 8-second video in 720p `
    + `(not 360p), 16:9, a video and not an image. Use the attached reference pictures for the man in every video and the attached `
    + `voice for his speech. Do not ask me anything, just make them.\n\n`
    + prompts.map((p, i) => `${i + 1}. ${String(p || "").replace(/\s+/g, " ").trim()}`).join("\n\n");
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function generateAgentVideos(page, {
  prompts, referenceImages = [], voice = null, outputDir, names = null, shouldStop = null,
  timeoutMs = 20 * 60 * 1000, log = () => {},
} = {}) {
  const diag = { ts: null, stage: "start", outcome: "unknown", count: prompts.length, startedAt: Date.now() };
  const videos = [];
  try {
    diag.stage = "ready";
    await waitForFlowReady(page);
    diag.overlay = await clearBlockingOverlay(page).catch(() => null);
    diag.stage = "agent_mode";
    diag.agentMode = await ensureAgentMode(page);
    if (!diag.agentMode?.ok) throw Object.assign(new Error("Flow's agent mode could not be turned on; nothing was sent"), { notSent: true });
    diag.agentConfirm = await setAgentConfirmNever(page).catch((e) => `error: ${e?.message || e}`);
    if (referenceImages.length) {
      diag.stage = "references";
      const r = await attachReferenceImages(page, referenceImages);
      diag.references = r.attached;
      if (r.missing?.length) diag.referencesMissing = r.missing;
    }
    if (voice?.name) {
      diag.stage = "voice";
      diag.voice = await attachVoice(page, voice.name, { performance: voice.performance || "" });
      await closePicker(page).catch(() => {});
    }
    const known = new Set((await collectAllVideoUrls(page)).map(mediaKey).filter(Boolean));
    diag.stage = "message";
    const editor = page.locator('div.ProseMirror[aria-label="What do you want to create?"], div.ProseMirror').first();
    await editor.waitFor({ state: "visible", timeout: 20000 });
    await editor.click();
    await page.keyboard.insertText(agentVideoMessage(prompts));
    if (shouldStop?.()) throw Object.assign(new Error("Stopped before the agent request was sent"), { notSent: true });
    diag.stage = "send";
    await page.locator('button[aria-label="Start generation"]').filter({ visible: true }).first().click({ timeout: 15000 });
    diag.sentAt = Date.now();
    log(`agent video: asked for ${prompts.length} clip(s) in one message`);

    diag.stage = "waiting";
    const pending = new Map();                     // tile key -> asb {mediaId, fifeUrl}, until its video downloads
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline && videos.length < prompts.length && !shouldStop?.()) {
      for (const u of await collectAllVideoUrls(page)) {
        const k = mediaKey(u);
        if (!k || known.has(k) || pending.has(k) || videos.some((v) => v.key === k)) continue;
        const asb = resolveAsbVideo(u);
        if (asb) pending.set(k, asb);
      }
      for (const [k, asb] of [...pending]) {
        if (videos.length >= prompts.length) break;
        const dest = path.join(outputDir, (names && names[videos.length]) || `agent_${String(videos.length + 1).padStart(3, "0")}.mp4`);
        try {
          await downloadMedia(page, asb.mediaId, dest, asb.fifeUrl, { kind: "video" });
          if (!fs.existsSync(dest) || fs.statSync(dest).size < 10000) throw new Error("empty file");
          videos.push({ key: k, path: path.resolve(dest), mediaId: asb.mediaId });
          pending.delete(k);
          log(`agent video: clip ${videos.length}/${prompts.length} saved`);
        } catch { /* still a placeholder: next round */ }
      }
      if (videos.length < prompts.length) await sleep(15000);
    }
    diag.outcome = videos.length >= prompts.length ? "success" : videos.length ? "partial" : (shouldStop?.() ? "stopped" : "timeout_no_media");
    if (videos.length < prompts.length) {
      diag.agentReply = await page.evaluate(() => document.body.innerText.slice(-1500)).catch(() => "");
    }
  } catch (e) {
    diag.outcome = e?.notSent ? "not_sent" : (diag.sentAt ? "error_after_send" : "error_before_send");
    diag.error = e?.message || String(e);
    if (!diag.sentAt) e.notSent = true;
    diag.ts = new Date().toISOString();
    writeUiAgentLog(outputDir, diag);
    throw e;
  }
  diag.ts = new Date().toISOString();
  diag.elapsedMs = Date.now() - diag.startedAt;
  writeUiAgentLog(outputDir, diag);
  return { videos, diag };
}
