from omaforge.core.http import Http
from omaforge.core.providers.base import GameContext, Match, Provider, ProviderError, ProviderUnavailable
from omaforge.core.providers.github import GitHub
from omaforge.core.providers.curseforge import CurseForge
from omaforge.core.providers.stubs import Wago
from omaforge.core.providers.wowinterface import WoWInterface

# Order is priority when several providers claim the same installed addon.
# CurseForge goes first because its fingerprint match names the exact file.
PROVIDERS = (CurseForge, WoWInterface, GitHub, Wago)


def build(http: Http, config: dict) -> dict[str, Provider]:
    out = {}
    for cls in PROVIDERS:
        pcfg = config.get("providers", {}).get(cls.name, {})
        if pcfg.get("enabled", True):
            out[cls.name] = cls(http, pcfg)
    return out


__all__ = ["GameContext", "Match", "Provider", "ProviderError", "ProviderUnavailable", "build", "PROVIDERS"]
