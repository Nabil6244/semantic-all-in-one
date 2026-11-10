/**
 * Persistent YouTube playback capture worker.
 * One Chrome process, one page per JSON-lines job on stdin.
 * Captures decoded <video> via captureStream(); never fetches googlevideo URLs.
 */
import { chromium } from "playwright-core";
import { createInterface } from "node:readline";
import { writeSync } from "node:fs";
import { mkdtemp, writeFile, unlink, stat } from "node:fs/promises";
import { spawn } from "node:child_process";
import { tmpdir } from "node:os";
import path from "node:path";

const AD_WAIT_MS = 45000; // two unskippable pre-rolls can run ~30 s; an ad that never ends fails the video (never recorded)
const PLAYBACK_WAIT_MS = 20000;
const SEEK_WAIT_MS = 12000;
const CONSENT_MS = 2500;
const PAGE_TIMEOUT_MS = 45000;

function send(obj) {
  writeSync(1, `${JSON.stringify(obj)}\n`);
}

function log(msg) {
  writeSync(2, `[BROWSER] ${msg}\n`);
}

function run(cmd, args) {
  return new Promise((resolve) => {
    // windowsHide: true — without it, every ffmpeg convert flashes a black CMD
    // box on Windows during YouTube browser capture.
    const child = spawn(cmd, args, {
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
      shell: false,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => {
      stdout += d.toString();
    });
    child.stderr.on("data", (d) => {
      stderr += d.toString();
    });
    child.on("close", (code) => resolve({ code, stdout, stderr }));
    child.on("error", (err) => resolve({ code: -1, stdout, stderr: String(err) }));
  });
}

function pageTextLooksLike(text, patterns) {
  const lower = text.toLowerCase();
  return patterns.some((p) => lower.includes(p));
}

async function dismissConsent(page) {
  for (const sel of [
    'button:has-text("Accept all")',
    'button:has-text("Reject all")',
    'button[aria-label="Accept all"]',
    'button[aria-label="Reject all"]',
  ]) {
    const btn = page.locator(sel).first();
    if (await btn.count()) {
      try {
        await btn.click({ timeout: CONSENT_MS });
        log("dismissed consent");
        return true;
      } catch {
        /* try next */
      }
    }
  }
  return false;
}

async function classifyBlock(page) {
  let text = "";
  try {
    text = (await page.locator("body").innerText({ timeout: 3000 })).slice(0, 8000);
  } catch {
    return null;
  }
  if (
    pageTextLooksLike(text, [
      "video unavailable",
      "this video isn't available",
      "this video is not available",
      "private video",
      "has been removed",
      "account associated with this video has been terminated",
    ])
  ) {
    return { kind: "unavailable", error: "video unavailable" };
  }
  if (
    pageTextLooksLike(text, [
      "sign in to confirm you’re not a bot",
      "sign in to confirm you're not a bot",
      "confirm you are not a bot",
      "unusual traffic",
    ])
  ) {
    return { kind: "bot_blocked", error: "playback blocked: bot verification" };
  }
  if (
    pageTextLooksLike(text, [
      "age-restricted",
      "confirm your age",
      "may be inappropriate for some users",
      "login to confirm your age",
    ])
  ) {
    return { kind: "age_restricted", error: "age restricted" };
  }
  return null;
}

// The player marks itself while an ad plays (#movie_player.ad-showing / .ad-interrupting); the older overlay is checked too.
async function adShowing(page) {
  return page
    .evaluate(() => {
      const p = document.getElementById("movie_player");
      if (p && (p.classList.contains("ad-showing") || p.classList.contains("ad-interrupting"))) return true;
      if (document.querySelector(".ytp-ad-player-overlay, .ytp-ad-player-overlay-layout, .ytp-ad-text")) return true;
      // between two ads the player can drop its ad classes for a moment; the <video> then still holds an ad, whose length is not the
      // video's own (the player's getDuration() keeps the real video's length the whole time)
      const v = document.querySelector("video");
      const real = p && typeof p.getDuration === "function" ? Number(p.getDuration()) : NaN;
      if (v && Number.isFinite(v.duration) && v.duration > 0 && Number.isFinite(real) && real > 0 && Math.abs(v.duration - real) > 1.5) return true;
      return false;
    })
    .catch(() => false);
}

// 2026-11-09 (owner): an unskippable ad was recorded as a War scene's footage, because after 15 s the old wait carried on and captured
// whatever played. Now: click any skip button, fast-forward an unskippable ad to its end, and when an ad still has not ended after
// AD_WAIT_MS the video fails (kind playback_failed: the next candidate is tried) instead of being recorded.
async function skipAdIfPresent(page) {
  const deadline = Date.now() + AD_WAIT_MS;
  let seen = false;
  let clear = 0;
  while (Date.now() < deadline) {
    if (!(await adShowing(page))) {
      clear += 1;                      // ad-free for ~1.2 s in a row: a second ad that follows the first is caught before recording
      if (!seen || clear >= 3) {
        if (seen) log("ad finished");
        return;
      }
      await page.waitForTimeout(400);
      continue;
    }
    clear = 0;
    seen = true;
    const skip = page
      .locator(".ytp-ad-skip-button-modern, .ytp-ad-skip-button, .ytp-skip-ad-button, .ytp-ad-skip-button-container button")
      .first();
    if (await skip.count()) {
      try {
        await skip.click({ timeout: 800 });
        log("skipped ad");
      } catch {
        /* keep waiting */
      }
    }
    await page
      .evaluate(() => {
        const p = document.getElementById("movie_player");
        const v = document.querySelector("video");
        if (p && p.classList.contains("ad-showing") && v && Number.isFinite(v.duration) && v.duration > 0.5) {
          v.muted = true;
          v.currentTime = Math.max(0, v.duration - 0.1);
        }
      })
      .catch(() => {});
    await page.waitForTimeout(400);
  }
  throw Object.assign(new Error("an ad would not end; this video is skipped (an ad is never recorded)"), { kind: "playback_failed" });
}

async function reseek(page, startAt) {
  await page.evaluate(async (t) => {
    const v = document.querySelector("video");
    if (!v) return;
    v.muted = true;
    if (Number.isFinite(t) && Math.abs(v.currentTime - t) > 1.25) v.currentTime = t;
    try {
      await v.play();
    } catch {
      /* ignore */
    }
  }, startAt);
  await page.waitForTimeout(600);
}

async function waitForPlayback(page, start) {
  await page.waitForSelector("video", { timeout: PAGE_TIMEOUT_MS });
  await page.evaluate(async (startAt) => {
    const video = document.querySelector("video");
    if (!video) throw new Error("no video element");
    video.muted = true;
    try {
      await video.play();
    } catch {
      /* autoplay may still start muted */
    }
    if (Number.isFinite(startAt) && startAt > 0) {
      video.currentTime = startAt;
    }
  }, start);

  await skipAdIfPresent(page);

  await page.waitForFunction(
    (startAt) => {
      const v = document.querySelector("video");
      return Boolean(v && v.videoWidth > 0 && v.readyState >= 2);
    },
    start,
    { timeout: PLAYBACK_WAIT_MS }
  );

  await page.evaluate(async (startAt) => {
    const video = document.querySelector("video");
    video.muted = true;
    if (Math.abs(video.currentTime - startAt) > 1.25) {
      video.currentTime = startAt;
    }
    try {
      await video.play();
    } catch {
      /* ignore */
    }
  }, start);

  const progressed = await page.waitForFunction(
    (startAt) => {
      const v = document.querySelector("video");
      if (!v || v.paused && v.currentTime === 0) return false;
      return v.currentTime + 0.05 >= Math.max(0, startAt - 1.5) && v.videoWidth > 0;
    },
    start,
    { timeout: SEEK_WAIT_MS }
  ).catch(() => null);

  if (!progressed) {
    throw Object.assign(new Error("playback did not advance after seek"), { kind: "playback_failed" });
  }

  const t0 = await page.evaluate(() => document.querySelector("video").currentTime);
  await page.waitForTimeout(400);
  const t1 = await page.evaluate(() => document.querySelector("video").currentTime);
  if (!(t1 > t0 + 0.05) && !(t1 > start)) {
    try {
      await page.evaluate(async () => {
        await document.querySelector("video").play();
      });
      await page.waitForTimeout(400);
    } catch {
      /* ignore */
    }
    const t2 = await page.evaluate(() => document.querySelector("video").currentTime);
    if (!(t2 > t0 + 0.05)) {
      throw Object.assign(new Error("currentTime did not advance"), { kind: "playback_failed" });
    }
  }
}

async function requestHighestQuality(page) {
  const before = await page.evaluate(async () => {
    const player = document.getElementById("movie_player");
    const levels =
      player && typeof player.getAvailableQualityLevels === "function"
        ? player.getAvailableQualityLevels() || []
        : [];
    const order = ["hd1080", "hd720", "large"];
    const pick = order.find((q) => levels.includes(q)) || "hd1080";
    try {
      if (player && typeof player.setPlaybackQualityRange === "function") {
        player.setPlaybackQualityRange(pick, pick);
      }
    } catch {
      /* ignore */
    }
    try {
      if (player && typeof player.setPlaybackQuality === "function") {
        player.setPlaybackQuality(pick);
      }
    } catch {
      /* ignore */
    }
    const v = document.querySelector("video");
    return {
      levels,
      pick,
      width: v ? v.videoWidth : 0,
      height: v ? v.videoHeight : 0,
    };
  });
  log(
    `player quality requested ${before.pick} (available: ${(before.levels || []).join(",") || "unknown"}; was ${before.width}x${before.height})`
  );
  await page
    .waitForFunction(
      () => {
        const v = document.querySelector("video");
        return Boolean(v && v.videoHeight >= 720);
      },
      { timeout: 8000 }
    )
    .catch(() => {});
  const after = await page.evaluate(() => {
    const v = document.querySelector("video");
    return { width: v ? v.videoWidth : 0, height: v ? v.videoHeight : 0 };
  });
  log(`video element ${after.width}x${after.height}`);
  return after;
}

async function captureClip(page, durationSec) {
  const durationMs = Math.round(Math.max(2.5, Math.min(8, durationSec)) * 1000);
  const record = await page.evaluate(async (ms) => {
    const video = document.querySelector("video");
    if (!video) return { error: "no video element" };
    if (typeof video.captureStream !== "function") return { error: "captureStream missing" };
    const stream = video.captureStream();
    if (!stream.getVideoTracks().length) return { error: "no video tracks on captureStream" };
    const mime = MediaRecorder.isTypeSupported("video/webm;codecs=vp9,opus")
      ? "video/webm;codecs=vp9,opus"
      : MediaRecorder.isTypeSupported("video/webm;codecs=vp8,opus")
        ? "video/webm;codecs=vp8,opus"
        : "video/webm";
    const chunks = [];
    const height = video.videoHeight || 720;
    const bitrate = height >= 1080 ? 8_000_000 : height >= 720 ? 5_000_000 : 2_500_000;
    const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: bitrate });
    rec.ondataavailable = (e) => {
      if (e.data && e.data.size) chunks.push(e.data);
    };
    rec.start(200);
    await new Promise((r) => setTimeout(r, ms + 400));
    await new Promise((resolve) => {
      rec.onstop = resolve;
      rec.stop();
    });
    const blob = new Blob(chunks, { type: mime });
    const buf = new Uint8Array(await blob.arrayBuffer());
    let binary = "";
    for (let i = 0; i < buf.length; i += 0x8000) {
      binary += String.fromCharCode(...buf.subarray(i, i + 0x8000));
    }
    return { bytes: buf.length, b64: btoa(binary), mime };
  }, durationMs);
  if (record.error || !record.b64 || record.bytes < 20000) {
    throw Object.assign(new Error(record.error || `capture too small (${record.bytes || 0} bytes)`), {
      kind: "capture_failed",
    });
  }
  return record;
}

