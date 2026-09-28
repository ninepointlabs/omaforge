"""GitHub releases, using the BigWigs packager's release.json to pick a zip per flavor."""

import calendar
import re
import time
import urllib.parse

from omaforge.core.models import Folder, Release, RemoteAddon
from omaforge.core.providers.base import GameContext, Match, Provider, ProviderError

API = "https://api.github.com"
REPO = re.compile(r"^(?:https?://github\.com/)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")


def parse_repo(text: str) -> str | None:
    m = REPO.match(text.strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


def release_channel(release: dict) -> str:
    tag = f"{release.get('tag_name', '')} {release.get('name', '')}".lower()
    if "alpha" in tag:
        return "alpha"
    if release.get("prerelease") or "beta" in tag:
        return "beta"
    return "stable"


def _ts(iso: str | None) -> int:
    if not iso:
        return 0
    return calendar.timegm(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ"))


class GitHub(Provider):
    name = "github"
    label = "GitHub"

    def _headers(self) -> dict:
        h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        token = self.config.get("token")
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    def _api(self, path: str, ttl: float = 600):
        return self.http.get_json(f"{API}{path}", self._headers(), ttl=ttl)

    def get_addon(self, addon_id: str, ctx: GameContext) -> RemoteAddon:
        repo = parse_repo(addon_id)
        if not repo:
            raise ProviderError(f"GitHub: {addon_id!r} is not owner/repo")
        r = self._api(f"/repos/{repo}", ttl=3600)
        latest = self.resolve(repo, ctx, "stable")
        return RemoteAddon(
            provider=self.name,
            id=r["full_name"],
            name=r["name"],
            author=r["owner"]["login"],
            summary=r.get("description") or "",
            url=r["html_url"],
            favorites=int(r.get("stargazers_count") or 0),
            version=latest.version if latest else "",
            updated=latest.date if latest else _ts(r.get("pushed_at")),
            compatible=latest is not None,
        )

    def search(self, query: str, ctx: GameContext, limit: int = 30) -> list[RemoteAddon]:
        repo = parse_repo(query)
        if repo:
            try:
                return [self.get_addon(repo, ctx)]
            except ProviderError:
                pass
        q = urllib.parse.quote(f"{query} topic:wow-addon")
        data = self._api(f"/search/repositories?q={q}&sort=stars&per_page={min(limit, 30)}", ttl=3600)
        out = []
        for r in data.get("items", []):
            out.append(
                RemoteAddon(
                    provider=self.name,
                    id=r["full_name"],
                    name=r["name"],
                    author=r["owner"]["login"],
                    summary=r.get("description") or "",
                    url=r["html_url"],
                    favorites=int(r.get("stargazers_count") or 0),
                    updated=_ts(r.get("pushed_at")),
                )
            )
        return out

    def _release_json(self, release: dict) -> dict | None:
        asset = next((a for a in release.get("assets", []) if a["name"] == "release.json"), None)
        if not asset:
            return None
        # Release assets never change once published; cache them for a long time.
        return self.http.get_json(asset["browser_download_url"], ttl=30 * 86400)

    def _pick(self, release: dict, ctx: GameContext) -> tuple[dict, str] | None:
        """(asset, compat) for this game, or None."""
        assets = {a["name"]: a for a in release.get("assets", [])}
        meta = self._release_json(release)
        if meta is not None:
            for flavors, compat in ((ctx.game.release_flavors, "ok"), (ctx.game.release_fallback, "fallback")):
                for entry in meta.get("releases", []):
                    if entry.get("nolib"):
                        continue
                    if any(m.get("flavor") in flavors for m in entry.get("metadata", [])):
                        asset = assets.get(entry.get("filename"))
                        if asset:
                            return asset, compat
            return None
        # No release.json: accept a single non-nolib zip, flavor unknown.
        zips = [a for n, a in assets.items() if n.endswith(".zip") and "nolib" not in n.lower()]
        return (zips[0], "unverified") if len(zips) == 1 else None

    def versions(self, addon_id: str, ctx: GameContext) -> list[Release]:
        repo = parse_repo(addon_id)
        if not repo:
            raise ProviderError(f"GitHub: {addon_id!r} is not owner/repo")
        releases = self._api(f"/repos/{repo}/releases?per_page=15")
        out = []
        for rel in releases:
            if rel.get("draft"):
                continue
            picked = self._pick(rel, ctx)
            if not picked:
                continue
            asset, compat = picked
            out.append(
                Release(
                    provider=self.name,
                    addon_id=repo,
                    version=rel.get("tag_name") or rel.get("name") or "",
                    download_url=asset["browser_download_url"],
                    filename=asset["name"],
                    channel=release_channel(rel),
                    date=_ts(rel.get("published_at")),
                    compat=compat,
                )
            )
        return out

    def match_installed(self, groups, folders: dict[str, Folder], ctx: GameContext) -> list[Match]:
        """Only a TOC X-Website pointing at a specific repo links a folder to GitHub."""
        out = []
        for g in groups:
            for f in g:
                m = re.match(r"https?://github\.com/([^/\s]+)/([^/\s#?]+)", folders[f].website)
                if m:
                    out.append(Match(self.name, f"{m.group(1)}/{m.group(2).removesuffix('.git')}", list(g), "website"))
                    break
        return out
