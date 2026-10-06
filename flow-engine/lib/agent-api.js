/**
 * Flow agent mode ("Agent" in Flow's prompt box): many images from ONE request.
 *
 * Captured live on flow.google.com (2026-10-06), from the page's own requests:
 *
 *   1. csbIsb (batchexecute)  args [projectId, null, <client request id, upper-case uuid>]
 *        -> [[<chat id>, [...timestamps...]]]          creates the project's agent chat; Google assigns the chat id
 *   2. FlowCreationAgentService/StreamChat (same host, same bl / f.sid / hl / _reqid / rt query, form body f.req + at)
 *        f.req = [null, JSON([chatId, [[[[message]]]], ["projects/<projectId>", null, [<reCAPTCHA token>, 1], null, null, turn]])]
 *        turn = 1 for a chat's first message, +1 per message after that.
 *      The reply is a stream of batchexecute frames. The agent first PLANS one `generate_image` tool call per image
 *      (prompt it wrote, aspect_ratio, model_usage_key, model_display_name, placeholder_frontend_id), then reports one
 *      RESULT per call, linked by placeholder_frontend_id (status, media_id, workflow_id, batch_id, display_name).
 *   3. as29s [mediaId] -> the media detail with its signed https://flow-content.google/image/... URL (the download).
 *
 * Observed behaviour (6 / 12 / 24-scene tests): one call and one result per numbered scene, in order, all "success",
 * ~22-32 s for the whole batch. The agent always used model_usage_key HARBOR_SEAL (Nano Banana 2 Lite) even when its
 * settings or the message asked for Nano Banana 2, and labels it "Nano Banana 2": trust model_usage_key, never the label.
 *
 * This file only talks to Flow; the batching, ledger and download decisions live in agent-runner.js.
 */
import crypto from "node:crypto";
import { batchexecute } from "./batchexecute-config.js";
import { BATCHEXECUTE_HEADERS, mintCaptchaWithFallback } from "./extension-captcha.js";
import { timing } from "../config.js";
import { currentHl, nextReqId, parseBatchExecuteResponse } from "./flow-api.js";
import { Submission, tagSubmission } from "./generation-state.js";

export const AGENT_STREAM_PATH =
  "/_/AiSandboxAngularFrontend/data/google.internal.labs.aisandbox.proto.flow.agent.v1.FlowCreationAgentService/StreamChat";
/** Flow's own agent sendMessage mints its token with this action (seen in Flow's JS 2026-10-06; images use
 * IMAGE_GENERATION). A token for the wrong action is answered with PUBLIC_ERROR_UNUSUAL_ACTIVITY. */
export const AGENT_RECAPTCHA_ACTION = "CHAT_GENERATION";
export const AGENT_CHAT_RPC = "csbIsb";
/** The aspect ratio strings the agent reports, for each image aspect setting. */
export const AGENT_ASPECT_FOR_SETTING = {
  IMAGE_ASPECT_RATIO_LANDSCAPE: "16:9",
  IMAGE_ASPECT_RATIO_PORTRAIT: "9:16",
  IMAGE_ASPECT_RATIO_SQUARE: "1:1",
};
/** HTTP statuses after which the request may still have been processed (same rule as the image path). */
const AMBIGUOUS_4XX = new Set([408, 409, 499]);
const REFUSAL_GRPC_CODES = new Set([3, 5, 7, 8, 9, 11, 12, 16]);

/** The scene ID the agent is asked to name an image with (S01, S02, …): the primary link between an image and its scene. */
export function agentSceneId(i) {
  return `S${String(i + 1).padStart(2, "0")}`;
}

const norm = (t) => String(t || "").replace(/\s+/g, " ").trim();

/**
 * The style text every scene shares (an opening and/or ending, cut at a word boundary), so the message can carry it once:
 * many projects add the same long style paragraph to every prompt, which otherwise fills the message after ~14 scenes.
 * Returns { opening, ending, texts } where opening + text + ending === the scene's prompt (whitespace normalised).
 */
