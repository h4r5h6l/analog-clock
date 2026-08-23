"""AnalogClock(QWidget): window behavior, timers, drag/move, paint glue.

This module owns everything window-shaped -- frameless/always-on-top
flags, the four QTimer responsibilities, Wayland-safe dragging with
debounced position persistence, and the paintEvent that delegates all
drawing to analogclock.drawing using state from the colors, timezones,
and hardware controllers.
"""

import sys

from PyQt5.QtCore import QPoint, Qt, QTimer
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QApplication, QDialog, QWidget

from analogclock import config
from analogclock.colors import COLOR_ROLES, ColorController
from analogclock.drawing import draw_clock, draw_hardware_specs
from analogclock.hardware import HardwareMonitor
from analogclock.settings_dialog import SettingsDialog
from analogclock.timezones import DEFAULT_BOTTOM_TZ, DEFAULT_TOP_TZ, TimezonePair, _safe_zoneinfo


class AnalogClock(QWidget):
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
    # Hardware specs panel (positioned to the right of clocks)
    HARDWARE_PANEL_HEIGHT = 110
    HARDWARE_PANEL_WIDTH = 90
    SPECS_PANEL_SPACING = 24
    WINDOW_HEIGHT = CLOCKS_HEIGHT + CONTROLS_SPACE
    WINDOW_WIDTH = CLOCK_SIZE + (HORIZONTAL_PADDING * 2) + SIDE_SLIDER_SPACE + HARDWARE_PANEL_WIDTH + SPECS_PANEL_SPACING
    KEEP_ON_TOP_SECONDS = 1.5
    # Free dragging vs edge snapping: when False (default) the clock can be
    # dragged freely to any position and remembers it across restarts; when
    # True the legacy bottom-left placement and enterEvent edge snap apply.
    SNAP_TO_EDGE_ENABLED = False

    def __init__(self):
        super().__init__()
        self.always_on_top = True
        self.apply_always_on_top_flags()
        self.setAttribute(Qt.WA_TranslucentBackground)
        # keep the clock window at 60% opacity for consistent transparency
        self.setWindowOpacity(0.60)
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
        # enlarge window height to include the top control area
        self.setFixedSize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT + self.top_control_offset)
        # Update hardware stats immediately
        self.hardware.poll()
        # Free-drag mode: restore the last saved position; only fall back to
        # the legacy bottom-left placement when nothing valid is saved (or
        # when edge snapping is explicitly enabled).
        if self.SNAP_TO_EDGE_ENABLED or not self.restore_from_config():
            self.move_to_bottom_left()

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

        # Draw clocks and specs content
        draw_clock(painter, clocks_x, top_y, top_now, self.CLOCK_SIZE, palette)
        draw_clock(
            painter,
            clocks_x,
            top_y + self.CLOCK_SIZE + self.CLOCK_SPACING,
            bottom_now,
            self.CLOCK_SIZE,
            palette,
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
        )

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
            self.update()
            # Single config write for the whole applied change set.
            self.save_window_position()

    def contextMenuEvent(self, event):
        self.open_settings_dialog()


