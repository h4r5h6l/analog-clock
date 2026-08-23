import sys

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication

from analogclock.analog_clock_widget import AnalogClock
from analogclock.bootstrap import (
    apply_platform_workarounds,
    apply_qt_attributes,
    load_bundled_font,
)

apply_platform_workarounds()
apply_qt_attributes()

app = QApplication(sys.argv)

# Register the bundled Noto Sans so text renders identically on every
# machine. If registration ever fails we keep the system default font;
# the metric-driven specs layout still guarantees nothing clips.
font_family = load_bundled_font()
if font_family:
    app.setFont(QFont(font_family))

clock = AnalogClock()
clock.show()
sys.exit(app.exec_())
