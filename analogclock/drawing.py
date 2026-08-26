"""Pure QPainter drawing routines.

Zero Qt-widget dependency: every function takes an active ``painter``
plus explicit geometry/colors, so the clock face can be rendered by the
main widget, the settings-dialog live preview, or a unit test alike.
All geometry/scale math lives here.
"""

import math
import re

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QBrush, QColor, QPainterPath, QPen

from analogclock.background_sheet import draw_background_sheet

# Specs panel styling (extracted from the former paintEvent constants).
SHEET_OPACITY = 0.82
SHEET_PADDING = 12
SHEET_RADIUS = 14
LINE_HEIGHT = 19
TEXT_PADDING = 6
METER_TRACK_HEIGHT = 5
METER_TRACK_RADIUS = 2.5
NA_ALPHA_RATIO = 0.45

_COLOR_LOW = QColor(76, 175, 80)    # green
_COLOR_MID = QColor(255, 193, 7)    # amber/yellow
_COLOR_HIGH = QColor(244, 67, 54)   # red


def _usage_color(value_percent):
    """Return a green→yellow→red color for a 0‑100 usage percentage."""
    t = max(0.0, min(100.0, value_percent)) / 100.0
    if t < 0.5:
        s = t / 0.5
        r = _COLOR_LOW.red() + s * (_COLOR_MID.red() - _COLOR_LOW.red())
        g = _COLOR_LOW.green() + s * (_COLOR_MID.green() - _COLOR_LOW.green())
        b = _COLOR_LOW.blue() + s * (_COLOR_MID.blue() - _COLOR_LOW.blue())
    else:
        s = (t - 0.5) / 0.5
        r = _COLOR_MID.red() + s * (_COLOR_HIGH.red() - _COLOR_MID.red())
        g = _COLOR_MID.green() + s * (_COLOR_HIGH.green() - _COLOR_MID.green())
        b = _COLOR_MID.blue() + s * (_COLOR_HIGH.blue() - _COLOR_MID.blue())
    return QColor(round(r), round(g), round(b))


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


def draw_meter_row(painter, x, y, width, label, value_percent, fill_color, track_color, label_color, border_color, na=False, value_text=None, show_value=True, track_offset=None):
    """Draw one labeled meter row: label + value text with a bar underneath.

    The label is left-aligned and the value (``NN%`` or ``N/A``) is
    right-aligned on the same text line; when ``show_value`` is False the
    default percentage is skipped, but an explicit ``value_text`` is still
    drawn (if ``na`` is False). A rounded 5px track spans the row width
    below the text, overlaid by a fill proportional to ``value_percent``
    unless ``na`` is True. ``track_offset`` is the distance from the row's
    top to the bar; it defaults to the text height (bar right under the
    label).
    """
    text_height = painter.fontMetrics().height()
    text_rect = QRectF(x, y, width, text_height)

    if show_value or (not na and value_text is not None):
        if na:
            dimmed_label = QColor(label_color)
            dimmed_label.setAlpha(round(dimmed_label.alpha() * NA_ALPHA_RATIO))
            draw_outlined_text(
                painter,
                text_rect,
                Qt.AlignRight | Qt.AlignVCenter,
                "N/A",
                dimmed_label,
                border_color,
            )
        else:
            draw_outlined_text(
                painter,
                text_rect,
                Qt.AlignRight | Qt.AlignVCenter,
                value_text if value_text is not None else f"{value_percent:.0f}%",
                label_color,
                border_color,
            )

    draw_outlined_text(
        painter,
        text_rect,
        Qt.AlignLeft | Qt.AlignVCenter,
        label,
        label_color,
        border_color,
    )

    track_y = y + (text_height if track_offset is None else track_offset)
    track_path = QPainterPath()
    track_path.addRoundedRect(QRectF(x, track_y, width, METER_TRACK_HEIGHT), METER_TRACK_RADIUS, METER_TRACK_RADIUS)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(track_color))
    painter.drawPath(track_path)

    if not na:
        fill_width = width * (value_percent / 100)
        fill_path = QPainterPath()
        fill_path.addRoundedRect(QRectF(x, track_y, fill_width, METER_TRACK_HEIGHT), METER_TRACK_RADIUS, METER_TRACK_RADIUS)
        painter.setBrush(QBrush(fill_color))
        painter.drawPath(fill_path)
        painter.setBrush(Qt.NoBrush)


