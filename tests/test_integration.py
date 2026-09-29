import json
import re

import pytest

from omaforge import integration


def jsonc_to_json(text: str) -> dict:
    text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return json.loads(text)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(integration, "binding_conflict", lambda keys: None)
    monkeypatch.setattr(integration, "hyprland_errors", lambda: "")
    menu = integration.menu_path(tmp_path)
    menu.parent.mkdir(parents=True)
    menu.write_text('{\n  "hey-tui": {"label":"HEY","action":"hey"},\n  // a comment\n}\n')
    binds = integration.bindings_path(tmp_path)
    binds.parent.mkdir(parents=True)
    binds.write_text('o.bind("SUPER + N", "Other", "other")\n')
    return tmp_path


def test_menu_install_is_idempotent_and_removable(home):
    integration.install_menu(home)
    integration.install_menu(home)
    text = integration.menu_path(home).read_text()
    assert text.count("// >>> omaforge") == 1
    data = jsonc_to_json(text)
    assert data["omaforge"]["label"] == "WoW Addons" and "hey-tui" in data
    assert integration.remove_menu(home)
    assert "omaforge" not in integration.menu_path(home).read_text()
    assert jsonc_to_json(integration.menu_path(home).read_text()) == {"hey-tui": {"label": "HEY", "action": "hey"}}
    assert list(home.glob(".config/omarchy/extensions/*.bak.*"))


def test_menu_created_when_missing(tmp_path):
    integration.install_menu(tmp_path)
    assert "omaforge" in jsonc_to_json(integration.menu_path(tmp_path).read_text())


def test_binding_install_replace_remove(home):
    integration.install_binding(home, "super+shift+z")
    integration.install_binding(home, "SUPER + SHIFT + J")
    text = integration.bindings_path(home).read_text()
    assert text.count("o.bind(") == 2 and '"SUPER + SHIFT + J", "WoW addons"' in text
    assert text.startswith('o.bind("SUPER + N"')
    assert integration.remove_binding(home)
    assert integration.bindings_path(home).read_text() == 'o.bind("SUPER + N", "Other", "other")\n'


def test_binding_conflict_and_hyprland_rejection(home, monkeypatch):
    monkeypatch.setattr(integration, "binding_conflict", lambda keys: "Close window")
    with pytest.raises(integration.SetupError, match="Close window"):
        integration.install_binding(home, "SUPER + W")
    monkeypatch.setattr(integration, "binding_conflict", lambda keys: None)
    monkeypatch.setattr(integration, "hyprland_errors", lambda: "bindings.lua:3: boom")
    before = integration.bindings_path(home).read_text()
    with pytest.raises(integration.SetupError, match="reverted"):
        integration.install_binding(home, "SUPER + SHIFT + Z")
    assert integration.bindings_path(home).read_text() == before


def test_normalize_keys():
    assert integration.normalize_keys("super + shift+z") == "SUPER + SHIFT + Z"
    with pytest.raises(integration.SetupError):
        integration.normalize_keys("z")


def test_setup_refuses_without_omarchy(tmp_path, monkeypatch, capsys):
    from omaforge import cli

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(integration.shutil, "which", lambda name: None)
    assert cli.main(["setup", "omarchy"]) == 1
    assert "only applies to Omarchy" in capsys.readouterr().err
    assert not integration.menu_path(tmp_path).exists()