async function convertToMp4(webmPath, outPath, duration, ffmpegBin) {
  const ff = await run(ffmpegBin, [
    "-y",
    "-i",
    webmPath,
    "-t",
    String(duration),
    "-c:v",
    "libx264",
    "-c:a",
    "aac",
    "-movflags",
    "+faststart",
    outPath,
  ]);
  if (ff.code !== 0) {
    throw Object.assign(new Error(`ffmpeg failed (${ff.code}): ${(ff.stderr || "").slice(-800)}`), {
      kind: "conversion_failed",
    });
  }
}

let browser;

async function launchBrowser() {
  const executable = process.env.YOUTUBE_CHROME_PATH || "";
  const opts = {
    headless: process.env.YOUTUBE_CHROME_HEADED === "1" ? false : true,
    args: ["--autoplay-policy=no-user-gesture-required", "--disable-blink-features=AutomationControlled"],
  };
  if (executable) {
    opts.executablePath = executable;
    browser = await chromium.launch(opts);
    log("chrome launched (YOUTUBE_CHROME_PATH)");
    return;
  }
  const channel = process.env.YOUTUBE_CHROME_CHANNEL || "chrome";
  try {
    browser = await chromium.launch({ ...opts, channel });
    log(`chrome launched (channel=${channel})`);
  } catch (e) {
    // No system Chrome — use Playwright Chromium (downloaded once by the app).
    const msg = String(e && e.message ? e.message : e);
    if (msg.includes("channel") || msg.includes("Executable doesn't exist") || msg.includes("browserType.launch")) {
      browser = await chromium.launch(opts);
      log("playwright chromium launched (no system chrome)");
    } else {
      throw e;
    }
  }
}

