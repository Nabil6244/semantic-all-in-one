# Bundled binaries (not committed)

Place platform binaries here before a local PyInstaller build:

| Platform | Files to put here |
|----------|------------------|
| macOS    | `bin/ffmpeg`, `bin/node` (no extension, both executable) |
| Windows  | `bin/ffmpeg.exe`, `bin/ffprobe.exe`, `bin/node.exe` |

Both are optional individually: without `ffmpeg` the app can't render at all (build fails, see `VideoGenerator.spec`); without `node` the app still works for Stock/Manual scenes, just not AI/Flow (build only warns).

## Where to get them

- **ffmpeg — macOS:** download a static build, or copy from Homebrew:
  `cp "$(brew --prefix ffmpeg)/bin/ffmpeg" bin/ffmpeg && chmod +x bin/ffmpeg`
- **ffmpeg — Windows:** from a release zip (BtbN win64-gpl or Gyan "essentials"), copy `bin/ffmpeg.exe` **and** `bin/ffprobe.exe` here (same zip). CI uses BtbN first (GitHub Releases); Gyan is only a fallback.
- **node — any platform:** download the **official** Node.js binary release from nodejs.org (NOT Homebrew's — Homebrew's `node` is dynamically linked against Homebrew's own OpenSSL/ICU and will not run on a machine without Homebrew; the official nodejs.org tarball only links against OS-provided system libraries and runs standalone). Extract the archive and copy just `bin/node` (macOS/Linux) or `node.exe` (Windows) — no other files needed, since `flow-engine/node_modules/` (committed separately, see `flow-engine/README.md`) is what actually runs.

```bash
# macOS example (arm64):
curl -sL -o node.tar.gz https://nodejs.org/dist/v24.19.0/node-v24.19.0-darwin-arm64.tar.gz
tar -xzf node.tar.gz
cp node-v24.19.0-darwin-arm64/bin/node bin/node && chmod +x bin/node
```

## Packaged builds

The GitHub Actions workflow downloads both ffmpeg and Node automatically before building — you do **not** need to commit these binaries.

At runtime:
- `app.py` looks for `bin/ffmpeg` next to the app / inside the PyInstaller bundle and prepends that folder to `PATH` so `video_generator.py` can call `ffmpeg` unchanged.
- `providers/flow/engine_manager.py` looks for `bin/node` the same way and uses it directly to launch `flow-engine/server.js` — no PATH/env changes, no npm install at runtime, since `flow-engine/node_modules/` ships pre-installed.
