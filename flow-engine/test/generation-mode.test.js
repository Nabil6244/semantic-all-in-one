import test from "node:test";
import assert from "node:assert/strict";

test("defaults.flowSettings.generationMode is rpc (extension CDP path)", async () => {
  const prev = process.env.FLOW_GENERATION_MODE;
  delete process.env.FLOW_GENERATION_MODE;
  try {
    const { defaults } = await import(`../config.js?t=${Date.now()}`);
    assert.equal(defaults.flowSettings.generationMode, "rpc");
  } finally {
    if (prev === undefined) delete process.env.FLOW_GENERATION_MODE;
    else process.env.FLOW_GENERATION_MODE = prev;
  }
});

test("resolveGenerationMode falls back to rpc", async () => {
  const { resolveGenerationMode } = await import("../lib/generation-dispatch.js");
  assert.equal(resolveGenerationMode({}), "rpc");
  assert.equal(resolveGenerationMode({ generationMode: "ui" }), "ui");
  assert.equal(resolveGenerationMode({ generationMode: "bogus" }), "rpc");
});
