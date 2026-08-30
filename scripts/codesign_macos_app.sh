#!/usr/bin/env bash
# Deep-sign dist/Semantic YT Studio.app with the hardened runtime, for
# notarization (Release Readiness Audit, Phase 1.3). Run AFTER
# `pyinstaller VideoGenerator.spec` and BEFORE `scripts/make_dmg.sh`.
#
# Requires env var MACOS_CODESIGN_IDENTITY, e.g.:
#   "Developer ID Application: Your Name (TEAMID1234)"
# The identity must already be in the active keychain (see the "Import
# signing certificate" CI step) or locally in Keychain Access.
#
# No secret is read from or written to source control by this script — the
# identity string and certificate live only in the CI secret store / the
# signer's local keychain.
set -euo pipefail

cd "$(dirname "$0")/.."

APP="dist/Semantic YT Studio.app"
ENTITLEMENTS="scripts/entitlements.plist"

if [[ -z "${MACOS_CODESIGN_IDENTITY:-}" ]]; then
  echo "ERROR: MACOS_CODESIGN_IDENTITY is not set." >&2
  exit 1
fi
if [[ ! -d "$APP" ]]; then
  echo "ERROR: $APP not found. Build first: pyinstaller VideoGenerator.spec" >&2
  exit 1
fi
if [[ ! -f "$ENTITLEMENTS" ]]; then
  echo "ERROR: $ENTITLEMENTS not found." >&2
  exit 1
fi

echo "==> Signing nested binaries first (inside-out), then the app bundle."

# Sign every nested Mach-O binary/dylib before the outer bundle, per Apple's
# guidance for complex bundles (PyInstaller's _internal/ dir is a flat pile
# of .dylib/.so files plus the app's own executables, not nested .frameworks,
# so this single pass covers it).
find "$APP" \( -name "*.dylib" -o -name "*.so" \) -type f -print0 |
  while IFS= read -r -d '' lib; do
    codesign --force --options runtime --timestamp \
      --entitlements "$ENTITLEMENTS" \
      --sign "$MACOS_CODESIGN_IDENTITY" "$lib"
  done

# Bundled executables that aren't the main binary (ffmpeg, ffprobe, node).
find "$APP/Contents/Frameworks" "$APP/Contents/MacOS" -type f -perm -u+x -print0 2>/dev/null |
  while IFS= read -r -d '' bin; do
    # Skip the main app executable — signed last, as part of the whole bundle.
    [[ "$bin" == "$APP/Contents/MacOS/Semantic YT Studio" ]] && continue
    codesign --force --options runtime --timestamp \
      --entitlements "$ENTITLEMENTS" \
      --sign "$MACOS_CODESIGN_IDENTITY" "$bin"
  done

# Finally, the whole app bundle (main executable + Info.plist + resources).
codesign --force --deep --options runtime --timestamp \
  --entitlements "$ENTITLEMENTS" \
  --sign "$MACOS_CODESIGN_IDENTITY" "$APP"

echo "==> Verifying signature."
codesign --verify --deep --strict --verbose=2 "$APP"

echo "Signed: $APP"
