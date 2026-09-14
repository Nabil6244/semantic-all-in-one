/**
 * Focused tests for staggered refresh + per-account lifecycle locking.
 * No real Flow / Playwright — pure scheduling + concurrency mocks.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { defaults, timing } from "../config.js";
import {
  AccountLifecycle,
  LifecycleState,
  computeRefreshOffset,
  createRefreshPlan,
  isMissingMediaIdError,
  stableAccountSlot,
} from "../lib/account-lifecycle.js";
import {
  waitForFlowReady,
  checkFlowReady,
  MissingMediaIdError,
  FatalError,
} from "../lib/flow-api.js";

// ---------------------------------------------------------------------------
// Refresh scheduling
// ---------------------------------------------------------------------------

test("default refreshFrequency is 20", () => {
  assert.equal(defaults.flowSettings.refreshFrequency, 20);
});

test("configured refreshEvery is respected by createRefreshPlan", () => {
  const plan = createRefreshPlan({
    refreshEvery: 15,
    workerIndex: 0,
    maxAccounts: 10,
  });
  assert.equal(plan.refreshEvery, 15);
  assert.equal(plan.offset, 0);
  assert.equal(plan.nextThreshold, 15);
  assert.equal(plan.shouldRefresh(14), false);
  assert.equal(plan.shouldRefresh(15), true);
});

test("accounts receive different stable offsets (20/22/24… pattern)", () => {
  const thresholds = [];
  for (let i = 0; i < 10; i++) {
    const plan = createRefreshPlan({
      refreshEvery: 20,
      workerIndex: i,
      maxAccounts: 10,
    });
    thresholds.push(plan.nextThreshold);
    assert.equal(plan.offset, i * 2);
  }
  assert.deepEqual(thresholds, [20, 22, 24, 26, 28, 30, 32, 34, 36, 38]);
  assert.equal(new Set(thresholds).size, 10, "must not synchronize all accounts");
});

test("offset from accountKey is stable across calls", () => {
  const a = computeRefreshOffset({ refreshEvery: 20, accountKey: "acct-xyz" });
  const b = computeRefreshOffset({ refreshEvery: 20, accountKey: "acct-xyz" });
  assert.equal(a, b);
  assert.notEqual(
    computeRefreshOffset({ refreshEvery: 20, accountKey: "acct-xyz" }),
    computeRefreshOffset({ refreshEvery: 20, accountKey: "acct-other" }),
  );
  assert.equal(typeof stableAccountSlot("acct-xyz"), "number");
});

test("threshold advances after refresh and does not re-fire for same completed", () => {
  const plan = createRefreshPlan({
    refreshEvery: 20,
    workerIndex: 1,
    maxAccounts: 10,
  });
  assert.equal(plan.nextThreshold, 22);
  assert.equal(plan.shouldRefresh(22), true);
  plan.advanceAfterRefresh(22);
  assert.equal(plan.nextThreshold, 42);
  assert.equal(plan.shouldRefresh(22), false);
  assert.equal(plan.shouldRefresh(41), false);
  assert.equal(plan.shouldRefresh(42), true);
});

test("refreshEvery=0 disables refresh", () => {
  const plan = createRefreshPlan({ refreshEvery: 0, workerIndex: 3 });
  assert.equal(plan.shouldRefresh(100), false);
  assert.equal(plan.nextThreshold, Infinity);
});

// ---------------------------------------------------------------------------
// Lifecycle locking
// ---------------------------------------------------------------------------

test("generation waits until refresh finishes (no overlap on same account)", async () => {
  const life = new AccountLifecycle({
    accountLabel: "A3",
    refreshEvery: 20,
    workerIndex: 2,
  });
  const events = [];
  const refresh = life.refresh(async () => {
    events.push("refresh-start");
    assert.equal(life.canGenerate(), false);
    await new Promise((r) => setTimeout(r, 40));
    events.push("refresh-end");
  });
  const gen = life.generate(async () => {
    events.push("gen-start");
    assert.equal(life.state, LifecycleState.WAITING_FOR_RESULT);
  });
  await Promise.all([refresh, gen]);
  assert.deepEqual(events, ["refresh-start", "refresh-end", "gen-start"]);
  assert.equal(life.state, LifecycleState.READY);
  assert.equal(life.canGenerate(), true);
});

test("refresh waits until generation finishes (no mid-flight reload)", async () => {
  const life = new AccountLifecycle({
    accountLabel: "A1",
    refreshEvery: 20,
    workerIndex: 0,
  });
  const events = [];
  const gen = life.generate(async () => {
    events.push("gen-start");
    await new Promise((r) => setTimeout(r, 40));
    events.push("gen-end");
  });
  const refresh = life.refresh(async () => {
    events.push("refresh-start");
  });
  await Promise.all([gen, refresh]);
  assert.deepEqual(events, ["gen-start", "gen-end", "refresh-start"]);
});

test("recovery queues behind refresh (account-local, no overlap)", async () => {
  const life = new AccountLifecycle({ accountLabel: "A2", refreshEvery: 20 });
  const events = [];
  const refresh = life.refresh(async () => {
    events.push("refresh");
    await new Promise((r) => setTimeout(r, 30));
  });
  const recover = life.recover(async () => {
    events.push("recover");
  });
  await Promise.all([refresh, recover]);
  assert.deepEqual(events, ["refresh", "recover"]);
});

test("account-local locking does not block other accounts", async () => {
  const a = new AccountLifecycle({ accountLabel: "A0", workerIndex: 0, refreshEvery: 20 });
  const b = new AccountLifecycle({ accountLabel: "A1", workerIndex: 1, refreshEvery: 20 });
  let bDone = false;
  const refreshA = a.refresh(() => new Promise((r) => setTimeout(r, 100)));
  await b.generate(async () => {
    bDone = true;
  });
  assert.equal(bDone, true);
  await refreshA;
});

// ---------------------------------------------------------------------------
// Readiness
// ---------------------------------------------------------------------------

function fakeReadyPage({ href, executeReady }) {
  const location = { href };
  const grecaptcha = {
    enterprise: executeReady ? { execute: async () => "tok" } : {},
  };
  return {
    async waitForLoadState() {},
    async evaluate(fn, arg) {
      globalThis.window = { grecaptcha, location };
      globalThis.grecaptcha = grecaptcha;
      globalThis.location = location;
      try {
        return arg === undefined ? await fn() : await fn(arg);
      } finally {
        delete globalThis.window;
        delete globalThis.grecaptcha;
        delete globalThis.location;
      }
    },
  };
}

test("checkFlowReady requires project URL and callable execute", async () => {
  const ok = await checkFlowReady(
    fakeReadyPage({
      href: "https://flow.google.com/project/abc-def",
      executeReady: true,
    }),
  );
  assert.equal(ok.hasProject, true);
  assert.equal(ok.hasRecaptcha, true);

  const home = await checkFlowReady(
    fakeReadyPage({ href: "https://flow.google.com/", executeReady: true }),
  );
  assert.equal(home.hasProject, false);

  const half = await checkFlowReady(
    fakeReadyPage({
      href: "https://flow.google.com/project/abc-def",
      executeReady: false,
    }),
  );
  assert.equal(half.hasRecaptcha, false);
});

test("waitForFlowReady eventually succeeds once execute attaches", async () => {
  let probes = 0;
  const location = { href: "https://flow.google.com/project/abc" };
  const page = {
    async waitForLoadState() {},
    async evaluate(fn, arg) {
      probes++;
      const grecaptcha = {
        enterprise: probes < 3 ? {} : { execute: async () => "x" },
      };
      globalThis.window = { grecaptcha, location };
      globalThis.grecaptcha = grecaptcha;
      globalThis.location = location;
      try {
        return arg === undefined ? await fn() : await fn(arg);
      } finally {
        delete globalThis.window;
        delete globalThis.grecaptcha;
        delete globalThis.location;
      }
    },
  };
  const ready = await waitForFlowReady(page, 5000);
  assert.equal(ready.hasRecaptcha, true);
  assert.ok(probes >= 3);
});

test("waitForFlowReady timeout produces Flow page readiness timeout", async () => {
  const page = fakeReadyPage({
    href: "https://flow.google.com/",
    executeReady: true,
  });
  await assert.rejects(
    () => waitForFlowReady(page, 1200),
    (err) =>
      err instanceof FatalError &&
      /Flow page readiness timeout/.test(err.message),
  );
});

// ---------------------------------------------------------------------------
// Missing mediaId helpers
// ---------------------------------------------------------------------------

test("isMissingMediaIdError classifies MissingMediaIdError", () => {
  assert.equal(isMissingMediaIdError(new MissingMediaIdError()), true);
  assert.equal(isMissingMediaIdError(new Error("No mediaId in generation response")), true);
  assert.equal(isMissingMediaIdError(new Error("rate limited")), false);
});

test("recovery reload budget is one per prompt by default", () => {
  const life = new AccountLifecycle({ accountLabel: "A9", refreshEvery: 20 });
  assert.equal(life.canRecoveryReload(), true);
  life.noteRecoveryReload();
  assert.equal(life.canRecoveryReload(), false);
  life.resetRecoveryBudget();
  assert.equal(life.canRecoveryReload(), true);
});

// ---------------------------------------------------------------------------
// Concurrency: 10 accounts, staggered refresh, no global lock
// ---------------------------------------------------------------------------

test("10 accounts can generate concurrently while one refreshes", async () => {
  const lives = Array.from({ length: 10 }, (_, i) =>
    new AccountLifecycle({
      accountLabel: `A${i}`,
      workerIndex: i,
      refreshEvery: 20,
      maxAccounts: 10,
    }),
  );
  assert.equal(timing.maxParallelAccounts, 10);

  const thresholds = lives.map((l) => l.refreshPlan.nextThreshold);
  assert.equal(new Set(thresholds).size, 10);

  let concurrent = 0;
  let maxConcurrent = 0;
  const refreshHold = lives[3].refresh(
    () => new Promise((r) => setTimeout(r, 60)),
  );

  const gens = lives
    .filter((_, i) => i !== 3)
    .map((life) =>
      life.generate(async () => {
        concurrent++;
        maxConcurrent = Math.max(maxConcurrent, concurrent);
        await new Promise((r) => setTimeout(r, 20));
        concurrent--;
      }),
    );

  await Promise.all(gens);
  await refreshHold;
  assert.ok(maxConcurrent >= 5, `expected parallel gens, got ${maxConcurrent}`);
  assert.equal(lives[3].state, LifecycleState.READY);
});

test("stress simulation: 10 accounts × 100 gens with staggered refresh counts", async () => {
  const refreshEvery = 20;
  const accounts = 10;
  const gensPerAccount = 100;
  const plans = Array.from({ length: accounts }, (_, i) =>
    createRefreshPlan({ refreshEvery, workerIndex: i, maxAccounts: accounts }),
  );
  const refreshCounts = Array(accounts).fill(0);
  const refreshTimeline = []; // { account, at }

  for (let a = 0; a < accounts; a++) {
    for (let c = 1; c <= gensPerAccount; c++) {
      if (plans[a].shouldRefresh(c, { hasMorePrompts: c < gensPerAccount })) {
        refreshTimeline.push({ account: a, at: c });
        refreshCounts[a]++;
        plans[a].advanceAfterRefresh(c);
      }
    }
  }

  // No synchronized bucket: at any completed count, ≤1 account refreshes.
  const byAt = new Map();
  for (const ev of refreshTimeline) {
    byAt.set(ev.at, (byAt.get(ev.at) || 0) + 1);
  }
  for (const [at, n] of byAt) {
    assert.ok(n <= 1, `synchronized refresh storm at completed=${at}: ${n} accounts`);
  }

  // Each account refreshed several times over 100 gens (base 20).
  for (const n of refreshCounts) {
    assert.ok(n >= 3 && n <= 6, `unexpected refresh count ${n}`);
  }

  assert.equal(
    refreshTimeline.length,
    refreshCounts.reduce((s, n) => s + n, 0),
  );
});
