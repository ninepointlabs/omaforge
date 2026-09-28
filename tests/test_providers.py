from pathlib import Path

import pytest
from conftest import FakeHttp, make_addon

from omaforge.core import flavors, scan
from omaforge.core.providers import GameContext, ProviderError, ProviderUnavailable
from omaforge.core.providers import curseforge as cfmod
from omaforge.core.providers import fingerprint
from omaforge.core.providers.curseforge import CurseForge
from omaforge.core.providers.github import GitHub, parse_repo, release_channel
from omaforge.core.providers.stubs import Wago
from omaforge.core.providers.wowinterface import API as WOWI, WoWInterface

TABLE = flavors.load(Path("/nonexistent"))


def ctx(game="retail", version=(12, 1, 0), addons_dir=None):
    return GameContext(TABLE.games[game], version, flavors.interface_number(version), addons_dir)


# --- WoWInterface ----------------------------------------------------------

FILELIST = [
    {"UID": "5086", "UIName": "BigWigs", "UIAuthorName": "funkydude", "UIVersion": "v426", "UIDownloadTotal": "100",
     "UICompatibility": [{"version": "12.1.0"}, {"version": "1.60.1"}], "UIDir": ["BigWigs", "BigWigs_Core"]},
    {"UID": "11190", "UIName": "Bartender4", "UIVersion": "4.18.0", "UIDownloadTotal": "500",
     "UICompatibility": [{"version": "11.2.0"}], "UIDir": ["Bartender4"]},
    {"UID": "99", "UIName": "Classic Thing", "UIVersion": "1", "UIDownloadTotal": "5",
     "UICompatibility": [{"version": "1.15.8"}], "UIDir": ["ClassicThing"]},
    {"UID": "7", "UIName": "Ace3", "UIVersion": "1", "UIDownloadTotal": "900",
     "UICompatibility": None, "UIDir": ["Ace3", "AceAddon-3.0", "LibStub"]},
    {"UID": "8", "UIName": "LibStub", "UIVersion": "1", "UIDownloadTotal": "10", "UIDir": ["LibStub"]},
]


def wowi(details=None):
    responses = {f"{WOWI}/filelist.json": FILELIST}
    for uid, d in (details or {}).items():
        responses[f"{WOWI}/filedetails/{uid}.json"] = d
    return WoWInterface(FakeHttp(responses), {})


def test_wowi_search_filters_by_game():
    names = [r.name for r in wowi().search("thing", ctx("retail"))]
    assert names == []
    assert [r.name for r in wowi().search("thing", ctx("classic_era", (1, 15, 8)))] == ["Classic Thing"]
    assert [r.id for r in wowi().search("bigwigs", ctx("forever", (1, 60, 1)))] == ["5086"]


def test_wowi_search_ranks_exact_then_popular():
    results = wowi().search("bar", ctx())
    assert results[0].name == "Bartender4"


def test_wowi_versions():
    p = wowi({"11190": [{"UID": "11190", "UIVersion": "4.18.0", "UIDownload": "https://cdn/x", "UIFileName": "b.zip",
                         "UIDate": 1700000000000, "UICompatibility": [{"version": "11.2.0"}]}]})
    [r] = p.versions("11190", ctx())
    assert (r.version, r.download_url, r.channel, r.date) == ("4.18.0", "https://cdn/x", "stable", 1700000000)
    assert p.versions("11190", ctx("classic_era", (1, 15, 8))) == []


def test_wowi_top_needs_listed_compat_and_sorts():
    p = wowi()
    assert [r.id for r in p.top(ctx(), "downloads")] == ["11190", "5086"]  # Ace3/LibStub list no compat
    assert {r.id for r in p.top(ctx("classic_era", (1, 15, 8)), "favorites")} == {"5086", "99"}
    assert [r.id for r in p.top(ctx(), "name")] == ["11190", "5086"]
    assert p.top(ctx(), "downloads", offset=1, limit=1)[0].id == "5086"


