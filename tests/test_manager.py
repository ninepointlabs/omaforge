import copy
import json

import pytest
from conftest import FakeHttp, make_addon, make_zip

from omaforge import config
from omaforge.core.manager import Manager, ManagerError, same_version

GH = "https://api.github.com"


def github_release(tag, folders, flavors=("mainline", "forever")):
    zip_name = f"Foo-{tag}.zip"
    return (
        {"tag_name": tag, "prerelease": False, "published_at": "2026-09-27T15:15:08Z",
         "assets": [{"name": zip_name, "browser_download_url": f"https://dl/{tag}/{zip_name}"},
                    {"name": "release.json", "browser_download_url": f"https://dl/{tag}/release.json"}]},
        {f"https://dl/{tag}/release.json": {"releases": [{"filename": zip_name, "nolib": False,
                                                           "metadata": [{"flavor": f} for f in flavors]}]}},
        {f"https://dl/{tag}/{zip_name}": make_zip({f: {"v.lua": tag} for f in folders})},
    )


class World:
    def __init__(self, wow_root, tmp_path):
        self.http = FakeHttp()
        self.releases = []
        cfg = copy.deepcopy(config.DEFAULTS)
        cfg["roots"] = {"paths": [str(wow_root)], "autodetect": False}
        self.m = Manager(cfg=cfg, http=self.http, home=tmp_path / "home")
        self.retail = self.m.client("retail")
        self.addons = self.retail.addons_dir

    def publish(self, tag, folders, flavors=("mainline", "forever")):
        rel, js, files = github_release(tag, folders, flavors)
        self.releases.insert(0, rel)
        self.http.responses[f"{GH}/repos/o/Foo/releases?per_page=15"] = self.releases
        self.http.responses.update(js)
        self.http.files.update(files)


@pytest.fixture
def world(wow_root, tmp_path):
    return World(wow_root, tmp_path)


def test_same_version():
    assert same_version("v426", "426") and same_version("V1.2", "v1.2") and not same_version("1.2", "1.3")
    assert same_version("version", "version")


def test_client_selection(world):
    assert world.m.client("forever").folder == "_classic_beta_"
    assert world.m.client("classic_beta").folder == "_classic_beta_"
    assert world.m.client(None).folder == "_retail_"
    with pytest.raises(ManagerError):
        world.m.client("mists")


def test_install_update_pin_uninstall(world):
    world.publish("v1", ["Foo", "Foo_Options"])
    rec = world.m.install(world.retail, "github", "o/Foo")
    assert rec["folders"] == ["Foo", "Foo_Options"] and rec["version"] == "v1"

    [a] = world.m.installed(world.retail)
    assert (a.key, a.managed, a.match, a.folders) == ("github:o/Foo", True, "state", ["Foo", "Foo_Options"])
    assert a.name == "Foo"  # the TOC title, not the repo name

    world.publish("v2", ["Foo"])
    [a] = world.m.check_updates(world.retail)
    assert a.update_available and a.latest.version == "v2"

    world.m.set_pref(world.retail, a.key, pinned=True)
    res = world.m.update(world.retail)
    assert res.results == [] and res.backup is None  # pinned addons are not bulk-updated

    world.m.set_pref(world.retail, a.key, pinned=False)
    res = world.m.update(world.retail)
    assert [r.new for r in res.results] == ["v2"]
    assert res.backup and res.backup["reason"] == "before-update"
    assert not (world.addons / "Foo_Options").exists()
    assert (world.addons / "Foo/v.lua").read_text() == "v2"

    assert world.m.uninstall(world.retail, "github:o/Foo") == ["Foo"]
    assert world.m.installed(world.retail) == []


def test_named_update_of_pinned_addon_is_skipped(world):
    world.publish("v1", ["Foo"])
    world.m.install(world.retail, "github", "o/Foo")
    world.publish("v2", ["Foo"])
    world.m.set_pref(world.retail, "github:o/Foo", pinned=True)
    [r] = world.m.update(world.retail, ["github:o/Foo"]).results
    assert r.skipped == "pinned"


def test_unknown_and_header_linked_addons(world):
    make_addon(world.addons, "Local", "## Title: My Local\n## Version: 3\n")
    make_addon(world.addons, "CurseOnly", "## Title: Curse Only\n## X-Curse-Project-ID: 42\n")
    addons = {a.name: a for a in world.m.check_updates(world.retail)}
    assert addons["My Local"].key == "local:Local" and addons["My Local"].provider is None
    assert addons["Curse Only"].key == "curseforge:42" and addons["Curse Only"].match == "toc"
    assert "API key" in addons["Curse Only"].update_error


def test_adopting_an_unmanaged_copy(world):
    make_addon(world.addons, "Foo", "## Title: Foo\n## Version: v0\n## X-Website: https://github.com/o/Foo\n")
    make_addon(world.addons, "Foo_Old", "## Dependencies: Foo\n")
    world.publish("v1", ["Foo"])
    [a] = world.m.check_updates(world.retail)
    assert (a.key, a.match, a.folders, a.update_available) == ("github:o/Foo", "website", ["Foo", "Foo_Old"], True)
    world.m.update(world.retail)
    [a] = world.m.installed(world.retail)
    assert a.managed and a.folders == ["Foo"]
    assert not (world.addons / "Foo_Old").exists()


