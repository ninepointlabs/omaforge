"""Load the real QML offscreen against a fake install and fail on any QML warning."""

import copy
import os
import time

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from conftest import FakeHttp, make_addon  # noqa: E402
from PySide6.QtCore import QtMsgType, qInstallMessageHandler  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402

from omaforge import config  # noqa: E402
from omaforge.core.manager import Manager  # noqa: E402
from omaforge.ui.app import QML_DIR  # noqa: E402
from omaforge.ui.backend import Backend  # noqa: E402
from omaforge.ui.theme import Theme  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QGuiApplication.instance() or QGuiApplication(["omaforge-test"])


def wait(app, backend, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if not backend.busy:
            for _ in range(5):
                app.processEvents()
            if not backend.busy:
                return
        time.sleep(0.01)
    raise TimeoutError("backend stayed busy")


def test_main_window_loads_without_qml_warnings(app, wow_root, tmp_path):
    make_addon(wow_root / "_retail_/Interface/AddOns", "Local", "## Title: Local Thing\n## Version: 1\n")
    cfg = copy.deepcopy(config.DEFAULTS)
    cfg["roots"] = {"paths": [str(wow_root)], "autodetect": False}
    for p in cfg["providers"].values():
        p["enabled"] = False
    manager = Manager(cfg=cfg, http=FakeHttp(), home=tmp_path / "home")

    messages = []

    def handler(kind, context, msg):
        # Only our QML: the session may add unrelated noise (e.g. the a11y bus).
        if kind != QtMsgType.QtDebugMsg and (".qml" in (context.file or "") or ".qml" in msg):
            messages.append(msg)

    previous = qInstallMessageHandler(handler)
    try:
        theme, backend = Theme(), Backend(manager)
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("theme", theme)
        engine.rootContext().setContextProperty("backend", backend)
        engine.load(QML_DIR / "Main.qml")
        assert engine.rootObjects()
        wait(app, backend)
        assert [c["label"] for c in backend.clients] == ["Forever Beta", "Retail"]
        assert backend.currentClient.startswith("retail@")
        assert [a["name"] for a in backend.addons] == ["Local Thing"]

        win = engine.rootObjects()[0]
        for page in (1, 2, 3, 4, 0):
            win.setProperty("pageIndex", page)
            if page == 1:
                backend.ensureExplore()
            if page == 3:
                backend.loadBackups()
            wait(app, backend)
        assert backend.exploreSources == []  # every provider is disabled here

        backend.createBackup()
        wait(app, backend)
        assert len(backend.backups) == 1
        backend.selectClient(backend.clients[0]["key"])
        wait(app, backend)
        assert backend.client["label"] == "Forever Beta" and backend.addons == []
        backend.shutdown()
    finally:
        qInstallMessageHandler(previous)
    assert messages == []
