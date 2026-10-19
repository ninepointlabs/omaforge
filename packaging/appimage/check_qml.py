"""Compile every QML file omaforge ships, with the bundle's Python and Qt.

    <AppDir>/opt/python3.12/bin/python3.12 -I packaging/appimage/check_qml.py

The window only builds the pages and popups a person opens, so a launch alone
would not notice a QML module pruned out of the AppImage. This does: every
import of every file must resolve. Prints the errors and exits 1 if any do not.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent  # noqa: E402

from omaforge.ui.app import QML_DIR  # noqa: E402

app = QGuiApplication(["omaforge"])
engine = QQmlApplicationEngine()
failed = 0
files = sorted(Path(QML_DIR).glob("*.qml"))
for path in files:
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(path)))
    if component.isError():
        failed += 1
        for error in component.errors():
            print(f"{path.name}: {error.toString()}", file=sys.stderr)
print(f"QML: {len(files) - failed} of {len(files)} files compile")
sys.exit(1 if failed else 0)
