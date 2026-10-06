import path from "node:path";
import fs from "node:fs";
import {
  downloadMedia as realDownloadMedia,
  resumeVideo as realResumeVideo,
  openOrCreateProject as realOpenOrCreateProject,
  createFlowProject as realCreateFlowProject,
  waitForFlowReady as realWaitForFlowReady,
  checkFlowReady as realCheckFlowReady,
  flowReload as realFlowReload,
  flowGoto as realFlowGoto,
  AuthExpiredError,
  EndpointRejectedError,
  QuotaError,
  RateLimitError,
  FatalError,
  MissingMediaIdError,
  VideoGenerationFailedError,
  timing,
  models,
  urls,
  mediaKindOf,
} from "./flow-api.js";
import { generateOneMedia as realGenerateOneMedia, resolveGenerationMode } from "./generation-dispatch.js";
import { defaults } from "../config.js";
import { AccountLifecycle, isMissingMediaIdError, logFlowAccount } from "./account-lifecycle.js";
import { accountDownloadDir } from "./paths.js";
import {
  Submission,
  submissionOf,
  tagSubmission,
  AccountRestrictedError,
  NeedsActionError,
  ResumableError,
} from "./generation-state.js";
import { LedgerState, defaultLedger, generationKey, scopeOf } from "./generation-ledger.js";

const MODEL_FALLBACK = models.fallbackOrder || ["NARWHAL", "GEM_PIX_2", "HARBOR_SEAL"];
const DEFAULT_REFRESH = defaults?.flowSettings?.refreshFrequency ?? 20;
/** Attempts to finish an accepted video (poll + final fetch) within one run, and the waits between them. */
const RESUME_WAITS_S = [0, 10, 30];
/** Download attempts within one run (each downloadMedia call already retries the CDN several times). */
const DOWNLOAD_WAITS_S = [0, 15];

function sleep(ms, shouldStop) {
  return new Promise((resolve) => {
    if (shouldStop?.() || ms <= 0) return resolve();
    const start = Date.now();
    const iv = setInterval(() => {
      if (shouldStop?.() || Date.now() - start >= ms) {
        clearInterval(iv);
        resolve();
      }
    }, Math.min(400, ms));
  });
}

function pad(n) {
  return String(n).padStart(3, "0");
}

function nextModel(current) {
  const i = MODEL_FALLBACK.indexOf(current);
  return i >= 0 && i < MODEL_FALLBACK.length - 1 ? MODEL_FALLBACK[i + 1] : null;
}

/**
 * One Flow page per account can run only one generation at a time. Each account's work (submit, poll, download) is chained
 * here, so two slices for the same account — a programming error, or two overlapping runs — can never submit concurrently
 * through the same page. Different accounts run in parallel.
 */
const accountChains = new Map();
export function withAccountLock(accountKey, fn) {
  const prev = accountChains.get(accountKey) || Promise.resolve();
  const run = prev.then(fn, fn);
  const tail = run.then(() => undefined, () => undefined);
  accountChains.set(accountKey, tail);
  tail.then(() => {
    if (accountChains.get(accountKey) === tail) accountChains.delete(accountKey);
  });
  return run;
}

/** A finished file of the expected kind is on disk (used to recognise output saved before a crash). */
export function isValidOutput(file, kind) {
  try {
    const st = fs.statSync(file, { throwIfNoEntry: false });
    if (!st || !st.isFile() || st.size < 64) return false;
    const fd = fs.openSync(file, "r");
    const head = Buffer.alloc(64);
    fs.readSync(fd, head, 0, 64, 0);
    fs.closeSync(fd);
    return mediaKindOf(head) === kind;
  } catch {
    return false;
  }
}

/** Put an existing finished file at `dest` (atomically), unless it already is `dest`. */
function placeExisting(src, dest) {
  if (path.resolve(src) === path.resolve(dest)) return path.resolve(dest);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  const tmp = `${dest}.${process.pid}.reuse.part`;
  fs.copyFileSync(src, tmp);
  fs.renameSync(tmp, dest);
  return path.resolve(dest);
}

