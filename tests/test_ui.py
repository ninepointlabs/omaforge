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


def test_details_popup_loads_and_closes_with_escape(app, wow_root, tmp_path):
    from PySide6.QtCore import QMetaObject, QObject, Q_ARG, Qt
    from PySide6.QtTest import QTest

    from PySide6.QtGui import QColor, QImage
    from PySide6.QtQuick import QQuickWindow
    from shiboken6 import Shiboken

    from omaforge.core.providers.wowinterface import API as WOWI

    make_addon(wow_root / "_retail_/Interface/AddOns", "Local", "## Title: Local Thing\n## Version: 1\n")
    shot = tmp_path / "shot.png"
    image = QImage(8, 8, QImage.Format_RGB32)
    image.fill(QColor("teal"))
    image.save(str(shot))
    entry = {"UID": "5108", "UIName": "Clique", "UIAuthorName": "Cladhaire", "UIVersion": "5.0", "UIDownloadTotal": "10",
             "UICompatibility": [{"version": "12.1.0", "name": "Retail"}], "UIDir": ["Clique"],
             "UIFileInfoURL": "https://wowi/5108", "UIIMGs": [shot.as_uri()]}
    http = FakeHttp({f"{WOWI}/filelist.json": [entry],
                     f"{WOWI}/filedetails/5108.json": [{**entry, "UIDescription": "Click [b]casting[/b]\n[url=https://x]x[/url]"}]})
    cfg = copy.deepcopy(config.DEFAULTS)
    cfg["roots"] = {"paths": [str(wow_root)], "autodetect": False}
    for name, p in cfg["providers"].items():
        p["enabled"] = name == "wowinterface"
    manager = Manager(cfg=cfg, http=http, home=tmp_path / "home")

    messages = []

    def handler(kind, context, msg):
        if kind != QtMsgType.QtDebugMsg and (".qml" in (context.file or "") or ".qml" in msg):
            messages.append(msg)

    previous = qInstallMessageHandler(handler)
    try:
        theme, backend = Theme(), Backend(manager)
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("theme", theme)
        engine.rootContext().setContextProperty("backend", backend)
        engine.load(QML_DIR / "Main.qml")
        win = Shiboken.wrapInstance(Shiboken.getCppPointer(engine.rootObjects()[0])[0], QQuickWindow)
        wait(app, backend)
        popup = win.findChild(QObject, "details")
        assert popup is not None

        QMetaObject.invokeMethod(popup, "show", Q_ARG("QVariant", {"provider": "wowinterface", "id": "5108", "name": "Clique"}))
        wait(app, backend)
        assert popup.property("opened") or popup.property("visible")
        d = backend.details
        assert d["addon"]["name"] == "Clique" and "<b>casting</b>" in d["description"]
        assert len(d["screenshots"]) == 1 and not backend.detailsLoading

        popup.setProperty("shot", 0)
        for _ in range(5):
            app.processEvents()
        QTest.keyClick(win, Qt.Key_Escape)
        for _ in range(5):
            app.processEvents()
        assert popup.property("shot") == -1 and popup.property("visible")  # Esc closed only the screenshot
        QTest.keyClick(win, Qt.Key_Escape)
        for _ in range(20):
            app.processEvents()
        assert not popup.property("visible")
        assert backend.details == {}

        # Clicking an installed addon's row opens it; its buttons still do their own thing.
        def find(item, text):
            if item.property("text") == text and item.isVisible():
                return item
            for child in item.childItems():
                found = find(child, text)
                if found:
                    return found

        def click(item):
            QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, item.mapToScene(item.boundingRect().center()).toPoint())
            wait(app, backend)

        click(find(win.contentItem(), "Pin"))
        assert not popup.property("visible")
        click(find(win.contentItem(), "Local Thing"))
        assert popup.property("visible")
        assert popup.property("item")["name"] == "Local Thing"
        assert backend.details == {}  # no known source: only what the TOC says
        QTest.keyClick(win, Qt.Key_Escape)
        wait(app, backend)
        assert not popup.property("visible")
        backend.shutdown()
    finally:
        qInstallMessageHandler(previous)
    assert messages == []
