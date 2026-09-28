import subprocess
import sys

from omaforge import buildkey
from omaforge.core.http import Http
from omaforge.core.providers import build

KEY = "$2a$10$example.key/for.tests.only.not.real.0123456789"


def test_roundtrip_and_obfuscated(tmp_path):
    pad, data = buildkey.encode(KEY)
    assert buildkey.decode(pad, data) == KEY
    path = buildkey.write(KEY, tmp_path / "_k.py")
    text = path.read_text()
    assert KEY not in text and "example" not in text


def test_builtin_key_used_only_without_user_key(monkeypatch):
    monkeypatch.setattr(buildkey, "builtin_curseforge_key", lambda: KEY)
    cf = build(Http(), {"providers": {"curseforge": {"api_key": ""}}})["curseforge"]
    assert cf.available and cf.config["builtin"]
    cf = build(Http(), {"providers": {"curseforge": {"api_key": "mine"}}})["curseforge"]
    assert cf.config["api_key"] == "mine" and "builtin" not in cf.config


def test_write_command_without_env_builds_keyless(monkeypatch, tmp_path):
    monkeypatch.setattr(buildkey, "TARGET", tmp_path / "_buildkey.py")
    monkeypatch.delenv(buildkey.ENV, raising=False)
    assert buildkey.main(["write"]) == 0
    assert not (tmp_path / "_buildkey.py").exists()


def test_repository_never_contains_generated_key():
    import pytest

    root = buildkey.TARGET.parent.parent
    if not (root / ".git").exists():
        pytest.skip("not a git checkout (e.g. building from a release tarball)")
    tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=buildkey.TARGET.parent.parent).stdout
    assert "omaforge/_buildkey.py" not in tracked.split()
