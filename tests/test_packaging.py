"""Every UI file must be covered by pyproject's package-data, or the installed app breaks."""

import fnmatch
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_ui_files_are_packaged():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]["package-data"]
    patterns = data["omaforge.ui"]
    ui = ROOT / "omaforge/ui"
    files = [p.relative_to(ui).as_posix() for p in ui.rglob("*")
             if p.is_file() and p.suffix != ".py" and "__pycache__" not in p.parts]
    missing = [f for f in files if not any(fnmatch.fnmatch(f, pat) for pat in patterns)]
    assert files and missing == []


def test_flavor_table_is_packaged():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]["package-data"]
    assert "flavors.toml" in data["omaforge.core"]