async function handleJob(job) {
  const { video_id: videoId, start, duration, out, ffmpeg } = job;
  if (!videoId || !out) {
    const result = { ok: false, kind: "playback_failed", error: "missing video_id or out" };
    send({ id: job.id, ...result });
    return result;
  }
  const startAt = Number(start) || 0;
  const dur = Number(duration) || 3.5;
  const ffmpegBin = ffmpeg || process.env.FFMPEG || "ffmpeg";
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    userAgent:
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
  });
  const page = await context.newPage();
  let tmpWebm;
  let result;
  try {
    log(`opening video ${videoId}`);
    await page.goto(
      `https://www.youtube.com/watch?v=${encodeURIComponent(videoId)}&t=${Math.floor(startAt)}s&vq=hd1080`,
      {
        waitUntil: "domcontentloaded",
        timeout: PAGE_TIMEOUT_MS,
      }
    );
    await dismissConsent(page);
    const blocked = await classifyBlock(page);
    if (blocked) {
      log(blocked.error);
      result = { ok: false, ...blocked };
    } else {
      log("waiting for player");
      try {
        await waitForPlayback(page, startAt);
      } catch (err) {
        const again = await classifyBlock(page);
        if (again) {
          log(again.error);
          result = { ok: false, ...again };
        } else {
          throw err;
        }
      }
      if (!result) {
        log("playback ready");
        const q = await requestHighestQuality(page);
        log(`seeking to ${startAt}s`);
        if (await adShowing(page)) {        // an ad that started after the first wait (pre-roll after the seek, or a mid-roll)
          log("ad before capture; waiting it out");
          await skipAdIfPresent(page);
          await reseek(page, startAt);
        }
        log("playback confirmed");
        log(`capturing ${dur}s`);
        const record = await captureClip(page, dur);
        if (await adShowing(page)) {
          throw Object.assign(new Error("an ad played during the capture; this clip is not used"), { kind: "playback_failed" });
        }
        const tmpDir = await mkdtemp(path.join(tmpdir(), "yt-browser-"));
        tmpWebm = path.join(tmpDir, `${videoId}.webm`);
        await writeFile(tmpWebm, Buffer.from(record.b64, "base64"));
        log(`capture complete: ${(record.bytes / 1024).toFixed(0)} KB webm`);
        log("converting WebM -> MP4");
        await convertToMp4(tmpWebm, out, dur, ffmpegBin);
        const st = await stat(out);
        log(`wrote ${out} (${st.size} bytes)`);
        result = {
          ok: true,
          duration: dur,
          bytes: st.size,
          out,
          width: q.width,
          height: q.height,
        };
      }
    }
  } catch (err) {
    const kind = err.kind || (String(err.message || err).includes("Timeout") ? "timeout" : "playback_failed");
    result = { ok: false, kind, error: String(err.message || err) };
  }
  send({ id: job.id, ...result });
  if (tmpWebm) {
    unlink(tmpWebm).catch(() => {});
  }
  setImmediate(() => {
    page.close().catch(() => {});
    context.close().catch(() => {});
  });
  return result;
}

async function main() {
  try {
    await launchBrowser();
  } catch (err) {
    send({ type: "fatal", kind: "browser_crashed", error: String(err.message || err) });
    process.exit(1);
  }
  send({ type: "ready" });
  const rl = createInterface({ input: process.stdin });
  for await (const line of rl) {
    if (!line.trim()) continue;
    let job;
    try {
      job = JSON.parse(line);
    } catch {
      send({ ok: false, kind: "playback_failed", error: "invalid json" });
      continue;
    }
    if (job.cmd === "shutdown") {
      break;
    }
    await handleJob(job);
  }
  try {
    await browser?.close();
  } catch {
    /* ignore */
  }
  process.exit(0);
}

process.on("uncaughtException", (err) => {
  send({ type: "fatal", kind: "browser_crashed", error: String(err) });
  process.exit(1);
});

main();
