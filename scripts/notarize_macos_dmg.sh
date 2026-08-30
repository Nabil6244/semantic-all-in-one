#!/usr/bin/env bash
# Submit dist/Semantic-YT-Studio.dmg to Apple notarization and staple the
# ticket on success (Release Readiness Audit, Phase 1.3). Run AFTER
# `scripts/make_dmg.sh`, on an already-codesigned .app (see
# scripts/codesign_macos_app.sh).
#
# Requires:
#   APPLE_ID                    Apple ID email used for the Developer account
#   APPLE_APP_SPECIFIC_PASSWORD App-specific password for that Apple ID
#                                (NOT the account password) — generate at
#                                appleid.apple.com > Sign-In and Security >
#                                App-Specific Passwords.
#   APPLE_TEAM_ID                Developer Team ID (e.g. ABCDE12345)
#
# None of these are read from or written to source control — they live only
# in the CI secret store.
set -euo pipefail

cd "$(dirname "$0")/.."

DMG="dist/Semantic-YT-Studio.dmg"

for var in APPLE_ID APPLE_APP_SPECIFIC_PASSWORD APPLE_TEAM_ID; do
  if [[ -z "${!var:-}" ]]; then
    echo "ERROR: $var is not set." >&2
    exit 1
  fi
done
if [[ ! -f "$DMG" ]]; then
  echo "ERROR: $DMG not found. Build it first: scripts/make_dmg.sh" >&2
  exit 1
fi

echo "==> Submitting $DMG to Apple notarization (this can take several minutes)."
xcrun notarytool submit "$DMG" \
  --apple-id "$APPLE_ID" \
  --password "$APPLE_APP_SPECIFIC_PASSWORD" \
  --team-id "$APPLE_TEAM_ID" \
  --wait

echo "==> Stapling notarization ticket to $DMG."
xcrun stapler staple "$DMG"

echo "==> Verifying staple + Gatekeeper acceptance."
xcrun stapler validate "$DMG"
spctl --assess --type open --context context:primary-signature -v "$DMG"

echo "Notarized and stapled: $DMG"
