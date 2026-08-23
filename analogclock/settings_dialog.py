"""Modal settings panel: contrast mode, fixed colors, clock timezones.

Includes a live single-clock preview rendered via drawing.draw_clock that
reflects either the automatic-contrast palette or the currently chosen
fixed colors. Color swatches are plain QFrames instead of recolored
buttons so they read as swatches rather than clickable controls.
"""

from datetime import datetime
from zoneinfo import available_timezones

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from analogclock.colors import COLOR_ROLES
from analogclock.drawing import draw_clock


class _ClockPreview(QWidget):
    """One live clock face reflecting the dialog's current choices."""

    PREVIEW_SIZE = 150

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.PREVIEW_SIZE + 16, self.PREVIEW_SIZE + 16)
        self.auto_mode = True
        self.manual_palette = {}

    def set_state(self, auto_mode, manual_palette):
        self.auto_mode = bool(auto_mode)
        self.manual_palette = dict(manual_palette)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            if self.auto_mode:
                # Neutral light backdrop -> automatic contrast resolves to
                # black hands with white halo, like a bright wallpaper.
                painter.fillRect(self.rect(), QColor(238, 238, 238))
                display = QColor(0, 0, 0)
                border = QColor(255, 255, 255)
                face = QColor(255, 255, 255)
                face.setAlpha(42)
                colors = {
                    "hand_color": display,
                    "tick_color": QColor(display),
                    "face_color": face,
                    "border_color": border,
                }
            else:
                colors = {
                    role: QColor(self.manual_palette.get(role))
                    for role in COLOR_ROLES
                }
            size = float(self.PREVIEW_SIZE)
            x = (self.width() - size) / 2
            y = (self.height() - size) / 2
            draw_clock(painter, x, y, datetime.now(), size, colors)
        finally:
            painter.end()


class SettingsDialog(QDialog):
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
        self._chosen_colors = dict(clock.colors.manual_colors)

        layout = QVBoxLayout(self)

        self.auto_check = QCheckBox("Use automatic contrast colors", self)
        self.auto_check.setChecked(clock.colors.use_auto_contrast)
        layout.addWidget(self.auto_check)

        color_group = QGroupBox("Fixed colors (used when auto contrast is off)", self)
        color_grid = QGridLayout(color_group)
        self._swatches = {}
        self._color_buttons = {}
        for row, role in enumerate(COLOR_ROLES):
            row_layout = QHBoxLayout()
            label = QLabel(SettingsDialog.ROLE_LABELS[role], color_group)
            # Plain QFrame swatch instead of a recolored push button.
            swatch = QFrame(color_group)
            swatch.setFixedSize(28, 18)
            swatch.setFrameShape(QFrame.StyledPanel)
            self._paint_swatch(swatch, clock.colors.manual_colors[role])
            button = QPushButton("Change...", color_group)
            button.setToolTip(f"Pick a fixed {role.replace('_', ' ')}")
            button.clicked.connect(
                lambda checked=False, r=role, s=swatch: self._pick(r, s)
            )
            row_layout.addWidget(label)
            row_layout.addWidget(swatch)
            row_layout.addStretch(1)
            row_layout.addWidget(button)
            color_grid.addLayout(row_layout, row, 0)
            self._swatches[role] = swatch
            self._color_buttons[role] = button
        layout.addWidget(color_group)

        preview_group = QGroupBox("Live preview", self)
        preview_layout = QVBoxLayout(preview_group)
        self.preview = _ClockPreview(preview_group)
        preview_layout.addWidget(self.preview, 0, Qt.AlignHCenter)
        layout.addWidget(preview_group)

        tz_group = QGroupBox("Clock timezones", self)
        tz_grid = QGridLayout(tz_group)
        tz_grid.addWidget(QLabel("Top clock:", tz_group), 0, 0)
        self.top_tz_combo = self._make_tz_combo(clock.timezones.top_name)
        tz_grid.addWidget(self.top_tz_combo, 0, 1)
        tz_grid.addWidget(QLabel("Bottom clock:", tz_group), 1, 0)
        self.bottom_tz_combo = self._make_tz_combo(clock.timezones.bottom_name)
        tz_grid.addWidget(self.bottom_tz_combo, 1, 1)
        layout.addWidget(tz_group)

        dialog_buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self
        )
        dialog_buttons.accepted.connect(self.accept)
        dialog_buttons.rejected.connect(self.reject)
        layout.addWidget(dialog_buttons)

        # Color pickers only make sense in manual mode; keep the live preview
        # in sync with either mode and animate its second hand once a second.
        self.auto_check.toggled.connect(self._sync_enabled)
        self.auto_check.toggled.connect(lambda checked: self.refresh_preview())
        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(1000)
        self._preview_timer.timeout.connect(self.preview.update)
        self._preview_timer.start()
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

    def _paint_swatch(self, frame, color):
        frame.setStyleSheet(f"background-color: {color.name()};")

    def _pick(self, role, swatch):
        initial = self._chosen_colors.get(role, QColor("#ffffff"))
        chosen = QColorDialog.getColor(
            initial, self, f"Choose {role.replace('_', ' ')}"
        )
        if chosen.isValid():
            self._chosen_colors[role] = chosen
            self._paint_swatch(swatch, chosen)
            self.refresh_preview()

    def refresh_preview(self):
        self.preview.set_state(self.auto_check.isChecked(), self._chosen_colors)

    def _sync_enabled(self):
        manual_mode = not self.auto_check.isChecked()
        for button in self._color_buttons.values():
            button.setEnabled(manual_mode)
        for swatch in self._swatches.values():
            swatch.setEnabled(manual_mode)
        self.refresh_preview()

    # -- values read back by AnalogClock.open_settings_dialog --------------

    def use_auto_contrast_checked(self):
        return self.auto_check.isChecked()

    def chosen_colors(self):
        return dict(self._chosen_colors)

    def top_timezone_text(self):
        return self.top_tz_combo.currentText().strip()

    def bottom_timezone_text(self):
        return self.bottom_tz_combo.currentText().strip()

