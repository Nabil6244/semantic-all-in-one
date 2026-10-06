import {
  listAccounts,
  createAccount,
  updateAccount,
  removeAccount,
  getAccount,
  getVideoLoads,
  addVideoLoad,
} from "./store.js";
import {
  openAccountBrowser,
  closeAccountBrowser,
  gotoFlow,
  closeAllBrowsers,
  openBrowserCount,
  inspectAccountPage,
} from "./accounts.js";
import {
  checkAuthStatus,
  dismissBlockingOverlays,
  openOrCreateProject,
  waitForFlowReady,
  logFlowNav,
} from "./flow-api.js";
import { runBatchSlice } from "./batch-runner.js";
import { accountIdentity } from "./profile-identity.js";
import { DOWNLOADS_ROOT } from "./paths.js";
import { timing } from "../config.js";
import fs from "node:fs";
import { defaultLedger, generationKey, scopeOf, LedgerState } from "./generation-ledger.js";

/** @type {Set<(msg: object) => void>} */
const listeners = new Set();

let stopAll = false;
let running = false;
/** Serialize GENERATE so concurrent Retry / asset jobs never race the running flag. */
let generateChain = Promise.resolve();
const accountProgress = new Map();
/** Throttle full STATE broadcasts during high-frequency BATCH_PROGRESS. */
let lastProgressStateAt = 0;

/** True when preparation failed because the Google session is gone (not a transient SPA glitch). */
export function isSignedOutPrepareError(err) {
  const msg = String(err?.message || err || "");
  return /not signed in/i.test(msg);
}

/** Honest failure text after rotation — do not blame rate limit/quota when accounts were signed out. */
export function failMessageForPending(item, selected = [], exhaustedAccounts = new Set()) {
  const reason = String(item?.reason || "");
  if (reason === "prepare_failed" || isSignedOutPrepareError(item)) {
    return "No signed-in Flow accounts could open for this scene. Open Accounts, sign in again, then Retry.";
  }
  if (reason === "auth_expired") {
    return "Flow signed out during generation. Sign in again in Accounts, then Retry this scene.";
  }
  if (reason === "quota") {
    return "Flow quota reached on every available account — skipping";
  }
  return "Rate limit / quota persists after account rotation — skipping";
}

/**
 * Cap simultaneous Chrome/Flow workers.
 *
 * Real-world: 1–5 accounts OK, ~10 starts hanging, 20 hangs. Never fan out to
 * every signed-in account just because the prompt count is large — queue the
 * remaining work onto the active worker pool / standby rotation instead.
 */
export function computeFlowWorkerCount(promptCount, accountCount, maxParallel) {
  const prompts = Math.max(0, Number(promptCount) || 0);
  const accounts = Math.max(0, Number(accountCount) || 0);
  const cap = Math.min(
    10,
    Math.max(1, Number(maxParallel) || timing.maxParallelAccounts || 10),
  );
  if (prompts <= 0 || accounts <= 0) return 0;
  return Math.min(accounts, prompts, cap);
}

function broadcast(msg) {
  for (const fn of listeners) {
    try {
      fn(msg);
    } catch {}
  }
}

