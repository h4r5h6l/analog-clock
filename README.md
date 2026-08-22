# Analog Clock Application

A desktop analog clock application displaying multiple timezones with intelligent color contrast adjustment. Built with PyQt5, this lightweight application features two synchronized analog clocks showing Berlin (Europe/Berlin) and Mumbai (Asia/Kolkata) timezones.

## Features

- **Dual Timezone Display**: Shows Berlin and Mumbai time zones simultaneously
- **Auto Color Contrast**: Automatically adjusts clock color (black/white) based on background brightness
- **Always-on-Top Toggle**: Double-click to toggle window always-on-top mode
- **Hardware Stats Monitor**: Real-time display of CPU, RAM, GPU, and VRAM usage (updates every 2 seconds)
- **Battery Indicator**: Displays current battery percentage and charging status in the hardware stats panel
- **Draggable**: Click and drag horizontally to reposition at screen bottom
- **Transparent Background**: 60% opacity for unobtrusive integration with desktop
- **Smooth Animations**: Color transitions and frame-based rendering for smooth updates

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
sudo apt-get install -y python3.12 python3.12-venv python3.12-dev build-essential

# For Fedora/RHEL-based systems
sudo dnf install -y python3.12 python3.12-devel gcc

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
python3.12 -m venv venv
```

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

With the virtual environment activated:

```bash
python clock.py
```

### Running with Full Path (Without Activation)

If you don't want to activate the venv manually:

```bash
./venv/bin/python clock.py
```

### Running in Background

To run the clock in the background and free up your terminal:

```bash
nohup venv/bin/python clock.py > clock.log 2>&1 &
```

## Usage Instructions

### Window Navigation
- **Drag**: Click and drag horizontally to move the clock left/right (stays at screen bottom)
- **Double-Click**: Toggle always-on-top window mode
- Close using your window manager's close button

### Display Information
- **Top Clock**: Shows current time in Berlin timezone (Europe/Berlin)
- **Bottom Clock**: Shows current time in Mumbai timezone (Asia/Kolkata)
- **Hardware Stats Panel**: Displayed on the right side of the clocks, vertically centered (updates every 2 seconds)
  - **CPU**: Current CPU usage percentage
  - **RAM**: Current RAM usage percentage
  - **GPU**: Current GPU usage percentage (if GPU is available)
  - **VRAM**: Current GPU VRAM usage percentage (if GPU is available)
  - **Bat**: Battery percentage and power state (AC/BAT or --% if unavailable)

### Color Adjustment
The clock automatically adjusts hand and tick-mark colors for optimal visibility:
- **Dark Background**: White clock elements
- **Light Background**: Black clock elements
- Color transitions smoothly over 0.35 seconds

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
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install PyQt5
```

### Display Server Issues

If the application won't display (especially on remote systems):

```bash
export QT_QPA_PLATFORM=xcb
python clock.py
```

### Battery Indicator Not Working

The battery indicator reads from `/sys/class/power_supply/`. This feature works on most modern Linux systems. If it doesn't display, it's typically not available on your system.

### GPU/VRAM Monitoring Not Available

The application uses GPUtil to monitor NVIDIA GPUs. If GPUtil is not installed or your system doesn't have an NVIDIA GPU, the GPU and VRAM sections will display "N/A". The application will still work normally with CPU and RAM monitoring.

## Creating a Desktop Launcher (Optional)

To create a desktop shortcut for easy access:

1. Create a `.desktop` file:

```bash
cat > ~/.local/share/applications/analog-clock.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=Analog Clock
Comment=Dual timezone analog clock with battery indicator
Exec=/home/YOUR_USERNAME/Documents/gitProjects/analog-clock/venv/bin/python /home/YOUR_USERNAME/Documents/gitProjects/analog-clock/clock.py
Icon=clock
Terminal=false
Categories=Utility;
EOF
```

Replace `YOUR_USERNAME` with your actual Linux username.

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
├── clock.py              # Main application file
├── background_sheet.py   # Helper for drawing translucent panels
├── requirements.txt      # Python dependencies
├── README.md             # This file
└── venv/                 # Virtual environment directory
    ├── bin/              # Executables (python, pip)
    ├── lib/              # Installed packages
    ├── include/          # Header files
    └── pyvenv.cfg        # Virtual environment config
```

### requirements.txt

The `requirements.txt` file contains:
```
PyQt5>=5.15.0
psutil>=5.9.0
GPUtil>=1.4.0
```

This file makes it easy to replicate the development environment or share the project with others.

## Dependencies Details

### PyQt5
- **PyQt5**: Cross-platform GUI framework
- **PyQt5.QtWidgets**: GUI components (QApplication, QWidget)
- **PyQt5.QtCore**: Core functionality (QTimer, signals)
- **PyQt5.QtGui**: Graphics (QPainter, colors, fonts)

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

- **Refresh Rate**: 60 FPS for smooth animations
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

**Last Updated**: 2026-08-22
