"""The flavor table: product id + version -> game and channel.

All knowledge about WoW branches lives in flavors.toml so that a new branch
can be added from ~/.config/omaforge/flavors.toml without a code change.
"""

import operator
import re
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from omaforge import paths
from omaforge.config import ConfigError

Version = tuple[int, ...]

_OPS = {">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt, "==": operator.eq}
_SPEC = re.compile(r"\s*(>=|<=|==|>|<)\s*([\d.]+)\s*")


def parse_version(text: str) -> Version:
    parts = re.findall(r"\d+", text or "")
    return tuple(int(p) for p in parts)


def _cmp(version: Version, spec: str) -> bool:
    m = _SPEC.fullmatch(spec)
    if not m:
        raise ValueError(f"bad version comparison {spec!r}")
    op, target = _OPS[m.group(1)], parse_version(m.group(2))
    # Compare on the target's precision: "<2" means major < 2, "==1.60" is 1.60.x.
    return op(version[: len(target)] + (0,) * max(0, len(target) - len(version)), target)


def interface_number(version: Version) -> int | None:
    """12.1.0 -> 120100, 1.15.7 -> 11507, 1.60.1 -> 16001."""
    if len(version) < 3:
        return None
    return version[0] * 10000 + version[1] * 100 + version[2]


@dataclass(frozen=True)
class Game:
    id: str
    label: str
    toc_suffixes: tuple[str, ...]
    release_flavors: tuple[str, ...]
    release_fallback: tuple[str, ...] = ()
    wowi_majors: tuple[int, ...] = ()
    curseforge_version_type: int | None = None
    verified: bool = True


@dataclass(frozen=True)
class Rule:
    products: tuple[str, ...]
    game: str
    version: tuple[str, ...] = ()
    channel: str | None = None
    verified: bool = True
    folders: tuple[str, ...] = ()

    def matches(self, product: str, version: Version, folder: str = "") -> bool:
        if "*" not in self.products and product not in self.products:
            return False
        if self.folders and folder not in self.folders:
            return False
        if self.version and not version:
            return False
        return all(_cmp(version, spec) for spec in self.version)


@dataclass(frozen=True)
class Resolution:
    game: Game
    channel: str
    verified: bool
    notes: tuple[str, ...] = ()


def channel_from_product(product: str) -> str:
    if product == "wowt" or product.endswith("_ptr"):
        return "ptr"
    if product == "wowxptr":
        return "xptr"
    if product.endswith("_beta") or product == "wowdev":
        return "beta"
    return "live"


@dataclass
class FlavorTable:
    games: dict[str, Game] = field(default_factory=dict)
    rules: list[Rule] = field(default_factory=list)
    folders: dict[str, str] = field(default_factory=dict)

    def folder_product(self, folder: str) -> str:
        """The product id to assume for a client folder without `.flavor.info`."""
        return self.folders.get(folder) or "wow" + folder.rstrip("_")

    def resolve(self, product: str, version: Version, folder: str = "") -> Resolution | None:
        for rule in self.rules:
            if rule.matches(product, version, folder):
                game = self.games[rule.game]
                notes = []
                if not rule.verified:
                    notes.append(f"product {product!r} mapped to {game.label} by an unverified rule")
                if not game.verified:
                    notes.append(f"{game.label}: TOC suffixes and release flavors are guesses")
                return Resolution(
                    game=game,
                    channel=rule.channel or channel_from_product(product),
                    verified=rule.verified and game.verified,
                    notes=tuple(notes),
                )
        return None


def _parse(data: dict) -> tuple[dict[str, Game], list[Rule], dict[str, str]]:
    games = {}
    for g in data.get("game", []):
        games[g["id"]] = Game(
            id=g["id"],
            label=g.get("label", g["id"]),
            toc_suffixes=tuple(g.get("toc_suffixes", [])),
            release_flavors=tuple(g.get("release_flavors", [])),
            release_fallback=tuple(g.get("release_fallback", [])),
            wowi_majors=tuple(g.get("wowi_majors", [])),
            curseforge_version_type=g.get("curseforge_version_type"),
            verified=g.get("verified", True),
        )
    rules = [
        Rule(
            products=tuple(r["products"]),
            game=r["game"],
            version=tuple(r.get("version", [])),
            channel=r.get("channel"),
            verified=r.get("verified", True),
            folders=tuple(r.get("folders", [])),
        )
        for r in data.get("rule", [])
    ]
    return games, rules, dict(data.get("folders", {}))


def _read_user(path: Path) -> tuple[dict[str, Game], list[Rule], dict[str, str]]:
    """The user's flavors.toml, or ConfigError naming the file and the problem."""
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except OSError as e:
        raise ConfigError(f"{path}: cannot read it ({e.strerror})", path) from None
    except UnicodeDecodeError:
        raise ConfigError(f"{path}: not UTF-8 text", path) from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}", path) from None
    for table in ("game", "rule"):
        entries = data.get(table, [])
        if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
            raise ConfigError(f"{path}: {table} must be written as [[{table}]] tables", path)
    if not isinstance(data.get("folders", {}), dict):
        raise ConfigError(f"{path}: folders must be a table", path)
    for i, g in enumerate(data.get("game", []), 1):
        if not isinstance(g.get("id"), str):
            raise ConfigError(f"{path}: [[game]] #{i} needs an id", path)
    for i, r in enumerate(data.get("rule", []), 1):
        if not isinstance(r.get("game"), str):
            raise ConfigError(f"{path}: [[rule]] #{i} needs a game", path)
        if not isinstance(r.get("products"), list) or not all(isinstance(p, str) for p in r["products"]):
            raise ConfigError(f"{path}: [[rule]] #{i} needs products, a list of product ids", path)
        specs = r.get("version", [])
        bad = [s for s in specs if not isinstance(s, str) or not _SPEC.fullmatch(s)] if isinstance(specs, list) else [specs]
        if bad:
            raise ConfigError(f"{path}: [[rule]] #{i} has a bad version comparison {bad[0]!r}", path)
    try:
        return _parse(data)
    except (TypeError, ValueError) as e:
        raise ConfigError(f"{path}: {e}", path) from None


def load(user_path: Path | None = None) -> FlavorTable:
    builtin = tomllib.loads(resources.files("omaforge.core").joinpath("flavors.toml").read_text("utf-8"))
    games, rules, folders = _parse(builtin)
    user_path = user_path if user_path is not None else paths.config_dir() / "flavors.toml"
    if user_path.is_file():
        ugames, urules, ufolders = _read_user(user_path)
        games.update(ugames)
        for i, rule in enumerate(urules, 1):
            if rule.game not in games:
                raise ConfigError(f"{user_path}: [[rule]] #{i} refers to unknown game {rule.game!r}", user_path)
        rules = urules + rules
        folders.update(ufolders)
    for rule in rules:
        if rule.game not in games:
            raise ValueError(f"flavor rule refers to unknown game {rule.game!r}")
    return FlavorTable(games, rules, folders)
