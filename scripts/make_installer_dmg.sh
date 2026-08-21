#!/usr/bin/env bash
# Turn dist/VideoGenerator-Installer.app into a small distributable .dmg
set -euo pipefail

cd "$(dirname "$0")/.."

APP="dist/VideoGenerator-Installer.app"
DMG="dist/VideoGenerator-Installer.dmg"
STAGE="dist/installer_dmg_stage"

if [[ ! -d "$APP" ]]; then
  echo "ERROR: $APP not found. Build first:"
  echo "  pyinstaller Installer.spec"
  exit 1
fi

rm -rf "$STAGE" "$DMG"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"

hdiutil create \
  -volname "Video Generator Setup" \
  -srcfolder "$STAGE" \
  -ov \
  -format UDZO \
  "$DMG"

rm -rf "$STAGE"
echo "Created: $DMG"
