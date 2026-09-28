"""CurseForge-compatible addon folder fingerprints.

A file's fingerprint is a 32-bit MurmurHash2 (seed 1) of its bytes with tab,
newline, carriage return and space removed. A folder's fingerprint (what
CurseForge lists per module) is MurmurHash2 (seed 1) of the decimal
fingerprints, sorted numerically and concatenated, of the files the game
would load: every .toc in the folder, the files each TOC lists, XML
<Script file>/<Include file> references (recursively) and Bindings.xml.

Verified against all 12 module fingerprints of BigWigs v426 from the
CurseForge API.
"""

import re
from pathlib import Path

_M = 0x5BD1E995
_WS = bytes((9, 10, 13, 32))


def murmur2(data: bytes, seed: int = 0) -> int:
    length = len(data)
    h = (seed ^ length) & 0xFFFFFFFF
    i = 0
    while length - i >= 4:
        k = int.from_bytes(data[i : i + 4], "little")
        k = (k * _M) & 0xFFFFFFFF
        k ^= k >> 24
        k = (k * _M) & 0xFFFFFFFF
        h = (h * _M) & 0xFFFFFFFF
        h ^= k
        i += 4
    rest = length - i
    if rest == 3:
        h ^= data[i + 2] << 16
    if rest >= 2:
        h ^= data[i + 1] << 8
    if rest >= 1:
        h ^= data[i]
        h = (h * _M) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * _M) & 0xFFFFFFFF
    h ^= h >> 15
    return h


def normalize(data: bytes) -> bytes:
    return data.translate(None, _WS)


def file_fingerprint(data: bytes) -> int:
    return murmur2(normalize(data), seed=1)


def _resolve(base: Path, rel: str) -> Path | None:
    """Resolve a Windows-style relative path case-insensitively, as the game does."""
    path = base
    for part in re.split(r"[\\/]+", rel.strip()):
        if part in ("", "."):
            continue
        if part == "..":
            path = path.parent
            continue
        exact = path / part
        if exact.exists():
            path = exact
            continue
        try:
            hit = next((c for c in path.iterdir() if c.name.lower() == part.lower()), None)
        except OSError:
            return None
        if hit is None:
            return None
        path = hit
    return path if path.is_file() else None


def loaded_files(folder: Path) -> set[Path]:
    files: set[Path] = set()

    def walk(path: Path | None) -> None:
        if path is None or path in files:
            return
        files.add(path)
        suffix = path.suffix.lower()
        if suffix not in (".toc", ".xml"):
            return
        text = path.read_text("utf-8", errors="replace")
        if suffix == ".toc":
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    walk(_resolve(path.parent, line))
        else:
            text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
            for m in re.finditer(r"<(?:Include|Script)\s+file\s*=\s*[\"'](.*?)[\"']", text, re.I):
                walk(_resolve(path.parent, m.group(1)))

    for toc in sorted(folder.glob("*")):
        if toc.is_file() and toc.suffix.lower() == ".toc":
            walk(toc)
    walk(_resolve(folder, "Bindings.xml"))
    return files


def folder_fingerprint(folder: Path) -> int:
    fps = sorted(file_fingerprint(p.read_bytes()) for p in loaded_files(folder))
    return murmur2("".join(str(f) for f in fps).encode(), seed=1)