def test_wowi_find_by_folders():
    p = wowi()
    assert p.find_by_folders(["BigWigs", "BigWigs_Core"], ctx()) == "5086"
    assert p.find_by_folders(["Nope"], ctx()) is None


def test_wowi_error_response():
    p = wowi({"1": {"ERROR": "No AddOn found."}})
    with pytest.raises(ProviderError, match="No AddOn found"):
        p.versions("1", ctx())


def test_wowi_matching_by_toc_and_folders(tmp_path):
    make_addon(tmp_path, "Bartender4", "## X-WoWI-ID: 11190\n")
    make_addon(tmp_path, "BigWigs")
    make_addon(tmp_path, "BigWigs_Core")
    make_addon(tmp_path, "LibStub")
    folders = scan.read_folders(tmp_path, ())
    matches = {m.addon_id: m for m in wowi().match_installed([["Bartender4"], ["BigWigs"], ["BigWigs_Core"], ["LibStub"]], folders, ctx())}
    assert matches["11190"].how == "toc"
    assert matches["5086"].how == "folders" and matches["5086"].folders == ["BigWigs", "BigWigs_Core"]
    assert matches["8"].folders == ["LibStub"]  # the specific entry, not Ace3


# --- GitHub ----------------------------------------------------------------

API = "https://api.github.com"


def rel(tag, prerelease=False, assets=("A-1.zip", "release.json"), draft=False):
    return {"tag_name": tag, "prerelease": prerelease, "draft": draft, "published_at": "2026-09-27T15:15:08Z",
            "assets": [{"name": a, "browser_download_url": f"https://dl/{tag}/{a}"} for a in assets]}


def release_json(*flavors_, filename="A-1.zip", nolib=False):
    return {"releases": [{"filename": filename, "nolib": nolib, "metadata": [{"flavor": f} for f in flavors_]}]}


def gh(releases, rjson):
    responses = {f"{API}/repos/o/r/releases?per_page=15": releases}
    for r in releases:
        responses[f"https://dl/{r['tag_name']}/release.json"] = rjson.get(r["tag_name"])
    return GitHub(FakeHttp(responses), {})


def test_parse_repo():
    assert parse_repo("https://github.com/BigWigsMods/BigWigs") == "BigWigsMods/BigWigs"
    assert parse_repo("o/r.git") == "o/r"
    assert parse_repo("nope") is None


def test_release_channel():
    assert release_channel({"tag_name": "v1"}) == "stable"
    assert release_channel({"tag_name": "v1-beta1"}) == "beta"
    assert release_channel({"tag_name": "v1", "prerelease": True}) == "beta"
    assert release_channel({"tag_name": "v1-alpha", "prerelease": True}) == "alpha"


def test_github_picks_zip_by_flavor():
    p = gh([rel("v2", True), rel("v1")], {"v2": release_json("mainline", "forever"), "v1": release_json("mainline")})
    assert [r.version for r in p.versions("o/r", ctx())] == ["v2", "v1"]
    assert p.resolve("o/r", ctx(), "stable").version == "v1"
    assert p.resolve("o/r", ctx(), "beta").version == "v2"
    assert [r.version for r in p.versions("o/r", ctx("forever", (1, 60, 1)))] == ["v2"]
    assert p.versions("o/r", ctx("mists", (5, 5, 3))) == []


def test_github_skips_nolib_and_drafts():
    p = gh([rel("v3", draft=True), rel("v1", assets=("A-1.zip", "A-1-nolib.zip", "release.json"))],
           {"v1": {"releases": [{"filename": "A-1-nolib.zip", "nolib": True, "metadata": [{"flavor": "mainline"}]},
                                {"filename": "A-1.zip", "nolib": False, "metadata": [{"flavor": "mainline"}]}]}})
    [r] = p.versions("o/r", ctx())
    assert r.filename == "A-1.zip"


def test_github_without_release_json():
    p = gh([rel("v1", assets=("A-1.zip",))], {})
    [r] = p.versions("o/r", ctx())
    assert r.compat == "unverified"


