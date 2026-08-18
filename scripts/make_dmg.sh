#!/usr/bin/env bash
# Turn dist/SemanticAllInOne.app into a distributable .dmg
set -euo pipefail

cd "$(dirname "$0")/.."

APP="dist/SemanticAllInOne.app"
DMG="dist/SemanticAllInOne.dmg"
STAGE="dist/dmg_stage"

if [[ ! -d "$APP" ]]; then
  echo "ERROR: $APP not found. Build first:"
  echo "  pyinstaller VideoGenerator.spec"
  exit 1
fi

rm -rf "$STAGE" "$DMG"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"

hdiutil create \
  -volname "Semantic All-In-One" \
  -srcfolder "$STAGE" \
  -ov \
  -format UDZO \
  "$DMG"

rm -rf "$STAGE"
echo "Created: $DMG"
