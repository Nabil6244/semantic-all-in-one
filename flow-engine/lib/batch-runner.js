import path from "node:path";
import {
  generateOneImage,
  generateOneVideo,
  downloadMedia,
  openOrCreateProject,
  waitForFlowReady,
  checkFlowReady,
  flowReload,
  AuthExpiredError,
  EndpointRejectedError,
  QuotaError,
  RateLimitError,
  FatalError,
  MissingMediaIdError,
  timing,
  models,
} from "./flow-api.js";
import { defaults } from "../config.js";
import {
  AccountLifecycle,
  isMissingMediaIdError,
  logFlowAccount,
} from "./account-lifecycle.js";
import { accountDownloadDir } from "./paths.js";

const MODEL_FALLBACK = models.fallbackOrder || ["NARWHAL", "GEM_PIX_2", "HARBOR_SEAL"];
const DEFAULT_REFRESH =
  defaults?.flowSettings?.refreshFrequency ?? 20;

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
 * Run a contiguous prompt slice on one Playwright page.
 *
 * @param {object} opts
 * @param {import('playwright').Page} opts.page
 * @param {string[]} opts.prompts
 * @param {number[]} opts.promptIndices  absolute 0-based indices
 * @param {number} opts.totalAbsolute
 * @param {object} opts.settings
 * @param {string} opts.folderLabel  subfolder under Flow_Images
 * @param {() => boolean} opts.shouldStop
 * @param {(evt: object) => void} opts.onProgress
 * @param {string} [opts.accountId]
 * @param {string} [opts.accountLabel]
 * @param {number} [opts.workerIndex]
 */
