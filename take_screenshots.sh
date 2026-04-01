#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# take_screenshots.sh — Automated App Store Screenshot Generator
#
# Generates native-resolution screenshots for Apple App Store:
#   - iPad Pro 13"  (2064×2752)  — Required for iPad submissions
#   - iPhone 6.7"   (1290×2796)  — Required for iPhone submissions
#
# Uses output-watching approach:
#   1. Runs flutter drive which navigates screens and prints "📸 <Label>"
#   2. When a 📸 line is detected, captures the simulator via simctl io
#
# Usage:
#   ./take_screenshots.sh            # All devices
#   ./take_screenshots.sh ipad       # iPad only
#   ./take_screenshots.sh iphone     # iPhone only
#   ./take_screenshots.sh --clean    # Remove all screenshots
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── Configuration ───────────────────────────────────────────────────────────
# Read device names from screenshot_project.json if available
PROJECT_JSON="$SCRIPT_DIR/screenshot_project.json"
if [ -f "$PROJECT_JSON" ]; then
  IPAD_NAME=$(python3 -c "import json; d=json.load(open('$PROJECT_JSON')); print(d.get('capture',{}).get('ipad_simulator','iPad Pro 13-inch (M5)'))" 2>/dev/null || echo "iPad Pro 13-inch (M5)")
  IPHONE_NAME=$(python3 -c "import json; d=json.load(open('$PROJECT_JSON')); print(d.get('capture',{}).get('iphone_simulator','iPhone 17 Pro Max'))" 2>/dev/null || echo "iPhone 17 Pro Max")
  APP_NAME=$(python3 -c "import json; d=json.load(open('$PROJECT_JSON')); print(d.get('app_name','App'))" 2>/dev/null || echo "App")
else
  IPAD_NAME="iPad Pro 13-inch (M5)"
  IPHONE_NAME="iPhone 17 Pro Max"
  APP_NAME="App"
fi

OUTPUT_DIR="$SCRIPT_DIR/screenshots"
IPAD_DIR="$OUTPUT_DIR/iPad Pro 13-inch"
IPHONE_DIR="$OUTPUT_DIR/iPhone 6.7-inch"
BACKUP_DIR="$OUTPUT_DIR/logical"

# ── Handle --clean flag ────────────────────────────────────────────────────
if [[ "${1:-}" == "--clean" ]]; then
  echo "Removing all screenshots..."
  rm -rf "$OUTPUT_DIR"
  echo "Done. Screenshots directory removed."
  exit 0
fi

# Lookup label → filename (must match screenshot_test.dart)
label_to_file() {
  case "$1" in
    Home)         echo "01_home" ;;
    "Net Worth")  echo "02_networth" ;;
    Goals)        echo "03_goals" ;;
    Retirement)   echo "04_retirement" ;;
    Cashflow)     echo "05_cashflow" ;;
    Protection)   echo "06_protection" ;;
    Import)       echo "07_import" ;;
    *)            echo "" ;;
  esac
}

# ── Helper Functions ────────────────────────────────────────────────────────

log() { echo "$(date '+%H:%M:%S') | $*"; }
err() { echo "$(date '+%H:%M:%S') | ❌ $*" >&2; }

get_udid() {
  local name="$1"
  xcrun simctl list devices available -j \
    | python3 -c "
import json, sys
data = json.load(sys.stdin)
for runtime, devices in data.get('devices', {}).items():
    for d in devices:
        if d['name'] == '$name' and d['isAvailable']:
            print(d['udid'])
            sys.exit(0)
sys.exit(1)
" 2>/dev/null
}

