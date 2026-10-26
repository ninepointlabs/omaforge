"""What omaforge installed, and per-addon preferences, per client.

Stored in ~/.local/share/omaforge/state.json. Writes go through a lock file
so the GUI and a timer-driven `omaforge update --all` cannot interleave.

omaforge writes this file itself, so a damaged one is not fatal: it is moved
aside to state.json.damaged-<time> (never deleted) and a new one is started.
`recovered` says so, and the CLI and the UI tell the user.
"""

import contextlib
import fcntl
import json
import os
import time
from pathlib import Path

from omaforge import paths
from omaforge.core.fsutil import atomic_write_json

SCHEMA = 1


def _problem(data) -> str | None:
    """Why a decoded state.json can't be used, or None when it can."""
    if not isinstance(data, dict):
        return "it is not a JSON object"
    clients = data.get("clients", {})
    if not isinstance(clients, dict):
        return "clients is not an object"
    for key, client in clients.items():
        if not isinstance(client, dict):
            return f"client {key!r} is not an object"
        for part in ("addons", "prefs"):
            entries = client.get(part, {})
            if not isinstance(entries, dict) or not all(isinstance(v, dict) for v in entries.values()):
                return f"{part} of client {key!r} is not an object of objects"
    return None


class State:
    def __init__(self, path: Path | None = None):
        self.path = path or paths.data_dir() / "state.json"
        # (where the damaged file went, what was wrong) once one has been set aside.
        self.recovered: tuple[Path, str] | None = None
        self.data = self._load()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text("utf-8"))
            problem = _problem(data)
        except FileNotFoundError:
            data, problem = None, None
        except UnicodeDecodeError:
            problem = "it is not UTF-8 text"
        except json.JSONDecodeError as e:
            problem = f"it is not valid JSON ({e})"
        if problem:
            moved = self._set_aside()
            if moved is None:  # another omaforge process moved it first
                return self._load()
            self.recovered = (moved, problem)
            data = None
        data = data or {"schema": SCHEMA, "clients": {}}
        data.setdefault("clients", {})
        return data

    def _set_aside(self) -> Path | None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest = self.path.with_name(f"{self.path.name}.damaged-{stamp}")
        n = 1
        while dest.exists():
            n += 1
            dest = self.path.with_name(f"{self.path.name}.damaged-{stamp}-{n}")
        try:
            os.rename(self.path, dest)
        except FileNotFoundError:
            return None
        return dest

    def recovery_message(self) -> str:
        if not self.recovered:
            return ""
        moved, problem = self.recovered
        return (f"{self.path} could not be read: {problem}. It was moved to {moved} and a new one started; "
                "pins, ignores, channels and install sources recorded there are reset until you restore it.")

    def reload(self) -> None:
        self.data = self._load()

    @contextlib.contextmanager
    def transaction(self):
        """Re-read under an exclusive lock, let the caller mutate, then save."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path.with_suffix(".lock"), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.data = self._load()
            yield self
            atomic_write_json(self.path, self.data)

    def client(self, key: str) -> dict:
        c = self.data["clients"].setdefault(key, {})
        c.setdefault("addons", {})
        c.setdefault("prefs", {})
        return c

    # Managed addons -------------------------------------------------------
    def addons(self, key: str) -> dict[str, dict]:
        return self.client(key)["addons"]

    def record(self, key: str, addon_key: str) -> dict | None:
        return self.addons(key).get(addon_key)

    def set_record(self, key: str, addon_key: str, record: dict) -> None:
        self.addons(key)[addon_key] = record

    def remove_record(self, key: str, addon_key: str) -> None:
        self.addons(key).pop(addon_key, None)

    def owner_of(self, key: str, folder: str) -> str | None:
        for addon_key, rec in self.addons(key).items():
            if folder in rec.get("folders", []):
                return addon_key
        return None

    # Preferences (also for addons omaforge did not install) ----------------
    def prefs(self, key: str, addon_key: str) -> dict:
        p = self.client(key)["prefs"].get(addon_key, {})
        return {"pinned": p.get("pinned", False), "ignored": p.get("ignored", False), "channel": p.get("channel", "stable")}

    def set_pref(self, key: str, addon_key: str, **values) -> None:
        prefs = self.client(key)["prefs"].setdefault(addon_key, {})
        prefs.update(values)
