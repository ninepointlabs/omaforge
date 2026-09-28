from pathlib import Path

import pytest

from omaforge.core import buildinfo, discovery, flavors
from omaforge.core.flavors import interface_number, parse_version


def test_build_info_parses_real_file(wow_root):
    builds = buildinfo.read_builds(wow_root)
    assert builds["wow"]["version"] == "12.1.0.69933"
    assert builds["wow_classic_beta"]["version"] == "1.60.1.70009"


def test_flavor_info_reads_product(wow_root):
    assert buildinfo.read_flavor(wow_root / "_retail_") == "wow"
    assert buildinfo.read_flavor(wow_root / "_classic_beta_") == "wow_classic_beta"
    assert buildinfo.read_flavor(wow_root / "missing") is None


@pytest.mark.parametrize(
    "product,version,game,channel,verified",
    [
        ("wow", "12.1.0.69933", "retail", "live", True),
        ("wowt", "12.1.5.70000", "retail", "ptr", True),
        ("wow_beta", "13.0.0.1", "retail", "beta", True),
        ("wow_classic_beta", "1.60.1.70009", "forever", "beta", True),
        ("wow_classic_era", "1.15.8.1", "classic_era", "live", True),
        ("wow_classic", "5.5.3.1", "mists", "live", True),
        ("wow_classic_ptr", "5.5.4.1", "mists", "ptr", True),
        ("wow_classic_beta", "5.5.4.1", "mists", "beta", True),
        ("wow_anniversary", "2.5.5.1", "tbc", "live", False),
        ("wow_forever", "1.61.0.1", "forever", "live", False),
        ("wow_something_new", "14.0.0.1", "retail", "live", False),
    ],
)
def test_rules(product, version, game, channel, verified):
    res = flavors.load(Path("/nonexistent")).resolve(product, parse_version(version))
    assert (res.game.id, res.channel, res.verified) == (game, channel, verified)


def test_forever_game_values():
    game = flavors.load(Path("/nonexistent")).games["forever"]
    assert game.toc_suffixes[0] == "Camelot"
    assert "forever" in game.release_flavors
    assert game.curseforge_version_type == 88568


def test_user_flavor_file_adds_branch_without_code(tmp_path):
    user = tmp_path / "flavors.toml"
    user.write_text(
        '[[game]]\nid = "plunder"\nlabel = "Plunderstorm"\ntoc_suffixes = ["Plunder"]\nrelease_flavors = ["plunder"]\n'
        '[[rule]]\nproducts = ["wow_plunder"]\ngame = "plunder"\n'
    )
    res = flavors.load(user).resolve("wow_plunder", parse_version("11.0.0"))
    assert res.game.label == "Plunderstorm"


def test_interface_number():
    assert interface_number((12, 1, 0, 69933)) == 120100
    assert interface_number((1, 60, 1)) == 16001
    assert interface_number((1, 15, 8)) == 11508


def test_discover_clients_in_root(wow_root):
    table = flavors.load(Path("/nonexistent"))
    clients = {c.folder: c for c in discovery.clients_in_root(wow_root, table)}
    assert clients["_retail_"].game.id == "retail"
    assert clients["_retail_"].interface == 120100
    assert clients["_classic_beta_"].label == "Forever Beta"
    assert clients["_classic_beta_"].key.startswith("classic_beta@")


def test_client_without_addons_dir_is_skipped(wow_root):
    (wow_root / "_ptr_").mkdir()
    table = flavors.load(Path("/nonexistent"))
    assert "_ptr_" not in {c.folder for c in discovery.clients_in_root(wow_root, table)}


def test_lutris_prefix_detection(tmp_path, wow_root):
    home = tmp_path / "home"
    games = home / ".local/share/lutris/games"
    games.mkdir(parents=True)
    prefix = wow_root.parents[2]
    (games / "battlenet.yml").write_text(f"game:\n  arch: win64\n  exe: x.exe\n  prefix: {prefix}\nname: Battle.net\n")
    roots = discovery.find_roots(home=home)
    assert roots == [wow_root.resolve()]


def test_steam_bottles_wine_detection(tmp_path, wow_root):
    import shutil

    home = tmp_path / "home"
    targets = [
        home / ".local/share/Steam/steamapps/compatdata/123/pfx",
        home / ".local/share/bottles/bottles/WoW",
        home / ".wine",
    ]
    for t in targets:
        shutil.copytree(wow_root.parents[2], t)
    roots = discovery.find_roots(home=home)
    assert len(roots) == 3


def test_manual_path_accepts_client_root_or_prefix(tmp_path, wow_root):
    home = tmp_path / "empty-home"
    home.mkdir()
    for given in (wow_root, wow_root / "_retail_", wow_root.parents[2]):
        assert discovery.find_roots([str(given)], autodetect=False, home=home) == [wow_root.resolve()]
    assert discovery.normalize_root(tmp_path / "nothing") is None
