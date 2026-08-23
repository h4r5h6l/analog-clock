"""Color state and desktop-contrast sampling.

Owns everything color-related that used to live on AnalogClock: the four
configurable roles, the auto-contrast sampler with its eased transition,
and the resolved per-frame palette handed to analogclock.drawing.
"""

import time

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication

# The four manually configurable color roles.
COLOR_ROLES = ("face_color", "hand_color", "tick_color", "border_color")

DEFAULT_MANUAL_COLORS = {
    "face_color": QColor(255, 255, 255),   # clock face fill
    "hand_color": QColor(0, 0, 0),         # hour/minute/second hands + hub
    "tick_color": QColor(0, 0, 0),         # tick marks around the face
    "border_color": QColor(255, 255, 255), # outlines, halos, hub ring
}

COLOR_TRANSITION_SECONDS = 0.35
CONTRAST_CHECK_SECONDS = 0.2


class ColorController:
    """Color state machine for one AnalogClock widget.

    Keeps a reference to the widget for screen sampling (contrast_color
    needs widget geometry) and to request repaints while a transition is
    animating.
    """

    def __init__(self, widget):
        self._widget = widget
        # use_auto_contrast=True  -> colors adapt automatically to the
        #     desktop luminance sampled behind the window (original behavior).
        # use_auto_contrast=False -> the fixed palette below is used instead.
        self.use_auto_contrast = True
        self.manual_colors = {
            role: QColor(color) for role, color in DEFAULT_MANUAL_COLORS.items()
        }
        self.display_color = QColor(Qt.black)
        self.start_color = QColor(self.display_color)
        self.target_color = QColor(self.display_color)
        self.transition_started_at = time.monotonic()
        self.last_contrast_check = 0

    # ---- Per-frame resolution ----------------------------------------------

    def resolved_palette(self):
        """Resolve the four roles for this frame, honoring the current mode."""
        if not self.use_auto_contrast:
            return {
                "hand_color": QColor(self.manual_colors.get("hand_color", QColor(0, 0, 0))),
                "tick_color": QColor(self.manual_colors.get("tick_color", QColor(0, 0, 0))),
                "face_color": QColor(self.manual_colors.get("face_color", QColor(255, 255, 255))),
                "border_color": QColor(self.manual_colors.get("border_color", QColor(255, 255, 255))),
            }
        clock_color = QColor(self.display_color)
        border_color = self.opposite_color(clock_color)
        face_color = QColor(border_color)
        face_color.setAlpha(42)
        tick_color = QColor(clock_color)
        return {
            "hand_color": clock_color,
            "tick_color": tick_color,
            "face_color": face_color,
            "border_color": border_color,
        }

    def color_for(self, role):
        """Per-role lookup of this frame's resolved color."""
        if role not in COLOR_ROLES:
            raise KeyError(f"Unknown color role: {role!r}")
        return self.resolved_palette()[role]

    @staticmethod
    def opposite_color(color):
        return QColor(255 - color.red(), 255 - color.green(), 255 - color.blue())

    def contrast_color(self):
        """Sample the desktop behind the widget; pick black or white text."""
        widget = self._widget
        screen = QApplication.screenAt(widget.mapToGlobal(widget.rect().center()))
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            return Qt.black

        center = widget.mapToGlobal(widget.rect().center())
        try:
            grabbed = screen.grabWindow(
                0,
                center.x() - 15,
                center.y() - 15,
                30,
                30,
            )
        except Exception:
            # Some platforms (notably Wayland) can reject or fail screen grabs;
            # fall back to black rather than letting the error repeat forever.
            return Qt.black
        image = grabbed.toImage()

        if image.isNull():
            return Qt.black

        total_luminance = 0
        samples = 0
        for x in range(0, image.width(), 5):
            for y in range(0, image.height(), 5):
                color = QColor(image.pixel(x, y))
                total_luminance += (
                    0.2126 * color.red()
                    + 0.7152 * color.green()
                    + 0.0722 * color.blue()
                )
                samples += 1

        average_luminance = total_luminance / samples
        return Qt.white if average_luminance < 128 else Qt.black

    def update_contrast_transition(self):
        """Advance the eased black/white interpolation (auto mode only)."""
        if not self.use_auto_contrast:
            # Manual palette: skip desktop sampling and interpolation
            # entirely and pin display_color to the manual hand color so the
            # remaining consumers (specs panel, battery label, sheet tint)
            # stay consistent with the fixed scheme.
            manual_hand = QColor(
                self.manual_colors.get("hand_color", QColor(0, 0, 0))
            )
            if self.display_color != manual_hand:
                self.display_color = manual_hand
                self._widget.update()
            return

        now = time.monotonic()
        if now - self.last_contrast_check >= CONTRAST_CHECK_SECONDS:
            self.last_contrast_check = now
            contrast_color = QColor(self.contrast_color())
            if contrast_color != self.target_color:
                self.start_color = QColor(self.display_color)
                self.target_color = contrast_color
                self.transition_started_at = now

        elapsed = now - self.transition_started_at
        progress = min(1.0, elapsed / COLOR_TRANSITION_SECONDS)
        eased = progress * progress * (3 - (2 * progress))
        previous_color = QColor(self.display_color)
        red = self.start_color.red() + (self.target_color.red() - self.start_color.red()) * eased
        green = self.start_color.green() + (self.target_color.green() - self.start_color.green()) * eased
        blue = self.start_color.blue() + (self.target_color.blue() - self.start_color.blue()) * eased
        self.display_color = QColor(round(red), round(green), round(blue))
        # Repaint only while the interpolated color actually changes. A constant
        # 60fps repaint loop starves the backing store; between transitions the
        # 1s clock timer keeps the hands moving.
        if self.display_color != previous_color:
            self._widget.update()

    # ---- Runtime appearance setters (persistence stays widget-side) --------

    def set_use_auto_contrast(self, enabled):
        """Toggle between adaptive desktop contrast and the fixed palette."""
        self.use_auto_contrast = bool(enabled)
        # Re-sync display_color immediately for both directions.
        self.update_contrast_transition()

    def set_manual_color(self, role, color):
        """Set one manual color role; picking a color implies manual mode."""
        if role not in COLOR_ROLES:
            return
        resolved = QColor(color)
        if not resolved.isValid():
            return
        self.manual_colors[role] = resolved
        self.use_auto_contrast = False
        self.update_contrast_transition()

    def apply_appearance_settings(self, use_auto_contrast, colors):
        """Apply a full palette + mode atomically."""
        for role in COLOR_ROLES:
            resolved = QColor(colors.get(role, self.manual_colors.get(role)))
            if resolved.isValid():
                self.manual_colors[role] = resolved
        self.use_auto_contrast = bool(use_auto_contrast)
        self.update_contrast_transition()


