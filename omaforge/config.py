"""User configuration in ~/.config/omaforge/config.toml.

The file is small and flat, so it is written back with a tiny TOML emitter
rather than pulling in a dependency. It holds API keys, so it is kept 0600.
"""

import copy
import os
import shutil
import time
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


class ConfigError(Exception):
    """A settings file omaforge can't use; `path` is that file."""

    def __init__(self, message: str, path: Path | None = None):
        super().__init__(message)
        self.path = path


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


def _kind(value) -> str:
    if isinstance(value, dict):
        return "a table"
    if isinstance(value, bool):
        return "true or false"
    if isinstance(value, int):
        return "a number"
    if isinstance(value, list):
        return "a list"
    return "a string" if isinstance(value, str) else type(value).__name__


def _check(defaults: dict, user: dict, prefix: str = "") -> str | None:
    """The first setting whose type differs from the default's, as a message."""
    for key, value in user.items():
        if key not in defaults:
            continue  # unknown keys are kept and ignored, as before
        name = f"{prefix}{key}"
        want = defaults[key]
        if _kind(value) != _kind(want):
            return f"{name} must be {_kind(want)}, not {_kind(value)}"
        if isinstance(want, list) and not all(isinstance(x, str) for x in value):
            return f"{name} must be a list of strings"
        if isinstance(want, dict):
            problem = _check(want, value, f"{name}.")
            if problem:
                return problem
    return None


def read_user(path: Path | None = None) -> dict:
    """The file as written, or {} when there is none; ConfigError when it can't be used."""
    path = path or config_path()
    try:
        with open(path, "rb") as fh:
            user = tomllib.load(fh)
    except FileNotFoundError:
        return {}
    except OSError as e:
        raise ConfigError(f"{path}: cannot read it ({e.strerror})", path) from None
    except UnicodeDecodeError:
        raise ConfigError(f"{path}: not UTF-8 text", path) from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}", path) from None
    problem = _check(DEFAULTS, user)
    if problem:
        raise ConfigError(f"{path}: {problem}", path)
    return user


def load(path: Path | None = None) -> dict:
    cfg = _merge(DEFAULTS, read_user(path))
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


def set_aside(path: Path | None = None) -> Path | None:
    """Rename the file to a timestamped copy next to it (kept 0600); returns the copy."""
    path = path or config_path()
    if not path.exists():
        return None
    dest = path.with_name(f"{path.name}.broken-{time.strftime('%Y%m%d-%H%M%S')}")
    n = 1
    while dest.exists():
        n += 1
        dest = dest.with_name(f"{path.name}.broken-{time.strftime('%Y%m%d-%H%M%S')}-{n}")
    shutil.copy2(path, dest)
    os.chmod(dest, 0o600)
    path.unlink()
    return dest


def save(cfg: dict, path: Path | None = None) -> None:
    path = path or config_path()
    try:
        read_user(path)
    except ConfigError:
        # Never write over a file we could not read: keep a copy first.
        set_aside(path)
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