boot_simulator() {
  local udid="$1"
  local name="$2"
  local state
  state=$(xcrun simctl list devices -j | python3 -c "
import json, sys
data = json.load(sys.stdin)
for runtime, devices in data.get('devices', {}).items():
    for d in devices:
        if d['udid'] == '$udid':
            print(d['state'])
            sys.exit(0)
" 2>/dev/null)

  if [ "$state" = "Booted" ]; then
    log "  $name already booted"
  else
    log "  Booting $name..."
    xcrun simctl boot "$udid" 2>/dev/null || true
    sleep 8
    log "  $name booted"
  fi
}

shutdown_simulator() {
  local udid="$1"
  local name="$2"
  log "  Shutting down $name..."
  xcrun simctl shutdown "$udid" 2>/dev/null || true
}

get_dimensions() {
  sips -g pixelWidth -g pixelHeight "$1" 2>/dev/null \
    | grep pixel \
    | awk '{print $2}' \
    | tr '\n' 'x' \
    | sed 's/x$//'
}

run_device() {
  local udid="$1"
  local device_label="$2"
  local output_dir="$3"

  log "  Running screenshot test on $device_label..."
  mkdir -p "$output_dir"

  # Also save logical-res backups from the driver
  local backup_device_dir="$BACKUP_DIR/$device_label"
  mkdir -p "$backup_device_dir"

  # Run Flutter drive and watch output for screenshot signals
  SCREENSHOT_DIR="$backup_device_dir" \
  flutter drive \
    --driver=test_driver/screenshot_driver.dart \
    --target=integration_test/screenshot_test.dart \
    --device-id="$udid" \
    --no-pub \
    2>&1 | while IFS= read -r line; do
      # Show progress lines
      if echo "$line" | grep -qE '(📱|✅|🔐|🎉|❌|⚠️|Saved:)'; then
        log "    $line"
      fi

      # When we see "📸 <Label>", capture the simulator screen
      if echo "$line" | grep -q '📸'; then
        # Extract label (everything after 📸 and space)
        local label
        label=$(echo "$line" | sed 's/.*📸 //')

        # Look up filename
        local filename
        filename=$(label_to_file "$label")
        if [ -n "$filename" ]; then
          # Brief delay to ensure the frame is fully rendered on screen
          sleep 0.3
          xcrun simctl io "$udid" screenshot --type=png "$output_dir/$filename.png" 2>/dev/null
          log "    📸 Captured $filename ($(get_dimensions "$output_dir/$filename.png"))"
        fi
      fi
    done

  # Count results
  local count
  count=$(find "$output_dir" -name "*.png" 2>/dev/null | wc -l | tr -d ' ')
  log "  ✅ $count native-resolution screenshots in $output_dir/"
}

# ── Main ────────────────────────────────────────────────────────────────────

main() {
  local target="${1:-all}"

  log "═══════════════════════════════════════════════════════════"
  log "  $APP_NAME — App Store Screenshot Generator"
  log "═══════════════════════════════════════════════════════════"

  local do_ipad=false
  local do_iphone=false

  case "$target" in
    ipad)    do_ipad=true ;;
    iphone)  do_iphone=true ;;
    all)     do_ipad=true; do_iphone=true ;;
    *)       err "Unknown target: $target (use: all, ipad, iphone)"; exit 1 ;;
  esac

  # Clean only the targeted device directories (not the entire output)
  mkdir -p "$OUTPUT_DIR"
  if $do_ipad; then rm -rf "$IPAD_DIR"; fi
  if $do_iphone; then rm -rf "$IPHONE_DIR"; fi

  # ── iPad ───────────────────────────────────────────────────────────────
  if $do_ipad; then
    log ""
    log "── iPad Pro 13-inch ──────────────────────────────────────"

    local ipad_udid
    ipad_udid=$(get_udid "$IPAD_NAME") || {
      err "Simulator not found: $IPAD_NAME"
      xcrun simctl list devices available | grep -i ipad
      exit 1
    }
    log "  UDID: $ipad_udid"

    boot_simulator "$ipad_udid" "$IPAD_NAME"
    open -a Simulator --args -CurrentDeviceUDID "$ipad_udid" 2>/dev/null || true
    sleep 3

    run_device "$ipad_udid" "ipad" "$IPAD_DIR" || true
    shutdown_simulator "$ipad_udid" "$IPAD_NAME"
  fi

  # ── iPhone ─────────────────────────────────────────────────────────────
  if $do_iphone; then
    log ""
    log "── iPhone 17 Pro Max (6.7-inch) ──────────────────────────"

    local iphone_udid
    iphone_udid=$(get_udid "$IPHONE_NAME") || {
      err "Simulator not found: $IPHONE_NAME"
      xcrun simctl list devices available | grep -i iphone
      exit 1
    }
    log "  UDID: $iphone_udid"

    boot_simulator "$iphone_udid" "$IPHONE_NAME"
    open -a Simulator --args -CurrentDeviceUDID "$iphone_udid" 2>/dev/null || true
    sleep 3

    run_device "$iphone_udid" "iphone" "$IPHONE_DIR" || true
    shutdown_simulator "$iphone_udid" "$IPHONE_NAME"
  fi

  # ── Summary ─────────────────────────────────────────────────────────────
  log ""
  log "═══════════════════════════════════════════════════════════"
  log "  Done!"
  log "═══════════════════════════════════════════════════════════"
  log ""
  log "  Output: $OUTPUT_DIR/"

  if $do_ipad && [ -d "$IPAD_DIR" ]; then
    log ""
    log "  iPad Pro 13-inch:"
    for f in "$IPAD_DIR"/*.png; do
      [ -f "$f" ] && log "    $(basename "$f")  $(get_dimensions "$f")"
    done
  fi

  if $do_iphone && [ -d "$IPHONE_DIR" ]; then
    log ""
    log "  iPhone 6.7-inch:"
    for f in "$IPHONE_DIR"/*.png; do
      [ -f "$f" ] && log "    $(basename "$f")  $(get_dimensions "$f")"
    done
  fi

  log ""
  log "  Next: python compose_screenshots.py  (to add captions + backgrounds)"
  log ""
}

main "$@"
