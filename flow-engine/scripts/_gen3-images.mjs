import WebSocket from "ws";
import path from "node:path";
import fs from "node:fs";

const outDir =
  process.env.FLOW_OUT ||
  path.join(process.env.HOME, "Downloads/Semantic YT Studio/_gen3_" + Date.now());
fs.mkdirSync(outDir, { recursive: true });

const prompts = [
  "man walking on street dubai city daytime, cinematic still photo",
  "man looking up at sky in surprise shock, dubai outdoor daylight",
  "wide shot of dubai marina skyline at golden hour, clear sky, cinematic",
].join("\n");

const accountIds = ["7e5d3e93-06e8-4527-b2a2-895307619bc3"]; // Account 5
const ws = new WebSocket("ws://127.0.0.1:8787/ws");
const results = [];
let done = false;

ws.on("message", (data) => {
  let msg;
  try {
    msg = JSON.parse(String(data));
  } catch {
    return;
  }
  if (["BATCH_PROGRESS", "PROMPT_RESULT", "GENERATE_DONE"].includes(msg.type) || msg.generateError) {
    console.log(
      JSON.stringify({
        type: msg.type,
        status: msg.status,
        index: msg.index,
        message: String(msg.message || msg.generateError || msg.error || "").slice(0, 220),
        path: msg.path,
      }),
    );
    fs.appendFileSync(path.join(outDir, "events.jsonl"), JSON.stringify(msg) + "\n");
    if (msg.type === "PROMPT_RESULT") results.push(msg);
    if (msg.type === "GENERATE_DONE") done = true;
    if (msg.generateError) done = true;
  }
});

await new Promise((r, j) => {
  ws.on("open", r);
  ws.on("error", j);
});
console.log("SENDING 3 images", outDir);
ws.send(
  JSON.stringify({
    type: "GENERATE",
    prompts,
    accountIds,
    settings: {
      mediaKind: "image",
      model: "GEM_PIX_2",
      aspectRatio: "IMAGE_ASPECT_RATIO_LANDSCAPE",
      imageCount: 1,
      autoDownload: true,
      outputDir: outDir,
      folder: "batch",
      generationMode: "rpc",
      delayMin: 2,
      delayMax: 4,
      refreshFrequency: 50,
    },
  }),
);

const deadline = Date.now() + 8 * 60 * 1000;
while (!done && Date.now() < deadline) await new Promise((r) => setTimeout(r, 1000));
ws.close();

const pngs = [];
(function walk(d) {
  for (const n of fs.readdirSync(d)) {
    const p = path.join(d, n);
    if (fs.statSync(p).isDirectory()) walk(p);
    else if (/\.png$/i.test(n)) pngs.push(p);
  }
})(outDir);

const summary = {
  done,
  pngCount: pngs.length,
  pngs,
  results: results.map((r) => ({ index: r.index, status: r.status, path: r.path, error: r.error })),
};
console.log("SUMMARY", JSON.stringify(summary, null, 2));
fs.writeFileSync(path.join(outDir, "summary.json"), JSON.stringify(summary, null, 2));
process.exit(pngs.length >= 3 ? 0 : 1);