export function onHudMessage(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** The Google address this account's profile is signed into. The profile's own record wins over the page scan, which
 *  finds nothing on today's Flow page (only an avatar) and could pick up an unrelated address; the saved one is the last
 *  known, so a signed-out row still says which Gmail to sign back in with. */
function knownEmail(a, st = null) {
  return accountIdentity(a.id)?.email || st?.email || a.email || null;
}

function accountPublic(a) {
  const prog = accountProgress.get(a.id) || {
    status: "idle",
    message: "",
    completed: 0,
    failed: 0,
    total: 0,
  };
  return {
    id: a.id,
    label: a.label,
    email: knownEmail(a),
    authenticated: !!a.authenticated,
    lastChecked: a.lastChecked || 0,
    progress: prog,
  };
}

export function getState() {
  return {
    type: "STATE",
    accounts: listAccounts().map(accountPublic),
    running,
    downloadsRoot: DOWNLOADS_ROOT,
    generateError: null,
  };
}

export function pushState(extra = {}) {
  broadcast({ ...getState(), ...extra });
}

export async function addAccount(label) {
  const a = createAccount(label);
  accountProgress.set(a.id, { status: "idle", message: "Added — sign in next" });
  pushState();
  return a;
}

/**
 * Open a real Chrome window for this account so the user can sign in once.
 * Polls until session token appears (or timeout / cancel).
 */
export async function loginAccount(accountId, { timeoutMs = 10 * 60 * 1000 } = {}) {
  const a = getAccount(accountId);
  if (!a) throw new Error("Unknown account");

  accountProgress.set(accountId, {
    status: "login",
    message: "Browser opened — sign in to Google Flow…",
  });
  pushState();

  const { page } = await openAccountBrowser(accountId, { headed: true });
  await gotoFlow(page);

  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (stopAll) break;
    const st = await checkAuthStatus(page);
    if (st.authenticated) {
      updateAccount(accountId, {
        authenticated: true,
        email: knownEmail(a, st),
        lastChecked: Date.now(),
      });
      accountProgress.set(accountId, {
        status: "idle",
        message: "Signed in",   // the address has its own place in the Accounts row
      });
      pushState();
      return getAccount(accountId);
    }
    accountProgress.set(accountId, {
      status: "login",
      message: "Waiting for Google sign-in…",
    });
    pushState();
    await new Promise((r) => setTimeout(r, 2500));
  }

  accountProgress.set(accountId, {
    status: "error",
    message: "Sign-in timed out — click Sign in again",
  });
  pushState();
  throw new Error("Sign-in timed out");
}

export async function refreshAccount(accountId) {
  const a = getAccount(accountId);
  if (!a) throw new Error("Unknown account");

  accountProgress.set(accountId, { status: "checking", message: "Checking…" });
  pushState();

  try {
    const { page } = await openAccountBrowser(accountId, { headed: true });
    await gotoFlow(page);
    const st = await checkAuthStatus(page);
    updateAccount(accountId, {
      authenticated: !!st.authenticated,
      email: knownEmail(a, st),
      lastChecked: Date.now(),
    });
    accountProgress.set(accountId, {
      status: st.authenticated ? "idle" : "error",
      message: st.authenticated
        ? "OK"
        : "Not signed in — click Sign in",
    });
  } catch (e) {
    updateAccount(accountId, { authenticated: false, lastChecked: Date.now() });
    accountProgress.set(accountId, {
      status: "error",
      message: e.message,
    });
  }
  pushState();
}

export async function refreshAll() {
  for (const a of listAccounts()) {
    await refreshAccount(a.id);
  }
}

export async function renameAccount(accountId, label) {
  updateAccount(accountId, { label: String(label || "").trim() || "Account" });
  pushState();
}

export async function deleteAccount(accountId) {
  await closeAccountBrowser(accountId);
  // Leave profile dir on disk so re-add can reuse cookies if same id — but we
  // remove the registry entry. Optionally wipe profile:
  try {
    const { profileDir } = await import("./paths.js");
    fs.rmSync(profileDir(accountId), { recursive: true, force: true });
  } catch {}
  removeAccount(accountId);
  accountProgress.delete(accountId);
  pushState();
}

/**
 * Warm each account: open browser, ensure auth, create a fresh project.
 * Called automatically at the start of Generate.
 */
async function prepareAccount(accountId, label) {
  accountProgress.set(accountId, {
    status: "preparing",
    message: "Opening browser + creating project…",
    completed: 0,
    failed: 0,
    total: 0,
  });
  pushState();

  const { page } = await openAccountBrowser(accountId, { headed: true });
  await gotoFlow(page);
  await dismissBlockingOverlays(page);
  let st = await checkAuthStatus(page);
  if (!st.authenticated) {
    await dismissBlockingOverlays(page);
    await new Promise((r) => setTimeout(r, 800));
    st = await checkAuthStatus(page);
  }
  if (!st.authenticated) {
    // Keep the registry honest: a single-prompt batch only opens the first
    // "authenticated" account, then rotates. Leaving a signed-out account marked
    // signed-in made every Generate burn ~60s×3 retries on dead profiles before
    // the Python idle timeout killed the batch (Accounts 2–4 on 2026-10-05).
    updateAccount(accountId, { authenticated: false, lastChecked: Date.now() });
    try {
      await closeAccountBrowser(accountId);
    } catch {}
    accountProgress.set(accountId, {
      status: "error",
      message: "Signed out — open Accounts and sign in again",
    });
    pushState();
    throw new Error(`Account "${label}" is not signed in`);
  }
  updateAccount(accountId, {
    authenticated: true,
    email: knownEmail(getAccount(accountId) || { id: accountId }, st),   // st.email alone was null and wiped the saved address
    lastChecked: Date.now(),
  });

  const projectId = await openOrCreateProject(page);
  await waitForFlowReady(page);
  accountProgress.set(accountId, {
    status: "ready",
    message: `Project ${projectId.slice(0, 8)}…`,
    projectId,
  });
  pushState();
  return page;
}

