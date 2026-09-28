"""CurseForge via the official REST API (https://docs.curseforge.com/rest-api/).

Needs an API key issued to omaforge (providers.curseforge.api_key). Installed
addons are identified by folder fingerprints, which CurseForge matches to an
exact file, so the installed version is known even for copies omaforge did
not install.
"""

import calendar
import re
import time
import urllib.parse

from omaforge.core.models import Folder, Release, RemoteAddon
from omaforge.core.http import HttpError
from omaforge.core.providers.base import DistributionDisabled, GameContext, Match, Provider, ProviderError
from omaforge.core.providers.fingerprint import folder_fingerprint

API = "https://api.curseforge.com/v1"
WOW_GAME_ID = 1
ADDONS_CLASS_ID = 1
# CurseForge ModsSearchSortField values.
SORT_FIELDS = {"popular": 2, "updated": 3, "name": 4, "downloads": 6}
RELEASE_TYPES = {1: "stable", 2: "beta", 3: "alpha"}


def clean_version(display_name: str) -> str:
    """'Plater-v656' -> 'v656', 'RareScanner_12.1.0.11' -> '12.1.0.11'; 'v426' is unchanged."""
    return re.sub(r"^[A-Za-z][\w.']*?[-_ ]+(?=v?\d)", "", display_name.strip()) or display_name


def _ts(iso: str | None) -> int:
    if not iso:
        return 0
    return calendar.timegm(time.strptime(iso.split(".")[0].rstrip("Z"), "%Y-%m-%dT%H:%M:%S"))


