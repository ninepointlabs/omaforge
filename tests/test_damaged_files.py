"""Damaged settings and state files, unknown-addon uninstalls, and the smaller QA fixes (2026-10-25 report)."""

import copy
import io

import pytest
from conftest import FakeHttp, make_addon

from omaforge import cli, config, paths
from omaforge.core import flavors, install
from omaforge.core.manager import Manager, ManagerError, same_version
from omaforge.core.providers.curseforge import clean_version
from omaforge.core.state import State


def setup(wow_root):
    cfg = config.load()
    cfg["roots"] = {"paths": [str(wow_root)], "autodetect": False}
    for p in cfg["providers"].values():
        p["enabled"] = False
    config.save(cfg)


def state_path():
    return paths.data_dir() / "state.json"


# M1: uninstall asks before removing addons omaforge doesn't know ------------
class Tty(io.StringIO):
    def isatty(self):
        return True


def test_uninstall_asks_on_a_terminal_for_a_self_made_addon(wow_root, capsys, monkeypatch):
    setup(wow_root)
    addons = wow_root / "_retail_/Interface/AddOns"
    make_addon(addons, "StoryTracker", "## Title: StoryTracker\n## Author: Tim\n## Version: 1\n")
    monkeypatch.setattr("sys.stdin", Tty())
    asked = []
    monkeypatch.setattr("builtins.input", lambda q: asked.append(q) or "n")
    assert cli.main(["uninstall", "StoryTracker", "-c", "retail"]) == 1
    assert "unknown to omaforge" in asked[0] and (addons / "StoryTracker").exists()
    assert "skipped StoryTracker" in capsys.readouterr().err

    monkeypatch.setattr("builtins.input", lambda q: "y")
    assert cli.main(["uninstall", "StoryTracker", "-c", "retail"]) == 0
    assert not (addons / "StoryTracker").exists()


def test_uninstall_with_stdin_closed_keeps_the_addon(wow_root, capsys, monkeypatch):
    setup(wow_root)
    addons = wow_root / "_retail_/Interface/AddOns"
    make_addon(addons, "QuestMusic")
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert cli.main(["uninstall", "QuestMusic", "-c", "retail"]) == 1
    assert (addons / "QuestMusic").exists() and "--yes" in capsys.readouterr().err


def test_uninstall_of_an_addon_omaforge_installed_does_not_ask(wow_root, capsys, monkeypatch):
    setup(wow_root)
    addons = wow_root / "_retail_/Interface/AddOns"
    make_addon(addons, "Managed")
    m = Manager()
    client = m.client("retail")
    with m.state.transaction() as s:
        s.set_record(client.key, "wowinterface:1", {"provider": "wowinterface", "id": "1", "name": "Managed",
                                                    "version": "1", "folders": ["Managed"]})
    monkeypatch.setattr("builtins.input", lambda q: pytest.fail("asked about a managed addon"))
    assert cli.main(["uninstall", "Managed", "-c", "retail"]) == 0
    assert not (addons / "Managed").exists()


# M2: damaged files are clean errors, and nothing is thrown away --------------
@pytest.mark.parametrize("content,problem", [
    ("{oops", "not valid JSON"),
    ("", "not valid JSON"),
    ("[1, 2]", "not a JSON object"),
    ('{"clients": 5}', "clients is not an object"),
    ('{"clients": {"retail@x": {"addons": []}}}', "addons of client 'retail@x'"),
])
def test_damaged_state_json_is_set_aside_and_kept(wow_root, capsys, content, problem):
    setup(wow_root)
    state_path().parent.mkdir(parents=True, exist_ok=True)
    state_path().write_text(content)
    assert cli.main(["list", "-c", "retail"]) == 0
    err = capsys.readouterr().err
    assert str(state_path()) in err and problem in err and "Traceback" not in err
    kept = list(state_path().parent.glob("state.json.damaged-*"))
    assert len(kept) == 1 and kept[0].read_text() == content and str(kept[0]) in err
    # The next run starts clean and says nothing more.
    assert cli.main(["pin", "Nope", "-c", "retail"]) == 1
    assert "damaged" not in capsys.readouterr().err
    assert len(list(state_path().parent.glob("state.json.damaged-*"))) == 1


