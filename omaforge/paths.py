"""XDG base directories for omaforge."""

import os
from pathlib import Path

APP = "omaforge"


def _xdg(var: str, default: str) -> Path:
    value = os.environ.get(var)
    base = Path(value) if value and os.path.isabs(value) else Path.home() / default
    return base / APP


def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config")


def data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share")


def cache_dir() -> Path:
    return _xdg("XDG_CACHE_HOME", ".cache")


def state_dir() -> Path:
    return _xdg("XDG_STATE_HOME", ".local/state")


def omarchy_theme_dir() -> Path:
    """The active Omarchy theme, as `omarchy theme set` materialises it."""
    state = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local/state")
    return Path(state) / "omarchy/current/theme"