export function splitSharedStyle(prompts, { minChars = 120, minSceneChars = 12 } = {}) {
  const ps = prompts.map(norm);
  const none = { opening: "", ending: "", texts: ps };
  if (ps.length < 2) return none;
  const cut = (common, fromEnd) => {
    // Keep only whole words: back off to the last space (opening) / first space (ending).
    if (!common) return "";
    if (!fromEnd) {
      if (ps.every((p) => p.length === common.length || p[common.length] === " ")) return common;
      const at = common.lastIndexOf(" ");
      return at > 0 ? common.slice(0, at + 1) : "";
    }
    if (ps.every((p) => p.length === common.length || p[p.length - common.length - 1] === " ")) return common;
    const at = common.indexOf(" ");
    return at >= 0 ? common.slice(at) : "";
  };
  let pre = ps[0];
  for (const p of ps) while (!p.startsWith(pre)) pre = pre.slice(0, -1);
  let opening = cut(pre, false);
  let suf = ps[0];
  for (const p of ps) while (!p.endsWith(suf)) suf = suf.slice(1);
  let ending = cut(suf, true);
  if (opening.length < minChars) opening = "";
  if (ending.length < minChars) ending = "";
  const texts = ps.map((p) => p.slice(opening.length, p.length - ending.length).trim());
  if (texts.some((t) => t.length < minSceneChars)) return none;
  return { opening: opening.trim(), ending: ending.trim(), texts };
}

/**
 * The message the agent gets: one line per scene with its ID, the shared style once, and the rules (one image each, the
 * text copied exactly, the image named with its scene ID). Observed live: the agent copies scene text verbatim, but Flow names
 * images itself, so the exact text is what ties an image to its scene (see mapCallsToScenes).
 */
export function buildAgentMessage(sceneTexts, { aspect = "16:9", opening = "", ending = "" } = {}) {
  const lines = sceneTexts.map((t, i) => `${agentSceneId(i)}: ${norm(t)}`);
  const parts = [opening && "the shared opening", "the scene text", ending && "the shared ending"].filter(Boolean).join(", then ");
  return [
    `Make exactly one image for each of the ${sceneTexts.length} scenes below, in this order, aspect ratio ${aspect}. ` +
      "Do not ask for confirmation and do not make extra images.",
    "For every image:",
    `- Image prompt: ${parts}, each copied exactly as written. Do not add, remove or change words.`,
    "- Name the image with its scene ID only (for example S01). Never put the scene ID in the image prompt.",
    ...(opening ? [`Shared opening: ${norm(opening)}`] : []),
    ...(ending ? [`Shared ending: ${norm(ending)}`] : []),
    "Scenes:",
    ...lines,
  ].join("\n");
}

/** Reasons that mean "this account must rest": the agent made nothing and the same account would be refused again. */
export const AGENT_COOL_DOWN_REASONS = new Set([
  "PUBLIC_ERROR_UNUSUAL_ACTIVITY_TOO_MUCH_TRAFFIC",
  "PUBLIC_ERROR_USER_QUOTA_REACHED",
  "AGENT_CAPACITY_EXCEEDED",
]);

/** The cool-down reason in an agent reply (error frame or anywhere in the stream), or null. */
export function coolDownReason(parsed, rawText = "") {
  if (parsed?.error?.reason && AGENT_COOL_DOWN_REASONS.has(parsed.error.reason)) return parsed.error.reason;
  for (const r of AGENT_COOL_DOWN_REASONS) if (String(rawText).includes(r)) return r;
  return null;
}

/** Runs `fn` in the page with the WIZ session values it needs; transport errors come back as { error }. */
async function inPage(page, fn, arg) {
  return page.evaluate(fn, arg);
}

