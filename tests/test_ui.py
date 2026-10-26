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
from omaforge.ui.about import AppInfo  # noqa: E402
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
        theme, backend, info = Theme(), Backend(manager), AppInfo()
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("theme", theme)
        engine.rootContext().setContextProperty("backend", backend)
        engine.rootContext().setContextProperty("appInfo", info)
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

        # About: F1 opens it, the license can be read, Esc closes it.
        from PySide6.QtCore import QObject, Qt
        from PySide6.QtQuick import QQuickItem, QQuickWindow
        from PySide6.QtTest import QTest
        from shiboken6 import Shiboken

        win = Shiboken.wrapInstance(Shiboken.getCppPointer(win)[0], QQuickWindow)
        about = win.findChild(QObject, "about")
        assert not about.property("visible")
        win.requestActivate()
        QTest.keyClick(win, Qt.Key_F1)
        wait(app, backend)
        assert about.property("visible")
        license_text = win.findChild(QQuickItem, "aboutLicenseText")
        assert not license_text.isVisible()
        about.setProperty("showLicense", True)
        wait(app, backend)
        assert license_text.isVisible() and license_text.property("text").startswith("MIT License")
        assert "no telemetry" in win.findChild(QQuickItem, "aboutPrivacy").property("text")
        QTest.keyClick(win, Qt.Key_Escape)
        wait(app, backend)
        assert not about.property("visible")
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
        theme, backend, info = Theme(), Backend(manager), AppInfo()
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("theme", theme)
        engine.rootContext().setContextProperty("backend", backend)
        engine.rootContext().setContextProperty("appInfo", info)
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


def _load(backend, font=None):
    from PySide6.QtQuick import QQuickWindow
    from shiboken6 import Shiboken

    engine = QQmlApplicationEngine()
    engine.keep = (Theme(), AppInfo())  # QML holds no reference of its own to context objects
    if font:
        engine.keep[0]._font = font
    engine.rootContext().setContextProperty("theme", engine.keep[0])
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("appInfo", engine.keep[1])
    engine.load(QML_DIR / "Main.qml")
    win = Shiboken.wrapInstance(Shiboken.getCppPointer(engine.rootObjects()[0])[0], QQuickWindow)
    return engine, win


def _qml_messages():
    messages = []

    def handler(kind, context, msg):
        if kind != QtMsgType.QtDebugMsg and (".qml" in (context.file or "") or ".qml" in msg):
            messages.append(msg)

    return messages, qInstallMessageHandler(handler)


def _visible(item, out=None):
    """Every visible item under `item`, with its scene rectangle."""
    out = [] if out is None else out
    for child in item.childItems():
        if child.isVisible() and child.opacity() > 0:
            out.append(child)
            _visible(child, out)
    return out


def test_broken_config_is_reported_and_never_saved_over(app, wow_root, tmp_path):
    from PySide6.QtCore import QObject
    from PySide6.QtQuick import QQuickItem

    path = config.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('roots = [\n[providers.github]\ntoken = "keep me"\n')
    original = path.read_text()
    messages, previous = _qml_messages()
    try:
        backend = Backend()  # builds its Manager from the (broken) files, as the app does
        engine, win = _load(backend)
        wait(app, backend)
        assert str(path) in backend.configError and backend.configErrorPath == str(path)
        assert backend.clients == [] and backend.settings["error"]
        assert win.findChild(QQuickItem, "configErrorBanner").isVisible()
        assert "No World of Warcraft install found" not in "".join(
            str(i.property("text")) for i in _visible(win.contentItem()))

        win.setProperty("pageIndex", 4)
        wait(app, backend)
        assert not win.findChild(QObject, "saveSettings").property("enabled")
        assert win.findChild(QQuickItem, "settingsBroken").isVisible()
        backend.saveSettings({"autodetect": True, "githubToken": "", "curseforgeKey": "", "wagoKey": "",
                              "backupsKeep": 10, "backupBeforeUpdate": True, "offline": False})
        wait(app, backend)
        assert path.read_text() == original and not list(path.parent.glob("config.toml.broken-*"))

        backend.setAsideBrokenFile()
        wait(app, backend)
        kept = list(path.parent.glob("config.toml.broken-*"))
        assert len(kept) == 1 and kept[0].read_text() == original
        assert backend.configError == "" and not path.exists()
        assert not win.findChild(QQuickItem, "configErrorBanner").isVisible()
        backend.shutdown()
    finally:
        qInstallMessageHandler(previous)
    assert messages == []


