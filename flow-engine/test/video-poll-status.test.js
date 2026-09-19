/**
 * pollVideoStatus() FAILED-status recognition — the fix for a real,
 * independently-verified bug: Google can mark a video generation workflow
 * "Failed" (confirmed live in the Flow web UI, 2026-09-19) after the
 * workflow was successfully CREATED, but pollVideoStatus() only ever
 * recognized PENDING(2)/COMPLETE(3) — any other status (including a real
 * FAILED one) fell through to "keep polling" and only surfaced as a
 * generic, misleading "timed out after 360s" once the full poll budget
 * was exhausted.
 *
 * IMPORTANT — the actual numeric FAILED status value has NOT been
 * captured from a live Flow response in this pass (no live Flow
 * infrastructure was used to write or verify this file). Per the fix's
 * own design, VIDEO_STATUS_FAILED therefore ships EMPTY in production;
 * these tests inject an assumed value into it (always restored in
 * `finally`) purely to prove the DETECTION MECHANISM is correct and
 * covered, not to claim the real value is known. See flow-api.js's own
 * comment on VIDEO_STATUS_FAILED for how to wire in the real value once
 * captured.
 *
 * Wire-format helpers (chunkOf/canned/jwpdufResult/fakePage/fullWiz) are
 * duplicated from video-generation.test.js rather than shared — matches
 * this test directory's existing convention (no shared test-utils module)
 * and keeps this file runnable in isolation.
 *
 * pollVideoStatus() sleeps the real timing.videoPollIntervalMs before
 * every attempt. Tests that need multiple poll cycles temporarily shrink
 * timing.videoPollIntervalMs/videoPollTimeoutMs (restored in `finally`)
 * so the suite doesn't take multiple real minutes — this never touches
 * production timing (the mutation is undone before the process's other
 * tests, or production code, ever see it).
 *
 * Run: node --test test/video-poll-status.test.js
 */
import test from "node:test";
import assert from "node:assert/strict";

const {
  pollVideoStatus,
  extractVideoPollStatus,
  VIDEO_STATUS_FAILED,
  VideoGenerationFailedError,
  FatalError,
  timing,
} = await import("../lib/flow-api.js");

const REAL_TOKEN = "A".repeat(42);
const PROJECT_ID = "3fe16e7e-e725-4dc0-852b-80593cffdd9f";
const WORKFLOW_ID = "5b04d221-f639-4495-9fc3-48828edad1dd";
const MEDIA_ID = "eef3f601-ea48-4502-9fef-71639a89e197";
const PROMPT = "a small red ball rolling slowly across a white studio floor";

function fakePage({ wiz = {}, fetchImpl = null } = {}) {
  const grecaptcha = { enterprise: { execute: async () => "CAPTCHA_TOKEN_XYZ" } };
  const location = { href: "https://flow.google.com/project/" + PROJECT_ID };
  const window = { WIZ_global_data: wiz, grecaptcha, location, fetch: fetchImpl };
  return {
    async waitForLoadState() {},
    async evaluate(fn, arg) {
      globalThis.window = window;
      globalThis.grecaptcha = grecaptcha;
      globalThis.location = location;
      globalThis.fetch = fetchImpl || (async () => { throw new Error("fetch not stubbed"); });
      try {
        return await fn(arg);
      } finally {
        delete globalThis.window;
        delete globalThis.grecaptcha;
        delete globalThis.location;
        delete globalThis.fetch;
      }
    },
  };
}

function fullWiz() {
  return { SNlM0e: REAL_TOKEN, cfb2h: "boq_labs-ai-sandbox-frontend_20260903.13_p0", FdrFJe: "5839573032030491108" };
}

function chunkOf(obj) {
  const json = JSON.stringify(obj);
  return `${Buffer.byteLength(json, "utf8")}\n${json}\n`;
}
function canned(...rpcResults) {
  let out = ")]}'\n\n";
  for (const [rpcid, resultValue] of rpcResults) {
    out += chunkOf([["wrb.fr", rpcid, JSON.stringify(resultValue), null, null, null, "generic"]]);
  }
  out += chunkOf([["e", 4, null, null, 143]]);
  return out;
}

// Real captured wire shape (see video-generation.test.js) — parametrized
// only on the status marker at DETAIL[8][0], exactly what production code
// reads. Using an arbitrary status number here (for UNKNOWN/assumed-FAILED
// cases) changes nothing about the surrounding shape's fidelity.
function jwpdufResult(status) {
  return [null, status === 3 ? 48 : null,
    [[WORKFLOW_ID, PROJECT_ID, MEDIA_ID, "CAE", null,
      [[1788540716, 26271000], PROMPT, null, null, null, null,
        [null, [["abra_t2v_4s_360p", 1, null, null, 2, 4]], [[null, null, [[[PROMPT]]]]], null, 1],
        null, [status], 1],
    ]],
  ];
}

