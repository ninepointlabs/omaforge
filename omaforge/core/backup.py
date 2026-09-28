"""Snapshots of a client's WTF folder (SavedVariables, settings), with restore."""

import os
import re
import shutil
import tarfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from omaforge import paths

try:  # Python 3.14+
    from compression import zstd  # noqa: F401

    MODE, EXT = "zst", ".tar.zst"
except ImportError:  # pragma: no cover
    MODE, EXT = "gz", ".tar.gz"


class BackupError(Exception):
    pass


@dataclass
class Backup:
    path: Path
    created: float
    reason: str
    size: int

    @property
    def id(self) -> str:
        return self.path.name.split(".tar")[0]

    def to_dict(self) -> dict:
        return {"id": self.id, "path": str(self.path), "created": self.created, "reason": self.reason, "size": self.size}


def backup_dir(client_key: str) -> Path:
    return paths.data_dir() / "backups" / client_key


def create(wtf_dir: Path, client_key: str, reason: str = "manual", keep: int = 10) -> Backup | None:
    if not wtf_dir.is_dir():
        return None
    dest_dir = backup_dir(client_key)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "-", reason.lower()).strip("-") or "manual"
    dest = dest_dir / f"{stamp}-{slug}{EXT}"
    n = 1
    while dest.exists():
        n += 1
        dest = dest_dir / f"{stamp}-{slug}-{n}{EXT}"
    tmp = dest.with_name(dest.name + ".part")
    try:
        with tarfile.open(tmp, f"w:{MODE}") as tar:
            tar.add(wtf_dir, arcname="WTF")
        tmp.replace(dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    created = Backup(dest, dest.stat().st_mtime, slug, dest.stat().st_size)
    prune(client_key, keep)
    return created


def list_backups(client_key: str) -> list[Backup]:
    out = []
    files = [p for p in backup_dir(client_key).glob("*.tar.*") if not p.name.endswith(".part")]
    for p in sorted(files, key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True):
        m = re.match(r"\d{8}-\d{6}-(.+?)(?:-\d+)?\.tar\.", p.name)
        out.append(Backup(p, p.stat().st_mtime, m.group(1) if m else "", p.stat().st_size))
    return out


def prune(client_key: str, keep: int) -> None:
    if keep <= 0:
        return
    for b in list_backups(client_key)[keep:]:
        b.path.unlink(missing_ok=True)


def find(client_key: str, backup_id: str) -> Backup:
    for b in list_backups(client_key):
        if b.id == backup_id or b.path.name == backup_id:
            return b
    raise BackupError(f"no backup {backup_id!r} for {client_key}")


def restore(backup: Backup, wtf_dir: Path, client_key: str, keep: int = 10) -> Backup | None:
    """Replace WTF with a backup. The current WTF is backed up first."""
    safety = create(wtf_dir, client_key, reason="before-restore", keep=keep + 1)
    stage = wtf_dir.parent / f".omaforge-restore-{uuid.uuid4().hex[:12]}"
    stage.mkdir()
    try:
        with tarfile.open(backup.path, "r:*") as tar:
            tar.extractall(stage, filter="data")
        new = stage / "WTF"
        if not new.is_dir():
            raise BackupError("backup does not contain a WTF folder")
        old = wtf_dir.parent / f".omaforge-oldwtf-{uuid.uuid4().hex[:12]}"
        if wtf_dir.exists():
            os.rename(wtf_dir, old)
        try:
            os.rename(new, wtf_dir)
        except OSError:
            if old.exists():
                os.rename(old, wtf_dir)
            raise
        shutil.rmtree(old, ignore_errors=True)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return safety
