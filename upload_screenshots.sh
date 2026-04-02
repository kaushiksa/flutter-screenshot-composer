#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# upload_screenshots.sh — Upload composed screenshots to App Store / Play Store
#
# Part of flutter-screenshot-composer (centralized tool).
# Reads active project from projects.json, finds composed screenshots in
# project_data/, organizes them for each store, and calls fastlane.
#
# Usage:
#   ./upload_screenshots.sh              # Upload to both stores
#   ./upload_screenshots.sh --ios        # Upload to App Store only
#   ./upload_screenshots.sh --android    # Upload to Play Store only
#   ./upload_screenshots.sh --dry-run    # Organize only, skip upload
#   ./upload_screenshots.sh --project X  # Override active project
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail  # no -e: we want to continue on partial failures

TOOL_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECTS_FILE="$TOOL_DIR/projects.json"

# ── Parse arguments ─────────────────────────────────────────────────────────
DRY_RUN=false
UPLOAD_IOS=true
UPLOAD_ANDROID=true
PROJECT_OVERRIDE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)   DRY_RUN=true; shift ;;
    --ios)       UPLOAD_ANDROID=false; shift ;;
    --android)   UPLOAD_IOS=false; shift ;;
    --project)   PROJECT_OVERRIDE="$2"; shift 2 ;;
    --help|-h)
      echo "Usage: $0 [--ios|--android|--dry-run|--project NAME]"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ── Logging ─────────────────────────────────────────────────────────────────
log()  { echo "$(date '+%H:%M:%S') | $*"; }
ok()   { echo "$(date '+%H:%M:%S') | ✅ $*"; }
warn() { echo "$(date '+%H:%M:%S') | ⚠️  $*"; }
fail() { echo "$(date '+%H:%M:%S') | ❌ $*"; }

# ── Resolve active project ─────────────────────────────────────────────────
if [[ ! -f "$PROJECTS_FILE" ]]; then
  fail "projects.json not found at $PROJECTS_FILE"
  exit 1
fi

if [[ -n "$PROJECT_OVERRIDE" ]]; then
  PROJECT_NAME="$PROJECT_OVERRIDE"
else
  PROJECT_NAME=$(python3 -c "import json; d=json.load(open('$PROJECTS_FILE')); print(d.get('active',''))")
fi

if [[ -z "$PROJECT_NAME" ]]; then
  fail "No active project. Use --project NAME or set active in projects.json"
  exit 1
fi

