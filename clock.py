from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
)
from PyQt5.QtCore import QTimer, Qt, QRectF, QPoint
from PyQt5.QtGui import QPainter, QPen, QColor, QBrush
import json
import os
import sys
import math
import time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones
import psutil
import subprocess
import shutil
try:
    import GPUtil
    HAS_GPU_SUPPORT = True
except ImportError:
    HAS_GPU_SUPPORT = False
from background_sheet import draw_background_sheet

# This clock positions itself (bottom-left placement, restored saved
# position, free dragging) and samples the pixels behind it for contrast.
# Both need client-side window positioning, which the native Wayland
# platform plugin cannot do -- every self.move() would be silently ignored
# by the compositor. Route through XWayland (xcb) on Linux unless the user
# chose a platform explicitly. Guarded so headless/offscreen setups without
# an X display are unaffected.
if (
    sys.platform.startswith("linux")
    and not os.environ.get("QT_QPA_PLATFORM")
    and os.environ.get("DISPLAY")
):
    os.environ["QT_QPA_PLATFORM"] = "xcb"

class SettingsDialog(QDialog):
    """Modal settings panel: contrast mode, fixed colors, clock timezones."""

    ROLE_LABELS = {
        "face_color": "Face",
        "hand_color": "Hands",
        "tick_color": "Ticks",
        "border_color": "Border",
    }

    def __init__(self, clock, parent=None):
        super().__init__(parent or clock)
        self.setWindowTitle("Analog Clock settings")
        self._clock = clock
        self._chosen_colors = dict(clock.manual_colors)

        layout = QVBoxLayout(self)

        self.auto_check = QCheckBox("Use automatic contrast colors", self)
        self.auto_check.setChecked(clock.use_auto_contrast)
        layout.addWidget(self.auto_check)

        color_group = QGroupBox("Fixed colors (used when auto contrast is off)", self)
        color_grid = QGridLayout(color_group)
        self._color_buttons = {}
        for row, role in enumerate(clock.COLOR_ROLES):
            button = QPushButton(
                SettingsDialog.ROLE_LABELS[role] + " color...", color_group
            )
            button.setToolTip(f"Pick a fixed {role.replace('_', ' ')}")
            self._paint_swatch(button, clock.manual_colors[role])
            button.clicked.connect(
                lambda checked=False, r=role, b=button: self._pick(r, b)
            )
            color_grid.addWidget(button, row, 0)
            self._color_buttons[role] = button
        layout.addWidget(color_group)

        tz_group = QGroupBox("Clock timezones", self)
        tz_grid = QGridLayout(tz_group)
        tz_grid.addWidget(QLabel("Top clock:", tz_group), 0, 0)
        self.top_tz_combo = self._make_tz_combo(clock.top_tz_name)
        tz_grid.addWidget(self.top_tz_combo, 0, 1)
        tz_grid.addWidget(QLabel("Bottom clock:", tz_group), 1, 0)
        self.bottom_tz_combo = self._make_tz_combo(clock.bottom_tz_name)
        tz_grid.addWidget(self.bottom_tz_combo, 1, 1)
        layout.addWidget(tz_group)

        dialog_buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self
        )
        dialog_buttons.accepted.connect(self.accept)
        dialog_buttons.rejected.connect(self.reject)
        layout.addWidget(dialog_buttons)

        # Color pickers only make sense in manual mode.
        self.auto_check.toggled.connect(self._sync_enabled)
        self._sync_enabled()

    # -- helpers -----------------------------------------------------------

    def _make_tz_combo(self, current_name):
        combo = QComboBox(self)
        combo.setEditable(True)
        try:
            names = sorted(available_timezones())
        except Exception:
            names = []
        combo.addItems(names)
        combo.setCurrentText(current_name)
        return combo

    def _paint_swatch(self, button, color):
        button.setStyleSheet(f"QPushButton {{ background-color: {color.name()}; }}")

    def _pick(self, role, button):
        initial = self._chosen_colors.get(role, QColor("#ffffff"))
        chosen = QColorDialog.getColor(
            initial, self, f"Choose {role.replace('_', ' ')}"
        )
        if chosen.isValid():
            self._chosen_colors[role] = chosen
            self._paint_swatch(button, chosen)

    def _sync_enabled(self):
        manual_mode = not self.auto_check.isChecked()
        for button in self._color_buttons.values():
            button.setEnabled(manual_mode)

    # -- values read back by AnalogClock.open_settings_dialog --------------

    def use_auto_contrast_checked(self):
        return self.auto_check.isChecked()

    def chosen_colors(self):
        return dict(self._chosen_colors)

    def top_timezone_text(self):
        return self.top_tz_combo.currentText().strip()

    def bottom_timezone_text(self):
        return self.bottom_tz_combo.currentText().strip()


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
    # (opacity control removed)
    COLOR_TRANSITION_SECONDS = 0.35
    CONTRAST_CHECK_SECONDS = 0.2
    KEEP_ON_TOP_SECONDS = 1.5
    # Free dragging vs edge snapping: when False (default) the clock can be
    # dragged freely to any position and remembers it across restarts; when
    # True the legacy bottom-left placement and enterEvent edge snap apply.
    SNAP_TO_EDGE_ENABLED = False
    # Where the last window x/y and appearance settings are persisted
    # (written on drag release and whenever colors/auto-contrast change).
    POSITION_CONFIG_DIR = Path.home() / ".config" / "analog-clock"
    POSITION_CONFIG_PATH = POSITION_CONFIG_DIR / "window_position.json"
    # The four manually configurable color roles (see manual_colors).
    COLOR_ROLES = ("face_color", "hand_color", "tick_color", "border_color")

    def __init__(self):
        super().__init__()
        self.always_on_top = True
        self.apply_always_on_top_flags()
        self.setAttribute(Qt.WA_TranslucentBackground)
        # keep the clock window at 60% opacity for consistent transparency
        self.setWindowOpacity(0.60)
        self.setFixedSize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        # Hardware stats storage
        self.cpu_percent = 0
        self.ram_percent = 0
        self.gpu_percent = 0
        self.gpu_vram_percent = 0
        self.gpu_available = False
        # opacity controls removed; reserve a top control area instead
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update)
        self.clock_timer.start(1000)
        # Hardware stats timer - updates every 2 seconds
        self.hardware_timer = QTimer(self)
        self.hardware_timer.timeout.connect(self.update_hardware_stats)
        # refresh the on-screen stats too (the old 60fps loop used to do this)
        self.hardware_timer.timeout.connect(self.update)
        self.hardware_timer.start(2000)
        # ---- Color scheme ---------------------------------------------
        # use_auto_contrast=True  -> colors adapt automatically to the
        #     desktop luminance sampled behind the window (original behavior).
        # use_auto_contrast=False -> the fixed palette below is used instead;
        #     edit the QColor values (or "#rrggbb" strings) to taste.
        self.use_auto_contrast = True
        self.manual_colors = {
            "face_color": QColor(255, 255, 255),   # clock face fill
            "hand_color": QColor(0, 0, 0),         # hour/minute/second hands + hub
            "tick_color": QColor(0, 0, 0),         # tick marks around the face
            "border_color": QColor(255, 255, 255), # outlines, halos, hub ring
        }
        self.display_color = QColor(Qt.black)
        self.start_color = QColor(self.display_color)
        self.target_color = QColor(self.display_color)
        self.transition_started_at = time.monotonic()
        self.last_contrast_check = 0
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.update_contrast_transition)
        self.animation_timer.start(16)
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
        # Clock timezones -- configurable from the right-click settings
        # dialog. An invalid name falls back to system local time.
        self.top_tz_name = "Europe/Berlin"
        self.bottom_tz_name = "Asia/Kolkata"
        self.top_tz = self._safe_zoneinfo(self.top_tz_name)
        self.bottom_tz = self._safe_zoneinfo(self.bottom_tz_name)
        self.update_control_colors()
        # reserve a smaller top control area so the clock is closer to the cursor
        # reduce the invisible padding above the topmost clock
        self.top_control_offset = 12
        # enlarge window height to include the top control area
        self.setFixedSize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT + self.top_control_offset)
        # Update hardware stats immediately
        self.update_hardware_stats()
        # Free-drag mode: restore the last saved position; only fall back to
        # the legacy bottom-left placement when nothing valid is saved (or
        # when edge snapping is explicitly enabled).
        if self.SNAP_TO_EDGE_ENABLED or not self.restore_window_position():
            self.move_to_bottom_left()

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

    def save_window_position(self):
        """Persist window x/y plus appearance settings so they survive restarts."""
        try:
            self.POSITION_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "x": int(self.x()),
                "y": int(self.y()),
                "use_auto_contrast": bool(self.use_auto_contrast),
                "manual_colors": {
                    role: self.manual_colors[role].name()
                    for role in self.COLOR_ROLES
                    if role in self.manual_colors
                },
                "top_timezone": self.top_tz_name,
                "bottom_timezone": self.bottom_tz_name,
            }
            self.POSITION_CONFIG_PATH.write_text(json.dumps(payload))
        except (OSError, ValueError):
            # Persistence is best-effort; never break dragging over it.
            pass

    def restore_window_position(self):
        """Restore a previously saved window position.

        Returns True when a saved position was applied, False when it is
        missing, corrupt, or off-screen (caller falls back to default
        placement).
        """
        try:
            data = json.loads(self.POSITION_CONFIG_PATH.read_text())
            x = int(data["x"])
            y = int(data["y"])
        except (OSError, ValueError, TypeError, KeyError):
            return False

        # Optional appearance settings -- tolerated missing on older files.
        if isinstance(data.get("use_auto_contrast"), bool):
            self.use_auto_contrast = data["use_auto_contrast"]
        saved_colors = data.get("manual_colors")
        if isinstance(saved_colors, dict):
            for role in self.COLOR_ROLES:
                value = saved_colors.get(role)
                if isinstance(value, str):
                    color = QColor(value)
                    if color.isValid():
                        self.manual_colors[role] = color

        # Optional timezone settings -- tolerated missing on older files.
        saved_top_tz = data.get("top_timezone")
        if isinstance(saved_top_tz, str) and self._safe_zoneinfo(saved_top_tz):
            self.top_tz_name = saved_top_tz
            self.top_tz = self._safe_zoneinfo(saved_top_tz)
        saved_bottom_tz = data.get("bottom_timezone")
        if isinstance(saved_bottom_tz, str) and self._safe_zoneinfo(saved_bottom_tz):
            self.bottom_tz_name = saved_bottom_tz
            self.bottom_tz = self._safe_zoneinfo(saved_bottom_tz)

        # Reject positions whose center no longer sits on any connected
        # screen (e.g. saved on an external monitor that is now detached).
        center = QPoint(x + self.width() // 2, y + self.height() // 2)
        if QApplication.screenAt(center) is None:
            return False

        self.move(x, y)
        return True

    # opacity controls and top-positioning for buttons removed

    def update_control_colors(self):
        clock_color = QColor(self.display_color)
        border_color = self.opposite_color(clock_color)

    def battery_percent(self):
        power_supply_path = Path("/sys/class/power_supply")
        if not power_supply_path.exists():
            return None

        for battery_path in sorted(power_supply_path.glob("BAT*")):
            capacity_path = battery_path / "capacity"
            if not capacity_path.exists():
                continue

            try:
                return max(0, min(100, int(capacity_path.read_text().strip())))
            except (OSError, ValueError):
                continue

        return None

    def battery_power_state(self):
        power_supply_path = Path("/sys/class/power_supply")
        if not power_supply_path.exists():
            return None

        for battery_path in sorted(power_supply_path.glob("BAT*")):
            status_path = battery_path / "status"
            if not status_path.exists():
                continue

            try:
                status = status_path.read_text().strip().lower()
            except OSError:
                continue

            if status == "discharging":
                return "BAT"
            if status in ("charging", "full", "not charging"):
                return "AC"

        return None

    def update_hardware_stats(self):
        """Update CPU, RAM, GPU, and VRAM usage percentages."""
        try:
            self.cpu_percent = psutil.cpu_percent(interval=0.1)
        except Exception:
            self.cpu_percent = 0

        try:
            self.ram_percent = psutil.virtual_memory().percent
        except Exception:
            self.ram_percent = 0
        # Attempt to get GPU stats via GPUtil (if available)
        self.gpu_available = False
        if HAS_GPU_SUPPORT:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu = gpus[0]
                    # GPUtil provides load as a float 0..1
                    self.gpu_percent = (gpu.load or 0.0) * 100
                    # memoryUsed and memoryTotal may be provided (MB)
                    total = getattr(gpu, 'memoryTotal', 0) or 0
                    used = getattr(gpu, 'memoryUsed', 0) or 0
                    self.gpu_vram_percent = (used / total) * 100 if total > 0 else 0.0
                    self.gpu_available = True
            except Exception:
                self.gpu_available = False

        # Fallback: try nvidia-smi if GPUtil is unavailable or didn't return data
        if not self.gpu_available:
            try:
                if shutil.which('nvidia-smi'):
                    cmd = [
                        'nvidia-smi',
                        '--query-gpu=utilization.gpu,memory.total,memory.used',
                        '--format=csv,noheader,nounits',
                    ]
                    out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
                    first_line = out.strip().splitlines()[0]
                    parts = [p.strip() for p in first_line.split(',')]
                    if len(parts) >= 3:
                        util = 0.0 if parts[0] in ('N/A', '') else float(parts[0])
                        mem_total = 0.0 if parts[1] in ('N/A', '') else float(parts[1])
                        mem_used = 0.0 if parts[2] in ('N/A', '') else float(parts[2])
                        self.gpu_percent = util
                        self.gpu_vram_percent = (mem_used / mem_total) * 100 if mem_total > 0 else 0.0
                        self.gpu_available = True
            except Exception:
                # any errors mean GPU info is not available via this fallback
                self.gpu_available = False

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

    def contrast_color(self):
        screen = QApplication.screenAt(self.mapToGlobal(self.rect().center()))
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            return Qt.black

        center = self.mapToGlobal(self.rect().center())
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
                self.update()
            return

        now = time.monotonic()
        if now - self.last_contrast_check >= self.CONTRAST_CHECK_SECONDS:
            self.last_contrast_check = now
            contrast_color = QColor(self.contrast_color())
            if contrast_color != self.target_color:
                self.start_color = QColor(self.display_color)
                self.target_color = contrast_color
                self.transition_started_at = now

        elapsed = now - self.transition_started_at
        progress = min(1.0, elapsed / self.COLOR_TRANSITION_SECONDS)
        eased = progress * progress * (3 - (2 * progress))
        previous_color = QColor(self.display_color)
        red = self.start_color.red() + (self.target_color.red() - self.start_color.red()) * eased
        green = self.start_color.green() + (self.target_color.green() - self.start_color.green()) * eased
        blue = self.start_color.blue() + (self.target_color.blue() - self.start_color.blue()) * eased
        self.display_color = QColor(round(red), round(green), round(blue))
        self.update_control_colors()
        # Repaint only while the interpolated color actually changes. A constant
        # 60fps repaint loop starves the backing store and was the main driver
        # of repeated QPainter/backing-store warnings; between transitions the
        # 1s clock timer keeps the hands moving.
        if self.display_color != previous_color:
            self.update()

    def opposite_color(self, color):
        return QColor(255 - color.red(), 255 - color.green(), 255 - color.blue())

    def draw_outlined_text(self, painter, rect, alignment, text, fill_color, border_color):
        painter.setPen(QPen(border_color))
        for dx, dy in (
            (-1, -1), (0, -1), (1, -1),
            (-1, 0),           (1, 0),
            (-1, 1),  (0, 1),  (1, 1),
        ):
            painter.drawText(rect.adjusted(dx, dy, dx, dy), alignment, text)

        painter.setPen(QPen(fill_color))
        painter.drawText(rect, alignment, text)

    def draw_outlined_hand(self, painter, center_x, center_y, length, angle, width, fill_color, border_color):
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

    def draw_clock(self, painter, top_left_x, top_left_y, now):
        scale = self.CLOCK_SIZE / 200
        center_x = top_left_x + self.CLOCK_SIZE / 2
        center_y = top_left_y + self.CLOCK_SIZE / 2
        margin = 10 * scale - 3
        face_size = self.CLOCK_SIZE - (margin * 2)
        hour_hand = 48 * scale
        minute_hand = 68 * scale
        second_hand = 76 * scale
        if self.use_auto_contrast:
            clock_color = QColor(self.display_color)
            border_color = self.opposite_color(clock_color)
            face_color = QColor(border_color)
            face_color.setAlpha(42)
            tick_color = QColor(clock_color)
        else:
            manual = self.manual_colors
            clock_color = QColor(manual.get("hand_color", QColor(0, 0, 0)))
            border_color = QColor(manual.get("border_color", QColor(255, 255, 255)))
            face_color = QColor(manual.get("face_color", QColor(255, 255, 255)))
            tick_color = QColor(manual.get("tick_color", QColor(0, 0, 0)))

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
        self.draw_outlined_hand(
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
        self.draw_outlined_hand(
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
        self.draw_outlined_hand(
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

    def draw_battery_indicator(self, painter):
        percent = self.battery_percent()
        power_state = self.battery_power_state()
        label_width = 72
        # center the label under the stacked clocks and place it at the bottom
        clocks_left = self.HORIZONTAL_PADDING
        x = clocks_left + (self.CLOCK_SIZE / 2) - (label_width / 2)
        # place the battery indicator near the bottom of the window
        y = self.height() - 28
        clock_color = QColor(self.display_color)
        border_color = self.opposite_color(clock_color)

        label = "--%" if percent is None else f"{percent}%"
        if power_state is not None:
            label = f"{label} {power_state}"
        label_font = painter.font()
        label_font.setPointSize(10)
        painter.setFont(label_font)
        self.draw_outlined_text(
            painter,
            QRectF(x, y - 3, label_width, 24),
            Qt.AlignCenter,
            label,
            clock_color,
            border_color,
        )

    def draw_hardware_specs(self, painter):
        """Draw the hardware specs panel with CPU, RAM, GPU, and VRAM usage on the right side."""
        clock_color = QColor(self.display_color)
        border_color = self.opposite_color(clock_color)
        
        # Calculate panel position (right side of clocks, vertically centered)
        scale = self.CLOCK_SIZE / 200
        margin = 10 * scale
        clocks_x = self.HORIZONTAL_PADDING
        top_y = margin + getattr(self, 'top_control_offset', 0)
        
        # Position panel to the right of clocks, vertically centered
        panel_x = clocks_x + self.CLOCK_SIZE + self.SPECS_PANEL_SPACING
        panel_y = top_y + (self.CLOCKS_HEIGHT - self.HARDWARE_PANEL_HEIGHT) / 2
        
        # Panel dimensions
        panel_width = self.HARDWARE_PANEL_WIDTH
        panel_height = self.HARDWARE_PANEL_HEIGHT

        # Background for the specs panel is drawn separately as an independent
        # rounded sheet in the main paintEvent so the panel and clocks appear
        # visually distinct. Keep this function focused on text rendering.

        # Set up font for specs text
        specs_font = painter.font()
        specs_font.setPointSize(10)
        specs_font.setBold(True)
        painter.setFont(specs_font)
        
        # Calculate line height and spacing
        line_height = 19
        padding = 6
        
        # Prepare specs text
        cpu_text = f"CPU: {self.cpu_percent:.0f}%"
        ram_text = f"RAM: {self.ram_percent:.0f}%"
        gpu_text = f"GPU: {self.gpu_percent:.0f}%" if self.gpu_available else "GPU: N/A"
        vram_text = f"VRAM: {self.gpu_vram_percent:.0f}%" if self.gpu_available else "VRAM: N/A"
        
        # Get battery info for display in specs panel
        battery_percent = self.battery_percent()
        battery_state = self.battery_power_state()
        battery_text = "--%" if battery_percent is None else f"{battery_percent}%"
        if battery_state is not None:
            battery_text = f"{battery_text} {battery_state}"
        
        # Draw specs text lines
        text_x = panel_x + padding + 1
        text_y = panel_y + padding
        
        self.draw_outlined_text(
            painter,
            QRectF(text_x, text_y, panel_width - (padding * 2), line_height),
            Qt.AlignLeft,
            cpu_text,
            clock_color,
            border_color,
        )
        
        self.draw_outlined_text(
            painter,
            QRectF(text_x, text_y + line_height, panel_width - (padding * 2), line_height),
            Qt.AlignLeft,
            ram_text,
            clock_color,
            border_color,
        )
        
        self.draw_outlined_text(
            painter,
            QRectF(text_x, text_y + (line_height * 2), panel_width - (padding * 2), line_height),
            Qt.AlignLeft,
            gpu_text,
            clock_color,
            border_color,
        )
        
        self.draw_outlined_text(
            painter,
            QRectF(text_x, text_y + (line_height * 3), panel_width - (padding * 2), line_height),
            Qt.AlignLeft,
            vram_text,
            clock_color,
            border_color,
        )
        
        self.draw_outlined_text(
            painter,
            QRectF(text_x, text_y + (line_height * 4), panel_width - (padding * 2), line_height),
            Qt.AlignLeft,
            f" {battery_text}",
            clock_color,
            border_color,
        )

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
        top_now = self._now_for(self.top_tz)
        bottom_now = self._now_for(self.bottom_tz)
        scale = self.CLOCK_SIZE / 200
        margin = 10 * scale
        # Stack the two clocks vertically; account for reserved top control area
        clocks_x = self.HORIZONTAL_PADDING
        top_y = margin + getattr(self, 'top_control_offset', 0)
        # Determine adaptive sheet color based on display_color
        # If display_color is dark (white text), sheet should be dark to match
        # If display_color is light (black text), sheet should be light
        clock_color = QColor(self.display_color)
        is_light_desktop = clock_color == QColor(Qt.black)  # black text means light background
        sheet_color = QColor(Qt.white) if is_light_desktop else QColor(Qt.black)
        sheet_opacity = 0.82
        
        # Draw the specs sheet
        sheet_padding = 8
        panel_x = clocks_x + self.CLOCK_SIZE + self.SPECS_PANEL_SPACING
        panel_y = top_y + (self.CLOCKS_HEIGHT - self.HARDWARE_PANEL_HEIGHT) / 2
        specs_sheet_x = panel_x - sheet_padding
        specs_sheet_y = panel_y - sheet_padding
        specs_sheet_w = self.HARDWARE_PANEL_WIDTH + (sheet_padding * 2)
        specs_sheet_h = self.HARDWARE_PANEL_HEIGHT + (sheet_padding * 2)
        draw_background_sheet(painter, specs_sheet_x, specs_sheet_y, specs_sheet_w, specs_sheet_h, sheet_color, sheet_opacity, radius=12)

        # Draw clocks and specs content
        self.draw_clock(painter, clocks_x, top_y, top_now)
        self.draw_clock(painter, clocks_x, top_y + self.CLOCK_SIZE + self.CLOCK_SPACING, bottom_now)
        self.draw_hardware_specs(painter)

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

    # ---- Runtime appearance controls (right-click menu) -------------------

    def set_use_auto_contrast(self, enabled):
        """Toggle between adaptive desktop contrast and the fixed palette."""
        self.use_auto_contrast = bool(enabled)
        # Re-sync display_color immediately for both directions.
        self.update_contrast_transition()
        self.save_window_position()

    def set_manual_color(self, role, color):
        """Set one manual color role; picking a color implies manual mode."""
        if role not in self.COLOR_ROLES:
            return
        resolved = QColor(color)
        if not resolved.isValid():
            return
        self.manual_colors[role] = resolved
        self.use_auto_contrast = False
        self.update_contrast_transition()
        self.save_window_position()

    # ---- Timezones ---------------------------------------------------------

    @staticmethod
    def _safe_zoneinfo(name):
        """Return ZoneInfo(name), or None when invalid -> system local time."""
        try:
            return ZoneInfo(str(name))
        except Exception:
            return None

    def _now_for(self, tz):
        return datetime.now(tz) if tz is not None else datetime.now()

    def set_timezones(self, top_name, bottom_name):
        """Adopt new timezone strings; invalid ones fall back to local time."""
        self.top_tz_name = str(top_name).strip()
        self.bottom_tz_name = str(bottom_name).strip()
        self.top_tz = self._safe_zoneinfo(self.top_tz_name)
        self.bottom_tz = self._safe_zoneinfo(self.bottom_tz_name)
        self.update()
        self.save_window_position()

    def apply_appearance_settings(self, use_auto_contrast, colors):
        """Apply a full palette + mode atomically (single config write)."""
        for role in self.COLOR_ROLES:
            resolved = QColor(colors.get(role, self.manual_colors.get(role)))
            if resolved.isValid():
                self.manual_colors[role] = resolved
        self.use_auto_contrast = bool(use_auto_contrast)
        self.update_contrast_transition()
        self.save_window_position()

    # ---- Settings dialog ---------------------------------------------------

    def _build_settings_dialog(self):
        return SettingsDialog(self)

    def open_settings_dialog(self):
        dialog = self._build_settings_dialog()
        if dialog.exec_() == QDialog.Accepted:
            self.apply_appearance_settings(
                dialog.use_auto_contrast_checked(), dialog.chosen_colors()
            )
            self.set_timezones(
                dialog.top_timezone_text(), dialog.bottom_timezone_text()
            )

    def contextMenuEvent(self, event):
        self.open_settings_dialog()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    clock = AnalogClock()
    clock.show()
    sys.exit(app.exec_())

#cd /home/hrshl/Documents/Projects/analog-clock && /home/hrshl/Documents/Projects/.venv/bin/python clock.py
