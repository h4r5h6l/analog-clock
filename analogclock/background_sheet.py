"""Utility to draw a semi-transparent background sheet behind UI elements.

Provides a single helper `draw_background_sheet(painter, x, y, width, height, color=None, opacity=0.5)`
that draws a filled rectangle with the requested opacity.

Placed in a separate module so the drawing logic stays organized and testable.
"""

from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtCore import Qt, QRectF


def draw_background_sheet(painter, x, y, width, height, color=None, opacity=0.5, radius=None):
    """Draw a rounded rectangular background sheet using `painter`.

    Args:
        painter: QPainter instance (already begun)
        x, y, width, height: rectangle geometry
        color: optional QColor or tuple; defaults to black
        opacity: float 0.0..1.0 (50% -> 0.5)
        radius: corner radius in pixels; if None a small radius is chosen
    """
    if color is None:
        color = QColor(0, 0, 0)
    c = QColor(color)
    try:
        alpha = int(round(255 * float(opacity)))
    except Exception:
        alpha = 127
    c.setAlpha(max(0, min(255, alpha)))

    # compute a sensible default radius if not provided
    try:
        if radius is None:
            radius = max(6, int(min(width, height) * 0.08))
        rx = float(radius)
        ry = float(radius)
    except Exception:
        rx = ry = 8.0

    painter.save()
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(c))
    painter.drawRoundedRect(QRectF(int(x), int(y), int(width), int(height)), rx, ry)
    painter.restore()
