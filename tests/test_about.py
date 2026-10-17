"""The About dialog's facts (no Qt)."""

from pathlib import Path

import omaforge

ROOT = Path(__file__).parent.parent


def test_bundled_license_is_the_license():
    # The app ships its own copy for the About dialog; it must not drift.
    assert (ROOT / "omaforge/ui/LICENSE.txt").read_text() == (ROOT / "LICENSE").read_text()


def test_facts_agree_with_the_repo():
    license_text = (ROOT / "LICENSE").read_text()
    assert license_text.startswith("MIT License")
    assert omaforge.LICENSE_NAME == "MIT License"
    assert omaforge.COPYRIGHT.replace("©", "Copyright (c)") in license_text
    assert omaforge.SUPPORT_EMAIL == "help@ninepointlabs.com"
    assert omaforge.ORGANIZATION == "Nine Point Labs"