class CurseForge(Provider):
    name = "curseforge"
    label = "CurseForge"

    @property
    def available(self) -> bool:
        return bool(self.config.get("api_key"))

    @property
    def unavailable_reason(self) -> str:
        return "" if self.available else "no API key (set providers.curseforge.api_key in config.toml)"

    def _headers(self) -> dict:
        return {"x-api-key": self.config["api_key"], "Accept": "application/json"}

    def _get(self, path: str, ttl: float = 600):
        self.require()
        return self.http.get_json(f"{API}{path}", self._headers(), ttl=ttl)["data"]

    def _version_type(self, ctx: GameContext) -> int:
        vt = ctx.game.curseforge_version_type
        if not vt:
            raise ProviderError(f"CurseForge: no game version type configured for {ctx.game.label}")
        return vt

    def _remote(self, m: dict, ctx: GameContext) -> RemoteAddon:
        vt = ctx.game.curseforge_version_type
        idx = [i for i in m.get("latestFilesIndexes", []) if i.get("gameVersionTypeId") == vt]
        return RemoteAddon(
            provider=self.name,
            id=str(m["id"]),
            name=m.get("name", ""),
            author=", ".join(a["name"] for a in m.get("authors", [])),
            summary=m.get("summary", ""),
            url=(m.get("links") or {}).get("websiteUrl", ""),
            downloads=int(m.get("downloadCount") or 0),
            version=next((clean_version(i["filename"].removesuffix(".zip")) for i in idx if i.get("releaseType") == 1), ""),
            updated=_ts(m.get("dateReleased")),
            compatible=bool(idx),
            rank=int(m.get("gamePopularityRank") or 0),
            icon=(m.get("logo") or {}).get("thumbnailUrl") or "",
            categories=[c["name"] for c in m.get("categories", [])],
            external_only=m.get("allowModDistribution") is False,
        )

    def search(self, query: str, ctx: GameContext, limit: int = 50) -> list[RemoteAddon]:
        q = urllib.parse.urlencode({
            "gameId": WOW_GAME_ID,
            "searchFilter": query,
            "gameVersionTypeId": self._version_type(ctx),
            "sortField": 2,  # popularity
            "sortOrder": "desc",
            "pageSize": min(limit, 50),
        })
        return [self._remote(m, ctx) for m in self._get(f"/mods/search?{q}", ttl=1800)]

    explore_sorts = ("popular", "downloads", "updated", "name")

    def categories(self, ctx: GameContext) -> list[dict]:
        data = self._get(f"/categories?gameId={WOW_GAME_ID}&classId={ADDONS_CLASS_ID}", ttl=7 * 86400)
        top = [c for c in data if c.get("parentCategoryId") == ADDONS_CLASS_ID and not c.get("isClass")]
        return sorted(({"id": str(c["id"]), "name": c["name"]} for c in top), key=lambda c: c["name"])

    def top(self, ctx: GameContext, sort: str = "popular", category: str | None = None,
            offset: int = 0, limit: int = 50) -> list[RemoteAddon]:
        params = {
            "gameId": WOW_GAME_ID,
            "classId": ADDONS_CLASS_ID,
            "gameVersionTypeId": self._version_type(ctx),
            "sortField": SORT_FIELDS.get(sort, 2),
            "sortOrder": "asc" if sort == "name" else "desc",
            "index": offset,
            "pageSize": min(limit, 50),
        }
        if category:
            params["categoryId"] = int(category)
        data = self._get(f"/mods/search?{urllib.parse.urlencode(params)}", ttl=3600)
        return [self._remote(m, ctx) for m in data]

    def get_addon(self, addon_id: str, ctx: GameContext) -> RemoteAddon:
        return self._remote(self._get(f"/mods/{int(addon_id)}", ttl=3600), ctx)

    def versions(self, addon_id: str, ctx: GameContext) -> list[Release]:
        vt = self._version_type(ctx)
        files = self._get(f"/mods/{int(addon_id)}/files?gameVersionTypeId={vt}&pageSize=50")
        out = []
        for f in files:
            if not f.get("isAvailable", True):
                continue
            out.append(
                Release(
                    provider=self.name,
                    addon_id=str(addon_id),
                    version=clean_version(f.get("displayName") or f.get("fileName", "")),
                    download_url=f.get("downloadUrl") or "",
                    filename=f.get("fileName", ""),
                    channel=RELEASE_TYPES.get(f.get("releaseType"), "alpha"),
                    date=_ts(f.get("fileDate")),
                    extra={"file_id": str(f["id"])},
                )
            )
        out.sort(key=lambda r: r.date, reverse=True)
        return out

    def resolve(self, addon_id: str, ctx: GameContext, channel: str = "stable") -> Release | None:
        release = super().resolve(addon_id, ctx, channel)
        if release and not release.download_url:
            # Authors can opt out of third-party distribution; the API then
            # gives no URL (403 on download-url) and the file is only on curseforge.com.
            try:
                url = self._get(f"/mods/{int(addon_id)}/files/{release.extra['file_id']}/download-url", ttl=3600)
            except HttpError as e:
                if e.status not in (403, 404):
                    raise
                url = None
            if not url:
                raise DistributionDisabled(
                    f"the author of CurseForge addon {addon_id} does not allow downloads in other apps"
                )
            release.download_url = url
        return release

    def alternates(self, addon_id: str, ctx: GameContext) -> tuple[str | None, list[str]]:
        """(GitHub repo from the project's source link, addon folders of its latest file for this game)."""
        m = self._get(f"/mods/{int(addon_id)}", ttl=3600)
        source = (m.get("links") or {}).get("sourceUrl") or ""
        match = re.match(r"https?://github\.com/([^/\s]+)/([^/\s#?]+)", source)
        repo = f"{match.group(1)}/{match.group(2).removesuffix('.git')}" if match else None
        vt = ctx.game.curseforge_version_type
        files = sorted(m.get("latestFiles", []),
                       key=lambda f: vt not in [g.get("gameVersionTypeId") for g in f.get("sortableGameVersions", [])])
        folders = [mod["name"] for mod in (files[0].get("modules", []) if files else [])]
        return repo, folders

    def match_installed(self, groups, folders: dict[str, Folder], ctx: GameContext) -> list[Match]:
        addons_dir = ctx.addons_dir
        out: list[Match] = []
        matched: set[str] = set()
        if self.available and addons_dir is not None:
            fps: dict[int, str] = {}
            for g in groups:
                for f in g:
                    try:
                        fps[folder_fingerprint(addons_dir / f)] = f
                    except OSError:
                        continue
            if fps:
                data = self.http.post_json(f"{API}/fingerprints/{WOW_GAME_ID}", {"fingerprints": sorted(fps)},
                                           self._headers(), ttl=3600)["data"]
                for m in data.get("exactMatches") or []:
                    file = m.get("file") or {}
                    mod_folders = [mod["name"] for mod in file.get("modules", []) if mod.get("fingerprint") in fps]
                    mod_folders = [f for f in mod_folders if f in folders and f not in matched]
                    if not mod_folders:
                        continue
                    matched |= set(mod_folders)
                    out.append(Match(self.name, str(m["id"]), mod_folders, "fingerprint",
                                     version=clean_version(file.get("displayName", ""))))
        # Without a fingerprint match, the TOC header still links the addon.
        for g in groups:
            if set(g) & matched:
                continue
            ids = {folders[f].provider_ids.get(self.name) for f in g} - {None}
            if ids:
                out.append(Match(self.name, sorted(ids)[0], list(g), "toc"))
        return out
