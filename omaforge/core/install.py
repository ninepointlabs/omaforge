"""Install and remove addon folders atomically.

A download is extracted into a staging directory next to AddOns (same
filesystem, so renames are atomic), then each folder is swapped in with
rename(2). The folders it replaces are parked in a trash directory until
every swap has succeeded; on any failure everything is moved back.
"""

import os
import shutil
import stat
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from omaforge.core import toc as tocmod

MAX_UNCOMPRESSED = 1024 * 1024 * 1024
MAX_FILES = 50_000


class InstallError(Exception):
    pass


class ConflictError(InstallError):
    def __init__(self, conflicts: dict[str, str]):
        names = ", ".join(f"{f} (owned by {o})" for f, o in sorted(conflicts.items()))
        super().__init__(f"folders belong to another addon: {names}")
        self.conflicts = conflicts


def _safe_members(zf: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members, total = [], 0
    infos = zf.infolist()
    if len(infos) > MAX_FILES:
        raise InstallError(f"archive has too many files ({len(infos)})")
    for info in infos:
        name = info.filename.replace("\\", "/")
        p = PurePosixPath(name)
        if p.is_absolute() or ".." in p.parts or (p.parts and ":" in p.parts[0]):
            raise InstallError(f"unsafe path in archive: {info.filename}")
        if stat.S_ISLNK(info.external_attr >> 16):
            raise InstallError(f"symlink in archive: {info.filename}")
        total += info.file_size
        if total > MAX_UNCOMPRESSED:
            raise InstallError("archive expands to more than 1 GiB")
        members.append(info)
    return members


def extract(zip_path: Path, dest: Path) -> list[str]:
    """Extract to `dest` and return the addon folder names found at its top level."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            members = _safe_members(zf)
            dest.mkdir(parents=True)
            for info in members:
                target = dest / info.filename.replace("\\", "/")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
    except zipfile.BadZipFile as e:
        raise InstallError(f"not a valid zip: {e}") from e

    folders = [p.name for p in dest.iterdir() if p.is_dir() and tocmod.any_toc(p)]
    if not folders:
        # Some archives wrap the addon folders in one extra directory.
        subdirs = [p for p in dest.iterdir() if p.is_dir() and not p.name.startswith("__MACOSX")]
        if len(subdirs) == 1:
            inner = [p for p in subdirs[0].iterdir() if p.is_dir() and tocmod.any_toc(p)]
            for p in inner:
                p.rename(dest / p.name)
            folders = [p.name for p in inner]
    if not folders:
        raise InstallError("archive contains no addon folders (no .toc files)")
    return sorted(folders, key=str.lower)


def _scratch(addons_dir: Path, kind: str) -> Path:
    return addons_dir.parent / f".omaforge-{kind}-{uuid.uuid4().hex[:12]}"


def install_zip(
    zip_path: Path,
    addons_dir: Path,
    previous: list[str] | tuple[str, ...] = (),
    owners: dict[str, str] | None = None,
    force: bool = False,
) -> list[str]:
    """Install an addon archive.

    `previous` are the folders this addon owned before (removed if the new
    version no longer ships them). `owners` maps folders owned by *other*
    managed addons to their keys; overwriting one needs `force`.
    Returns the installed folder names.
    """
    addons_dir.mkdir(parents=True, exist_ok=True)
    stage = _scratch(addons_dir, "stage")
    trash = _scratch(addons_dir, "trash")
    try:
        new = extract(zip_path, stage)
        conflicts = {f: o for f, o in (owners or {}).items() if f in new}
        if conflicts and not force:
            raise ConflictError(conflicts)

        trash.mkdir()
        moved_out: list[str] = []  # existing folders parked in trash
        moved_in: list[str] = []  # new folders swapped into AddOns
        try:
            for name in new:
                dest = addons_dir / name
                if dest.exists() or dest.is_symlink():
                    os.rename(dest, trash / name)
                    moved_out.append(name)
                os.rename(stage / name, dest)
                moved_in.append(name)
            for name in previous:
                if name not in new and (addons_dir / name).exists():
                    os.rename(addons_dir / name, trash / name)
                    moved_out.append(name)
        except OSError as e:
            for name in reversed(moved_in):
                os.rename(addons_dir / name, stage / name)
            for name in reversed(moved_out):
                os.rename(trash / name, addons_dir / name)
            raise InstallError(f"install failed and was rolled back: {e}") from e
        return new
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(trash, ignore_errors=True)


def remove_folders(addons_dir: Path, folders: list[str]) -> list[str]:
    """Remove folders: move all of them aside first, then delete. Returns what was removed."""
    trash = _scratch(addons_dir, "trash")
    trash.mkdir(parents=True)
    moved = []
    try:
        for name in folders:
            if not name or "/" in name or name in (".", ".."):
                raise InstallError(f"refusing to remove {name!r}")
            src = addons_dir / name
            if src.exists() or src.is_symlink():
                os.rename(src, trash / name)
                moved.append(name)
    except OSError as e:
        for name in reversed(moved):
            os.rename(trash / name, addons_dir / name)
        shutil.rmtree(trash, ignore_errors=True)
        raise InstallError(f"uninstall failed and was rolled back: {e}") from e
    shutil.rmtree(trash, ignore_errors=True)
    return moved


def cleanup_scratch(addons_dir: Path) -> None:
    """Tidy up after a crash mid-install.

    A folder parked in trash whose replacement never arrived is put back.
    """
    for p in addons_dir.parent.glob(".omaforge-trash-*"):
        for child in p.iterdir():
            if not (addons_dir / child.name).exists():
                os.rename(child, addons_dir / child.name)
    for p in addons_dir.parent.glob(".omaforge-*"):
        shutil.rmtree(p, ignore_errors=True)
