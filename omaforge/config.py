"""User configuration in ~/.config/omaforge/config.toml.

The file is small and flat, so it is written back with a tiny TOML emitter
rather than pulling in a dependency. It holds API keys, so it is kept 0600.
"""

import copy
import os
import tomllib
from pathlib import Path

from omaforge import paths
from omaforge.core.fsutil import atomic_write_text

DEFAULTS: dict = {
    "roots": {
        # Extra install roots added by hand. Each may be a WoW root
        # ("World of Warcraft"), a client folder ("_retail_") or a Wine prefix.
        "paths": [],
        "autodetect": True,
    },
    "providers": {
        "wowinterface": {"enabled": True},
        "github": {"enabled": True, "token": ""},
        "wago": {"enabled": True, "api_key": ""},
        "curseforge": {"enabled": True, "api_key": ""},
    },
    "backups": {"keep": 10, "before_bulk_update": True},
    "network": {"offline": False},
}


def config_path() -> Path:
    return paths.config_dir() / "config.toml"


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load(path: Path | None = None) -> dict:
    path = path or config_path()
    try:
        with open(path, "rb") as fh:
            user = tomllib.load(fh)
    except FileNotFoundError:
        user = {}
    cfg = _merge(DEFAULTS, user)
    # Environment wins for secrets so CI/timers need not write them to disk.
    env = {
        ("github", "token"): "OMAFORGE_GITHUB_TOKEN",
        ("wago", "api_key"): "OMAFORGE_WAGO_API_KEY",
        ("curseforge", "api_key"): "OMAFORGE_CURSEFORGE_API_KEY",
    }
    for (provider, key), var in env.items():
        if os.environ.get(var):
            cfg["providers"][provider][key] = os.environ[var]
    return cfg


def save(cfg: dict, path: Path | None = None) -> None:
    path = path or config_path()
    atomic_write_text(path, dumps(cfg), mode=0o600)


def _value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        escaped = v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    raise TypeError(f"cannot write {type(v).__name__} to TOML")


def dumps(cfg: dict) -> str:
    lines: list[str] = []

    def table(prefix: str, data: dict) -> None:
        scalars = {k: v for k, v in data.items() if not isinstance(v, dict)}
        tables = {k: v for k, v in data.items() if isinstance(v, dict)}
        if scalars:
            if prefix:
                lines.append(f"[{prefix}]")
            for k, v in scalars.items():
                lines.append(f"{k} = {_value(v)}")
            lines.append("")
        for k, v in tables.items():
            table(f"{prefix}.{k}" if prefix else k, v)

    table("", cfg)
    return "\n".join(lines).rstrip() + "\n"
