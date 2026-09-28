"""What omaforge installed, and per-addon preferences, per client.

Stored in ~/.local/share/omaforge/state.json. Writes go through a lock file
so the GUI and a timer-driven `omaforge update --all` cannot interleave.
"""

import contextlib
import fcntl
from pathlib import Path

from omaforge import paths
from omaforge.core.fsutil import atomic_write_json, read_json

SCHEMA = 1


class State:
    def __init__(self, path: Path | None = None):
        self.path = path or paths.data_dir() / "state.json"
        self.data = self._load()

    def _load(self) -> dict:
        data = read_json(self.path, None) or {"schema": SCHEMA, "clients": {}}
        data.setdefault("clients", {})
        return data

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
