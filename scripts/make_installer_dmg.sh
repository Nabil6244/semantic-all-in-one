#!/usr/bin/env bash
# Optional stub installer DMG (not the primary team deliverable; see make_dmg.sh).
# Turn dist/Semantic YT Studio Setup.app into a small distributable .dmg
set -euo pipefail

cd "$(dirname "$0")/.."

APP="dist/Semantic YT Studio Setup.app"
DMG="dist/Semantic-YT-Studio-Setup.dmg"
STAGE="dist/installer_dmg_stage"

if [[ ! -d "$APP" ]]; then
  echo "ERROR: $APP not found. Build first:"
  echo "  pyinstaller Installer.spec"
  exit 1
fi

rm -rf "$STAGE" "$DMG"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"

hdiutil create \
  -volname "Semantic YT Studio Setup" \
  -srcfolder "$STAGE" \
  -ov \
  -format UDZO \
  "$DMG"

rm -rf "$STAGE"
echo "Created: $DMG"
