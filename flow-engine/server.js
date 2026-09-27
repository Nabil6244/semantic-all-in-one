/**
 * Semantic Automator Desktop — HTTP + WebSocket HUD server.
 *
 * CLI:        node server.js  → http://127.0.0.1:8787
 * Electron:   import { startServer } from "./server.js"
 */
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { WebSocketServer } from "ws";
import { PUBLIC_DIR, ensureDirs, DOWNLOADS_ROOT, DATA_DIR } from "./lib/paths.js";
import {
  onHudMessage,
  getState,
  pushState,
  addAccount,
  loginAccount,
  refreshAccount,
  refreshAll,
  renameAccount,
  deleteAccount,
  generate,
  stopGenerate,
  resetGenerateState,
  closeBrowsers,
  shutdown,
  inspectAccount,
} from "./lib/orchestrator.js";
import { defaults } from "./config.js";
import crypto from "node:crypto";

/**
 * Fingerprint of the engine code THIS process loaded (server.js + lib/*.js),
 * computed once at startup. The app compares it with the files on disk
 * before reusing an already-running engine: Node only reads code at start,
 * so an engine left running across an app update kept executing its OLD
 * code (a days-old engine was still using the retired direct-RPC video path
 * after batch-runner.js had moved to the UI path). Must match
 * providers/flow/engine_manager.py's engine_code_version().
 */
const ENGINE_CODE_VERSION = (() => {
  try {
    const root = path.dirname(fileURLToPath(import.meta.url));
    const files = ["server.js"].concat(
      fs.readdirSync(path.join(root, "lib")).filter((f) => f.endsWith(".js")).sort().map((f) => `lib/${f}`),
    );
    const h = crypto.createHash("sha256");
    for (const rel of files) {
      h.update(rel);
      h.update("\0");
      h.update(fs.readFileSync(path.join(root, rel)));
      h.update("\0");
    }
    return h.digest("hex").slice(0, 16);
  } catch {
    return "unknown";
  }
})();

const DEFAULT_PORT = Number(process.env.SA_PORT || 8787);

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".png": "image/png",
  ".svg": "image/svg+xml",
};

/**
 * @param {number} [port]
 * @returns {Promise<{ port: number, close: () => Promise<void> }>}
 */
