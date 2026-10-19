"""Running away from Omarchy (the AppImage on another distro): CA certificates and the theme."""

import ssl

import pytest

from omaforge import paths
from omaforge.core import http


class FakeContext:
    def __init__(self, cas: int):
        self.cas = cas
        self.loaded = []

    def cert_store_stats(self):
        return {"x509_ca": self.cas}

    def load_verify_locations(self, cafile=None):
        self.loaded.append(cafile)


@pytest.fixture
def fresh_context(monkeypatch):
    monkeypatch.setattr(http, "_context", None)


def test_ssl_context_keeps_python_defaults_when_they_have_certificates(fresh_context, monkeypatch):
    context = FakeContext(cas=140)
    monkeypatch.setattr(ssl, "create_default_context", lambda: context)
    assert http.ssl_context() is context
    assert context.loaded == []
    assert http.ssl_context() is context  # made once


def test_ssl_context_loads_the_distributions_bundle_when_python_found_none(fresh_context, monkeypatch, tmp_path):
    context = FakeContext(cas=0)
    bundle = tmp_path / "ca-certificates.crt"
    bundle.write_text("certs")
    monkeypatch.setattr(ssl, "create_default_context", lambda: context)
    monkeypatch.setattr(http, "CA_FILES", (str(tmp_path / "missing.pem"), str(bundle)))
    http.ssl_context()
    assert context.loaded == [str(bundle)]


def test_theme_dir_uses_the_old_config_path_only_when_the_state_one_is_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    state = tmp_path / "state/omarchy/current/theme"
    legacy = tmp_path / "config/omarchy/current/theme"
    assert paths.omarchy_theme_dir() == state  # neither: nothing to read or watch
    legacy.mkdir(parents=True)
    assert paths.omarchy_theme_dir() == legacy
    state.parent.mkdir(parents=True)
    assert paths.omarchy_theme_dir() == state


def test_theme_without_omarchy_follows_the_desktops_light_or_dark(monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QGuiApplication

    from omaforge.ui import theme as theme_mod

    QGuiApplication.instance() or QGuiApplication(["omaforge-test"])
    monkeypatch.setattr(theme_mod, "system_prefers_light", lambda: True)
    light = theme_mod.Theme()
    assert light.dark is False
    assert light.background == theme_mod.LIGHT_DEFAULTS["background"]
    monkeypatch.setattr(theme_mod, "system_prefers_light", lambda: False)
    dark = theme_mod.Theme()
    assert dark.dark is True
    assert dark.background == theme_mod.DEFAULTS["background"]
