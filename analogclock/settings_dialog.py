"""Modal settings panel: fixed clock colors, timezones, and display sizes.

Includes a live preview rendered via drawing.draw_clock and draw_hardware_specs
that reflects the currently chosen fixed colors for the clock face and the
hardware stats panel (text and background sheet). Color swatches are plain
QFrames instead of recolored buttons so they read as swatches rather than
clickable controls.
"""

from datetime import datetime
from zoneinfo import available_timezones

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from analogclock.colors import COLOR_ROLES
from analogclock.drawing import draw_clock, draw_hardware_specs

# Static stats shown in the settings preview so the hardware panel (its text
# color and background sheet) is visible without polling live stats.
_STUB_STATS = {
    "cpu_percent": 66.6,
    "ram_percent": 47.3,
    "gpu_percent": 31.2,
    "gpu_vram_percent": 42.1,
    "gpu_available": True,
    "battery_text": "BAT 77%",
}


class _AppearancePreview(QWidget):
    """Live preview of the clock and a hardware panel in the current colors.

    The preview scales its clock face and hardware panel with the chosen clock
    size (so the background sheet grows with it), and the specs font tracks the
    chosen font size. The preview clock is capped so the dialog stays compact
    while still reflecting the scaling direction.
    """

    CLOCK_SIZE = 130
    MAX_PREVIEW_CLOCK_SIZE = 170
    DEFAULT_FONT_SIZE = 10
    PANEL_W_RATIO = 90 / 160
    PANEL_H_RATIO = 110 / 160
    MARGIN = 16
    GAP = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manual_palette = {}
        self._clock_size = self.CLOCK_SIZE
        self._font_size = self.DEFAULT_FONT_SIZE
        self._apply_size()

    def set_state(self, manual_palette, clock_size=None, font_size=None):
        self.manual_palette = dict(manual_palette)
        if clock_size is not None:
            self._clock_size = max(
                self.CLOCK_SIZE, min(self.MAX_PREVIEW_CLOCK_SIZE, int(clock_size))
            )
        if font_size is not None:
            self._font_size = int(font_size)
        self._apply_size()
        self.update()

    def _apply_size(self):
        """Recompute panel dims and the fixed preview size from the clock size."""
        self._panel_width = max(1, round(self._clock_size * self.PANEL_W_RATIO))
        self._panel_height = max(1, round(self._clock_size * self.PANEL_H_RATIO))
        width = self.MARGIN + self._clock_size + self.GAP + self._panel_width + self.MARGIN
        height = self.MARGIN + self._clock_size + self.MARGIN
        self.setFixedSize(width, height)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            colors = {
                role: QColor(self.manual_palette.get(role))
                for role in COLOR_ROLES
            }
            draw_clock(
                painter,
                float(self.MARGIN),
                float(self.MARGIN),
                datetime.now(),
                float(self._clock_size),
                colors,
            )
            draw_hardware_specs(
                painter,
                self.MARGIN + self._clock_size + self.GAP,
                self.MARGIN,
                self._panel_width,
                self._panel_height,
                _STUB_STATS,
                colors,
                font_size=self._font_size,
            )
        finally:
            painter.end()


class SettingsDialog(QDialog):
    ROLE_LABELS = {
        "face_color": "Face",
        "hand_color": "Hands",
        "tick_color": "Ticks",
        "border_color": "Border",
        "text_color": "Text",
        "sheet_color": "Sheet",
    }

    def __init__(self, clock, parent=None):
        super().__init__(parent or clock)
        self.setWindowTitle("Analog Clock settings")
        self._clock = clock
        self._chosen_colors = dict(clock.colors.manual_colors)
        # Display-size choices, applied live to the preview and (on accept)
        # written to the clock instance and persisted with the rest of the
        # appearance settings.
        self._chosen_clock_size = int(clock.CLOCK_SIZE)
        self._chosen_font_size = int(clock.font_size)

        layout = QVBoxLayout(self)

        color_group = QGroupBox("Clock colors", self)
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

        size_group = QGroupBox("Display size", self)
        size_layout = QFormLayout(size_group)
        self.clock_size_spin = QSpinBox(size_group)
        self.clock_size_spin.setRange(clock.MIN_CLOCK_SIZE, clock.MAX_CLOCK_SIZE)
        self.clock_size_spin.setSuffix(" px")
        self.clock_size_spin.setValue(self._chosen_clock_size)
        self.font_size_spin = QSpinBox(size_group)
        self.font_size_spin.setRange(clock.MIN_FONT_SIZE, clock.MAX_FONT_SIZE)
        self.font_size_spin.setSuffix(" pt")
        self.font_size_spin.setValue(self._chosen_font_size)
        size_layout.addRow("Clock size:", self.clock_size_spin)
        size_layout.addRow("Font size:", self.font_size_spin)
        self.clock_size_spin.valueChanged.connect(self._on_size_changed)
        self.font_size_spin.valueChanged.connect(self._on_size_changed)
        layout.addWidget(size_group)

        preview_group = QGroupBox("Live preview", self)
        preview_layout = QVBoxLayout(preview_group)
        self.preview = _AppearancePreview(preview_group)
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

        # Keep the live preview in sync with the chosen colors and animate
        # its second hand once a second.
        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(1000)
        self._preview_timer.timeout.connect(self.preview.update)
        self._preview_timer.start()
        self.refresh_preview()

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
        self.preview.set_state(
            self._chosen_colors,
            clock_size=self._chosen_clock_size,
            font_size=self._chosen_font_size,
        )

    def _on_size_changed(self):
        self._chosen_clock_size = self.clock_size_spin.value()
        self._chosen_font_size = self.font_size_spin.value()
        self.refresh_preview()

    # -- values read back by AnalogClock.open_settings_dialog --------------

    def chosen_colors(self):
        return dict(self._chosen_colors)

    def chosen_clock_size(self):
        return self.clock_size_spin.value()

    def chosen_font_size(self):
        return self.font_size_spin.value()

    def top_timezone_text(self):
        return self.top_tz_combo.currentText().strip()

    def bottom_timezone_text(self):
        return self.bottom_tz_combo.currentText().strip()

