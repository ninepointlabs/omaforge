from conftest import make_addon

from omaforge.core.providers.fingerprint import file_fingerprint, folder_fingerprint, loaded_files, murmur2


def test_murmur2_smhasher_verification():
    # SMHasher's verification value for 32-bit MurmurHash2.
    acc = b""
    for i in range(256):
        acc += murmur2(bytes(range(i)), 256 - i).to_bytes(4, "little")
    assert murmur2(acc, 0) == 0x27864C1E


def test_file_fingerprint_ignores_whitespace():
    assert file_fingerprint(b"a b\tc\r\nd") == file_fingerprint(b"abcd")


def test_loaded_files_follow_toc_and_xml_case_insensitively(tmp_path):
    folder = make_addon(
        tmp_path,
        "Foo",
        toc="## Title: Foo\n# comment.lua\nLocales\\Load.XML\ncore.lua\nmissing.lua\n",
        files={
            "locales/load.xml": '<Ui><!-- <Script file="skip.lua"/> --><Script file="enUS.lua"/><Include file="Sub\\x.xml"/></Ui>',
            "locales/enUS.lua": "L = {}",
            "locales/sub/x.xml": '<Ui><Script file="y.lua"/></Ui>',
            "locales/sub/y.lua": "y",
            "locales/skip.lua": "skip",
            "core.lua": "core",
            "Bindings.xml": "<Bindings/>",
            "unused.lua": "not loaded",
        },
    )
    (folder / "Foo_Camelot.toc").write_text("core.lua\n")
    names = sorted(p.relative_to(folder).as_posix() for p in loaded_files(folder))
    assert names == ["Bindings.xml", "Foo.toc", "Foo_Camelot.toc", "core.lua", "locales/enUS.lua",
                     "locales/load.xml", "locales/sub/x.xml", "locales/sub/y.lua"]


def test_folder_fingerprint_ignores_unloaded_files(tmp_path):
    folder = make_addon(tmp_path, "Foo", toc="core.lua\n", files={"core.lua": "x"})
    before = folder_fingerprint(folder)
    (folder / "README.md").write_text("docs")
    assert folder_fingerprint(folder) == before
    (folder / "core.lua").write_text("changed")
    assert folder_fingerprint(folder) != before
