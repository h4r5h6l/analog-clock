# Analog Clock Application

A desktop analog clock widget for Linux, built with PyQt5. Two stacked analog clocks show configurable timezones (defaults: Europe/Berlin and Asia/Kolkata) next to a live hardware stats panel, with automatic contrast so the clock stays readable on any wallpaper.

## Features

- **Dual Timezone Display**: Two stacked analog clocks, each with a configurable IANA timezone (defaults: Berlin and Mumbai)
- **Auto Color Contrast**: Automatically adjusts clock colors (black/white) based on the brightness of the wallpaper behind the window
- **Custom Color Palette**: Pick fixed face/hand/tick/border colors instead of auto contrast
- **Settings Dialog**: Right-click the clock to change timezones, colors, and contrast mode
- **Hardware Stats Monitor**: Real-time display of CPU, RAM, GPU, and VRAM usage (updates every 2 seconds)
- **Battery Indicator**: Battery percentage and charging status (AC/BAT) in the hardware stats panel
- **Draggable Anywhere**: Free dragging to any screen position; the position is remembered across restarts
- **Always on Top**: Frameless tool window that stays above other windows and re-shows itself if minimized
- **Transparent Background**: 60% opacity for unobtrusive integration with the desktop
- **Smooth Animations**: Eased color transitions; repaints only when something actually changes
- **Wayland-Safe**: Routes through XWayland (xcb) automatically so positioning, dragging, and screen sampling work on both X11 and Wayland

## Requirements

- **Linux OS** (tested on modern distributions)
- **Python 3.12+**
- **PyQt5** GUI framework
- **psutil** for system resource monitoring
- **GPUtil** for GPU monitoring (optional, gracefully falls back if unavailable)

## Installation Steps for Linux

### Step 1: Install System Dependencies

Before creating a virtual environment, ensure you have the required system packages:

```bash
# For Debian/Ubuntu-based systems
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-dev build-essential

# For Fedora/RHEL-based systems
sudo dnf install -y python3 python3-devel gcc

# For Arch-based systems
sudo pacman -S --needed python base-devel
```

### Step 2: Navigate to Project Directory

```bash
cd /path/to/analog-clock
```

### Step 3: Create Virtual Environment

Create an isolated Python environment to avoid conflicts with system packages:

```bash
python3 -m venv venv
```

Any Python ≥ 3.12 works; the development environment for this project currently uses Python 3.14.

This will create a `venv/` directory containing the isolated Python environment.

### Step 4: Activate Virtual Environment

Activate the virtual environment for your current terminal session:

```bash
source venv/bin/activate
```

You should see `(venv)` prefix in your terminal prompt, indicating the virtual environment is active.

### Step 5: Upgrade pip and setuptools

Ensure you have the latest package manager versions:

```bash
pip install --upgrade pip setuptools wheel
```

### Step 6: Install Required Dependencies

Install all required packages from the `requirements.txt` file:

```bash
pip install -r requirements.txt
```

**Note**: The project includes a `requirements.txt` file with all dependencies. If you prefer to install manually:

```bash
pip install PyQt5>=5.15.0 psutil>=5.9.0 GPUtil>=1.4.0
```

### Step 7: Verify Installation

Test if all dependencies are correctly installed:

```bash
python3 -c "from PyQt5.QtWidgets import QApplication; print('PyQt5 installed successfully')"
```

## Running the Application

### Standard Execution

With the virtual environment activated (run from the project root):

```bash
python main.py
```

### Running with Full Path (Without Activation)

If you don't want to activate the venv manually:

```bash
./venv/bin/python main.py
```

### Running in Background

To run the clock in the background and free up your terminal:

```bash
nohup venv/bin/python main.py > clock.log 2>&1 &
```

## Usage Instructions

### Window Navigation
- **Drag**: Left-click and drag to move the window anywhere on screen; the position is saved automatically (debounced) and restored on the next launch
- **Right-Click**: Open the settings dialog (contrast mode, fixed colors, both timezones) — it opens beside the clock (right side, or left if there is no room) and stays above it
- The window is always-on-top and re-shows itself if minimized; it has no title bar or close button

### Display Information
- **Top Clock / Bottom Clock**: Each shows the timezone chosen in the settings dialog (defaults: Europe/Berlin and Asia/Kolkata; invalid names fall back to system local time)
- **Hardware Stats Panel**: Displayed on the right side of the clocks, vertically centered (updates every 2 seconds)
  - **CPU**: Current CPU usage percentage
  - **RAM**: Current RAM usage percentage
  - **GPU**: Current GPU usage percentage (if GPU is available)
  - **VRAM**: Current GPU VRAM usage percentage (if GPU is available)
  - **Bat**: Battery percentage and power state (AC/BAT or --% if unavailable)

