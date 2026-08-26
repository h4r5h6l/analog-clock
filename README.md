# Analog Clock

A lightweight Linux desktop widget built with PyQt5. It displays two configurable
timezone clocks alongside live CPU, RAM, GPU, VRAM, and battery statistics.

## Features

- Two analog clocks with configurable IANA timezones
- Live system and battery monitoring
- Custom colors, clock sizes, font size, opacity, and always-on-top mode
- Dragging, optional snap-to-grid, and saved settings
- X11 and Wayland support through XWayland when available
- **Dual Timezone Display**: Two stacked analog clocks, each with a configurable IANA timezone (defaults: Berlin and Mumbai)
- **Custom Color Palette**: Pick fixed colors for the clock face, hands, ticks, and border, plus the hardware-panel text and its background sheet
- **Settings Dialog**: Right-click the clock to change timezones and colors
- **Resizable Clock & Text**: Change the clock face size and the specs font size in the settings dialog; both stacked clocks and the hardware-panel background sheet resize together, and the sizes are saved between restarts
- **Adjustable Opacity**: A slider makes just the clock faces and the hardware-panel background sheet translucent (hands, ticks, borders and specs text stay sharp); the value is saved and restored on the next launch
- **Hardware Stats Monitor**: Real-time display of CPU, RAM, GPU, and VRAM usage (updates every 2 seconds)
- **Battery Indicator**: Power state (AC/BAT) always shown in the hardware stats panel; percentage shown before the power state when metric values are enabled (e.g. `76% AC`)
- **Draggable Anywhere**: Free dragging to any screen position; the position is remembered across restarts
- **Snap to Grid**: Optionally align the window to a visible grid while dragging (configurable spacing from 5 to 150 px in the settings dialog, default off for backward compatibility). The grid overlay appears on screen during the drag and disappears when you release the clock.
- **Always on Top**: Frameless tool window that stays above other windows and re-shows itself if minimized. Toggle the behavior anytime using the eye icon button in the top-left corner of the clock, or via the settings dialog.
- **Eye Toggle Button**: Click the eye icon (👁️) in the top-left corner of the clock to quickly toggle always-on-top mode. When always-on-top is enabled, the eye is open; when disabled, it shows a stop sign (🚫). The setting persists across restarts. The eye button's opacity automatically matches the clock face opacity (with a 40% minimum) for consistent visual integration.
- **Transparent Background**: 60% opacity for unobtrusive integration with the desktop
- **Smooth Animations**: Repaints only when something actually changes
- **Wayland-Safe**: Routes through XWayland (xcb) automatically so positioning and dragging work on both X11 and Wayland

## Requirements

- Linux
- Python 3.12+
- PyQt5 >= 5.15.0
- psutil >= 5.9.0
- GPUtil >= 1.4.0 (optional at runtime)
- setuptools >= 69.0.0

## Install and Run

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

Left-click and drag the widget to move it. Right-click to open settings.

## Build

Create a standalone executable with PyInstaller:

```bash
pip install pyinstaller
pyinstaller clock.spec
```

The packaged application is created in `dist/clock`.

## Start Automatically

The included `analog_clock.desktop` launcher can start the widget when you log
in. Copy it to the autostart directory:
```bash
nohup venv/bin/python main.py > clock.log 2>&1 &
```

## Usage Instructions

### Window Navigation
- **Drag**: Left-click and drag to move the window anywhere on screen; the position is saved automatically (debounced) and restored on the next launch
- **Right-Click**: Open the settings dialog (colors, timezones, and display sizes) — it opens beside the clock (right side, or left if there is no room) and stays above it
- The window is always-on-top and re-shows itself if minimized; it has no title bar or close button