def test_damaged_state_json_keeps_earlier_copies(tmp_path):
    path = tmp_path / "state.json"
    for text in ("{a", "{b"):
        path.write_text(text)
        st = State(path)
        assert st.recovered and st.data["clients"] == {}
    assert sorted(p.read_text() for p in tmp_path.glob("state.json.damaged-*")) == ["{a", "{b"]


def test_unreadable_state_json_bytes(tmp_path):
    path = tmp_path / "state.json"
    path.write_bytes(b"\xff\xfe\x00")
    st = State(path)
    assert "not UTF-8" in st.recovery_message() and not path.exists()


@pytest.mark.parametrize("content,problem", [
    ("[[rule]] products=", "line 1"),
    ('[[rule]]\nproducts = ["x"]\ngame = "nope"\n', "unknown game 'nope'"),
    ('[[rule]]\ngame = "retail"\n', "needs products"),
    ('[[rule]]\nproducts = "wow"\ngame = "retail"\n', "needs products"),
    ('[[rule]]\nproducts = ["x"]\ngame = "retail"\nversion = [">1x"]\n', "bad version comparison"),
    ('[[rule]]\nproducts = ["x"]\ngame = "retail"\nversion = ">1"\n', "bad version comparison"),
    ('rule = 5\n', "[[rule]] tables"),
    ('[[game]]\nlabel = "x"\n', "needs an id"),
    ('folders = 1\n', "folders must be a table"),
])
def test_broken_flavors_toml_is_a_clean_error(wow_root, capsys, content, problem):
    setup(wow_root)
    path = paths.config_dir() / "flavors.toml"
    path.write_text(content)
    assert cli.main(["clients"]) == 1
    err = capsys.readouterr().err
    assert err.startswith(f"omaforge: {path}: ") and problem in err and "Traceback" not in err
    assert path.read_text() == content


def test_valid_user_flavors_still_load(tmp_path):
    path = tmp_path / "flavors.toml"
    path.write_text('[[rule]]\nproducts = ["wowz"]\ngame = "retail"\nversion = [">=12"]\n')
    table = flavors.load(path)
    assert table.resolve("wowz", (12, 1, 0)).game.id == "retail"


@pytest.mark.parametrize("content,problem", [
    ("roots = [\n", "config.toml: "),
    ("roots = 5\n", "roots must be a table, not a number"),
    ('[roots]\npaths = "x"\n', "roots.paths must be a list, not a string"),
    ("[roots]\npaths = [1]\n", "roots.paths must be a list of strings"),
    ('[backups]\nkeep = "x"\n', "backups.keep must be a number"),
    ("[network]\noffline = 1\n", "network.offline must be true or false"),
    ('[providers]\ngithub = "x"\n', "providers.github must be a table"),
])
def test_broken_config_toml_is_a_clean_error(capsys, content, problem):
    config.config_path().parent.mkdir(parents=True, exist_ok=True)
    config.config_path().write_text(content)
    assert cli.main(["list"]) == 1
    err = capsys.readouterr().err
    assert str(config.config_path()) in err and problem in err and "Traceback" not in err
    assert config.config_path().read_text() == content


def test_unknown_config_keys_are_still_fine():
    config.config_path().parent.mkdir(parents=True, exist_ok=True)
    config.config_path().write_text('[providers.newthing]\nenabled = true\n[extra]\nx = 1\n')
    assert config.load()["providers"]["github"]["enabled"] is True


def test_save_never_overwrites_an_unreadable_config_without_a_copy():
    path = config.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('roots = [\n[providers.github]\ntoken = "secret"\n')
    with pytest.raises(config.ConfigError) as e:
        config.load()
    assert e.value.path == path
    config.save(copy.deepcopy(config.DEFAULTS))
    kept = list(path.parent.glob("config.toml.broken-*"))
    assert len(kept) == 1 and "secret" in kept[0].read_text()
    assert oct(kept[0].stat().st_mode & 0o777) == "0o600"
    assert config.load()["roots"]["paths"] == []


