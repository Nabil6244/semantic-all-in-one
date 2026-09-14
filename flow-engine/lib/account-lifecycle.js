/**
 * Per-account Flow lifecycle: staggered refresh scheduling + serial lock.
 *
 * Concurrency stays multi-account (e.g. 10 workers). This module only serializes
 * refresh / recovery / generation *within* one account so a reload never races
 * an in-flight generate on the same page.
 */

export const LifecycleState = Object.freeze({
  READY: "READY",
  GENERATING: "GENERATING",
  WAITING_FOR_RESULT: "WAITING_FOR_RESULT",
  REFRESHING: "REFRESHING",
  WAITING_FOR_FLOW_READY: "WAITING_FOR_FLOW_READY",
  RECOVERING: "RECOVERING",
});

/** States that may start a new generation. */
const GENERATION_ALLOWED = new Set([LifecycleState.READY]);

/**
 * Stable non-negative integer from an account id / label (no crypto needed).
 * @param {string} accountKey
 */
export function stableAccountSlot(accountKey) {
  const s = String(accountKey || "");
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/**
 * Bounded stagger offset in completed-prompt units.
 * With base=20 and 10 accounts, offsets are 0,2,4,… so first refreshes land at
 * 20,22,24… instead of all hitting completed%20===0 together.
 *
 * @param {object} opts
 * @param {number} opts.refreshEvery  configured base (must stay positive)
 * @param {string} [opts.accountKey]
 * @param {number} [opts.workerIndex]  preferred when known (0-based)
 * @param {number} [opts.maxAccounts=10]  spreads offsets across this many slots
 */
export function computeRefreshOffset({
  refreshEvery,
  accountKey = "",
  workerIndex = null,
  maxAccounts = 10,
} = {}) {
  const base = Math.max(0, Math.floor(Number(refreshEvery) || 0));
  if (base <= 0) return 0;
  const slots = Math.max(1, Math.min(Math.floor(maxAccounts) || 10, base));
  const idx =
    workerIndex != null && Number.isFinite(Number(workerIndex))
      ? Math.max(0, Math.floor(Number(workerIndex)))
      : stableAccountSlot(accountKey);
  // Step of 2 when base allows (matches the 20/22/24… target); else 1.
  const step = base >= slots * 2 ? 2 : 1;
  return (idx % slots) * step;
}

/**
 * Build the first refresh threshold and helpers for advancing after a refresh.
 * Refresh fires when `completed >= nextThreshold` (not modulo), so a threshold
 * cannot fire twice.
 */
export function createRefreshPlan({
  refreshEvery,
  accountKey = "",
  workerIndex = null,
  maxAccounts = 10,
} = {}) {
  const base = Math.max(0, Math.floor(Number(refreshEvery) || 0));
  const offset = computeRefreshOffset({
    refreshEvery: base,
    accountKey,
    workerIndex,
    maxAccounts,
  });
  let nextThreshold = base > 0 ? base + offset : Infinity;
  return {
    refreshEvery: base,
    offset,
    get nextThreshold() {
      return nextThreshold;
    },
    shouldRefresh(completed, { hasMorePrompts = true } = {}) {
      if (base <= 0 || !hasMorePrompts) return false;
      return completed >= nextThreshold;
    },
    /** Call once after a successful refresh for this threshold. */
    advanceAfterRefresh(completed) {
      if (base <= 0) {
        nextThreshold = Infinity;
        return nextThreshold;
      }
      nextThreshold = Math.max(completed, nextThreshold) + base;
      return nextThreshold;
    },
  };
}

export function logFlowAccount(accountLabel, message, extra = {}) {
  const id = accountLabel || extra.accountId || "account";
  const bits = [`[FLOW] Account ${id} ${message}`];
  if (extra.completed != null) bits.push(`completed=${extra.completed}`);
  if (extra.nextThreshold != null) bits.push(`nextRefresh=${extra.nextThreshold}`);
  if (extra.state) bits.push(`state=${extra.state}`);
  if (extra.detail) bits.push(String(extra.detail));
  console.error(bits.join(" | "));
}

/**
 * Serial async lock + state machine for one Flow account page.
 */
export class AccountLifecycle {
  /**
   * @param {object} opts
   * @param {string} [opts.accountId]
   * @param {string} [opts.accountLabel]
   * @param {number} [opts.workerIndex]
   * @param {number} [opts.refreshEvery]
   * @param {number} [opts.maxAccounts]
   * @param {number} [opts.maxRecoveryReloadsPerPrompt]
   */
  constructor(opts = {}) {
    this.accountId = opts.accountId || "";
    this.accountLabel = opts.accountLabel || opts.accountId || "account";
    this.workerIndex = opts.workerIndex;
    this.state = LifecycleState.READY;
    this._tail = Promise.resolve();
    this._depth = 0;
    this.refreshPlan = createRefreshPlan({
      refreshEvery: opts.refreshEvery,
      accountKey: this.accountId || this.accountLabel,
      workerIndex: this.workerIndex,
      maxAccounts: opts.maxAccounts,
    });
    this.recoveryReloads = 0;
    this.maxRecoveryReloadsPerPrompt =
      Number(opts.maxRecoveryReloadsPerPrompt) > 0
        ? Math.floor(Number(opts.maxRecoveryReloadsPerPrompt))
        : 1;
  }

  get label() {
    return this.accountLabel;
  }

  canGenerate() {
    return GENERATION_ALLOWED.has(this.state) && this._depth === 0;
  }

  /**
   * Run exclusive work for this account. Nested acquire is rejected so
   * refresh cannot start under an active generation (and vice versa).
   * @template T
   * @param {string} nextState
   * @param {() => Promise<T>} fn
   * @returns {Promise<T>}
   */
  async runExclusive(nextState, fn) {
    const run = this._tail.then(async () => {
      if (this._depth > 0) {
        throw new Error(
          `Account ${this.label} lifecycle overlap: tried ${nextState} while ${this.state}`,
        );
      }
      this._depth = 1;
      this.state = nextState;
      try {
        return await fn();
      } finally {
        this.state = LifecycleState.READY;
        this._depth = 0;
      }
    });
    this._tail = run.then(
      () => undefined,
      () => undefined,
    );
    return run;
  }

  async generate(fn) {
    try {
      const result = await this.runExclusive(LifecycleState.GENERATING, async () => {
        logFlowAccount(this.label, "generation start", { state: this.state });
        this.state = LifecycleState.WAITING_FOR_RESULT;
        return fn();
      });
      logFlowAccount(this.label, "generation success");
      return result;
    } catch (err) {
      logFlowAccount(this.label, "generation failure", {
        detail: String(err?.message || err).slice(0, 120),
      });
      throw err;
    }
  }

  async refresh(fn) {
    return this.runExclusive(LifecycleState.REFRESHING, async () => {
      logFlowAccount(this.label, "refreshing", {
        nextThreshold: this.refreshPlan.nextThreshold,
        state: LifecycleState.REFRESHING,
      });
      this.state = LifecycleState.WAITING_FOR_FLOW_READY;
      logFlowAccount(this.label, "waiting for Flow readiness");
      const out = await fn();
      logFlowAccount(this.label, "Flow ready");
      return out;
    });
  }

  async recover(fn) {
    logFlowAccount(this.label, "recovery start");
    try {
      const out = await this.runExclusive(LifecycleState.RECOVERING, async () => {
        this.state = LifecycleState.WAITING_FOR_FLOW_READY;
        return fn();
      });
      logFlowAccount(this.label, "recovery end");
      return out;
    } catch (err) {
      logFlowAccount(this.label, "recovery end", {
        detail: String(err?.message || err).slice(0, 120),
      });
      throw err;
    }
  }

  resetRecoveryBudget() {
    this.recoveryReloads = 0;
  }

  noteRecoveryReload() {
    this.recoveryReloads += 1;
    return this.recoveryReloads;
  }

  canRecoveryReload() {
    return this.recoveryReloads < this.maxRecoveryReloadsPerPrompt;
  }
}

/** True when the thrown error is a missing mediaId from Flow generation. */
export function isMissingMediaIdError(err) {
  const msg = String(err?.message || err || "");
  return /No mediaId/i.test(msg);
}