/** Create the agent chat for this project. Returns the chat id Google assigned. Nothing is generated by this call. */
export async function createAgentChat(page, projectId) {
  const requestId = crypto.randomUUID().toUpperCase();
  const out = await inPage(
    page,
    async ({ rpc, projectId, requestId, path, reqId, hl, timeoutMs, headers }) => {
      const wiz = window.WIZ_global_data || {};
      const at = wiz.SNlM0e, bl = wiz.cfb2h, fsid = wiz.FdrFJe;
      if (!at || !bl || !fsid) return { error: "Missing WIZ session state (at/bl/f.sid)", recoverable: true };
      const url = "https://flow.google.com" + path + "?rpcids=" + rpc + "&source-path=" + encodeURIComponent("/project/" + projectId) +
        "&bl=" + encodeURIComponent(bl) + "&f.sid=" + encodeURIComponent(fsid) + "&hl=" + encodeURIComponent(hl) + "&_reqid=" + reqId + "&rt=c";
      const body = "f.req=" + encodeURIComponent(JSON.stringify([[[rpc, JSON.stringify([projectId, null, requestId]), null, "generic"]]])) +
        "&at=" + encodeURIComponent(at);
      const ac = new AbortController();
      const tm = setTimeout(() => ac.abort(), timeoutMs);
      try {
        const resp = await fetch(url, { method: "POST", headers, body, credentials: "include", signal: ac.signal });
        clearTimeout(tm);
        const text = await resp.text();
        return resp.ok ? { text } : { error: "HTTP " + resp.status, status: resp.status };
      } catch (e) {
        clearTimeout(tm);
        return { error: e.name === "AbortError" ? "Request timed out" : String(e.message || e) };
      }
    },
    {
      rpc: AGENT_CHAT_RPC, projectId, requestId, path: batchexecute.path, reqId: nextReqId(page), hl: currentHl(page),
      timeoutMs: timing.apiRequestTimeoutMs, headers: BATCHEXECUTE_HEADERS,
    },
  );
  if (!out || out.error) throw tagSubmission(new Error(`Could not start a Flow agent chat: ${out?.error || "no response"}`), Submission.NOT_SUBMITTED);
  const parsed = parseBatchExecuteResponse(out.text, AGENT_CHAT_RPC);
  const chatId = Array.isArray(parsed) && Array.isArray(parsed[0]) && typeof parsed[0][0] === "string" ? parsed[0][0] : null;
  if (!chatId) throw tagSubmission(new Error("Could not start a Flow agent chat: no chat id in the answer"), Submission.NOT_SUBMITTED);
  return chatId;
}

/**
 * Send one message to the agent and return the whole reply stream as text. The send boundary: once the request is on the
 * wire, a failure without an answer is UNKNOWN (the agent may be generating), never NOT_SUBMITTED.
 */
export async function sendAgentMessage(page, { projectId, chatId, turn, message, timeoutMs = 240_000 }) {
  const captcha = await mintCaptchaWithFallback(page, AGENT_RECAPTCHA_ACTION);
  if (!captcha?.token) throw tagSubmission(new Error("reCAPTCHA token missing for the agent request"), Submission.NOT_SUBMITTED);
  const out = await inPage(
    page,
    async ({ path, projectId, chatId, turn, message, captcha, reqId, hl, timeoutMs, headers }) => {
      const wiz = window.WIZ_global_data || {};
      const at = wiz.SNlM0e, bl = wiz.cfb2h, fsid = wiz.FdrFJe;
      if (!at || !bl || !fsid) return { error: "Missing WIZ session state (at/bl/f.sid)", notSent: true };
      const url = "https://flow.google.com" + path + "?bl=" + encodeURIComponent(bl) + "&f.sid=" + encodeURIComponent(fsid) +
        "&hl=" + encodeURIComponent(hl) + "&_reqid=" + reqId + "&rt=c";
      const inner = [chatId, [[[[message]]]], ["projects/" + projectId, null, [captcha, 1], null, null, turn]];
      const body = "f.req=" + encodeURIComponent(JSON.stringify([null, JSON.stringify(inner)])) + "&at=" + encodeURIComponent(at);
      const ac = new AbortController();
      const tm = setTimeout(() => ac.abort(), timeoutMs);
      const sentAt = Date.now();
      try {
        const resp = await fetch(url, { method: "POST", headers, body, credentials: "include", signal: ac.signal });
        const text = await resp.text();
        clearTimeout(tm);
        return resp.ok ? { text, sentAt, doneAt: Date.now() } : { error: "HTTP " + resp.status, status: resp.status, text: text.slice(0, 500), sentAt };
      } catch (e) {
        clearTimeout(tm);
        return { error: e.name === "AbortError" ? "The agent did not finish in time" : String(e.message || e), sentAt };
      }
    },
    {
      path: AGENT_STREAM_PATH, projectId, chatId, turn, message, captcha: captcha.token, reqId: nextReqId(page), hl: currentHl(page),
      timeoutMs, headers: BATCHEXECUTE_HEADERS,
    },
  );
  if (!out) throw tagSubmission(new Error("The agent request returned nothing"), Submission.UNKNOWN);
  if (out.notSent) throw tagSubmission(new Error(out.error), Submission.NOT_SUBMITTED);
  if (out.error) {
    const sub = out.status >= 400 && out.status < 500 && !AMBIGUOUS_4XX.has(out.status) ? Submission.REJECTED : Submission.UNKNOWN;
    throw tagSubmission(new Error(`Flow agent request failed: ${out.error}`), sub, { httpStatus: out.status || null });
  }
  return { text: out.text, durationMs: out.doneAt - out.sentAt };
}