def test_broken_flavors_toml_is_reported_too(app, tmp_path):
    path = config.config_path().parent / "flavors.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[[rule]] products=")
    backend = Backend()
    engine, win = _load(backend)
    wait(app, backend)
    assert backend.configErrorPath == str(path) and "line 1" in backend.configError
    backend.shutdown()


def test_damaged_state_json_is_reported_in_the_window(app, wow_root, tmp_path):
    from omaforge import paths

    state = paths.data_dir() / "state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("{oops")
    cfg = copy.deepcopy(config.DEFAULTS)
    cfg["roots"] = {"paths": [str(wow_root)], "autodetect": False}
    for p in cfg["providers"].values():
        p["enabled"] = False
    toasts = []
    backend = Backend(Manager(cfg=cfg, http=FakeHttp(), home=tmp_path / "home"))
    backend.toast.connect(lambda kind, msg: toasts.append((kind, msg)))
    wait(app, backend)
    assert backend.clients and any(str(state) in m and "damaged-" in m for _, m in toasts)
    backend.shutdown()


@pytest.mark.parametrize("font", [None, "DejaVu Sans Mono"])  # the Omarchy font here, a wide one as in CI
@pytest.mark.parametrize("width", [640, 760, 1000, 1180])
def test_window_fits_half_a_screen(app, wow_root, tmp_path, width, font):
    """Nothing is cut off on the right, down to the minimum width (QA M4)."""
    for name in ("BugSack", "Details", "StoryTracker"):
        make_addon(wow_root / "_retail_/Interface/AddOns", name, f"## Title: {name} with a long title\n## Version: 1\n")
    cfg = copy.deepcopy(config.DEFAULTS)
    cfg["roots"] = {"paths": [str(wow_root)], "autodetect": False}
    for p in cfg["providers"].values():
        p["enabled"] = False
    cfg["providers"]["wowinterface"]["enabled"] = True
    messages, previous = _qml_messages()
    try:
        backend = Backend(Manager(cfg=cfg, http=FakeHttp(), home=tmp_path / "home"))
        engine, win = _load(backend, font)
        wait(app, backend)
        assert win.property("minimumWidth") <= 640
        win.setProperty("width", 1400)  # start wide, as a window that is then tiled
        wait(app, backend)
        win.grabWindow()
        win.setProperty("width", width)
        win.setProperty("height", 700)
        for page in (0, 2, 3, 4):
            win.setProperty("pageIndex", page)
            wait(app, backend)
            win.grabWindow()  # renders a frame, which is when layouts are polished offscreen
            for item in _visible(win.contentItem()):
                text = item.property("text")
                if not isinstance(text, str) or not text or not item.property("hoverEnabled"):
                    continue  # buttons and fields only
                right = item.mapToScene(item.boundingRect().topRight()).x()
                assert right <= width + 0.5, f"page {page}: {text!r} ends at {right:.0f} > {width}"
        win.setProperty("pageIndex", 0)
        wait(app, backend)
        win.grabWindow()
        texts = [i.property("text") for i in _visible(win.contentItem()) if i.property("hoverEnabled")]
        if width < 1000:
            assert "Remove" not in texts and texts.count("⋯") >= 4  # three rows and the toolbar
        if width >= 1180:
            assert texts.count("Remove") == 3 and "Import…" in texts
        backend.shutdown()
    finally:
        qInstallMessageHandler(previous)
    assert messages == []