export async function runBatchSlice({
  page,
  prompts,
  promptIndices,
  totalAbsolute,
  settings,
  folderLabel,
  shouldStop,
  onProgress,
  accountId,
  accountLabel,
  workerIndex,
}) {
  const emit = (type, payload) => onProgress?.({ type, ...payload });
  const downloadsRoot = settings.outputDir || undefined;
  const outDir = accountDownloadDir(folderLabel, downloadsRoot);
  const settingsLocal = { ...settings };
  let completed = 0;
  let failed = 0;
  let stopBatch = false;
  // Set when the account's Google session is gone, so the orchestrator can
  // mark it signed-out instead of scheduling it again next batch.
  let authExpired = false;

  const refreshEvery =
    settingsLocal.refreshFrequency != null
      ? Number(settingsLocal.refreshFrequency)
      : DEFAULT_REFRESH;
  const life = new AccountLifecycle({
    accountId: accountId || page?.__flowAccountId || "",
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
  const projectId = await openOrCreateProject(page);
  await waitForFlowReady(page);
  emit("status", { message: `Project ready (${projectId.slice(0, 8)}…)`, projectId });

  const rateRetries = timing.rateLimitRetrySeconds || [60, 120];
  const quotaRetries = timing.quotaRetrySeconds || [60, 120];
  const sessRetries = timing.sessionRetrySeconds || [5, 15, 30];
  /** Prompts that need another account after this account hit rate/quota limits. */
  const reassign = [];

  for (let i = 0; i < prompts.length && !stopBatch; i++) {
    if (shouldStop?.()) {
      emit("BATCH_PROGRESS", {
        index: promptIndices[i],
        total: totalAbsolute,
        status: "stopped",
        message: "Stopped.",
      });
      break;
    }

    const abs = promptIndices[i];
    const prompt = prompts[i];
    const mediaKind = settingsLocal.mediaKind === "video" ? "video" : "image";
    const ext = mediaKind === "video" ? "mp4" : "png";
    // Video generation is a single (slow, expensive) job per prompt — imageCount
    // only applies to the image path, matching the original EtVideo/EtImage split.
    const count = mediaKind === "video" ? 1 : settingsLocal.imageCount || 1;

    emit("BATCH_PROGRESS", {
      index: abs,
      total: totalAbsolute,
      status: "running",
      message: `Working ${i + 1}/${prompts.length} (saved ${completed}) · "${prompt.slice(0, 40)}…"`,
    });

    let done = false;
    let rateAttempt = 0;
    let sessAttempt = 0;
    life.resetRecoveryBudget();

    while (!done && !shouldStop?.()) {
      try {
        if (!life.canGenerate()) {
          throw new FatalError(
            `Account ${life.label} not ready for generation (state=${life.state})`,
            true,
          );
        }

        const mediaIds = [];
        let savedPath = null;
        await life.generate(async () => {
          for (let slot = 0; slot < count; slot++) {
            if (shouldStop?.()) break;
            if (slot > 0) await sleep(timing.imageSlotStaggerMs || 250, shouldStop);
            const generated =
              mediaKind === "video"
                ? await generateOneVideo(page, projectId, prompt, settingsLocal, abs * 10 + slot)
                : await generateOneImage(page, projectId, prompt, settingsLocal, abs * 10 + slot);
            const mediaId = generated.mediaId;
            const directUrl = generated.fifeUrl || null;
            mediaIds.push(mediaId);

            if (settingsLocal.autoDownload !== false) {
              const name =
                count > 1
                  ? `${pad(abs + 1)}-${slot + 1}.${ext}`
                  : `${pad(abs + 1)}.${ext}`;
              const dest = path.join(outDir, name);
              emit("BATCH_PROGRESS", {
                index: abs,
                total: totalAbsolute,
                status: "running",
                message: `Downloading ${name}…`,
              });
              await downloadMedia(page, mediaId, dest, directUrl);
              // Absolute path so Windows Python can resolve the file without
              // depending on cwd / mixed separators from the Node sidecar.
              savedPath = path.resolve(dest);
              const { statSync } = await import("node:fs");
              let st;
              try {
                st = statSync(savedPath);
              } catch {
                st = null;
              }
              if (!st || !st.isFile() || st.size < 64) {
                throw new Error(
                  `Download finished but file missing or empty on disk: ${savedPath}`,
                );
              }
              emit("status", { message: `Saved ${name}` });
            }
          }
        });

        if (!mediaIds.length) throw new Error(`All ${mediaKind} requests failed`);
        if (settingsLocal.autoDownload !== false && !savedPath) {
          throw new Error(`Flow ${mediaKind} finished without a saved file path`);
        }

        completed++;
        done = true;
        emit("PROMPT_RESULT", {
          index: abs,
          prompt,
          status: "done",
          mediaIds,
          path: savedPath,
        });
        emit("BATCH_PROGRESS", {
          index: abs,
          total: totalAbsolute,
          status: "done",
          message: `Saved ${completed}/${prompts.length} on this account`,
          completed,
          failed,
          path: savedPath,
        });

        // Scheduled refresh ONLY after generation+download fully complete.
        const hasMore = i < prompts.length - 1;
        if (
          life.refreshPlan.shouldRefresh(completed, { hasMorePrompts: hasMore }) &&
          !shouldStop?.()
        ) {
          const threshold = life.refreshPlan.nextThreshold;
          logFlowAccount(
            life.label,
            `refresh scheduled at ${completed}/${refreshEvery}`,
            { completed, nextThreshold: threshold },
          );
          emit("BATCH_PROGRESS", {
            index: abs,
            total: totalAbsolute,
            status: "running",
            message: "Refreshing Flow page…",
          });
          await life.refresh(async () => {
            await flowReload(
              page,
              `batch-runner:refreshEvery=${refreshEvery}+offset=${life.refreshPlan.offset}`,
              {
                waitUntil: "domcontentloaded",
                timeout: 45000,
              },
            );
            await waitForFlowReady(page);
          });
          life.refreshPlan.advanceAfterRefresh(completed);
          logFlowAccount(life.label, "resumed generation", {
            completed,
            nextThreshold: life.refreshPlan.nextThreshold,
          });
        }

        if (i < prompts.length - 1 && !shouldStop?.()) {
          const lo = (settingsLocal.delayMin ?? 3) * 1000;
          const hi = (settingsLocal.delayMax ?? 8) * 1000;
          const wait = lo + Math.random() * Math.max(0, hi - lo);
          if (wait > 0) {
            let left = Math.ceil(wait / 1000);
            emit("BATCH_PROGRESS", {
              index: promptIndices[i + 1],
              total: totalAbsolute,
              status: "waiting",
              countdown: left,
              message: `Waiting ${left}s…`,
            });
            await sleep(wait, shouldStop);
          }
        }
      } catch (err) {
        let activeErr = err;
        const waitThenRefresh = async (seconds, label, { forceReload = true } = {}) => {
          emit("BATCH_PROGRESS", {
            index: abs,
            total: totalAbsolute,
            status: "waiting",
            countdown: seconds,
            message: `${label} ${seconds}s…`,
          });
          await sleep(seconds * 1000, shouldStop);
          if (shouldStop?.()) return;

          await life.recover(async () => {
            let needReload = forceReload;
            if (!forceReload) {
              const snap = await checkFlowReady(page).catch(() => null);
              needReload = !(snap && snap.hasProject && snap.hasRecaptcha);
            }
            if (needReload) {
              if (!life.canRecoveryReload()) {
                throw new FatalError(
                  `Account ${life.label} recovery reload budget exhausted`,
                  true,
                );
              }
              life.noteRecoveryReload();
              await flowReload(page, `batch-runner:error-recovery:${label}`, {
                waitUntil: "domcontentloaded",
                timeout: 45000,
              });
            }
            // Must pass readiness — never proceed into grec.execute half-ready.
            await waitForFlowReady(page);
          });
        };

        if (activeErr instanceof RateLimitError) {
          if (rateAttempt < rateRetries.length) {
            life.resetRecoveryBudget();
            await waitThenRefresh(rateRetries[rateAttempt++], "Rate limited — retrying in");
            continue;
          }
          // Hand off to another signed-in account instead of failing the scene.
          done = true;
          reassign.push({ index: abs, prompt, reason: "rate_limit" });
          emit("PROMPT_RESULT", {
            index: abs,
            prompt,
            status: "rate_limited",
            error: activeErr.message,
            reassign: true,
          });
          emit("BATCH_PROGRESS", {
            index: abs,
            total: totalAbsolute,
            status: "waiting",
            message: "Rate limit persists — rotating account…",
            completed,
            failed,
          });
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
            emit("BATCH_PROGRESS", {
              index: abs,
              total: totalAbsolute,
              status: "waiting",
              message: `Switching model to ${nxt}`,
            });
            continue;
          }
          // This account is done for the batch — reassign current + remaining prompts.
          done = true;
          stopBatch = true;
          reassign.push({ index: abs, prompt, reason: "quota" });
          for (let j = i + 1; j < prompts.length; j++) {
            reassign.push({
              index: promptIndices[j],
              prompt: prompts[j],
              reason: "quota",
            });
          }
          emit("PROMPT_RESULT", {
            index: abs,
            prompt,
            status: "rate_limited",
            error: activeErr.message,
            reassign: true,
          });
          emit("BATCH_PROGRESS", {
            index: abs,
            total: totalAbsolute,
            status: "waiting",
            message: "Quota exhausted — rotating to another account…",
            completed,
            failed,
          });
          break;
        }

        if (activeErr instanceof EndpointRejectedError) {
          // Not the account's fault — rotating to another one would fail
          // identically, so stop this batch and say what is actually wrong.
          done = true;
          stopBatch = true;
          failed++;
          emit("PROMPT_RESULT", {
            index: abs,
            prompt,
            status: "failed",
            error: activeErr.message,
          });
          emit("BATCH_PROGRESS", {
            index: abs,
            total: totalAbsolute,
            status: "failed",
            message: activeErr.message,
            completed,
            failed,
          });
          break;
        }

        if (activeErr instanceof AuthExpiredError) {
          // Signing out is per-account, not per-scene: hand this prompt and
          // every remaining one to another signed-in account rather than
          // failing them all against a dead session.
          done = true;
          stopBatch = true;
          authExpired = true;
          reassign.push({ index: abs, prompt, reason: "auth_expired" });
          for (let j = i + 1; j < prompts.length; j++) {
            reassign.push({
              index: promptIndices[j],
              prompt: prompts[j],
              reason: "auth_expired",
            });
          }
          emit("PROMPT_RESULT", {
            index: abs,
            prompt,
            status: "rate_limited",
            error: activeErr.message,
            reassign: true,
          });
          emit("BATCH_PROGRESS", {
            index: abs,
            total: totalAbsolute,
            status: "waiting",
            message: "Account signed out — rotating to another account…",
            completed,
            failed,
          });
          break;
        }

        // Missing mediaId: classify, check page health, at most one controlled
        // reload per prompt, then readiness — never reload-storm.
        if (
          activeErr instanceof MissingMediaIdError ||
          isMissingMediaIdError(activeErr)
        ) {
          if (sessAttempt < sessRetries.length) {
            const delay = sessRetries[sessAttempt++];
            try {
              await waitThenRefresh(delay, "No mediaId — retrying in", {
                forceReload: false,
              });
              continue;
            } catch (recErr) {
              activeErr = recErr;
              // Do not spin forever when the reload budget is exhausted.
              if (
                sessAttempt < sessRetries.length &&
                !/recovery reload budget exhausted/i.test(
                  String(recErr?.message || ""),
                )
              ) {
                continue;
              }
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
            await waitThenRefresh(
              sessRetries[sessAttempt++],
              `⚠ ${String(activeErr.message).slice(0, 50)} — retrying in`,
            );
            continue;
          }
        }

        failed++;
        done = true;
        emit("PROMPT_RESULT", {
          index: abs,
          prompt,
          status: "failed",
          error: activeErr.message,
        });
        emit("BATCH_PROGRESS", {
          index: abs,
          total: totalAbsolute,
          status: "failed",
          message: `Failed: ${activeErr.message}`,
          completed,
          failed,
        });

        if (activeErr instanceof FatalError && !activeErr.recoverable) {
          stopBatch = true;
        }
      }
    }
  }

  emit("BATCH_DONE", {
    completed,
    failed,
    total: totalAbsolute,
    sliceTotal: prompts.length,
    folder: outDir,
    reassign,
  });
  return { completed, failed, folder: outDir, reassign, authExpired };
}
