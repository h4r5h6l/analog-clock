"""Color state for the fixed manual palette.

Owns everything color-related that used to live on AnalogClock: the
configurable color roles (clock face, hands, ticks, border, specs text,
specs sheet) and the resolved per-frame palette handed to
analogclock.drawing.
"""

from PyQt5.QtGui import QColor

# Manually configurable color roles. The first four paint the clock face;
# text_color and sheet_color paint the hardware panel and are intentionally
# independent of the hand/border colors so recoloring one does not bleed
# into the other (previously the panel's sheet/text were inferred from the
# hand color, which made recoloring the hands also flip the panel).
COLOR_ROLES = (
    "face_color",
    "hand_color",
    "tick_color",
    "border_color",
    "text_color",
    "sheet_color",
)

DEFAULT_MANUAL_COLORS = {
    "face_color": QColor(255, 255, 255),   # clock face fill
    "hand_color": QColor(0, 0, 0),         # hour/minute/second hands + hub
    "tick_color": QColor(0, 0, 0),         # tick marks around the face
    "border_color": QColor(255, 255, 255), # outlines, halos, hub ring
    "text_color": QColor(0, 0, 0),         # CPU/RAM/GPU/VRAM/battery text
    "sheet_color": QColor(255, 255, 255),  # hardware panel background sheet
}


class ColorController:
    """Fixed-palette color state for one AnalogClock widget."""

    def __init__(self):
        self.manual_colors = {
            role: QColor(color) for role, color in DEFAULT_MANUAL_COLORS.items()
        }

    # ---- Per-frame resolution ----------------------------------------------

    def resolved_palette(self):
        """Resolve every color role for this frame from the fixed palette."""
        return {
            role: QColor(self.manual_colors.get(role, default))
            for role, default in DEFAULT_MANUAL_COLORS.items()
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


