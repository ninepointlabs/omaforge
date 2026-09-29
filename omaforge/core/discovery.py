"""Find World of Warcraft installs in Wine prefixes and the clients inside them."""

import glob
import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from omaforge.core import buildinfo
from omaforge.core.flavors import FlavorTable, Game, parse_version, interface_number

WOW_DIRS = ("Program Files (x86)/World of Warcraft", "Program Files/World of Warcraft")
CLIENT_DIR = re.compile(r"^_[a-z0-9_]+_$")


@dataclass
class Client:
    root: Path
    folder: str
    product: str
    version: str
    game: Game | None
    channel: str
    verified: bool
    notes: list[str] = field(default_factory=list)

    @property
    def path(self) -> Path:
        return self.root / self.folder

    @property
    def addons_dir(self) -> Path:
        return self.path / "Interface" / "AddOns"

    @property
    def wtf_dir(self) -> Path:
        return self.path / "WTF"

    @property
    def key(self) -> str:
        """Stable id: the client folder plus a short hash of its root."""
        digest = hashlib.sha1(str(self.root).encode()).hexdigest()[:8]
        return f"{self.folder.strip('_')}@{digest}"

    @property
    def interface(self) -> int | None:
        return interface_number(parse_version(self.version))

    @property
    def label(self) -> str:
        name = self.game.label if self.game else self.product
        if self.channel != "live":
            name += f" {self.channel.upper() if self.channel in ('ptr', 'xptr') else self.channel.title()}"
        return name

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "root": str(self.root),
            "folder": self.folder,
            "path": str(self.path),
            "product": self.product,
            "version": self.version,
            "interface": self.interface,
            "game": self.game.id if self.game else None,
            "channel": self.channel,
            "verified": self.verified,
            "notes": list(self.notes),
        }


def _home() -> Path:
    return Path.home()


def lutris_prefixes(home: Path) -> list[Path]:
    out = []
    flatpak = home / ".var/app/net.lutris.Lutris"
    for cfg_dir in (home / ".local/share/lutris/games", home / ".config/lutris/games",
                    flatpak / "data/lutris/games", flatpak / "config/lutris/games"):
        for yml in sorted(cfg_dir.glob("*.yml")):
            try:
                text = yml.read_text("utf-8", errors="replace")
            except OSError:
                continue
            # Lutris game configs are YAML; the prefix sits under `game:`. A regex
            # avoids a YAML dependency and is enough for this one key.
            m = re.search(r"^game:\s*\n(?:[ \t]+.*\n)*?[ \t]+prefix:\s*(.+)$", text, re.M)
            if m:
                out.append(Path(os.path.expanduser(m.group(1).strip().strip("'\""))))
    return out


def steam_prefixes(home: Path) -> list[Path]:
    steam_roots = [
        home / ".steam/steam",
        home / ".local/share/Steam",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
    ]
    libraries = []
    for root in steam_roots:
        if not root.is_dir():
            continue
        libraries.append(root)
        vdf = root / "steamapps/libraryfolders.vdf"
        try:
            libraries += [Path(p) for p in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text("utf-8", errors="replace"))]
        except OSError:
            pass
    out = []
    for lib in libraries:
        out += [Path(p) / "pfx" for p in glob.glob(str(lib / "steamapps/compatdata/*"))]
    return out


def bottles_prefixes(home: Path) -> list[Path]:
    out = []
    for base in (home / ".local/share/bottles/bottles", home / ".var/app/com.usebottles.bottles/data/bottles/bottles"):
        out += [Path(p) for p in glob.glob(str(base / "*"))]
    return out


def other_prefixes(home: Path) -> list[Path]:
    out = [home / ".wine"]
    if os.environ.get("WINEPREFIX"):
        out.append(Path(os.environ["WINEPREFIX"]))
    out += [Path(p) for p in glob.glob(str(home / "Games/Heroic/Prefixes/*"))]
    out += [Path(p) for p in glob.glob(str(home / "Games/*"))]
    return out


def wow_root_in_prefix(prefix: Path) -> list[Path]:
    return [prefix / "drive_c" / d for d in WOW_DIRS if (prefix / "drive_c" / d).is_dir()]


def normalize_root(path: Path) -> Path | None:
    """Accept a WoW root, a client folder inside one, or a Wine prefix."""
    path = Path(os.path.expanduser(str(path)))
    if not path.is_dir():
        return None
    if CLIENT_DIR.match(path.name) and (path.parent / ".build.info").exists():
        return path.parent
    if (path / ".build.info").exists() or any(is_client_dir(p) for p in _children(path)):
        return path
    roots = wow_root_in_prefix(path)
    return roots[0] if roots else None


def _children(path: Path) -> list[Path]:
    try:
        return [p for p in path.iterdir() if p.is_dir()]
    except OSError:
        return []


def is_client_dir(path: Path) -> bool:
    return bool(CLIENT_DIR.match(path.name)) and (path / "Interface" / "AddOns").is_dir()


def find_roots(extra: list[str] | None = None, autodetect: bool = True, home: Path | None = None) -> list[Path]:
    home = home or _home()
    candidates: list[Path] = []
    if autodetect:
        prefixes = lutris_prefixes(home) + steam_prefixes(home) + bottles_prefixes(home) + other_prefixes(home)
        for prefix in prefixes:
            candidates += wow_root_in_prefix(prefix)
    for p in extra or []:
        root = normalize_root(Path(p))
        if root:
            candidates.append(root)
    seen, out = set(), []
    for c in candidates:
        real = os.path.realpath(c)
        if real not in seen:
            seen.add(real)
            out.append(Path(real))
    return out


def clients_in_root(root: Path, table: FlavorTable) -> list[Client]:
    builds = buildinfo.read_builds(root)
    clients = []
    for child in sorted(_children(root)):
        if not is_client_dir(child):
            continue
        notes = []
        product = buildinfo.read_flavor(child)
        if not product:
            # No .flavor.info: guess the product from the folder name.
            product = "wow" if child.name == "_retail_" else "wow" + child.name.rstrip("_")
            notes.append(f"no .flavor.info; product guessed from folder name as {product!r}")
        version = builds.get(product, {}).get("version", "")
        if not version:
            notes.append(f"product {product!r} not listed in .build.info; version unknown")
        res = table.resolve(product, parse_version(version))
        if res is None:
            notes.append(f"no flavor rule matches product {product!r} version {version or '?'}")
            clients.append(Client(root, child.name, product, version, None, "live", False, notes))
            continue
        clients.append(
            Client(root, child.name, product, version, res.game, res.channel, res.verified, notes + list(res.notes))
        )
    return clients


def discover(table: FlavorTable, extra: list[str] | None = None, autodetect: bool = True, home: Path | None = None) -> list[Client]:
    clients = []
    for root in find_roots(extra, autodetect, home):
        clients += clients_in_root(root, table)
    return clients
