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
} from "./accounts.js";
import {
  checkAuthStatus,
  dismissBlockingOverlays,
  openOrCreateProject,
  waitForFlowReady,
} from "./flow-api.js";
import { runBatchSlice } from "./batch-runner.js";
import { DOWNLOADS_ROOT } from "./paths.js";
import fs from "node:fs";

/** @type {Set<(msg: object) => void>} */
const listeners = new Set();

let stopAll = false;
let running = false;
/** Serialize GENERATE so concurrent Retry / asset jobs never race the running flag. */
let generateChain = Promise.resolve();
const accountProgress = new Map();

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
    email: a.email || null,
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
        email: st.email || a.email,
        lastChecked: Date.now(),
      });
      accountProgress.set(accountId, {
        status: "idle",
        message: "Signed in" + (st.email ? ` (${st.email})` : ""),
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
      email: st.email || a.email,
      lastChecked: Date.now(),
    });
    accountProgress.set(accountId, {
      status: st.authenticated ? "idle" : "error",
      message: st.authenticated
        ? "OK" + (st.email ? ` · ${st.email}` : "")
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
    throw new Error(`Account "${label}" is not signed in`);
  }
  updateAccount(accountId, {
    authenticated: true,
    email: st.email,
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

export function splitPrompts(prompts, n) {
  const slices = Array.from({ length: n }, () => ({
    prompts: [],
    indices: [],
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

async function runGenerate({ prompts, settings, accountIds }) {
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

  // One Chrome per prompt needed — never open every signed-in account for a
  // single Flow video (that was flooding the dock with idle browsers).
  // Large batches (15+) fan out to every signed-in account for parallel work.
  const PARALLEL_ACCOUNT_THRESHOLD = 15;
  const workerCount =
    prompts.length >= PARALLEL_ACCOUNT_THRESHOLD
      ? selected.length
      : Math.min(selected.length, Math.max(1, prompts.length));
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

  async function ensurePrepared(account) {
    const { getPage } = await import("./accounts.js");
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
          totalAbsolute: total,
          settings: { ...settings, folder: a.label },
          folderLabel: a.label,
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
              if (isVideoBatch && !evt.reassign && evt.status !== "rate_limited") {
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
            pushState();
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
    // First pass — initial workers
    await Promise.all(
      workers.map((a) =>
        ensurePrepared(a).catch((e) => {
          accountProgress.set(a.id, { status: "error", message: e.message });
          pushState();
          throw e;
        }),
      ),
    );

    let pending = await runPass(workers, splitPrompts(prompts, workers.length));
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
          byAccount.set(pick.id, { prompts: [], indices: [] });
        }
        const bucket = byAccount.get(pick.id);
        bucket.prompts.push(item.prompt);
        bucket.indices.push(item.index);
      }

      for (const item of noAccountLeft) {
        emitFinalFail(
          item.index,
          item.prompt,
          "Rate limit / quota persists on all signed-in accounts — skipping",
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
        "Rate limit / quota persists after account rotation — skipping",
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
  const before = contexts.size;
  stopAll = true;
  await closeAllBrowsers();
  pushState({ browsersClosed: before });
  return before;
}

export async function shutdown() {
  stopAll = true;
  await closeAllBrowsers();
}
