import { generateOneImage, generateOneVideo } from "./flow-api.js";
import { generateOneImageViaUI, generateOneVideoViaUI } from "./flow-ui-experiment.js";
import { resolveGenerationMode as configuredMode, GENERATION_MODES } from "../config.js";
import { Submission, AccountRestrictedError } from "./generation-state.js";
import { logFlowAccount } from "./account-lifecycle.js";

/** rpc | ui | rpc_then_ui for these settings; config.js is the one place the default lives. */
export function resolveGenerationMode(settings) {
  const m = String(settings?.generationMode ?? "").trim().toLowerCase();
  return GENERATION_MODES.has(m) ? m : configuredMode();
}

/**
 * May a failed RPC attempt be followed by a UI attempt for the same prompt? Only when the RPC request certainly never reached
 * Google (the page was not ready, no token could be made, the in-page check failed before sending). Never after:
 *   - an unknown outcome (timeout, lost connection, unreadable answer, navigation during the call): it may have been accepted;
 *   - any answer from Google (rate limit, quota, sign-out, refusal): the UI would be the same request through another door;
 *   - an account restriction (UNUSUAL_ACTIVITY): a stop condition, never retried another way.
 */
export function mayFallBackToUi(err) {
  if (!err || err instanceof AccountRestrictedError) return false;
  return err.submission === Submission.NOT_SUBMITTED;
}

/**
 * Generate one image or video in the configured mode. Errors always carry `submission` (see generation-state.js).
 * `onAccepted(workflowId)` is called as soon as Flow has accepted an RPC video job, before polling.
 *
 * @returns {Promise<{ mediaId: string, fifeUrl?: string | null, generateClicked?: boolean, via: "rpc" | "ui" }>}
 */
export async function generateOneMedia(
  page,
  projectId,
  prompt,
  settings,
  promptIndex,
  mediaKind,
  { shouldStop, accountLabel, forceUi = false, onAccepted, impl = {} } = {},
) {
  const mode = forceUi ? "ui" : resolveGenerationMode(settings);
  const rpcImage = impl.generateOneImage || generateOneImage;
  const rpcVideo = impl.generateOneVideo || generateOneVideo;
  const uiImage = impl.generateOneImageViaUI || generateOneImageViaUI;
  const uiVideo = impl.generateOneVideoViaUI || generateOneVideoViaUI;

  const runRpc = async () => {
    const out =
      mediaKind === "video"
        ? await rpcVideo(page, projectId, prompt, settings, promptIndex, { onAccepted })
        : await rpcImage(page, projectId, prompt, settings, promptIndex);
    return { ...out, via: "rpc" };
  };
  const runUi = async () => {
    const out =
      mediaKind === "video"
        ? await uiVideo(page, projectId, prompt, settings, promptIndex, { shouldStop })
        : await uiImage(page, projectId, prompt, settings, promptIndex);
    return { ...out, via: "ui" };
  };

  if (mode === "ui") return runUi();
  if (mode === "rpc") return runRpc();

  try {
    return await runRpc();
  } catch (err) {
    if (!mayFallBackToUi(err)) throw err;
    logFlowAccount(
      accountLabel || "account",
      `RPC could not be sent (${String(err.message || err).slice(0, 100)}) — using the Flow UI instead`,
    );
    return runUi();
  }
}
