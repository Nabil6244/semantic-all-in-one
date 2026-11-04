/**
 * Flow's agent refusing a whole paste ("This generation might violate our policies", live 2026-11-02) is recognised, but only
 * in the chat after this paste: old refusals still in an account's chat made batches look refused within seconds and their
 * scenes went one by one. Run: node --test test/agent-refusal.test.js
 */
import test from "node:test";
import assert from "node:assert/strict";

const { countRefusals, refusalsAfter, pasteMarker } = await import("../lib/flow-ui-agent.js");

test("the refusal message is counted; ordinary chat text is not", () => {
  assert.ok(countRefusals("This generation might violate our policies. Please try a different prompt or send feedback.") > 0);
  assert.equal(countRefusals("Generating 9 images of the trainee holding a towel"), 0);
});

test("old refusals above this paste are ignored; a refusal below it counts", () => {
  const msg = "Make these images:\nS01: the trainee gripping a thick folded towel with both hands\nS02: a hand in a vise";
  const m = pasteMarker(msg);
  const old = "Earlier: This generation might violate our policies. ";
  assert.equal(refusalsAfter(old + msg + "\nGenerating 2 images...", m), 0);
  assert.ok(refusalsAfter(old + msg + "\nThis generation might violate our policies.", m) > 0);
  assert.equal(refusalsAfter("This generation might violate our policies.", m), 0, "this paste not on the page: no refusal assumed");
});
