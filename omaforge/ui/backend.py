"""The bridge between QML and the core Manager.

All Manager calls run on one worker thread, one job at a time, so the UI
never blocks on the network and the Manager is never used concurrently.
Results come back through a queued signal and update plain list/dict
properties that QML binds to.
"""

import copy
import json
import os
import subprocess
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from omaforge import __version__, config as configmod
from omaforge.buildkey import builtin_curseforge_key
from omaforge.core.describe import clean_html
from omaforge.core.manager import Manager


def markdown_to_html(text: str) -> str:
    """Markdown as the same small HTML subset the other sources give (main thread: QTextDocument)."""
    from PySide6.QtGui import QTextDocument

    doc = QTextDocument()
    doc.setMarkdown(text)
    return clean_html(doc.toHtml())


def _path(url_or_path: str) -> Path:
    if url_or_path.startswith("file:"):
        return Path(QUrl(url_or_path).toLocalFile())
    return Path(os.path.expanduser(url_or_path))


class Backend(QObject):
    changed = Signal()
    busyChanged = Signal()
    detailsChanged = Signal()
    toast = Signal(str, str)  # kind (info, error), message
    _done = Signal(object, object, object)  # callback, result, error

    def __init__(self, manager: Manager | None = None, parent=None):
        super().__init__(parent)
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="omaforge")
        self._jobs = 0
        self._status = ""
        self.m = manager
        self._clients: list[dict] = []
        self._current = ""
        self._addons: list[dict] = []
        self._checked = False
        self._results: list[dict] = []
        self._search_errors: dict = {}
        self._backups: list[dict] = []
        self._providers: list[dict] = []
        self._explore_sources: list[dict] = []
        self._explore = {"provider": "", "sort": "popular", "category": "", "client": ""}
        self._explore_results: list[dict] = []
        self._explore_categories: list[dict] = []
        self._explore_more = False
        self._details: dict = {}
        self._details_for = ""  # provider:id the details view is waiting for
        self._done.connect(self._finish)
        self._run(self._load_clients, self._clients_loaded, "Looking for World of Warcraft")

    # Job plumbing ---------------------------------------------------------
    def _run(self, fn, then=None, status: str = "") -> None:
        self._jobs += 1
        if status:
            self._status = status
        self.busyChanged.emit()

        def job():
            try:
                self._done.emit(then, fn(), None)
            except Exception as e:  # reported in the UI, never swallowed
                traceback.print_exc()
                self._done.emit(then, None, e)

        self._pool.submit(job)

    @Slot(object, object, object)
    def _finish(self, then, result, error) -> None:
        self._jobs -= 1
        if self._jobs == 0:
            self._status = ""
        self.busyChanged.emit()
        if error is not None:
            self.toast.emit("error", str(error))
        elif then is not None:
            then(result)

    def _client(self):
        return self.m.client(self._current) if self._current else None

    # Properties -----------------------------------------------------------
    @Property(bool, notify=busyChanged)
    def busy(self):
        return self._jobs > 0

    @Property(str, notify=busyChanged)
    def status(self):
        return self._status

    @Property(str, constant=True)
    def version(self):
        return __version__

    @Property("QVariantList", notify=changed)
    def clients(self):
        return self._clients

    @Property(str, notify=changed)
    def currentClient(self):
        return self._current

    @Property("QVariantMap", notify=changed)
    def client(self):
        return next((c for c in self._clients if c["key"] == self._current), {})

    @Property("QVariantList", notify=changed)
    def addons(self):
        return self._addons

    @Property(bool, notify=changed)
    def checked(self):
        return self._checked

    @Property(int, notify=changed)
    def updateCount(self):
        return sum(1 for a in self._addons if a["update_available"] and not a["pinned"] and not a["ignored"])

    @Property("QVariantList", notify=changed)
    def searchResults(self):
        return self._results

    @Property("QVariantMap", notify=changed)
    def searchErrors(self):
        return self._search_errors

    @Property("QVariantList", notify=changed)
    def backups(self):
        return self._backups

    @Property("QVariantList", notify=changed)
    def providers(self):
        return self._providers

    @Property("QVariantList", notify=changed)
    def exploreSources(self):
        return self._explore_sources

    @Property(str, notify=changed)
    def exploreProvider(self):
        return self._explore["provider"]

    @Property(str, notify=changed)
    def exploreSort(self):
        return self._explore["sort"]

    @Property(str, notify=changed)
    def exploreCategory(self):
        return self._explore["category"]

    @Property("QVariantList", notify=changed)
    def exploreCategories(self):
        return self._explore_categories

    @Property("QVariantList", notify=changed)
    def exploreResults(self):
        return self._explore_results

    @Property(bool, notify=changed)
    def exploreHasMore(self):
        return self._explore_more

    @Property("QVariantMap", notify=detailsChanged)
    def details(self):
        return self._details

    @Property(bool, notify=detailsChanged)
    def detailsLoading(self):
        return bool(self._details_for) and not self._details

    @Property("QVariantMap", notify=changed)
    def settings(self):
        cfg = configmod.load()
        return {
            "roots": list(cfg["roots"]["paths"]),
            "autodetect": cfg["roots"]["autodetect"],
            "githubToken": cfg["providers"]["github"]["token"],
            "curseforgeKey": cfg["providers"]["curseforge"]["api_key"],
            "curseforgeBuiltin": bool(builtin_curseforge_key()),
            "wagoKey": cfg["providers"]["wago"]["api_key"],
            "backupsKeep": cfg["backups"]["keep"],
            "backupBeforeUpdate": cfg["backups"]["before_bulk_update"],
            "offline": cfg["network"]["offline"],
            "configPath": str(configmod.config_path()),
        }

    # Clients --------------------------------------------------------------
    def _load_clients(self):
        if self.m is None:
            self.m = Manager()
        clients = self.m.clients(refresh=True)
        providers = [{"name": p.name, "label": p.label, "available": p.available, "reason": p.unavailable_reason}
                     for p in self.m.providers.values()]
        return [c.to_dict() for c in clients], providers, self.m.explore_sources()

    def _clients_loaded(self, result) -> None:
        self._clients, self._providers, self._explore_sources = result
        names = [s["name"] for s in self._explore_sources]
        if self._explore["provider"] not in names:
            self._explore.update(provider=names[0] if names else "", category="", client="")
        keys = [c["key"] for c in self._clients]
        if self._current not in keys:
            self._current = self.m.client(None).key if self._clients else ""
        self.changed.emit()
        if self._current:
            self.selectClient(self._current)

    @Slot()
    def rescan(self) -> None:
        self._run(self._load_clients, self._clients_loaded, "Looking for World of Warcraft")

    @Slot(str)
    def selectClient(self, key: str) -> None:
        if key != self._current:
            self._results, self._search_errors = [], {}
        self._current = key
        self._addons, self._checked, self._backups = [], False, []
        self.changed.emit()
        self.refresh(check=True)

    # Addons ---------------------------------------------------------------
    def _set_addons(self, result) -> None:
        addons, checked = result
        self._addons = [a.to_dict() for a in addons]
        self._checked = checked
        self.changed.emit()

    @Slot()
    def refresh(self, check: bool = False) -> None:
        client = self._client()
        if client is None:
            return
        key = self._current

        def work():
            addons = self.m.installed(client)
            return addons, False

        def then(result):
            if key == self._current:
                self._set_addons(result)
                if check:
                    self.checkUpdates()

        self._run(work, then, "Reading addons")

    @Slot()
    def checkUpdates(self) -> None:
        client, key = self._client(), self._current
        if client is None:
            return

        def then(result):
            if key == self._current:
                self._set_addons(result)

        self._run(lambda: (self.m.check_updates(client), True), then, "Checking for updates")

    def _after_update(self, res) -> None:
        updated = [r for r in res.results if r.new]
        failed = [r for r in res.results if not r.ok]
        if failed:
            self.toast.emit("error", "; ".join(f"{r.name}: {r.error}" for r in failed))
        if updated:
            msg = ", ".join(f"{r.name} {r.new}" for r in updated)
            if res.backup:
                msg += " (WTF backed up first)"
            self.toast.emit("info", f"Updated {msg}")
        elif not failed:
            self.toast.emit("info", "Everything is up to date")
        self.checkUpdates()

    @Slot()
    def updateAll(self) -> None:
        client = self._client()
        if client:
            self._run(lambda: self.m.update(client), self._after_update, "Updating addons")

    @Slot(str)
    def updateAddon(self, key: str) -> None:
        client = self._client()
        if client:
            self._run(lambda: self.m.update(client, [key]), self._after_update, "Updating")

    @Slot(str)
    def uninstall(self, key: str) -> None:
        client = self._client()
        if client is None:
            return
        name = next((a["name"] for a in self._addons if a["key"] == key), key)

        def then(removed):
            self.toast.emit("info", f"Removed {name} ({len(removed)} folder{'s' if len(removed) != 1 else ''})")
            self.refresh()

        self._run(lambda: self.m.uninstall(client, key), then, f"Removing {name}")

    def _pref(self, key: str, **values) -> None:
        client = self._client()
        if client is None:
            return
        for a in self._addons:
            if a["key"] == key:
                a.update(values)
        self.changed.emit()
        self._run(lambda: self.m.set_pref(client, key, **values),
                  (lambda _: self.checkUpdates()) if "channel" in values else None)

    @Slot(str, bool)
    def setPinned(self, key: str, value: bool) -> None:
        self._pref(key, pinned=value)

    @Slot(str, bool)
    def setIgnored(self, key: str, value: bool) -> None:
        self._pref(key, ignored=value)

    @Slot(str, str)
    def setChannel(self, key: str, channel: str) -> None:
        self._pref(key, channel=channel)

    # Search / install -----------------------------------------------------
    @Slot(str, "QVariantList")
    def search(self, query: str, providers) -> None:
        client, key = self._client(), self._current
        if client is None or not query.strip():
            return
        def then(result):
            if key != self._current:
                return
            results, errors = result
            self._results = self._mark_installed([r.to_dict() for r in results])
            if not self._results and not errors:
                self.toast.emit("info", f"Nothing found for \"{query}\"")
            self._search_errors = errors
            self.changed.emit()

        self._run(lambda: self.m.search(client, query, list(providers) or None), then, f"Searching for {query}")

    # Explore ---------------------------------------------------------------
    def _installed_keys(self) -> set[str]:
        """provider:id of every installed addon, including the sources its TOC links to."""
        keys = set()
        for a in self._addons:
            keys.add(a["key"])
            keys.update(f"{p}:{i}" for p, i in (a.get("links") or {}).items())
        return keys

    def _mark_installed(self, results: list[dict]) -> list[dict]:
        installed = self._installed_keys()
        return [{**r, "installed": f"{r['provider']}:{r['id']}" in installed} for r in results]

    @Slot()
    def ensureExplore(self) -> None:
        """Load the ranked list for the current client unless it is already shown."""
        if self._explore["provider"] and (self._explore["client"] != self._current or not self._explore_results):
            self.loadExplore(self._explore["provider"], self._explore["sort"], self._explore["category"])

    @Slot(str, str, str)
    def loadExplore(self, provider: str, sort: str, category: str) -> None:
        client = self._client()
        if client is None or not provider:
            return
        source = next((s for s in self._explore_sources if s["name"] == provider), None)
        if source and sort not in source["sorts"]:
            sort = source["sorts"][0]
        provider_changed = provider != self._explore["provider"]
        self._explore.update(provider=provider, sort=sort, category=category, client=self._current)
        self._explore_results, self._explore_more = [], False
        if provider_changed:
            self._explore_categories = []
        self.changed.emit()
        key = self._current

        def work():
            cats = self.m.categories(client, provider) if provider_changed or not self._explore_categories else None
            return self.m.explore(client, provider, sort, category or None, 0, 50), cats

        def then(result):
            if key != self._current or provider != self._explore["provider"]:
                return
            results, cats = result
            if cats is not None:
                self._explore_categories = cats
            self._explore_results = self._mark_installed([r.to_dict() for r in results])
            self._explore_more = len(results) == 50
            self.changed.emit()

        self._run(work, then, "Loading top addons")

    @Slot()
    def exploreMore(self) -> None:
        client, e = self._client(), dict(self._explore)
        if client is None or not self._explore_more:
            return
        offset = len(self._explore_results)

        def then(results):
            if e != self._explore:
                return
            self._explore_results = self._explore_results + self._mark_installed([r.to_dict() for r in results])
            self._explore_more = len(results) == 50
            self.changed.emit()

        self._run(lambda: self.m.explore(client, e["provider"], e["sort"], e["category"] or None, offset, 50),
                  then, "Loading more")

    # Details ---------------------------------------------------------------
    @Slot(str, str)
    def loadDetails(self, provider: str, addon_id: str) -> None:
        client = self._client()
        want = f"{provider}:{addon_id}"
        self._details_for, self._details = want, {}
        if client is None:
            self._details = {"error": "No World of Warcraft client selected"}
        self.detailsChanged.emit()
        if client is None:
            return

        def work():
            try:
                return self.m.details(client, provider, addon_id).to_dict()
            except Exception as e:  # shown in the details view instead of a toast
                traceback.print_exc()
                return {"error": str(e)}

        def then(details):
            if self._details_for == want:
                if details.get("description_format") == "markdown":
                    details.update(description=markdown_to_html(details["description"]), description_format="html")
                self._details = details
                self.detailsChanged.emit()

        self._run(work, then, "Loading details")

    @Slot()
    def closeDetails(self) -> None:
        self._details_for, self._details = "", {}
        self.detailsChanged.emit()

    @Slot(str, str, str)
    def install(self, provider: str, addon_id: str, channel: str) -> None:
        client = self._client()
        if client is None:
            return

        def then(rec):
            warn = "" if rec["compat"] == "ok" else " (flavor not verified for this client)"
            via = f" from {rec['via']}" if rec.get("via") else ""
            self.toast.emit("info", f"Installed {rec['name']} {rec['version']}{via}{warn}")
            for r in self._results + self._explore_results:
                if r["provider"] == provider and r["id"] == addon_id:
                    r["installed"] = True
            self.changed.emit()
            self.refresh()

        self._run(lambda: self.m.install(client, provider, addon_id, channel or None), then, "Installing")

    # Backups --------------------------------------------------------------
    @Slot()
    def loadBackups(self) -> None:
        client = self._client()
        if client is None:
            return

        def then(bs):
            self._backups = [b.to_dict() for b in bs]
            self.changed.emit()

        self._run(lambda: self.m.backups(client), then)

    @Slot()
    def createBackup(self) -> None:
        client = self._client()
        if client is None:
            return

        def then(b):
            self.toast.emit("info", f"Backed up WTF ({b.size / 1e6:.1f} MB)" if b else "No WTF folder to back up yet")
            self.loadBackups()

        self._run(lambda: self.m.backup(client), then, "Backing up WTF")

    @Slot(str)
    def restoreBackup(self, backup_id: str) -> None:
        client = self._client()
        if client is None:
            return

        def then(safety):
            self.toast.emit("info", f"Restored {backup_id}" + (f"; the previous WTF is saved as {safety.id}" if safety else ""))
            self.loadBackups()

        self._run(lambda: self.m.restore(client, backup_id), then, "Restoring WTF")

    # Export / import ------------------------------------------------------
    @Slot(str)
    def exportList(self, url: str) -> None:
        client = self._client()
        if client is None:
            return
        path = _path(url)

        def work():
            data = self.m.export(client)
            path.write_text(json.dumps(data, indent=2) + "\n")
            return data

        self._run(work, lambda d: self.toast.emit("info", f"Exported {len(d['addons'])} addons to {path.name}"), "Exporting")

    @Slot(str)
    def importList(self, url: str) -> None:
        client = self._client()
        if client is None:
            return
        path = _path(url)

        def then(results):
            failed = [r for r in results if not r.ok]
            new = [r for r in results if r.new]
            self.toast.emit("error" if failed else "info",
                            f"Imported {len(new)} addons" + (f"; failed: {', '.join(r.name for r in failed)}" if failed else ""))
            self.refresh()

        self._run(lambda: self.m.import_list(client, json.loads(path.read_text())), then, "Importing")

    # Settings -------------------------------------------------------------
    @Slot(str)
    def addRoot(self, url: str) -> None:
        def then(root):
            self.toast.emit("info", f"Added {root}")
            self.changed.emit()
            self.rescan()

        self._run(lambda: self.m.roots_add(str(_path(url))), then, "Adding install")

    @Slot(str)
    def removeRoot(self, path: str) -> None:
        self._run(lambda: self.m.roots_remove(path), lambda _: (self.changed.emit(), self.rescan()))

    @Slot("QVariantMap")
    def saveSettings(self, s) -> None:
        def work():
            cfg = configmod.load()
            cfg["roots"]["autodetect"] = bool(s["autodetect"])
            cfg["providers"]["github"]["token"] = s["githubToken"].strip()
            cfg["providers"]["curseforge"]["api_key"] = s["curseforgeKey"].strip()
            cfg["providers"]["wago"]["api_key"] = s["wagoKey"].strip()
            cfg["backups"]["keep"] = int(s["backupsKeep"])
            cfg["backups"]["before_bulk_update"] = bool(s["backupBeforeUpdate"])
            cfg["network"]["offline"] = bool(s["offline"])
            configmod.save(cfg)
            self.m = Manager(cfg=configmod.load())

        def then(_):
            self.toast.emit("info", "Settings saved")
            self.rescan()

        self._run(work, then, "Saving settings")

    @Slot(str)
    def openPath(self, path: str) -> None:
        subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @Slot(str)
    def openUrl(self, url: str) -> None:
        if url.startswith(("https://", "http://")):
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
