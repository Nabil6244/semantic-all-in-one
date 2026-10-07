/**
 * Image batches through Flow's agent mode (settings.generationMode = "agent"): up to agent.maxBatch scenes per request,
 * one image per scene, then the same per-scene results, files and ledger records as the standard path (batch-runner.js).
 *
 * Safety rules (same ledger, same keys as runBatchSlice, so the two paths guard each other):
 *   - a scene the ledger blocks / can reuse / can resume is handled exactly as the standard path would;
 *   - an agent request that fails before it is sent, or is refused outright, created nothing: those scenes go to the
 *     standard path in this same run;
 *   - once a request is on the wire, a missing answer is UNKNOWN: those scenes are never sent again automatically
 *     (Needs action, like the standard path);
 *   - every image is matched to its scene by the scene ID the agent named it with (S01…), else by the scene's exact text in
 *     the agent's prompt; a scene the agent did not make, or made in the wrong aspect ratio, goes to the standard path; an
 *     image that cannot be tied to one scene is never guessed;
 *   - a cool-down answer (too much traffic, quota, agent capacity) rests the account: its scenes go to other accounts,
 *     never to the standard path on the same account;
 *   - fewer than agent.minScenes pending scenes use the standard path (an agent request has a fixed ~40-60 s cost).
 * The agent always makes Nano Banana 2 Lite. Its images count as finished for the scene whatever model is chosen (user
 * decision 2026-10-06): the ledger key is the standard path's, so switching agent mode off reuses them.
 * The account lock and the pause between requests keep one agent request per account at a time.
 */
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { agent as agentConfig } from "../config.js";
import { canonicalImageModel } from "../config.js";
import {
  AGENT_ASPECT_FOR_SETTING,
  agentSceneId,
  buildAgentMessage,
  coolDownReason,
  createAgentChat as realCreateAgentChat,
  fetchImageUrl as realFetchImageUrl,
  mapCallsToScenes,
  parseAgentStream,
  sendAgentMessage as realSendAgentMessage,
  splitSharedStyle,
  wordsOf,
} from "./agent-api.js";
import { isValidOutput, runBatchSlice as realRunBatchSlice, withAccountLock } from "./batch-runner.js";
import {
  downloadMedia as realDownloadMedia,
  openOrCreateProject as realOpenOrCreateProject,
  waitForFlowReady as realWaitForFlowReady,
} from "./flow-api.js";
import { LedgerState, defaultLedger, generationKey, scopeOf } from "./generation-ledger.js";
import { Submission, submissionOf } from "./generation-state.js";
import { accountDownloadDir } from "./paths.js";

const DOWNLOAD_WAITS_S = [0, 15];

function sleep(ms, shouldStop) {
  return new Promise((resolve) => {
    const start = Date.now();
    const iv = setInterval(() => {
      if (shouldStop?.() || Date.now() - start >= ms) {
        clearInterval(iv);
        resolve();
      }
    }, Math.min(250, Math.max(10, ms)));
  });
}

const pad = (n) => String(n).padStart(3, "0");

/** Copy an existing saved file to `dest` (atomic), or keep it where it is when it already is `dest`. */
function placeExisting(src, dest) {
  if (!src || path.resolve(src) === path.resolve(dest)) return path.resolve(src || dest);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  const tmp = `${dest}.${process.pid}.reuse.part`;
  fs.copyFileSync(src, tmp);
  fs.renameSync(tmp, dest);
  return path.resolve(dest);
}

/**
 * Scenes inside an agent request that has not returned yet (ledger key -> who is making it). A Retry of one of these
 * scenes must not send a second request while the first may still produce its image (orchestrator.js checks this).
 */
export const activeAgentScenes = new Map();

/** The ledger key of a scene on the agent path (the standard path's identity: generationMode is not part of it). */
export function agentSceneKey({ prompt, promptKey = null, index = 0, settings = {} }) {
  const standard = { ...settings };
  delete standard.generationMode;
  if (standard.model) standard.model = canonicalImageModel(standard.model);
  return generationKey({
    mediaKind: "image",
    prompt: promptKey != null ? `${promptKey}\u0000${prompt}` : `#${index}\u0000${prompt}`,
    settings: standard,
    slot: 0,
    scope: scopeOf(standard.outputDir),
  });
}

