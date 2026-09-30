"""WoWInterface (MMOUI) via its public JSON API. No key needed."""

import html
import re

from omaforge.core.describe import describe
from omaforge.core.http import HttpError
from omaforge.core.models import AddonDetails, Folder, Release, RemoteAddon, Screenshot
from omaforge.core.providers.base import GameContext, Match, Provider, ProviderError

API = "https://api.mmoui.com/v3/game/WOW"


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


class WoWInterface(Provider):
    name = "wowinterface"
    label = "WoWInterface"

    def _filelist(self) -> list[dict]:
        data = self.http.get_json(f"{API}/filelist.json", ttl=3600)
        if not isinstance(data, list):
            raise ProviderError("WoWInterface: unexpected filelist response")
        return data

    def _details(self, addon_id: str, ttl: float = 600) -> dict:
        data = self.http.get_json(f"{API}/filedetails/{addon_id}.json", ttl=ttl)
        if isinstance(data, dict) and data.get("ERROR"):
            raise ProviderError(f"WoWInterface: {data['ERROR']} (id {addon_id})")
        if not isinstance(data, list) or not data:
            raise ProviderError(f"WoWInterface: no addon {addon_id}")
        return data[0]

    @staticmethod
    def compatible(entry: dict, ctx: GameContext) -> bool:
        compat = entry.get("UICompatibility") or []
        if not compat or not ctx.game.wowi_majors:
            return True  # the author did not say; do not hide it
        for c in compat:
            m = re.match(r"(\d+)", str(c.get("version", "")))
            if m and int(m.group(1)) in ctx.game.wowi_majors:
                return True
        return False

    def _remote(self, e: dict, ctx: GameContext) -> RemoteAddon:
        return RemoteAddon(
            provider=self.name,
            id=str(e["UID"]),
            name=e.get("UIName", ""),
            author=e.get("UIAuthorName", ""),
            summary="",
            url=e.get("UIFileInfoURL", ""),
            downloads=int(e.get("UIDownloadTotal") or 0),
            version=e.get("UIVersion", ""),
            updated=int(e.get("UIDate") or 0) // 1000,
            folders=list(e.get("UIDir") or []),
            compatible=self.compatible(e, ctx),
            downloads_monthly=int(e.get("UIDownloadMonthly") or 0),
            favorites=int(e.get("UIFavoriteTotal") or 0),
            icon=next(iter(e.get("UIIMG_Thumbs") or []), ""),
        )

    def search(self, query: str, ctx: GameContext, limit: int = 50) -> list[RemoteAddon]:
        q = _norm(query)
        if not q:
            return []
        tokens = q.split()
        scored = []
        for e in self._filelist():
            if not self.compatible(e, ctx):
                continue
            name = _norm(e.get("UIName", ""))
            dirs = " ".join(_norm(d) for d in e.get("UIDir") or [])
            hay = f"{name} {dirs} {_norm(e.get('UIAuthorName', ''))}"
            if str(e.get("UID")) == query.strip():
                score = 0
            elif name == q:
                score = 1
            elif name.startswith(q):
                score = 2
            elif all(t in name for t in tokens):
                score = 3
            elif all(t in hay for t in tokens):
                score = 4
            else:
                continue
            scored.append((score, -int(e.get("UIDownloadTotal") or 0), e))
        scored.sort(key=lambda s: (s[0], s[1]))
        return [self._remote(e, ctx) for _, _, e in scored[:limit]]

    explore_sorts = ("popular", "downloads", "updated", "favorites", "name")

    def find_by_folders(self, folders: list[str], ctx: GameContext) -> str | None:
        """The WoWInterface id of the addon shipping (mostly) these folders."""
        if not folders:
            return None
        want = {f.lower() for f in folders}
        best = None
        for e in self._filelist():
            dirs = {d.lower() for d in e.get("UIDir") or []}
            if not (want & dirs) or not self.compatible(e, ctx):
                continue
            overlap = len(want & dirs) / len(want | dirs)
            if overlap >= 0.5 and (best is None or overlap > best[0]):
                best = (overlap, str(e["UID"]))
        return best[1] if best else None

    def top(self, ctx: GameContext, sort: str = "popular", category: str | None = None,
            offset: int = 0, limit: int = 50) -> list[RemoteAddon]:
        # Only addons whose author lists this game; search is more lenient.
        entries = [e for e in self._filelist() if e.get("UICompatibility") and self.compatible(e, ctx)]
        keys = {
            "popular": lambda e: -int(e.get("UIDownloadMonthly") or 0),
            "downloads": lambda e: -int(e.get("UIDownloadTotal") or 0),
            "updated": lambda e: -int(e.get("UIDate") or 0),
            "favorites": lambda e: -int(e.get("UIFavoriteTotal") or 0),
            "name": lambda e: (e.get("UIName") or "").lower(),
        }
        entries.sort(key=keys.get(sort, keys["popular"]))
        return [self._remote(e, ctx) for e in entries[offset : offset + limit]]

    def get_addon(self, addon_id: str, ctx: GameContext) -> RemoteAddon:
        d = self._details(addon_id)
        r = self._remote(d, ctx)
        r.summary = (d.get("UIDescription") or "").split("\r\n\r\n")[0][:400]
        return r

    def details(self, addon_id: str, ctx: GameContext) -> AddonDetails:
        d = self._details(addon_id)
        try:
            # Only the file list has the screenshots, supported versions and page link.
            entry = next((e for e in self._filelist() if str(e.get("UID")) == str(d["UID"])), {})
        except (ProviderError, HttpError):
            entry = {}
        e = {**entry, **d}
        fmt, text = describe(d.get("UIDescription") or "", "bbcode")
        images = e.get("UIIMGs") or []
        thumbs = e.get("UIIMG_Thumbs") or []
        links = {"Website": e.get("UIFileInfoURL") or ""}
        if e.get("UIDonationLink"):
            links["Donate"] = html.unescape(e["UIDonationLink"])
        versions = []
        for c in e.get("UICompatibility") or []:
            label = f"{c.get('name')} ({c.get('version')})" if c.get("name") else str(c.get("version", ""))
            if label and label not in versions:
                versions.append(label)
        return AddonDetails(
            addon=self._remote(e, ctx),
            description=text,
            description_format=fmt,
            screenshots=[Screenshot(url, thumbs[i] if i < len(thumbs) else url) for i, url in enumerate(images)],
            links={k: v for k, v in links.items() if v},
            game_versions=versions,
        )

    def versions(self, addon_id: str, ctx: GameContext) -> list[Release]:
        d = self._details(addon_id)
        if d.get("UIPending") == "1":
            return []
        if not self.compatible(d, ctx):
            return []
        return [
            Release(
                provider=self.name,
                addon_id=str(d["UID"]),
                version=d.get("UIVersion", ""),
                download_url=d["UIDownload"],
                filename=d.get("UIFileName", ""),
                channel="stable",  # WoWInterface has one file per addon
                date=int(d.get("UIDate") or 0) // 1000,
            )
        ]

    def match_installed(self, groups, folders: dict[str, Folder], ctx: GameContext) -> list[Match]:
        matches, rest = [], []
        for g in groups:
            ids = {folders[f].provider_ids.get(self.name) for f in g} - {None}
            if ids:
                matches.append(Match(self.name, sorted(ids)[0], list(g), "toc"))
            else:
                rest.append(g)
        if not rest:
            return matches

        try:
            filelist = self._filelist()
        except ProviderError:
            return matches
        except Exception:  # offline with no cache: folder matching just does not happen
            return matches
        by_dir: dict[str, list[dict]] = {}
        for e in filelist:
            for d in e.get("UIDir") or []:
                by_dir.setdefault(d.lower(), []).append(e)

        installed = {f.lower(): f for f in folders}
        for g in rest:
            gset = {f.lower() for f in g}
            best = None
            for f in g:
                for e in by_dir.get(f.lower(), []):
                    dirs = {d.lower() for d in e.get("UIDir") or []}
                    present = dirs & installed.keys()
                    coverage = len(present) / len(dirs)
                    # The entry must cover the whole group and most of its folders must be installed.
                    if not gset <= dirs or coverage < 0.5:
                        continue
                    # Prefer full coverage, then the most specific entry, then popularity.
                    key = (coverage, -len(dirs), int(e.get("UIDownloadTotal") or 0))
                    if best is None or key > best[0]:
                        best = (key, e, present)
            if best:
                _, e, present = best
                matches.append(Match(self.name, str(e["UID"]), sorted({installed[p] for p in present}), "folders", e.get("UIName", "")))
        return matches
