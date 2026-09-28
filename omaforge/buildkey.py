"""A CurseForge API key baked into release builds, lightly obfuscated.

The key is never in the repository. Release builds generate
`omaforge/_buildkey.py` from $OMAFORGE_CURSEFORGE_BUILD_KEY:

    python -m omaforge.buildkey write

The obfuscation (XOR with a random pad, base64) only keeps the key out of
plain-text greps and secret scanners; anyone with the package can recover
it. A key the user sets in config.toml or $OMAFORGE_CURSEFORGE_API_KEY always
takes precedence.
"""

import base64
import os
import secrets
import sys
from pathlib import Path

ENV = "OMAFORGE_CURSEFORGE_BUILD_KEY"
TARGET = Path(__file__).parent / "_buildkey.py"


def encode(key: str) -> tuple[str, str]:
    raw = key.encode()
    pad = secrets.token_bytes(len(raw))
    mixed = bytes(a ^ b for a, b in zip(raw, pad))
    return base64.b64encode(pad).decode()[::-1], base64.b64encode(mixed).decode()[::-1]


def decode(pad: str, data: str) -> str:
    p = base64.b64decode(pad[::-1])
    d = base64.b64decode(data[::-1])
    return bytes(a ^ b for a, b in zip(d, p)).decode()


def builtin_curseforge_key() -> str:
    try:
        from omaforge import _buildkey  # generated at build time, absent in the repo
    except ImportError:
        return ""
    try:
        return decode(_buildkey.PAD, _buildkey.DATA)
    except (ValueError, UnicodeDecodeError):
        return ""


def write(key: str, target: Path = TARGET) -> Path:
    pad, data = encode(key)
    target.write_text(f'# Generated at build time. Not in the repository.\nPAD = "{pad}"\nDATA = "{data}"\n')
    return target


def main(argv: list[str]) -> int:
    if argv[:1] != ["write"]:
        print("usage: python -m omaforge.buildkey write   (reads $" + ENV + ")", file=sys.stderr)
        return 2
    key = os.environ.get(ENV, "").strip()
    if not key:
        TARGET.unlink(missing_ok=True)
        print(f"{ENV} not set; building without a CurseForge key")
        return 0
    write(key)
    print(f"wrote {TARGET.name} (CurseForge key embedded, obfuscated)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
