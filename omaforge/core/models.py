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
    downloads_monthly: int = 0  # WoWInterface only
    favorites: int = 0  # WoWInterface favorites, GitHub stars
    rank: int = 0  # CurseForge game popularity rank (1 = most popular)
    icon: str = ""
    categories: list[str] = field(default_factory=list)
    external_only: bool = False  # author disabled downloads in third-party apps

    def to_dict(self) -> dict:
        return asdict(self)


# What a star remembers, so the addon can be listed without asking its source again.
# Left out on purpose: version, updated, compatible and rank describe one game version
# at one moment, and a star is for every game version, for as long as it stays.
STAR_FIELDS = ("name", "author", "summary", "url", "icon", "downloads", "favorites", "categories", "external_only")


def star_keys(addon: dict) -> list[str]:
    """provider:id of a remote or installed addon as a dict, then those its TOC links to. Empty without a source."""
    provider, addon_id = addon.get("provider"), addon.get("id") or addon.get("source_id")
    if not provider or not addon_id:
        return []
    links = addon.get("links") or {}
    return [f"{provider}:{addon_id}"] + [f"{p}:{i}" for p, i in links.items() if f"{p}:{i}" != f"{provider}:{addon_id}"]


def star_record(addon: dict, starred_at: int) -> dict:
    """What state.json keeps for a star; fields of the wrong type are dropped."""
    blank = RemoteAddon("", "", "")
    kept = {f: addon[f] for f in STAR_FIELDS if isinstance(addon.get(f), type(getattr(blank, f)))}
    return {**kept, "starred_at": starred_at}


def starred_addon(key: str, record: dict) -> dict | None:
    """A star as a whole RemoteAddon dict for the UI, or None if its key isn't provider:id."""
    provider, _, addon_id = key.partition(":")
    if not provider or not addon_id:
        return None
    starred_at = record.get("starred_at")
    kept = star_record(record, starred_at if isinstance(starred_at, int) else 0)
    starred_at = kept.pop("starred_at")
    kept["name"] = kept.get("name") or addon_id
    return {**RemoteAddon(provider, addon_id, **kept).to_dict(), "starred_at": starred_at}


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


@dataclass
class Screenshot:
    url: str
    thumbnail: str = ""
    title: str = ""


@dataclass
class AddonDetails:
    """Everything a source says about one addon, for the details view."""

    addon: RemoteAddon
    description: str = ""
    description_format: str = "html"  # "html" (a small safe subset) or "markdown"
    screenshots: list[Screenshot] = field(default_factory=list)
    links: dict[str, str] = field(default_factory=dict)  # label -> URL: Website, Source, Issues, Wiki, Donate
    game_versions: list[str] = field(default_factory=list)  # as the source lists them
    created: int = 0  # unix seconds

    def to_dict(self) -> dict:
        return asdict(self)
