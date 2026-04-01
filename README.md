# Flutter Screenshot Composer

A plug-and-play tool for capturing, composing, and uploading App Store / Play Store screenshots from any Flutter project.

**Features:**
- Browser-based UI for previewing and tweaking screenshots
- Auto-detects screens from PNG files in `screenshots/` folder
- Gradient backgrounds with marketing headline/subheadline overlays
- AI-generated captions via OpenAI (optional)
- Capture screenshots directly from iOS Simulator
- Auto-scales to all required App Store & Play Store sizes
- Upload to App Store Connect and Google Play via fastlane
- Fully configurable per-project via `screenshot_project.json`

![Screenshot Composer UI](docs/screenshot-composer-ui.png)

---

## Quick Start

### 1. Copy files into your Flutter project

```bash
# From your Flutter project root:
curl -sL https://github.com/kaushiksa/flutter-screenshot-composer/archive/main.tar.gz | tar xz --strip-components=1

# Or clone and copy:
git clone https://github.com/kaushiksa/flutter-screenshot-composer.git /tmp/fsc
cp /tmp/fsc/compose_screenshots.py .
cp /tmp/fsc/take_screenshots.sh .
cp /tmp/fsc/test_driver/screenshot_driver.dart test_driver/
cp /tmp/fsc/integration_test/screenshot_test_template.dart integration_test/screenshot_test.dart
```

### 2. Install Python dependencies

```bash
pip install Pillow numpy
# Optional: for AI-generated captions
pip install openai
```

### 3. Create your project config

Create `screenshot_project.json` in your Flutter project root:

```json
{
  "app_name": "My App",
  "app_description": "a mobile app that does amazing things",
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
  "captions": {
    "01_home": {
      "headline": "Welcome Home",
      "subheadline": "Everything you need, at a glance"
    },
    "02_search": {
      "headline": "Find Anything Fast",
      "subheadline": "Search across all your content"
    },
    "03_profile": {
      "headline": "Your Profile, Your Way",
      "subheadline": "Customize your experience"
    }
  },
  "capture": {
    "ipad_simulator": "iPad Pro 13-inch (M5)",
    "iphone_simulator": "iPhone 17 Pro Max"
  }
}
```

### 4. Add screenshots

