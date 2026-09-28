from conftest import make_addon

from omaforge.core import scan, toc


def test_parse_fields_and_escapes():
    t = toc.parse(
        "﻿## Interface: 11508, 16001, 120100\n"
        "## Title: |cff33ff99Big|rWigs |TInterface\\Icon:0|t\n"
        "## Version: v426\n## X-Curse-Project-ID: 2382\n## X-WoWI-ID: 5086\n"
        "## Dependencies: BigWigs_Core, LibStub\n## RequiredDeps: Foo\n## OptionalDeps: Bar\n",
        folder="BigWigs",
    )
    assert t.title == "BigWigs"
    assert t.interfaces == [11508, 16001, 120100]
    assert t.provider_ids == {"curseforge": "2382", "wowinterface": "5086"}
    assert t.dependencies == ["BigWigs_Core", "LibStub", "Foo"]


def test_unexpanded_packager_tokens_are_ignored():
    t = toc.parse("## Version: @project-version@\n## X-Curse-Project-ID: @curse-id@\n")
    assert t.version == ""
    assert t.provider_ids == {}


def test_select_toc_by_flavor(tmp_path):
    folder = make_addon(tmp_path, "Addon")
    (folder / "Addon_Mainline.toc").write_text("## Interface: 120100\n## Title: Retail\n")
    (folder / "Addon-Camelot.toc").write_text("## Interface: 16001\n## Title: Forever\n")
    (folder / "Addon_Vanilla.toc").write_text("## Interface: 11508\n## Title: Era\n")
    assert toc.read(folder, ("Mainline", "Standard")).title == "Retail"
    assert toc.read(folder, ("Camelot", "Classic")).title == "Forever"
    assert toc.read(folder, ("Vanilla", "Classic")).title == "Era"
    assert toc.read(folder, ("Mists", "Classic")).title == "Addon"  # plain TOC


def test_folder_not_loadable_for_flavor_is_still_listed(tmp_path):
    folder = tmp_path / "RetailOnly"
    folder.mkdir()
    (folder / "RetailOnly_Mainline.toc").write_text("## Title: Retail only\n")
    folders = scan.read_folders(tmp_path, ("Camelot", "Classic"))
    assert folders["RetailOnly"].loadable is False
    assert folders["RetailOnly"].title == "Retail only"


def test_non_addon_folders_and_scratch_are_skipped(tmp_path):
    (tmp_path / "NoToc").mkdir()
    (tmp_path / ".omaforge-stage-x").mkdir()
    make_addon(tmp_path, "Real")
    assert list(scan.read_folders(tmp_path, ())) == ["Real"]


def _dbm_like(tmp_path):
    make_addon(tmp_path, "DBM-Core", "## Title: DBM\n## Version: 12.1.11\n")
    make_addon(tmp_path, "DBM-GUI", "## Title: DBM GUI\n## Dependencies: DBM-Core\n## LoadOnDemand: 1\n")
    make_addon(tmp_path, "DBM-Raids-Midnight", "## Dependencies: DBM-Core\n## LoadOnDemand: 1\n")
    make_addon(tmp_path, "DBM-StatusBarTimers", "## Dependencies: DBM-Core\n")
    make_addon(tmp_path, "BigWigs", "## Title: BigWigs\n## X-Curse-Project-ID: 2382\n")
    make_addon(tmp_path, "BigWigs_Core", "## Dependencies: BigWigs\n")
    make_addon(tmp_path, "BigWigs_Plugins", "## X-Curse-Project-ID: 2382\n")
    make_addon(tmp_path, "LittleWigs", "## Dependencies: BigWigs_Core\n")
    make_addon(tmp_path, "LibStub")
    make_addon(tmp_path, "WeakAuras", "## Title: WeakAuras\n")
    make_addon(tmp_path, "WeakAurasOptions", "## Dependencies: WeakAuras\n")
    return scan.read_folders(tmp_path, ())


def test_grouping_multi_folder_addons(tmp_path):
    folders = _dbm_like(tmp_path)
    groups = sorted(scan.group_folders(folders, {}))
    assert ["DBM-Core", "DBM-GUI", "DBM-Raids-Midnight", "DBM-StatusBarTimers"] in groups
    assert ["BigWigs", "BigWigs_Core", "BigWigs_Plugins"] in groups
    assert ["LittleWigs"] in groups  # depends on BigWigs but is a different addon
    assert ["LibStub"] in groups
    assert ["WeakAuras", "WeakAurasOptions"] in groups


def test_recorded_ownership_wins_over_heuristics(tmp_path):
    folders = _dbm_like(tmp_path)
    groups = scan.group_folders(folders, {"github:dbm": ["DBM-Core", "DBM-GUI"], "gone:x": ["Missing"]})
    assert ["DBM-Core", "DBM-GUI"] in groups
    # Folders outside the record are separate addons, even if they depend on it.
    assert ["DBM-Raids-Midnight"] in groups and ["DBM-StatusBarTimers"] in groups


def test_main_folder(tmp_path):
    folders = _dbm_like(tmp_path)
    group = ["DBM-Core", "DBM-GUI", "DBM-Raids-Midnight", "DBM-StatusBarTimers"]
    assert scan.main_folder(group, folders) == "DBM-Core"
    assert scan.main_folder(["BigWigs", "BigWigs_Core", "BigWigs_Plugins"], folders) == "BigWigs"
