"""Starring addons, installed or not: what is kept, and the Starred page."""

import copy
import json

import pytest
from conftest import FakeHttp, make_addon

from omaforge import config, paths
from omaforge.core import state as statemod
from omaforge.core.manager import Manager, ManagerError
from omaforge.core.state import State

CLIQUE = {"provider": "wowinterface", "id": "5108", "name": "Clique", "author": "Cladhaire", "summary": "Click casting",
          "url": "https://wowi/5108", "icon": "", "downloads": 10, "favorites": 2, "categories": ["Combat"],
          "external_only": False, "version": "5.0", "updated": 1700000000, "compatible": False, "rank": 3, "folders": ["Clique"]}


def manager(wow_root, tmp_path, http=None, enabled=("wowinterface",)):
    cfg = copy.deepcopy(config.DEFAULTS)
    cfg["roots"] = {"paths": [str(wow_root)], "autodetect": False}
    for name, p in cfg["providers"].items():
        p["enabled"] = name in enabled
    return Manager(cfg=cfg, http=http or FakeHttp(), home=tmp_path / "home")


def state_file():
    return paths.data_dir() / "state.json"


def names(stars):
    return [s["name"] for s in stars]


# What is kept ----------------------------------------------------------------
def test_a_star_on_an_addon_that_is_not_installed_survives_a_restart(wow_root, tmp_path):
    m = manager(wow_root, tmp_path)
    assert m.stars() == []
    m.set_starred(CLIQUE, True)

    on_disk = json.loads(state_file().read_text())
    assert list(on_disk["starred"]) == ["wowinterface:5108"]
    assert on_disk["clients"] == {}  # nothing is tied to a client or an install

    star = manager(wow_root, tmp_path).stars()[0]
    assert (star["provider"], star["id"], star["name"], star["author"]) == ("wowinterface", "5108", "Clique", "Cladhaire")
    assert star["url"] == "https://wowi/5108" and star["categories"] == ["Combat"]


def test_what_only_holds_for_one_game_version_is_not_kept(wow_root, tmp_path):
    m = manager(wow_root, tmp_path)
    m.set_starred(CLIQUE, True)
    kept = json.loads(state_file().read_text())["starred"]["wowinterface:5108"]
    assert not {"version", "updated", "compatible", "rank", "folders", "provider", "id"} & set(kept)
    star = m.stars()[0]
    assert star["compatible"] is True and star["version"] == "" and star["updated"] == 0


def test_stars_are_written_atomically_through_the_state_lock(wow_root, tmp_path, monkeypatch):
    m = manager(wow_root, tmp_path)
    m.set_starred(CLIQUE, True)
    before = state_file().read_text()

    def fail(path, obj):
        raise OSError("disk full")

    monkeypatch.setattr(statemod, "atomic_write_json", fail)
    with pytest.raises(OSError):
        m.set_starred({**CLIQUE, "id": "1", "name": "Other"}, True)
    assert state_file().read_text() == before


def test_a_star_made_elsewhere_is_not_overwritten(wow_root, tmp_path):
    first, second = manager(wow_root, tmp_path), manager(wow_root, tmp_path)
    first.set_starred(CLIQUE, True)
    second.set_starred({**CLIQUE, "id": "1", "name": "Other"}, True)  # second loaded before first wrote
    assert sorted(names(first.stars())) == ["Clique", "Other"]


def test_newest_first_and_unstar(wow_root, tmp_path, monkeypatch):
    m = manager(wow_root, tmp_path)
    for at, (addon_id, name) in enumerate([("1", "Old"), ("2", "New")]):
        monkeypatch.setattr("omaforge.core.manager.time.time", lambda at=at: 100 + at)
        m.set_starred({**CLIQUE, "id": addon_id, "name": name}, True)
    assert names(m.stars()) == ["New", "Old"]
    m.set_starred({**CLIQUE, "id": "2"}, False)
    assert names(m.stars()) == ["Old"]
    m.set_starred({**CLIQUE, "id": "2"}, False)  # already off
    assert names(m.stars()) == ["Old"]


def test_the_key_is_the_source_and_id_not_the_folder_so_it_outlives_the_install(wow_root, tmp_path):
    addons = wow_root / "_retail_/Interface/AddOns"
    make_addon(addons, "Managed")
    m = manager(wow_root, tmp_path)
    client = m.client("retail")
    with m.state.transaction() as s:
        s.set_record(client.key, "wowinterface:7", {"provider": "wowinterface", "id": "7", "name": "Managed",
                                                    "version": "1", "folders": ["Managed"]})
    installed = next(a for a in m.installed(client) if a.key == "wowinterface:7")
    m.set_starred(installed.to_dict(), True)
    assert m.stars()[0]["id"] == "7" and m.stars()[0]["name"] == "Managed"

    m.uninstall(client, "wowinterface:7")
    assert not (addons / "Managed").exists()
    assert names(manager(wow_root, tmp_path).stars()) == ["Managed"]


def test_unstarring_an_installed_addon_clears_the_sources_its_toc_links_to(wow_root, tmp_path):
    m = manager(wow_root, tmp_path)
    m.set_starred({"provider": "curseforge", "id": "99", "name": "Clique"}, True)
    m.set_starred({"provider": "wowinterface", "source_id": "5108", "name": "Clique", "links": {"curseforge": "99"}}, False)
    assert m.stars() == []


def test_an_addon_with_no_known_source_can_not_be_starred(wow_root, tmp_path):
    m = manager(wow_root, tmp_path)
    with pytest.raises(ManagerError, match="no known source"):
        m.set_starred({"key": "local:Mine", "name": "Mine", "provider": None, "source_id": None}, True)
    assert not state_file().exists()


# Files from older versions, and damaged ones --------------------------------
def test_a_state_file_from_before_stars_loads_and_keeps_everything(wow_root, tmp_path):
    state_file().parent.mkdir(parents=True, exist_ok=True)
    older = {"schema": 1, "clients": {"retail@x": {"addons": {}, "prefs": {"a:1": {"pinned": True}}}}}
    state_file().write_text(json.dumps(older))
    m = manager(wow_root, tmp_path)
    assert m.stars() == []
    m.set_starred(CLIQUE, True)
    after = json.loads(state_file().read_text())
    assert after["clients"] == older["clients"] and "wowinterface:5108" in after["starred"]


@pytest.mark.parametrize("starred", ["[]", "5", '{"wowinterface:1": []}'])
def test_starred_of_the_wrong_shape_is_set_aside_like_other_damage(starred):
    state_file().parent.mkdir(parents=True, exist_ok=True)
    content = '{"clients": {}, "starred": %s}' % starred
    state_file().write_text(content)
    st = State()
    assert st.recovered and "starred" in st.recovered[1] and "stars" in st.recovery_message()
    assert st.recovered[0].read_text() == content and st.stars() == {}


def test_a_hand_edited_star_shows_what_it_can(wow_root, tmp_path):
    state_file().parent.mkdir(parents=True, exist_ok=True)
    state_file().write_text(json.dumps({"clients": {}, "starred": {
        "no-colon": {"name": "Skipped"},
        "wowinterface:1": {"name": 5, "categories": "nope", "downloads": "many", "starred_at": "soon"},
    }}))
    stars = manager(wow_root, tmp_path).stars()
    assert len(stars) == 1
    s = stars[0]
    assert (s["name"], s["categories"], s["downloads"], s["starred_at"]) == ("1", [], 0, 0)
