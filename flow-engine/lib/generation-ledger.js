/**
 * Persistent record of every generation the engine submits, so a crash, a stop or an automatic rerun can never turn into a
 * second paid generation of the same thing.
 *
 * One entry per generation identity (project scope + media kind + scene key + prompt + the settings that change the result +
 * slot):
 *
 *   SUBMITTING            written just BEFORE the request is sent. Found later = the process died mid-submit: unknown.
 *   SUBMITTED_UNKNOWN     the request may have been accepted, outcome unknown.
 *   ACCEPTED              Google created the job; workflowId known (video). failedStage says what did not finish
 *                         ("poll" = POLL_FAILED, "final_fetch" = FINAL_FETCH_FAILED). Resume = poll + final fetch + download.
 *   MEDIA_ID_KNOWN        the media id is known; `dest` is where the file is being written. Resume = reuse `dest` if it is a
 *                         valid file (the process died after saving it), else download.
 *   DOWNLOAD_FAILED       media id known, the download did not finish. Resume as MEDIA_ID_KNOWN.
 *   FAILED_ON_FLOW        Google reported the job failed after creating it.
 *   COMPLETED_LOCAL       the file is on disk.
 *   FAILED_BEFORE_SUBMISSION / REJECTED   nothing was created (proven). The only states that allow an automatic new submission.
 *
 * Decisions (decide()). `confirmed` = the user explicitly asked for this scene again (Retry / Regenerate in the app); an
 * automatic run is never confirmed. There is NO time limit: Flow's state cannot be checked from here, so "it has been a while"
 * is not evidence that a job does not exist.
 *   no entry, FAILED_BEFORE_SUBMISSION, REJECTED              -> submit
 *   COMPLETED_LOCAL, not confirmed                           -> reuse the file if valid, else fetch the same media again
 *                                                                (owner account) or block; never generate it again
 *   COMPLETED_LOCAL, confirmed (Regenerate)                   -> submit (the user asked for a new one)
 *   ACCEPTED / MEDIA_ID_KNOWN / DOWNLOAD_FAILED, same account -> resume; only after a CONFIRMED run already failed to resume
 *                                                                does a further confirmed request submit a new one
 *   ACCEPTED / MEDIA_ID_KNOWN / DOWNLOAD_FAILED, other account, SUBMITTING, SUBMITTED_UNKNOWN, FAILED_ON_FLOW
 *                                                             -> block unless confirmed
 *
 * Writes are synchronous and atomic (temp file + rename); the engine is one Node process, so writes never interleave.
 */
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

export const LedgerState = Object.freeze({
  SUBMITTING: "SUBMITTING",
  SUBMITTED_UNKNOWN: "SUBMITTED_UNKNOWN",
  ACCEPTED: "ACCEPTED",
  MEDIA_ID_KNOWN: "MEDIA_ID_KNOWN",
  DOWNLOAD_FAILED: "DOWNLOAD_FAILED",
  COMPLETED_LOCAL: "COMPLETED_LOCAL",
  FAILED_BEFORE_SUBMISSION: "FAILED_BEFORE_SUBMISSION",
  REJECTED: "REJECTED",
  FAILED_ON_FLOW: "FAILED_ON_FLOW",
});

/** Proven to have created nothing: the only states after which a new submission needs no confirmation. */
const NOTHING_CREATED = new Set([LedgerState.FAILED_BEFORE_SUBMISSION, LedgerState.REJECTED]);
const RESUMABLE = new Set([LedgerState.ACCEPTED, LedgerState.MEDIA_ID_KNOWN, LedgerState.DOWNLOAD_FAILED]);

/** Entries in these states are dropped after KEEP_MS; every other state is kept until it is resolved (never expires). */
const PRUNABLE = new Set([LedgerState.COMPLETED_LOCAL, LedgerState.FAILED_BEFORE_SUBMISSION, LedgerState.REJECTED]);
export const KEEP_MS = 30 * 24 * 60 * 60 * 1000;

/** Settings that change what is generated (a different model is a different generation). */
const IDENTITY_SETTINGS = ["model", "aspectRatio", "videoModel", "videoDuration", "videoResolution", "videoAspectRatio", "seedMode", "seedValue"];

/**
 * The project a run belongs to. The app gives every run its own folder (<project>/flow/runs/<run id>), so the project is the
 * folder two levels up; any other output folder is its own scope.
 */
export function scopeOf(outputDir) {
  if (!outputDir) return "";
  const resolved = path.resolve(String(outputDir));
  const runs = path.dirname(resolved);
  if (path.basename(runs) === "runs" && path.basename(path.dirname(runs)) === "flow") return path.dirname(path.dirname(runs));
  if (path.basename(runs) === ".flow_runs") return path.dirname(runs);
  return resolved;
}