export async function startServer(port = DEFAULT_PORT) {
  ensureDirs();

  function serveStatic(req, res) {
    let urlPath = decodeURIComponent((req.url || "/").split("?")[0]);
    if (urlPath === "/") urlPath = "/index.html";
    const file = path.join(
      PUBLIC_DIR,
      path.normalize(urlPath).replace(/^(\.\.[/\\])+/, ""),
    );
    if (!file.startsWith(PUBLIC_DIR)) {
      res.writeHead(403);
      return res.end("Forbidden");
    }
    if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404);
      return res.end("Not found");
    }
    const ext = path.extname(file);
    res.writeHead(200, { "Content-Type": MIME[ext] || "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  }

  const server = http.createServer((req, res) => {
    if (req.method === "GET") return serveStatic(req, res);
    res.writeHead(405);
    res.end("Method not allowed");
  });

  const wss = new WebSocketServer({ server, path: "/ws" });

  function send(ws, obj) {
    if (ws.readyState === 1) ws.send(JSON.stringify(obj));
  }

  wss.on("connection", (ws) => {
    send(ws, getState());
    send(ws, {
      type: "INFO",
      downloadsRoot: DOWNLOADS_ROOT,
      dataDir: DATA_DIR,
      defaults: defaults.flowSettings,
      codeVersion: ENGINE_CODE_VERSION,
    });

    ws.on("message", async (raw) => {
      let msg;
      try {
        msg = JSON.parse(String(raw));
      } catch {
        return;
      }
      const t = msg.type;
      try {
        if (t === "HELLO") {
          send(ws, getState());
        } else if (t === "SHUTDOWN") {
          // The app retiring an engine that runs outdated code (see
          // ENGINE_CODE_VERSION); same exit path as SIGTERM.
          setTimeout(() => process.kill(process.pid, "SIGTERM"), 50);
        } else if (t === "ADD_ACCOUNT") {
          await addAccount(msg.label);
        } else if (t === "LOGIN") {
          loginAccount(msg.accountId).catch((e) =>
            pushState({ generateError: e.message }),
          );
        } else if (t === "REFRESH") {
          if (msg.accountId) await refreshAccount(msg.accountId);
          else await refreshAll();
        } else if (t === "RENAME") {
          await renameAccount(msg.accountId, msg.label);
        } else if (t === "DELETE") {
          await deleteAccount(msg.accountId);
        } else if (t === "GENERATE") {
          const prompts = String(msg.prompts || "")
            .split(/\r?\n/)
            .map((s) => s.trim())
            .filter(Boolean);
          generate({
            prompts,
            settings: { ...defaults.flowSettings, ...(msg.settings || {}) },
            accountIds: msg.accountIds || null,
          }).catch((e) => pushState({ generateError: e.message }));
        } else if (t === "STOP") {
          stopGenerate({ force: !!msg.force });
        } else if (t === "RESET_GENERATE") {
          resetGenerateState();
        } else if (t === "CLOSE_BROWSERS") {
          await closeBrowsers();
        } else if (t === "INSPECT_PAGE") {
          // TEMPORARY read-only diagnostic — see accounts.js's
          // inspectAccountPage doc comment. Never touches Flow RPCs,
          // reCAPTCHA, or generation.
          const result = await inspectAccount(msg.accountId);
          send(ws, { type: "INSPECT_RESULT", accountId: msg.accountId, ...result });
        }
      } catch (e) {
        send(ws, { type: "ERROR", message: e.message });
        pushState({ generateError: e.message });
      }
    });
  });

  const unsub = onHudMessage((msg) => {
    for (const client of wss.clients) send(client, msg);
  });

  const listenPort = await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, "127.0.0.1", () => {
      const addr = server.address();
      resolve(typeof addr === "object" && addr ? addr.port : port);
    });
  });

  console.log(`Semantic Automator Desktop → http://127.0.0.1:${listenPort}`);
  console.log(`Downloads folder: ${DOWNLOADS_ROOT}`);
  console.log(`Account data:     ${DATA_DIR}`);

  return {
    port: listenPort,
    close: async () => {
      unsub();
      await shutdown();
      await new Promise((r) => server.close(() => r()));
      try {
        wss.close();
      } catch {}
    },
  };
}

/**
 * Detect `node server.js` so the HTTP/WS server starts.
 *
 * Packaged Mac apps often fail a naive path equality check:
 * - `/var/...` vs `/private/var/...` (macOS realpath)
 * - relative `server.js` vs absolute import.meta.url
 * Without a match, this file loads and Node exits 0 immediately — Settings then
 * shows "flow engine process exited immediately (code 0)" and Add Account fails.
 */
const isDirectRun = (() => {
  try {
    const invokedRaw = process.argv[1];
    if (!invokedRaw) return false;
    const self = path.resolve(fileURLToPath(import.meta.url));
    const invoked = path.resolve(invokedRaw);
    if (invoked === self) return true;
    try {
      if (fs.realpathSync(invoked) === fs.realpathSync(self)) return true;
    } catch {
      /* ignore */
    }
    // Last resort: Python always launches this file as `node …/server.js`.
    return path.basename(invoked) === "server.js";
  } catch {
    return false;
  }
})();

if (isDirectRun) {
  const handle = await startServer();
  const exit = async () => {
    await handle.close();
    process.exit(0);
  };
  process.on("SIGINT", exit);
  process.on("SIGTERM", exit);
} else {
  console.error(
    "[flow-engine] Not starting server — argv[1] did not look like server.js:",
    process.argv[1],
  );
}
