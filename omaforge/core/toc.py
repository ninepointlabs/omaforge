"""Parse addon `.toc` files and pick the one a given client would load."""

import re
from dataclasses import dataclass, field
from pathlib import Path

PROVIDER_HEADERS = {
    "curseforge": "x-curse-project-id",
    "wago": "x-wago-id",
    "wowinterface": "x-wowi-id",
}

_COLOR = re.compile(r"\|c[0-9a-fA-F]{8}|\|r|\|T[^|]*\|t|\|A[^|]*\|a")


def clean_text(text: str) -> str:
    """Strip WoW UI escape codes (colors, textures) from a TOC title."""
    return re.sub(r"\s+", " ", _COLOR.sub("", text)).strip()


@dataclass
class Toc:
    folder: str
    file: str
    fields: dict[str, str] = field(default_factory=dict)  # lower-cased keys

    def get(self, key: str, default: str = "") -> str:
        return self.fields.get(key.lower(), default)

    @property
    def title(self) -> str:
        return clean_text(self.get("title")) or self.folder

    @property
    def version(self) -> str:
        v = self.get("version")
        return "" if v.startswith("@") else v

    @property
    def interfaces(self) -> list[int]:
        return [int(x) for x in re.findall(r"\d+", self.get("interface"))]

    @property
    def load_on_demand(self) -> bool:
        return self.get("loadondemand") == "1"

    @property
    def dependencies(self) -> list[str]:
        deps = []
        for key, value in self.fields.items():
            if key in ("dependencies", "requireddeps") or re.fullmatch(r"dep\w*", key):
                deps += [d.strip() for d in value.split(",") if d.strip()]
        return deps

    @property
    def provider_ids(self) -> dict[str, str]:
        out = {}
        for provider, header in PROVIDER_HEADERS.items():
            value = self.get(header).strip()
            if value and not value.startswith("@"):
                out[provider] = value
        return out

    @property
    def website(self) -> str:
        return self.get("x-website") or self.get("x-url") or ""


def parse(text: str, folder: str = "", file: str = "") -> Toc:
    fields: dict[str, str] = {}
    for line in text.lstrip("﻿").splitlines():
        m = re.match(r"^##\s*([^:]+?)\s*:\s*(.*?)\s*$", line)
        if m:
            fields.setdefault(m.group(1).lower(), m.group(2))
    return Toc(folder=folder, file=file, fields=fields)


def toc_candidates(folder: Path) -> dict[str | None, Path]:
    """Map of suffix (lower-case, None for the plain TOC) -> file."""
    out: dict[str | None, Path] = {}
    pattern = re.compile(rf"^{re.escape(folder.name)}(?:[-_]([A-Za-z0-9]+))?\.toc$", re.I)
    try:
        entries = list(folder.iterdir())
    except OSError:
        return out
    for entry in entries:
        m = pattern.match(entry.name)
        if m and entry.is_file():
            out[m.group(1).lower() if m.group(1) else None] = entry
    return out


def select_toc(folder: Path, suffixes: tuple[str, ...] | list[str]) -> Path | None:
    """The TOC the client would read: first matching suffix, else the plain TOC."""
    candidates = toc_candidates(folder)
    for suffix in suffixes:
        if suffix.lower() in candidates:
            return candidates[suffix.lower()]
    return candidates.get(None)


def read(folder: Path, suffixes: tuple[str, ...] | list[str] = ()) -> Toc | None:
    path = select_toc(folder, suffixes)
    if path is None:
        return None
    try:
        text = path.read_text("utf-8", errors="replace")
    except OSError:
        return None
    return parse(text, folder=folder.name, file=path.name)


def any_toc(folder: Path) -> bool:
    return bool(toc_candidates(folder))
