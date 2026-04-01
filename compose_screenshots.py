#!/usr/bin/env python3
"""
Compose App Store screenshots with marketing captions and styled backgrounds.

Reads raw screenshots from screenshots/{device}/, uses config from
screenshot_config.json, composites gradient background + text + rounded-corner
screenshot with shadow, and outputs to screenshots/composed/{device}/.

Usage:
    python compose_screenshots.py                        # Open preview UI, then generate
    python compose_screenshots.py --no-preview           # Generate directly (no UI)
    python compose_screenshots.py --regenerate-captions  # Generate fresh AI captions first
    python compose_screenshots.py --no-ai                # Use only hardcoded fallback captions
"""

import argparse
import io
import json
import os
import subprocess
import threading
import webbrowser
from functools import partial
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, unquote

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
FONT_PATH = SCRIPT_DIR / "fonts" / "Inter.ttc"
CAPTIONS_FILE = SCRIPT_DIR / "screenshot_captions.json"
CONFIG_FILE = SCRIPT_DIR / "screenshot_config.json"
PROJECT_FILE = SCRIPT_DIR / "screenshot_project.json"
PREVIEW_PORT = 8234

# Default device configs — used when no project config specifies devices
DEFAULT_DEVICE_CONFIGS = {
    "iPhone 6.7-inch": {
        "width": 1320,
        "height": 2868,
        "screenshot_scale": 0.82,
        "corner_radius": 80,
        "text_area_ratio": 0.22,
        "headline_size": 72,
        "subheadline_size": 36,
        "padding_top": 140,
        "line_gap": 30,
    },
    "iPad Pro 13-inch": {
        "width": 2064,
        "height": 2752,
        "screenshot_scale": 0.85,
        "corner_radius": 40,
        "text_area_ratio": 0.20,
        "headline_size": 90,
        "subheadline_size": 48,
        "padding_top": 120,
        "line_gap": 36,
    },
}

# A palette of gradients to auto-assign to discovered screens
GRADIENT_PALETTE = [
    ("#2563EB", "#1E40AF"),
    ("#7C3AED", "#5B21B6"),
    ("#0D9488", "#0F766E"),
    ("#3B82F6", "#7C3AED"),
    ("#10B981", "#059669"),
    ("#14B8A6", "#0D9488"),
    ("#F59E0B", "#D97706"),
    ("#EF4444", "#DC2626"),
    ("#8B5CF6", "#6D28D9"),
    ("#EC4899", "#DB2777"),
]


def load_project_config() -> dict:
    """Load project-level config from screenshot_project.json if it exists."""
    if PROJECT_FILE.exists():
        return json.loads(PROJECT_FILE.read_text())
    return {}


def discover_screens() -> list[tuple[str, str]]:
    """Auto-detect screens from PNG files in screenshots/ subfolders."""
    screenshots_dir = SCRIPT_DIR / "screenshots"
    if not screenshots_dir.exists():
        return []
    found = set()
    for device_dir in screenshots_dir.iterdir():
        if device_dir.is_dir() and device_dir.name != "composed":
            for png in device_dir.glob("*.png"):
                found.add(png.stem)
    # Sort by name (files like 01_home, 02_networth sort naturally)
    sorted_keys = sorted(found)
    # Convert key to label: "01_home" -> "Home", "settings" -> "Settings"
    screens = []
    for key in sorted_keys:
        # Strip leading number prefix if present (e.g. "01_home" -> "home")
        parts = key.split("_", 1)
        if len(parts) == 2 and parts[0].isdigit():
            label = parts[1].replace("_", " ").title()
        else:
            label = key.replace("_", " ").title()
        screens.append((key, label))
    return screens


def get_screens(project_config: dict) -> list[tuple[str, str]]:
    """Get screens list: from project config, or auto-discovered, or empty."""
    if "screens" in project_config:
        return [(s["key"], s["label"]) for s in project_config["screens"]]
    discovered = discover_screens()
    if discovered:
        return discovered
    return []


def get_default_gradients(screens: list[tuple[str, str]], project_config: dict) -> dict:
    """Get gradient mapping for screens."""
    if "gradients" in project_config:
        return {k: tuple(v) for k, v in project_config["gradients"].items()}
    # Auto-assign from palette
    return {key: GRADIENT_PALETTE[i % len(GRADIENT_PALETTE)] for i, (key, _) in enumerate(screens)}


def get_default_captions(screens: list[tuple[str, str]], project_config: dict) -> dict:
    """Get default captions for screens."""
    if "captions" in project_config:
        return project_config["captions"]
    return {key: {"headline": label, "subheadline": ""} for key, label in screens}


# These are resolved at load time by main() / load_config()
PROJECT_CONFIG = {}
SCREENS = []
DEFAULT_GRADIENTS = {}
DEFAULT_CAPTIONS = {}


# =============================================================================
# Helpers
# =============================================================================

def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def create_gradient(width: int, height: int, color_top: str, color_bottom: str) -> Image.Image:
    c1 = hex_to_rgb(color_top)
    c2 = hex_to_rgb(color_bottom)
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    for ch in range(3):
        arr[:, :, ch] = np.linspace(c1[ch], c2[ch], height, dtype=np.uint8)[:, np.newaxis]
    return Image.fromarray(arr, "RGB")


def get_font(size: int, weight: str = "bold") -> ImageFont.FreeTypeFont:
    indices = {"bold": 14, "semibold": 12, "medium": 10, "regular": 0}
    idx = indices.get(weight, 14)
    if FONT_PATH.exists():
        return ImageFont.truetype(str(FONT_PATH), size, index=idx)
    var_path = FONT_PATH.parent / "InterVariable.ttf"
    if var_path.exists():
        return ImageFont.truetype(str(var_path), size)
    sf_path = Path("/System/Library/Fonts/SFNS.ttf")
    if sf_path.exists():
        return ImageFont.truetype(str(sf_path), size)
    return ImageFont.load_default()


def apply_rounded_corners(image: Image.Image, radius: int) -> Image.Image:
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    w, h = image.size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=radius, fill=255)
    image.putalpha(mask)
    return image


def add_drop_shadow(image, canvas_size, position, shadow_offset=12, shadow_blur=30, shadow_opacity=60):
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    if image.mode == "RGBA":
        alpha = image.split()[3]
        shadow = Image.new("RGBA", image.size, (0, 0, 0, shadow_opacity))
        shadow.putalpha(alpha)
        canvas.paste(shadow, (position[0], position[1] + shadow_offset), shadow)
        canvas = canvas.filter(ImageFilter.GaussianBlur(shadow_blur))
    canvas.paste(image, position, image)
    return canvas