/**
 * Order accounts so the LEAST cumulatively-loaded gets the biggest slice.
 *
 * splitPrompts() hands its `rem` extra prompts to the FIRST slices, and
 * slices[i] belongs to workers[i]. Ordering workers by ascending cumulative
 * VIDEO load therefore routes those extras to the accounts that have run the
 * fewest video jobs so far — without touching splitPrompts or its <=1
 * per-batch invariant, which still holds for any ordering.
 *
 * VIDEO only: IMAGE is free, so image batches keep their existing order.
 * Ties break on the account's original position, so the result is
 * deterministic rather than dependent on Map/sort instability.
 */
export function orderWorkersByVideoLoad(workers, isVideo, loadsOverride) {
  if (!isVideo || workers.length < 2) return workers;
  let loads = loadsOverride;
  if (!loads) {
    try {
      loads = getVideoLoads();
    } catch {
      return workers;             // fairness is best-effort, never fatal
    }
  }
  return workers
    .map((a, i) => ({ a, i, load: loads.get(a.id) || 0 }))
    .sort((x, y) => x.load - y.load || x.i - y.i)
    .map((e) => e.a);
}

export function splitPrompts(prompts, n, keys = null) {
  const slices = Array.from({ length: n }, () => ({
    prompts: [],
    indices: [],
    keys: [],
  }));
  if (n === 0) return slices;
  const base = Math.floor(prompts.length / n);
  let rem = prompts.length % n;
  let offset = 0;
  for (let i = 0; i < n; i++) {
    const size = base + (rem > 0 ? 1 : 0);
    if (rem > 0) rem--;
    for (let j = 0; j < size; j++) {
      slices[i].prompts.push(prompts[offset]);
      slices[i].indices.push(offset);
      slices[i].keys.push(keys ? keys[offset] ?? null : null);
      offset++;
    }
  }
  return slices;
}

/**
 * Queue GENERATE calls. A leftover Node process after app relaunch used to keep
 * `running === true` forever (STOP only sets stopAll); Retry then threw
 * "A batch is already running" for every scene. Soft-stop nudges an active
 * batch; force-reset clears a stuck flag so the next job can start.
 */
export function generate(opts) {
  const run = generateChain.then(() => runGenerate(opts));
  // Keep the chain alive after failures so later jobs still run.
  generateChain = run.catch(() => {});
  return run;
}

/**
 * Prompts whose generation Flow already accepted on a specific account (ledger state ACCEPTED / MEDIA_ID_KNOWN /
 * DOWNLOAD_FAILED) can only be resumed from that account. Move each into its owner's slice when the owner is a worker,
 * or add the owner as a worker when it is a signed-in standby. Returns the (possibly extended) worker list and slices.
 */
export function routeToOwners(workers, slices, selected, ownerOf) {
  const outWorkers = [...workers];
  const outSlices = slices.map((sl) => ({ prompts: [...sl.prompts], indices: [...sl.indices], keys: [...(sl.keys || [])] }));
  for (let w = 0; w < outSlices.length; w++) {
    for (let j = outSlices[w].indices.length - 1; j >= 0; j--) {
      const owner = ownerOf(outSlices[w].indices[j]);
      if (!owner || owner === outWorkers[w].id) continue;
      let target = outWorkers.findIndex((a) => a.id === owner);
      if (target < 0) {
        const standby = selected.find((a) => a.id === owner);
        if (!standby) continue;             // owner not available: the batch runner reports it, never resubmits
        outWorkers.push(standby);
        outSlices.push({ prompts: [], indices: [], keys: [] });
        target = outWorkers.length - 1;
      }
      for (const field of ["prompts", "indices", "keys"]) {
        const [v] = outSlices[w][field].splice(j, 1);
        outSlices[target][field].push(v);
      }
    }
  }
  return { workers: outWorkers, slices: outSlices };
}

