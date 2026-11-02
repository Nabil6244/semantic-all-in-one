/**
 * Flow's agent refusing a whole paste ("This generation might violate our policies", live 2026-11-02) is recognised, so the
 * wait stops at once and the scenes are recorded as nothing made (safe to send again), never "unknown".
 * Run: node --test test/agent-refusal.test.js
 */
import test from "node:test";
import assert from "node:assert/strict";

const { countRefusals } = await import("../lib/flow-ui-agent.js");

test("the refusal message is counted; ordinary chat text is not", () => {
  assert.ok(countRefusals("This generation might violate our policies. Please try a different prompt or send feedback.") > 0);
  assert.equal(countRefusals("Generating 9 images of the trainee holding a towel"), 0);
  assert.equal(countRefusals(""), 0);
});

test("a refusal already in the chat before the click is not taken for a new one", () => {
  const before = countRefusals("old: This generation might violate our policies.");
  const after = countRefusals("old: This generation might violate our policies. new: This generation might violate our policies.");
  assert.ok(after > before);
  assert.equal(countRefusals("old: This generation might violate our policies. Here are your 9 images"), before);
});