PROJECT_PATH=$(python3 -c "
import json
d = json.load(open('$PROJECTS_FILE'))
for p in d.get('projects', []):
    if p['name'] == '$PROJECT_NAME':
        print(p['path'])
        break
")

if [[ -z "$PROJECT_PATH" ]] || [[ ! -d "$PROJECT_PATH" ]]; then
  fail "Project '$PROJECT_NAME' not found or path missing: $PROJECT_PATH"
  exit 1
fi

DATA_DIR="$TOOL_DIR/project_data/$PROJECT_NAME/screenshots"
COMPOSED_DIR="$DATA_DIR/composed"
APPSTORE_DIR="$DATA_DIR/appstore/en-US"
PLAYSTORE_DIR="$DATA_DIR/playstore/en-US/images/phoneScreenshots"

log "═══════════════════════════════════════════════════════════"
log "  Screenshot Upload — $PROJECT_NAME"
log "═══════════════════════════════════════════════════════════"
log ""
log "  Project:   $PROJECT_NAME"
log "  App path:  $PROJECT_PATH"
log "  Data:      $DATA_DIR"
log ""

# ── Find composed screenshots ──────────────────────────────────────────────
IPAD_DIR="$COMPOSED_DIR/iPad Pro 13-inch"
IPHONE_DIR="$COMPOSED_DIR/iPhone 6.7-inch"
PHONE_DIR="$COMPOSED_DIR/Phone"

if [[ ! -d "$IPHONE_DIR" ]]; then
  # Fallback to raw screenshots
  IPHONE_DIR="$DATA_DIR/iPhone 6.7-inch"
  IPAD_DIR="$DATA_DIR/iPad Pro 13-inch"
  if [[ -d "$IPHONE_DIR" ]]; then
    warn "Using raw screenshots (no captions/styling)"
  else
    fail "No screenshots found at $COMPOSED_DIR or $DATA_DIR"
    fail "Run 'Generate All' in the composer UI first."
    exit 1
  fi
else
  log "Using composed screenshots (with captions and styling)"
fi

IPHONE_COUNT=$(ls "$IPHONE_DIR"/*.png 2>/dev/null | wc -l | tr -d ' ')
IPAD_COUNT=0
if [[ -d "$IPAD_DIR" ]]; then
  IPAD_COUNT=$(ls "$IPAD_DIR"/*.png 2>/dev/null | wc -l | tr -d ' ')
fi

log "Found: $IPHONE_COUNT iPhone + $IPAD_COUNT iPad screenshots"
[[ "$IPHONE_COUNT" -gt 0 ]] || { fail "No iPhone screenshots"; exit 1; }

# ── Organize for App Store ─────────────────────────────────────────────────
if $UPLOAD_IOS; then
  log ""
  log "── Organizing for App Store ──────────────────────────────"
  rm -rf "$APPSTORE_DIR"
  mkdir -p "$APPSTORE_DIR"

  if [[ -d "$IPAD_DIR" ]] && [[ "$IPAD_COUNT" -gt 0 ]]; then
    for f in "$IPAD_DIR"/*.png; do
      name=$(basename "$f")
      cp "$f" "$APPSTORE_DIR/IPAD_PRO_129_${name}"
      log "  + IPAD_PRO_129_${name}"
    done
  fi

  for f in "$IPHONE_DIR"/*.png; do
    name=$(basename "$f")
    cp "$f" "$APPSTORE_DIR/APP_IPHONE_67_${name}"
    log "  + APP_IPHONE_67_${name}"
  done

  # Also add 6.5" and 5.5" if available
  for size_dir in "iPhone 6.5-inch" "iPhone 5.5-inch"; do
    extra_dir="$COMPOSED_DIR/$size_dir"
    if [[ -d "$extra_dir" ]]; then
      prefix=$(echo "$size_dir" | sed 's/iPhone /APP_IPHONE_/' | sed 's/-inch//' | sed 's/\./_/')
      for f in "$extra_dir"/*.png; do
        name=$(basename "$f")
        cp "$f" "$APPSTORE_DIR/${prefix}_${name}"
        log "  + ${prefix}_${name}"
      done
    fi
  done

  TOTAL=$(ls "$APPSTORE_DIR"/*.png 2>/dev/null | wc -l | tr -d ' ')
  ok "Organized $TOTAL App Store screenshots"
fi

# ── Organize for Play Store ────────────────────────────────────────────────
if $UPLOAD_ANDROID; then
  log ""
  log "── Organizing for Play Store ─────────────────────────────"
  rm -rf "$PLAYSTORE_DIR"
  mkdir -p "$PLAYSTORE_DIR"

  PHONE_SRC="$PHONE_DIR"
  [[ -d "$PHONE_SRC" ]] || PHONE_SRC="$IPHONE_DIR"

  i=1
  for f in "$PHONE_SRC"/*.png; do
    cp "$f" "$PLAYSTORE_DIR/${i}.png"
    log "  + ${i}.png ← $(basename "$f")"
    i=$((i + 1))
  done

  PLAY_TOTAL=$(ls "$PLAYSTORE_DIR"/*.png 2>/dev/null | wc -l | tr -d ' ')
  ok "Organized $PLAY_TOTAL Play Store screenshots"
fi

# ── Dry run exit ───────────────────────────────────────────────────────────
if $DRY_RUN; then
  log ""
  log "Dry run — skipping upload. Screenshots ready at:"
  $UPLOAD_IOS    && log "  App Store:  $APPSTORE_DIR"
  $UPLOAD_ANDROID && log "  Play Store: $PLAYSTORE_DIR"
  exit 0
fi

# ── Upload to App Store ────────────────────────────────────────────────────
IOS_OK=true
ANDROID_OK=true

if $UPLOAD_IOS; then
  log ""
  log "── Uploading to App Store Connect ────────────────────────"

  FASTLANE_DIR="$PROJECT_PATH/ios"
  if [[ ! -f "$FASTLANE_DIR/fastlane/Fastfile" ]]; then
    fail "iOS fastlane not found at $FASTLANE_DIR/fastlane/Fastfile"
    IOS_OK=false
  elif ! command -v fastlane &>/dev/null; then
    fail "fastlane not installed. Run: gem install fastlane"
    IOS_OK=false
  else
    log "Running: cd $FASTLANE_DIR && fastlane upload_screenshots"
    log ""

    cd "$FASTLANE_DIR"
    # Stream full output — no filtering
    if fastlane upload_screenshots 2>&1 | while IFS= read -r line; do
      echo "  [fastlane] $line"
    done; then
      ok "App Store upload complete!"
    else
      fail "App Store upload failed (exit code: ${PIPESTATUS[0]})"
      IOS_OK=false
    fi
  fi
fi

# ── Upload to Play Store ──────────────────────────────────────────────────
if $UPLOAD_ANDROID; then
  log ""
  log "── Uploading to Google Play Store ────────────────────────"

  FASTLANE_DIR="$PROJECT_PATH/android"
  if [[ ! -f "$FASTLANE_DIR/fastlane/Fastfile" ]]; then
    fail "Android fastlane not found at $FASTLANE_DIR/fastlane/Fastfile"
    ANDROID_OK=false
  elif ! command -v fastlane &>/dev/null; then
    fail "fastlane not installed. Run: gem install fastlane"
    ANDROID_OK=false
  else
    log "Running: cd $FASTLANE_DIR && fastlane upload_screenshots"
    log ""

    cd "$FASTLANE_DIR"
    if fastlane upload_screenshots 2>&1 | while IFS= read -r line; do
      echo "  [fastlane] $line"
    done; then
      ok "Play Store upload complete!"
    else
      fail "Play Store upload failed (exit code: ${PIPESTATUS[0]})"
      ANDROID_OK=false
    fi
  fi
fi

# ── Summary ────────────────────────────────────────────────────────────────
log ""
log "═══════════════════════════════════════════════════════════"
if $IOS_OK && $ANDROID_OK; then
  ok "All uploads complete!"
else
  $IOS_OK     || fail "App Store upload had errors"
  $ANDROID_OK || fail "Play Store upload had errors"
fi
log "═══════════════════════════════════════════════════════════"
$UPLOAD_IOS    && log "  App Store:  https://appstoreconnect.apple.com"
$UPLOAD_ANDROID && log "  Play Store: https://play.google.com/console"
log ""
