#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# upload_store.sh — Upload EVERYTHING to App Store / Play Store
#
# Part of flutter-screenshot-composer (centralized tool).
# Handles: screenshots, metadata, icons, feature graphics — all from one place.
#
# Usage:
#   ./upload_store.sh                           # Upload everything to both stores
#   ./upload_store.sh --screenshots             # Screenshots only
#   ./upload_store.sh --metadata                # Metadata + icon + feature graphic only
#   ./upload_store.sh --ios                     # App Store only
#   ./upload_store.sh --android                 # Play Store only
#   ./upload_store.sh --generate-assets         # Generate feature graphic etc (no upload)
#   ./upload_store.sh --dry-run                 # Organize only, skip upload
#   ./upload_store.sh --project X               # Override active project
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail

TOOL_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECTS_FILE="$TOOL_DIR/projects.json"

# ── Parse arguments ─────────────────────────────────────────────────────────
DRY_RUN=false
UPLOAD_IOS=true
UPLOAD_ANDROID=true
DO_SCREENSHOTS=true
DO_METADATA=true
GENERATE_ONLY=false
PROJECT_OVERRIDE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)          DRY_RUN=true; shift ;;
    --ios)              UPLOAD_ANDROID=false; shift ;;
    --android)          UPLOAD_IOS=false; shift ;;
    --screenshots)      DO_METADATA=false; shift ;;
    --metadata)         DO_SCREENSHOTS=false; shift ;;
    --generate-assets)  GENERATE_ONLY=true; shift ;;
    --project)          PROJECT_OVERRIDE="$2"; shift 2 ;;
    --help|-h)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "  --ios              App Store only"
      echo "  --android          Play Store only"
      echo "  --screenshots      Screenshots only (skip metadata)"
      echo "  --metadata         Metadata/icon/feature graphic only (skip screenshots)"
      echo "  --generate-assets  Generate feature graphic etc, no upload"
      echo "  --dry-run          Organize files, skip upload"
      echo "  --project NAME     Override active project"
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
[[ -f "$PROJECTS_FILE" ]] || { fail "projects.json not found"; exit 1; }

if [[ -n "$PROJECT_OVERRIDE" ]]; then
  PROJECT_NAME="$PROJECT_OVERRIDE"
else
  PROJECT_NAME=$(python3 -c "import json; d=json.load(open('$PROJECTS_FILE')); print(d.get('active',''))")
fi
[[ -n "$PROJECT_NAME" ]] || { fail "No active project"; exit 1; }

