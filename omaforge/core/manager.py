"""The one entry point the CLI and the UI use. Everything else is plumbing."""

import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from omaforge import __version__, config as configmod, paths
from omaforge.core import backup as backupmod
from omaforge.core import discovery, flavors, install, scan
from omaforge.core.discovery import Client
from omaforge.core.flavors import parse_version
from omaforge.core.http import Http, HttpError
from omaforge.core.models import CHANNELS, InstalledAddon, Release, RemoteAddon
from omaforge.core.providers import GameContext, Provider, ProviderError, build as build_providers
from omaforge.core.providers.base import DistributionDisabled
from omaforge.core.state import State

EXPORT_FORMAT = "omaforge.addons"


class ManagerError(Exception):
    pass


def same_version(a: str, b: str) -> bool:
    def norm(v: str) -> str:
        v = (v or "").strip().lower()
        return v[1:] if v.startswith("v") and v[1:2].isdigit() else v

    return norm(a) == norm(b)


def display_name(toc_title: str, repo: str) -> str:
    """A GitHub addon's name: its TOC title, unless that is decorated ("<DBM Core> Main Core")."""
    if toc_title and not re.search(r"[<>\[\]{}]", toc_title):
        return toc_title
    words = re.sub(r"([a-z])([A-Z])", r"\1 \2", repo.split("/")[-1]).replace("-", " ").replace("_", " ")
    return words.strip() or repo


@dataclass
class UpdateResult:
    key: str
    name: str
    old: str
    new: str = ""
    ok: bool = True
    skipped: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class BulkResult:
    results: list[UpdateResult] = field(default_factory=list)
    backup: dict | None = None

    def to_dict(self) -> dict:
        return {"results": [r.to_dict() for r in self.results], "backup": self.backup}


