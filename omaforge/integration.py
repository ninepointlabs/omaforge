"""`omaforge setup omarchy`: add omaforge to the Omarchy menu and, optionally, a keybinding.

Edits live between marker comments in the user's own config files, so they
can be updated or removed again without touching anything else:

  ~/.config/omarchy/extensions/omarchy-menu.jsonc   (hot-reloads)
  ~/.config/hypr/bindings.lua                       (validated with hyprctl)

A timestamped backup is written next to each file before it changes.
"""

import re
import shutil
import subprocess
import time
from pathlib import Path

LAUNCH = "omarchy-launch-or-focus omaforge 'uwsm-app -- omaforge'"
MENU_BEGIN = "  // >>> omaforge — managed by `omaforge setup omarchy`, do not edit between the markers"
MENU_END = "  // <<< omaforge"
LUA_BEGIN = "-- >>> omaforge — managed by `omaforge setup omarchy`, do not edit between the markers"
LUA_END = "-- <<< omaforge"
ICON = "\U000f02b4"  # nf-md-gamepad_variant


class SetupError(Exception):
    pass


def require_omarchy() -> None:
    if not shutil.which("omarchy"):
        raise SetupError("`omarchy` not found; `setup omarchy` only applies to Omarchy systems. "
                         "Elsewhere, launch omaforge from your app launcher or run `omaforge`.")


def menu_path(home: Path) -> Path:
    return home / ".config/omarchy/extensions/omarchy-menu.jsonc"


def bindings_path(home: Path) -> Path:
    return home / ".config/hypr/bindings.lua"


def _strip_block(text: str, begin: str, end: str) -> str:
    pattern = re.compile(rf"^[ \t]*{re.escape(begin.strip())}.*?^[ \t]*{re.escape(end.strip())}[^\n]*\n?", re.M | re.S)
    return pattern.sub("", text)


def _backup(path: Path) -> None:
    if path.exists():
        shutil.copy2(path, path.with_name(f"{path.name}.bak.{int(time.time())}"))


def menu_block() -> str:
    entry = (f'  "omaforge": {{"icon":"{ICON}","label":"WoW Addons",'
             f'"description":"omaforge: World of Warcraft addon manager",'
             f'"action":"{LAUNCH}","when":"command -v omaforge >/dev/null"}},')
    return f"{MENU_BEGIN}\n{entry}\n{MENU_END}\n"


def install_menu(home: Path) -> Path:
    path = menu_path(home)
    text = path.read_text("utf-8") if path.exists() else "{\n}\n"
    text = _strip_block(text, MENU_BEGIN, MENU_END)
    idx = text.find("{")
    if idx < 0:
        raise SetupError(f"{path}: no top-level object to add to")
    new = text[: idx + 1] + "\n" + menu_block() + text[idx + 1 :].lstrip("\n")
    _backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new, "utf-8")
    return path


def remove_menu(home: Path) -> bool:
    path = menu_path(home)
    if not path.exists():
        return False
    text = path.read_text("utf-8")
    new = _strip_block(text, MENU_BEGIN, MENU_END)
    if new != text:
        _backup(path)
        path.write_text(new, "utf-8")
    return new != text


def normalize_keys(keys: str) -> str:
    """'super+shift+z' -> 'SUPER + SHIFT + Z'."""
    parts = [p.strip().upper() for p in keys.replace("+", " ").split()]
    if len(parts) < 2:
        raise SetupError(f"{keys!r}: give modifiers and a key, e.g. 'SUPER + SHIFT + Z'")
    return " + ".join(parts)


def binding_conflict(keys: str) -> str | None:
    """The description of an existing binding on these keys, if `omarchy` can tell."""
    if not shutil.which("omarchy"):
        return None
    try:
        out = subprocess.run(["omarchy", "menu", "keybindings", "--print"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    mods, key = keys.split(" + ")[:-1], keys.split(" + ")[-1]
    listed = f"{' '.join(mods)} + {key}"  # the listing's form: "SUPER SHIFT + W"
    for line in out.splitlines():
        if line.startswith(listed + " ") and "→" in line and "omaforge" not in line.lower() and "WoW addons" not in line:
            return line.split("→", 1)[1].strip()
    return None


def install_binding(home: Path, keys: str, validate: bool = True) -> Path:
    keys = normalize_keys(keys)
    path = bindings_path(home)
    if not path.exists():
        raise SetupError(f"{path} not found; is this an Omarchy system?")
    conflict = binding_conflict(keys)
    if conflict:
        raise SetupError(f"{keys} is already bound to {conflict!r}; pick another combination")
    original = path.read_text("utf-8")
    text = _strip_block(original, LUA_BEGIN, LUA_END).rstrip("\n")
    block = f'{LUA_BEGIN}\no.bind("{keys}", "WoW addons", "{LAUNCH}")\n{LUA_END}\n'
    _backup(path)
    path.write_text(f"{text}\n\n{block}", "utf-8")
    if validate:
        errors = hyprland_errors()
        if errors:
            path.write_text(original, "utf-8")
            hyprland_errors()
            raise SetupError(f"Hyprland rejected the binding, change reverted: {errors}")
    return path


def remove_binding(home: Path, validate: bool = True) -> bool:
    path = bindings_path(home)
    if not path.exists():
        return False
    text = path.read_text("utf-8")
    new = _strip_block(text, LUA_BEGIN, LUA_END)
    if new == text:
        return False
    _backup(path)
    path.write_text(new.rstrip("\n") + "\n", "utf-8")
    if validate:
        hyprland_errors()
    return True


def hyprland_errors() -> str:
    """Reload Hyprland and return its config errors ('' when clean or not running)."""
    if not shutil.which("hyprctl"):
        return ""
    try:
        subprocess.run(["hyprctl", "reload"], capture_output=True, timeout=10)
        out = subprocess.run(["hyprctl", "configerrors"], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return "" if not out or out.lower() in ("no errors", "") else out
