import json

from conftest import make_addon

from omaforge import cli, config


def setup(wow_root):
    cfg = config.load()
    cfg["roots"] = {"paths": [str(wow_root)], "autodetect": False}
    for p in cfg["providers"].values():
        p["enabled"] = False
    config.save(cfg)


def test_clients_and_list_json(wow_root, capsys):
    setup(wow_root)
    make_addon(wow_root / "_retail_/Interface/AddOns", "Local", "## Title: Local\n## Version: 2\n")
    assert cli.main(["clients", "--json"]) == 0
    clients = json.loads(capsys.readouterr().out)
    assert {c["game"] for c in clients} == {"retail", "forever"}

    assert cli.main(["list", "-c", "retail", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert [(a["name"], a["version"], a["provider"]) for a in data["addons"]] == [("Local", "2", None)]


def test_clients_lists_unrun_forever_client(forever_root, capsys):
    setup(forever_root)
    assert cli.main(["clients"]) == 0
    out = capsys.readouterr().out
    row = next(line for line in out.splitlines() if line.startswith("forever@"))
    assert "Forever" in row and "not installed yet" in row and "wowf" in row
    assert cli.main(["clients", "--json"]) == 0
    forever = next(c for c in json.loads(capsys.readouterr().out) if c["folder"] == "_forever_")
    assert (forever["game"], forever["channel"], forever["version"], forever["preinstalled"]) == ("forever", "live", "", True)
    assert cli.main(["list", "-c", "forever"]) == 0
    assert capsys.readouterr().out.startswith("Forever (not installed yet) - 0 addons")
    assert not (forever_root / "_forever_/Interface").exists()


def test_pin_uninstall_and_update_all(wow_root, capsys):
    setup(wow_root)
    addons = wow_root / "_retail_/Interface/AddOns"
    make_addon(addons, "Local")
    make_addon(addons, "Local_Options", "## Dependencies: Local\n")
    assert cli.main(["pin", "Local", "-c", "retail"]) == 0
    assert cli.main(["update", "--all"]) == 0
    out = capsys.readouterr().out
    assert "Retail:" in out and "Forever Beta:" in out
    # Local is unknown (no provider), so it needs confirming; without a TTY that means --yes.
    assert cli.main(["uninstall", "Local", "-c", "retail"]) == 1
    assert "--yes" in capsys.readouterr().err and (addons / "Local").exists()
    assert cli.main(["uninstall", "Local", "-c", "retail", "--yes"]) == 0
    assert not (addons / "Local").exists() and not (addons / "Local_Options").exists()


def test_errors_exit_nonzero(wow_root, capsys):
    setup(wow_root)
    assert cli.main(["uninstall", "Nope", "-c", "retail"]) == 1
    assert "no installed addon" in capsys.readouterr().err
    assert cli.main(["install", "not-a-source", "-c", "retail"]) == 1


def test_export_import_files(wow_root, tmp_path, capsys):
    setup(wow_root)
    out = tmp_path / "list.json"
    assert cli.main(["export", str(out), "-c", "retail"]) == 0
    assert json.loads(out.read_text())["format"] == "omaforge.addons"
    assert cli.main(["import", str(out), "-c", "forever"]) == 0


def test_import_bad_file_is_a_clean_error(wow_root, tmp_path, capsys):
    setup(wow_root)
    assert cli.main(["import", str(tmp_path / "missing.json"), "-c", "retail"]) == 1
    assert "cannot read" in capsys.readouterr().err
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert cli.main(["import", str(bad), "-c", "retail"]) == 1
    err = capsys.readouterr().err
    assert "bad.json is not valid JSON" in err and "line 1" in err
    bad.write_text("[]")
    assert cli.main(["import", str(bad), "-c", "retail"]) == 1
    assert "not an omaforge addon list" in capsys.readouterr().err


def test_broken_config_is_a_clean_error(wow_root, capsys):
    config.config_path().parent.mkdir(parents=True, exist_ok=True)
    config.config_path().write_text("roots = nope\n")
    assert cli.main(["clients"]) == 1
    err = capsys.readouterr().err
    assert str(config.config_path()) in err and "line 1" in err