def draw_clock(painter, top_left_x, top_left_y, now, size, colors, opacity=1.0):
    """Draw one clock face.

    ``colors`` maps the four COLOR_ROLES entries to resolved QColors for
    this frame (see colors.ColorController.resolved_palette).
    ``opacity`` (0.0..1.0) sets the translucency of the face fill only.
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
    # minimal floating look. Opacity makes just the face see-through;
    # hands, ticks and borders stay fully opaque.
    face_color.setAlpha(max(0, min(255, round(255 * opacity))))
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


def draw_hardware_specs(painter, panel_x, panel_y, panel_width, panel_height, stats, colors, font_size=10, opacity=SHEET_OPACITY, show_values=True):
    """Draw the rounded specs sheet plus CPU/RAM/GPU/VRAM/battery text.

    ``stats`` comes from hardware.HardwareMonitor.stats_snapshot();
    ``panel_x/y/width/height`` describe the panel rect computed by the
    caller from the widget's layout constants; ``font_size`` is the specs
    text point size (the caller controls it from the appearance settings).
    When ``show_values`` is False the percentage labels are hidden for
    CPU/RAM/GPU/VRAM, while the Battery row still shows just the power
    state (AC/BAT) instead of the full percentage.
    """
    text_color = QColor(colors["text_color"])
    border_color = QColor(colors["border_color"])
    sheet_color = QColor(colors["sheet_color"])

    # Set up font for specs text
    specs_font = painter.font()
    specs_font.setPointSize(font_size)
    specs_font.setBold(True)
    painter.setFont(specs_font)

    padding = TEXT_PADDING
    # Line height tracks the font so the five stat rows keep their spacing
    # as the user enlarges the specs text; extra room fits each row's meter
    # bar plus breathing space between rows.
    line_height = round(font_size * 3.2)
    # Bar sits below the label text; derive offset from actual font metrics
    # so the bar never collides with the text regardless of font size.
    text_height = painter.fontMetrics().height()
    track_offset = text_height + 2

    # Compute panel_height from the actual content so the sheet is
    # vertically symmetrical (equal padding above and below).
    content_height = 4 * line_height + track_offset + METER_TRACK_HEIGHT
    panel_height = content_height + (padding * 2)

    # Background sheet as an independent rounded rectangle so the panel and
    # clocks appear visually distinct.
    sheet_x = panel_x - SHEET_PADDING
    sheet_y = panel_y - SHEET_PADDING
    sheet_w = panel_width + (SHEET_PADDING * 2)
    sheet_h = panel_height + (SHEET_PADDING * 2)
    draw_background_sheet(painter, sheet_x, sheet_y, sheet_w, sheet_h, sheet_color, opacity, radius=SHEET_RADIUS)

    track_color = QColor(120, 120, 120, 140)
    gpu_available = stats["gpu_available"]
    battery_text = stats.get("battery_text", "")
    battery_percent = stats.get("battery_percent")
    battery_power_state = stats.get("battery_power_state") or ""

    # Fallback: parse from battery_text if individual fields aren't
    # provided (e.g. older callers or the settings preview stub).
    if battery_percent is None:
        match = re.match(r"\s*(\d+(?:\.\d+)?)%", battery_text or "")
        if match:
            battery_percent = float(match.group(1))
    if not battery_power_state:
        parts = (battery_text or "").strip().split()
        if len(parts) >= 2:
            battery_power_state = parts[-1]

    # Per-row fill colors: usage bars go green→yellow→red; battery is reversed.
    cpu_color = _usage_color(stats["cpu_percent"])
    ram_color = _usage_color(stats["ram_percent"])
    gpu_color = _usage_color(stats["gpu_percent"])
    vram_color = _usage_color(stats["gpu_vram_percent"])
    bat_color = _usage_color(100 - (battery_percent or 0))

    # Draw specs rows (label + value text with a meter bar underneath)
    text_x = panel_x + padding + 1
    text_y = panel_y + padding

    draw_meter_row(
        painter,
        text_x,
        text_y,
        panel_width - (padding * 2),
        "CPU:",
        stats["cpu_percent"],
        cpu_color,
        track_color,
        text_color,
        border_color,
        show_value=show_values,
        track_offset=track_offset,
    )

    draw_meter_row(
        painter,
        text_x,
        text_y + line_height,
        panel_width - (padding * 2),
        "RAM:",
        stats["ram_percent"],
        ram_color,
        track_color,
        text_color,
        border_color,
        show_value=show_values,
        track_offset=track_offset,
    )

    draw_meter_row(
        painter,
        text_x,
        text_y + (line_height * 2),
        panel_width - (padding * 2),
        "GPU:",
        stats["gpu_percent"],
        gpu_color,
        track_color,
        text_color,
        border_color,
        na=not gpu_available,
        show_value=show_values,
        track_offset=track_offset,
    )

    draw_meter_row(
        painter,
        text_x,
        text_y + (line_height * 3),
        panel_width - (padding * 2),
        "VRAM:",
        stats["gpu_vram_percent"],
        vram_color,
        track_color,
        text_color,
        border_color,
        na=not gpu_available,
        show_value=show_values,
        track_offset=track_offset,
    )

    # When metric values are hidden, show only the power state (AC/DC);
    # when visible, show battery percentage before the power state.
    if show_values:
        if battery_percent is not None and battery_power_state:
            bat_value_text = f"{battery_percent:.0f}% {battery_power_state}"
        elif battery_percent is not None:
            bat_value_text = f"{battery_percent:.0f}%"
        else:
            bat_value_text = None
    else:
        bat_value_text = battery_power_state if battery_power_state else None

    draw_meter_row(
        painter,
        text_x,
        text_y + (line_height * 4),
        panel_width - (padding * 2),
        "Battery:",
        battery_percent if battery_percent is not None else 0,
        bat_color,
        track_color,
        text_color,
        border_color,
        na=battery_percent is None,
        value_text=bat_value_text,
        show_value=show_values,
        track_offset=track_offset,
    )