/** Every batchexecute frame payload in the stream, parsed (frames that are not JSON are skipped). */
function streamFrames(text) {
  const frames = [];
  for (const line of String(text || "").split("\n")) {
    if (!line.startsWith("[[")) continue;
    let outer;
    try {
      outer = JSON.parse(line);
    } catch {
      continue;
    }
    for (const f of outer) {
      if (!Array.isArray(f) || f[0] !== "wrb.fr") continue;
      if (typeof f[2] === "string") {
        try {
          frames.push({ payload: JSON.parse(f[2]) });
        } catch {}
      } else if (Array.isArray(f[5])) {
        frames.push({ error: f[5] });   // [code, null, [[type, [reason]]]]
      }
    }
  }
  return frames;
}

function walk(x, fn) {
  if (!Array.isArray(x)) return;
  fn(x);
  for (const v of x) walk(v, fn);
}

/** The key/value arguments of a tool call or result: [["prompt", [null, null, "..."]], ...]. */
function kvOf(args) {
  const kv = {};
  walk(args, (a) => {
    if (typeof a[0] === "string" && Array.isArray(a[1]) && a[1].length === 3 && (typeof a[1][2] === "string" || typeof a[1][2] === "number")) {
      kv[a[0]] = a[1][2];
    }
  });
  return kv;
}

/**
 * Read the agent's reply: the planned generate_image calls (in the order the agent made them), each call's result, the
 * agent's text, and any error frame. Never throws.
 */
export function parseAgentStream(text) {
  const calls = [];
  const results = {};
  const seen = new Set();
  const texts = [];
  let error = null;
  for (const frame of streamFrames(text)) {
    if (frame.error) {
      const code = Number(frame.error[0]);
      const reason = JSON.stringify(frame.error).match(/PUBLIC_ERROR_[A-Z_]+/);
      error = { grpcCode: Number.isFinite(code) ? code : null, reason: reason ? reason[0] : null };
      continue;
    }
    walk(frame.payload, (a) => {
      if (a[0] === "generate_image" && a[1] === "generate_image" && Array.isArray(a[2])) {
        const kv = kvOf(a[2]);
        const pid = kv.placeholder_frontend_id;
        if (!pid) return;
        if (kv.media_id || kv.status) {
          results[pid] = {
            status: String(kv.status || ""), mediaId: kv.media_id || null, workflowId: kv.workflow_id || null,
            batchId: kv.batch_id || null, title: kv.display_name || "",
          };
        } else if (!seen.has(pid)) {
          seen.add(pid);
          calls.push({
            placeholderId: pid, prompt: String(kv.prompt || ""), aspect: String(kv.aspect_ratio || ""),
            modelKey: String(kv.model_usage_key || ""), modelLabel: String(kv.model_display_name || ""), fields: kv,
          });
        }
      } else if (a[0] === "text" && Array.isArray(a[1]) && typeof a[1][2] === "string") {
        texts.push(a[1][2]);
      }
    });
  }
  return { calls, results, text: texts.join(""), error, refused: !!(error && REFUSAL_GRPC_CODES.has(error.grpcCode)) };
}

