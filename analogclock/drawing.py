"""Pure QPainter drawing routines.

Zero Qt-widget dependency: every function takes an active ``painter``
plus explicit geometry/colors, so the clock face can be rendered by the
main widget, the settings-dialog live preview, or a unit test alike.
All geometry/scale math lives here.
"""

import math

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QBrush, QColor, QPen

from analogclock.background_sheet import draw_background_sheet

# Specs panel styling (extracted from the former paintEvent constants).
SHEET_OPACITY = 0.82
SHEET_PADDING = 8
SHEET_RADIUS = 12
LINE_HEIGHT = 19
TEXT_PADDING = 6


def draw_outlined_text(painter, rect, alignment, text, fill_color, border_color):
    painter.setPen(QPen(border_color))
    for dx, dy in (
        (-1, -1), (0, -1), (1, -1),
        (-1, 0),           (1, 0),
        (-1, 1),  (0, 1),  (1, 1),
    ):
        painter.drawText(rect.adjusted(dx, dy, dx, dy), alignment, text)

    painter.setPen(QPen(fill_color))
    painter.drawText(rect, alignment, text)


def draw_outlined_hand(painter, center_x, center_y, length, angle, width, fill_color, border_color):
    end_x = int(center_x + length * math.sin(math.radians(angle)))
    end_y = int(center_y - length * math.cos(math.radians(angle)))
    halo_color = QColor(border_color)
    halo_color.setAlpha(115)

    painter.setPen(QPen(halo_color, width + 7, Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(int(center_x), int(center_y), end_x, end_y)
    painter.setPen(QPen(border_color, width + 4, Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(int(center_x), int(center_y), end_x, end_y)
    painter.setPen(QPen(fill_color, width, Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(int(center_x), int(center_y), end_x, end_y)

    dot_radius = max(2, round(width * 0.75))
    painter.setPen(QPen(border_color, 1))
    painter.setBrush(QBrush(fill_color))
    painter.drawEllipse(QRectF(end_x - dot_radius, end_y - dot_radius, dot_radius * 2, dot_radius * 2))


def draw_clock(painter, top_left_x, top_left_y, now, size, colors):
    """Draw one clock face.

    ``colors`` maps the four COLOR_ROLES entries to resolved QColors for
    this frame (see colors.ColorController.resolved_palette).
    """
    scale = size / 200
    center_x = top_left_x + size / 2
    center_y = top_left_y + size / 2
    margin = 10 * scale - 3
    face_size = size - (margin * 2)
    hour_hand = 48 * scale
    minute_hand = 68 * scale
    second_hand = 76 * scale

    clock_color = QColor(colors["hand_color"])
    border_color = QColor(colors["border_color"])
    face_color = QColor(colors["face_color"])
    tick_color = QColor(colors["tick_color"])

    # Soft translucent face fill only -- no hard outline ring, for a
    # minimal floating look.
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(face_color))
    painter.drawEllipse(int(top_left_x + margin), int(top_left_y + margin), int(face_size), int(face_size))

    # Draw 60 tick marks around the face instead of numerals.
    # Major ticks sit at the 12 hour positions (i % 5 == 0).
    face_radius = face_size / 2
    outer_radius = face_radius * 0.95
    major_inner_radius = face_radius * 0.85
    minor_inner_radius = face_radius * 0.90
    major_tick_color = QColor(tick_color)
    minor_tick_color = QColor(tick_color)
    minor_tick_color.setAlpha(90)
    major_pen = QPen(major_tick_color, max(2, round(4 * scale)), Qt.SolidLine, Qt.RoundCap)
    minor_pen = QPen(minor_tick_color, max(1, round(2 * scale)), Qt.SolidLine, Qt.RoundCap)
    for i in range(60):
        angle = i * 6
        is_major = i % 5 == 0
        inner_radius = major_inner_radius if is_major else minor_inner_radius
        start_x = center_x + inner_radius * math.sin(math.radians(angle))
        start_y = center_y - inner_radius * math.cos(math.radians(angle))
        end_x = center_x + outer_radius * math.sin(math.radians(angle))
        end_y = center_y - outer_radius * math.cos(math.radians(angle))
        painter.setPen(major_pen if is_major else minor_pen)
        painter.drawLine(int(start_x), int(start_y), int(end_x), int(end_y))

    hour = now.hour % 12
    minute = now.minute
    second = now.second
    hour_angle = (hour * 30) + (minute * 0.5)
    draw_outlined_hand(
        painter,
        center_x,
        center_y,
        hour_hand,
        hour_angle,
        max(3, round(6 * scale)),
        clock_color,
        border_color,
    )
    min_angle = minute * 6
    draw_outlined_hand(
        painter,
        center_x,
        center_y,
        minute_hand,
        min_angle,
        max(3, round(5 * scale)),
        clock_color,
        border_color,
    )
    sec_angle = second * 6
    draw_outlined_hand(
        painter,
        center_x,
        center_y,
        second_hand,
        sec_angle,
        max(2, round(3 * scale)),
        clock_color,
        border_color,
    )
    hub_radius = max(4, round(6 * scale))
    painter.setPen(QPen(border_color, 2))
    painter.setBrush(QBrush(clock_color))
    painter.drawEllipse(QRectF(center_x - hub_radius, center_y - hub_radius, hub_radius * 2, hub_radius * 2))
    painter.setBrush(Qt.NoBrush)


def draw_hardware_specs(painter, panel_x, panel_y, panel_width, panel_height, stats, colors):
    """Draw the rounded specs sheet plus CPU/RAM/GPU/VRAM/battery text.

    ``stats`` comes from hardware.HardwareMonitor.stats_snapshot();
    ``panel_x/y/width/height`` describe the panel rect computed by the
    caller from the widget's layout constants.
    """
    text_color = QColor(colors["text_color"])
    border_color = QColor(colors["border_color"])
    sheet_color = QColor(colors["sheet_color"])

    # Background sheet as an independent rounded rectangle so the panel and
    # clocks appear visually distinct.
    sheet_x = panel_x - SHEET_PADDING
    sheet_y = panel_y - SHEET_PADDING
    sheet_w = panel_width + (SHEET_PADDING * 2)
    sheet_h = panel_height + (SHEET_PADDING * 2)
    draw_background_sheet(painter, sheet_x, sheet_y, sheet_w, sheet_h, sheet_color, SHEET_OPACITY, radius=SHEET_RADIUS)

    # Set up font for specs text
    specs_font = painter.font()
    specs_font.setPointSize(10)
    specs_font.setBold(True)
    painter.setFont(specs_font)

    padding = TEXT_PADDING
    line_height = LINE_HEIGHT

    # Prepare specs text
    cpu_text = f"CPU: {stats['cpu_percent']:.0f}%"
    ram_text = f"RAM: {stats['ram_percent']:.0f}%"
    gpu_text = f"GPU: {stats['gpu_percent']:.0f}%" if stats["gpu_available"] else "GPU: N/A"
    vram_text = f"VRAM: {stats['gpu_vram_percent']:.0f}%" if stats["gpu_available"] else "VRAM: N/A"
    battery_text = stats["battery_text"]

    # Draw specs text lines
    text_x = panel_x + padding + 1
    text_y = panel_y + padding

    draw_outlined_text(
        painter,
        QRectF(text_x, text_y, panel_width - (padding * 2), line_height),
        Qt.AlignLeft,
        cpu_text,
        text_color,
        border_color,
    )

    draw_outlined_text(
        painter,
        QRectF(text_x, text_y + line_height, panel_width - (padding * 2), line_height),
        Qt.AlignLeft,
        ram_text,
        text_color,
        border_color,
    )

    draw_outlined_text(
        painter,
        QRectF(text_x, text_y + (line_height * 2), panel_width - (padding * 2), line_height),
        Qt.AlignLeft,
        gpu_text,
        text_color,
        border_color,
    )

    draw_outlined_text(
        painter,
        QRectF(text_x, text_y + (line_height * 3), panel_width - (padding * 2), line_height),
        Qt.AlignLeft,
        vram_text,
        text_color,
        border_color,
    )

    draw_outlined_text(
        painter,
        QRectF(text_x, text_y + (line_height * 4), panel_width - (padding * 2), line_height),
        Qt.AlignLeft,
        f" {battery_text}",
        text_color,
        border_color,
    )


