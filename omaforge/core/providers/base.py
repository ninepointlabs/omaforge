"""The provider interface every addon source implements."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from omaforge.core.flavors import Game
from omaforge.core.http import Http
from omaforge.core.models import Folder, Release, RemoteAddon


class ProviderError(Exception):
    pass


class ProviderUnavailable(ProviderError):
    """The provider cannot be used yet (missing API key, not implemented)."""


@dataclass
class Match:
    """A provider's claim that a set of installed folders is one of its addons."""

    provider: str
    addon_id: str
    folders: list[str]
    how: str  # "toc", "folders", "website", "fingerprint"
    name: str = ""
    version: str = ""  # installed version, when the provider can tell (fingerprints)


@dataclass
class GameContext:
    """What a provider needs to know about the target client."""

    game: Game
    version: tuple[int, ...]
    interface: int | None
    addons_dir: Path | None = None


class Provider(ABC):
    name: str = ""
    label: str = ""

    def __init__(self, http: Http, config: dict):
        self.http = http
        self.config = config

    @property
    def available(self) -> bool:
        return True

    @property
    def unavailable_reason(self) -> str:
        return ""

    def require(self) -> None:
        if not self.available:
            raise ProviderUnavailable(f"{self.label}: {self.unavailable_reason}")

    @abstractmethod
    def search(self, query: str, ctx: GameContext, limit: int = 50) -> list[RemoteAddon]: ...

    @abstractmethod
    def get_addon(self, addon_id: str, ctx: GameContext) -> RemoteAddon: ...

    @abstractmethod
    def versions(self, addon_id: str, ctx: GameContext) -> list[Release]:
        """Releases usable on this game, newest first."""

    def resolve(self, addon_id: str, ctx: GameContext, channel: str = "stable") -> Release | None:
        from omaforge.core.models import channel_allows

        for release in self.versions(addon_id, ctx):
            if channel_allows(channel, release.channel):
                return release
        return None

    def download_headers(self, release: Release) -> dict[str, str]:
        return {}

    @abstractmethod
    def match_installed(self, groups: list[list[str]], folders: dict[str, Folder], ctx: GameContext) -> list[Match]:
        """Claim installed folder groups that belong to this provider."""
