/**
 * Focused tests for cumulative Flow VIDEO credit balancing.
 * Run: node --test test/video-allocation.test.js
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

// Isolate the accounts store before anything imports paths.js.
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "flow-alloc-"));
process.env.SA_DATA_DIR = TMP;

const { splitPrompts, orderWorkersByVideoLoad } = await import("../lib/orchestrator.js");
const store = await import("../lib/store.js");

const acct = (id) => ({ id, label: id, authenticated: true });
const prompts = (n) => Array.from({ length: n }, (_, i) => `p${i}`);

/**
 * Mirror the REAL generate() allocation path, in order:
 *   selected -> workerCount -> ordering -> slice -> splitPrompts
 *
 * An earlier version of this helper ordered ALL accounts and split across all
 * of them, skipping workerCount entirely. That bypassed the exact truncation
 * that caused the defect, so the suite passed while small VIDEO batches were
 * still pinned to the first accounts. Keep this mirroring orchestrator.js.
 */
const PARALLEL_ACCOUNT_THRESHOLD = 15;

function allocate(accounts, count, loads, isVideo = true) {
  const workerCount =
    count >= PARALLEL_ACCOUNT_THRESHOLD
      ? accounts.length
      : Math.min(accounts.length, Math.max(1, count));
  const workers = orderWorkersByVideoLoad(accounts, isVideo, loads).slice(0, workerCount);
  const slices = splitPrompts(prompts(count), workers.length);
  const out = new Map();
  workers.forEach((w, i) => out.set(w.id, slices[i].prompts.length));
  return out;
}

const SEVEN = ["a", "b", "c", "d", "e", "f", "g"].map(acct);
const zero = () => new Map(SEVEN.map((a) => [a.id, 0]));

test("1. 70 clips / 7 accounts -> 10 each", () => {
  const sizes = [...allocate(SEVEN, 70, zero()).values()];
  assert.deepEqual(sizes, [10, 10, 10, 10, 10, 10, 10]);
});

test("2. 73 clips / 7 accounts -> 11,11,11,10,10,10,10", () => {
  const sizes = [...allocate(SEVEN, 73, zero()).values()];
  assert.deepEqual(sizes.slice().sort((x, y) => y - x), [11, 11, 11, 10, 10, 10, 10]);
  assert.equal(Math.max(...sizes) - Math.min(...sizes), 1);
  assert.equal(sizes.reduce((s, n) => s + n, 0), 73);
});

test("3. repeated batches rotate the remainder instead of favouring the first accounts", () => {
  const loads = zero();
  const totals = new Map(SEVEN.map((a) => [a.id, 0]));
  for (let batch = 0; batch < 7; batch++) {
    for (const [id, n] of allocate(SEVEN, 73, loads)) {
      loads.set(id, loads.get(id) + n);
      totals.set(id, totals.get(id) + n);
    }
  }
  const t = [...totals.values()];
  // 7 batches x 73 = 511 clips over 7 accounts = 73 each, perfectly even.
  assert.equal(t.reduce((s, n) => s + n, 0), 511);
  assert.ok(
    Math.max(...t) - Math.min(...t) <= 1,
    `cumulative spread must stay <=1, got ${JSON.stringify(t)}`,
  );
  // The old behaviour gave account "a" the +1 every time (77 vs 70).
  assert.notEqual(Math.max(...t), 77);
});

test("4. retry batches participate in the same cumulative accounting", () => {
  const loads = zero();
  for (const [id, n] of allocate(SEVEN, 70, loads)) loads.set(id, loads.get(id) + n);
  // Three clips failed and are retried as their own small batch.
  const retry = allocate(SEVEN, 3, loads);
  const got = [...retry.entries()].filter(([, n]) => n > 0).map(([id]) => id);
  assert.equal(got.length, 3, "a 3-clip retry must spread over 3 accounts");
  for (const [id, n] of retry) loads.set(id, loads.get(id) + n);

  // Next full batch must steer away from the accounts that took the retries.
  const next = allocate(SEVEN, 73, loads);
  for (const id of got) {
    assert.equal(next.get(id), 10, `${id} already took a retry; it must not also take the +1`);
  }
});

test("5. unavailable / quota-exhausted accounts are excluded", () => {
  const eligible = SEVEN.filter((a) => !["c", "f"].includes(a.id)); // 5 left
  const sizes = [...allocate(eligible, 73, zero()).values()];
  assert.equal(sizes.length, 5);
  assert.equal(sizes.reduce((s, n) => s + n, 0), 73);
  assert.equal(Math.max(...sizes) - Math.min(...sizes), 1);
  const ids = [...allocate(eligible, 73, zero()).keys()];
  assert.ok(!ids.includes("c") && !ids.includes("f"));
});

test("6. IMAGE allocation is unchanged (no reordering, original order kept)", () => {
  const loads = new Map([["a", 999], ["b", 0], ["c", 0], ["d", 0], ["e", 0], ["f", 0], ["g", 0]]);
  const imageOrder = orderWorkersByVideoLoad(SEVEN, false, loads).map((w) => w.id);
  assert.deepEqual(imageOrder, SEVEN.map((a) => a.id), "image batches must not be reordered");
  // Video with the same loads DOES reorder.
  const videoOrder = orderWorkersByVideoLoad(SEVEN, true, loads).map((w) => w.id);
  assert.equal(videoOrder.at(-1), "a", "heaviest account sorts last for video");
});

