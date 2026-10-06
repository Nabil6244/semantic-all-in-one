/**
 * Which Google account a Flow profile is signed into, read from Chrome's own
 * "Local State" file in the profile folder (profile.info_cache.Default:
 * user_name = the address, gaia_name = the full name). Chrome writes this when
 * the profile signs in to Google, so it needs no browser, no network and no
 * Flow request. The Flow page itself only shows an avatar, which is why the
 * old page-text scan never found an address.
 */
import fs from "node:fs";
import path from "node:path";
import { profileDir } from "./paths.js";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// The state is pushed to the app many times a second while generating: re-read a file only when Chrome has changed it.
const cache = new Map(); // file -> { mtimeMs, identity }

/** { email, name } for a profile folder, or null when unknown (no file, unreadable, not signed in to Google). */
export function readProfileIdentity(dir) {
  const file = path.join(dir, "Local State");
  try {
    const { mtimeMs } = fs.statSync(file);
    const hit = cache.get(file);
    if (hit && hit.mtimeMs === mtimeMs) return hit.identity;
    const info = JSON.parse(fs.readFileSync(file, "utf8"))?.profile?.info_cache?.Default;
    const email = String(info?.user_name || "").trim();
    const identity = EMAIL.test(email) ? { email, name: String(info?.gaia_name || "").trim() || null } : null;
    cache.set(file, { mtimeMs, identity });
    return identity;
  } catch {
    return null;
  }
}

/** Same, for an account id (its profile under the app's profiles folder). */
export function accountIdentity(accountId) {
  return readProfileIdentity(profileDir(accountId));
}
