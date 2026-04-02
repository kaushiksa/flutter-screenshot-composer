# Flutter Screenshot Composer

A centralized tool for capturing, composing, and uploading App Store / Play Store screenshots across all your Flutter projects.

**One install, all your apps.**

## Features

- **Multi-project** — Register all your Flutter projects, switch between them from the UI
- **Browser-based UI** at `http://localhost:8234` for previewing and tweaking
- **Auto-detects screens** from PNG files
- **Gradient backgrounds** with marketing headline/subheadline overlays
- **AI-generated captions** via OpenAI (optional)
- **Capture from Simulator** — trigger screenshot capture directly from the UI
- **Auto-scales** to all required App Store & Play Store sizes
- **Upload** to App Store Connect and Google Play via fastlane
- **Centralized storage** — all screenshots, config, and composed output stored with the tool

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/kaushiksa/flutter-screenshot-composer.git ~/tools/screenshot-composer
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
- Enter a name (e.g. "MyApp")
- Enter the path to your Flutter project (e.g. `/Users/you/work/myapp`)

Or from the CLI:
```bash
python compose_screenshots.py --add-project "MyApp" "/Users/you/work/myapp"
```

This will:
- Register the project in `projects.json`
- Create `project_data/MyApp/` for screenshots and config
- Copy `screenshot_driver.dart` and `screenshot_test_template.dart` into your project's `screenshots/` folder

### 4. Add screenshots

**Option A — Drop PNGs manually:**

Place raw screenshots in the tool's project data folder:
```
~/tools/screenshot-composer/project_data/MyApp/screenshots/
  iPhone 6.7-inch/
    01_home.png
    02_profile.png
  iPad Pro 13-inch/
    01_home.png
    02_profile.png
```

**Option B — Capture from Simulator:**

1. Set up your project's screenshot test (see [Setting Up Automated Capture](#setting-up-automated-capture))
2. Click **"Capture from Simulator"** in the UI

### 5. Compose & Upload

- Adjust gradients, captions, typography in the sidebar
- Click **"Generate All"** to compose all screenshots
- Click **"Upload iOS"** / **"Upload Android"** to push to stores

---

## What Lives Where

```
~/tools/screenshot-composer/              # The tool (install once)
  compose_screenshots.py                  # Main tool
  take_screenshots.sh                     # Capture script
  projects.json                           # Registry of all projects
  project_data/
    MyApp/                                # Everything for this project
      screenshots/
        iPhone 6.7-inch/                  # Raw screenshots
          01_home.png
        iPad Pro 13-inch/
          01_home.png
        composed/                         # Generated output
          iPhone 6.7-inch/
          iPhone 6.5-inch/                # Auto-scaled
          Phone/                          # Play Store
      screenshot_config.json              # Layout config (from UI tweaks)
      screenshot_captions.json            # Captions
  test_driver/
    screenshot_driver.dart                # Template (auto-copied to projects)
  integration_test/
    screenshot_test_template.dart         # Template (auto-copied to projects)

your_flutter_project/                     # Your app (minimal footprint)
  screenshot_project.json                 # Optional: app name, screens, colors
  screenshots/                            # Only dart files for capture
    screenshot_test.dart                  # Your app-specific capture test
    screenshot_driver.dart                # Generic driver (auto-copied)
```

**Your Flutter project stays clean** — no raw screenshots, no composed output, no config files. Just the optional project config and the dart files needed for automated capture.

---

## Setting Up a New Project

### Step 1: Register

```bash
python compose_screenshots.py --add-project "MyApp" "/path/to/flutter/project"
```

### Step 2: Create `screenshot_project.json` (optional)

Create this file in your Flutter project root:

```json
{
  "app_name": "My App",
  "app_description": "a short description for AI caption generation",
  "screens": [
    {"key": "01_home", "label": "Home"},
    {"key": "02_search", "label": "Search"},
    {"key": "03_profile", "label": "Profile"}
  ],
  "gradients": {
    "01_home": ["#2563EB", "#1E40AF"],
    "02_search": ["#7C3AED", "#5B21B6"],
    "03_profile": ["#10B981", "#059669"]
  },
  "capture": {
    "ipad_simulator": "iPad Pro 13-inch (M5)",
    "iphone_simulator": "iPhone 17 Pro Max"
  }
}
```

Without this file, the tool auto-detects everything from the PNG filenames and assigns colors from a built-in palette.

### Step 3: Add screenshots

Either drop PNGs into `project_data/MyApp/screenshots/iPhone 6.7-inch/` or set up automated capture (see below).

### Step 4: Launch and compose

```bash
python compose_screenshots.py
```

---

## Setting Up Automated Capture

When you register a project, the tool auto-copies two files into `your_project/screenshots/`:

- `screenshot_driver.dart` — Generic, works as-is
- `screenshot_test_template.dart` — Rename to `screenshot_test.dart` and customize

### Customize `screenshot_test.dart`

Fill in the TODOs:
1. **Imports** — Your app's packages
2. **Screen list** — Routes and filenames
3. **App init** — Firebase, etc.
4. **Auth** — Login if needed
5. **Navigation** — GoRouter, Navigator, etc.

Then click **"Capture from Simulator"** in the UI.

---

## Multi-Project Workflow

| Action | UI | CLI |
|--------|-----|-----|
| Add project | Click **+** | `--add-project "Name" "/path"` |
| Switch project | Select from dropdown | `--project "Name"` |
| Remove project | Click **x** | — |

Switching projects reloads all config, screenshots, and captions for that project.

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
