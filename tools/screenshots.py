"""Render README screenshots from the real UI, offscreen.

Run it against a demo setup, never your own install (paths show in the UI):

    XDG_CONFIG_HOME=/tmp/demo/config XDG_DATA_HOME=/tmp/demo/data \\
    XDG_STATE_HOME=/tmp/demo/state OMAFORGE_CURSEFORGE_API_KEY=... \\
    python tools/screenshots.py docs/screenshots

XDG_STATE_HOME decides the Omarchy theme (omarchy/current/theme/colors.toml);
the script swaps stock themes from /usr/share/omarchy/themes in for the
theme scenes.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

THEMES = Path("/usr/share/omarchy/themes")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--scale", default="2")
    ap.add_argument("--theme", default="tokyo-night", help="theme for the main screenshots")
    ap.add_argument("--themes", default="tokyo-night,catppuccin-latte,gruvbox,rose-pine",
                    help="themes for the theme strip")
    args = ap.parse_args()
    # A large virtual screen at the requested pixel ratio, so the window is not clamped.
    screen = {"screens": [{"name": "shot", "x": 0, "y": 0, "width": 3840, "height": 2160,
                           "logicalDpi": 96, "logicalBaseDpi": 96, "dpr": float(args.scale)}]}
    cfg = Path(tempfile.mkstemp(suffix=".json")[1])
    cfg.write_text(json.dumps(screen))
    os.environ["QT_QPA_PLATFORM"] = f"offscreen:configfile={cfg}"
    os.environ["QT_SCALE_FACTOR"] = args.scale
    args.out.mkdir(parents=True, exist_ok=True)

    from PySide6.QtCore import QObject, QTimer
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow
    from shiboken6 import Shiboken

    from omaforge import paths
    from omaforge.ui.app import QML_DIR
    from omaforge.ui.backend import Backend
    from omaforge.ui.theme import Theme

    theme_file = paths.omarchy_theme_dir() / "colors.toml"
    theme_file.parent.mkdir(parents=True, exist_ok=True)

    def use_theme(name: str) -> None:
        shutil.copy(THEMES / name / "colors.toml", theme_file)
        theme._reload()

    app = QGuiApplication(["omaforge"])
    theme, backend = Theme(), Backend()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("theme", theme)
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(QML_DIR / "Main.qml")
    if not engine.rootObjects():
        return 1
    win = Shiboken.wrapInstance(Shiboken.getCppPointer(engine.rootObjects()[0])[0], QQuickWindow)

    def client(game):
        return next(c["key"] for c in backend.clients if c["game"] == game)

    # (file name or None, setup) — setup runs, then we wait for the backend and images.
    scenes = [
        (None, lambda: use_theme(args.theme)),
        (None, lambda: backend.selectClient(client("retail"))),
        ("installed", lambda: win.setProperty("pageIndex", 0)),
        ("explore", lambda: (win.setProperty("pageIndex", 1), backend.loadExplore("curseforge", "popular", ""))),
        ("explore-forever", lambda: (backend.selectClient(client("forever")), win.setProperty("pageIndex", 1),
                                     backend.loadExplore("wowinterface", "favorites", ""))),
        (None, lambda: backend.selectClient(client("retail"))),
        ("search", lambda: (win.setProperty("pageIndex", 2),
                            set_search_sort(),
                            backend.search("weakauras", [s["name"] for s in backend.providers if s["available"]]))),
        ("backups", lambda: (win.setProperty("pageIndex", 3), backend.loadBackups())),
    ]
    for name in args.themes.split(","):
        scenes.append((None, lambda n=name: (use_theme(n), win.setProperty("pageIndex", 0))))
        scenes.append((f"theme-{name}", lambda: None))

    def set_search_sort():
        root = engine.rootObjects()[0]
        root.findChild(QObject, "searchQuery").setProperty("text", "weakauras")
        root.findChild(QObject, "searchSort").setProperty("currentIndex", 1)  # Most downloaded

    step = {"i": 0}

    def after_idle(then, tries=600):
        if backend.busy and tries:
            QTimer.singleShot(100, lambda: after_idle(then, tries - 1))
        else:
            QTimer.singleShot(2500, then)  # let remote icons arrive

    def run():
        if step["i"] >= len(scenes):
            backend.shutdown()
            app.quit()
            return
        name, setup = scenes[step["i"]]
        step["i"] += 1
        setup()

        def shoot():
            if name:
                path = args.out / f"{name}.png"
                win.grabWindow().save(str(path))
                print("wrote", path)
            run()

        after_idle(shoot)

    after_idle(run)
    app.exec()
    return 0


if __name__ == "__main__":
    sys.exit(main())
