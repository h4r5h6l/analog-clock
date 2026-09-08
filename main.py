import sys
from pathlib import Path

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction, QApplication, QMenu, QSystemTrayIcon

from analogclock.analog_clock_widget import AnalogClock
from analogclock.bootstrap import apply_platform_workarounds

apply_platform_workarounds()

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)
app.setWindowIcon(QIcon(str(Path(__file__).with_name("clock.png"))))
clock = AnalogClock()


def create_tray(clock):
    """Create the tray icon and its control menu."""
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None
    tray = QSystemTrayIcon(app.windowIcon(), app)
    tray.setToolTip("Analog Clock")
    menu = QMenu()

    show_action = QAction("Show clock", menu)
    show_action.triggered.connect(clock.show_from_tray)
    settings_action = QAction("Settings...", menu)
    settings_action.triggered.connect(clock.open_settings_dialog)
    always_on_top_action = QAction("Always on top", menu)
    always_on_top_action.setCheckable(True)
    always_on_top_action.toggled.connect(clock.set_always_on_top)
    if clock.virtual_desktop_support_available():
        all_desktops_action = QAction("Show on all virtual desktops", menu)
        all_desktops_action.setCheckable(True)
        all_desktops_action.toggled.connect(clock.set_show_on_all_desktops)
        menu.addAction(all_desktops_action)
    else:
        all_desktops_action = None
    quit_action = QAction("Quit", menu)
    quit_action.triggered.connect(app.quit)

    menu.addAction(show_action)
    menu.addAction(settings_action)
    menu.addSeparator()
    menu.addAction(always_on_top_action)
    menu.addSeparator()
    menu.addAction(quit_action)

    def sync_actions():
        always_on_top_action.blockSignals(True)
        if all_desktops_action is not None:
            all_desktops_action.blockSignals(True)
        always_on_top_action.setChecked(clock.always_on_top)
        if all_desktops_action is not None:
            all_desktops_action.setChecked(clock.show_on_all_desktops)
        always_on_top_action.blockSignals(False)
        if all_desktops_action is not None:
            all_desktops_action.blockSignals(False)

    menu.aboutToShow.connect(sync_actions)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: clock.show_from_tray()
        if reason == QSystemTrayIcon.Trigger
        else None
    )
    tray.show()
    return tray


tray = create_tray(clock)
clock.show()
QTimer.singleShot(0, lambda: clock.set_show_on_all_desktops(clock.show_on_all_desktops, save=False))
sys.exit(app.exec_())
