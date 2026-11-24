import test from "node:test";
import assert from "node:assert/strict";
import { nextAccountLabel } from "../lib/store.js";

test("next account label skips past the highest number, not the count", () => {
  const accounts = ["Account 3", "Account 4", "Account 9", "Account 14"].map((label) => ({ label }));
  assert.equal(nextAccountLabel(accounts), "Account 15");
});

test("next account label starts at 1 and ignores custom names", () => {
  assert.equal(nextAccountLabel([]), "Account 1");
  assert.equal(nextAccountLabel([{ label: "Work" }, { label: "Account 2" }]), "Account 3");
});