export function generationKey({ mediaKind, prompt, settings = {}, slot = 0, scope = "" }) {
  const picked = IDENTITY_SETTINGS.map((k) => [k, settings[k] ?? null]);
  const raw = JSON.stringify([scope, mediaKind, String(prompt).trim(), picked, slot]);
  return crypto.createHash("sha256").update(raw).digest("hex").slice(0, 32);
}

export class GenerationLedger {
  constructor(file, { now = () => Date.now() } = {}) {
    this.file = file;
    this.now = now;
    this._data = null;
  }

  _load() {
    if (this._data) return this._data;
    let data = { version: 1, entries: {} };
    try {
      if (this.file && fs.existsSync(this.file)) {
        const parsed = JSON.parse(fs.readFileSync(this.file, "utf8"));
        if (parsed && typeof parsed.entries === "object") data = parsed;
      }
    } catch {
      // A corrupt ledger must not stop generation, but it must not be silently overwritten either: keep it aside.
      try {
        fs.renameSync(this.file, `${this.file}.corrupt-${this.now()}`);
      } catch {}
    }
    const cutoff = this.now() - KEEP_MS;
    for (const [k, e] of Object.entries(data.entries)) {
      if (!e || (PRUNABLE.has(e.state) && (e.updatedAt || 0) < cutoff)) delete data.entries[k];
    }
    this._data = data;
    return data;
  }

  _save() {
    if (!this.file) return;
    fs.mkdirSync(path.dirname(this.file), { recursive: true });
    const tmp = `${this.file}.${process.pid}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(this._data, null, 1));
    fs.renameSync(tmp, this.file);
  }

  get(key) {
    const e = this._load().entries[key];
    return e ? { ...e } : null;
  }

  /** Merge `patch` into the entry and write it to disk before returning. */
  put(key, patch) {
    const data = this._load();
    const prev = data.entries[key] || { key, createdAt: this.now() };
    data.entries[key] = { ...prev, ...patch, key, updatedAt: this.now() };
    this._save();
    return { ...data.entries[key] };
  }

  /**
   * What to do with a generation identity before submitting it.
   * @param {string} key
   * @param {{ accountId: string, runId: string, confirmed?: boolean, validFile?: (path: string) => boolean }} ctx
   * @returns {{ action: "submit" } | { action: "reuse", entry: object } | { action: "resume", entry: object } |
   *           { action: "block", entry: object, reason: string }}
   */
  decide(key, { accountId, runId, confirmed = false, validFile = () => false }) {
    const e = this.get(key);
    if (!e || NOTHING_CREATED.has(e.state)) return { action: "submit" };
    if (e.state === LedgerState.COMPLETED_LOCAL) {
      if (confirmed) return { action: "submit" };   // Regenerate: the user asked for a new one
      if (e.savedPath && validFile(e.savedPath)) return { action: "reuse", entry: e };
      // Generated before but the file is gone: fetch the same media again (its owner account only), never generate it again.
      if (e.mediaId && e.accountId === accountId) return { action: "resume", entry: { ...e, state: LedgerState.MEDIA_ID_KNOWN } };
      return {
        action: "block",
        entry: e,
        reason: `this scene was already generated on Flow account ${e.accountLabel || e.accountId} but its file is gone; sign that account in to fetch it again, or click Retry on this scene to generate a new one`,
      };
    }
    if (RESUMABLE.has(e.state)) {
      if (e.accountId === accountId) {
        if (confirmed && e.confirmedResumeFailedRunId && e.confirmedResumeFailedRunId !== runId) return { action: "submit" };
        return { action: "resume", entry: e };
      }
      if (confirmed) return { action: "submit" };
      return {
        action: "block",
        entry: e,
        reason: `this generation already exists on Flow account ${e.accountLabel || e.accountId}; sign that account in to download it, or click Retry on this scene to generate a new one`,
      };
    }
    if (confirmed) return { action: "submit" };
    if (e.state === LedgerState.FAILED_ON_FLOW) {
      return { action: "block", entry: e, reason: "Flow reported this generation as failed. Click Retry on this scene to generate it again" };
    }
    return {
      action: "block",
      entry: e,
      reason: "an earlier request for this scene may already have been accepted by Flow (its result was never confirmed). Check the Flow project; click Retry on this scene to generate it again",
    };
  }
}

let shared = null;

/** The engine's ledger (DATA_DIR/flow-generation-ledger.json). */
export async function defaultLedger() {
  if (!shared) {
    const { DATA_DIR } = await import("./paths.js");
    shared = new GenerationLedger(process.env.FLOW_LEDGER_FILE || path.join(DATA_DIR, "flow-generation-ledger.json"));
  }
  return shared;
}
