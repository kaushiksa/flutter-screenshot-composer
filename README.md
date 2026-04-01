# Flutter Screenshot Composer

A centralized tool for capturing, composing, and uploading App Store / Play Store screenshots across all your Flutter projects.

**One install, all your apps.**

## Features

- **Multi-project** — Register all your Flutter projects, switch between them from the UI
- **Browser-based UI** at `http://localhost:8234` for previewing and tweaking
- **Auto-detects screens** from PNG files in the project's `screenshots/` folder
- **Gradient backgrounds** with marketing headline/subheadline overlays
- **AI-generated captions** via OpenAI (optional)
- **Capture from Simulator** — trigger screenshot capture directly from the UI
- **Auto-scales** to all required App Store & Play Store sizes
- **Upload** to App Store Connect and Google Play via fastlane
- Per-project config stored centrally — no files copied into your projects

---

## Quick Start

### 1. Install

```bash
# Clone to a permanent location
git clone https://github.com/kaushiksa/flutter-screenshot-composer.git ~/tools/screenshot-composer

# Install Python dependencies
pip install Pillow numpy
pip install openai  # optional, for AI captions
```

### 2. Launch

```bash
cd ~/tools/screenshot-composer
python compose_screenshots.py
```

Opens the UI at `http://localhost:8234`.

### 3. Add your first project

From the UI, click the **+** button next to the project dropdown:
- Enter a name (e.g. "Dhi")
- Enter the path to your Flutter project (e.g. `/Users/you/work/Dhi/v2/monorepo/app`)

Or from the CLI:
```bash
python compose_screenshots.py --add-project "Dhi" "/Users/you/work/Dhi/v2/monorepo/app"
```

This will:
- Register the project
- Copy `screenshot_driver.dart` and `screenshot_test_template.dart` into the project (if not already present)
- Switch to it as the active project

### 4. Add screenshots

**Option A — Drop PNGs manually:**
Place raw screenshots in your Flutter project:
```
your_flutter_project/
  screenshots/
    iPhone 6.7-inch/
      01_home.png
      02_profile.png
    iPad Pro 13-inch/
      01_home.png
      02_profile.png
```

**Option B — Capture from Simulator:**
1. Customize `integration_test/screenshot_test.dart` in your project (copy from the template)
2. Click **"Capture from Simulator"** in the UI

### 5. Compose & Upload

- Adjust gradients, captions, typography in the sidebar
- Click **"Generate All"** to compose all screenshots
- Click **"Upload iOS"** / **"Upload Android"** to push to stores

---

## Multi-Project Workflow

The project selector dropdown in the UI header lets you:

| Action | UI | CLI |
|--------|-----|-----|
| Add project | Click **+** | `--add-project "Name" "/path"` |
| Switch project | Select from dropdown | `--project "Name"` |
| Remove project | Click **x** | — |

All project configs (layout settings, captions) are stored centrally in `project_data/<name>/`, so your Flutter projects stay clean.

### What lives where

```
~/tools/screenshot-composer/          # The tool (install once)
  compose_screenshots.py              # Main tool
  take_screenshots.sh                 # Capture script
  projects.json                       # Registry of all projects
  project_data/
    Dhi/                              # Per-project config
      screenshot_config.json
      screenshot_captions.json
    FurFam/
      screenshot_config.json
      screenshot_captions.json
  test_driver/
    screenshot_driver.dart            # Auto-copied to projects
  integration_test/
    screenshot_test_template.dart     # Auto-copied to projects

your_flutter_project/                 # Your app (no tool files needed)
  screenshot_project.json             # Optional: app name, screens, colors
  screenshots/                        # Raw + composed screenshots
    iPhone 6.7-inch/
    iPad Pro 13-inch/
    composed/
  integration_test/
    screenshot_test.dart              # Your app-specific navigation
  test_driver/
    screenshot_driver.dart            # Auto-copied by the tool
```

---

## Project Config (`screenshot_project.json`)

Optional file in your Flutter project root. All fields are optional.

```json
{
  "app_name": "My App",
  "app_description": "a short description for AI caption generation",
  "screens": [
    {"key": "01_home", "label": "Home"},
    {"key": "02_search", "label": "Search"}
  ],
  "gradients": {
    "01_home": ["#2563EB", "#1E40AF"],
    "02_search": ["#7C3AED", "#5B21B6"]
  },
  "captions": {
    "01_home": {"headline": "Welcome Home", "subheadline": "Everything at a glance"}
  },
  "capture": {
    "ipad_simulator": "iPad Pro 13-inch (M5)",
    "iphone_simulator": "iPhone 17 Pro Max"
  }
}
```

Without this file, the tool auto-detects everything from the PNG filenames.

---

## CLI Usage

```bash
# Launch UI (default)
python compose_screenshots.py

# Add a project
python compose_screenshots.py --add-project "AppName" "/path/to/flutter/project"

# Switch project and launch
python compose_screenshots.py --project "AppName"

# Generate without UI
python compose_screenshots.py --no-preview

# Force new AI captions
python compose_screenshots.py --regenerate-captions

# Process specific device
python compose_screenshots.py --iphone-only
python compose_screenshots.py --ipad-only
```

---

## Auto-Generated Sizes

From the iPhone 6.7" source, the tool automatically generates:

| Size | Resolution | Store |
|------|-----------|-------|
| iPhone 6.7-inch | 1320 x 2868 | App Store (required) |
| iPhone 6.5-inch | 1284 x 2778 | App Store (scaled) |
| iPhone 5.5-inch | 1242 x 2208 | App Store (scaled) |
| iPad Pro 13-inch | 2064 x 2752 | App Store (native) |
| Phone | 1080 x 1920 | Play Store (cropped + scaled) |

---

## Setting Up Automated Capture

1. The tool auto-copies `screenshot_driver.dart` and `screenshot_test_template.dart` when you add a project
2. Rename the template: `mv integration_test/screenshot_test_template.dart integration_test/screenshot_test.dart`
3. Fill in the TODOs: your app imports, screen routes, auth setup
4. Click **"Capture from Simulator"** in the UI

---

## Requirements

- **Python 3.10+**
- **Pillow** and **numpy** (`pip install Pillow numpy`)
- **Flutter SDK** (for automated capture)
- **Xcode + iOS Simulator** (for capture on macOS)
- **OpenAI Python SDK** (optional: `pip install openai`)
- **fastlane** (optional, for store uploads)

---

## License

MIT
