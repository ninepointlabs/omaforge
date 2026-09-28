"""Plain data types shared by the core, the CLI and the UI."""

from dataclasses import asdict, dataclass, field

CHANNELS = ("stable", "beta", "alpha")


def channel_allows(wanted: str, release_channel: str) -> bool:
    """A `beta` subscription accepts stable and beta releases, `alpha` accepts all."""
    return CHANNELS.index(release_channel) <= CHANNELS.index(wanted)


@dataclass
class RemoteAddon:
    provider: str
    id: str
    name: str
    author: str = ""
    summary: str = ""
    url: str = ""
    downloads: int = 0
    version: str = ""
    updated: int = 0  # unix seconds
    folders: list[str] = field(default_factory=list)
    compatible: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Release:
    provider: str
    addon_id: str
    version: str
    download_url: str
    filename: str = ""
    channel: str = "stable"
    date: int = 0
    # "ok", or "fallback" when chosen from a release_fallback flavor.
    compat: str = "ok"
    extra: dict[str, str] = field(default_factory=dict)  # provider-specific ids

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("extra")
        return d


@dataclass
class Folder:
    name: str
    title: str
    version: str
    interfaces: list[int]
    dependencies: list[str]
    provider_ids: dict[str, str]
    website: str
    author: str
    load_on_demand: bool
    loadable: bool  # the client finds a TOC it reads


@dataclass
class InstalledAddon:
    key: str  # "provider:id" when linked, "local:<folder>" otherwise
    name: str
    main_folder: str
    folders: list[str]
    version: str
    author: str = ""
    provider: str | None = None
    source_id: str | None = None
    match: str | None = None  # state, toc, folders, website
    links: dict[str, str] = field(default_factory=dict)
    managed: bool = False
    compatible: bool = True
    loadable: bool = True
    channel: str = "stable"
    pinned: bool = False
    ignored: bool = False
    latest: Release | None = None
    update_error: str = ""

    @property
    def update_available(self) -> bool:
        return bool(self.latest and self.latest.version and self.latest.version != self.version)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["latest"] = self.latest.to_dict() if self.latest else None
        d["update_available"] = self.update_available
        return d