test("ordering is deterministic on ties and never drops or duplicates an account", () => {
  const loads = zero();
  const ids = orderWorkersByVideoLoad(SEVEN, true, loads).map((w) => w.id);
  assert.deepEqual(ids, SEVEN.map((a) => a.id), "equal loads keep original order");
  const mixed = new Map([["a", 5], ["b", 5], ["c", 1], ["d", 9], ["e", 1], ["f", 0], ["g", 5]]);
  const out = orderWorkersByVideoLoad(SEVEN, true, mixed).map((w) => w.id);
  assert.deepEqual(out, ["f", "c", "e", "a", "b", "g", "d"]);
  assert.equal(new Set(out).size, 7);
});

test("store: video load persists and only counts what it is told", () => {
  store.upsertAccount({ id: "acct-1", label: "one", authenticated: true });
  store.upsertAccount({ id: "acct-2", label: "two", authenticated: true });
  assert.equal(store.getVideoLoads().get("acct-1"), 0, "legacy record reads as 0");

  store.addVideoLoad("acct-1", 10);
  store.addVideoLoad("acct-1", 3);
  store.addVideoLoad("acct-2", 0);        // rate-limited slice: nothing consumed
  assert.equal(store.getVideoLoads().get("acct-1"), 13);
  assert.equal(store.getVideoLoads().get("acct-2"), 0);

  store.addVideoLoad("missing-id", 5);    // must not throw or create records
  assert.equal(store.listAccounts().length, 2);
});

// --- Regression: small VIDEO batches (prompts.length < accounts) -----------
// Defect was `orderWorkersByVideoLoad(selected.slice(0, workerCount))` —
// truncating by list order BEFORE load-ordering, so low-load accounts further
// down the list were unreachable. Measured before the fix: ten 3-clip retries
// gave {a:10, b:10, c:10, d:0, e:0, f:0, g:0}.

test("small VIDEO batch selects the LEAST-loaded accounts, not the first ones", () => {
  const loads = new Map([
    ["a", 10], ["b", 10], ["c", 10],
    ["d", 0], ["e", 0], ["f", 0], ["g", 0],
  ]);
  const picked = [...allocate(SEVEN, 3, loads).entries()]
    .filter(([, n]) => n > 0)
    .map(([id]) => id);

  assert.equal(picked.length, 3);
  assert.deepEqual(picked.slice().sort(), ["d", "e", "f"]);
  for (const heavy of ["a", "b", "c"]) {
    assert.ok(!picked.includes(heavy), `${heavy} is loaded 10 and must not be picked`);
  }
});

test("repeated small retries rotate toward the least-loaded accounts", () => {
  const loads = new Map(SEVEN.map((a) => [a.id, 0]));
  for (let i = 0; i < 14; i++) {
    for (const [id, n] of allocate(SEVEN, 3, loads)) loads.set(id, loads.get(id) + n);
  }
  const v = [...loads.values()];
  assert.equal(v.reduce((s, n) => s + n, 0), 42, "14 retries x 3 clips");
  assert.equal(
    Math.max(...v) - Math.min(...v), 0,
    `42 clips over 7 accounts must land 6 each, got ${JSON.stringify(Object.fromEntries(loads))}`,
  );
  assert.ok(!v.includes(0), "no account may be starved of VIDEO work");
});

test("mixed batch sizes stay as balanced as mathematically possible", () => {
  const loads = new Map(SEVEN.map((a) => [a.id, 0]));
  let total = 0;
  for (const count of [73, 3, 5, 70, 2, 19, 1, 4, 31, 3]) {
    for (const [id, n] of allocate(SEVEN, count, loads)) loads.set(id, loads.get(id) + n);
    total += count;
  }
  const v = [...loads.values()];
  assert.equal(v.reduce((s, n) => s + n, 0), total);
  assert.ok(
    Math.max(...v) - Math.min(...v) <= 1,
    `cumulative spread must stay <=1 across varied batch sizes, got ${JSON.stringify(
      Object.fromEntries(loads),
    )}`,
  );
});

test("quota-exhausted accounts stay excluded even on small batches", () => {
  // Orchestrator filters exhausted accounts out of `selected` upstream.
  const eligible = SEVEN.filter((a) => !["d", "e"].includes(a.id));
  const loads = new Map([
    ["a", 10], ["b", 10], ["c", 10],
    ["d", 0], ["e", 0],          // exhausted: lowest load, must still be skipped
    ["f", 1], ["g", 2],
  ]);
  const picked = [...allocate(eligible, 2, loads).entries()]
    .filter(([, n]) => n > 0)
    .map(([id]) => id);
  assert.deepEqual(picked.slice().sort(), ["f", "g"]);
  assert.ok(!picked.includes("d") && !picked.includes("e"));
});

test("IMAGE small batches keep original order (unchanged by the fix)", () => {
  const loads = new Map([
    ["a", 10], ["b", 10], ["c", 10],
    ["d", 0], ["e", 0], ["f", 0], ["g", 0],
  ]);
  const picked = [...allocate(SEVEN, 3, loads, false).entries()]
    .filter(([, n]) => n > 0)
    .map(([id]) => id);
  assert.deepEqual(picked, ["a", "b", "c"], "image must still take the first accounts");
});
