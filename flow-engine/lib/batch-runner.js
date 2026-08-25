import path from "node:path";
import {
  generateOneImage,
  generateOneVideo,
  downloadMedia,
  openOrCreateProject,
  waitForFlowReady,
  QuotaError,
  RateLimitError,
  FatalError,
  timing,
  models,
} from "./flow-api.js";
import { accountDownloadDir } from "./paths.js";

const MODEL_FALLBACK = models.fallbackOrder || ["NARWHAL", "GEM_PIX_2", "HARBOR_SEAL"];

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
}) {
  const emit = (type, payload) => onProgress?.({ type, ...payload });
  const downloadsRoot = settings.outputDir || undefined;
  const outDir = accountDownloadDir(folderLabel, downloadsRoot);
  const settingsLocal = { ...settings };
  let completed = 0;
  let failed = 0;
  let stopBatch = false;

  emit("status", { message: "Opening / creating Flow project…" });
  const projectId = await openOrCreateProject(page);
  await waitForFlowReady(page);
  emit("status", { message: `Project ready (${projectId.slice(0, 8)}…)`, projectId });

  const rateRetries = timing.rateLimitRetrySeconds || [60, 120];
  const quotaRetries = timing.quotaRetrySeconds || [60, 120];
  const sessRetries = timing.sessionRetrySeconds || [5, 15, 30];
  const refreshEvery = settingsLocal.refreshFrequency ?? 5;

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

    while (!done && !shouldStop?.()) {
      try {
        const mediaIds = [];
        let savedPath = null;
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
            emit("status", { message: `Saved ${name}` });
          }
        }

        if (!mediaIds.length) throw new Error(`All ${mediaKind} requests failed`);

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

        if (
          refreshEvery > 0 &&
          completed % refreshEvery === 0 &&
          i < prompts.length - 1 &&
          !shouldStop?.()
        ) {
          emit("BATCH_PROGRESS", {
            index: abs,
            total: totalAbsolute,
            status: "running",
            message: "Refreshing Flow page…",
          });
          await page.reload({ waitUntil: "domcontentloaded", timeout: 45000 });
          await waitForFlowReady(page);
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
        const waitThenRefresh = async (seconds, label) => {
          emit("BATCH_PROGRESS", {
            index: abs,
            total: totalAbsolute,
            status: "waiting",
            countdown: seconds,
            message: `${label} ${seconds}s…`,
          });
          await sleep(seconds * 1000, shouldStop);
          if (shouldStop?.()) return;
          await page.reload({ waitUntil: "domcontentloaded", timeout: 45000 });
          await waitForFlowReady(page).catch(() => {});
        };

        if (err instanceof RateLimitError) {
          if (rateAttempt < rateRetries.length) {
            await waitThenRefresh(rateRetries[rateAttempt++], "Rate limited — retrying in");
            continue;
          }
          failed++;
          done = true;
          emit("PROMPT_RESULT", { index: abs, prompt, status: "failed", error: err.message });
          emit("BATCH_PROGRESS", {
            index: abs,
            total: totalAbsolute,
            status: "failed",
            message: "Rate limit persists — skipping",
            completed,
            failed,
          });
          break;
        }

        if (err instanceof QuotaError) {
          if (rateAttempt < quotaRetries.length) {
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
          failed++;
          done = true;
          stopBatch = true;
          emit("PROMPT_RESULT", { index: abs, prompt, status: "failed", error: err.message });
          emit("BATCH_PROGRESS", {
            index: abs,
            total: totalAbsolute,
            status: "failed",
            message: "Quota exhausted — stopping this account",
            completed,
            failed,
          });
          break;
        }

        const recoverable =
          (err instanceof FatalError && err.recoverable) ||
          (!(err instanceof FatalError) &&
            !String(err.message).includes("401") &&
            !String(err.message).includes("400") &&
            !String(err.message).includes("expired"));

        if (recoverable && sessAttempt < sessRetries.length) {
          await waitThenRefresh(
            sessRetries[sessAttempt++],
            `⚠ ${String(err.message).slice(0, 50)} — retrying in`,
          );
          continue;
        }

        failed++;
        done = true;
        emit("PROMPT_RESULT", {
          index: abs,
          prompt,
          status: "failed",
          error: err.message,
        });
        emit("BATCH_PROGRESS", {
          index: abs,
          total: totalAbsolute,
          status: "failed",
          message: `Failed: ${err.message}`,
          completed,
          failed,
        });

        if (err instanceof FatalError && !err.recoverable) {
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
  });
  return { completed, failed, folder: outDir };
}