def test_roots_add_refuses_to_touch_a_broken_config(wow_root, capsys):
    path = config.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("roots = [\n")
    assert cli.main(["roots", "add", str(wow_root)]) == 1
    assert path.read_text() == "roots = [\n" and not list(path.parent.glob("config.toml.broken-*"))
    assert "Traceback" not in capsys.readouterr().err


# Low items -------------------------------------------------------------------
def test_roots_remove_of_an_unknown_path_fails(wow_root, capsys):
    setup(wow_root)
    assert cli.main(["roots", "remove", "/nope"]) == 1
    assert "/nope isn't in your roots" in capsys.readouterr().err
    assert cli.main(["roots", "remove", str(wow_root)]) == 0


def test_unknown_provider_for_explore_and_search(wow_root, capsys):
    setup(wow_root)
    assert cli.main(["explore", "-p", "nosuch", "-c", "retail"]) == 1
    assert "unknown or disabled provider 'nosuch'" in capsys.readouterr().err
    assert cli.main(["explore", "-p", "nosuch", "--categories", "-c", "retail"]) == 1
    assert "unknown or disabled provider 'nosuch'" in capsys.readouterr().err
    assert cli.main(["search", "x", "-p", "nosuch", "-c", "retail"]) == 1
    assert "unknown or disabled provider 'nosuch'" in capsys.readouterr().err


def test_empty_github_search_says_how_to_add_any_repo(wow_root, capsys, monkeypatch):
    setup(wow_root)
    cfg = config.load()
    cfg["providers"]["github"]["enabled"] = True
    config.save(cfg)
    from omaforge.core.providers.github import GitHub

    monkeypatch.setattr(GitHub, "search", lambda self, q, ctx, limit=30: [])
    assert cli.main(["search", "buggrabber", "-p", "gh", "-c", "retail"]) == 0
    assert "owner/repo" in capsys.readouterr().out


def test_missing_addon_id_names_the_source_not_the_url(wow_root, tmp_path):
    cfg = copy.deepcopy(config.DEFAULTS)
    cfg["roots"] = {"paths": [str(wow_root)], "autodetect": False}
    m = Manager(cfg=cfg, http=FakeHttp(), home=tmp_path / "home")
    with pytest.raises(ManagerError) as e:
        m.install(m.client("retail"), "wowinterface", "999999")
    assert str(e.value) == "no WoWInterface addon '999999'"


def test_unwritable_addons_folder_message(tmp_path, monkeypatch):
    from conftest import make_zip

    addons = tmp_path / "AddOns"
    addons.mkdir()
    z = tmp_path / "a.zip"
    z.write_bytes(make_zip({"A": {"x.lua": "1"}}))

    def denied(src, dst):
        raise PermissionError(13, "Permission denied", str(src))

    monkeypatch.setattr(install.os, "rename", denied)
    with pytest.raises(install.InstallError) as e:
        install.install_zip(z, addons)
    assert str(e.value).startswith(f"can't write to {addons} (Permission denied); nothing was changed")


def test_curseforge_file_names_as_versions():
    assert clean_version("1.0.1.zip") == "1.0.1" and clean_version("Plater-v656.zip") == "v656"
    assert same_version("0.7.14.zip", "0.7.14") and not same_version("0.7.14.zip", "1.0.1")


def test_wago_does_not_ask_for_a_key_yet():
    from omaforge.core.providers.stubs import Wago

    for key in ("", "k"):
        w = Wago(FakeHttp(), {"api_key": key})
        assert not w.available and "not supported yet" in w.unavailable_reason
        assert "api_key" not in w.unavailable_reason


def test_check_explains_question_marks(wow_root, capsys, monkeypatch):
    setup(wow_root)
    make_addon(wow_root / "_retail_/Interface/AddOns", "Odd")
    from omaforge.core import manager as managermod

    real = managermod.Manager.check_updates

    def check(self, client, addons):
        real(self, client, addons)
        for a in addons:
            a.update_error = "CurseForge: no file for this game"

    monkeypatch.setattr(managermod.Manager, "check_updates", check)
    assert cli.main(["check", "-c", "retail"]) == 0
    out = capsys.readouterr().out
    assert "? could not be checked:" in out and "Odd: CurseForge: no file for this game" in out