def test_github_fallback_flavor_is_flagged():
    table = flavors.FlavorTable(dict(TABLE.games), TABLE.rules)
    from dataclasses import replace

    game = replace(table.games["forever"], release_fallback=("classic",))
    p = gh([rel("v1")], {"v1": release_json("classic")})
    [r] = p.versions("o/r", GameContext(game, (1, 60, 1), 16001))
    assert r.compat == "fallback"


def test_github_website_match(tmp_path):
    make_addon(tmp_path, "Foo", "## X-Website: https://github.com/someone/Foo\n")
    make_addon(tmp_path, "Org", "## X-Website: https://github.com/BigWigsMods\n")
    folders = scan.read_folders(tmp_path, ())
    matches = GitHub(FakeHttp(), {}).match_installed([["Foo"], ["Org"]], folders, ctx())
    assert [(m.addon_id, m.how) for m in matches] == [("someone/Foo", "website")]


def test_github_token_header():
    assert GitHub(FakeHttp(), {"token": "t"})._headers()["Authorization"] == "Bearer t"
    assert "Authorization" not in GitHub(FakeHttp(), {})._headers()


# --- CurseForge ------------------------------------------------------------

CF = cfmod.API


def cf_file(fid, name, rtype=1, url="https://edge/x.zip", date="2026-09-27T15:15:04.31Z"):
    return {"id": fid, "displayName": name, "fileName": f"{name}.zip", "releaseType": rtype, "fileDate": date,
            "downloadUrl": url, "isAvailable": True}


def test_curseforge_requires_key():
    p = CurseForge(FakeHttp(), {"api_key": ""})
    assert not p.available
    with pytest.raises(ProviderUnavailable):
        p.versions("1", ctx())


def test_curseforge_versions_and_channels():
    http = FakeHttp({f"{CF}/mods/2382/files?gameVersionTypeId=517&pageSize=50": {"data": [
        cf_file(3, "v427-alpha", 3, date="2026-09-29T00:00:00Z"),
        cf_file(2, "v426", 1, date="2026-09-27T00:00:00Z"),
        cf_file(1, "v426-beta", 2, date="2026-09-26T00:00:00Z"),
    ]}})
    p = CurseForge(http, {"api_key": "k"})
    assert p.resolve("2382", ctx(), "stable").version == "v426"
    assert p.resolve("2382", ctx(), "alpha").version == "v427-alpha"


def test_curseforge_forever_uses_its_version_type():
    http = FakeHttp({f"{CF}/mods/2382/files?gameVersionTypeId=88568&pageSize=50": {"data": [cf_file(2, "v426")]}})
    assert CurseForge(http, {"api_key": "k"}).resolve("2382", ctx("forever", (1, 60, 1))).version == "v426"


def test_curseforge_distribution_disabled():
    from omaforge.core.providers.base import DistributionDisabled

    http = FakeHttp({
        f"{CF}/mods/61284/files?gameVersionTypeId=517&pageSize=50": {"data": [cf_file(9, "Details", url=None)]},
        f"{CF}/mods/61284/files/9/download-url": {"data": None},
    })
    with pytest.raises(DistributionDisabled):
        CurseForge(http, {"api_key": "k"}).resolve("61284", ctx())
    # The real API answers 403 rather than an empty URL.
    del http.responses[f"{CF}/mods/61284/files/9/download-url"]
    http.status = 403
    with pytest.raises(DistributionDisabled):
        CurseForge(http, {"api_key": "k"}).resolve("61284", ctx())


