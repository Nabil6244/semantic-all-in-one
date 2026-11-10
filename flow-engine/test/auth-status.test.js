/**
 * Auth detection for Accounts Refresh All / Sign in.
 * Run: node --test test/auth-status.test.js
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { decideAuthStatus } from "../lib/flow-api.js";

test("SNlM0e token means signed in", () => {
  const d = decideAuthStatus({
    token: "A".repeat(42),
    url: "https://flow.google.com/",
    readyState: "complete",
  });
  assert.equal(d.authenticated, true);
  assert.equal(d.uncertain, false);
  assert.equal(d.decision, "wiz-token");
});

test("stable /about with Sign-in CTA and no avatar is signed out (not a false negative)", () => {
  const d = decideAuthStatus({
    token: null,
    url: "https://flow.google.com/about",
    readyState: "complete",
    hasSignInCta: true,
    hasAvatar: false,
    hasGoogleCookies: true, // leftover cookies must not override the shell
  });
  assert.equal(d.authenticated, false);
  assert.equal(d.uncertain, false);
  assert.equal(d.decision, "signed-out-shell");
});

test("page still loading is unknown, never signed-out", () => {
  const d = decideAuthStatus({
    token: null,
    url: "https://flow.google.com/",
    readyState: "loading",
  });
  assert.equal(d.authenticated, false);
  assert.equal(d.uncertain, true);
  assert.equal(d.decision, "unknown-loading");
});

test("evaluate failure is unknown, never signed-out", () => {
  const d = decideAuthStatus({
    token: null,
    url: "https://flow.google.com/",
    readyState: "complete",
    evaluateError: "Execution context was destroyed",
  });
  assert.equal(d.uncertain, true);
  assert.equal(d.authenticated, false);
});

test("about:blank / not on Flow yet is unknown", () => {
  const d = decideAuthStatus({
    token: null,
    url: "about:blank",
    readyState: "complete",
  });
  assert.equal(d.uncertain, true);
});

test("avatar + Google cookies on settled home means signed in without waiting for a brittle selector alone", () => {
  const d = decideAuthStatus({
    token: null,
    url: "https://flow.google.com/",
    readyState: "complete",
    hasAvatar: true,
    hasGoogleCookies: true,
    hasSignInCta: false,
  });
  assert.equal(d.authenticated, true);
  assert.equal(d.uncertain, false);
  assert.equal(d.decision, "dom-avatar");
});

test("Google cookies alone while WIZ hydrates stay unknown", () => {
  const d = decideAuthStatus({
    token: null,
    url: "https://flow.google.com/",
    readyState: "complete",
    hasAvatar: false,
    hasGoogleCookies: true,
    hasSignInCta: false,
  });
  assert.equal(d.uncertain, true);
  assert.equal(d.decision, "unknown-cookies-only");
});

test("checkAuthStatus never navigates (passive observe contract)", () => {
  const src = fs.readFileSync(new URL("../lib/flow-api.js", import.meta.url), "utf8");
  // The auth check used to page.goto flowHome whenever url() flickered off
  // flow.google.com mid-reload — that is the reload-loop root cause.
  assert.doesNotMatch(
    src,
    /export async function checkAuthStatus[\s\S]*?flowGoto\([\s\S]*?checkAuthStatus:not-on-flow-domain/,
  );
  assert.match(src, /never page\.goto \/ reload/);
});

test("loginAccount observes passively after a single gotoFlow", () => {
  const src = fs.readFileSync(new URL("../lib/orchestrator.js", import.meta.url), "utf8");
  assert.match(src, /observing passively/);
  assert.match(src, /dismissOverlays:\s*false/);
  assert.match(src, /cancelLogin/);
});

test("refreshAccount does not force authenticated:false on catch / uncertain", () => {
  const src = fs.readFileSync(new URL("../lib/orchestrator.js", import.meta.url), "utf8");
  assert.match(src, /Check inconclusive/);
  // The old catch forced a sign-out: updateAccount(accountId, { authenticated: false ...})
  // inside refreshAccount's catch. Keep that from returning.
  const refresh = src.slice(src.indexOf("export async function refreshAccount"));
  const catchBlock = refresh.slice(refresh.indexOf("} catch (e)"), refresh.indexOf("pushState();", refresh.indexOf("} catch (e)")));
  assert.doesNotMatch(catchBlock, /authenticated:\s*false/);
});