Either:
- **Manual:** Drop raw PNG screenshots into `screenshots/iPhone 6.7-inch/` and `screenshots/iPad Pro 13-inch/`
- **Automated:** Set up the Flutter integration test (see [Automated Capture](#automated-capture) below)

### 5. Launch the composer

```bash
python compose_screenshots.py
```

Opens a browser UI at `http://localhost:8234` where you can:
- Preview composed screenshots in real-time
- Adjust gradients, captions, typography, and layout
- Generate all composed screenshots
- Upload directly to App Store / Play Store

---

## How It Works

```
Raw Screenshots    -->    Compose    -->    Upload
(from simulator)       (add backgrounds,   (to App Store /
                        captions, styling)   Play Store)
```

### Files

| File | Purpose |
|------|---------|
| `compose_screenshots.py` | Main tool - preview UI, composition engine, upload |
| `take_screenshots.sh` | Automated capture from iOS Simulator |
| `screenshot_project.json` | Your project config (app name, screens, colors, captions) |
| `screenshot_config.json` | Layout config (auto-generated, tweakable via UI) |
| `screenshot_captions.json` | Captions (auto-generated or AI-generated) |
| `test_driver/screenshot_driver.dart` | Flutter driver that saves screenshots to disk |
| `integration_test/screenshot_test.dart` | Your app-specific navigation test |

### Directory Structure

```
your_flutter_project/
  compose_screenshots.py
  take_screenshots.sh
  screenshot_project.json          # Your project config
  screenshot_config.json           # Auto-generated layout config
  screenshot_captions.json         # Auto-generated captions
  test_driver/
    screenshot_driver.dart         # Generic - works as-is
  integration_test/
    screenshot_test.dart           # Customize for your app
  screenshots/
    iPhone 6.7-inch/               # Raw screenshots (1290x2796)
      01_home.png
      02_search.png
    iPad Pro 13-inch/              # Raw screenshots (2064x2752)
      01_home.png
      02_search.png
    composed/                      # Output (auto-generated)
      iPhone 6.7-inch/
      iPad Pro 13-inch/
      iPhone 6.5-inch/             # Auto-scaled
      iPhone 5.5-inch/             # Auto-scaled
      Phone/                       # Play Store (1080x1920)
```

---

## Detailed Guide

### Project Config (`screenshot_project.json`)

All fields are optional. The tool auto-detects what it can.

```json
{
  "app_name": "My App",
  "app_description": "Short description for AI caption generation",
  "screens": [
    {"key": "01_home", "label": "Home"}
  ],
  "devices": {
    "iPhone 6.7-inch": {
      "width": 1320, "height": 2868,
      "screenshot_scale": 0.82, "corner_radius": 80,
      "text_area_ratio": 0.22,
      "headline_size": 72, "subheadline_size": 36,
      "padding_top": 140, "line_gap": 30
    }
  },
  "gradients": {
    "01_home": ["#2563EB", "#1E40AF"]
  },
  "captions": {
    "01_home": {"headline": "...", "subheadline": "..."}
  },
  "capture": {
    "ipad_simulator": "iPad Pro 13-inch (M5)",
    "iphone_simulator": "iPhone 17 Pro Max"
  }
}
```

**Without a project config**, the tool will:
- Auto-detect screens from PNGs in `screenshots/` subfolders
- Use default device sizes (iPhone 6.7" and iPad 13")
- Auto-assign gradient colors from a built-in palette
- Use filenames as labels (e.g. `01_home.png` -> "Home")

### Automated Capture

#### 1. Customize the screenshot test

Copy the template and fill in the TODOs:

```bash
cp integration_test/screenshot_test_template.dart integration_test/screenshot_test.dart
```

Edit `screenshot_test.dart` to:
- Import your app's packages
- Define your screen list (routes + filenames)
- Initialize your app (Firebase, etc.)
- Set up authentication if needed
- Navigate to each screen

#### 2. Run capture

From the browser UI, click **"Capture from Simulator"**, or from the terminal:

```bash
./take_screenshots.sh           # All devices (iPad + iPhone)
./take_screenshots.sh iphone    # iPhone only
./take_screenshots.sh ipad      # iPad only
./take_screenshots.sh --clean   # Remove all screenshots
```

### Compose via CLI (no UI)

```bash
# Generate all composed screenshots directly
python compose_screenshots.py --no-preview

# Force AI caption regeneration
python compose_screenshots.py --regenerate-captions

# Use only config captions (no AI)
python compose_screenshots.py --no-ai

# Process specific device only
python compose_screenshots.py --iphone-only
python compose_screenshots.py --ipad-only
```

### Upload to Stores

The UI has **Upload iOS**, **Upload Android**, and **Upload Both** buttons.

This requires:
- **iOS:** fastlane configured in `ios/fastlane/` with an `upload_screenshots` lane
- **Android:** fastlane configured in `android/fastlane/` with an `upload_screenshots` lane
- An `upload_screenshots.sh` script in your project root

### AI Captions

Set `OPENAI_API_KEY` in your environment or in a `.env` file, then:
- Click **"Regenerate Captions"** in the UI, or
- Run `python compose_screenshots.py --regenerate-captions`

The AI uses your `app_name` and `app_description` from `screenshot_project.json` to generate relevant marketing copy.

---

## Auto-Generated Sizes

From iPhone 6.7" source screenshots, the tool automatically generates:

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
- **OpenAI Python SDK** (optional, for AI captions: `pip install openai`)
- **fastlane** (optional, for store uploads)

---

## Example

See the [example/](example/) directory for a sample `screenshot_project.json` from the Dhi finance app.

---

## License

MIT
