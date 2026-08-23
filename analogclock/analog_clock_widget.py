"""AnalogClock(QWidget): window behavior, timers, drag/move, paint glue.

This module owns everything window-shaped -- frameless/always-on-top
flags, the four QTimer responsibilities, Wayland-safe dragging with
debounced position persistence, and the paintEvent that delegates all
drawing to analogclock.drawing using state from the colors, timezones,
and hardware controllers.
"""

import sys

from PyQt5.QtCore import QPoint, Qt, QTimer
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QApplication, QDialog, QWidget

from analogclock import config
from analogclock.colors import COLOR_ROLES, ColorController
from analogclock.drawing import draw_clock, draw_hardware_specs
from analogclock.hardware import HardwareMonitor
from analogclock.settings_dialog import SettingsDialog
from analogclock.timezones import DEFAULT_BOTTOM_TZ, DEFAULT_TOP_TZ, TimezonePair, _safe_zoneinfo


class GridOverlay(QWidget):
    """Full-screen translucent overlay that draws the snap grid while dragging.

    The lines are drawn at global coordinates that are multiples of the grid
    spacing, so they line up exactly with the positions the window can snap
    to. The overlay passes mouse events through and never takes focus.
    """

    LINE_ALPHA = 90

    def __init__(self):
        super().__init__()
        self.grid_spacing = 10
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

    def show_grid(self, grid_spacing):
        """Cover the whole virtual desktop and paint the grid."""
        self.grid_spacing = max(5, int(grid_spacing))
        screen = QApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.virtualGeometry())
        self.show()
        self.update()

    def hide_grid(self):
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            spacing = max(5, self.grid_spacing)
            pen = QPen(QColor(255, 255, 255, self.LINE_ALPHA), 1)
            pen.setStyle(Qt.DotLine)
            painter.setPen(pen)

            geo = self.geometry()
            width, height = geo.width(), geo.height()

            # Vertical lines at global multiples of the spacing.
            gx = ((geo.x() + spacing - 1) // spacing) * spacing
            while gx <= geo.x() + width:
                lx = gx - geo.x()
                painter.drawLine(lx, 0, lx, height)
                gx += spacing

            # Horizontal lines at global multiples of the spacing.
            gy = ((geo.y() + spacing - 1) // spacing) * spacing
            while gy <= geo.y() + height:
                ly = gy - geo.y()
                painter.drawLine(0, ly, width, ly)
                gy += spacing
        finally:
            painter.end()


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
    # Grid snapping configuration (controlled via the settings dialog).
    DEFAULT_GRID_SPACING = 10  # pixels
    MIN_GRID_SPACING = 5
    MAX_GRID_SPACING = 150

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

        # Grid snapping: disabled by default so existing saved positions are
        # not disturbed. Overridden on restore or via the settings dialog.
        self.snap_to_grid = False
        self.grid_spacing = self.DEFAULT_GRID_SPACING
        # Full-screen overlay that paints the grid while a drag is active.
        self._grid_overlay = GridOverlay()

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
        # Cursor-to-window-top-left offset captured on press, used to compute
        # absolute drag positions so grid snapping never loses cursor travel.
        self._drag_offset = None

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
            "snap_to_grid": bool(self.snap_to_grid),
            "grid_spacing": int(self.grid_spacing),
            "opacity": round(self.opacity, 3),
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
        # Optional grid-snapping settings -- tolerated missing on older files.
        saved_snap = data.get("snap_to_grid")
        if isinstance(saved_snap, bool):
            self.snap_to_grid = saved_snap
        saved_grid = data.get("grid_spacing")
        if isinstance(saved_grid, int):
            self.grid_spacing = max(
                self.MIN_GRID_SPACING,
                min(self.MAX_GRID_SPACING, saved_grid),
            )
        # Optional opacity -- tolerated missing on older files.
        saved_opacity = data.get("opacity")
        if isinstance(saved_opacity, (int, float)):
            self.opacity = max(
                self.MIN_OPACITY, min(self.MAX_OPACITY, float(saved_opacity))
            )
        self._apply_geometry()

        # Reject positions whose center no longer sits on any connected
        # screen (e.g. saved on an external monitor that is now detached).
        center = QPoint(x + self.width() // 2, y + self.height() // 2)
        if QApplication.screenAt(center) is None:
            return False

        # When grid snapping is enabled, snap the restored position to the grid.
        if self.snap_to_grid:
            x, y = self._snap_position(x, y)

        self.move(x, y)
        return True

    def _snap_value(self, value):
        """Round ``value`` to the nearest multiple of the grid spacing."""
        spacing = max(self.MIN_GRID_SPACING, int(self.grid_spacing))
        return spacing * round(value / spacing)

    def _snap_position(self, x, y):
        """Return ``(x, y)`` snapped to the nearest grid intersection."""
        return self._snap_value(x), self._snap_value(y)

    def apply_grid_settings(self, snap_enabled, grid_spacing):
        """Adopt new snap-to-grid settings from the settings dialog.

        Enabling the setting also snaps the current position to the grid so
        the change is immediately visible.
        """
        self.snap_to_grid = bool(snap_enabled)
        self.grid_spacing = max(
            self.MIN_GRID_SPACING,
            min(self.MAX_GRID_SPACING, int(grid_spacing)),
        )
        if self.snap_to_grid:
            x, y = self._snap_position(self.x(), self.y())
            self.move(x, y)
        self.save_window_position()
        self.update()

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
            # Show the visual snap grid while dragging when snapping is on.
            if self.snap_to_grid:
                self._grid_overlay.show_grid(self.grid_spacing)
            # Native Wayland clients cannot move themselves; hand the drag
            # to the compositor in that case (startSystemMove is ignored on
            # other platforms, so this is a strict fallback).
            if QApplication.platformName().startswith("wayland"):
                handle = self.windowHandle()
                if handle is not None and handle.startSystemMove():
                    return
            self.old_pos = event.globalPos()
            # Capture the cursor's offset from the window top-left so drag
            # positions can be computed absolutely from the cursor.
            self._drag_offset = event.globalPos() - QPoint(self.x(), self.y())

    def mouseMoveEvent(self, event):
        # Require the left button to still be held: guards against a stale
        # old_pos (e.g. a release swallowed mid-compositor-grab) making the
        # window chase the cursor with no button pressed.
        if self.old_pos is not None and (event.buttons() & Qt.LeftButton):
            # Absolute positioning: derive the target from the cursor and the
            # grab offset captured on press. This keeps the window exactly
            # under the cursor even when grid snapping rounds the position,
            # so large spacings never accumulate "lost" mouse travel.
            target = event.globalPos() - self._drag_offset
            if self.snap_to_grid:
                target = QPoint(*self._snap_position(target.x(), target.y()))
            self.move(target.x(), target.y())

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
        self._grid_overlay.hide_grid()
        if event.button() == Qt.LeftButton and self.old_pos is not None:
            self.save_window_position()
        self.old_pos = None
        self._drag_offset = None

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
            self.apply_grid_settings(
                dialog.grid_snap_enabled(), dialog.grid_spacing()
            )
            self.apply_opacity(dialog.chosen_opacity())
            self.update()
            # Single config write for the whole applied change set.
            self.save_window_position()

    def contextMenuEvent(self, event):
        self.open_settings_dialog()