def render_text_centered(draw, text, y, canvas_width, font, fill=(255, 255, 255, 255), max_width_ratio=0.88):
    max_w = int(canvas_width * max_width_ratio)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    current_font = font
    current_size = font.size
    while text_w > max_w and current_size > 20:
        current_size -= 2
        current_font = get_font(current_size, "bold" if current_size > 50 else "medium")
        bbox = draw.textbbox((0, 0), text, font=current_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    x = (canvas_width - text_w) // 2
    draw.text((x, y), text, font=current_font, fill=fill)
    return text_h


# =============================================================================
# Caption Generation
# =============================================================================

def load_openai_key() -> str | None:
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    env_path = SCRIPT_DIR.parent / "backend" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("OPENAI_API_KEY="):
                return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def generate_captions_with_ai(api_key: str, screens: list[tuple[str, str]] = None,
                               project_config: dict = None) -> dict:
    print("  Calling OpenAI for caption generation...")
    client = OpenAI(api_key=api_key)
    screens = screens or SCREENS
    project_config = project_config or PROJECT_CONFIG

    app_name = project_config.get("app_name", "the app")
    app_description = project_config.get("app_description", "a mobile application")

    screen_list = "\n".join(
        f"{i+1}. {key} - {label}" for i, (key, label) in enumerate(screens)
    )
    screen_keys = ", ".join(key for key, _ in screens)

    prompt = f"""You are writing App Store screenshot captions for "{app_name}" — {app_description}.

Generate compelling marketing captions for these {len(screens)} screens. Each caption needs:
- headline: 4-7 words, punchy, benefit-focused, title case
- subheadline: 6-12 words, descriptive, supporting the headline

Screens:
{screen_list}

Requirements:
- Make users want to download immediately
- Each headline must be distinct (no repetitive patterns)
- Subheadlines should complement, not repeat, the headline
- Be approachable yet professional, avoid jargon

Return as JSON with keys: {screen_keys}. Each with "headline" and "subheadline"."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.8,
        max_tokens=800,
    )
    result = json.loads(response.choices[0].message.content)
    print("  Captions generated successfully")
    return result


# =============================================================================
# Config
# =============================================================================

def init_project():
    """Initialize global project state from config files and auto-discovery."""
    global PROJECT_CONFIG, SCREENS, DEFAULT_GRADIENTS, DEFAULT_CAPTIONS
    PROJECT_CONFIG = load_project_config()
    SCREENS = get_screens(PROJECT_CONFIG)
    DEFAULT_GRADIENTS = get_default_gradients(SCREENS, PROJECT_CONFIG)
    DEFAULT_CAPTIONS = get_default_captions(SCREENS, PROJECT_CONFIG)


def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    captions = DEFAULT_CAPTIONS
    if CAPTIONS_FILE.exists():
        captions = json.loads(CAPTIONS_FILE.read_text())
    else:
        api_key = load_openai_key()
        if api_key and OPENAI_AVAILABLE and SCREENS:
            captions = generate_captions_with_ai(api_key)
            CAPTIONS_FILE.write_text(json.dumps(captions, indent=2))
    return {
        "devices": PROJECT_CONFIG.get("devices", DEFAULT_DEVICE_CONFIGS),
        "gradients": {k: list(v) for k, v in DEFAULT_GRADIENTS.items()},
        "captions": captions,
    }


def save_config(config: dict):
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


# =============================================================================
# Core Compositing
# =============================================================================

def compose_screenshot(raw_path, screen_key, device_cfg, captions, gradients):
    W = device_cfg["width"]
    H = device_cfg["height"]
    grad_top, grad_bottom = gradients.get(screen_key, ("#2563EB", "#1E40AF"))
    canvas = create_gradient(W, H, grad_top, grad_bottom)

    caption = captions.get(screen_key, DEFAULT_CAPTIONS.get(screen_key, {}))
    headline = caption.get("headline", "")
    subheadline = caption.get("subheadline", "")

    text_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(text_layer)
    y = device_cfg["padding_top"]
    headline_font = get_font(device_cfg["headline_size"], "bold")
    h_height = render_text_centered(draw, headline, y, W, headline_font, fill=(255, 255, 255, 255))
    y += h_height + device_cfg["line_gap"]
    sub_font = get_font(device_cfg["subheadline_size"], "medium")
    render_text_centered(draw, subheadline, y, W, sub_font, fill=(255, 255, 255, 200))

    canvas = canvas.convert("RGBA")
    canvas = Image.alpha_composite(canvas, text_layer)

    raw = Image.open(raw_path).convert("RGBA")
    scale = device_cfg["screenshot_scale"]
    new_w = int(W * scale)
    new_h = int(raw.height * (new_w / raw.width))
    raw_scaled = raw.resize((new_w, new_h), Image.LANCZOS)
    raw_rounded = apply_rounded_corners(raw_scaled, device_cfg["corner_radius"])

    text_area_h = int(H * device_cfg["text_area_ratio"])
    gap = 40
    ss_x = (W - new_w) // 2
    ss_y = text_area_h + gap

    shadow_layer = add_drop_shadow(raw_rounded, (W, H), (ss_x, ss_y))
    canvas = Image.alpha_composite(canvas, shadow_layer)
    return canvas.convert("RGB")


def compose_preview(screen_key, config, device=None):
    """Compose a single screenshot and return JPEG bytes for preview."""
    devices = config.get("devices", DEFAULT_DEVICE_CONFIGS)
    gradients = config.get("gradients", DEFAULT_GRADIENTS)
    captions = config.get("captions", DEFAULT_CAPTIONS)

    # If device specified, use only that device; otherwise try all
    if device and device in devices:
        candidates = [(device, devices[device])]
    else:
        candidates = list(devices.items())

    for device_name, device_cfg in candidates:
        raw_path = SCRIPT_DIR / "screenshots" / device_name / f"{screen_key}.png"
        if raw_path.exists():
            img = compose_screenshot(raw_path, screen_key, device_cfg, captions, gradients)
            # Downscale for preview (max 600px wide)
            w, h = img.size
            preview_w = 600
            preview_h = int(h * (preview_w / w))
            img = img.resize((preview_w, preview_h), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=85)
            return buf.getvalue()
    return None


def _get_screen_files(input_dir: Path) -> list[tuple[str, str]]:
    """Get screen (key, label) pairs from actual files in a directory."""
    screens_dict = dict(SCREENS)
    found = []
    for png in sorted(input_dir.glob("*.png")):
        key = png.stem
        label = screens_dict.get(key, key.replace("_", " ").title())
        found.append((key, label))
    return found


def run_composition(config: dict, excluded: dict | None = None):
    devices = config.get("devices", DEFAULT_DEVICE_CONFIGS)
    gradients = config.get("gradients", DEFAULT_GRADIENTS)
    captions = config.get("captions", DEFAULT_CAPTIONS)
    excluded = excluded or {}
    results = []

    for device_name, device_cfg in devices.items():
        input_dir = SCRIPT_DIR / "screenshots" / device_name
        output_dir = SCRIPT_DIR / "screenshots" / "composed" / device_name
        output_dir.mkdir(parents=True, exist_ok=True)
        device_excluded = excluded.get(device_name, [])

        if not input_dir.exists():
            print(f"  Skipping {device_name} (no raw screenshots)")
            continue

        for screen_key, screen_label in _get_screen_files(input_dir):
            if screen_key in device_excluded:
                composed_path = output_dir / f"{screen_key}.png"
                if composed_path.exists():
                    composed_path.unlink()
                print(f"  {device_name} / {screen_label}: EXCLUDED")
                continue
            raw_path = input_dir / f"{screen_key}.png"
            final = compose_screenshot(raw_path, screen_key, device_cfg, captions, gradients)
            assert final.size == (device_cfg["width"], device_cfg["height"])
            output_path = output_dir / f"{screen_key}.png"
            final.save(output_path, "PNG")
            results.append(f"{device_name}/{screen_key}.png ({final.size[0]}x{final.size[1]})")
            print(f"  {device_name} / {screen_label}: {final.size[0]}x{final.size[1]}")

    # Auto-generate scaled App Store sizes from iPhone source
    iphone_src = None
    for name in devices:
        candidate = SCRIPT_DIR / "screenshots" / "composed" / name
        if "iPhone" in name and candidate.exists():
            iphone_src = candidate
            break

    if iphone_src and iphone_src.exists():
        SCALED_SIZES = {
            "iPhone 6.5-inch": (1284, 2778),
            "iPhone 5.5-inch": (1242, 2208),
        }
        for size_name, (tw, th) in SCALED_SIZES.items():
            out_dir = SCRIPT_DIR / "screenshots" / "composed" / size_name
            out_dir.mkdir(parents=True, exist_ok=True)
            for src in sorted(iphone_src.glob("*.png")):
                img = Image.open(src)
                scaled = img.resize((tw, th), Image.LANCZOS)
                scaled.save(out_dir / src.name, "PNG")
                results.append(f"{size_name}/{src.name} ({tw}x{th})")
            print(f"  {size_name}: scaled {len(list(out_dir.glob('*.png')))} screenshots ({tw}x{th})")

    # Auto-generate Play Store phone screenshots (1080x1920, 9:16)
    if iphone_src and iphone_src.exists():
        play_dir = SCRIPT_DIR / "screenshots" / "composed" / "Phone"
        play_dir.mkdir(parents=True, exist_ok=True)
        play_w, play_h = 1080, 1920
        for src in sorted(iphone_src.glob("*.png")):
            img = Image.open(src)
            src_w, src_h = img.size
            target_ratio = play_w / play_h
            src_ratio = src_w / src_h
            if src_ratio > target_ratio:
                new_h = src_h
                new_w = int(src_h * target_ratio)
                left = (src_w - new_w) // 2
                img = img.crop((left, 0, left + new_w, new_h))
            else:
                new_w = src_w
                new_h = int(src_w / target_ratio)
                img = img.crop((0, 0, new_w, new_h))
            scaled = img.resize((play_w, play_h), Image.LANCZOS)
            scaled.save(play_dir / src.name, "PNG")
            results.append(f"Phone/{src.name} ({play_w}x{play_h})")
        print(f"  Phone (Play Store): scaled {len(list(play_dir.glob('*.png')))} screenshots ({play_w}x{play_h})")

    return results


def run_composition_streaming(config: dict, send_progress=None):
    """Like run_composition but sends SSE progress events."""
    devices = config.get("devices", DEFAULT_DEVICE_CONFIGS)
    gradients = config.get("gradients", DEFAULT_GRADIENTS)
    captions = config.get("captions", DEFAULT_CAPTIONS)
    results = []

    for device_name, device_cfg in devices.items():
        input_dir = SCRIPT_DIR / "screenshots" / device_name
        output_dir = SCRIPT_DIR / "screenshots" / "composed" / device_name
        output_dir.mkdir(parents=True, exist_ok=True)

        if not input_dir.exists():
            continue

        for screen_key, screen_label in _get_screen_files(input_dir):
            raw_path = input_dir / f"{screen_key}.png"
            if send_progress:
                send_progress({"type": "progress", "message": f"Composing {device_name} / {screen_label}..."})
            final = compose_screenshot(raw_path, screen_key, device_cfg, captions, gradients)
            output_path = output_dir / f"{screen_key}.png"
            final.save(output_path, "PNG")
            results.append(f"{device_name}/{screen_key}.png ({final.size[0]}x{final.size[1]})")
            print(f"  {device_name} / {screen_label}: {final.size[0]}x{final.size[1]}")

    # Auto-generate scaled App Store sizes
    iphone_src = None
    for name in devices:
        candidate = SCRIPT_DIR / "screenshots" / "composed" / name
        if "iPhone" in name and candidate.exists():
            iphone_src = candidate
            break

    if iphone_src and iphone_src.exists():
        SCALED_SIZES = {
            "iPhone 6.5-inch": (1284, 2778),
            "iPhone 5.5-inch": (1242, 2208),
        }
        for size_name, (tw, th) in SCALED_SIZES.items():
            if send_progress:
                send_progress({"type": "progress", "message": f"Scaling {size_name} ({tw}x{th})..."})
            out_dir = SCRIPT_DIR / "screenshots" / "composed" / size_name
            out_dir.mkdir(parents=True, exist_ok=True)
            for src in sorted(iphone_src.glob("*.png")):
                img = Image.open(src)
                scaled = img.resize((tw, th), Image.LANCZOS)
                scaled.save(out_dir / src.name, "PNG")
                results.append(f"{size_name}/{src.name} ({tw}x{th})")

    # Auto-generate Play Store phone screenshots (1080x1920, 9:16)
    if iphone_src and iphone_src.exists():
        play_w, play_h = 1080, 1920
        if send_progress:
            send_progress({"type": "progress", "message": f"Scaling Play Store phone ({play_w}x{play_h})..."})
        play_dir = SCRIPT_DIR / "screenshots" / "composed" / "Phone"
        play_dir.mkdir(parents=True, exist_ok=True)
        for src in sorted(iphone_src.glob("*.png")):
            img = Image.open(src)
            src_w, src_h = img.size
            target_ratio = play_w / play_h
            src_ratio = src_w / src_h
            if src_ratio > target_ratio:
                new_h = src_h
                new_w = int(src_h * target_ratio)
                left = (src_w - new_w) // 2
                img = img.crop((left, 0, left + new_w, new_h))
            else:
                new_w = src_w
                new_h = int(src_w / target_ratio)
                img = img.crop((0, 0, new_w, new_h))
            scaled = img.resize((play_w, play_h), Image.LANCZOS)
            scaled.save(play_dir / src.name, "PNG")
            results.append(f"Phone/{src.name} ({play_w}x{play_h})")

    return results


# =============================================================================
# Preview Web UI — server-side rendered previews (PIL, not canvas)
# =============================================================================

PREVIEW_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__APP_NAME__ — Screenshot Composer</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif; background: #0f0f0f; color: #e5e5e5; }
  .header { padding: 14px 24px; background: #1a1a1a; border-bottom: 1px solid #333; display: flex; align-items: center; justify-content: space-between; }
  .header h1 { font-size: 16px; font-weight: 600; }
  .header .actions { display: flex; gap: 8px; }
  .btn { padding: 8px 16px; border: none; border-radius: 8px; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.15s; }
  .btn-secondary { background: #333; color: #e5e5e5; }
  .btn-secondary:hover { background: #444; }
  .btn-green { background: #059669; color: white; }
  .btn-green:hover { background: #047857; }
  .btn-red { background: #444; color: #999; }
  .btn-red:hover { background: #555; color: #ccc; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .main { display: flex; height: calc(100vh - 53px - 36px); }
  .sidebar { width: 320px; background: #1a1a1a; border-right: 1px solid #333; overflow-y: auto; padding: 14px; flex-shrink: 0; }
  .preview-area { flex: 1; display: flex; align-items: center; justify-content: center; overflow: auto; padding: 20px; background: #111; position: relative; }
  .preview-area img { max-height: calc(100vh - 130px); max-width: 100%; border-radius: 10px; box-shadow: 0 8px 32px rgba(0,0,0,0.5); }
  .preview-area .loading { color: #666; font-size: 14px; }
  .nav-arrow { position: absolute; top: 50%; transform: translateY(-50%); background: rgba(255,255,255,0.08); border: 1px solid #444; color: #aaa; width: 36px; height: 60px; border-radius: 8px; cursor: pointer; font-size: 18px; display: flex; align-items: center; justify-content: center; transition: all 0.15s; }
  .nav-arrow:hover { background: rgba(255,255,255,0.15); color: #fff; }
  .nav-arrow.left { left: 8px; }
  .nav-arrow.right { right: 8px; }
  .section { margin-bottom: 16px; }
  .section-title { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: #555; margin-bottom: 8px; }
  .tabs { display: flex; gap: 4px; margin-bottom: 10px; }
  .tab { padding: 6px 14px; border-radius: 6px; font-size: 12px; cursor: pointer; background: #262626; border: 1px solid #333; color: #888; transition: all 0.15s; }
  .tab.active { background: #2563EB; color: white; border-color: #2563EB; }
  .screen-tabs { display: flex; flex-wrap: wrap; gap: 3px; margin-bottom: 10px; }
  .screen-tab { padding: 5px 9px; border-radius: 6px; font-size: 11px; cursor: pointer; background: #262626; border: 1px solid #333; color: #888; transition: all 0.15s; }
  .screen-tab.active { background: #7C3AED; color: white; border-color: #7C3AED; }
  .screen-tab.unavailable { opacity: 0.35; cursor: default; }
  .control { margin-bottom: 12px; }
  .control label { display: flex; justify-content: space-between; font-size: 11px; color: #888; margin-bottom: 3px; }
  .control label .val { color: #2563EB; font-weight: 600; font-variant-numeric: tabular-nums; }
  .control input[type=range] { width: 100%; accent-color: #2563EB; height: 16px; }
  .control input[type=text] { width: 100%; padding: 6px 9px; border-radius: 6px; border: 1px solid #333; background: #262626; color: #e5e5e5; font-size: 12px; }
  .control input[type=text]:focus { border-color: #2563EB; outline: none; }
  .color-row { display: flex; gap: 6px; align-items: center; }
  .color-row input[type=color] { width: 36px; height: 28px; padding: 2px; border-radius: 6px; cursor: pointer; border: 1px solid #333; }
  .color-row input[type=text] { flex: 1; }
  .status { padding: 8px 20px; background: #1a1a1a; border-top: 1px solid #333; font-size: 11px; color: #555; text-align: center; }
  .status.success { color: #10B981; }
  .status.working { color: #F59E0B; }
  .status.error { color: #EF4444; }
  .shortcut-hint { font-size: 10px; color: #444; margin-left: 6px; }
</style>
</head>
<body>
<div class="header">
  <h1>__APP_NAME__ — Screenshot Composer</h1>
  <div class="actions">
    <button class="btn btn-red" onclick="resetDefaults()">Reset</button>
    <button class="btn btn-secondary" onclick="saveConfig()">Save Config</button>
    <button class="btn btn-secondary" onclick="updatePreview()">Refresh <span class="shortcut-hint">Enter</span></button>
    <button class="btn" id="captureBtn" onclick="captureScreenshots()" style="background:#F59E0B; color:#1a1a1a; font-weight:700;">Capture from Simulator</button>
    <button class="btn btn-green" id="generateBtn" onclick="generateAll()">Generate All</button>
    <button class="btn btn-secondary" id="uploadIosBtn" onclick="uploadScreenshots('ios')" style="background:#7C3AED; color:white;">Upload iOS</button>
    <button class="btn btn-secondary" id="uploadAndroidBtn" onclick="uploadScreenshots('android')" style="background:#3DDC84; color:#1a1a1a;">Upload Android</button>
    <button class="btn btn-secondary" id="uploadBothBtn" onclick="uploadScreenshots('both')" style="background:#2563EB; color:white;">Upload Both</button>
  </div>
</div>
<div class="main">
  <div class="sidebar">
    <div class="section">
      <div class="section-title">Device</div>
      <div class="tabs" id="deviceTabs"></div>
    </div>
    <div class="section">
      <div class="section-title">Screen <span class="shortcut-hint" style="float:right">arrow keys</span></div>
      <div class="screen-tabs" id="screenTabs"></div>
      <button class="btn btn-red" id="removeScreenBtn" onclick="removeScreen()" style="margin-top:6px; font-size:11px; padding:5px 10px;">Delete This Screen</button>
    </div>
    <div class="section">
      <div class="section-title">Caption</div>
      <div class="control">
        <label>Headline</label>
        <input type="text" id="headline" onchange="updatePreview()">
      </div>
      <div class="control">
        <label>Subheadline</label>
        <input type="text" id="subheadline" onchange="updatePreview()">
      </div>
    </div>
    <div class="section">
      <div class="section-title">Typography</div>
      <div class="control">
        <label>Headline Size <span class="val" id="headlineSizeVal"></span></label>
        <input type="range" id="headlineSize" min="40" max="140">
      </div>
      <div class="control">
        <label>Subheadline Size <span class="val" id="subheadlineSizeVal"></span></label>
        <input type="range" id="subheadlineSize" min="20" max="80">
      </div>
      <div class="control">
        <label>Top Padding <span class="val" id="paddingTopVal"></span></label>
        <input type="range" id="paddingTop" min="40" max="300">
      </div>
      <div class="control">
        <label>Line Gap <span class="val" id="lineGapVal"></span></label>
        <input type="range" id="lineGap" min="5" max="80">
      </div>
    </div>
    <div class="section">
      <div class="section-title">Screenshot</div>
      <div class="control">
        <label>Scale <span class="val" id="screenshotScaleVal"></span></label>
        <input type="range" id="screenshotScale" min="50" max="100">
      </div>
      <div class="control">
        <label>Corner Radius <span class="val" id="cornerRadiusVal"></span></label>
        <input type="range" id="cornerRadius" min="0" max="120">
      </div>
      <div class="control">
        <label>Text Area <span class="val" id="textAreaRatioVal"></span></label>
        <input type="range" id="textAreaRatio" min="10" max="40">
      </div>
    </div>
    <div class="section">
      <div class="section-title">Gradient</div>
      <div class="control">
        <label>Top</label>
        <div class="color-row">
          <input type="color" id="gradTop" onchange="syncGradHex(); updatePreview()">
          <input type="text" id="gradTopHex" onchange="syncGradPicker(); updatePreview()" placeholder="#2563EB">
        </div>
      </div>
      <div class="control">
        <label>Bottom</label>
        <div class="color-row">
          <input type="color" id="gradBottom" onchange="syncGradHex(); updatePreview()">
          <input type="text" id="gradBottomHex" onchange="syncGradPicker(); updatePreview()" placeholder="#1E40AF">
        </div>
      </div>
    </div>
  </div>
  <div class="preview-area" id="previewArea">
    <button class="nav-arrow left" onclick="prevScreen()">&lsaquo;</button>
    <div class="loading">Loading preview...</div>
    <button class="nav-arrow right" onclick="nextScreen()">&rsaquo;</button>
  </div>
</div>
<div class="status" id="status">Adjust settings, then click Generate All. Enter=refresh, Arrow keys=navigate screens.</div>

<script>
let config = null;
let currentDevice = null;
let currentScreen = null;
let availableScreens = {};
let SCREENS_LIST = __SCREENS_JSON__;
const DEFAULT_CONFIG = __DEFAULT_CONFIG_JSON__;

async function init() {
  const resp = await fetch('/api/config');
  config = await resp.json();
  // Check which screens have raw screenshots
  const avResp = await fetch('/api/available');
  availableScreens = await avResp.json();
  // Merge discovered screens into SCREENS_LIST
  const knownKeys = new Set(SCREENS_LIST.map(s => s[0]));
  for (const [device, keys] of Object.entries(availableScreens)) {
    for (const key of keys) {
      if (!knownKeys.has(key)) {
        const parts = key.split('_');
        const label = parts.length > 1 && /^\\d+$/.test(parts[0])
          ? parts.slice(1).map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
          : key.replace(/_/g, ' ').replace(/\\b\\w/g, c => c.toUpperCase());
        SCREENS_LIST.push([key, label]);
        knownKeys.add(key);
      }
    }
  }
  SCREENS_LIST.sort((a, b) => a[0].localeCompare(b[0]));
  // Default to first device that has screenshots
  const names = Object.keys(config.devices);
  currentDevice = names.find(n => availableScreens[n] && availableScreens[n].length > 0) || names[names.length - 1];
  // Default to first available screen
  const firstAvail = availableScreens[currentDevice] || [];
  currentScreen = firstAvail[0] || (SCREENS_LIST[0] && SCREENS_LIST[0][0]) || null;
  buildDeviceTabs();
  buildScreenTabs();
  syncUI();
  updatePreview();
}

function buildDeviceTabs() {
  const el = document.getElementById('deviceTabs');
  el.innerHTML = '';
  for (const name of Object.keys(config.devices)) {
    const tab = document.createElement('div');
    const shortName = name.includes('iPad') ? 'iPad' : 'iPhone';
    const count = (availableScreens[name] || []).length;
    tab.className = 'tab' + (name === currentDevice ? ' active' : '');
    tab.textContent = shortName + (count > 0 ? ' (' + count + ')' : '');
    if (count === 0) tab.style.opacity = '0.5';
    tab.onclick = () => { currentDevice = name; buildDeviceTabs(); buildScreenTabs(); syncUI(); updatePreview(); };
    el.appendChild(tab);
  }
}

function buildScreenTabs() {
  const el = document.getElementById('screenTabs');
  el.innerHTML = '';
  const avail = availableScreens[currentDevice] || [];
  for (const [key, label] of SCREENS_LIST) {
    const tab = document.createElement('div');
    const hasScreenshot = avail.includes(key);
    tab.className = 'screen-tab' + (key === currentScreen ? ' active' : '');
    if (!hasScreenshot) tab.style.opacity = '0.35';
    tab.textContent = label;
    tab.onclick = () => { currentScreen = key; buildScreenTabs(); syncUI(); updatePreview(); };
    el.appendChild(tab);
  }
  // Show/hide remove button based on whether screenshot exists
  const btn = document.getElementById('removeScreenBtn');
  btn.style.display = avail.includes(currentScreen) ? '' : 'none';
}

function syncUI() {
  const dc = config.devices[currentDevice];
  const cap = (config.captions || {})[currentScreen] || {};
  const grad = (config.gradients || {})[currentScreen] || ['#2563EB', '#1E40AF'];

  document.getElementById('headline').value = cap.headline || '';
  document.getElementById('subheadline').value = cap.subheadline || '';
  setSlider('headlineSize', dc.headline_size);
  setSlider('subheadlineSize', dc.subheadline_size);
  setSlider('paddingTop', dc.padding_top);
  setSlider('lineGap', dc.line_gap);
  setSlider('screenshotScale', Math.round(dc.screenshot_scale * 100));
  setSlider('cornerRadius', dc.corner_radius);
  setSlider('textAreaRatio', Math.round(dc.text_area_ratio * 100));
  document.getElementById('gradTop').value = grad[0];
  document.getElementById('gradTopHex').value = grad[0];
  document.getElementById('gradBottom').value = grad[1];
  document.getElementById('gradBottomHex').value = grad[1];
  updateSliderLabels();
}

function setSlider(id, val) { document.getElementById(id).value = val; }

function updateSliderLabels() {
  document.getElementById('headlineSizeVal').textContent = document.getElementById('headlineSize').value;
  document.getElementById('subheadlineSizeVal').textContent = document.getElementById('subheadlineSize').value;
  document.getElementById('paddingTopVal').textContent = document.getElementById('paddingTop').value;
  document.getElementById('lineGapVal').textContent = document.getElementById('lineGap').value;
  document.getElementById('screenshotScaleVal').textContent = document.getElementById('screenshotScale').value + '%';
  document.getElementById('cornerRadiusVal').textContent = document.getElementById('cornerRadius').value;
  document.getElementById('textAreaRatioVal').textContent = document.getElementById('textAreaRatio').value + '%';
}

function readUI() {
  const dc = config.devices[currentDevice];
  dc.headline_size = parseInt(document.getElementById('headlineSize').value);
  dc.subheadline_size = parseInt(document.getElementById('subheadlineSize').value);
  dc.padding_top = parseInt(document.getElementById('paddingTop').value);
  dc.line_gap = parseInt(document.getElementById('lineGap').value);
  dc.screenshot_scale = parseInt(document.getElementById('screenshotScale').value) / 100;
  dc.corner_radius = parseInt(document.getElementById('cornerRadius').value);
  dc.text_area_ratio = parseInt(document.getElementById('textAreaRatio').value) / 100;

  if (!config.captions) config.captions = {};
  if (!config.captions[currentScreen]) config.captions[currentScreen] = {};
  config.captions[currentScreen].headline = document.getElementById('headline').value;
  config.captions[currentScreen].subheadline = document.getElementById('subheadline').value;

  if (!config.gradients) config.gradients = {};
  config.gradients[currentScreen] = [
    document.getElementById('gradTop').value,
    document.getElementById('gradBottom').value
  ];
  updateSliderLabels();
}

function syncGradHex() {
  document.getElementById('gradTopHex').value = document.getElementById('gradTop').value;
  document.getElementById('gradBottomHex').value = document.getElementById('gradBottom').value;
}
function syncGradPicker() {
  const top = document.getElementById('gradTopHex').value;
  const bottom = document.getElementById('gradBottomHex').value;
  if (/^#[0-9a-fA-F]{6}$/.test(top)) document.getElementById('gradTop').value = top;
  if (/^#[0-9a-fA-F]{6}$/.test(bottom)) document.getElementById('gradBottom').value = bottom;
}

// Screen navigation
function getAvailableScreenKeys() {
  return (availableScreens[currentDevice] || []);
}
function prevScreen() {
  const keys = getAvailableScreenKeys();
  if (keys.length === 0) return;
  const idx = keys.indexOf(currentScreen);
  currentScreen = keys[(idx - 1 + keys.length) % keys.length];
  buildScreenTabs(); syncUI(); updatePreview();
}
function nextScreen() {
  const keys = getAvailableScreenKeys();
  if (keys.length === 0) return;
  const idx = keys.indexOf(currentScreen);
  currentScreen = keys[(idx + 1) % keys.length];
  buildScreenTabs(); syncUI(); updatePreview();
}

// Debounced preview on slider drag
let debounceTimer = null;
function debouncedPreview() {
  readUI();
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(updatePreview, 400);
}

// Server-side rendered preview
let previewCounter = 0;
async function updatePreview() {
  readUI();
  const myCount = ++previewCounter;
  setStatus('Rendering...', 'working');
  try {
    const resp = await fetch('/api/preview', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ screen: currentScreen, device: currentDevice, config: config }),
    });
    if (myCount !== previewCounter) return;
    if (!resp.ok) { setStatus('No screenshot for this screen/device', 'error'); return; }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const area = document.getElementById('previewArea');
    // Preserve nav arrows
    area.innerHTML = '<button class="nav-arrow left" onclick="prevScreen()">&lsaquo;</button>'
      + '<img src="' + url + '" alt="Preview">'
      + '<button class="nav-arrow right" onclick="nextScreen()">&rsaquo;</button>';
    setStatus(currentDevice + ' / ' + currentScreen, '');
  } catch (e) {
    if (myCount === previewCounter) setStatus('Error: ' + e.message, 'error');
  }
}

async function generateAll() {
  readUI();
  const btn = document.getElementById('generateBtn');
  btn.disabled = true; btn.textContent = 'Generating...';
  setStatus('Generating all screenshots...', 'working');
  try {
    const resp = await fetch('/api/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(config),
    });
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let lastResult = null;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const msg = JSON.parse(line.slice(6));
            if (msg.type === 'progress') setStatus(msg.message, 'working');
            else if (msg.type === 'done') { lastResult = msg; setStatus('Done! ' + msg.count + ' screenshots generated', 'success'); }
            else if (msg.type === 'error') setStatus('Error: ' + msg.message, 'error');
          } catch(e) {}
        }
      }
    }
    if (!lastResult) setStatus('Generation completed', 'success');
  } catch (e) { setStatus('Error: ' + e.message, 'error'); }
  btn.disabled = false; btn.textContent = 'Generate All';
}

async function saveConfig() {
  readUI();
  try {
    const resp = await fetch('/api/save-config', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(config),
    });
    const result = await resp.json();
    if (result.success) setStatus('Config saved to screenshot_config.json', 'success');
    else setStatus('Save failed: ' + (result.error || 'Unknown'), 'error');
  } catch (e) { setStatus('Save error: ' + e.message, 'error'); }
}

function resetDefaults() {
  if (!confirm('Reset all settings to defaults?')) return;
  config.devices = JSON.parse(JSON.stringify(DEFAULT_CONFIG.devices));
  config.gradients = JSON.parse(JSON.stringify(DEFAULT_CONFIG.gradients));
  // Keep current captions (AI-generated)
  buildDeviceTabs(); syncUI(); updatePreview();
  setStatus('Reset to defaults', 'success');
}

function setStatus(msg, cls) {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.className = 'status ' + (cls || '');
}

// Live label updates + debounced preview while dragging sliders
document.addEventListener('input', function(e) {
  if (e.target.type === 'range') { updateSliderLabels(); debouncedPreview(); }
});

// Keyboard shortcuts
document.addEventListener('keydown', function(e) {
  if (e.target.tagName === 'INPUT' && e.target.type === 'text') {
    if (e.key === 'Enter') { e.target.blur(); updatePreview(); }
    return;
  }
  if (e.key === 'ArrowLeft') { e.preventDefault(); prevScreen(); }
  else if (e.key === 'ArrowRight') { e.preventDefault(); nextScreen(); }
  else if (e.key === 'Enter') { e.preventDefault(); updatePreview(); }
});

async function uploadScreenshots(target) {
  const labels = { ios: 'App Store Connect', android: 'Google Play Store', both: 'App Store + Play Store' };
  const label = labels[target] || target;
  if (!confirm('Generate + Upload screenshots to ' + label + '?')) return;
  readUI();
  const btns = ['uploadIosBtn', 'uploadAndroidBtn', 'uploadBothBtn', 'generateBtn'];
  btns.forEach(id => { document.getElementById(id).disabled = true; });
  setStatus('Generating + uploading to ' + label + '...', 'working');
  try {
    const payload = Object.assign({}, config, { upload_target: target });
    const resp = await fetch('/api/upload', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const msg = JSON.parse(line.slice(6));
            if (msg.type === 'progress') setStatus(msg.message, 'working');
            else if (msg.type === 'done') setStatus('Upload complete! Check ' + label + '.', 'success');
            else if (msg.type === 'error') setStatus('Error: ' + msg.message, 'error');
          } catch(e) {}
        }
      }
    }
  } catch (e) { setStatus('Upload error: ' + e.message, 'error'); }
  btns.forEach(id => { document.getElementById(id).disabled = false; });
}

async function removeScreen() {
  const screenLabel = SCREENS_LIST.find(s => s[0] === currentScreen)?.[1] || currentScreen;
  if (!confirm('Delete "' + screenLabel + '" screenshot for ' + currentDevice + '?\\n\\nThe raw screenshot file will be permanently deleted.')) return;
  try {
    const resp = await fetch('/api/delete-screen', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ device: currentDevice, screen: currentScreen }),
    });
    const result = await resp.json();
    if (result.success) {
      // Refresh available screens list
      const avResp = await fetch('/api/available');
      availableScreens = await avResp.json();
      buildDeviceTabs(); buildScreenTabs();
      setStatus('Deleted ' + screenLabel + ' from ' + currentDevice, 'success');
      updatePreview();
    } else {
      setStatus('Delete failed: ' + (result.error || 'Unknown'), 'error');
    }
  } catch (e) { setStatus('Delete error: ' + e.message, 'error'); }
}

async function captureScreenshots() {
  const target = prompt('Capture from which device?\\n\\n1. all (iPad + iPhone)\\n2. ipad\\n3. iphone\\n\\nType: all, ipad, or iphone', 'all');
  if (!target || !['all', 'ipad', 'iphone'].includes(target.toLowerCase())) return;
  const btn = document.getElementById('captureBtn');
  const allBtns = ['captureBtn', 'generateBtn', 'uploadIosBtn', 'uploadAndroidBtn', 'uploadBothBtn'];
  allBtns.forEach(id => { const b = document.getElementById(id); if (b) b.disabled = true; });
  btn.textContent = 'Capturing...';
  setStatus('Launching simulator and capturing screenshots...', 'working');
  try {
    const resp = await fetch('/api/capture', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ target: target.toLowerCase() }),
    });
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const msg = JSON.parse(line.slice(6));
            if (msg.type === 'progress') setStatus(msg.message, 'working');
            else if (msg.type === 'done') {
              setStatus('Capture complete! Refreshing...', 'success');
              // Refresh available screenshots
              const avResp = await fetch('/api/available');
              availableScreens = await avResp.json();
              buildDeviceTabs(); buildScreenTabs();
              updatePreview();
            }
            else if (msg.type === 'error') setStatus('Capture error: ' + msg.message, 'error');
          } catch(e) {}
        }
      }
    }
  } catch (e) { setStatus('Capture error: ' + e.message, 'error'); }
  allBtns.forEach(id => { const b = document.getElementById(id); if (b) b.disabled = false; });
  btn.textContent = 'Capture from Simulator';
}

init();
</script>
</body>
</html>"""


class PreviewHandler(BaseHTTPRequestHandler):
    def __init__(self, config, *args, **kwargs):
        self.config = config
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        cmd = getattr(self, 'command', '?')
        path = getattr(self, 'path', '?')
        print(f"[HTTP] {cmd} {path} — {args[0] if args else ''}")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "":
            self._serve_html()
        elif path == "/api/config":
            self._serve_json(self.config)
        elif path == "/api/available":
            self._serve_available()
        else:
            self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/preview":
            self._handle_preview()
        elif path == "/api/generate":
            self._handle_generate()
        elif path == "/api/upload":
            self._handle_upload()
        elif path == "/api/capture":
            self._handle_capture()
        elif path == "/api/save-config":
            self._handle_save_config()
        elif path == "/api/delete-screen":
            self._handle_delete_screen()
        else:
            self.send_error(404)

    def _serve_html(self):
        screens_json = json.dumps(SCREENS)
        default_config_json = json.dumps({
            "devices": DEFAULT_DEVICE_CONFIGS,
            "gradients": {k: list(v) for k, v in DEFAULT_GRADIENTS.items()},
        })
        app_name = PROJECT_CONFIG.get("app_name", "App")
        html = PREVIEW_HTML.replace("__SCREENS_JSON__", screens_json)
        html = html.replace("__DEFAULT_CONFIG_JSON__", default_config_json)
        html = html.replace("__APP_NAME__", app_name)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def _serve_available(self):
        # Re-discover screens in case new ones were captured
        global SCREENS, DEFAULT_GRADIENTS, DEFAULT_CAPTIONS
        new_screens = discover_screens()
        if new_screens and new_screens != SCREENS:
            # Merge: keep existing screens, add new ones
            existing_keys = {k for k, _ in SCREENS}
            for key, label in new_screens:
                if key not in existing_keys:
                    SCREENS.append((key, label))
            SCREENS.sort()
            DEFAULT_GRADIENTS = get_default_gradients(SCREENS, PROJECT_CONFIG)
            # Only add default captions for new screens, keep existing
            for key, label in SCREENS:
                if key not in DEFAULT_CAPTIONS:
                    DEFAULT_CAPTIONS[key] = {"headline": label, "subheadline": ""}

        result = {}
        for device_name in (self.config.get("devices") or DEFAULT_DEVICE_CONFIGS):
            input_dir = SCRIPT_DIR / "screenshots" / device_name
            available = []
            if input_dir.exists():
                for png in sorted(input_dir.glob("*.png")):
                    available.append(png.stem)
            result[device_name] = available
        self._serve_json(result)

    def _serve_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _handle_preview(self):
        """Render a single screenshot with PIL and return JPEG for preview."""
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            req = json.loads(body)
            screen_key = req["screen"]
            cfg = req["config"]
            device = req.get("device")
            print(f"[PREVIEW] screen={screen_key} device={device}")
            jpeg_bytes = compose_preview(screen_key, cfg, device=device)
            if jpeg_bytes:
                print(f"[PREVIEW] OK — {len(jpeg_bytes)} bytes")
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.end_headers()
                self.wfile.write(jpeg_bytes)
            else:
                print(f"[PREVIEW] No raw screenshot for {screen_key}/{device}")
                self.send_error(404, "No raw screenshot found for " + screen_key)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.send_error(500, str(e))

    def _start_sse(self):
        """Begin a Server-Sent Events response."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

    def _send_sse(self, data: dict):
        """Send a single SSE event."""
        try:
            line = f"data: {json.dumps(data)}\n\n"
            self.wfile.write(line.encode())
            self.wfile.flush()
        except BrokenPipeError:
            pass

    def _handle_generate(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            new_config = json.loads(body)
            self.config.update(new_config)
            save_config(self.config)
            if "captions" in new_config:
                CAPTIONS_FILE.write_text(json.dumps(new_config["captions"], indent=2))

            self._start_sse()
            self._send_sse({"type": "progress", "message": "Starting composition..."})

            results = run_composition_streaming(self.config, self._send_sse)

            self._send_sse({"type": "done", "count": len(results), "files": results})
            print(f"[GENERATE] Done! {len(results)} screenshots generated.")
        except Exception as e:
            import traceback
            traceback.print_exc()
            try:
                self._send_sse({"type": "error", "message": str(e)})
            except Exception:
                pass

    def _handle_upload(self):
        """Generate composed screenshots, then upload to stores with streaming progress."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            new_config = json.loads(body) if body.strip() else {}
            upload_target = new_config.pop("upload_target", "both")
            if new_config:
                self.config.update(new_config)
                save_config(self.config)
                if "captions" in new_config:
                    CAPTIONS_FILE.write_text(json.dumps(new_config["captions"], indent=2))

            self._start_sse()

            # Step 1: Generate composed screenshots
            self._send_sse({"type": "progress", "message": "Generating composed screenshots..."})
            results = run_composition_streaming(self.config, self._send_sse)
            self._send_sse({"type": "progress", "message": f"Generated {len(results)} composed screenshots"})

            # Step 2: Upload via fastlane
            upload_script = SCRIPT_DIR / "upload_screenshots.sh"
            if not upload_script.exists():
                self._send_sse({"type": "error", "message": "upload_screenshots.sh not found"})
                return

            # Build upload command with target flag
            cmd = ["bash", str(upload_script)]
            if upload_target == "ios":
                cmd.append("--ios")
                target_label = "App Store"
            elif upload_target == "android":
                cmd.append("--android")
                target_label = "Play Store"
            else:
                target_label = "App Store + Play Store"

            self._send_sse({"type": "progress", "message": f"Uploading to {target_label}..."})
            proc = subprocess.Popen(
                cmd,
                cwd=str(SCRIPT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in proc.stdout:
                line = line.strip()
                if line:
                    print(f"  {line}")
                    self._send_sse({"type": "progress", "message": line})
            proc.wait()

            if proc.returncode == 0:
                self._send_sse({"type": "done", "message": f"Upload to {target_label} complete!"})
                print(f"[UPLOAD] Done! ({target_label})")
            else:
                self._send_sse({"type": "error", "message": f"Upload failed (exit code {proc.returncode})"})
        except Exception as e:
            import traceback
            traceback.print_exc()
            try:
                self._send_sse({"type": "error", "message": str(e)})
            except Exception:
                pass

    def _handle_capture(self):
        """Run take_screenshots.sh to capture from iOS Simulator with streaming output."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            req = json.loads(body) if body.strip() else {}
            target = req.get("target", "all")
            if target not in ("all", "ipad", "iphone"):
                target = "all"

            capture_script = SCRIPT_DIR / "take_screenshots.sh"
            if not capture_script.exists():
                self._start_sse()
                self._send_sse({"type": "error", "message": "take_screenshots.sh not found"})
                return

            self._start_sse()
            self._send_sse({"type": "progress", "message": f"Starting capture ({target})..."})

            proc = subprocess.Popen(
                ["bash", str(capture_script), target],
                cwd=str(SCRIPT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in proc.stdout:
                line = line.strip()
                if line:
                    print(f"  [CAPTURE] {line}")
                    self._send_sse({"type": "progress", "message": line})
            proc.wait()

            if proc.returncode == 0:
                self._send_sse({"type": "done", "message": "Capture complete!"})
                print(f"[CAPTURE] Done! ({target})")
            else:
                self._send_sse({"type": "error", "message": f"Capture failed (exit code {proc.returncode})"})
        except Exception as e:
            import traceback
            traceback.print_exc()
            try:
                self._send_sse({"type": "error", "message": str(e)})
            except Exception:
                pass

    def _handle_save_config(self):
        """Save current config to screenshot_config.json without generating."""
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            new_config = json.loads(body)
            self.config.update(new_config)
            save_config(self.config)
            if "captions" in new_config:
                CAPTIONS_FILE.write_text(json.dumps(new_config["captions"], indent=2))
            print("[SAVE] Config saved to screenshot_config.json")
            self._serve_json({"success": True})
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._serve_json({"success": False, "error": str(e)})

    def _handle_delete_screen(self):
        """Delete raw + composed screenshot files for a screen/device."""
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            req = json.loads(body)
            device = req["device"]
            screen_key = req["screen"]
            deleted = []
            # Delete raw screenshot
            raw_path = SCRIPT_DIR / "screenshots" / device / f"{screen_key}.png"
            if raw_path.exists():
                raw_path.unlink()
                deleted.append(str(raw_path))
            # Delete composed screenshot
            composed_path = SCRIPT_DIR / "screenshots" / "composed" / device / f"{screen_key}.png"
            if composed_path.exists():
                composed_path.unlink()
                deleted.append(str(composed_path))
            print(f"[DELETE] {device}/{screen_key} — deleted {len(deleted)} files")
            self._serve_json({"success": True, "deleted": deleted})
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._serve_json({"success": False, "error": str(e)})


def run_preview_server(config: dict):
    handler = partial(PreviewHandler, config)
    server = HTTPServer(("127.0.0.1", PREVIEW_PORT), handler)
    url = f"http://localhost:{PREVIEW_PORT}"
    print(f"\nPreview UI: {url}")
    print("Adjust settings, then click Generate All.")
    print("Press Ctrl+C to stop.\n")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Compose App Store screenshots with captions")
    parser.add_argument("--no-preview", action="store_true", help="Generate directly, skip preview UI")
    parser.add_argument("--regenerate-captions", action="store_true", help="Force fresh AI caption generation")
    parser.add_argument("--no-ai", action="store_true", help="Use only hardcoded fallback captions")
    parser.add_argument("--iphone-only", action="store_true", help="Process iPhone only")
    parser.add_argument("--ipad-only", action="store_true", help="Process iPad only")
    args = parser.parse_args()

    init_project()
    app_name = PROJECT_CONFIG.get("app_name", "Screenshot Composer")

    config = load_config()

    if args.regenerate_captions:
        api_key = load_openai_key()
        if api_key and OPENAI_AVAILABLE:
            config["captions"] = generate_captions_with_ai(api_key)
            CAPTIONS_FILE.write_text(json.dumps(config["captions"], indent=2))
        else:
            print("  OpenAI unavailable, using existing captions")
    elif args.no_ai:
        config["captions"] = DEFAULT_CAPTIONS

    if args.iphone_only:
        config["devices"] = {k: v for k, v in config["devices"].items() if "iPhone" in k}
    elif args.ipad_only:
        config["devices"] = {k: v for k, v in config["devices"].items() if "iPad" in k}

    if args.no_preview:
        print(f"{app_name} — Compose App Store Screenshots")
        print("=" * 40)
        captions = config.get("captions", DEFAULT_CAPTIONS)
        print("\nCaptions:")
        for key, _ in SCREENS:
            c = captions.get(key, {})
            print(f'  {key}: "{c.get("headline", "")}" / "{c.get("subheadline", "")}"')
        save_config(config)
        print()
        results = run_composition(config)
        print(f"\nDone! {len(results)} composed screenshots in screenshots/composed/")
        print("Next: ./upload_screenshots.sh")
        return

    # Default: preview UI
    print(f"{app_name} — Screenshot Composer")
    print("=" * 40)
    if SCREENS:
        print(f"  Screens: {len(SCREENS)} ({', '.join(k for k, _ in SCREENS)})")
    else:
        print("  No screens found yet. Drop PNGs in screenshots/<device>/ or use Capture.")
    save_config(config)
    run_preview_server(config)


if __name__ == "__main__":
    main()
