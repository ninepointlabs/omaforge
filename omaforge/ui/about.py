"""Facts for the About dialog, exposed to QML as `appInfo`."""

import os
import sys
from pathlib import Path

import PySide6
from PySide6.QtCore import Property, QObject, Slot, qVersion
from PySide6.QtGui import QGuiApplication

from omaforge import APP_NAME, COPYRIGHT, CREATED, LICENSE_NAME, ORGANIZATION, SUPPORT_EMAIL, TAGLINE, __version__

LICENSE_FILE = Path(__file__).parent / "LICENSE.txt"


class AppInfo(QObject):
    name = Property(str, lambda self: APP_NAME, constant=True)
    tagline = Property(str, lambda self: TAGLINE, constant=True)
    version = Property(str, lambda self: __version__, constant=True)
    organization = Property(str, lambda self: ORGANIZATION, constant=True)
    supportEmail = Property(str, lambda self: SUPPORT_EMAIL, constant=True)
    created = Property(str, lambda self: CREATED, constant=True)
    license = Property(str, lambda self: LICENSE_NAME, constant=True)
    copyright = Property(str, lambda self: COPYRIGHT, constant=True)
    qtVersion = Property(str, lambda self: qVersion(), constant=True)
    pysideVersion = Property(str, lambda self: PySide6.__version__, constant=True)
    pythonVersion = Property(str, lambda self: sys.version.split()[0], constant=True)

    @Property(str, constant=True)
    def licenseText(self) -> str:
        try:
            text = LICENSE_FILE.read_text(encoding="utf-8")
        except OSError:
            return f"{LICENSE_NAME}, {COPYRIGHT}"
        # One line per paragraph, so it wraps to the dialog's width.
        return "\n\n".join(" ".join(p.split()) for p in text.split("\n\n") if p.strip())

    @Property(str, constant=True)
    def details(self) -> str:
        """Version details to paste into a support email."""
        return (
            f"{APP_NAME} {__version__}\n"
            f"Qt {qVersion()}, PySide6 {PySide6.__version__}, Python {sys.version.split()[0]}\n"
            f"{os.environ.get('XDG_CURRENT_DESKTOP', 'unknown desktop')}, {QGuiApplication.platformName()}"
        )

    @Slot(str)
    def copy(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)
