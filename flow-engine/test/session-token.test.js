/**
 * Flow moved off labs.google onto flow.google.com, and the old
 * `/fx/api/auth/session` REST route is gone (confirmed live: it now 200s
 * with the app's HTML shell, not JSON). The new app is built on Google's
 * Wiz framework, which embeds the signed-in session's token directly in the
 * page as `window.WIZ_global_data.SNlM0e` — getSessionToken() now reads
 * that in-page value instead of making a network request.
 * Run: node --test test/session-token.test.js
 */
import test from "node:test";
import assert from "node:assert/strict";

const { getSessionToken, waitForSessionToken } = await import("../lib/flow-api.js");

const REAL_TOKEN = "A".repeat(42); // shape observed live: a 42-char string

/** Minimal page stub: runs the evaluated fn with `window` set from a script. */
function fakePage(windowStates) {
  let i = 0;
  return {
    calls: 0,
    async waitForLoadState() {},
    async evaluate(fn) {
      this.calls++;
      globalThis.window = windowStates[Math.min(i++, windowStates.length - 1)];
      try {
        return fn();
      } finally {
        delete globalThis.window;
      }
    },
  };
}

test("a populated SNlM0e token means signed in", async () => {
  const page = fakePage([{ WIZ_global_data: { SNlM0e: REAL_TOKEN } }]);
  assert.equal(await getSessionToken(page), REAL_TOKEN);
});

test("a wrapped {e: token} shape is also accepted", async () => {
  const page = fakePage([{ WIZ_global_data: { SNlM0e: { e: REAL_TOKEN } } }]);
  assert.equal(await getSessionToken(page), REAL_TOKEN);
});

test("missing WIZ_global_data means not signed in", async () => {
  const page = fakePage([{}]);
  assert.equal(await getSessionToken(page), null);
});

test("WIZ_global_data present but SNlM0e missing means not signed in", async () => {
  const page = fakePage([{ WIZ_global_data: { OtherKey: "x" } }]);
  assert.equal(await getSessionToken(page), null);
});

test("empty string token means not signed in", async () => {
  const page = fakePage([{ WIZ_global_data: { SNlM0e: "" } }]);
  assert.equal(await getSessionToken(page), null);
});

test("whitespace-only token means not signed in", async () => {
  const page = fakePage([{ WIZ_global_data: { SNlM0e: "   " } }]);
  assert.equal(await getSessionToken(page), null);
});

test("null/undefined token means not signed in", async () => {
  assert.equal(await getSessionToken(fakePage([{ WIZ_global_data: { SNlM0e: null } }])), null);
  assert.equal(await getSessionToken(fakePage([{ WIZ_global_data: { SNlM0e: undefined } }])), null);
});

test("a non-string, non-{e} shape is not mistaken for a token", async () => {
  const page = fakePage([{ WIZ_global_data: { SNlM0e: 12345 } }]);
  assert.equal(await getSessionToken(page), null);
});

test("no network request is made", async () => {
  const originalFetch = globalThis.fetch;
  let called = false;
  globalThis.fetch = async () => {
    called = true;
    throw new Error("getSessionToken must not fetch");
  };
  try {
    await getSessionToken(fakePage([{ WIZ_global_data: { SNlM0e: REAL_TOKEN } }]));
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(called, false);
});

// ---- existing page/browser behavior (polling, error tolerance) is intact ----

test("a token arriving late is picked up instead of failing the account", async () => {
  // The SPA can take a moment after navigation before WIZ_global_data is
  // populated — waitForSessionToken's polling/backoff must still cover that.
  const page = fakePage([{}, {}, { WIZ_global_data: { SNlM0e: REAL_TOKEN } }]);
  assert.equal(await waitForSessionToken(page, 8000), REAL_TOKEN);
  assert.ok(page.calls >= 3, "must have polled, not read once");
});

test("polling gives up and reports signed-out for a genuinely dead session", async () => {
  const page = fakePage([{}]);
  const started = Date.now();
  assert.equal(await waitForSessionToken(page, 1200), null);
  assert.ok(Date.now() - started >= 1000, "must actually wait before giving up");
  assert.ok(Date.now() - started < 6000, "must be bounded");
});

test("a mid-navigation evaluate error is treated as 'not ready', not fatal", async () => {
  const page = {
    calls: 0,
    async waitForLoadState() {},
    async evaluate() {
      this.calls++;
      if (this.calls < 3) throw new Error("Execution context was destroyed");
      return "at-456";
    },
  };
  assert.equal(await waitForSessionToken(page, 8000), "at-456");
});

test("the signed-out message is still reachable for a real sign-out", async () => {
  const src = await import("node:fs").then((fs) =>
    fs.readFileSync(new URL("../lib/flow-api.js", import.meta.url), "utf8"),
  );
  assert.match(src, /Not signed in to labs\.google/);
  // ...but only after polling, never off a single immediate read.
  assert.match(src, /await waitForSessionToken\(page\);\s*\n\s*if \(!token\)/);
});
