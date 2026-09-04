import { chromium } from "playwright";
import fs from "node:fs";
import { profileDir, ensureDirs } from "./paths.js";
import { urls } from "./flow-api.js";

/** @type {Map<string, import('playwright').BrowserContext>} */
const contexts = new Map();
/** @type {Map<string, import('playwright').Page>} */
const pages = new Map();

function launchOpts(headed) {
  // Prefer installed Google Chrome (looks more like a normal user).
  const opts = {
    headless: !headed,
    viewport: { width: 1280, height: 900 },
    args: [
      "--disable-blink-features=AutomationControlled",
      "--no-first-run",
      "--no-default-browser-check",
    ],
    ignoreDefaultArgs: ["--enable-automation"],
  };
  // channel chrome if present on macOS/Windows; fall back to bundled Chromium
  if (process.platform === "darwin" || process.platform === "win32") {
    opts.channel = "chrome";
  }
  return opts;
}

/**
 * Open (or reuse) a persistent browser context for this account.
 * @param {string} accountId
 * @param {{ headed?: boolean }} [opts]
 */
export async function openAccountBrowser(accountId, opts = {}) {
  ensureDirs();
  const headed = opts.headed !== false; // default headed for reliability / login
  if (contexts.has(accountId)) {
    const ctx = contexts.get(accountId);
    let page = pages.get(accountId);
    if (!page || page.isClosed()) {
      page = ctx.pages()[0] || (await ctx.newPage());
      pages.set(accountId, page);
    }
    return { context: ctx, page };
  }

  const userDataDir = profileDir(accountId);
  fs.mkdirSync(userDataDir, { recursive: true });

  let context;
  try {
    context = await chromium.launchPersistentContext(
      userDataDir,
      launchOpts(headed),
    );
  } catch (e) {
    // No Chrome channel — use Playwright Chromium
    if (String(e.message || e).includes("channel")) {
      const fallback = launchOpts(headed);
      delete fallback.channel;
      context = await chromium.launchPersistentContext(userDataDir, fallback);
    } else {
      throw e;
    }
  }

  contexts.set(accountId, context);
  context.on("close", () => {
    contexts.delete(accountId);
    pages.delete(accountId);
  });

  const page = context.pages()[0] || (await context.newPage());
  pages.set(accountId, page);
  return { context, page };
}

export async function gotoFlow(page) {
  // Flow moved off labs.google (where every URL had a "/tools/flow" path
  // segment) onto flow.google.com (which never does) — the old check below
  // was therefore ALWAYS true post-migration, forcing a fresh navigation to
  // flowHome on every single call even when the page was already sitting on
  // a perfectly good, already-open project. That's what caused the visible
  // "refreshing" loop: gotoFlow() throwing away an open project every time
  // prepareAccount() ran, which then had to fall through to creating a new
  // one. Skip navigating away from any URL that's already on the current
  // Flow domain — a project page included.
  const url = page.url();
  if (!url.includes("flow.google.com") && !url.includes("labs.google")) {
    await page.goto(urls.flowHome, {
      waitUntil: "domcontentloaded",
      timeout: 60000,
    });
  }
}

export async function closeAccountBrowser(accountId) {
  const ctx = contexts.get(accountId);
  if (ctx) {
    try {
      await ctx.close();
    } catch {}
  }
  contexts.delete(accountId);
  pages.delete(accountId);
}

export async function closeAllBrowsers() {
  const ids = [...contexts.keys()];
  for (const id of ids) await closeAccountBrowser(id);
}

export function isBrowserOpen(accountId) {
  return contexts.has(accountId);
}

export function getPage(accountId) {
  return pages.get(accountId) || null;
}
