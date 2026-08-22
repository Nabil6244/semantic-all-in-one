import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export const DESKTOP_ROOT = path.resolve(__dirname, "..");
export const PUBLIC_DIR = path.join(DESKTOP_ROOT, "public");

/** Persistent app data (accounts registry + browser profiles). */
export const DATA_DIR =
  process.env.SA_DATA_DIR ||
  path.join(os.homedir(), ".semantic-automator-desktop");

export const ACCOUNTS_FILE = path.join(DATA_DIR, "accounts.json");
export const PROFILES_DIR = path.join(DATA_DIR, "profiles");

/** Where generated images land (mirrors extension's Flow_Images layout). */
export const DOWNLOADS_ROOT =
  process.env.SA_DOWNLOADS_DIR ||
  path.join(os.homedir(), "Downloads", "Flow_Images");

export function ensureDirs() {
  // Only writable runtime dirs — never PUBLIC_DIR (lives inside app.asar when packaged).
  for (const d of [DATA_DIR, PROFILES_DIR, DOWNLOADS_ROOT]) {
    fs.mkdirSync(d, { recursive: true });
  }
}

export function profileDir(accountId) {
  return path.join(PROFILES_DIR, accountId);
}

export function accountDownloadDir(labelOrIndex, root = DOWNLOADS_ROOT) {
  const safe = String(labelOrIndex || "account")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40) || "account";
  const base = root || DOWNLOADS_ROOT;
  fs.mkdirSync(base, { recursive: true });
  const dir = path.join(base, safe);
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}
