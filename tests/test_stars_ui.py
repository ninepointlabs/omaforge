"""The star button and the Starred page, against the real QML offscreen."""

import json
import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from conftest import FakeHttp, make_addon  # noqa: E402
from PySide6.QtCore import Q_ARG, QMetaObject, QObject, Qt, qInstallMessageHandler  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from test_manager import github_release  # noqa: E402
from test_stars import CLIQUE, manager, state_file  # noqa: E402
from test_ui import _load, _qml_messages, _visible, wait  # noqa: E402

from omaforge.core import state as statemod  # noqa: E402
from omaforge.core.providers.wowinterface import API as WOWI  # noqa: E402
from omaforge.ui.backend import Backend  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QGuiApplication.instance() or QGuiApplication(["omaforge-test"])


def wowi_http(count=30):
    entries = [{"UID": str(1000 + i), "UIName": f"Addon {i:02}", "UIAuthorName": "Someone", "UIVersion": "1", "UIDownloadTotal": str(100 - i),
                "UICompatibility": [{"version": "12.1.0", "name": "Retail"}], "UIDir": [f"Addon{i}"],
                "UIFileInfoURL": f"https://wowi/{i}"} for i in range(count)]
    return FakeHttp({f"{WOWI}/filelist.json": entries, **{f"{WOWI}/filedetails/{e['UID']}.json": [e] for e in entries}})


def in_page(win, name):
    return win.findChild(QQuickItem, name)


def rows(view):
    """The delegates inside the viewport, top to bottom; the view also keeps some just outside it."""
    top, bottom = view.mapToScene(view.boundingRect().topLeft()).y(), view.mapToScene(view.boundingRect().bottomLeft()).y()
    found = [i for i in view.property("contentItem").childItems() if i.property("r") and i.isVisible()]
    found = [i for i in found if i.mapToScene(i.boundingRect().topLeft()).y() >= top
             and i.mapToScene(i.boundingRect().bottomLeft()).y() <= bottom]
    return sorted(found, key=lambda i: i.y())


def star_of(row):
    return next(i for i in _visible(row) if i.objectName() == "star")


def click(app, backend, win, item):
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, item.mapToScene(item.boundingRect().center()).toPoint())
    wait(app, backend)
    win.grabWindow()
    wait(app, backend)


def show_page(app, backend, win, index):
    win.setProperty("pageIndex", index)
    wait(app, backend)
    win.grabWindow()
    wait(app, backend)


@pytest.fixture
def ui(app, wow_root, tmp_path):
    messages, previous = _qml_messages()
    held = []

    def start(http=None, enabled=("wowinterface",), width=1400):
        backend = Backend(manager(wow_root, tmp_path, http or wowi_http(), enabled))
        engine, win = _load(backend)
        held.append((backend, engine, win))
        win.setProperty("width", width)
        win.setProperty("height", 760)
        wait(app, backend)
        win.grabWindow()
        return backend, win

    yield start
    for backend, _, _ in held:
        backend.shutdown()
    qInstallMessageHandler(previous)
    assert messages == []


def explore_list(win):
    # Explore's list has no name of its own: it is the view holding Explore's rows.
    def find(item):
        for child in item.childItems():
            if child.inherits("QQuickListView") and child.isVisible():
                return child
            found = find(child)
            if found:
                return found

    return find(win.contentItem())


@pytest.mark.parametrize("width", [640, 1400])
def test_star_from_explore_keeps_the_place_and_lists_it_under_starred(app, ui, width):
    backend, win = ui(width=width)
    backend.loadExplore("wowinterface", "popular", "")
    show_page(app, backend, win, 1)
    view = explore_list(win)
    view.setProperty("contentY", 400.0)
    wait(app, backend)
    win.grabWindow()
    row = rows(view)[1]
    addon_id = row.property("r")["id"]
    name = row.property("r")["name"]

    click(app, backend, win, star_of(row))

    assert view.property("contentY") == 400.0  # the list wasn't rebuilt
    assert not win.findChild(QObject, "details").property("visible")  # and the star didn't open the details
    assert backend.starredKeys == {f"wowinterface:{addon_id}": True}
    assert star_of(row).property("text") == "★"
    assert not backend.starred[0]["installed"]

    show_page(app, backend, win, 3)
    assert [r.property("r")["name"] for r in rows(in_page(win, "starredList"))] == [name]

    click(app, backend, win, star_of(rows(in_page(win, "starredList"))[0]))
    assert backend.starred == [] and in_page(win, "starredList").property("count") == 0
    assert json.loads(state_file().read_text())["starred"] == {}


def test_taking_a_star_off_keeps_the_place_in_the_starred_list(app, ui):
    backend, win = ui()
    backend.loadExplore("wowinterface", "popular", "")
    wait(app, backend)
    for r in backend.exploreResults[:20]:
        backend.setStarred(r, True)
    wait(app, backend)
    show_page(app, backend, win, 3)
    view = in_page(win, "starredList")
    view.setProperty("contentY", 300.0)
    wait(app, backend)
    win.grabWindow()

    click(app, backend, win, star_of(rows(view)[1]))
    assert view.property("count") == 19 and view.property("contentY") == 300.0


def test_stars_are_there_after_a_restart_and_on_every_client(app, ui):
    backend, win = ui()
    backend.setStarred(CLIQUE, True)
    wait(app, backend)

    backend, win = ui()  # a new window and Manager, reading the file
    assert [s["name"] for s in backend.starred] == ["Clique"]
    other = next(c["key"] for c in backend.clients if c["key"] != backend.currentClient)
    backend.selectClient(other)
    wait(app, backend)
    assert [s["name"] for s in backend.starred] == ["Clique"]


