"""Color state for the fixed manual palette.

Owns everything color-related that used to live on AnalogClock: the four
configurable roles and the resolved per-frame palette handed to
analogclock.drawing.
"""

from PyQt5.QtGui import QColor

# The four manually configurable color roles.
COLOR_ROLES = ("face_color", "hand_color", "tick_color", "border_color")

DEFAULT_MANUAL_COLORS = {
    "face_color": QColor(255, 255, 255),   # clock face fill
    "hand_color": QColor(0, 0, 0),         # hour/minute/second hands + hub
    "tick_color": QColor(0, 0, 0),         # tick marks around the face
    "border_color": QColor(255, 255, 255), # outlines, halos, hub ring
}


class ColorController:
    """Fixed-palette color state for one AnalogClock widget."""

    def __init__(self):
        self.manual_colors = {
            role: QColor(color) for role, color in DEFAULT_MANUAL_COLORS.items()
        }

    # ---- Per-frame resolution ----------------------------------------------

    def resolved_palette(self):
        """Resolve the four roles for this frame from the fixed palette."""
        return {
            "hand_color": QColor(self.manual_colors.get("hand_color", QColor(0, 0, 0))),
            "tick_color": QColor(self.manual_colors.get("tick_color", QColor(0, 0, 0))),
            "face_color": QColor(self.manual_colors.get("face_color", QColor(255, 255, 255))),
            "border_color": QColor(self.manual_colors.get("border_color", QColor(255, 255, 255))),
        }

    def color_for(self, role):
        """Per-role lookup of this frame's resolved color."""
        if role not in COLOR_ROLES:
            raise KeyError(f"Unknown color role: {role!r}")
        return self.resolved_palette()[role]

    # ---- Runtime appearance setters (persistence stays widget-side) --------

    def set_manual_color(self, role, color):
        """Set one manual color role."""
        if role not in COLOR_ROLES:
            return
        resolved = QColor(color)
        if not resolved.isValid():
            return
        self.manual_colors[role] = resolved

    def apply_appearance_settings(self, colors):
        """Apply a full palette atomically."""
        for role in COLOR_ROLES:
            resolved = QColor(colors.get(role, self.manual_colors.get(role)))
            if resolved.isValid():
                self.manual_colors[role] = resolved