/**
 * Run a prompt slice on one account's page.
 *
 * Every generation goes through the ledger (generation-ledger.js): its state is written BEFORE the request is sent and after
 * every step, so a failure, a stop, a crash or a later Retry resumes what exists instead of generating it again. Only a
 * failure proven to have created nothing (Submission.NOT_SUBMITTED / REJECTED) is retried as a new generation.
 *
 * @param {object} opts
 * @param {import('playwright').Page} opts.page
 * @param {string[]} opts.prompts
 * @param {number[]} opts.promptIndices  absolute 0-based indices
 * @param {(string|null)[]} [opts.promptKeys]  stable per-prompt ids from the caller (scene numbers), same order as prompts
 * @param {number} opts.totalAbsolute
 * @param {object} opts.settings
 * @param {string} opts.folderLabel  subfolder under the output folder
 * @param {() => boolean} opts.shouldStop
 * @param {(evt: object) => void} opts.onProgress
 * @param {string} [opts.accountId]
 * @param {string} [opts.accountLabel]
 * @param {number} [opts.workerIndex]
 * @param {object} [opts.deps]  replacements for the Flow calls (tests)
 */
export async function runBatchSlice({
  page,
  prompts,
  promptIndices,
  promptKeys,
  totalAbsolute,
  settings,
  folderLabel,
  shouldStop,
  onProgress,
  accountId,
  accountLabel,
  workerIndex,
  deps = {},
}) {
  const d = {
    generateOneMedia: realGenerateOneMedia,
    resumeVideo: realResumeVideo,
    downloadMedia: realDownloadMedia,
    openOrCreateProject: realOpenOrCreateProject,
    createFlowProject: realCreateFlowProject,
    waitForFlowReady: realWaitForFlowReady,
    checkFlowReady: realCheckFlowReady,
    flowReload: realFlowReload,
    flowGoto: realFlowGoto,
    sleep,
    ...deps,
  };
  const ledger = d.ledger || (await defaultLedger());
  const emit = (type, payload) => onProgress?.({ type, ...payload });
  const outDir = accountDownloadDir(folderLabel, settings.outputDir || undefined);
  const settingsLocal = { ...settings };
  const runId = settingsLocal._runId || `run-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const scope = scopeOf(settingsLocal.outputDir);
  const owner = accountId || page?.__flowAccountId || "";
  // Scenes the user explicitly asked for again (Retry / Regenerate). Only these may override a possibly-existing generation.
  const confirmedKeys = new Set((settingsLocal.confirmResubmitKeys || []).map(String));
  let completed = 0;
  let failed = 0;
  let stopBatch = false;
  let authExpired = false;
  let restricted = null;
  // Set after a UI generation whose result was never seen: its tile may still appear on this page later and must not be
  // taken for the next prompt's result, so the next UI generation starts in a fresh Flow project.
  let uiPageTainted = false;

  const refreshEvery =
    settingsLocal.refreshFrequency != null ? Number(settingsLocal.refreshFrequency) : DEFAULT_REFRESH;
  const life = new AccountLifecycle({
    accountId: owner,
    accountLabel: accountLabel || folderLabel || accountId || "account",
    workerIndex,
    refreshEvery,
    maxAccounts: timing.maxParallelAccounts || 10,
  });

  logFlowAccount(life.label, `refresh scheduled at ${life.refreshPlan.nextThreshold}/${refreshEvery}`, {
    nextThreshold: life.refreshPlan.nextThreshold,
    detail: `offset=${life.refreshPlan.offset}`,
  });

  emit("status", { message: "Opening / creating Flow project…" });
  let projectId = await d.openOrCreateProject(page);
  await d.waitForFlowReady(page);
  emit("status", { message: `Project ready (${projectId.slice(0, 8)}…)`, projectId });

  const rateRetries = timing.rateLimitRetrySeconds || [60, 120];
  const quotaRetries = timing.quotaRetrySeconds || [60, 120];
  const sessRetries = timing.sessionRetrySeconds || [5, 15, 30];
  const reassign = [];

  const failPrompt = (abs, prompt, message, extra = {}) => {
    failed++;
    emit("PROMPT_RESULT", { index: abs, prompt, status: "failed", error: message, ...extra });
    emit("BATCH_PROGRESS", { index: abs, total: totalAbsolute, status: "failed", message: `Failed: ${message}`, completed, failed });
  };

  async function moveToFreshProject() {
    const id = await d.createFlowProject(page);
    await d.flowGoto(page, urls.flowProject(id), "batch-runner:ui-result-may-arrive-late", { waitUntil: "domcontentloaded", timeout: 60000 });
    await d.waitForFlowReady(page);
    projectId = id;
    uiPageTainted = false;
    logFlowAccount(life.label, "moved to a fresh Flow project (an earlier UI result may still arrive on the old one)");
  }

  /** Poll + final-fetch an accepted video until its media id is known. Never submits anything. */
  async function finishAcceptedVideo(key, workflowId, abs, confirmed) {
    let lastErr = null;
    for (const wait of RESUME_WAITS_S) {
      if (shouldStop?.()) break;
      if (wait) {
        emit("BATCH_PROGRESS", { index: abs, total: totalAbsolute, status: "waiting", countdown: wait, message: `Video was accepted — checking it again in ${wait}s…` });
        await d.sleep(wait * 1000, shouldStop);
      }
      try {
        const r = await d.resumeVideo(page, workflowId, projectId, settingsLocal);
        ledger.put(key, { state: LedgerState.MEDIA_ID_KNOWN, mediaId: r.mediaId, fifeUrl: r.fifeUrl || null, failedStage: null });
        return r;
      } catch (err) {
        lastErr = err;
        if (err instanceof VideoGenerationFailedError) {
          ledger.put(key, { state: LedgerState.FAILED_ON_FLOW, error: err.message });
          throw new NeedsActionError(`${err.message}. Nothing to download; click Retry on this scene to generate it again.`, { ledgerState: LedgerState.FAILED_ON_FLOW, key });
        }
        // POLL_FAILED / FINAL_FETCH_FAILED: recorded on the ACCEPTED entry, resumed later, never resubmitted.
        ledger.put(key, { failedStage: err?.stage === "final" ? "final_fetch" : "poll" });
        if (err instanceof AuthExpiredError) break;   // cannot poll from a signed-out session; resumed after sign-in
        try {
          await d.waitForFlowReady(page);
        } catch {}
      }
    }
    return keepResumable(key, LedgerState.ACCEPTED, `Video was generated on Flow (job ${String(workflowId).slice(0, 8)}…) but could not be fetched yet: ${lastErr?.message || "stopped"}`, lastErr, confirmed);
  }

  /**
   * A known generation could not be finished in this run: it stays resumable (nothing is ever submitted automatically). Only
   * when the user explicitly asked for this scene again and even that run could not fetch it does the next explicit request
   * generate a new one.
   */
  function keepResumable(key, state, message, cause, confirmed) {
    ledger.put(key, { state, error: message, ...(confirmed ? { confirmedResumeFailedRunId: runId } : {}) });
    const next = confirmed
      ? "Still not fetched after your Retry; click Retry again to generate a new one instead"
      : "Retry fetches it again — it will not be generated twice";
    throw new ResumableError(`${message}. ${next}.`, { ledgerState: state, key, cause });
  }

  async function downloadKnownMedia(key, job, dest, ext, confirmed) {
    let lastErr = null;
    for (const wait of DOWNLOAD_WAITS_S) {
      if (shouldStop?.()) break;
      if (wait) await d.sleep(wait * 1000, shouldStop);
      try {
        await d.downloadMedia(page, job.mediaId, dest, job.fifeUrl || null, { kind: ext === "mp4" ? "video" : "image" });
        const st = fs.statSync(dest, { throwIfNoEntry: false });
        if (!st || !st.isFile() || st.size < 64) throw new Error(`Download finished but file missing or empty on disk: ${dest}`);
        return path.resolve(dest);
      } catch (err) {
        lastErr = err;
      }
    }
    return keepResumable(key, LedgerState.DOWNLOAD_FAILED, `Flow generated this ${ext === "mp4" ? "video" : "image"} but the download failed: ${lastErr?.message || "stopped"}`, lastErr, confirmed);
  }

  /** One generated file for one slot of one prompt: submit (or resume), finish, download. */
  async function runSlot({ abs, prompt, promptKey, slot, count, mediaKind, ext }) {
    const key = generationKey({
      mediaKind,
      prompt: promptKey != null ? `${promptKey}\u0000${prompt}` : `#${abs}\u0000${prompt}`,
      settings: settingsLocal,
      slot,
      scope,
    });
    const confirmed = promptKey != null && confirmedKeys.has(String(promptKey));
    const name = count > 1 ? `${pad(abs + 1)}-${slot + 1}.${ext}` : `${pad(abs + 1)}.${ext}`;
    const dest = path.join(outDir, name);
    const decision = ledger.decide(key, { accountId: owner, runId, confirmed, validFile: (p) => isValidOutput(p, mediaKind) });
    if (decision.action === "block") {
      throw new NeedsActionError(`Not submitted: ${decision.reason}.`, { ledgerState: decision.entry.state, key });
    }
    if (decision.action === "reuse") {
      // Already generated and saved (the app may not have picked it up before a crash): hand over the same file again.
      const savedPath = settingsLocal.autoDownload !== false ? placeExisting(decision.entry.savedPath, dest) : decision.entry.savedPath;
      ledger.put(key, { savedPath });
      emit("status", { message: `Reusing ${name}: it was already generated and saved` });
      return { mediaId: decision.entry.mediaId, savedPath, submitted: false };
    }

    let job;
    let submitted = false;
    if (decision.action === "resume") {
      const e = decision.entry;
      job = { workflowId: e.workflowId || null, mediaId: e.mediaId || null, fifeUrl: e.fifeUrl || null };
      submitted = true;
      // The process may have died after the file was saved but before it was recorded as complete: use that file.
      if (e.mediaId && e.dest && isValidOutput(e.dest, mediaKind)) {
        const savedPath = settingsLocal.autoDownload !== false ? placeExisting(e.dest, dest) : path.resolve(e.dest);
        ledger.put(key, { state: LedgerState.COMPLETED_LOCAL, savedPath });
        emit("status", { message: `Recovered ${name}: it was saved before the engine stopped` });
        return { mediaId: e.mediaId, savedPath, submitted };
      }
      emit("status", { message: `Resuming a generation Flow already has (${e.state})` });
    } else {
      // Claimed in the same tick as decide(): another slice deciding on this key from here on sees SUBMITTING and is blocked.
      ledger.put(key, {
        state: LedgerState.SUBMITTING, accountId: owner, accountLabel: life.label, mediaKind, slot, runId, projectId,
        prompt: String(prompt).slice(0, 200), workflowId: null, mediaId: null, fifeUrl: null, dest: null, savedPath: null,
        failedStage: null, confirmedResumeFailedRunId: null, error: null,
      });
      if (uiPageTainted && resolveGenerationMode(settingsLocal) !== "rpc") {
        try {
          await moveToFreshProject();
        } catch (err) {
          ledger.put(key, { state: LedgerState.FAILED_BEFORE_SUBMISSION, error: String(err?.message || err) });
          throw tagSubmission(err, Submission.NOT_SUBMITTED);
        }
        ledger.put(key, { projectId });
      }
      try {
        const g = await d.generateOneMedia(page, projectId, prompt, settingsLocal, abs * 10 + slot, mediaKind, {
          shouldStop,
          accountLabel: life.label,
          onAccepted: (workflowId) => ledger.put(key, { state: LedgerState.ACCEPTED, workflowId }),
        });
        submitted = true;
        job = { mediaId: g.mediaId, fifeUrl: g.fifeUrl || null };
        ledger.put(key, { state: LedgerState.MEDIA_ID_KNOWN, mediaId: g.mediaId, fifeUrl: g.fifeUrl || null, via: g.via || null });
      } catch (err) {
        const sub = submissionOf(err);
        if (sub === Submission.NOT_SUBMITTED) {
          ledger.put(key, { state: LedgerState.FAILED_BEFORE_SUBMISSION, error: String(err?.message || err) });
          throw err;
        }
        if (sub === Submission.REJECTED) {
          ledger.put(key, { state: LedgerState.REJECTED, error: String(err?.message || err) });
          throw err;
        }
        if (err?.pageMayShowLateResult) uiPageTainted = true;
        // Flow already accepted the job (onAccepted wrote its id) even if the error itself says less: resume, never resubmit.
        const knownWorkflow = err?.workflowId || ledger.get(key)?.workflowId || null;
        if (knownWorkflow && !err.workflowId) err.workflowId = knownWorkflow;
        if ((sub === Submission.ACCEPTED || knownWorkflow) && err.workflowId) {
          if (err instanceof VideoGenerationFailedError) {
            ledger.put(key, { state: LedgerState.FAILED_ON_FLOW, workflowId: err.workflowId, error: err.message });
            throw new NeedsActionError(`${err.message}. Nothing to download; click Retry on this scene to generate it again.`, { ledgerState: LedgerState.FAILED_ON_FLOW, key });
          }
          ledger.put(key, { state: LedgerState.ACCEPTED, workflowId: err.workflowId, failedStage: err?.stage === "final" ? "final_fetch" : "poll" });
          job = { workflowId: err.workflowId, mediaId: null, fifeUrl: null };
          submitted = true;
        } else {
          ledger.put(key, { state: LedgerState.SUBMITTED_UNKNOWN, error: String(err?.message || err) });
          throw new NeedsActionError(
            `Not resubmitted: Flow may already have accepted this request (${String(err?.message || err).slice(0, 160)}). ` +
              "Check the Flow project; click Retry on this scene to generate it again.",
            { ledgerState: LedgerState.SUBMITTED_UNKNOWN, key },
          );
        }
      }
    }

    if (!job.mediaId && job.workflowId) job = { ...job, ...(await finishAcceptedVideo(key, job.workflowId, abs, confirmed)) };
    if (!job.mediaId) {
      // A resumable entry with neither id cannot be resumed (should not happen): never guess, never resubmit.
      ledger.put(key, { state: LedgerState.SUBMITTED_UNKNOWN });
      throw new NeedsActionError("Not resubmitted: the earlier request's result could not be identified. Click Retry on this scene to generate it again.", { key });
    }

    let savedPath = null;
    if (settingsLocal.autoDownload !== false) {
      // Where the file is going, recorded BEFORE writing it: a crash after the save is recognised next time.
      ledger.put(key, { dest: path.resolve(dest) });
      emit("BATCH_PROGRESS", { index: abs, total: totalAbsolute, status: "running", message: `Downloading ${name}…` });
      savedPath = await downloadKnownMedia(key, job, dest, ext, confirmed);
      emit("status", { message: `Saved ${name}` });
    }
    ledger.put(key, { state: LedgerState.COMPLETED_LOCAL, savedPath, mediaId: job.mediaId });
    return { mediaId: job.mediaId, savedPath, submitted };
  }

  for (let i = 0; i < prompts.length && !stopBatch; i++) {
    if (shouldStop?.()) {
      emit("BATCH_PROGRESS", { index: promptIndices[i], total: totalAbsolute, status: "stopped", message: "Stopped." });
      break;
    }

    const abs = promptIndices[i];
    const prompt = prompts[i];
    const promptKey = promptKeys?.[i] ?? null;
    const mediaKind = settingsLocal.mediaKind === "video" ? "video" : "image";
    const ext = mediaKind === "video" ? "mp4" : "png";
    // Video is one job per prompt; imageCount only applies to images.
    const count = mediaKind === "video" ? 1 : settingsLocal.imageCount || 1;

    if (!String(prompt || "").trim()) {
      failPrompt(abs, prompt, "The prompt is empty — nothing was sent to Flow.");
      continue;
    }

    emit("BATCH_PROGRESS", {
      index: abs,
      total: totalAbsolute,
      status: "running",
      message: `Working ${i + 1}/${prompts.length} (saved ${completed}) · "${prompt.slice(0, 40)}…"`,
    });

    let done = false;
    let rateAttempt = 0;
    let sessAttempt = 0;
    let anySubmitted = false;
    /** Slots already finished for this prompt: never generated again when another slot is retried. */
    const slotResults = [];
    life.resetRecoveryBudget();

    while (!done && !shouldStop?.()) {
      try {
        if (!life.canGenerate()) {
          throw new FatalError(`Account ${life.label} not ready for generation (state=${life.state})`, true);
        }

        await withAccountLock(owner || life.label, () => life.generate(async () => {
          for (let slot = 0; slot < count; slot++) {
            if (shouldStop?.()) break;
            if (slotResults[slot]) continue;
            if (slot > 0) await d.sleep(timing.imageSlotStaggerMs || 250, shouldStop);
            const r = await runSlot({ abs, prompt, promptKey, slot, count, mediaKind, ext });
            anySubmitted = anySubmitted || r.submitted;
            slotResults[slot] = r;
          }
        }));

        const results = slotResults.filter(Boolean);
        if (results.length < count) {
          if (shouldStop?.()) break;
          throw new Error(`Only ${results.length} of ${count} ${mediaKind}s finished`);
        }
        const mediaIds = results.map((r) => r.mediaId);
        const savedPath = results[results.length - 1].savedPath;
        if (settingsLocal.autoDownload !== false && !savedPath) {
          throw new Error(`Flow ${mediaKind} finished without a saved file path`);
        }

        completed++;
        done = true;
        emit("PROMPT_RESULT", { index: abs, prompt, status: "done", mediaIds, path: savedPath, submitted: anySubmitted });
        emit("BATCH_PROGRESS", {
          index: abs, total: totalAbsolute, status: "done", message: `Saved ${completed}/${prompts.length} on this account`,
          completed, failed, path: savedPath,
        });

        // Scheduled refresh ONLY after generation+download fully complete.
        const hasMore = i < prompts.length - 1;
        if (life.refreshPlan.shouldRefresh(completed, { hasMorePrompts: hasMore }) && !shouldStop?.()) {
          logFlowAccount(life.label, `refresh scheduled at ${completed}/${refreshEvery}`, { completed, nextThreshold: life.refreshPlan.nextThreshold });
          emit("BATCH_PROGRESS", { index: abs, total: totalAbsolute, status: "running", message: "Refreshing Flow page…" });
          await life.refresh(async () => {
            await d.flowReload(page, `batch-runner:refreshEvery=${refreshEvery}+offset=${life.refreshPlan.offset}`, {
              waitUntil: "domcontentloaded",
              timeout: 45000,
            });
            await d.waitForFlowReady(page);
          });
          life.refreshPlan.advanceAfterRefresh(completed);
          logFlowAccount(life.label, "resumed generation", { completed, nextThreshold: life.refreshPlan.nextThreshold });
        }

        if (i < prompts.length - 1 && !shouldStop?.()) {
          const lo = (settingsLocal.delayMin ?? 3) * 1000;
          const hi = (settingsLocal.delayMax ?? 8) * 1000;
          const wait = lo + Math.random() * Math.max(0, hi - lo);
          if (wait > 0) {
            emit("BATCH_PROGRESS", {
              index: promptIndices[i + 1], total: totalAbsolute, status: "waiting", countdown: Math.ceil(wait / 1000),
              message: `Waiting ${Math.ceil(wait / 1000)}s…`,
            });
            await d.sleep(wait, shouldStop);
          }
        }
      } catch (err) {
        let activeErr = err;

        // 1. The generation may exist (or does): never generated again in this run — a person decides, or a later run resumes.
        if (err instanceof NeedsActionError || err instanceof ResumableError) {
          done = true;
          failPrompt(abs, prompt, err.message, {
            needsAction: true, resumable: err instanceof ResumableError, ledgerState: err.ledgerState,
            submitted: anySubmitted || err instanceof ResumableError,
          });
          continue;
        }
        // 2. Google is restricting this account: stop it here, retry nothing, hand nothing to another account.
        if (err instanceof AccountRestrictedError) {
          done = true;
          stopBatch = true;
          restricted = err.reason;
          failPrompt(abs, prompt, err.message, { restricted: true });
          for (let j = i + 1; j < prompts.length; j++) {
            failPrompt(promptIndices[j], prompts[j], `Not run: Flow restricted account ${life.label} (${err.reason}).`, { restricted: true });
          }
          break;
        }
        // 3. Defence in depth: anything that may have created a generation and was not converted above.
        const sub = submissionOf(err);
        if (sub === Submission.UNKNOWN || sub === Submission.ACCEPTED) {
          done = true;
          failPrompt(abs, prompt, `Not resubmitted: ${err?.message || err}. Click Retry to generate it again.`, { needsAction: true, submitted: true });
          continue;
        }

        // From here on the failure is proven to have created nothing: retrying generates nothing twice.
        const waitThenRefresh = async (seconds, label, { forceReload = true } = {}) => {
          emit("BATCH_PROGRESS", { index: abs, total: totalAbsolute, status: "waiting", countdown: seconds, message: `${label} ${seconds}s…` });
          await d.sleep(seconds * 1000, shouldStop);
          if (shouldStop?.()) return;
          await life.recover(async () => {
            let needReload = forceReload;
            if (!forceReload) {
              const snap = await d.checkFlowReady(page).catch(() => null);
              needReload = !(snap && snap.hasProject && snap.hasRecaptcha);
            }
            if (needReload) {
              if (!life.canRecoveryReload()) {
                throw new FatalError(`Account ${life.label} recovery reload budget exhausted`, true);
              }
              life.noteRecoveryReload();
              await d.flowReload(page, `batch-runner:error-recovery:${label}`, { waitUntil: "domcontentloaded", timeout: 45000 });
            }
            await d.waitForFlowReady(page);
          });
        };

        if (activeErr instanceof RateLimitError) {
          if (rateAttempt < rateRetries.length) {
            life.resetRecoveryBudget();
            await waitThenRefresh(rateRetries[rateAttempt++], "Rate limited — retrying in");
            continue;
          }
          done = true;
          reassign.push({ index: abs, prompt, promptKey, reason: "rate_limit" });
          emit("PROMPT_RESULT", { index: abs, prompt, status: "rate_limited", error: activeErr.message, reassign: true });
          emit("BATCH_PROGRESS", { index: abs, total: totalAbsolute, status: "waiting", message: "Rate limit persists — rotating account…", completed, failed });
          break;
        }

        if (activeErr instanceof QuotaError) {
          if (rateAttempt < quotaRetries.length) {
            life.resetRecoveryBudget();
            await waitThenRefresh(quotaRetries[rateAttempt++], "Quota hit — retrying in");
            continue;
          }
          const nxt = nextModel(settingsLocal.model);
          if (nxt) {
            settingsLocal.model = nxt;
            rateAttempt = 0;
            emit("BATCH_PROGRESS", { index: abs, total: totalAbsolute, status: "waiting", message: `Switching model to ${nxt}` });
            continue;
          }
          done = true;
          stopBatch = true;
          reassign.push({ index: abs, prompt, promptKey, reason: "quota" });
          for (let j = i + 1; j < prompts.length; j++) {
            reassign.push({ index: promptIndices[j], prompt: prompts[j], promptKey: promptKeys?.[j] ?? null, reason: "quota" });
          }
          emit("PROMPT_RESULT", { index: abs, prompt, status: "rate_limited", error: activeErr.message, reassign: true });
          emit("BATCH_PROGRESS", { index: abs, total: totalAbsolute, status: "waiting", message: "Quota exhausted — rotating to another account…", completed, failed });
          break;
        }

        if (activeErr instanceof EndpointRejectedError) {
          // Not the account's fault — another account would fail identically.
          done = true;
          stopBatch = true;
          failPrompt(abs, prompt, activeErr.message);
          break;
        }

        if (activeErr instanceof AuthExpiredError) {
          // Signed out before anything was submitted: hand this prompt and the rest to a signed-in account.
          done = true;
          stopBatch = true;
          authExpired = true;
          reassign.push({ index: abs, prompt, promptKey, reason: "auth_expired" });
          for (let j = i + 1; j < prompts.length; j++) {
            reassign.push({ index: promptIndices[j], prompt: prompts[j], promptKey: promptKeys?.[j] ?? null, reason: "auth_expired" });
          }
          emit("PROMPT_RESULT", { index: abs, prompt, status: "rate_limited", error: activeErr.message, reassign: true });
          emit("BATCH_PROGRESS", { index: abs, total: totalAbsolute, status: "waiting", message: "Account signed out — rotating to another account…", completed, failed });
          break;
        }

        // A refused or unsent request with no media id: check page health, at most one controlled reload per prompt.
        if (activeErr instanceof MissingMediaIdError || isMissingMediaIdError(activeErr)) {
          if (sessAttempt < sessRetries.length) {
            const delay = sessRetries[sessAttempt++];
            try {
              await waitThenRefresh(delay, "No mediaId — retrying in", { forceReload: false });
              continue;
            } catch (recErr) {
              activeErr = recErr;
              if (sessAttempt < sessRetries.length && !/recovery reload budget exhausted/i.test(String(recErr?.message || ""))) {
                continue;
              }
            }
          }
          // Live Oct 6: NARWHAL returns bare gRPC 5 with no media on every account; GEM_PIX_2 still works.
          // After same-model retries are exhausted, step to the next model (same as QuotaError) rather than failing the scene.
          if (activeErr instanceof MissingMediaIdError || isMissingMediaIdError(activeErr)) {
            const nxt = nextModel(settingsLocal.model);
            if (nxt) {
              settingsLocal.model = nxt;
              sessAttempt = 0;
              life.resetRecoveryBudget();
              emit("BATCH_PROGRESS", { index: abs, total: totalAbsolute, status: "waiting", message: `Switching model to ${nxt}` });
              continue;
            }
          }
        } else {
          const recoverable =
            (activeErr instanceof FatalError && activeErr.recoverable) ||
            (!(activeErr instanceof FatalError) &&
              !String(activeErr.message).includes("401") &&
              !String(activeErr.message).includes("400") &&
              !String(activeErr.message).includes("expired"));
          if (recoverable && sessAttempt < sessRetries.length) {
            life.resetRecoveryBudget();
            await waitThenRefresh(sessRetries[sessAttempt++], `⚠ ${String(activeErr.message).slice(0, 50)} — retrying in`);
            continue;
          }
        }

        done = true;
        failPrompt(abs, prompt, activeErr.message);
        if (activeErr instanceof FatalError && !activeErr.recoverable) stopBatch = true;
      }
    }
  }

  emit("BATCH_DONE", { completed, failed, total: totalAbsolute, sliceTotal: prompts.length, folder: outDir, reassign });
  return { completed, failed, folder: outDir, reassign, authExpired, restricted };
}
