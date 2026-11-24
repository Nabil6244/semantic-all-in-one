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
function cachedRead(file, pick) {
  try {
    const { mtimeMs } = fs.statSync(file);
    const hit = cache.get(file);
    if (hit && hit.mtimeMs === mtimeMs) return hit.identity;
    const identity = pick(JSON.parse(fs.readFileSync(file, "utf8")));
    cache.set(file, { mtimeMs, identity });
    return identity;
  } catch {
    return null;
  }
}

function asIdentity(email, name) {
  const e = String(email || "").trim();
  return EMAIL.test(e) ? { email: e, name: String(name || "").trim() || null } : null;
}

export function readProfileIdentity(dir) {
  const fromLocalState = cachedRead(path.join(dir, "Local State"), (j) => {
    const info = j?.profile?.info_cache?.Default;
    return asIdentity(info?.user_name, info?.gaia_name);
  });
  if (fromLocalState) return fromLocalState;
  // Chrome started by automation often leaves Local State's user_name empty, but the profile's own
  // Preferences still lists the signed-in Google account under account_info.
  return cachedRead(path.join(dir, "Default", "Preferences"), (j) => {
    const info = (Array.isArray(j?.account_info) ? j.account_info : []).find((x) => EMAIL.test(String(x?.email || "")));
    return info ? asIdentity(info.email, info.full_name) : null;
  });
}

/** Same, for an account id (its profile under the app's profiles folder). */
export function accountIdentity(accountId) {
  return readProfileIdentity(profileDir(accountId));
}
