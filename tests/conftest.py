import io
import shutil
import zipfile
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def xdg(tmp_path, monkeypatch):
    """Keep every test away from the real ~/.config, ~/.local and ~/.cache."""
    for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(var, str(tmp_path / "xdg" / var.lower()))
    for var in ("OMAFORGE_GITHUB_TOKEN", "OMAFORGE_WAGO_API_KEY", "OMAFORGE_CURSEFORGE_API_KEY", "WINEPREFIX"):
        monkeypatch.delenv(var, raising=False)
    # Release builds embed a CurseForge key; tests must not see (or use) it.
    from omaforge import buildkey

    monkeypatch.setattr(buildkey, "builtin_curseforge_key", lambda: "")


@pytest.fixture
def wow_root(tmp_path) -> Path:
    """A WoW root built from the real .build.info / .flavor.info of the dev machine."""
    root = tmp_path / "prefix/drive_c/Program Files (x86)/World of Warcraft"
    shutil.copytree(FIXTURES / "wowroot", root)
    for client in ("_retail_", "_classic_beta_"):
        (root / client / "Interface/AddOns").mkdir(parents=True)
        (root / client / "WTF/Account").mkdir(parents=True)
        (root / client / "WTF/Config.wtf").write_text('SET locale "enUS"\n')
    return root


def make_addon(parent: Path, name: str, toc: str = "", files: dict[str, str] | None = None, suffix: str = "") -> Path:
    folder = parent / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}{suffix}.toc").write_text(toc or f"## Interface: 120100\n## Title: {name}\n## Version: 1.0\n")
    for rel, content in (files or {}).items():
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_text(content)
    return folder


def make_zip(folders: dict[str, dict[str, str]], prefix: str = "") -> bytes:
    """folders: {folder: {relative path: content}}; a TOC is added when missing."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for folder, files in folders.items():
            files = dict(files)
            if not any(p.endswith(".toc") for p in files):
                files[f"{folder}.toc"] = f"## Interface: 120100\n## Title: {folder}\n## Version: 1.0\n"
            for rel, content in files.items():
                zf.writestr(f"{prefix}{folder}/{rel}", content)
    return buf.getvalue()


class FakeHttp:
    """Serves canned JSON and zip bodies by URL."""

    def __init__(self, responses: dict | None = None, files: dict[str, bytes] | None = None):
        self.responses = responses or {}
        self.posts: dict = {}
        self.files = files or {}
        self.offline = False
        self.status = 404  # returned for unknown URLs
        self.requests: list[str] = []

    def get_json(self, url, headers=None, ttl=0):
        self.requests.append(url)
        if url not in self.responses:
            from omaforge.core.http import HttpError

            raise HttpError(f"{url}: HTTP {self.status}", self.status)
        return self.responses[url]

    def post_json(self, url, payload, headers=None, ttl=0):
        self.requests.append(url)
        value = self.posts[url]
        return value(payload) if callable(value) else value

    def download(self, url, dest, headers=None, max_bytes=0):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.files[url])
        return dest
