import sys

from PyQt5.QtWidgets import QApplication

from analogclock.analog_clock_widget import AnalogClock
from analogclock.bootstrap import apply_platform_workarounds

apply_platform_workarounds()

app = QApplication(sys.argv)
clock = AnalogClock()
clock.show()
sys.exit(app.exec_())
