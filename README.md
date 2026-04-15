# Pixiis

Unified game launcher with controller navigation and voice input for Windows.

Pixiis scans your installed games across Steam, Xbox, Epic, GOG, EA, and more, then presents them in a single controller-friendly dashboard with voice-to-text search.

## Features

- **Unified game library** — auto-detects games from Steam, Xbox/UWP, Epic, GOG, EA, Start Menu, and custom folders
- **Controller-first navigation** — full Xbox controller support with D-pad/stick navigation, bumper page switching, and configurable voice trigger
- **Voice input** — hold a trigger to dictate search queries or text; powered by faster-whisper with live + final transcription passes
- **Dark gaming theme** — custom Qt stylesheet with theme editor and per-color customization
- **Game metadata** — pulls cover art, descriptions, and ratings from RAWG
- **Twitch & YouTube integration** — look up streams and trailers for any game
- **Text-to-speech** — spoken feedback via Kokoro TTS
- **Auto-start** — optional Windows startup via registry
- **Configurable** — TOML-based config with sensible defaults and a full Settings UI

## Installation

```bash
git clone <repo-url> pixiis
cd pixiis
pip install -e ".[all]"
```

### Requirements

- Python 3.10+
- Windows 10/11 (controller and game-library features are Windows-specific)
- CUDA-capable GPU recommended for voice models (CPU fallback available)

## Usage

```bash
# Launch the dashboard UI
pixiis --ui

# Scan installed games (CLI)
pixiis --scan

# Run as background daemon (tray icon, controller, voice — no window)
pixiis --daemon

# Show version
pixiis --version
```

## Controller Mapping

| Input | Action |
|---|---|
| Left Stick / D-pad | Navigate tiles and UI elements |
| A | Select / confirm |
| B | Back / cancel |
| X | Search |
| Y | Launch selected game |
| LB / RB | Previous / next page tab |
| Right Trigger* | Hold to record voice input |
| Right Stick | Scroll |
| LB + RB | Open file manager |

*\* Voice trigger is configurable in Settings: Right Trigger, Left Trigger, Hold Y, or Hold X.*

## Configuration

Pixiis uses TOML configuration files:

- **Defaults:** `resources/default_config.toml` (bundled)
- **User overrides:** `%APPDATA%/pixiis/config.toml` (created on first settings save)

### Key sections

| Section | What it controls |
|---|---|
| `[voice]` | Whisper model, device (cuda/cpu), energy threshold, VAD backend |
| `[voice.tts]` | Text-to-speech voice and speed |
| `[controller]` | Deadzone, vibration, hold threshold, voice trigger |
| `[controller.macros]` | Button-to-action mapping |
| `[library]` | Enabled providers, scan interval, custom paths |
| `[ui]` | Tile size, animations, fullscreen |
| `[ui.colors]` | Theme colors, font, border radius |
| `[services.*]` | API keys for RAWG, YouTube, Twitch |
| `[daemon]` | Auto-start on boot |

All settings can also be changed from the in-app Settings page.

## Building

```bash
# Build distributable with PyInstaller
python scripts/build.py

# Or use the spec file directly
pyinstaller pixiis.spec
```

Output goes to `dist/pixiis/`. An NSIS installer stub is generated at `installer.nsi`.

## Project Structure

```
pixiis/
  src/pixiis/
    controller/    Xbox controller backend and macro system
    core/          Config, events, paths, types
    daemon/        Background daemon and Windows auto-start
    library/       Game library scanners (Steam, Xbox, Epic, GOG, EA, ...)
    services/      RAWG, Twitch, YouTube, TTS, image loading
    ui/            PySide6 dashboard — pages, widgets, controller bridge
    voice/         Audio capture, VAD, transcription pipeline
  resources/       Default config, themes, icons
  scripts/         Build and utility scripts
```

## Screenshots

<!-- TODO: Add screenshots -->

## License

See LICENSE file for details.
