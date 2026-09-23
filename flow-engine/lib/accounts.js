import { chromium } from "playwright";
import fs from "node:fs";
import { profileDir, ensureDirs } from "./paths.js";
import { flowGoto, logFlowNav, urls } from "./flow-api.js";

/** @type {Map<string, import('playwright').BrowserContext>} */
const contexts = new Map();
/** @type {Map<string, import('playwright').Page>} */
const pages = new Map();

function tagPage(page, accountId) {
  if (!page) return page;
  try {
    page.__flowAccountId = accountId;
    if (!page.__flowOpenedAt) page.__flowOpenedAt = Date.now();
  } catch {
    /* ignore */
  }
  return page;
}

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
      page = tagPage(ctx.pages()[0] || (await ctx.newPage()), accountId);
      pages.set(accountId, page);
      logFlowNav(page, "page.create", "openAccountBrowser:reuse-context-new-page", {
        accountId,
      });
    } else {
      tagPage(page, accountId);
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

  const page = tagPage(context.pages()[0] || (await context.newPage()), accountId);
  pages.set(accountId, page);
  logFlowNav(page, "page.create", "openAccountBrowser:new-context", {
    accountId,
    targetUrl: `profile=${userDataDir}`,
  });
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
    await flowGoto(page, urls.flowHome, "gotoFlow:not-on-flow-domain", {
      waitUntil: "domcontentloaded",
      timeout: 60000,
    });
  } else {
    logFlowNav(page, "gotoFlow.skip", "already-on-flow-domain");
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

/**
 * TEMPORARY read-only diagnostic — measures browser runtime state (navigator/
 * WebGL/service-worker/location facts) on an account's Flow page, for a
 * one-off differential audit against a normal Chrome session. Never touches
 * Flow RPCs, reCAPTCHA, generation, or browser launch configuration; never
 * reads cookies, WIZ values, or any query parameter besides `hl`.
 *
 * Reuses the existing page if the account's browser is already open (no new
 * browser, no new page, no reload); only opens/navigates if nothing is open
 * yet for this account, since there is otherwise nothing to measure.
 *
 * Remove this function (and its server.js/orchestrator.js wiring) once the
 * one-off measurement it exists for is done — it is not part of normal
 * account/generation behavior.
 */
export async function inspectAccountPage(accountId) {
  let page = getPage(accountId);
  let openedFresh = false;
  if (!page || page.isClosed()) {
    ({ page } = await openAccountBrowser(accountId, { headed: true }));
    await gotoFlow(page);
    openedFresh = true;
  }

  const data = await page.evaluate(() => {
    const out = {
      webdriver: navigator.webdriver ?? null,
      pluginsLength: navigator.plugins ? navigator.plugins.length : null,
      languages: navigator.languages ? Array.from(navigator.languages) : null,
      language: navigator.language ?? null,
      userAgent: navigator.userAgent ?? null,
      userAgentData: null,
      webglVendor: null,
      webglRenderer: null,
      serviceWorkerScopes: null,
      href: location.href,
      pathname: location.pathname,
      hl: null,
    };

    try {
      if (navigator.userAgentData) {
        out.userAgentData = {
          brands: navigator.userAgentData.brands || null,
          mobile: navigator.userAgentData.mobile ?? null,
          platform: navigator.userAgentData.platform ?? null,
        };
      }
    } catch {}

    try {
      const canvas = document.createElement("canvas");
      const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
      if (gl) {
        const ext = gl.getExtension("WEBGL_debug_renderer_info");
        if (ext) {
          out.webglVendor = gl.getParameter(ext.UNMASKED_VENDOR_WEBGL);
          out.webglRenderer = gl.getParameter(ext.UNMASKED_RENDERER_WEBGL);
        }
      }
    } catch {}

    try {
      const u = new URL(location.href);
      out.hl = u.searchParams.get("hl");
    } catch {}

    return out;
  });

  // Separate evaluate: getRegistrations() is async and awaiting it inline
  // above would need top-level await inside the sync evaluate callback.
  const scopes = await page.evaluate(async () => {
    try {
      if (!navigator.serviceWorker || !navigator.serviceWorker.getRegistrations) return null;
      const regs = await navigator.serviceWorker.getRegistrations();
      return regs.map((r) => r.scope);
    } catch {
      return null;
    }
  });
  data.serviceWorkerScopes = scopes;

  return { data, openedFresh };
}