function fetchReturningStatuses(statuses) {
  let i = 0;
  return async () => {
    const status = statuses[Math.min(i, statuses.length - 1)];
    i++;
    return { ok: true, status: 200, text: async () => canned(["jwpduf", jwpdufResult(status)]) };
  };
}

/** Temporarily shrink poll timing for a fast test; always restored. */
async function withFastPolling(intervalMs, timeoutMs, fn) {
  const origInterval = timing.videoPollIntervalMs;
  const origTimeout = timing.videoPollTimeoutMs;
  timing.videoPollIntervalMs = intervalMs;
  timing.videoPollTimeoutMs = timeoutMs;
  try {
    await fn();
  } finally {
    timing.videoPollIntervalMs = origInterval;
    timing.videoPollTimeoutMs = origTimeout;
  }
}

// ---------------------------------------------------------------------------
// 1. PENDING -> continue polling (status extraction + a real two-cycle
//    poll that only resolves once a later poll reports COMPLETE).
// ---------------------------------------------------------------------------

test("extractVideoPollStatus: status 2 is PENDING", () => {
  assert.equal(extractVideoPollStatus(jwpdufResult(2)).status, 2);
});

test("pollVideoStatus continues past a PENDING poll into a later COMPLETE one", async () => {
  await withFastPolling(20, 5000, async () => {
    const fetchImpl = fetchReturningStatuses([2, 2, 3]);
    const page = fakePage({ wiz: fullWiz(), fetchImpl });
    const result = await pollVideoStatus(page, WORKFLOW_ID, PROJECT_ID);
    assert.equal(result.workflowId, WORKFLOW_ID);
    assert.equal(result.mediaId, MEDIA_ID);
  });
});

// ---------------------------------------------------------------------------
// 2. COMPLETE -> success (existing behavior, re-verified here alongside
//    the new detailPreview field so a regression in either is caught).
// ---------------------------------------------------------------------------

test("pollVideoStatus resolves immediately on the first COMPLETE poll", async () => {
  await withFastPolling(20, 5000, async () => {
    const fetchImpl = fetchReturningStatuses([3]);
    const page = fakePage({ wiz: fullWiz(), fetchImpl });
    const result = await pollVideoStatus(page, WORKFLOW_ID, PROJECT_ID);
    assert.equal(result.workflowId, WORKFLOW_ID);
    assert.equal(result.mediaId, MEDIA_ID);
  });
});

test("extractVideoPollStatus exposes a capped, non-throwing detailPreview", () => {
  const { detailPreview } = extractVideoPollStatus(jwpdufResult(2));
  assert.equal(typeof detailPreview, "string");
  assert.ok(detailPreview.length <= 201); // 200 + the "…" truncation marker
});

// ---------------------------------------------------------------------------
// 3/5/6. CONFIRMED FAILED (mechanism proof, value injected for the test
//    only — see module docstring) -> immediate failure, no 360s wait,
//    reason preserved when present, honest message when not.
// ---------------------------------------------------------------------------

test("an injected FAILED status throws VideoGenerationFailedError immediately (not a timeout)", async () => {
  const ASSUMED_FAILED_STATUS = 4; // injected for this test only — NOT a captured value
  VIDEO_STATUS_FAILED.add(ASSUMED_FAILED_STATUS);
  try {
    await withFastPolling(20, 5000, async () => {
      const fetchImpl = fetchReturningStatuses([ASSUMED_FAILED_STATUS, 3]); // a later COMPLETE must never be reached
      const page = fakePage({ wiz: fullWiz(), fetchImpl });
      const t0 = Date.now();
      await assert.rejects(
        () => pollVideoStatus(page, WORKFLOW_ID, PROJECT_ID),
        (err) => {
          assert.ok(err instanceof VideoGenerationFailedError);
          assert.ok(err instanceof FatalError, "must be a FatalError subclass so batch-runner does not retry it");
          assert.equal(err.recoverable, false);
          assert.equal(err.providerStatus, ASSUMED_FAILED_STATUS);
          assert.ok(err.message.includes("Flow video generation failed"));
          assert.ok(err.message.includes(String(ASSUMED_FAILED_STATUS)));
          assert.ok(!/timed out/i.test(err.message), "a confirmed failure must never read like a timeout");
          return true;
        },
      );
      const elapsedMs = Date.now() - t0;
      assert.ok(elapsedMs < 3000, `must fail on the FIRST poll, not wait out the budget (took ${elapsedMs}ms)`);
    });
  } finally {
    VIDEO_STATUS_FAILED.delete(ASSUMED_FAILED_STATUS);
  }
});