/** How long to wait for an agent reply: grows with the batch (a 24-scene reply under load took several minutes). */
export function agentReplyTimeoutMs(scenes) {
  const n = Math.max(1, Number(scenes) || 1);
  return Math.min(agentConfig.streamTimeoutMaxMs, agentConfig.streamTimeoutBaseMs + n * agentConfig.streamTimeoutPerSceneMs);
}

/** Two scene texts an image could not be told apart by: identical, or one inside the other (case and spaces ignored). */
export function textsClash(a, b) {
  const x = wordsOf(a);
  const y = wordsOf(b);
  return !!x && !!y && (` ${x} `.includes(` ${y} `) || ` ${y} `.includes(` ${x} `));
}

/**
 * Split pending scenes into agent requests of at most `maxBatch` scenes and `maxChars` of scene text, balanced (26 scenes
 * become 13 + 13, not 24 + 2). `lenOf` is the text an item adds to the message (its scene text when the style is shared).
 * Images are tied to scenes by exact text, so two scenes whose texts clash (see textsClash) never share a request.
 */
export function planAgentBatches(items, {
  maxBatch = agentConfig.maxBatch, maxChars = agentConfig.maxMessageChars, lenOf = (it) => String(it.prompt).length,
  textOf = (it) => it.text ?? it.prompt,
} = {}) {
  if (!items.length) return [];
  const size = (it) => lenOf(it) + 8;
  const total = items.reduce((n, it) => n + size(it), 0);
  const count = Math.max(Math.ceil(items.length / maxBatch), Math.ceil(total / Math.max(1, maxChars)));
  const target = Math.min(maxBatch, Math.ceil(items.length / count));
  const batches = [];
  const fits = (batch, it) =>
    batch.items.length < target && batch.chars + size(it) <= maxChars && !batch.items.some((o) => textsClash(textOf(o), textOf(it)));
  let open = 0;   // batches before this one are full
  for (const it of items) {
    while (open < batches.length && batches[open].items.length >= target) open++;
    let batch = batches.slice(open).find((bt) => fits(bt, it));
    if (!batch) {
      batch = { items: [], chars: 0 };
      batches.push(batch);
    }
    batch.items.push(it);
    batch.chars += size(it);
  }
  return batches.map((bt) => bt.items);
}

