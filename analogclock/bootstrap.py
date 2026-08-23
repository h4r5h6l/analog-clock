"""Platform workarounds applied before QApplication is constructed.

This clock positions itself (restored saved position, free dragging) and
samples the pixels behind it for contrast. Both need client-side window
positioning, which the native Wayland platform plugin cannot do -- every
self.move() would be silently ignored by the compositor. Route through
XWayland (xcb) on Linux unless the user chose a platform explicitly.
Guarded so headless/offscreen setups without an X display are unaffected.
"""

import os
import sys


def apply_platform_workarounds():
    """Force the xcb (XWayland) platform plugin on Linux desktops."""
    if (
        sys.platform.startswith("linux")
        and not os.environ.get("QT_QPA_PLATFORM")
        and os.environ.get("DISPLAY")
    ):
        os.environ["QT_QPA_PLATFORM"] = "xcb"


def apply_qt_attributes():
    """Enable high-DPI support; must run before QApplication is constructed.

    AA_EnableHighDpiScaling makes device-independent pixels follow the
    desktop scale factor, so fonts and layout scale together instead of
    fighting each other on machines whose display scaling is not 100%.
    """
    from PyQt5.QtCore import QCoreApplication, Qt

    for name in ("AA_EnableHighDpiScaling", "AA_UseHighDpiPixmaps"):
        attribute = getattr(Qt, name, None)
        if attribute is not None:
            QCoreApplication.setAttribute(attribute)


def load_bundled_font():
    """Register the bundled Noto Sans TTFs; return the family name or None.

    Works both from a source checkout (analogclock/fonts next to this file)
    and from a PyInstaller bundle (sys._MEIPASS/analogclock/fonts). Returns
    None when nothing could be registered, letting the caller fall back to
    the system default font.
    """
    from pathlib import Path

    from PyQt5.QtGui import QFontDatabase

    candidates = [Path(__file__).resolve().parent / "fonts"]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "analogclock" / "fonts")
        candidates.append(Path(meipass) / "fonts")

    for directory in candidates:
        if not directory.is_dir():
            continue
        last_font_id = -1
        for ttf_path in sorted(directory.glob("*.ttf")):
            font_id = QFontDatabase.addApplicationFont(str(ttf_path))
            if font_id != -1:
                last_font_id = font_id
        if last_font_id != -1:
            families = QFontDatabase.applicationFontFamilies(last_font_id)
            if families:
                return families[0]
    return None
