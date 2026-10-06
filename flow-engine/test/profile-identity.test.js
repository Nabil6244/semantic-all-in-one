/**
 * The Accounts panel names the Gmail each Flow profile is signed into. It comes from Chrome's own "Local State"
 * file in the profile folder; anything missing or odd there must mean "unknown", never a crash or a wrong address.
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { readProfileIdentity } from "../lib/profile-identity.js";

function profileWith(localState) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "flow-profile-"));
  if (localState !== undefined) fs.writeFileSync(path.join(dir, "Local State"), typeof localState === "string" ? localState : JSON.stringify(localState));
  return dir;
}

test("a profile signed in to Google gives its address and name", () => {
  const dir = profileWith({ profile: { info_cache: { Default: { user_name: "someone@gmail.com", gaia_name: "Some One" } } } });
  assert.deepEqual(readProfileIdentity(dir), { email: "someone@gmail.com", name: "Some One" });
});

test("no name is fine", () => {
  const dir = profileWith({ profile: { info_cache: { Default: { user_name: "someone@gmail.com" } } } });
  assert.deepEqual(readProfileIdentity(dir), { email: "someone@gmail.com", name: null });
});

test("unknown when the profile is not signed in, the file is missing or broken, or the value is not an address", () => {
  assert.equal(readProfileIdentity(profileWith({ profile: { info_cache: { Default: { user_name: "" } } } })), null);
  assert.equal(readProfileIdentity(profileWith({ profile: {} })), null);
  assert.equal(readProfileIdentity(profileWith(undefined)), null);
  assert.equal(readProfileIdentity(profileWith("{not json")), null);
  assert.equal(readProfileIdentity(profileWith({ profile: { info_cache: { Default: { user_name: "Person 1" } } } })), null);
});

test("a changed file is read again (Chrome updates it when the profile signs in or out)", () => {
  const dir = profileWith({ profile: { info_cache: { Default: { user_name: "first@gmail.com" } } } });
  assert.equal(readProfileIdentity(dir).email, "first@gmail.com");
  const file = path.join(dir, "Local State");
  fs.writeFileSync(file, JSON.stringify({ profile: { info_cache: { Default: { user_name: "second@gmail.com" } } } }));
  const later = new Date(Date.now() + 5000);
  fs.utimesSync(file, later, later);
  assert.equal(readProfileIdentity(dir).email, "second@gmail.com");
});