def test_curseforge_top_and_categories():
    mod = {"id": 3358, "name": "DBM", "downloadCount": 634, "gamePopularityRank": 1, "allowModDistribution": False,
           "logo": {"thumbnailUrl": "https://img/dbm.png"}, "categories": [{"name": "Boss Encounters"}],
           "authors": [{"name": "MysticalOS"}], "latestFilesIndexes": [{"gameVersionTypeId": 517, "releaseType": 1, "filename": "DBM-1.zip"}]}
    http = FakeHttp({
        f"{CF}/mods/search?gameId=1&classId=1&gameVersionTypeId=517&sortField=6&sortOrder=desc&index=50&pageSize=50&categoryId=1014": {"data": [mod]},
        f"{CF}/categories?gameId=1&classId=1": {"data": [
            {"id": 1014, "name": "Boss Encounters", "parentCategoryId": 1}, {"id": 1028, "name": "Warrior", "parentCategoryId": 1020},
            {"id": 1, "name": "Addons", "isClass": True}]},
    })
    p = CurseForge(http, {"api_key": "k"})
    [r] = p.top(ctx(), "downloads", "1014", offset=50)
    assert (r.rank, r.icon, r.external_only, r.version, r.categories) == (1, "https://img/dbm.png", True, "1", ["Boss Encounters"])
    assert p.categories(ctx()) == [{"id": "1014", "name": "Boss Encounters"}]


def test_curseforge_alternates():
    http = FakeHttp({f"{CF}/mods/3358": {"data": {
        "links": {"sourceUrl": "https://github.com/DeadlyBossMods/DeadlyBossMods"},
        "latestFiles": [
            {"sortableGameVersions": [{"gameVersionTypeId": 67408}], "modules": [{"name": "DBM-Classic"}]},
            {"sortableGameVersions": [{"gameVersionTypeId": 517}], "modules": [{"name": "DBM-Core"}, {"name": "DBM-GUI"}]},
        ]}}})
    assert CurseForge(http, {"api_key": "k"}).alternates("3358", ctx()) == ("DeadlyBossMods/DeadlyBossMods", ["DBM-Core", "DBM-GUI"])


def test_curseforge_fingerprint_matching(tmp_path):
    make_addon(tmp_path, "BigWigs", files={"core.lua": "x"}, toc="## X-Curse-Project-ID: 2382\ncore.lua\n")
    make_addon(tmp_path, "BigWigs_Core")
    make_addon(tmp_path, "OnlyHeader", "## X-Curse-Project-ID: 55\n")
    make_addon(tmp_path, "Unknown")
    folders = scan.read_folders(tmp_path, ())
    fp = {name: fingerprint.folder_fingerprint(tmp_path / name) for name in folders}

    def lookup(payload):
        assert sorted(payload["fingerprints"]) == sorted(fp.values())
        return {"data": {"exactMatches": [{"id": 2382, "file": {"displayName": "v425", "modules": [
            {"name": "BigWigs", "fingerprint": fp["BigWigs"]},
            {"name": "BigWigs_Core", "fingerprint": fp["BigWigs_Core"]},
            {"name": "BigWigs_Extra", "fingerprint": 1},
        ]}}]}}

    http = FakeHttp()
    http.posts[f"{CF}/fingerprints/1"] = lookup
    groups = [["BigWigs"], ["BigWigs_Core"], ["OnlyHeader"], ["Unknown"]]
    matches = CurseForge(http, {"api_key": "k"}).match_installed(groups, folders, ctx(addons_dir=tmp_path))
    by_id = {m.addon_id: m for m in matches}
    assert by_id["2382"].folders == ["BigWigs", "BigWigs_Core"]
    assert (by_id["2382"].how, by_id["2382"].version) == ("fingerprint", "v425")
    assert by_id["55"].how == "toc"
    assert len(matches) == 2


def test_wago_stub():
    assert not Wago(FakeHttp(), {"api_key": ""}).available
    w = Wago(FakeHttp(), {"api_key": "key"})
    assert not w.available and "not implemented" in w.unavailable_reason


@pytest.mark.parametrize("raw,clean", [
    ("Plater-v656", "v656"), ("RareScanner_12.1.0.11", "12.1.0.11"), ("v426", "v426"),
    ("12.1.11", "12.1.11"), ("LittleWigs-v12.1.18", "v12.1.18"), ("Questie v12.0.2+v1.0.4", "v12.0.2+v1.0.4"),
    ("Details.20260901.13950.160", "Details.20260901.13950.160"), ("release", "release"),
])
def test_curseforge_clean_version(raw, clean):
    assert cfmod.clean_version(raw) == clean
