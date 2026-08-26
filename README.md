# Analog Clock

A lightweight Linux desktop widget built with PyQt5. It displays two configurable
timezone clocks alongside live CPU, RAM, GPU, VRAM, and battery statistics.

## Features

- Two analog clocks with configurable IANA timezones
- Live system and battery monitoring
- Custom colors, clock sizes, font size, opacity, and always-on-top mode
- Dragging, optional snap-to-grid, and saved settings
- X11 and Wayland support through XWayland when available

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