PROJECT_PATH=$(python3 -c "
import json
d = json.load(open('$PROJECTS_FILE'))
for p in d.get('projects', []):
    if p['name'] == '$PROJECT_NAME':
        print(p['path'])
        break
")
[[ -n "$PROJECT_PATH" ]] && [[ -d "$PROJECT_PATH" ]] || { fail "Project path not found: $PROJECT_PATH"; exit 1; }

DATA_DIR="$TOOL_DIR/project_data/$PROJECT_NAME/screenshots"
COMPOSED_DIR="$DATA_DIR/composed"
PROJECT_JSON="$PROJECT_PATH/screenshot_project.json"

log "═══════════════════════════════════════════════════════════"
log "  Store Upload — $PROJECT_NAME"
log "═══════════════════════════════════════════════════════════"
log ""
log "  Project:   $PROJECT_NAME"
log "  App path:  $PROJECT_PATH"
log "  Mode:      $(${DO_SCREENSHOTS} && echo 'screenshots ')$(${DO_METADATA} && echo 'metadata ')"
log ""

# ── Generate Feature Graphic ──────────────────────────────────────────────
generate_feature_graphic() {
  local out_path="$1"
  log "Generating feature graphic..."

  python3 << PYEOF
from PIL import Image, ImageDraw, ImageFont
import numpy as np, json, sys
from pathlib import Path

W, H = 1024, 500
project_json = Path("$PROJECT_JSON")

# Defaults
app_name = "$PROJECT_NAME"
subtitle = ""
c1, c2 = (100, 100, 200), (50, 50, 100)

# Read project config
if project_json.exists():
    cfg = json.loads(project_json.read_text())
    app_name = cfg.get("app_name", app_name)
    subtitle = cfg.get("app_description", subtitle)[:60]
    grads = cfg.get("gradients", {})
    if grads:
        first_grad = list(grads.values())[0]
        if len(first_grad) >= 2:
            h1, h2 = first_grad[0].lstrip("#"), first_grad[1].lstrip("#")
            c1 = (int(h1[0:2],16), int(h1[2:4],16), int(h1[4:6],16))
            c2 = (int(h2[0:2],16), int(h2[2:4],16), int(h2[4:6],16))

# Gradient
arr = np.zeros((H, W, 3), dtype=np.uint8)
for ch in range(3):
    arr[:, :, ch] = np.linspace(c1[ch], c2[ch], H, dtype=np.uint8)[:, np.newaxis]
img = Image.fromarray(arr, "RGB")
draw = ImageDraw.Draw(img)

try:
    font_h = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", 52)
    font_s = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", 24)
except:
    font_h = ImageFont.load_default()
    font_s = font_h

# App icon
icon_path = Path("$PROJECT_PATH") / "assets" / "icons" / "app-icon.png"
icon_y = 75
if icon_path.exists():
    icon = Image.open(str(icon_path)).convert("RGBA").resize((80, 80), Image.LANCZOS)
    img = img.convert("RGBA")
    img.paste(icon, ((W-80)//2, icon_y), icon)
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)

# Title
bbox = draw.textbbox((0,0), app_name, font=font_h)
draw.text(((W-(bbox[2]-bbox[0]))//2, 170), app_name, font=font_h, fill=(255,255,255))

# Subtitle
if subtitle:
    bbox2 = draw.textbbox((0,0), subtitle, font=font_s)
    draw.text(((W-(bbox2[2]-bbox2[0]))//2, 250), subtitle, font=font_s, fill=(255,255,255,200))

img.save("$out_path", "PNG")
print(f"  Feature graphic: {img.size[0]}x{img.size[1]}")
PYEOF

  [[ -f "$out_path" ]] && ok "Feature graphic generated: $out_path" || fail "Feature graphic generation failed"
}

# ── Generate / sync metadata assets ──────────────────────────────────────
if $DO_METADATA; then
  log "── Generating Store Assets ──────────────────────────────"

  # iOS: app icon (1024x1024)
  IOS_META="$PROJECT_PATH/ios/fastlane/metadata"
  if [[ ! -f "$IOS_META/app_icon.png" ]]; then
    ICON_SRC="$PROJECT_PATH/assets/icons/app-icon.png"
    if [[ -f "$ICON_SRC" ]]; then
      mkdir -p "$IOS_META"
      sips -z 1024 1024 "$ICON_SRC" --out "$IOS_META/app_icon.png" 2>/dev/null
      ok "iOS app icon (1024x1024)"
    fi
  else
    log "  iOS app icon already exists"
  fi

  # Android: feature graphic
  ANDROID_IMAGES="$PROJECT_PATH/android/fastlane/metadata/android/en-US/images"
  mkdir -p "$ANDROID_IMAGES"
  generate_feature_graphic "$ANDROID_IMAGES/featureGraphic.png"

  # Android: icon (512x512)
  if [[ ! -f "$ANDROID_IMAGES/icon.png" ]]; then
    ICON_SRC="$PROJECT_PATH/assets/icons/app-icon.png"
    if [[ -f "$ICON_SRC" ]]; then
      cp "$ICON_SRC" "$ANDROID_IMAGES/icon.png"
      ok "Android app icon (512x512)"
    fi
  else
    log "  Android app icon already exists"
  fi

  # Generate metadata from screenshot_project.json if metadata files don't exist
  if [[ -f "$PROJECT_JSON" ]]; then
    log ""
    log "── Syncing metadata from screenshot_project.json ────────"

    APP_NAME=$(python3 -c "import json; print(json.load(open('$PROJECT_JSON')).get('app_name',''))")
    APP_DESC=$(python3 -c "import json; print(json.load(open('$PROJECT_JSON')).get('app_description',''))")

    # iOS metadata
    IOS_LANG="$IOS_META/en-US"
    mkdir -p "$IOS_LANG"
    [[ -f "$IOS_LANG/name.txt" ]]    || { echo -n "$APP_NAME" > "$IOS_LANG/name.txt"; log "  + iOS name.txt"; }
    [[ -f "$IOS_META/copyright.txt" ]] || { echo "$(date +%Y) $APP_NAME" > "$IOS_META/copyright.txt"; log "  + iOS copyright.txt"; }

    # Android metadata
    ANDROID_LANG="$PROJECT_PATH/android/fastlane/metadata/android/en-US"
    mkdir -p "$ANDROID_LANG"
    [[ -f "$ANDROID_LANG/title.txt" ]] || { echo -n "$APP_NAME" > "$ANDROID_LANG/title.txt"; log "  + Android title.txt"; }
  fi
fi

if $GENERATE_ONLY; then
  ok "Assets generated. Skipping upload."
  exit 0
fi

# ── Organize screenshots ─────────────────────────────────────────────────
APPSTORE_DIR="$PROJECT_PATH/screenshots/appstore/en-US"
PLAYSTORE_DIR="$PROJECT_PATH/screenshots/playstore/en-US/images/phoneScreenshots"

if $DO_SCREENSHOTS; then
  IPAD_DIR="$COMPOSED_DIR/iPad Pro 13-inch"
  IPHONE_DIR="$COMPOSED_DIR/iPhone 6.7-inch"
  PHONE_DIR="$COMPOSED_DIR/Phone"

  if [[ ! -d "$IPHONE_DIR" ]]; then
    IPHONE_DIR="$DATA_DIR/iPhone 6.7-inch"
    IPAD_DIR="$DATA_DIR/iPad Pro 13-inch"
    [[ -d "$IPHONE_DIR" ]] && warn "Using raw screenshots" || { fail "No screenshots found"; exit 1; }
  else
    log "Using composed screenshots"
  fi

  IPHONE_COUNT=$(ls "$IPHONE_DIR"/*.png 2>/dev/null | wc -l | tr -d ' ')
  IPAD_COUNT=0
  [[ -d "$IPAD_DIR" ]] && IPAD_COUNT=$(ls "$IPAD_DIR"/*.png 2>/dev/null | wc -l | tr -d ' ')
  log "Found: $IPHONE_COUNT iPhone + $IPAD_COUNT iPad screenshots"

  if $UPLOAD_IOS; then
    log ""
    log "── Organizing for App Store ──────────────────────────────"
    rm -rf "$APPSTORE_DIR"; mkdir -p "$APPSTORE_DIR"
    [[ -d "$IPAD_DIR" ]] && [[ "$IPAD_COUNT" -gt 0 ]] && for f in "$IPAD_DIR"/*.png; do
      cp "$f" "$APPSTORE_DIR/IPAD_PRO_129_$(basename "$f")"; done
    for f in "$IPHONE_DIR"/*.png; do
      cp "$f" "$APPSTORE_DIR/APP_IPHONE_67_$(basename "$f")"; done
    for size_dir in "iPhone 6.5-inch" "iPhone 5.5-inch"; do
      extra="$COMPOSED_DIR/$size_dir"
      [[ -d "$extra" ]] && {
        prefix=$(echo "$size_dir" | sed 's/iPhone /APP_IPHONE_/' | sed 's/-inch//' | sed 's/\./_/')
        for f in "$extra"/*.png; do cp "$f" "$APPSTORE_DIR/${prefix}_$(basename "$f")"; done
      }
    done
    ok "Organized $(ls "$APPSTORE_DIR"/*.png 2>/dev/null | wc -l | tr -d ' ') App Store screenshots"
  fi

  if $UPLOAD_ANDROID; then
    log ""
    log "── Organizing for Play Store ─────────────────────────────"
    rm -rf "$PLAYSTORE_DIR"; mkdir -p "$PLAYSTORE_DIR"
    PHONE_SRC="$PHONE_DIR"; [[ -d "$PHONE_SRC" ]] || PHONE_SRC="$IPHONE_DIR"
    i=1; for f in "$PHONE_SRC"/*.png; do cp "$f" "$PLAYSTORE_DIR/${i}.png"; i=$((i+1)); done
    ok "Organized $(ls "$PLAYSTORE_DIR"/*.png 2>/dev/null | wc -l | tr -d ' ') Play Store screenshots"
  fi
fi

# ── Dry run exit ─────────────────────────────────────────────────────────
if $DRY_RUN; then
  log ""; log "Dry run — skipping upload."
  exit 0
fi

# ── Upload ───────────────────────────────────────────────────────────────
IOS_OK=true
ANDROID_OK=true

run_cmd() {
  local label="$1"; shift
  log "Running: $*"
  if "$@" 2>&1 | while IFS= read -r line; do echo "  [fastlane] $line"; done; then
    ok "$label complete!"
    return 0
  else
    fail "$label failed (exit code: ${PIPESTATUS[0]})"
    return 1
  fi
}

# ── iOS uploads ──────────────────────────────────────────────────────────
if $UPLOAD_IOS; then
  log ""
  log "── Uploading to App Store Connect ────────────────────────"
  IOS_DIR="$PROJECT_PATH/ios"
  IOS_META="$IOS_DIR/fastlane/metadata"

  if ! command -v fastlane &>/dev/null; then
    fail "fastlane not installed"; IOS_OK=false
  else
    # Detect API key from Fastfile or use env
    API_KEY_PATH="$PROJECT_PATH/private_keys/AuthKey_4Y382MAR5G.p8"
    DELIVER_COMMON=(
      --app_identifier "$(grep -m1 'app_identifier' "$IOS_DIR/fastlane/Fastfile" 2>/dev/null | sed 's/.*"\(.*\)".*/\1/' || echo '')"
      --force
      --precheck_include_in_app_purchases false
      --skip_binary_upload true
    )

    # Try using lanes if they exist, otherwise use deliver directly
    if $DO_SCREENSHOTS; then
      cd "$IOS_DIR"
      run_cmd "App Store screenshots" fastlane upload_screenshots || IOS_OK=false
    fi

    if $DO_METADATA && [[ -d "$IOS_META" ]]; then
      cd "$IOS_DIR"
      # Check if upload_metadata lane exists
      if grep -q "lane :upload_metadata" "$IOS_DIR/fastlane/Fastfile" 2>/dev/null; then
        run_cmd "App Store metadata" fastlane upload_metadata || IOS_OK=false
      else
        # Use deliver directly — works for any project
        log "No upload_metadata lane found, using deliver directly..."
        run_cmd "App Store metadata" fastlane deliver \
          --skip_binary_upload true \
          --skip_screenshots true \
          --skip_metadata false \
          --overwrite_screenshots false \
          --metadata_path "$IOS_META" \
          --precheck_include_in_app_purchases false \
          --force true \
          || IOS_OK=false
      fi
    fi
  fi
fi

# ── Android uploads ──────────────────────────────────────────────────────
if $UPLOAD_ANDROID; then
  log ""
  log "── Uploading to Google Play Store ────────────────────────"
  ANDROID_DIR="$PROJECT_PATH/android"
  ANDROID_META="$ANDROID_DIR/fastlane/metadata/android"
  PLAY_JSON="$PROJECT_PATH/play-service-account.json"
  PACKAGE_NAME=$(grep -m1 'package_name' "$ANDROID_DIR/fastlane/Fastfile" 2>/dev/null | sed "s/.*'\(.*\)'.*/\1/" || echo '')

  if ! command -v fastlane &>/dev/null; then
    fail "fastlane not installed"; ANDROID_OK=false
  elif [[ ! -f "$PLAY_JSON" ]]; then
    fail "play-service-account.json not found at $PLAY_JSON"; ANDROID_OK=false
  else
    if $DO_SCREENSHOTS; then
      cd "$ANDROID_DIR"
      run_cmd "Play Store screenshots" fastlane upload_screenshots || ANDROID_OK=false
    fi

    if $DO_METADATA && [[ -d "$ANDROID_META" ]]; then
      cd "$ANDROID_DIR"
      # Check if upload_metadata lane exists
      if grep -q "lane :upload_metadata" "$ANDROID_DIR/fastlane/Fastfile" 2>/dev/null; then
        run_cmd "Play Store metadata" fastlane upload_metadata || ANDROID_OK=false
      else
        # Use supply directly — works for any project
        log "No upload_metadata lane found, using supply directly..."
        run_cmd "Play Store metadata" fastlane supply \
          --skip_upload_apk true \
          --skip_upload_aab true \
          --skip_upload_screenshots true \
          --skip_upload_changelogs true \
          --skip_upload_metadata false \
          --skip_upload_images false \
          --json_key "$PLAY_JSON" \
          --package_name "$PACKAGE_NAME" \
          --metadata_path "$ANDROID_META" \
          || ANDROID_OK=false
      fi
    fi
  fi
fi

# ── Summary ──────────────────────────────────────────────────────────────
log ""
log "═══════════════════════════════════════════════════════════"
$IOS_OK && $ANDROID_OK && ok "All uploads complete!" || {
  $IOS_OK     || fail "App Store had errors"
  $ANDROID_OK || fail "Play Store had errors"
}
log "═══════════════════════════════════════════════════════════"
$UPLOAD_IOS    && log "  App Store:  https://appstoreconnect.apple.com"
$UPLOAD_ANDROID && log "  Play Store: https://play.google.com/console"
log ""
