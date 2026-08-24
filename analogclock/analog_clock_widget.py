"""AnalogClock(QWidget): window behavior, timers, drag/move, paint glue.

This module owns everything window-shaped -- frameless/always-on-top
flags, the four QTimer responsibilities, Wayland-safe dragging with
debounced position persistence, and the paintEvent that delegates all
drawing to analogclock.drawing using state from the colors, timezones,
and hardware controllers.
"""

import sys

from PyQt5.QtCore import QPoint, Qt, QTimer, QRect
from PyQt5.QtGui import QColor, QFont, QPainter, QFontMetrics
from PyQt5.QtWidgets import QApplication, QDialog, QWidget

from analogclock import config
from analogclock.colors import COLOR_ROLES, ColorController
from analogclock.drawing import draw_clock, draw_hardware_specs
from analogclock.hardware import HardwareMonitor
from analogclock.settings_dialog import SettingsDialog
from analogclock.timezones import DEFAULT_BOTTOM_TZ, DEFAULT_TOP_TZ, TimezonePair, _safe_zoneinfo


class AnalogClock(QWidget):
    # Default and bounds for the new clock-size appearance control. A clock
    # face of DEFAULT_CLOCK_SIZE is drawn on a 200-px logical canvas (see
    # draw_clock's `size / 200`); CLOCK_SIZE scales that whole canvas.
    DEFAULT_CLOCK_SIZE = 160
    MIN_CLOCK_SIZE = 80
    MAX_CLOCK_SIZE = 360
    # Default and bounds for the new font-size appearance control (specs text).
    DEFAULT_FONT_SIZE = 10
    MIN_FONT_SIZE = 6
    MAX_FONT_SIZE = 32
    # Translucency of the clock face and the hardware-panel background sheet
    # (hands, ticks, text and borders stay fully opaque). Slider is in percent.
    DEFAULT_OPACITY = 0.60
    MIN_OPACITY = 0.20
    MAX_OPACITY = 1.0
    CLOCK_SIZE = 160
    # smaller gap between stacked clocks to bring faces closer together
    CLOCK_SPACING = 6
    HORIZONTAL_PADDING = 20
    # reduce reserved right-side space so the window doesn't grab the cursor area
    SIDE_SLIDER_SPACE = 6
    CONTROLS_SPACE = 34
    # vertical gap between top clock and control buttons when placed above
    BUTTON_TOP_GAP = 44
    # (top control area reserved for controls)
    CLOCKS_HEIGHT = CLOCK_SIZE * 2 + CLOCK_SPACING
    # Hardware specs panel (positioned to the right of clocks). The *_BASE
    # values are the panel size at DEFAULT_CLOCK_SIZE; _apply_geometry scales
    # them with the clock so the background sheet grows with it.
    HARDWARE_PANEL_HEIGHT_BASE = 110
    HARDWARE_PANEL_WIDTH_BASE = 90
    SPECS_PANEL_SPACING = 24
    WINDOW_HEIGHT = CLOCKS_HEIGHT + CONTROLS_SPACE
    WINDOW_WIDTH = CLOCK_SIZE + (HORIZONTAL_PADDING * 2) + SIDE_SLIDER_SPACE + HARDWARE_PANEL_WIDTH_BASE + SPECS_PANEL_SPACING
    KEEP_ON_TOP_SECONDS = 1.5
    # Eye toggle button for always-on-top feature
    EYE_BUTTON_SIZE = 20
    EYE_BUTTON_MARGIN = 8
    # Free dragging vs edge snapping: when False (default) the clock can be
    # dragged freely to any position and remembers it across restarts; when
    # True the legacy bottom-left placement and enterEvent edge snap apply.
    SNAP_TO_EDGE_ENABLED = False

    def __init__(self):
        super().__init__()
        self.always_on_top = True
        self.apply_always_on_top_flags()
        self.setAttribute(Qt.WA_TranslucentBackground)
        # Translucency applied to the clock face and the hardware-panel sheet
        # (not the whole window, so hands/ticks/text stay sharp). Controlled by
        # the settings dialog opacity slider; defaults to the prior 60%.
        self.opacity = self.DEFAULT_OPACITY
        self.setFixedSize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)

        # ---- Extracted controllers --------------------------------------
        self.hardware = HardwareMonitor()
        self.colors = ColorController()
        self.timezones = TimezonePair(DEFAULT_TOP_TZ, DEFAULT_BOTTOM_TZ)

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update)
        self.clock_timer.start(1000)
        # Hardware stats timer - updates every 2 seconds; refreshes the
        # on-screen stats too.
        self.hardware_timer = QTimer(self)
        self.hardware_timer.timeout.connect(self._on_hardware_poll)
        self.hardware_timer.start(2000)
        self.visibility_timer = QTimer(self)
        self.visibility_timer.timeout.connect(self.ensure_on_top)
        self.visibility_timer.start(round(self.KEEP_ON_TOP_SECONDS * 1000))

        # Debounced autosave: any window move restarts this timer, so bursts
        # of move events (drags, programmatic placements) collapse into a
        # single config write ~0.5s after motion stops. Drag releases still
        # save immediately via mouseReleaseEvent.
        self._position_save_timer = QTimer(self)
        self._position_save_timer.setSingleShot(True)
        self._position_save_timer.setInterval(500)
        self._position_save_timer.timeout.connect(self.save_window_position)
        self.old_pos = None

        # reserve a smaller top control area so the clock is closer to the cursor
        self.top_control_offset = 12
        # Mutable appearance state (defaults; overridden on restore or via the
        # settings dialog). Instance attrs so each clock can deviate from the
        # class defaults independently.
        self.CLOCK_SIZE = self.DEFAULT_CLOCK_SIZE
        self.font_size = self.DEFAULT_FONT_SIZE
        # Recompute clock/panel/window geometry from the current size and fix
        # the window to the new size (includes the reserved top control area).
        self._apply_geometry()
        # Update hardware stats immediately
        self.hardware.poll()
        # Free-drag mode: restore the last saved position; only fall back to
        # the legacy bottom-left placement when nothing valid is saved (or
        # when edge snapping is explicitly enabled).
        if self.SNAP_TO_EDGE_ENABLED or not self.restore_from_config():
            self.move_to_bottom_left()

    # ---- Geometry / sizing ---------------------------------------------------

    def _apply_geometry(self):
        """Recompute clock panel and window geometry from the current clock size.

        ``CLOCK_SIZE`` scales the stacked faces (draw_clock normalizes via
        ``size / 200``); the hardware panel and its background sheet scale with
        it through the ``*_BASE`` ratios, so a larger clock grows both faces
        **and** the background sheet.
        """
        panel_w_ratio = self.HARDWARE_PANEL_WIDTH_BASE / self.DEFAULT_CLOCK_SIZE
        panel_h_ratio = self.HARDWARE_PANEL_HEIGHT_BASE / self.DEFAULT_CLOCK_SIZE
        self.HARDWARE_PANEL_WIDTH = max(1, round(self.CLOCK_SIZE * panel_w_ratio))
        self.HARDWARE_PANEL_HEIGHT = max(1, round(self.CLOCK_SIZE * panel_h_ratio))
        self.CLOCKS_HEIGHT = self.CLOCK_SIZE * 2 + self.CLOCK_SPACING
        self.WINDOW_WIDTH = (
            self.CLOCK_SIZE
            + (self.HORIZONTAL_PADDING * 2)
            + self.SIDE_SLIDER_SPACE
            + self.HARDWARE_PANEL_WIDTH
            + self.SPECS_PANEL_SPACING
        )
        self.WINDOW_HEIGHT = self.CLOCKS_HEIGHT + self.CONTROLS_SPACE
        self.setFixedSize(
            self.WINDOW_WIDTH,
            self.WINDOW_HEIGHT + getattr(self, "top_control_offset", 0),
        )

    def apply_display_size(self, clock_size, font_size):
        """Apply user-chosen clock and font sizes, then re-layout and repaint."""
        self.CLOCK_SIZE = max(
            self.MIN_CLOCK_SIZE, min(self.MAX_CLOCK_SIZE, int(clock_size))
        )
        self.font_size = max(
            self.MIN_FONT_SIZE, min(self.MAX_FONT_SIZE, int(font_size))
        )
        self._apply_geometry()
        self.update()

    def apply_opacity(self, opacity):
        """Apply face/sheet opacity (0.0..1.0) from the settings dialog."""
        self.opacity = max(self.MIN_OPACITY, min(self.MAX_OPACITY, float(opacity)))
        self.update()

    # ---- Window flags / visibility -----------------------------------------

    def apply_always_on_top_flags(self):
        flags = Qt.FramelessWindowHint | Qt.Tool
        # only add the always-on-top / bypass hint when requested
        if getattr(self, "always_on_top", True):
            flags |= Qt.WindowStaysOnTopHint
            if sys.platform.startswith("linux"):
                flags |= Qt.X11BypassWindowManagerHint
        self.setWindowFlags(flags)

    def ensure_on_top(self):
        if self.windowState() & Qt.WindowMinimized:
            self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        if not self.isVisible():
            self.show()
        # only force raise when the clock is meant to stay on top
        if getattr(self, "always_on_top", True):
            self.raise_()

    def keep_visible(self):
        if self.windowState() & Qt.WindowMinimized:
            self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.show()
        # respect the user's toggle: don't force-focus if not always-on-top
        if getattr(self, "always_on_top", True):
            self.raise_()
            self.activateWindow()

    def changeEvent(self, event):
        if event.type() == event.WindowStateChange and self.windowState() & Qt.WindowMinimized:
            QTimer.singleShot(0, self.keep_visible)
            QTimer.singleShot(100, self.keep_visible)
        super().changeEvent(event)

    # ---- Placement ----------------------------------------------------------

    def move_to_bottom_left(self):
        screen = QApplication.screenAt(self.mapToGlobal(self.rect().center()))
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            return

        geometry = screen.availableGeometry()
        left_margin = round(geometry.width() * 0.1)
        x = geometry.left() + left_margin
        y = self.bottom_y(geometry)
        self.move(x, y)

    def bottom_y(self, geometry):
        return geometry.bottom() - self.height() + 1

    # ---- Persistence glue (JSON I/O lives in analogclock.config) ------------

    def save_window_position(self):
        """Persist window x/y plus appearance settings so they survive restarts."""
        payload = {
            "x": int(self.x()),
            "y": int(self.y()),
            "manual_colors": {
                role: self.colors.manual_colors[role].name()
                for role in COLOR_ROLES
                if role in self.colors.manual_colors
            },
            "top_timezone": self.timezones.top_name,
            "bottom_timezone": self.timezones.bottom_name,
            "clock_size": int(self.CLOCK_SIZE),
            "font_size": int(self.font_size),
            "opacity": round(self.opacity, 3),
            "always_on_top": bool(self.always_on_top),
        }
        config.save_window_position(payload)

    def restore_from_config(self):
        """Restore a previously saved position.

        Returns True when a saved position was applied, False when it is
        missing, corrupt, or off-screen (caller falls back to default
        placement).
        """
        data = config.restore_window_position()
        if not isinstance(data, dict):
            return False

        try:
            x = int(data["x"])
            y = int(data["y"])
        except (OSError, ValueError, TypeError, KeyError):
            return False

        # Optional appearance settings -- tolerated missing on older files.
        saved_colors = data.get("manual_colors")
        if isinstance(saved_colors, dict):
            for role in COLOR_ROLES:
                value = saved_colors.get(role)
                if isinstance(value, str):
                    color = QColor(value)
                    if color.isValid():
                        self.colors.manual_colors[role] = color

        # Optional timezone settings -- tolerated missing on older files.
        saved_top_tz = data.get("top_timezone")
        new_top = (
            saved_top_tz
            if isinstance(saved_top_tz, str) and _safe_zoneinfo(saved_top_tz)
            else self.timezones.top_name
        )
        saved_bottom_tz = data.get("bottom_timezone")
        new_bottom = (
            saved_bottom_tz
            if isinstance(saved_bottom_tz, str) and _safe_zoneinfo(saved_bottom_tz)
            else self.timezones.bottom_name
        )
        self.timezones.set(new_top, new_bottom)

        # Optional display-size settings -- tolerated missing on older files.
        # Applied (and geometry recomputed) before the screen-position check
        # below, since the window size depends on the chosen clock size.
        saved_clock_size = data.get("clock_size")
        if isinstance(saved_clock_size, int):
            self.CLOCK_SIZE = max(
                self.MIN_CLOCK_SIZE, min(self.MAX_CLOCK_SIZE, saved_clock_size)
            )
        saved_font_size = data.get("font_size")
        if isinstance(saved_font_size, int):
            self.font_size = max(
                self.MIN_FONT_SIZE, min(self.MAX_FONT_SIZE, saved_font_size)
            )
        # Optional opacity -- tolerated missing on older files.
        saved_opacity = data.get("opacity")
        if isinstance(saved_opacity, (int, float)):
            self.opacity = max(
                self.MIN_OPACITY, min(self.MAX_OPACITY, float(saved_opacity))
            )
        # Optional always-on-top setting -- tolerated missing on older files.
        saved_aot = data.get("always_on_top")
        if isinstance(saved_aot, bool):
            self.always_on_top = saved_aot
        self._apply_geometry()

        # Re-apply window flags to honor any restored always-on-top setting.
        self.apply_always_on_top_flags()

        # Reject positions whose center no longer sits on any connected
        # screen (e.g. saved on an external monitor that is now detached).
        center = QPoint(x + self.width() // 2, y + self.height() // 2)
        if QApplication.screenAt(center) is None:
            return False

        self.move(x, y)
        return True

    def set_timezones(self, top_name, bottom_name):
        """Adopt new timezone strings; invalid ones fall back to local time."""
        self.timezones.set(top_name, bottom_name)
        self.update()
        self.save_window_position()

    # ---- Timers / hardware --------------------------------------------------

    def _on_hardware_poll(self):
        self.hardware.poll()
        self.update()

    # ---- Dragging (Wayland-safe) ---------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Check if the click is on the eye toggle button
            if self.eye_button_rect().contains(event.pos()):
                self.toggle_always_on_top()
                return
            # Native Wayland clients cannot move themselves; hand the drag
            # to the compositor in that case (startSystemMove is ignored on
            # other platforms, so this is a strict fallback).
            if QApplication.platformName().startswith("wayland"):
                handle = self.windowHandle()
                if handle is not None and handle.startSystemMove():
                    return
            self.old_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        # Require the left button to still be held: guards against a stale
        # old_pos (e.g. a release swallowed mid-compositor-grab) making the
        # window chase the cursor with no button pressed.
        if self.old_pos is not None and (event.buttons() & Qt.LeftButton):
            delta = event.globalPos() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPos()

    def moveEvent(self, event):
        super().moveEvent(event)
        # Persist position wherever it came from (drag, restore, dialog).
        # Guarded: moves can occur inside __init__ before the timer exists.
        timer = getattr(self, "_position_save_timer", None)
        if timer is not None:
            timer.start()

    def enterEvent(self, event):
        # Edge snapping conflicts with free dragging; only snap when the
        # legacy behavior is explicitly re-enabled via SNAP_TO_EDGE_ENABLED.
        if not self.SNAP_TO_EDGE_ENABLED:
            super().enterEvent(event)
            return

        screen = QApplication.screenAt(self.mapToGlobal(self.rect().center()))
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            return

        geometry = screen.availableGeometry()
        window_right = self.x() + self.width()
        dist_left = self.x() - geometry.left()
        dist_right = geometry.right() - window_right
        margin = round(geometry.width() * 0.1)

        if dist_left >= dist_right:
            x = geometry.left() + margin
        else:
            x = geometry.right() - self.width() - margin + 1

        self.move(x, self.bottom_y(geometry))
        super().enterEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.old_pos is not None:
            self.save_window_position()
        self.old_pos = None

    # ---- Painting -------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            self.paint_clocks_and_specs(painter)
            self.draw_eye_button(painter)
        finally:
            # Release the paint device immediately. Letting the painter stay
            # active past this event makes every following begin/end cycle log
            # "QPainter::begin" / "QBackingStore::endPaint()" warnings.
            painter.end()

    def paint_clocks_and_specs(self, painter):
        painter.setRenderHint(QPainter.Antialiasing)
        top_now = self.timezones.now_top()
        bottom_now = self.timezones.now_bottom()
        scale = self.CLOCK_SIZE / 200
        margin = 10 * scale
        # Stack the two clocks vertically; account for reserved top control area
        clocks_x = self.HORIZONTAL_PADDING
        top_y = margin + getattr(self, 'top_control_offset', 0)

        palette = self.colors.resolved_palette()

        # Draw clocks and specs content. Opacity makes only the faces (and the
        # hardware sheet) translucent; hands, ticks and borders stay opaque.
        draw_clock(painter, clocks_x, top_y, top_now, self.CLOCK_SIZE, palette, opacity=self.opacity)
        draw_clock(
            painter,
            clocks_x,
            top_y + self.CLOCK_SIZE + self.CLOCK_SPACING,
            bottom_now,
            self.CLOCK_SIZE,
            palette,
            opacity=self.opacity,
        )

        # Hardware specs panel (positioned to the right of clocks, vertically
        # centered); draw_hardware_specs paints its own rounded sheet.
        panel_x = clocks_x + self.CLOCK_SIZE + self.SPECS_PANEL_SPACING
        panel_y = top_y + (self.CLOCKS_HEIGHT - self.HARDWARE_PANEL_HEIGHT) / 2
        draw_hardware_specs(
            painter,
            panel_x,
            panel_y,
            self.HARDWARE_PANEL_WIDTH,
            self.HARDWARE_PANEL_HEIGHT,
            self.hardware.stats_snapshot(),
            palette,
            font_size=self.font_size,
            opacity=self.opacity,
        )

    # ---- Eye toggle button ------------------------------------------------------

    def eye_button_rect(self):
        """Return the screen-rect for the always-on-top eye toggle button."""
        x = self.EYE_BUTTON_MARGIN
        y = self.EYE_BUTTON_MARGIN + getattr(self, 'top_control_offset', 0) - 5
        return QRect(x, y, self.EYE_BUTTON_SIZE, self.EYE_BUTTON_SIZE)

    def draw_eye_button(self, painter):
        """Draw the eye toggle button in the top-left corner.
        
        The button's opacity is tied to the clock face opacity setting, with a
        minimum alpha floor so the control stays tappable even at low opacity.
        """
        painter.save()
        try:
            rect = self.eye_button_rect()

            # Apply the same opacity as the clock face/sheet, with a floor so
            # the button remains visible and tappable at very low opacities.
            button_opacity = max(0.4, self.opacity)
            painter.setOpacity(button_opacity)

            # Button background (semi-transparent rounded rect)
            palette = self.colors.resolved_palette()
            bg_color = QColor(palette["sheet_color"])
            bg_color.setAlpha(int(180 * button_opacity))
            painter.setPen(Qt.NoPen)
            painter.setBrush(bg_color)
            painter.drawRoundedRect(rect, 4, 4)

            # Border
            border_color = QColor(palette["border_color"])
            painter.setPen(border_color)
            painter.drawRoundedRect(rect, 4, 4)

            # Eye icon - use Unicode characters
            # 👁️ (U+1F441 U+FE0F) for enabled/on-top, 🚫 for disabled
            font = QFont("Arial", 10, QFont.Bold)
            painter.setFont(font)
            fm = QFontMetrics(font)

            if self.always_on_top:
                # Eye open symbol (Unicode: U+1F441 U+FE0F)
                icon_text = "👁️"
            else:
                # Stop sign for disabled state
                icon_text = "🚫"

            # Center the text in the button
            text_width = fm.horizontalAdvance(icon_text)
            text_height = fm.height()
            text_x = rect.center().x() - text_width // 2
            text_y = rect.center().y() + text_height // 2 - 2
            painter.setPen(QColor(palette["hand_color"]))
            painter.drawText(text_x, text_y, icon_text)
        finally:
            painter.restore()

    def toggle_always_on_top(self):
        """Toggle the always-on-top state and reapply window flags."""
        self.always_on_top = not self.always_on_top
        self.apply_always_on_top_flags()
        self.save_window_position()
        self.update()

    # ---- Settings dialog ------------------------------------------------------

    def _build_settings_dialog(self):
        return SettingsDialog(self)

    def _place_beside_clock(self, dialog):
        """Position the settings dialog right (or left) of the clock window.

        Right side is preferred; if it does not fit on the clock's screen,
        the dialog flips to the left side. When neither side fits completely
        (small screens), the side with more free room wins and the dialog is
        clamped to stay fully on-screen. Vertically it aligns with the
        clock's top edge, clamped to the screen.
        """
        screen = QApplication.screenAt(self.mapToGlobal(self.rect().center()))
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            return

        geometry = screen.availableGeometry()
        dialog.adjustSize()
        size = dialog.frameGeometry().size()
        width = size.width()
        height = size.height()

        gap = 8
        right_x = self.x() + self.width() + gap
        left_x = self.x() - gap - width
        fits_right = right_x + width <= geometry.right() + 1
        fits_left = left_x >= geometry.left()

        if fits_right:
            x = right_x
        elif fits_left:
            x = left_x
        else:
            # Neither side fits fully: take whichever has more free room.
            room_right = geometry.right() + 1 - (self.x() + self.width())
            room_left = self.x() - geometry.left()
            if room_right >= room_left:
                x = right_x
            else:
                x = left_x
            # Clamp so the dialog stays fully visible on this screen.
            x = max(geometry.left(), min(x, geometry.right() - width + 1))

        y = self.y()
        y = max(geometry.top(), min(y, geometry.bottom() - height + 1))
        dialog.move(x, y)

    def open_settings_dialog(self):
        dialog = self._build_settings_dialog()
        # The clock itself is an always-on-top, window-manager-bypassing tool
        # window, so a plain dialog stacks underneath it. Give the dialog the
        # same stay-on-top hint, show it beside the clock (right preferred,
        # left otherwise), bring it above, then run the modal loop on the
        # already-visible dialog.
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowStaysOnTopHint)
        dialog.show()
        self._place_beside_clock(dialog)
        dialog.raise_()
        dialog.activateWindow()
        if dialog.exec_() == QDialog.Accepted:
            self.colors.apply_appearance_settings(dialog.chosen_colors())
            self.timezones.set(
                dialog.top_timezone_text(), dialog.bottom_timezone_text()
            )
            self.apply_display_size(
                dialog.chosen_clock_size(), dialog.chosen_font_size()
            )
            self.apply_opacity(dialog.chosen_opacity())

            # Apply always-on-top setting dynamically
            new_aot = dialog.always_on_top()
            if new_aot != self.always_on_top:
                self.always_on_top = new_aot
                self.apply_always_on_top_flags()

            self.update()
            # Single config write for the whole applied change set.
            self.save_window_position()

    def contextMenuEvent(self, event):
        self.open_settings_dialog()