export async function runAgentSlice(params) {
  const {
    page, prompts, promptIndices, promptKeys, totalAbsolute, settings, folderLabel, shouldStop, onProgress,
    accountId, accountLabel, deps = {},
  } = params;
  const d = {
    openOrCreateProject: realOpenOrCreateProject,
    waitForFlowReady: realWaitForFlowReady,
    downloadMedia: realDownloadMedia,
    createAgentChat: realCreateAgentChat,
    sendAgentMessage: realSendAgentMessage,
    fetchImageUrl: realFetchImageUrl,
    runBatchSlice: realRunBatchSlice,
    sleep,
    ...deps,
  };
  const ledger = d.ledger || (await defaultLedger());
  const emit = (type, payload) => onProgress?.({ type, ...payload });
  const outDir = accountDownloadDir(folderLabel, settings.outputDir || undefined);
  // The standard path's settings (same ledger identity: generationMode is not part of the key).
  const standardSettings = { ...settings };
  delete standardSettings.generationMode;
  if (standardSettings.model) standardSettings.model = canonicalImageModel(standardSettings.model);
  const runId = standardSettings._runId || `run-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const scope = scopeOf(standardSettings.outputDir);
  const owner = accountId || page?.__flowAccountId || "";
  const label = accountLabel || folderLabel || owner || "account";
  const confirmedKeys = new Set((standardSettings.confirmResubmitKeys || []).map(String));
  const expectedAspect = AGENT_ASPECT_FOR_SETTING[standardSettings.aspectRatio || "IMAGE_ASPECT_RATIO_LANDSCAPE"] || "16:9";
  const batchGapMs = Number(standardSettings.agentBatchGapMs ?? agentConfig.batchGapMs);
  let completed = 0;
  let failed = 0;
  let restricted = null;
  const reassign = [];
  const fallback = [];   // scenes for the standard path: the agent made nothing for them

  const fail = (it, message, extra = {}) => {
    failed++;
    emit("PROMPT_RESULT", { index: it.abs, prompt: it.prompt, status: "failed", error: message, ...extra });
    emit("BATCH_PROGRESS", { index: it.abs, total: totalAbsolute, status: "failed", message: `Failed: ${message}`, completed, failed });
  };
  const done = (it, mediaId, savedPath, extra = {}) => {
    completed++;
    emit("PROMPT_RESULT", { index: it.abs, prompt: it.prompt, status: "done", mediaIds: [mediaId], path: savedPath, ...extra });
    emit("BATCH_PROGRESS", { index: it.abs, total: totalAbsolute, status: "done", message: `Saved ${completed}/${prompts.length} on this account`, completed, failed, path: savedPath });
  };

  emit("status", { message: "Opening / creating Flow project…" });
  const projectId = await d.openOrCreateProject(page);
  await d.waitForFlowReady(page);

  // ---- 1. What the ledger already knows about each scene (identical rules to the standard path).
  const toGenerate = [];
  const toDownload = [];
  for (let i = 0; i < prompts.length; i++) {
    const abs = promptIndices[i];
    const prompt = prompts[i];
    const promptKey = promptKeys?.[i] ?? null;
    const it = { i, abs, prompt, promptKey, dest: path.join(outDir, `${pad(abs + 1)}.png`) };
    if (!String(prompt || "").trim()) {
      fail(it, "The prompt is empty — nothing was sent to Flow.");
      continue;
    }
    it.key = agentSceneKey({ prompt, promptKey, index: abs, settings: standardSettings });
    it.confirmed = promptKey != null && confirmedKeys.has(String(promptKey));
    const decision = ledger.decide(it.key, { accountId: owner, runId, confirmed: it.confirmed, validFile: (p) => isValidOutput(p, "image") });
    if (decision.action === "block") {
      fail(it, `Not submitted: ${decision.reason}.`, { needsAction: true, ledgerState: decision.entry.state });
    } else if (decision.action === "reuse") {
      const savedPath = placeExisting(decision.entry.savedPath, it.dest);
      ledger.put(it.key, { savedPath });
      done(it, decision.entry.mediaId, savedPath, { submitted: false });
    } else if (decision.action === "resume" && decision.entry.mediaId) {
      toDownload.push({ ...it, mediaId: decision.entry.mediaId, resumed: true });
    } else if (decision.action === "resume") {
      // A resumable entry without a media id (an accepted video-style job) cannot be finished by the agent path.
      fallback.push(it);
    } else {
      toGenerate.push(it);
    }
  }

  // ---- 2. Agent requests (a few scenes are quicker on the standard path).
  const minScenes = Number(standardSettings.agentMinScenes ?? agentConfig.minScenes);
  if (toGenerate.length && toGenerate.length < minScenes) {
    emit("status", { message: `${toGenerate.length} scene(s): using the standard Flow path (quicker than an agent request)` });
    fallback.push(...toGenerate.splice(0));
  }
  const style = splitSharedStyle(toGenerate.map((it) => it.prompt));
  toGenerate.forEach((it, j) => { it.text = style.texts[j]; });
  const styleChars = style.opening.length + style.ending.length;
  const batches = planAgentBatches(toGenerate, { lenOf: (it) => it.text.length, textOf: (it) => it.text, maxChars: Math.max(2000, agentConfig.maxMessageChars - styleChars) });
  let coolDown = null;      // set when Flow says this account must rest: the rest of its scenes go to other accounts
  const rest = (its, reason) => {
    for (const it of its) {
      ledger.put(it.key, { state: LedgerState.REJECTED, error: reason });
      reassign.push({ index: it.abs, prompt: it.prompt, promptKey: it.promptKey, reason: "rate_limit" });
      emit("PROMPT_RESULT", { index: it.abs, prompt: it.prompt, status: "rate_limited", error: `Flow asked account ${label} to slow down (${reason})`, reassign: true });
    }
  };
  let b = 0;
  for (; b < batches.length && !shouldStop?.() && !restricted && !coolDown; b++) {
    const batch = batches[b];
    if (b > 0 && batchGapMs > 0) {
      emit("BATCH_PROGRESS", { index: batch[0].abs, total: totalAbsolute, status: "waiting", countdown: Math.ceil(batchGapMs / 1000), message: `Next agent batch in ${Math.ceil(batchGapMs / 1000)}s…` });
      await d.sleep(batchGapMs, shouldStop);
      if (shouldStop?.()) break;
    }
    // One identity per agent request, kept on every scene of it (a reconnect or a restart never makes a new one).
    const agentRequestId = `agentreq-${crypto.randomUUID()}`;
    try {
    await withAccountLock(owner || label, async () => {
      for (const it of batch) {
        activeAgentScenes.set(it.key, { accountId: owner, accountLabel: label, runId, agentRequestId, since: Date.now() });
        ledger.put(it.key, {
          state: LedgerState.SUBMITTING, accountId: owner, accountLabel: label, mediaKind: "image", slot: 0, runId, projectId,
          prompt: String(it.prompt).slice(0, 200), workflowId: null, mediaId: null, fifeUrl: null, dest: null, savedPath: null,
          failedStage: null, confirmedResumeFailedRunId: null, error: null, via: "agent", agentRequestId, agentChatId: null,
          sceneText: String(it.text || "").slice(0, 200),
        });
        emit("BATCH_PROGRESS", { index: it.abs, total: totalAbsolute, status: "running", message: `Agent generating (batch ${b + 1}/${batches.length}, ${batch.length} scenes)…` });
      }
      const notCreated = (its, state, why) => {
        for (const it of its) {
          ledger.put(it.key, { state, error: why });
          fallback.push(it);
        }
      };
      let chatId;
      try {
        chatId = await d.createAgentChat(page, projectId);
      } catch (err) {
        notCreated(batch, LedgerState.FAILED_BEFORE_SUBMISSION, String(err?.message || err));
        return;
      }
      for (const it of batch) ledger.put(it.key, { agentChatId: chatId });   // kept even if the reply never comes
      let reply;
      try {
        reply = await d.sendAgentMessage(page, {
          projectId, chatId, turn: 1,
          message: buildAgentMessage(batch.map((it) => it.text), { aspect: expectedAspect, opening: style.opening, ending: style.ending }),
          timeoutMs: Number(standardSettings.agentReplyTimeoutMs) || agentReplyTimeoutMs(batch.length),
        });
      } catch (err) {
        const sub = submissionOf(err);
        if (err?.httpStatus === 429) {
          coolDown = "HTTP 429";
          return rest(batch, coolDown);
        }
        if (sub === Submission.NOT_SUBMITTED) return notCreated(batch, LedgerState.FAILED_BEFORE_SUBMISSION, String(err?.message || err));
        if (sub === Submission.REJECTED) return notCreated(batch, LedgerState.REJECTED, String(err?.message || err));
        // On the wire, no answer: the agent may be generating. Never sent again automatically.
        for (const it of batch) {
          ledger.put(it.key, { state: LedgerState.SUBMITTED_UNKNOWN, error: String(err?.message || err) });
          fail(it, `Not resubmitted: the Flow agent may already be making this image (${String(err?.message || err).slice(0, 120)}). Check the Flow project; click Retry on this scene to generate it again.`, { needsAction: true, submitted: true });
        }
        return;
      }

      const parsed = parseAgentStream(reply.text);
      if (parsed.error && parsed.error.reason === "PUBLIC_ERROR_UNUSUAL_ACTIVITY" && !parsed.calls.length) {
        restricted = parsed.error.reason;
        for (const it of batch) {
          ledger.put(it.key, { state: LedgerState.REJECTED, error: restricted });
          fail(it, `Flow restricted account ${label} (${restricted}).`, { restricted: true });
        }
        return;
      }
      const cool = coolDownReason(parsed, reply.text);
      if (cool && !parsed.calls.length) {
        coolDown = cool;
        return rest(batch, cool);
      }
      if (!parsed.calls.length) {
        // A refusal, or the agent answered with a question instead of images: nothing was created.
        const why = parsed.error ? `Flow agent refused (code ${parsed.error.grpcCode}${parsed.error.reason ? `, ${parsed.error.reason}` : ""})`
          : `Flow agent made no images${parsed.text ? `: ${parsed.text.slice(0, 160)}` : ""}`;
        return notCreated(batch, LedgerState.REJECTED, why);
      }

      const { mapping, extraCalls } = mapCallsToScenes(batch.map((it) => it.text), parsed.calls, parsed.results);
      batch.forEach((it, j) => {
        const match = mapping.get(j);
        const call = match?.call;
        if (!call) {
          if (extraCalls.length) {
            // The agent made images we could not tie to one scene: one of them may be this scene's. Never guess.
            // Keep what the agent actually asked for, so a mismatch can be audited later.
            const unmatched = extraCalls.map((c) => ({ placeholderId: c.placeholderId, prompt: c.prompt.slice(0, 500), mediaId: parsed.results[c.placeholderId]?.mediaId || null }));
            ledger.put(it.key, { state: LedgerState.SUBMITTED_UNKNOWN, error: "agent image could not be matched to this scene", agentChatId: chatId,
              sceneText: String(it.text || "").slice(0, 300), agentUnmatched: unmatched });
            fail(it, "Not resubmitted: the Flow agent made an image that could not be matched to this scene. Check the Flow project; click Retry on this scene to generate it again.",
              { needsAction: true, submitted: true, agentUnmatched: unmatched });
          } else {
            ledger.put(it.key, { state: LedgerState.REJECTED, error: "the agent made no image for this scene" });
            fallback.push(it);
          }
          return;
        }
        const res = parsed.results[call.placeholderId];
        if (!res) {
          ledger.put(it.key, { state: LedgerState.SUBMITTED_UNKNOWN, error: "the agent planned this image but reported no result" });
          fail(it, "Not resubmitted: the Flow agent started this image but did not report it. Check the Flow project; click Retry on this scene to generate it again.", { needsAction: true, submitted: true });
          return;
        }
        if (res.status !== "success" || !res.mediaId) {
          ledger.put(it.key, { state: LedgerState.REJECTED, error: `agent result ${res.status || "missing"}` });
          fallback.push(it);
          return;
        }
        // The explicit IDs that tie this scene to its request and result, kept for audits.
        const agentInfo = {
          agentModel: call.modelKey || null, agentPrompt: call.prompt.slice(0, 400), agentAspect: call.aspect || null,
          agentBatchId: res.batchId || null, agentChatId: chatId, agentRequestId, agentSceneId: agentSceneId(j), agentPlaceholderId: call.placeholderId,
          agentTitle: String(res.title || "").slice(0, 80), agentMatch: match.method, sceneText: String(it.text || "").slice(0, 200),
        };
        if (call.aspect && call.aspect !== expectedAspect) {
          // Made, but in the wrong shape for this video: keep the record, use the standard path for the scene.
          ledger.put(it.key, { state: LedgerState.REJECTED, error: `agent image is ${call.aspect}, not ${expectedAspect}`, ...agentInfo, mediaId: res.mediaId });
          fallback.push(it);
          return;
        }
        ledger.put(it.key, { state: LedgerState.MEDIA_ID_KNOWN, mediaId: res.mediaId, workflowId: res.workflowId, ...agentInfo });
        toDownload.push({ ...it, mediaId: res.mediaId, agentInfo });
      });
    });
    } finally {
      // The request has returned (or timed out): its scenes are no longer "being made right now".
      for (const it of batch) activeAgentScenes.delete(it.key);
    }
  }

  const unsent = batches.slice(b).flat();
  if (coolDown) {
    // The account must rest: what it has not made goes to other accounts, not to the standard path here.
    rest(unsent, coolDown);
    rest(fallback.splice(0), coolDown);
  } else if (unsent.length) {
    for (const it of unsent) fail(it, restricted ? `Not run: Flow restricted account ${label}.` : "Stopped before it was sent to Flow — nothing was generated.");
  }

  // ---- 3. Downloads (read-only: never generates). After Stop, finished images are still collected for a short grace period.
  const graceMs = Number(standardSettings.agentStopGraceMs ?? agentConfig.stopGraceMs);
  let stopSeenAt = 0;
  const downloadsStopped = () => {
    if (!shouldStop?.()) return false;
    stopSeenAt = stopSeenAt || Date.now();
    return Date.now() - stopSeenAt >= graceMs;
  };
  let downloaded = 0;
  for (const it of toDownload) {
    if (downloadsStopped()) break;
    downloaded++;
    emit("BATCH_PROGRESS", { index: it.abs, total: totalAbsolute, status: "running", message: `Downloading ${path.basename(it.dest)}…` });
    ledger.put(it.key, { dest: path.resolve(it.dest) });
    let lastErr = null;
    let savedPath = null;
    for (const wait of DOWNLOAD_WAITS_S) {
      if (downloadsStopped() || (wait && shouldStop?.())) break;
      if (wait) await d.sleep(wait * 1000, shouldStop);
      try {
        const url = await d.fetchImageUrl(page, it.mediaId);
        await d.downloadMedia(page, it.mediaId, it.dest, url || null, { kind: "image" });
        if (!isValidOutput(it.dest, "image")) throw new Error(`Download finished but the file is missing or not an image: ${it.dest}`);
        savedPath = path.resolve(it.dest);
        break;
      } catch (err) {
        lastErr = err;
      }
    }
    if (savedPath) {
      ledger.put(it.key, { state: LedgerState.COMPLETED_LOCAL, savedPath, mediaId: it.mediaId });
      done(it, it.mediaId, savedPath, { submitted: !it.resumed, via: "agent", ...(it.agentInfo || {}) });
    } else {
      const state = LedgerState.DOWNLOAD_FAILED;
      ledger.put(it.key, { state, error: String(lastErr?.message || lastErr || "stopped"), ...(it.confirmed ? { confirmedResumeFailedRunId: runId } : {}) });
      fail(it, `Flow generated this image but the download failed: ${lastErr?.message || "stopped"}. Retry fetches it again — it will not be generated twice.`, { needsAction: true, resumable: true, ledgerState: state, submitted: true });
    }
  }

  // Stopped during downloads: those images exist on Flow and their media ids are in the ledger; the next run only downloads.
  for (const it of toDownload.slice(downloaded)) {
    fail(it, "Stopped before this image was downloaded. It was generated on Flow; Retry downloads it — it will not be generated twice.",
      { needsAction: true, resumable: true, ledgerState: LedgerState.MEDIA_ID_KNOWN, submitted: true });
  }

  // ---- 4. Scenes the agent made nothing for. In a pool run (agent-pool.js) they go back to the pool, which sends five or
  // more as another agent request and fewer through the standard path; run on its own, they use the standard path here.
  if (params.deferFallback) {
    const back = shouldStop?.() || restricted ? [] : fallback.splice(0);
    for (const it of fallback) fail(it, restricted ? `Not run: Flow restricted account ${label}.` : "Stopped before this scene could be made again — nothing was generated for it.");
    emit("BATCH_DONE", { completed, failed, total: totalAbsolute, sliceTotal: prompts.length, folder: outDir, reassign });
    return {
      completed, failed, folder: outDir, reassign, authExpired: false, restricted, coolDown,
      fallback: back.map((it) => ({ index: it.abs, prompt: it.prompt, promptKey: it.promptKey })),
    };
  }
  if (fallback.length && !shouldStop?.() && !restricted && standardSettings.agentFallback !== false) {
    emit("status", { message: `${fallback.length} scene(s) the agent did not make: using the standard Flow path` });
    const r = await d.runBatchSlice({
      ...params,
      prompts: fallback.map((it) => it.prompt),
      promptIndices: fallback.map((it) => it.abs),
      promptKeys: fallback.map((it) => it.promptKey),
      settings: standardSettings,
      deps: params.standardDeps || {},
      onProgress: (evt) => {
        if (evt.type === "BATCH_DONE") return;   // this slice reports its own BATCH_DONE below
        if (evt.type === "PROMPT_RESULT") evt.status === "done" ? completed++ : failed++;
        onProgress?.(evt);
      },
    });
    reassign.push(...(r?.reassign || []));
    if (r?.restricted) restricted = r.restricted;
  } else if (fallback.length) {
    for (const it of fallback) fail(it, restricted ? `Not run: Flow restricted account ${label}.` : "Stopped before the standard Flow path could make this scene.");
  }

  emit("BATCH_DONE", { completed, failed, total: totalAbsolute, sliceTotal: prompts.length, folder: outDir, reassign });
  return { completed, failed, folder: outDir, reassign, authExpired: false, restricted, coolDown };
}
