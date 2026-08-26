import {
  listAccounts,
  createAccount,
  updateAccount,
  removeAccount,
  getAccount,
} from "./store.js";
import {
  openAccountBrowser,
  closeAccountBrowser,
  gotoFlow,
  closeAllBrowsers,
} from "./accounts.js";
import {
  checkAuthStatus,
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
  const st = await checkAuthStatus(page);
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

function splitPrompts(prompts, n) {
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
  const workerCount = Math.min(selected.length, Math.max(1, prompts.length));
  const workers = selected.slice(0, workerCount);
  for (const a of selected) {
    const used = workers.some((w) => w.id === a.id);
    accountProgress.set(a.id, {
      status: "idle",
      message: used ? "Starting…" : "Not needed for this batch",
      completed: 0,
      failed: 0,
      total: 0,
    });
  }
  pushState({ generateError: null });

  const slices = splitPrompts(prompts, workers.length);
  const total = prompts.length;
  let caught = null;

  try {
    // Prepare only accounts that will receive prompts
    await Promise.all(
      workers.map((a) =>
        prepareAccount(a.id, a.label).catch((e) => {
          accountProgress.set(a.id, {
            status: "error",
            message: e.message,
          });
          pushState();
          throw e;
        }),
      ),
    );

    // Run slices in parallel
    await Promise.all(
      workers.map(async (a, i) => {
        const slice = slices[i];
        if (!slice.prompts.length) {
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

        const { getPage } = await import("./accounts.js");
        const page = getPage(a.id);
        if (!page) throw new Error("Browser closed for " + a.label);

        accountProgress.set(a.id, {
          status: "running",
          message: `0 / ${slice.prompts.length}`,
          completed: 0,
          failed: 0,
          total: slice.prompts.length,
        });
        pushState();

        await runBatchSlice({
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
            } else if (evt.type === "status") {
              accountProgress.set(a.id, {
                ...cur,
                message: evt.message || cur.message,
              });
            }
            pushState();
          },
        });
      }),
    );
  } catch (e) {
    caught = e;
  } finally {
    running = false;
    let anyWork = 0;
    for (const p of accountProgress.values()) {
      anyWork += (Number(p.completed) || 0) + (Number(p.failed) || 0);
    }
    const extra = {};
    if (caught) {
      extra.generateError = caught.message;
    } else if (anyWork === 0 && prompts?.length) {
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
  stopAll = true;
  await closeAllBrowsers();
  pushState();
}

export async function shutdown() {
  stopAll = true;
  await closeAllBrowsers();
}