test("a FAILED result preserves the raw provider status/detail for diagnostics", async () => {
  const ASSUMED_FAILED_STATUS = 5;
  VIDEO_STATUS_FAILED.add(ASSUMED_FAILED_STATUS);
  try {
    await withFastPolling(20, 5000, async () => {
      const fetchImpl = fetchReturningStatuses([ASSUMED_FAILED_STATUS]);
      const page = fakePage({ wiz: fullWiz(), fetchImpl });
      await assert.rejects(
        () => pollVideoStatus(page, WORKFLOW_ID, PROJECT_ID),
        (err) => {
          assert.equal(err.providerStatus, ASSUMED_FAILED_STATUS);
          // No separate human-readable reason exists in this wire shape
          // beyond the status marker itself — providerDetail carries the
          // capped raw DETAIL array preview instead of an invented reason.
          assert.ok(err.providerDetail === null || typeof err.providerDetail === "string");
          return true;
        },
      );
    });
  } finally {
    VIDEO_STATUS_FAILED.delete(ASSUMED_FAILED_STATUS);
  }
});

// ---------------------------------------------------------------------------
// 4. UNKNOWN -> logged, never silently promoted to success OR failure;
//    the existing timeout/continue semantics still apply.
// ---------------------------------------------------------------------------

test("an arbitrary unrecognized status is neither success nor failure — polling continues", async () => {
  const ARBITRARY_UNKNOWN_STATUS = 999; // not 2, not 3, and not in VIDEO_STATUS_FAILED
  assert.ok(!VIDEO_STATUS_FAILED.has(ARBITRARY_UNKNOWN_STATUS));
  await withFastPolling(20, 5000, async () => {
    const fetchImpl = fetchReturningStatuses([ARBITRARY_UNKNOWN_STATUS, ARBITRARY_UNKNOWN_STATUS, 3]);
    const page = fakePage({ wiz: fullWiz(), fetchImpl });
    // Must NOT throw (not silently FAILED) and must NOT resolve early
    // (not silently COMPLETE) — it only resolves once a real COMPLETE
    // arrives on a later poll.
    const result = await pollVideoStatus(page, WORKFLOW_ID, PROJECT_ID);
    assert.equal(result.workflowId, WORKFLOW_ID);
  });
});

test("an unrecognized status logs the raw value without throwing credentials/tokens", async () => {
  const ARBITRARY_UNKNOWN_STATUS = 777;
  const originalConsoleError = console.error;
  const logged = [];
  console.error = (...args) => logged.push(args.join(" "));
  try {
    await withFastPolling(20, 5000, async () => {
      const fetchImpl = fetchReturningStatuses([ARBITRARY_UNKNOWN_STATUS, 3]);
      const page = fakePage({ wiz: fullWiz(), fetchImpl });
      await pollVideoStatus(page, WORKFLOW_ID, PROJECT_ID);
    });
  } finally {
    console.error = originalConsoleError;
  }
  const line = logged.find((l) => l.includes("pollVideoStatus"));
  assert.ok(line, "expected a [FLOW] pollVideoStatus diagnostic line");
  assert.ok(line.includes("raw_video_status=777"));
  assert.ok(line.includes("recognized=false"));
  assert.ok(line.includes(WORKFLOW_ID));
  assert.ok(!line.includes(REAL_TOKEN), "must never log the WIZ session token");
});

// ---------------------------------------------------------------------------
// 8. Timeout: a workflow that stays genuinely PENDING must still time out
//    exactly as before (existing behavior unchanged).
// ---------------------------------------------------------------------------

test("a workflow that never leaves PENDING still times out (existing behavior preserved)", async () => {
  await withFastPolling(10, 25, async () => {
    const fetchImpl = fetchReturningStatuses([2]);
    const page = fakePage({ wiz: fullWiz(), fetchImpl });
    await assert.rejects(
      () => pollVideoStatus(page, WORKFLOW_ID, PROJECT_ID),
      (err) => {
        assert.ok(/timed out/i.test(err.message));
        assert.ok(!(err instanceof VideoGenerationFailedError));
        return true;
      },
    );
  });
});

test("a timeout after seeing an unrecognized status includes the raw status, honestly labeled 'unrecognized'", async () => {
  await withFastPolling(10, 25, async () => {
    const fetchImpl = fetchReturningStatuses([42]);
    const page = fakePage({ wiz: fullWiz(), fetchImpl });
    await assert.rejects(
      () => pollVideoStatus(page, WORKFLOW_ID, PROJECT_ID),
      (err) => {
        assert.ok(/timed out/i.test(err.message));
        assert.ok(err.message.includes("42"));
        assert.ok(err.message.includes("unrecognized"));
        assert.ok(!/^Flow video generation failed/.test(err.message), "must not be rebranded as a confirmed failure");
        return true;
      },
    );
  });
});
