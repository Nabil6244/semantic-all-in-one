import fs from "node:fs";
import crypto from "node:crypto";
import { ACCOUNTS_FILE, ensureDirs } from "./paths.js";

const DEFAULT = { accounts: [], updatedAt: 0 };

function readRaw() {
  ensureDirs();
  if (!fs.existsSync(ACCOUNTS_FILE)) return { ...DEFAULT };
  try {
    return { ...DEFAULT, ...JSON.parse(fs.readFileSync(ACCOUNTS_FILE, "utf8")) };
  } catch {
    return { ...DEFAULT };
  }
}

function writeRaw(data) {
  ensureDirs();
  data.updatedAt = Date.now();
  fs.writeFileSync(ACCOUNTS_FILE, JSON.stringify(data, null, 2));
}

export function listAccounts() {
  return readRaw().accounts;
}

export function getAccount(id) {
  return listAccounts().find((a) => a.id === id) || null;
}

export function upsertAccount(partial) {
  const data = readRaw();
  const idx = data.accounts.findIndex((a) => a.id === partial.id);
  if (idx >= 0) {
    data.accounts[idx] = { ...data.accounts[idx], ...partial, updatedAt: Date.now() };
  } else {
    data.accounts.push({
      id: partial.id || crypto.randomUUID(),
      label: partial.label || `Account ${data.accounts.length + 1}`,
      email: partial.email || null,
      authenticated: !!partial.authenticated,
      lastChecked: partial.lastChecked || 0,
      createdAt: Date.now(),
      updatedAt: Date.now(),
      ...partial,
    });
  }
  writeRaw(data);
  return data.accounts.find((a) => a.id === (partial.id || data.accounts.at(-1).id));
}

export function createAccount(label) {
  const n = listAccounts().length + 1;
  return upsertAccount({
    id: crypto.randomUUID(),
    label: label || String(n),
    authenticated: false,
  });
}

export function updateAccount(id, patch) {
  const cur = getAccount(id);
  if (!cur) throw new Error("Account not found: " + id);
  return upsertAccount({ ...cur, ...patch, id });
}

export function removeAccount(id) {
  const data = readRaw();
  data.accounts = data.accounts.filter((a) => a.id !== id);
  writeRaw(data);
}

/**
 * Cumulative VIDEO job load per account, used to keep Flow VIDEO credit
 * consumption even across MANY batches and retries (a single batch is already
 * balanced to within 1 by splitPrompts). IMAGE jobs are free and are never
 * counted here.
 *
 * Stored on the existing account record in the existing accounts JSON — no new
 * database. Missing/legacy records simply read as 0.
 */
export function getVideoLoads() {
  const loads = new Map();
  for (const a of listAccounts()) {
    loads.set(a.id, Number(a.videoJobs) || 0);
  }
  return loads;
}

/** Add `n` consumed VIDEO jobs to an account. Written once per slice, not per prompt. */
export function addVideoLoad(id, n) {
  const count = Number(n) || 0;
  if (!id || count <= 0) return;
  const data = readRaw();
  const idx = data.accounts.findIndex((a) => a.id === id);
  if (idx < 0) return;
  data.accounts[idx].videoJobs = (Number(data.accounts[idx].videoJobs) || 0) + count;
  data.accounts[idx].updatedAt = Date.now();
  writeRaw(data);
}