class Manager:
    def __init__(self, cfg: dict | None = None, state: State | None = None, http: Http | None = None,
                 table: flavors.FlavorTable | None = None, home: Path | None = None):
        self.cfg = cfg if cfg is not None else configmod.load()
        self.state = state or State()
        self.http = http or Http(offline=self.cfg["network"]["offline"])
        self.table = table or flavors.load()
        self.home = home
        self.providers: dict[str, Provider] = build_providers(self.http, self.cfg)
        self._clients: list[Client] | None = None

    # Clients --------------------------------------------------------------
    def clients(self, refresh: bool = False) -> list[Client]:
        if self._clients is None or refresh:
            roots = self.cfg["roots"]
            self._clients = discovery.discover(self.table, roots["paths"], roots["autodetect"], self.home)
        return self._clients

    def client(self, selector: str | None = None) -> Client:
        clients = self.clients()
        if not clients:
            raise ManagerError("no World of Warcraft clients found; add an install with `omaforge roots add <path>`")
        if not selector:
            if len(clients) == 1:
                return clients[0]
            live_retail = [c for c in clients if c.game and c.game.id == "retail" and c.channel == "live"]
            return (live_retail or clients)[0]
        s = selector.lower().strip("_")
        exact = [c for c in clients if s in (c.key.lower(), c.folder.strip("_").lower(), c.label.lower())]
        if len(exact) == 1:
            return exact[0]
        by_game = [c for c in clients if c.game and c.game.id == s]
        if len(by_game) == 1:
            return by_game[0]
        matches = exact or by_game
        if matches:
            raise ManagerError(f"{selector!r} matches several clients: {', '.join(c.key for c in matches)}")
        raise ManagerError(f"no client {selector!r}; known: {', '.join(c.key for c in clients)}")

    def ctx(self, client: Client) -> GameContext:
        if client.game is None:
            raise ManagerError(f"{client.folder}: unknown game for product {client.product!r}; add a rule to flavors.toml")
        return GameContext(client.game, parse_version(client.version), client.interface, client.addons_dir)

    def roots_add(self, path: str) -> Path:
        root = discovery.normalize_root(Path(path))
        if root is None:
            raise ManagerError(f"{path}: no World of Warcraft install found there")
        cfg = configmod.load()
        if str(root) not in cfg["roots"]["paths"]:
            cfg["roots"]["paths"].append(str(root))
            configmod.save(cfg)
        self.cfg["roots"]["paths"] = cfg["roots"]["paths"]
        self._clients = None
        return root

    def roots_remove(self, path: str) -> None:
        cfg = configmod.load()
        root = discovery.normalize_root(Path(path))
        cfg["roots"]["paths"] = [p for p in cfg["roots"]["paths"] if p not in (path, str(root) if root else None)]
        configmod.save(cfg)
        self.cfg["roots"]["paths"] = cfg["roots"]["paths"]
        self._clients = None

    # Installed addons -----------------------------------------------------
    def _suffixes(self, client: Client) -> tuple[str, ...]:
        return client.game.toc_suffixes if client.game else ()

    def _compatible(self, client: Client, interfaces: list[int]) -> bool:
        ci = client.interface
        if not ci or not interfaces:
            return True
        return any(i // 10000 == ci // 10000 and i // 100 >= ci // 100 for i in interfaces)

    def installed(self, client: Client) -> list[InstalledAddon]:
        self.state.reload()
        folders = scan.read_folders(client.addons_dir, self._suffixes(client))
        records = self.state.addons(client.key)
        owned = {k: [f for f in r.get("folders", []) if f in folders] for k, r in records.items()}
        groups = scan.group_folders(folders, owned)

        by_folder_owner = {f: k for k, fs in owned.items() for f in fs}
        managed_groups, free_groups = [], []
        for g in groups:
            (managed_groups if g[0] in by_folder_owner else free_groups).append(g)

        claims = self._claim(client, free_groups, folders, set(by_folder_owner))
        addons: list[InstalledAddon] = []
        for g in managed_groups:
            k = by_folder_owner[g[0]]
            rec = records[k]
            addons.append(self._addon(client, g, folders, key=k, provider=rec["provider"], source_id=rec["id"],
                                      match="state", name=rec.get("name"), version=rec.get("version"), managed=True))
        for g, match in claims:
            if match is None:
                main = scan.main_folder(g, folders)
                addons.append(self._addon(client, g, folders, key=f"local:{main}"))
            else:
                addons.append(self._addon(client, g, folders, key=f"{match.provider}:{match.addon_id}",
                                          provider=match.provider, source_id=match.addon_id, match=match.how,
                                          version=match.version or None))
        addons.sort(key=lambda a: a.name.lower())
        return addons

    def _claim(self, client, groups, folders, taken: set[str]):
        """Let providers claim unowned groups, merging groups a claim spans."""
        if client.game is None:
            return [(g, None) for g in groups]
        ctx = self.ctx(client)
        remaining = [list(g) for g in groups]
        result = []
        for provider in self.providers.values():
            if not remaining:
                break
            try:
                matches = provider.match_installed(remaining, folders, ctx)
            except (ProviderError, HttpError):
                continue
            claimed_folders: set[str] = set()
            for m in matches:
                span = [g for g in remaining if set(g) & set(m.folders) and not set(g) & claimed_folders]
                if not span:
                    continue
                merged = sorted({f for g in span for f in g} | (set(m.folders) - taken - claimed_folders), key=str.lower)
                merged = [f for f in merged if f in folders]
                claimed_folders |= set(merged)
                result.append((merged, m))
            remaining = [g for g in remaining if not set(g) & claimed_folders]
        result += [(g, None) for g in remaining]
        # Two groups can claim the same addon (e.g. split by the heuristics): merge them.
        merged: dict[str, tuple[list[str], object]] = {}
        out = []
        for g, m in result:
            if m is None:
                out.append((g, None))
                continue
            k = f"{m.provider}:{m.addon_id}"
            if k in merged:
                merged[k][0].extend(g)
            else:
                merged[k] = (list(g), m)
        out += [(sorted(set(g), key=str.lower), m) for g, m in merged.values()]
        return out

    def _addon(self, client, group, folders, key, provider=None, source_id=None, match=None, name=None,
               version=None, managed=False) -> InstalledAddon:
        main = scan.main_folder(group, folders)
        f = folders[main]
        links = {}
        for fname in group:
            for p, pid in folders[fname].provider_ids.items():
                links.setdefault(p, pid)
        prefs = self.state.prefs(client.key, key)
        return InstalledAddon(
            key=key,
            name=name or f.title,
            main_folder=main,
            folders=group,
            version=version if version is not None else f.version,
            author=f.author,
            provider=provider,
            source_id=source_id,
            match=match,
            links=links,
            managed=managed,
            compatible=self._compatible(client, f.interfaces),
            loadable=f.loadable,
            channel=prefs["channel"],
            pinned=prefs["pinned"],
            ignored=prefs["ignored"],
        )

    # Updates --------------------------------------------------------------
    def _latest(self, client: Client, addon: InstalledAddon) -> InstalledAddon:
        provider = self.providers.get(addon.provider or "")
        if provider is None:
            addon.update_error = "no provider" if addon.provider is None else f"{addon.provider} disabled"
            return addon
        if not provider.available:
            addon.update_error = f"{provider.label}: {provider.unavailable_reason}"
            return addon
        try:
            addon.latest = provider.resolve(addon.source_id, self.ctx(client), addon.channel)
            if addon.latest is None:
                addon.update_error = f"no {addon.channel} release for {client.label}"
            elif same_version(addon.latest.version, addon.version):
                addon.latest.version = addon.version
        except (ProviderError, HttpError) as e:
            addon.update_error = str(e)
        return addon

    def check_updates(self, client: Client, addons: list[InstalledAddon] | None = None) -> list[InstalledAddon]:
        addons = addons if addons is not None else self.installed(client)
        todo = [a for a in addons if a.provider and not a.ignored]
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda a: self._latest(client, a), todo))
        return addons

    def update(self, client: Client, keys: list[str] | None = None, backup: bool | None = None,
               progress=None) -> BulkResult:
        """Update the given addons, or every updatable one when `keys` is None."""
        addons = self.check_updates(client)
        by_key = {a.key: a for a in addons}
        if keys is not None:
            missing = [k for k in keys if k not in by_key]
            if missing:
                raise ManagerError(f"not installed: {', '.join(missing)}")
            targets = [by_key[k] for k in keys]
        else:
            targets = [a for a in addons if a.update_available and not a.pinned and not a.ignored]

        result = BulkResult()
        pending = [a for a in targets if a.update_available and not a.pinned]
        bulk = keys is None or len(keys) > 1
        if backup is None:
            backup = bulk and self.cfg["backups"]["before_bulk_update"]
        if pending and backup:
            b = backupmod.create(client.wtf_dir, client.key, "before-update", self.cfg["backups"]["keep"])
            result.backup = b.to_dict() if b else None

        for a in targets:
            r = UpdateResult(a.key, a.name, a.version)
            if a.pinned:
                r.skipped = "pinned"
            elif a.update_error and not a.latest:
                r.ok, r.error = False, a.update_error
            elif not a.update_available:
                r.skipped = "up to date"
            else:
                if progress:
                    progress(a)
                try:
                    self._install_release(client, a.latest, previous=a.folders, name=a.name,
                                          replace_key=a.key)
                    r.new = a.latest.version
                except Exception as e:  # keep going; report per addon
                    r.ok, r.error = False, str(e)
            result.results.append(r)
        return result

    # Install / uninstall --------------------------------------------------
    def search(self, client: Client, query: str, providers: list[str] | None = None) -> tuple[list[RemoteAddon], dict[str, str]]:
        ctx = self.ctx(client)
        results, errors = [], {}
        for name, p in self.providers.items():
            if providers and name not in providers:
                continue
            if not p.available:
                continue
            try:
                results += p.search(query, ctx)
            except (ProviderError, HttpError) as e:
                errors[name] = str(e)
        return results, errors

    def explore_sources(self) -> list[dict]:
        return [{"name": p.name, "label": p.label, "sorts": list(p.explore_sorts)}
                for p in self.providers.values() if p.explore_sorts and p.available]

    def explore(self, client: Client, provider: str, sort: str = "popular", category: str | None = None,
                offset: int = 0, limit: int = 50) -> list[RemoteAddon]:
        p = self.providers.get(provider)
        if p is None or not p.explore_sorts:
            raise ManagerError(f"{provider} has no ranked addon lists")
        p.require()
        return p.top(self.ctx(client), sort, category or None, offset, limit)

    def categories(self, client: Client, provider: str) -> list[dict]:
        p = self.providers.get(provider)
        if p is None or not p.available:
            return []
        return p.categories(self.ctx(client))

    def install(self, client: Client, provider: str, addon_id: str, channel: str | None = None,
                force: bool = False) -> dict:
        p = self.providers.get(provider)
        if p is None:
            raise ManagerError(f"unknown or disabled provider {provider!r}")
        p.require()
        key = f"{provider}:{addon_id}"
        channel = channel or self.state.prefs(client.key, key)["channel"]
        if channel not in CHANNELS:
            raise ManagerError(f"channel must be one of {', '.join(CHANNELS)}")
        try:
            release = p.resolve(addon_id, self.ctx(client), channel)
        except DistributionDisabled as e:
            alt = self._alternate_source(client, provider, addon_id, channel)
            if alt is None:
                raise ManagerError(f"{e}, and no GitHub or WoWInterface copy was found; get it from curseforge.com") from e
            rec = self.install(client, *alt, channel=channel, force=force)
            rec["via"] = f"{alt[0]} (CurseForge downloads disabled by the author)"
            return rec
        if release is None:
            raise ManagerError(f"no {channel} release for {client.label}")
        # Adopt an existing unmanaged copy so its folders are replaced, not duplicated.
        previous, name = [], None
        for a in self.installed(client):
            if a.key == key:
                previous, name = a.folders, a.name
        if name is None:
            try:
                name = p.get_addon(addon_id, self.ctx(client)).name
            except (ProviderError, HttpError):
                name = addon_id
        rec = self._install_release(client, release, previous=previous, name=name, replace_key=key, force=force)
        with self.state.transaction() as st:
            st.set_pref(client.key, key, channel=channel)
        return rec

    def _alternate_source(self, client: Client, provider: str, addon_id: str, channel: str) -> tuple[str, str] | None:
        """Where else to get an addon whose CurseForge author blocks third-party downloads."""
        p = self.providers.get(provider)
        if not hasattr(p, "alternates"):
            return None
        ctx = self.ctx(client)
        try:
            repo, folders = p.alternates(addon_id, ctx)
        except (ProviderError, HttpError):
            return None
        gh = self.providers.get("github")
        if repo and gh and gh.available:
            try:
                if gh.resolve(repo, ctx, channel):
                    return "github", repo
            except (ProviderError, HttpError):
                pass
        wowi = self.providers.get("wowinterface")
        if folders and wowi and wowi.available:
            try:
                wid = wowi.find_by_folders(folders, ctx)
                if wid and wowi.resolve(wid, ctx, channel):
                    return "wowinterface", wid
            except (ProviderError, HttpError):
                pass
        return None

    def _install_release(self, client: Client, release: Release, previous: list[str], name: str,
                         replace_key: str, force: bool = False) -> dict:
        key = f"{release.provider}:{release.addon_id}"
        install.cleanup_scratch(client.addons_dir)
        dl_dir = paths.cache_dir() / "downloads"
        zip_path = dl_dir / f"{uuid.uuid4().hex}.zip"
        provider = self.providers[release.provider]
        try:
            self.http.download(release.download_url, zip_path, provider.download_headers(release))
            with self.state.transaction() as st:
                owners = {f: k for k, r in st.addons(client.key).items() if k not in (key, replace_key)
                          for f in r.get("folders", [])}
                new = install.install_zip(zip_path, client.addons_dir, previous=previous, owners=owners, force=force)
                if release.provider == "github":
                    # A repo name ("WeakAuras2") is a poor display name; use the addon's own title.
                    folders = scan.read_folders(client.addons_dir, self._suffixes(client))
                    present = [f for f in new if f in folders]
                    if present:
                        name = display_name(folders[scan.main_folder(present, folders)].title, release.addon_id)
                # Folders taken over from other records (with --force) leave those records.
                for k, r in list(st.addons(client.key).items()):
                    if k in (key, replace_key):
                        continue
                    r["folders"] = [f for f in r.get("folders", []) if f not in new]
                    if not r["folders"]:
                        st.remove_record(client.key, k)
                if replace_key != key:
                    st.remove_record(client.key, replace_key)
                rec = {
                    "provider": release.provider,
                    "id": release.addon_id,
                    "name": name,
                    "version": release.version,
                    "folders": new,
                    "filename": release.filename,
                    "release_date": release.date,
                    "release_channel": release.channel,
                    "compat": release.compat,
                    "installed_at": int(time.time()),
                    "omaforge": __version__,
                }
                st.set_record(client.key, key, rec)
            return rec
        finally:
            zip_path.unlink(missing_ok=True)

    def uninstall(self, client: Client, key: str) -> list[str]:
        addon = next((a for a in self.installed(client) if a.key == key), None)
        if addon is None:
            raise ManagerError(f"not installed: {key}")
        removed = install.remove_folders(client.addons_dir, addon.folders)
        with self.state.transaction() as st:
            st.remove_record(client.key, key)
            st.client(client.key)["prefs"].pop(key, None)
        return removed

    # Preferences ----------------------------------------------------------
    def set_pref(self, client: Client, key: str, **values) -> None:
        if "channel" in values and values["channel"] not in CHANNELS:
            raise ManagerError(f"channel must be one of {', '.join(CHANNELS)}")
        with self.state.transaction() as st:
            st.set_pref(client.key, key, **values)

    # Backups --------------------------------------------------------------
    def backup(self, client: Client, reason: str = "manual") -> backupmod.Backup | None:
        return backupmod.create(client.wtf_dir, client.key, reason, self.cfg["backups"]["keep"])

    def backups(self, client: Client) -> list[backupmod.Backup]:
        return backupmod.list_backups(client.key)

    def restore(self, client: Client, backup_id: str) -> backupmod.Backup | None:
        return backupmod.restore(backupmod.find(client.key, backup_id), client.wtf_dir, client.key,
                                 self.cfg["backups"]["keep"])

    # Export / import ------------------------------------------------------
    def export(self, client: Client) -> dict:
        addons = self.installed(client)
        return {
            "format": EXPORT_FORMAT,
            "version": 1,
            "exported": int(time.time()),
            "game": client.game.id if client.game else None,
            "client": client.label,
            "addons": [
                {"provider": a.provider, "id": a.source_id, "name": a.name, "version": a.version,
                 "channel": a.channel, "pinned": a.pinned, "ignored": a.ignored}
                for a in addons if a.provider
            ],
            "unknown": [{"name": a.name, "folders": a.folders} for a in addons if not a.provider],
        }

    def import_list(self, client: Client, data: dict, progress=None) -> list[UpdateResult]:
        if data.get("format") != EXPORT_FORMAT:
            raise ManagerError("not an omaforge addon list")
        installed = {a.key for a in self.installed(client)}
        out = []
        for entry in data.get("addons", []):
            key = f"{entry['provider']}:{entry['id']}"
            r = UpdateResult(key, entry.get("name", key), "")
            if key in installed:
                r.skipped = "already installed"
            else:
                if progress:
                    progress(entry)
                try:
                    rec = self.install(client, entry["provider"], entry["id"], entry.get("channel", "stable"))
                    r.new = rec["version"]
                except Exception as e:
                    r.ok, r.error = False, str(e)
            if r.ok:
                self.set_pref(client, key, pinned=bool(entry.get("pinned")), ignored=bool(entry.get("ignored")),
                              channel=entry.get("channel", "stable"))
            out.append(r)
        return out