### Display Information
- **Top Clock / Bottom Clock**: Each shows the timezone chosen in the settings dialog (defaults: Europe/Berlin and Asia/Kolkata; invalid names fall back to system local time)
- **Hardware Stats Panel**: Displayed on the right side of the clocks, vertically centered (updates every 2 seconds)
  - **CPU**: Current CPU usage percentage
  - **RAM**: Current RAM usage percentage
  - **GPU**: Current GPU usage percentage (if GPU is available)
  - **VRAM**: Current GPU VRAM usage percentage (if GPU is available)
          - **Bat**: Battery power state (AC/BAT) is always shown; percentage is shown before the power state only when metric values are enabled (e.g. `76% AC`; displays `N/A` when no battery is present)

### Custom Colors
The clock always uses your fixed colors, chosen in the settings dialog (a live preview shows the result): clock face, hands, ticks, and border, plus the hardware-panel text and its background sheet. Defaults: white face, border, and sheet with black hands, ticks, and text.

### Display Size
Use the **Display size** controls in the settings dialog to set the clock face size and the specs (hardware-panel) font size. Increasing the clock size grows **both** stacked clocks and the hardware-panel background sheet together; the chosen sizes are saved to `window_position.json` alongside your colors and timezones and restored on the next launch.

### Opacity
The **Opacity** slider in the settings dialog controls the translucency of just the clock faces and the hardware-panel background sheet. Hands, ticks, borders and specs text remain fully opaque, so the clocks stay legible while the face and sheet sink into the background. The value is saved to `window_position.json` with the other display settings and is restored on the next launch.

## Troubleshooting

### PyQt5 Installation Issues

If you encounter issues installing PyQt5, try:

```bash
pip install PyQt5 --upgrade
```

For X11 display issues on Linux:
```bash
sudo apt-get install -y libqt5gui5 libqt5core5a libqt5dbus5
```

### Virtual Environment Issues

If the virtual environment doesn't work, recreate it:

```bash
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install PyQt5
```

### Display Server Issues

The app routes itself through XWayland (xcb) automatically via
`analogclock/bootstrap.py` whenever an X display is available. If it still
won't display (e.g. on remote/headless systems), try:

```bash
export QT_QPA_PLATFORM=xcb
python main.py
```

### Battery Indicator Not Working

Battery info comes from `psutil.sensors_battery()` first, falling back to a
direct read of `/sys/class/power_supply/`. This works on most modern Linux
systems; if it shows `--%`, no battery is reported on your system.

### GPU/VRAM Monitoring Not Available

The application uses GPUtil to monitor NVIDIA GPUs. If GPUtil is not installed or your system doesn't have an NVIDIA GPU, the GPU and VRAM sections will display "N/A". The application will still work normally with CPU and RAM monitoring.

## Creating a Desktop Launcher (Optional)

A ready-made launcher ships with the project as `analog_clock.desktop`. To install it:

1. Copy it into your applications directory:

```bash
cp analog_clock.desktop ~/.local/share/applications/analog-clock.desktop
```

2. If your checkout does not live at `/home/YOUR_USERNAME/Documents/git_projects/analog-clock`, edit the installed copy and fix the `Exec` and `Path` lines to point at your `venv/bin/python` and `main.py`.

2. Make it executable and update the desktop database:

```bash
chmod +x ~/.local/share/applications/analog-clock.desktop
update-desktop-database ~/.local/share/applications/
```

Now you can launch the application from your application menu or launcher.

## Autostart on Login (Optional)

To automatically start the clock when you log in:

1. Create an autostart entry:

```bash
mkdir -p ~/.config/autostart
cp analog_clock.desktop ~/.config/autostart/
```

Update the `Exec` and `Path` values first if the project is not located at the
path configured in the launcher.

## Configuration

Settings are saved automatically in:

```text
~/.config/analog-clock/window_position.json
```

## Project Structure

```text
analog-clock/
├── main.py                 # Application entry point
├── requirements.txt        # Python dependencies
├── clock.spec              # PyInstaller build configuration
├── analog_clock.desktop    # Desktop and autostart launcher
└── analogclock/            # Application package
	├── analog_clock_widget.py
	├── settings_dialog.py
	├── hardware.py
	├── drawing.py
	├── background_sheet.py
	├── bootstrap.py
	├── colors.py
	├── config.py
	└── timezones.py
```

## License

Provided as-is for personal use.
