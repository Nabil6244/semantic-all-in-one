// Credit-safety regression: batch-runner.js must never click Flow's paid
// "Start generation" twice for the same video prompt (a detection timeout or
// a failed download after the click previously looped back and re-clicked it
// -- the "10 video prompts -> 18 Flow videos" report). The real assertions
// live in fixtures/video-no-reclick.child.mjs, which needs Node's module
// mocking flag, so it runs in a child process here.
import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

test("video prompts are never re-submitted after the paid Generate click", () => {
  const child = spawnSync(
    process.execPath,
    ["--experimental-test-module-mocks", "--test", path.join(here, "fixtures", "video-no-reclick.child.mjs")],
    { encoding: "utf8", timeout: 120000 },
  );
  assert.equal(child.status, 0, `child test run failed:\n${child.stdout}\n${child.stderr}`);
});