async function runGenerate({ prompts, settings, accountIds, promptKeys = null }) {
  // Wait for a live batch; if the flag is stuck with no work, force-clear it.
  const waitDeadline = Date.now() + 15_000;
  while (running) {
    stopAll = true;
    if (Date.now() >= waitDeadline) {
      running = false;
      break;
    }
    await new Promise((r) => setTimeout(r, 250));
  }

  const all = listAccounts();
  const selected = (accountIds?.length
    ? all.filter((a) => accountIds.includes(a.id))
    : all
  ).filter((a) => a.authenticated);

  const donePayload = { type: "GENERATE_DONE", outputDir: settings?.outputDir || null };

  if (!selected.length) {
    pushState({
      generateError:
        "No signed-in accounts. Add accounts and complete Sign in first.",
    });
    broadcast(donePayload);
    return;
  }
  if (!prompts?.length) {
    pushState({ generateError: "Paste at least one prompt." });
    broadcast(donePayload);
    return;
  }

  stopAll = false;
  running = true;
  // One id per run: the ledger uses it to tell "the user was told in an earlier run and asked again" from "this run".
  settings = { ...settings, _runId: `run-${Date.now()}-${Math.random().toString(36).slice(2, 8)}` };

  // Bounded Chrome fan-out — never open every signed-in account at once.
  // Unused authenticated accounts remain on standby for rate-limit rotation.
  const workerCount = computeFlowWorkerCount(
    prompts.length,
    selected.length,
    timing.maxParallelAccounts,
  );
  // Only VIDEO consumes Flow credits; IMAGE is free and keeps existing order.
  const isVideoBatch = String(settings?.mediaKind || "").toLowerCase() === "video";
  // Order BEFORE truncating: slicing first would pick the first `workerCount`
  // accounts by list order, so a low-load account further down the list could
  // never be reached whenever prompts.length < selected.length (the common
  // retry case). For IMAGE the ordering is a no-op, so this stays exactly
  // `selected.slice(0, workerCount)` as before.
  const workers = orderWorkersByVideoLoad(selected, isVideoBatch).slice(0, workerCount);
  for (const a of selected) {
    const used = workers.some((w) => w.id === a.id);
    accountProgress.set(a.id, {
      status: "idle",
      message: used ? "Starting…" : "Standby (rate-limit rotation)",
      completed: 0,
      failed: 0,
      total: 0,
    });
  }
  pushState({ generateError: null });

  /** @type {Map<number, Set<string>>} */
  const triedByIndex = new Map();
  /** Accounts that hit hard quota and should not receive more work this run. */
  const exhaustedAccounts = new Set();
  const total = prompts.length;
  let caught = null;

  const markTried = (index, accountId) => {
    if (!triedByIndex.has(index)) triedByIndex.set(index, new Set());
    triedByIndex.get(index).add(accountId);
  };

  const remainingAccountsFor = (index) =>
    selected.filter(
      (a) => !exhaustedAccounts.has(a.id) && !(triedByIndex.get(index) || new Set()).has(a.id),
    );

  /**
   * Get a ready page for this account, retrying transient preparation failures.
   *
   * A single throw here used to condemn the account's ENTIRE slice: runPass
   * catches it once, reassigns every prompt as "prepare_failed" and marks the
   * account exhausted. On a 100+ scene project all workers start navigating at
   * the same moment, so a transient "Execution context was destroyed" during
   * that first navigation failed hundreds of scenes instantly — which is what
   * a whole run of images falling back to stock actually was.
   *
   * Preparation is cheap and generates nothing, so retrying it costs no Flow
   * credit; only a genuinely broken account reaches the throw now.
   */
  async function ensurePrepared(account, attempts = 3) {
    const { getPage } = await import("./accounts.js");
    let lastErr;
    for (let attempt = 1; attempt <= attempts; attempt++) {
      try {
        let page = getPage(account.id);
        if (!page || page.isClosed()) {
          await prepareAccount(account.id, account.label);
          page = getPage(account.id);
        } else {
          // Reused Chrome window — ensure we're on a live project, not mid-navigation.
          await openOrCreateProject(page);
          await waitForFlowReady(page);
        }
        if (!page) throw new Error("Browser closed for " + account.label);
        return page;
      } catch (e) {
        lastErr = e;
        // Signed-out is permanent for this run: do not sleep/retry on the same
        // dead /about tab (that used to consume the whole 180s idle budget).
        if (isSignedOutPrepareError(e)) {
          updateAccount(account.id, { authenticated: false, lastChecked: Date.now() });
          try {
            await closeAccountBrowser(account.id);
          } catch {}
          accountProgress.set(account.id, {
            status: "error",
            message: "Signed out — open Accounts and sign in again",
          });
          pushState();
          break;
        }
        if (stopAll || attempt >= attempts) break;
        accountProgress.set(account.id, {
          status: "checking",
          message: `Preparing… (attempt ${attempt + 1}/${attempts})`,
        });
        pushState();
        // Let the SPA finish whatever navigation broke the last attempt.
        // This 3000*attempt sleep is a known ~3–4s delayed re-entry point —
        // log it so a visible refresh after that delay is attributable.
        const backoffMs = 3000 * attempt;
        logFlowNav(getPage(account.id), "ensurePrepared.retry", String(e?.message || e), {
          accountId: account.id,
          targetUrl: `backoffMs=${backoffMs} nextAttempt=${attempt + 1}/${attempts}`,
        });
        await new Promise((r) => setTimeout(r, backoffMs));
      }
    }
    throw lastErr || new Error("Could not prepare " + account.label);
  }

  /**
   * Run prompt slices on the given accounts in parallel.
   * Returns items that need another account (rate limit / quota handoff).
   */
  async function runPass(passWorkers, slices) {
    /** @type {{ index: number, prompt: string, reason?: string, fromAccountId: string }[]} */
    const reassign = [];

    await Promise.all(
      passWorkers.map(async (a, i) => {
        const slice = slices[i];
        if (!slice?.prompts?.length) {
          accountProgress.set(a.id, {
            status: "idle",
            message: "No prompts assigned",
            completed: 0,
            failed: 0,
            total: 0,
          });
          pushState();
          return;
        }

        for (const idx of slice.indices) markTried(idx, a.id);

        let page;
        try {
          page = await ensurePrepared(a);
        } catch (e) {
          accountProgress.set(a.id, { status: "error", message: e.message });
          pushState();
          for (let j = 0; j < slice.prompts.length; j++) {
            reassign.push({
              index: slice.indices[j],
              prompt: slice.prompts[j],
              promptKey: slice.keys?.[j] ?? null,
              reason: "prepare_failed",
              fromAccountId: a.id,
            });
          }
          exhaustedAccounts.add(a.id);
          return;
        }

        accountProgress.set(a.id, {
          status: "running",
          message: `0 / ${slice.prompts.length}`,
          completed: 0,
          failed: 0,
          total: slice.prompts.length,
        });
        pushState();

        let sliceVideoJobs = 0;
        const result = await runBatchSlice({
          page,
          prompts: slice.prompts,
          promptIndices: slice.indices,
          promptKeys: slice.keys,
          totalAbsolute: total,
          settings: { ...settings, folder: a.label },
          // label + short id: two accounts whose labels read alike never share a folder
          folderLabel: `${a.label}-${String(a.id).slice(0, 6)}`,
          accountId: a.id,
          accountLabel: a.label,
          workerIndex: i,
          shouldStop: () => stopAll,
          onProgress: (evt) => {
            const cur = accountProgress.get(a.id) || {};
            if (evt.type === "BATCH_PROGRESS") {
              accountProgress.set(a.id, {
                ...cur,
                status: evt.status === "failed" ? "running" : evt.status || "running",
                message: evt.message || cur.message,
                completed: evt.completed ?? cur.completed,
                failed: evt.failed ?? cur.failed,
                total: slice.prompts.length,
                index: evt.index,
              });
              broadcast({
                type: "BATCH_PROGRESS",
                accountId: a.id,
                label: a.label,
                ...evt,
              });
            } else if (evt.type === "BATCH_DONE") {
              accountProgress.set(a.id, {
                status: "done",
                message: `Done · ${evt.completed} ok · ${evt.failed} fail`,
                completed: evt.completed,
                failed: evt.failed,
                total: slice.prompts.length,
                folder: evt.folder,
              });
            } else if (evt.type === "PROMPT_RESULT") {
              // Count only jobs this account actually SPENT a credit on.
              // A "rate_limited" result with reassign:true never ran here —
              // it is handed to another account — so counting it would
              // penalize an account for work it did not do.
              if (isVideoBatch && evt.submitted) {
                sliceVideoJobs += 1;
              }
              broadcast({
                type: "PROMPT_RESULT",
                accountId: a.id,
                label: a.label,
                ...evt,
              });
            } else if (evt.type === "status") {
              accountProgress.set(a.id, {
                ...cur,
                message: evt.message || cur.message,
              });
            }
            // Always forward BATCH_PROGRESS / PROMPT_RESULT; throttle full STATE
            // snapshots so N Chrome workers cannot flood the UI websocket.
            const now = Date.now();
            const throttle = Number(timing.progressStateThrottleMs) || 250;
            const important =
              evt.type === "BATCH_DONE" ||
              evt.type === "PROMPT_RESULT" ||
              evt.status === "failed" ||
              evt.status === "done";
            if (important || now - lastProgressStateAt >= throttle) {
              lastProgressStateAt = now;
              pushState();
            }
          },
        });

        if (result?.authExpired) {
          // Leaving the account flagged authenticated meant every later batch
          // picked it again and failed the same way, with a raw Google 401 as
          // the only clue. Mark it signed out so the UI can say so and the
          // scheduler stops choosing it.
          updateAccount(a.id, { authenticated: false, lastChecked: Date.now() });
          exhaustedAccounts.add(a.id);
          accountProgress.set(a.id, {
            status: "error",
            message: "Signed out — click Sign in for this account",
          });
          pushState();
        }

        // Flush this slice's consumed VIDEO jobs once, so a 50-clip slice is
        // one small JSON write rather than 50. Best-effort: fairness must
        // never break a batch that otherwise succeeded.
        if (isVideoBatch && sliceVideoJobs > 0) {
          try {
            addVideoLoad(a.id, sliceVideoJobs);
          } catch {}
        }

        for (const item of result?.reassign || []) {
          if (item.reason === "quota") exhaustedAccounts.add(a.id);
          reassign.push({ ...item, fromAccountId: a.id });
        }
      }),
    );

    return reassign;
  }

  function emitFinalFail(index, prompt, message) {
    broadcast({
      type: "PROMPT_RESULT",
      index,
      prompt,
      status: "failed",
      error: message,
      message,
    });
    broadcast({
      type: "BATCH_PROGRESS",
      index,
      total,
      status: "failed",
      message,
    });
  }

  try {
    // Prepare once inside runPass (per worker). A previous redundant
    // Promise.all(ensurePrepared) here + ensurePrepared again in runPass
    // double-initialized every account: openOrCreateProject / waitForFlowReady
    // ran twice before the first generation, which could surface as a second
    // navigation shortly after the page appeared ready.
    // Jobs Flow already accepted go back to the account that owns them (only it can poll and download them).
    const ledger = await defaultLedger();
    const scope = scopeOf(settings?.outputDir);
    const mediaKind = isVideoBatch ? "video" : "image";
    const ownerOf = (index) => {
      const p = prompts[index];
      const pk = promptKeys?.[index];
      const key = generationKey({ mediaKind, prompt: pk != null ? `${pk}\u0000${p}` : `#${index}\u0000${p}`, settings, slot: 0, scope });
      const e = ledger.get(key);
      return e && [LedgerState.ACCEPTED, LedgerState.MEDIA_ID_KNOWN, LedgerState.DOWNLOAD_FAILED].includes(e.state) ? e.accountId : null;
    };
    const routed = routeToOwners(workers, splitPrompts(prompts, workers.length, promptKeys), selected, ownerOf);
    let pending = await runPass(routed.workers, routed.slices);
    let passesRun = 1;

    // Rotate: reassign rate-limited / quota-handed prompts to other accounts.
    let rotateRound = 0;
    while (pending.length && !stopAll && rotateRound < selected.length + 1) {
      rotateRound++;
      /** @type {Map<string, { prompts: string[], indices: number[] }>} */
      const byAccount = new Map();
      // Re-read once per round: earlier rounds/slices have since flushed.
      let rotationLoads = new Map();
      if (isVideoBatch) {
        try {
          rotationLoads = getVideoLoads();
        } catch {}
      }
      /** @type {{ index: number, prompt: string }[]} */
      const noAccountLeft = [];

      for (const item of pending) {
        const candidates = remainingAccountsFor(item.index);
        if (!candidates.length) {
          noAccountLeft.push(item);
          continue;
        }
        // Prefer an account that is not currently exhausted; pick round-robin by load.
        // For VIDEO, ties break on CUMULATIVE load so rotation also moves work
        // toward accounts that have spent the fewest credits so far.
        candidates.sort((a, b) => {
          const la = (byAccount.get(a.id)?.prompts.length || 0);
          const lb = (byAccount.get(b.id)?.prompts.length || 0);
          if (la !== lb) return la - lb;
          if (!isVideoBatch) return 0;
          return (rotationLoads.get(a.id) || 0) - (rotationLoads.get(b.id) || 0);
        });
        const pick = candidates[0];
        if (!byAccount.has(pick.id)) {
          byAccount.set(pick.id, { prompts: [], indices: [], keys: [] });
        }
        const bucket = byAccount.get(pick.id);
        bucket.prompts.push(item.prompt);
        bucket.indices.push(item.index);
        bucket.keys.push(item.promptKey ?? null);
      }

      for (const item of noAccountLeft) {
        emitFinalFail(
          item.index,
          item.prompt,
          failMessageForPending(item, selected, exhaustedAccounts),
        );
      }

      if (!byAccount.size) break;

      const passWorkers = [];
      const slices = [];
      for (const a of selected) {
        const bucket = byAccount.get(a.id);
        if (!bucket?.prompts?.length) continue;
        passWorkers.push(a);
        slices.push(bucket);
        accountProgress.set(a.id, {
          status: "running",
          message: `Rotating ${bucket.prompts.length} prompt(s)…`,
          completed: 0,
          failed: 0,
          total: bucket.prompts.length,
        });
      }
      pushState();
      broadcast({
        type: "status",
        message: `Rate-limit rotation round ${rotateRound}: ${passWorkers.length} account(s), ${
          [...byAccount.values()].reduce((n, b) => n + b.prompts.length, 0)
        } prompt(s)`,
      });

      pending = await runPass(passWorkers, slices);
      passesRun += 1;
    }

    // Anything still pending after rotation budget → fail.
    for (const item of pending) {
      emitFinalFail(
        item.index,
        item.prompt,
        failMessageForPending(item, selected, exhaustedAccounts),
      );
    }

    // Stash so finally knows we actually attempted work.
    accountProgress.set("__passes_run__", { completed: passesRun, failed: 0, total: passesRun });
  } catch (e) {
    caught = e;
  } finally {
    running = false;
    const passesMeta = accountProgress.get("__passes_run__");
    accountProgress.delete("__passes_run__");
    let anyWork = 0;
    for (const [id, p] of accountProgress.entries()) {
      if (id.startsWith("__")) continue;
      anyWork += (Number(p.completed) || 0) + (Number(p.failed) || 0);
    }
    const extra = {};
    if (caught) {
      extra.generateError = caught.message;
    } else if (anyWork === 0 && prompts?.length && !(passesMeta && passesMeta.completed > 0)) {
      extra.generateError = "Batch ended before any prompt ran.";
    }
    pushState(extra);
    broadcast(donePayload);
  }
}

export function stopGenerate({ force = false } = {}) {
  stopAll = true;
  if (force) {
    // Stuck leftover after app kill: no live generate() finally will clear this.
    running = false;
  }
  pushState();
}

/** Clear a stuck `running` flag left by a previous app session. */
export function resetGenerateState() {
  stopAll = true;
  running = false;
  pushState({ generateError: null });
}

export async function closeBrowsers() {
  const before = openBrowserCount();
  stopAll = true;
  await closeAllBrowsers();
  pushState({ browsersClosed: before });
  return before;
}

export async function shutdown() {
  stopAll = true;
  await closeAllBrowsers();
}

/** TEMPORARY — see accounts.js's inspectAccountPage doc comment. */
export async function inspectAccount(accountId) {
  return inspectAccountPage(accountId);
}
