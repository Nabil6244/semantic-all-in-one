/**
 * Extension-parity reCAPTCHA mint (Auto Flow mainworld-bridge + mint-on-about).
 *
 * The working extension prefers minting on a hidden https://flow.google.com/about
 * tab with grecaptcha.enterprise.execute(siteKey, { action }), then uses that
 * token in batchexecute from the /project tab. Minting only on /project (or with
 * a mismatched site key) is what the bridge comments link to UNUSUAL_ACTIVITY.
 */
import { secrets } from "../config.js";
import { batchexecute } from "./batchexecute-config.js";

const ABOUT_URL = "https://flow.google.com/about";

/**
 * @param {import('playwright').Page} projectPage
 * @param {string} action IMAGE_GENERATION | VIDEO_GENERATION | …
 * @returns {Promise<{ token: string, mintedOn: string, durationMs: number }>}
 */
export async function mintCaptchaLikeExtension(projectPage, action) {
  const siteKey = secrets.recaptchaSiteKey;
  const context = projectPage.context();
  const about = await context.newPage();
  const started = Date.now();
  try {
    await about.goto(ABOUT_URL, { waitUntil: "domcontentloaded", timeout: 60000 });
    // Match mainworld-bridge injectGrecaptcha + waitGrecaptcha + mintCaptcha.
    const token = await about.evaluate(
      async ({ siteKey, action }) => {
        function detectSiteKey() {
          try {
            const cfg = typeof ___grecaptcha_cfg !== "undefined" ? ___grecaptcha_cfg : undefined;
            const clients = cfg && cfg.clients;
            if (!clients) return "";
            for (const ck of Object.keys(clients)) {
              const client = clients[ck];
              for (const p of Object.keys(client)) {
                const v = client[p];
                if (v && typeof v === "object") {
                  for (const p2 of Object.keys(v)) {
                    const v2 = v[p2];
                    if (v2 && typeof v2 === "object" && v2.sitekey) return v2.sitekey;
                  }
                }
              }
            }
          } catch {
            /* ignore */
          }
          return "";
        }

        function injectGrecaptcha(key) {
          try {
            if (window.grecaptcha?.enterprise?.execute) return;
            if (!key) return;
            if (document.querySelector("script[data-af-recaptcha]")) return;
            try {
              if (window.trustedTypes?.createPolicy) {
                window.trustedTypes.createPolicy("default", {
                  createScriptURL: (u) => {
                    if (/^https:\/\/(www\.google\.com\/recaptcha\/|www\.gstatic\.com\/recaptcha\/)/.test(u))
                      return u;
                    throw new Error("blocked");
                  },
                  createScript: (s) => s,
                  createHTML: (s) => s,
                });
              }
            } catch {
              /* default policy already exists */
            }
            const s = document.createElement("script");
            const nEl = document.querySelector("script[nonce]");
            if (nEl?.nonce) s.nonce = nEl.nonce;
            s.src =
              "https://www.google.com/recaptcha/enterprise.js?render=" + encodeURIComponent(key);
            s.async = true;
            s.setAttribute("data-af-recaptcha", "1");
            (document.head || document.documentElement).appendChild(s);
          } catch {
            /* best-effort */
          }
        }

        async function waitGrecaptcha(ms) {
          const deadline = Date.now() + ms;
          for (;;) {
            if (window.grecaptcha?.enterprise?.execute) return true;
            if (Date.now() > deadline) return false;
            await new Promise((r) => setTimeout(r, 300));
          }
        }

        const detected = detectSiteKey();
        if (!window.grecaptcha?.enterprise?.execute) {
          injectGrecaptcha(siteKey || detected);
        }
        if (!(await waitGrecaptcha(10000))) {
          return { token: null, error: "grecaptcha.enterprise not available on /about" };
        }
        const key = siteKey || detected;
        if (!key) return { token: null, error: "site key unresolved" };
        await new Promise((resolve) => {
          try {
            window.grecaptcha.enterprise.ready(resolve);
          } catch {
            resolve();
          }
        });
        try {
          const token = await Promise.race([
            window.grecaptcha.enterprise.execute(key, { action }),
            new Promise((_, reject) =>
              setTimeout(() => reject(new Error("execute timeout")), 15000),
            ),
          ]);
          return { token, error: null };
        } catch (e) {
          return { token: null, error: String(e?.message || e) };
        }
      },
      { siteKey, action },
    );

    if (!token?.token) {
      throw new Error(token?.error || "reCAPTCHA execute on /about returned empty token");
    }
    return {
      token: String(token.token),
      mintedOn: ABOUT_URL,
      durationMs: Date.now() - started,
    };
  } finally {
    try {
      await about.close();
    } catch {
      /* ignore */
    }
  }
}

/**
 * Prefer /about mint (extension SW path); fall back to project-page mint
 * (extension content-script path) when /about fails.
 */
export async function mintCaptchaWithFallback(projectPage, action) {
  try {
    return await mintCaptchaLikeExtension(projectPage, action);
  } catch (aboutErr) {
    const siteKey = secrets.recaptchaSiteKey;
    const started = Date.now();
    const token = await projectPage.evaluate(
      async ({ siteKey, action }) => {
        const grec = window.grecaptcha?.enterprise;
        if (!grec?.execute) return null;
        await new Promise((resolve) => {
          try {
            grec.ready(resolve);
          } catch {
            resolve();
          }
        });
        return grec.execute(siteKey, { action });
      },
      { siteKey, action },
    );
    if (!token) {
      throw new Error(
        `captcha failed (about: ${aboutErr?.message || aboutErr}; project mint empty)`,
      );
    }
    return {
      token: String(token),
      mintedOn: "project-fallback",
      durationMs: Date.now() - started,
      aboutError: String(aboutErr?.message || aboutErr),
    };
  }
}

/** Headers matching Auto Flow adapter batchexecute POST. */
export const BATCHEXECUTE_HEADERS = {
  "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
  "X-Same-Domain": "1",
};

export function extensionHl() {
  return "en";
}

/** Random _reqid in the extension's 1e5–1e6 range. */
export function extensionReqId() {
  return Math.floor(100000 + Math.random() * 900000);
}

export function captchaActionForMedia(mediaKind) {
  return mediaKind === "video"
    ? batchexecute.captchaActions.video
    : batchexecute.captchaActions.image;
}
