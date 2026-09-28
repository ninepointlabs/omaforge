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

Version = tuple[int, ...]

_OPS = {">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt, "==": operator.eq}


def parse_version(text: str) -> Version:
    parts = re.findall(r"\d+", text or "")
    return tuple(int(p) for p in parts)


def _cmp(version: Version, spec: str) -> bool:
    m = re.fullmatch(r"\s*(>=|<=|==|>|<)\s*([\d.]+)\s*", spec)
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

    def matches(self, product: str, version: Version) -> bool:
        if "*" not in self.products and product not in self.products:
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

    def resolve(self, product: str, version: Version) -> Resolution | None:
        for rule in self.rules:
            if rule.matches(product, version):
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


def _parse(data: dict) -> tuple[dict[str, Game], list[Rule]]:
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
        )
        for r in data.get("rule", [])
    ]
    return games, rules


def load(user_path: Path | None = None) -> FlavorTable:
    builtin = tomllib.loads(resources.files("omaforge.core").joinpath("flavors.toml").read_text("utf-8"))
    games, rules = _parse(builtin)
    user_path = user_path if user_path is not None else paths.config_dir() / "flavors.toml"
    if user_path.is_file():
        with open(user_path, "rb") as fh:
            ugames, urules = _parse(tomllib.load(fh))
        games.update(ugames)
        rules = urules + rules
    for rule in rules:
        if rule.game not in games:
            raise ValueError(f"flavor rule refers to unknown game {rule.game!r}")
    return FlavorTable(games, rules)