def test_install_from_the_starred_page_then_it_stays_starred_after_removal(app, ui, wow_root):
    rel, js, files = github_release("v1", ["Foo"])
    http = FakeHttp({"https://api.github.com/repos/o/Foo/releases?per_page=15": [rel], **js}, files)
    backend, win = ui(http, enabled=("github",))
    toasts = []
    backend.toast.connect(lambda kind, msg: toasts.append((kind, msg)))
    backend.setStarred({"provider": "github", "id": "o/Foo", "name": "Foo", "author": "o"}, True)
    wait(app, backend)
    show_page(app, backend, win, 3)

    row = rows(in_page(win, "starredList"))[0]
    install = next(i for i in _visible(row) if i.property("text") == "Install")
    click(app, backend, win, install)

    assert toasts and toasts[-1][0] == "info", toasts
    assert (wow_root / "_retail_/Interface/AddOns/Foo").exists()
    assert backend.starred[0]["installed"] is True
    installed = next(a for a in backend.addons if a["key"] == "github:o/Foo")
    assert installed

    backend.uninstall("github:o/Foo")
    wait(app, backend)
    assert not (wow_root / "_retail_/Interface/AddOns/Foo").exists()
    assert backend.starred[0]["installed"] is False  # and it can be installed again from there


def test_filter_sort_and_not_installed(app, ui, wow_root):
    make_addon(wow_root / "_retail_/Interface/AddOns", "Here", "## Title: Here\n## Version: 1\n## X-WoWI-ID: 5\n")
    backend, win = ui()
    with backend.m.state.transaction() as s:
        s.set_record(backend.currentClient, "wowinterface:5", {"provider": "wowinterface", "id": "5", "name": "Here",
                                                               "version": "1", "folders": ["Here"]})
    backend.refresh()
    wait(app, backend)
    for addon_id, name, author in (("5", "Here", "b"), ("6", "Zed", "Ann"), ("7", "Ada", "Bob")):
        backend.setStarred({"provider": "wowinterface", "id": addon_id, "name": name, "author": author}, True)
    wait(app, backend)
    show_page(app, backend, win, 3)
    page = win.findChild(QObject, "starredFilter").parent().parent()
    shown = lambda: [a["name"] for a in page.property("shown").toVariant()]

    assert shown() == ["Ada", "Zed", "Here"]  # as starred, newest first

    win.findChild(QObject, "starredSort").setProperty("currentIndex", 1)
    wait(app, backend)
    assert shown() == ["Ada", "Here", "Zed"]

    win.findChild(QObject, "starredFilter").setProperty("text", "ann")  # by author
    wait(app, backend)
    assert shown() == ["Zed"]
    win.findChild(QObject, "starredFilter").setProperty("text", "")

    page.setProperty("notInstalledOnly", True)
    wait(app, backend)
    assert shown() == ["Ada", "Zed"]


def test_star_on_installed_rows_and_in_details(app, ui, wow_root):
    addons = wow_root / "_retail_/Interface/AddOns"
    make_addon(addons, "Mine", "## Title: Mine\n## Version: 1\n")
    make_addon(addons, "Known")
    backend, win = ui()
    with backend.m.state.transaction() as s:
        s.set_record(backend.currentClient, "wowinterface:1000", {"provider": "wowinterface", "id": "1000", "name": "Known",
                                                                  "version": "1", "folders": ["Known"]})
    backend.refresh()
    wait(app, backend)
    win.grabWindow()

    def installed_row(name):
        def walk(item):
            for child in item.childItems():
                a = child.property("a")
                if a and a["name"] == name:
                    return child
                found = walk(child)
                if found:
                    return found

        return walk(win.contentItem())

    assert not [i for i in _visible(installed_row("Mine")) if i.objectName() == "star"]  # no source, no star
    click(app, backend, win, star_of(installed_row("Known")))
    assert list(backend.starredKeys) == ["wowinterface:1000"]
    assert backend.starred[0]["installed"] is True
    assert not win.findChild(QObject, "details").property("visible")

    # Details of an addon not installed: the star there is the same star.
    popup = win.findChild(QObject, "details")
    QMetaObject.invokeMethod(popup, "show", Q_ARG("QVariant", {"provider": "wowinterface", "id": "1001", "name": "Addon 01"}))
    wait(app, backend)
    win.grabWindow()
    star = next(i for i in _visible(popup.property("contentItem")) if i.objectName() == "star")
    click(app, backend, win, star)
    assert "wowinterface:1001" in backend.starredKeys
    entry = next(s for s in backend.starred if s["id"] == "1001")
    assert entry["name"] == "Addon 01" and entry["author"] == "Someone"  # from the source, not just the row
    assert popup.property("visible")


def test_a_star_that_can_not_be_saved_is_taken_back_and_reported(app, ui, monkeypatch):
    backend, win = ui()
    toasts = []
    backend.toast.connect(lambda kind, msg: toasts.append((kind, msg)))

    def fail(path, obj):
        raise OSError("disk full")

    monkeypatch.setattr(statemod, "atomic_write_json", fail)
    backend.setStarred(CLIQUE, True)
    assert backend.starredKeys  # shown at once, without waiting for the worker
    wait(app, backend)
    assert backend.starredKeys == {} and backend.starred == []
    assert any(kind == "error" and "disk full" in msg for kind, msg in toasts)


def test_empty_page_says_how_to_star(app, ui):
    backend, win = ui()
    show_page(app, backend, win, 3)
    texts = " ".join(str(i.property("text")) for i in _visible(in_page(win, "starredList")))
    assert "Nothing starred yet" in texts