def test_install_conflict_with_other_managed_addon(world):
    world.publish("v1", ["Foo", "LibShared"])
    world.m.install(world.retail, "github", "o/Foo")
    rel, js, files = github_release("b1", ["Bar", "LibShared"])
    rel["assets"][0]["browser_download_url"] = "https://dl/b1/Foo-b1.zip"
    world.http.responses[f"{GH}/repos/o/Bar/releases?per_page=15"] = [rel]
    world.http.responses.update(js)
    world.http.files.update(files)
    with pytest.raises(Exception, match="another addon"):
        world.m.install(world.retail, "github", "o/Bar")
    world.m.install(world.retail, "github", "o/Bar", force=True)
    records = world.m.state.addons(world.retail.key)
    assert records["github:o/Foo"]["folders"] == ["Foo"]
    assert records["github:o/Bar"]["folders"] == ["Bar", "LibShared"]


def test_forever_gets_the_forever_build(world):
    world.publish("v1", ["Foo"], flavors=("mainline",))
    forever = world.m.client("forever")
    with pytest.raises(ManagerError, match="no stable release for Forever Beta"):
        world.m.install(forever, "github", "o/Foo")
    world.publish("v2", ["Foo"], flavors=("mainline", "forever"))
    assert world.m.install(forever, "github", "o/Foo")["version"] == "v2"


def test_export_import_roundtrip(world, wow_root):
    world.publish("v1", ["Foo"])
    world.m.install(world.retail, "github", "o/Foo", channel="beta")
    world.m.set_pref(world.retail, "github:o/Foo", pinned=True)
    make_addon(world.addons, "Local")
    data = json.loads(json.dumps(world.m.export(world.retail)))
    assert data["addons"] == [{"provider": "github", "id": "o/Foo", "name": "Foo", "version": "v1",
                               "channel": "beta", "pinned": True, "ignored": False}]
    assert data["unknown"] == [{"name": "Local", "folders": ["Local"]}]

    forever = world.m.client("forever")
    results = world.m.import_list(forever, data)
    assert [(r.ok, r.new) for r in results] == [(True, "v1")]
    [a] = world.m.installed(forever)
    assert (a.pinned, a.channel) == (True, "beta")
    assert world.m.import_list(forever, data)[0].skipped == "already installed"
    with pytest.raises(ManagerError):
        world.m.import_list(forever, {"format": "other"})


def test_backup_restore_via_manager(world):
    sv = world.retail.wtf_dir / "Account/SV.lua"
    sv.write_text("1")
    b = world.m.backup(world.retail)
    sv.write_text("2")
    world.m.restore(world.retail, b.id)
    assert sv.read_text() == "1"


def test_roots_add_persists(tmp_path, wow_root):
    cfg = copy.deepcopy(config.DEFAULTS)
    cfg["roots"]["autodetect"] = False
    m = Manager(cfg=cfg, http=FakeHttp(), home=tmp_path / "home")
    assert m.clients() == []
    m.roots_add(str(wow_root / "_retail_"))
    assert len(m.clients()) == 2
    assert config.load()["roots"]["paths"] == [str(wow_root.resolve())]
    with pytest.raises(ManagerError):
        m.roots_add(str(tmp_path))


def test_blocked_curseforge_addon_installs_from_github(world, monkeypatch):
    from omaforge.core.providers.base import DistributionDisabled
    from omaforge.core.providers.curseforge import CurseForge

    world.publish("v1", ["Foo"])
    cf = CurseForge(world.http, {"api_key": "k"})
    monkeypatch.setattr(cf, "resolve", lambda *a, **k: (_ for _ in ()).throw(DistributionDisabled("blocked")))
    monkeypatch.setattr(cf, "alternates", lambda addon_id, ctx: ("o/Foo", ["Foo"]))
    world.m.providers["curseforge"] = cf
    rec = world.m.install(world.retail, "curseforge", "3358")
    assert (rec["provider"], rec["id"]) == ("github", "o/Foo") and "disabled" in rec["via"]

    monkeypatch.setattr(cf, "alternates", lambda addon_id, ctx: (None, ["Nothing"]))
    with pytest.raises(ManagerError, match="curseforge.com"):
        world.m.install(world.retail, "curseforge", "3358")


def test_explore_requires_ranking_provider(world):
    with pytest.raises(ManagerError):
        world.m.explore(world.retail, "github")
    assert [s["name"] for s in world.m.explore_sources()] == ["wowinterface"]


def test_display_name():
    from omaforge.core.manager import display_name

    assert display_name("WeakAuras", "WeakAuras/WeakAuras2") == "WeakAuras"
    assert display_name("<DBM Core> Main Core", "DeadlyBossMods/DeadlyBossMods") == "Deadly Boss Mods"
    assert display_name("", "o/some-addon_name") == "some addon name"