/** A text as its words only: lower case, accents/quotes/dashes/punctuation dropped, single spaces ("Don’t—stop!" -> "don t stop"). */
export function wordsOf(text) {
  return String(text || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ").trim();
}

/** The scene IDs (of this batch) found in a string: "S07" -> 6. */
function sceneIdsIn(text, count) {
  const out = new Set();
  for (const m of String(text || "").matchAll(/\bS(\d{2,3})\b/g)) {
    const i = Number(m[1]) - 1;
    if (i >= 0 && i < count) out.add(i);
  }
  return out;
}

/**
 * Tie the agent's images to our scenes. Never fuzzy:
 *   1. by scene ID: the image's name (or, failing that, any field of its call) carries exactly one of this request's scene
 *      IDs, and no other image claims the same ID;
 *   2. otherwise by exact text: the call's prompt contains exactly one remaining scene's text word for word (the agent was
 *      observed to copy scene text verbatim) and no other remaining call contains it.
 * Anything else stays unmatched (never guessed). Returns { mapping: sceneIndex -> { call, method }, unmatchedScenes, extraCalls }.
 */
export function mapCallsToScenes(sceneTexts, calls, results = {}) {
  const n = sceneTexts.length;
  const mapping = new Map();
  const usedCalls = new Set();
  const claims = new Map();   // scene index -> placeholder ids claiming it
  const claimOf = new Map();  // placeholder id -> scene index
  for (const c of calls) {
    let ids = sceneIdsIn(results[c.placeholderId]?.title, n);
    if (!ids.size) ids = new Set([...Object.values(c.fields || {})].flatMap((v) => [...sceneIdsIn(v, n)]));
    if (ids.size !== 1) continue;
    const i = [...ids][0];
    claimOf.set(c.placeholderId, i);
    claims.set(i, [...(claims.get(i) || []), c.placeholderId]);
  }
  for (const c of calls) {
    const i = claimOf.get(c.placeholderId);
    if (i == null || claims.get(i).length !== 1) continue;
    mapping.set(i, { call: c, method: "id" });
    usedCalls.add(c.placeholderId);
  }
  // Exact words in the same order; only letter case, punctuation, quote and dash styles may differ (the agent was seen to
  // tidy those). Never a partial or reordered match.
  const lower = (t) => ` ${wordsOf(t)} `;
  // Calls with no usable ID — including two images claiming the same ID — can still be settled by exact text.
  const free = calls.filter((c) => !usedCalls.has(c.placeholderId));
  const openScenes = sceneTexts.map((_, i) => i).filter((i) => !mapping.has(i) && lower(sceneTexts[i]));
  for (const c of free) {
    const hits = openScenes.filter((i) => !mapping.has(i) && lower(c.prompt).includes(lower(sceneTexts[i])));
    if (hits.length !== 1) continue;
    const i = hits[0];
    if (free.filter((o) => lower(o.prompt).includes(lower(sceneTexts[i]))).length !== 1) continue;
    mapping.set(i, { call: c, method: "text" });
    usedCalls.add(c.placeholderId);
  }
  return {
    mapping,
    unmatchedScenes: sceneTexts.map((_, i) => i).filter((i) => !mapping.has(i)),
    extraCalls: calls.filter((c) => !usedCalls.has(c.placeholderId)),
  };
}

/** The signed image URL for a media id (as29s), or null. Read-only: never generates anything. */
export async function fetchImageUrl(page, mediaId) {
  const out = await inPage(
    page,
    async ({ path, mediaId, reqId, hl, timeoutMs, headers }) => {
      const wiz = window.WIZ_global_data || {};
      const at = wiz.SNlM0e, bl = wiz.cfb2h, fsid = wiz.FdrFJe;
      if (!at || !bl || !fsid) return { error: "Missing WIZ session state" };
      const url = "https://flow.google.com" + path + "?rpcids=as29s&bl=" + encodeURIComponent(bl) + "&f.sid=" + encodeURIComponent(fsid) +
        "&hl=" + encodeURIComponent(hl) + "&_reqid=" + reqId + "&rt=c";
      const body = "f.req=" + encodeURIComponent(JSON.stringify([[["as29s", JSON.stringify([mediaId]), null, "generic"]]])) +
        "&at=" + encodeURIComponent(at);
      const ac = new AbortController();
      const tm = setTimeout(() => ac.abort(), timeoutMs);
      try {
        const resp = await fetch(url, { method: "POST", headers, body, credentials: "include", signal: ac.signal });
        clearTimeout(tm);
        return resp.ok ? { text: await resp.text() } : { error: "HTTP " + resp.status };
      } catch (e) {
        clearTimeout(tm);
        return { error: String(e.message || e) };
      }
    },
    { path: batchexecute.path, mediaId, reqId: nextReqId(page), hl: currentHl(page), timeoutMs: timing.apiRequestTimeoutMs, headers: BATCHEXECUTE_HEADERS },
  );
  if (!out || out.error) return null;
  return imageUrlFromAs29s(out.text);
}

/** The signed flow-content.google image URL in an as29s answer. The payload is JSON inside JSON, so it is decoded
 * properly: a regex over the raw text cuts the URL at its first escaped "=" or "&", and a cut signed URL is a 403. */
export function imageUrlFromAs29s(text) {
  const find = (node) => {
    if (typeof node === "string") return node.startsWith("https://flow-content.google/image/") ? node : null;
    if (Array.isArray(node)) for (const child of node) { const hit = find(child); if (hit) return hit; }
    return null;
  };
  return find(parseBatchExecuteResponse(String(text || ""), "as29s"));
}
