import io
import os
import stat
import zipfile

import pytest
from conftest import make_addon, make_zip

from omaforge.core import backup, install


def _write(tmp_path, data: bytes):
    p = tmp_path / "addon.zip"
    p.write_bytes(data)
    return p


def test_install_replaces_and_removes_stale_folders(tmp_path):
    addons = tmp_path / "Interface/AddOns"
    make_addon(addons, "Foo", files={"old.lua": "old"})
    make_addon(addons, "Foo_Legacy")
    make_addon(addons, "Other")
    z = _write(tmp_path, make_zip({"Foo": {"new.lua": "new"}, "Foo_Options": {}}))
    new = install.install_zip(z, addons, previous=["Foo", "Foo_Legacy"])
    assert new == ["Foo", "Foo_Options"]
    assert (addons / "Foo/new.lua").exists() and not (addons / "Foo/old.lua").exists()
    assert not (addons / "Foo_Legacy").exists()
    assert (addons / "Other").exists()
    assert not list((tmp_path / "Interface").glob(".omaforge-*"))


def test_install_refuses_folders_owned_by_another_addon(tmp_path):
    addons = tmp_path / "Interface/AddOns"
    make_addon(addons, "LibShared", files={"keep.lua": "x"})
    z = _write(tmp_path, make_zip({"Foo": {}, "LibShared": {}}))
    with pytest.raises(install.ConflictError):
        install.install_zip(z, addons, owners={"LibShared": "wowinterface:1"})
    assert (addons / "LibShared/keep.lua").exists()
    assert not (addons / "Foo").exists()
    install.install_zip(z, addons, owners={"LibShared": "wowinterface:1"}, force=True)
    assert not (addons / "LibShared/keep.lua").exists()


@pytest.mark.parametrize("bad", ["../evil/x.toc", "/abs/x.toc", "C:/x/x.toc"])
def test_unsafe_archives_are_rejected(tmp_path, bad):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(bad, "x")
    with pytest.raises(install.InstallError):
        install.install_zip(_write(tmp_path, buf.getvalue()), tmp_path / "Interface/AddOns")


def test_symlinks_are_rejected(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("Foo/link")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "/etc/passwd")
    with pytest.raises(install.InstallError, match="symlink"):
        install.install_zip(_write(tmp_path, buf.getvalue()), tmp_path / "Interface/AddOns")


def test_archive_without_addons_is_rejected(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("README.md", "hi")
    with pytest.raises(install.InstallError, match="no addon folders"):
        install.install_zip(_write(tmp_path, buf.getvalue()), tmp_path / "Interface/AddOns")


def test_wrapped_archive_is_unwrapped(tmp_path):
    addons = tmp_path / "Interface/AddOns"
    z = _write(tmp_path, make_zip({"Foo": {}}, prefix="Foo-1.0/"))
    assert install.install_zip(z, addons) == ["Foo"]
    assert (addons / "Foo/Foo.toc").exists()


def test_failed_swap_rolls_back(tmp_path, monkeypatch):
    addons = tmp_path / "Interface/AddOns"
    make_addon(addons, "A", files={"v1": "1"})
    make_addon(addons, "B", files={"v1": "1"})
    z = _write(tmp_path, make_zip({"A": {"v2": "2"}, "B": {"v2": "2"}}))
    real_rename = os.rename
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 4:  # A out, A in, B out, then fail moving B in
            raise OSError("disk on fire")
        return real_rename(src, dst)

    monkeypatch.setattr(install.os, "rename", flaky)
    with pytest.raises(install.InstallError, match="rolled back"):
        install.install_zip(z, addons)
    monkeypatch.setattr(install.os, "rename", real_rename)
    assert (addons / "A/v1").exists() and (addons / "B/v1").exists()
    assert not (addons / "A/v2").exists()


def test_cleanup_restores_orphaned_folders(tmp_path):
    addons = tmp_path / "Interface/AddOns"
    addons.mkdir(parents=True)
    trash = tmp_path / "Interface/.omaforge-trash-abc"
    make_addon(trash, "Parked")
    make_addon(trash, "Replaced")
    make_addon(addons, "Replaced", files={"new": "1"})
    install.cleanup_scratch(addons)
    assert (addons / "Parked").exists()
    assert (addons / "Replaced/new").exists()
    assert not trash.exists()


def test_remove_folders(tmp_path):
    addons = tmp_path / "AddOns"
    make_addon(addons, "A")
    make_addon(addons, "A_Options")
    assert install.remove_folders(addons, ["A", "A_Options", "Gone"]) == ["A", "A_Options"]
    assert list(addons.iterdir()) == []
    with pytest.raises(install.InstallError):
        install.remove_folders(addons, ["../x"])


def test_backup_and_restore(tmp_path):
    wtf = tmp_path / "WTF"
    (wtf / "Account/SavedVariables").mkdir(parents=True)
    (wtf / "Account/SavedVariables/Foo.lua").write_text("Foo = 1")
    b = backup.create(wtf, "retail@x", "before-update", keep=5)
    assert b and b.path.exists() and b.reason == "before-update"
    (wtf / "Account/SavedVariables/Foo.lua").write_text("Foo = 2")
    safety = backup.restore(b, wtf, "retail@x", keep=5)
    assert (wtf / "Account/SavedVariables/Foo.lua").read_text() == "Foo = 1"
    assert safety.reason == "before-restore"
    assert len(backup.list_backups("retail@x")) == 2
    assert not list(tmp_path.glob(".omaforge-*"))


def test_backup_pruning(tmp_path):
    wtf = tmp_path / "WTF"
    wtf.mkdir()
    for _ in range(4):
        backup.create(wtf, "k", keep=2)
    assert len(backup.list_backups("k")) == 2


def test_backup_without_wtf(tmp_path):
    assert backup.create(tmp_path / "missing", "k") is None
