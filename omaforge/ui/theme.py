"""The active Omarchy theme, exposed to QML and re-read when it changes.

Omarchy writes the current theme to ~/.local/state/omarchy/current/theme/
(`omarchy theme set` replaces the directory), so the file, its directory and
the parent are all watched.
"""

import shutil
import subprocess
import tomllib

from PySide6.QtCore import Property, QFileSystemWatcher, QObject, QTimer, Signal
from PySide6.QtGui import QColor, QFontDatabase

from omaforge import paths

DEFAULTS = {
    "background": "#121212",
    "foreground": "#bebebe",
    "accent": "#7aa2f7",
    "selection": "#2a2a2a",
    "red": "#d35f5f",
    "green": "#8fbf6a",
    "yellow": "#e0af68",
}


def _mix(a: str, b: str, amount: float) -> str:
    ca, cb = QColor(a), QColor(b)
    r = ca.redF() + (cb.redF() - ca.redF()) * amount
    g = ca.greenF() + (cb.greenF() - ca.greenF()) * amount
    bl = ca.blueF() + (cb.blueF() - ca.blueF()) * amount
    return QColor.fromRgbF(r, g, bl).name()


def omarchy_font() -> str:
    """The font `omarchy font set` chose, else the system monospace font."""
    if shutil.which("omarchy"):
        try:
            out = subprocess.run(["omarchy", "font", "current"], capture_output=True, text=True, timeout=2)
            name = out.stdout.strip()
            if out.returncode == 0 and name and name in QFontDatabase.families():
                return name
        except (OSError, subprocess.TimeoutExpired):
            pass
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()


class Theme(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._c = dict(DEFAULTS)
        self._dark = True
        self._font = omarchy_font()
        self._watcher = QFileSystemWatcher(self)
        # `theme set` swaps files in several steps; settle before re-reading.
        self._debounce = QTimer(self, singleShot=True, interval=150)
        self._debounce.timeout.connect(self._reload)
        self._watcher.fileChanged.connect(lambda _: self._debounce.start())
        self._watcher.directoryChanged.connect(lambda _: self._debounce.start())
        self._reload()

    def _reload(self) -> None:
        theme_dir = paths.omarchy_theme_dir()
        colors = dict(DEFAULTS)
        mode = None
        try:
            with open(theme_dir / "colors.toml", "rb") as fh:
                data = tomllib.load(fh)
            mode = data.get("mode")
            colors.update({k: v for k, v in data.items() if isinstance(v, str) and v.startswith("#")})
        except (OSError, tomllib.TOMLDecodeError):
            pass
        self._c = colors
        if mode in ("dark", "light"):
            self._dark = mode == "dark"
        else:
            self._dark = QColor(colors["background"]).lightnessF() < 0.5
        watched = self._watcher.files() + self._watcher.directories()
        if watched:
            self._watcher.removePaths(watched)
        for p in (theme_dir.parent, theme_dir, theme_dir / "colors.toml"):
            if p.exists():
                self._watcher.addPath(str(p))
        self.changed.emit()

    def _get(self, key: str, fallback: str) -> str:
        return self._c.get(key) or fallback

    @Property(bool, notify=changed)
    def dark(self):
        return self._dark

    @Property(str, notify=changed)
    def background(self):
        return self._c["background"]

    @Property(str, notify=changed)
    def surface(self):
        return _mix(self._c["background"], self._c["foreground"], 0.05)

    @Property(str, notify=changed)
    def raised(self):
        return _mix(self._c["background"], self._c["foreground"], 0.10)

    @Property(str, notify=changed)
    def border(self):
        return _mix(self._c["background"], self._c["foreground"], 0.18)

    @Property(str, notify=changed)
    def foreground(self):
        return self._c["foreground"]

    @Property(str, notify=changed)
    def dim(self):
        return _mix(self._c["background"], self._c["foreground"], 0.55)

    @Property(str, notify=changed)
    def accent(self):
        return self._c["accent"]

    @Property(str, notify=changed)
    def accentText(self):
        return "#000000" if QColor(self._c["accent"]).lightnessF() > 0.55 else "#ffffff"

    @Property(str, notify=changed)
    def selection(self):
        return self._get("selection", _mix(self._c["background"], self._c["accent"], 0.25))

    @Property(str, notify=changed)
    def red(self):
        return self._c["red"]

    @Property(str, notify=changed)
    def green(self):
        return self._c["green"]

    @Property(str, notify=changed)
    def yellow(self):
        return self._c["yellow"]

    @Property(str, notify=changed)
    def font(self):
        return self._font
