"""Wago Addons: wired in, waiting for an API key.

It needs a key issued to this application; omaforge never borrows another
client's key and never scrapes the site. With no key configured the
provider reports itself unavailable. With a key configured it still reports
unavailable until the API client is written, so a key alone never causes
half-implemented network calls.
"""

from omaforge.core.models import Folder
from omaforge.core.providers.base import GameContext, Match, Provider, ProviderUnavailable


class _KeyedStub(Provider):
    key_field = "api_key"
    implemented = False

    @property
    def available(self) -> bool:
        return bool(self.config.get(self.key_field)) and self.implemented

    @property
    def unavailable_reason(self) -> str:
        if not self.config.get(self.key_field):
            return f"no API key (set providers.{self.name}.{self.key_field} in config.toml)"
        return "API client not implemented yet"

    def search(self, query, ctx, limit=50):
        self.require()
        return []

    def get_addon(self, addon_id, ctx):
        self.require()
        raise ProviderUnavailable(self.unavailable_reason)

    def versions(self, addon_id, ctx):
        self.require()
        return []

    def match_installed(self, groups, folders: dict[str, Folder], ctx: GameContext) -> list[Match]:
        # TOC headers identify the addon even without a key, so it shows as
        # linked (but not updatable) instead of unknown.
        out = []
        for g in groups:
            ids = {folders[f].provider_ids.get(self.name) for f in g} - {None}
            if ids:
                out.append(Match(self.name, sorted(ids)[0], list(g), "toc"))
        return out


class Wago(_KeyedStub):
    name = "wago"
    label = "Wago Addons"
    # API: https://addons.wago.io/api/external (key issued on request).

