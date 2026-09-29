"""Start the Qt Quick app."""

import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

QML_DIR = Path(__file__).parent / "qml"
ICON = Path(__file__).parent / "icons" / "omaforge.svg"


def run(argv: list[str] | None = None) -> int:
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtQml import QQmlApplicationEngine

    from omaforge.ui.backend import Backend
    from omaforge.ui.theme import Theme

    QCoreApplication.setApplicationName("omaforge")
    QCoreApplication.setOrganizationName("omaforge")
    QGuiApplication.setDesktopFileName("omaforge")  # Wayland app_id; matches the .desktop file
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QGuiApplication(argv if argv is not None else sys.argv)
    if ICON.exists():
        app.setWindowIcon(QIcon(str(ICON)))

    theme = Theme()
    backend = Backend()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("theme", theme)
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(QML_DIR / "Main.qml")
    if not engine.rootObjects():
        msg = "omaforge: the interface failed to load (see the QML errors above); please report this"
        print(msg, file=sys.stderr)
        if os.environ.get("OMAFORGE_SELFTEST") != "1" and shutil.which("notify-send"):
            subprocess.run(["notify-send", "-a", "omaforge", "-u", "critical", "omaforge could not start",
                            "The interface failed to load. Run `omaforge` in a terminal for details."], check=False)
        return 1
    if os.environ.get("OMAFORGE_SELFTEST") == "1":
        # Used by the release workflow against the installed package.
        backend.shutdown()
        print("omaforge: interface loaded")
        return 0
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    code = app.exec()
    backend.shutdown()
    return code