### Color Adjustment
In automatic contrast mode the clock adjusts its colors for optimal visibility:
- **Dark Background**: White clock elements
- **Light Background**: Black clock elements
- Colors transition smoothly over 0.35 seconds
- Turn auto contrast off in the settings dialog to use your own fixed face/hand/tick/border colors (a live preview shows the result)

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

### `QFont::fromString Invalid description 'Noto Sans,...'` in the terminal

This message is emitted by your **desktop environment's Qt theme plugin**
(GNOME/KDE/qt5ct) while it parses the system font record at startup — not by
this application (the codebase contains no font-string parsing). It is
harmless: the bundled Noto Sans takes precedence for all app text anyway.
Per project decision we leave desktop theme integration untouched.

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
cp ~/.local/share/applications/analog-clock.desktop ~/.config/autostart/
```

The clock will now start automatically when you log into your desktop environment.

## Project Structure

```
analog-clock/
├── main.py                    # Entry point: platform workarounds, QApplication, exec_()
├── clock.spec                 # PyInstaller spec (builds from main.py)
├── analog_clock.desktop       # App-menu launcher
├── requirements.txt           # Python dependencies
├── README.md                  # This file
├── analogclock/               # Application package
│   ├── __init__.py
│   ├── bootstrap.py           # Wayland/xcb QT_QPA_PLATFORM workaround
│   ├── config.py              # JSON persistence (~/.config/analog-clock/)
│   ├── colors.py              # ColorController: auto contrast + manual palette
│   ├── timezones.py           # TimezonePair + safe zoneinfo lookups + defaults
│   ├── hardware.py            # HardwareMonitor: CPU/RAM/GPU/VRAM/battery
│   ├── drawing.py             # Pure QPainter drawing routines (widget-free)
│   ├── background_sheet.py    # Translucent rounded-sheet helper
│   ├── settings_dialog.py     # Settings dialog with live preview
│   ├── fonts/                 # Bundled Noto Sans Regular/Bold (OFL) + license
│   └── analog_clock_widget.py # AnalogClock(QWidget): timers, drag/move, paint glue
└── venv/                      # Virtual environment directory (gitignored)
```

### requirements.txt

The `requirements.txt` file contains:
```
PyQt5>=5.15.0
psutil>=5.9.0
GPUtil>=1.4.0
setuptools>=69.0.0
```

(`setuptools` provides the `distutils` shim that GPUtil imports on Python 3.12+.)

This file makes it easy to replicate the development environment or share the project with others.

## Dependencies Details

### PyQt5
- **PyQt5**: Cross-platform GUI framework
- **PyQt5.QtWidgets**: GUI components (QApplication, QWidget)
- **PyQt5.QtCore**: Core functionality (QTimer, signals)
- **PyQt5.QtGui**: Graphics (QPainter, colors, fonts)

### Fonts

The app bundles **Noto Sans Regular/Bold** (SIL Open Font License — see
`analogclock/fonts/OFL.txt`) and registers it at startup via
`QFontDatabase.addApplicationFont`, so text renders identically on every
machine regardless of installed fonts. The hardware panel's size is measured
from the loaded font with `QFontMetrics` (`drawing.measure_specs_panel`), so
even if font registration ever fails and the system default is used, labels
still fit instead of clipping.

### System Monitoring
- **psutil**: Cross-platform library for retrieving information on running processes and system utilization (CPU, RAM)
- **GPUtil**: GPU monitoring utility for NVIDIA GPUs (gracefully degrades if unavailable)

### Python Standard Library
- `sys`: System-specific parameters
- `math`: Mathematical functions
- `time`: Time access and conversions
- `pathlib.Path`: File system path operations
- `datetime.datetime`: Date and time handling
- `zoneinfo.ZoneInfo`: Timezone support

## Performance Notes

- **Animation Timer**: ticks at ~60 Hz but repaints only while a color transition is actually animating
- **Clock Update**: Every 1 second
- **Hardware Stats Update**: Every 2 seconds
- **Contrast Check**: Every 0.2 seconds (efficient background sampling)
- **Memory Footprint**: Minimal (~30-50 MB)
- **CPU Usage**: Low (mainly event-driven)

## License

This project is provided as-is for personal use.

## Support

For issues with:
- **PyQt5**: Consult [PyQt5 Documentation](https://www.riverbankcomputing.com/static/Docs/PyQt5/)
- **Timezones**: Python's `zoneinfo` module provides IANA timezone database support
- **Display Issues**: Check your X11/Wayland configuration

---

**Last Updated**: 2026-08-23
