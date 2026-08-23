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
