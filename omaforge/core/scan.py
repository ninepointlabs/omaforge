"""Scan a client's AddOns folder and group folders into addons.

An addon is often several folders (DBM ships DBM-Core, DBM-GUI and a folder
per raid). Folders are grouped by, in order of trust:

1. omaforge's own records of which folders came from which download;
2. a shared X-Curse-Project-ID / X-Wago-ID / X-WoWI-ID header;
3. a dependency on a folder whose name is a prefix of theirs
   (DBM-Raids-WarWithin -> DBM-Core, BigWigs_Plugins -> BigWigs).

Recorded groups are never merged by the heuristics.
"""

import re
from pathlib import Path

from omaforge.core import toc as tocmod
from omaforge.core.models import Folder


def read_folders(addons_dir: Path, suffixes: tuple[str, ...]) -> dict[str, Folder]:
    out = {}
    try:
        entries = sorted(addons_dir.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return out
    for entry in entries:
        if entry.name.startswith(".") or not entry.is_dir():
            continue
        t = tocmod.read(entry, suffixes)
        loadable = t is not None
        if t is None:
            # Present but built for another flavor: read any TOC for metadata.
            cands = tocmod.toc_candidates(entry)
            if not cands:
                continue
            path = cands.get(None) or sorted(cands.values())[0]
            t = tocmod.parse(path.read_text("utf-8", errors="replace"), entry.name, path.name)
        out[entry.name] = Folder(
            name=entry.name,
            title=t.title,
            version=t.version,
            interfaces=t.interfaces,
            dependencies=t.dependencies,
            provider_ids=t.provider_ids,
            website=t.website,
            author=tocmod.clean_text(t.get("author")),
            load_on_demand=t.load_on_demand,
            loadable=loadable,
        )
    return out


class _UnionFind:
    def __init__(self, items):
        self.parent = {i: i for i in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)

    def groups(self) -> list[list[str]]:
        out: dict[str, list[str]] = {}
        for item in self.parent:
            out.setdefault(self.find(item), []).append(item)
        return [sorted(v, key=str.lower) for v in out.values()]


def _prefix(name: str) -> str:
    return re.split(r"[-_ .]", name, maxsplit=1)[0].lower()


def _related(child: str, parent: str) -> bool:
    c, p = child.lower(), parent.lower()
    if c.startswith(p) and c != p:
        return True
    pre = _prefix(child)
    return len(pre) >= 3 and pre == _prefix(parent) and re.search(r"[-_ .]", child) is not None


def group_folders(folders: dict[str, Folder], owned: dict[str, list[str]]) -> list[list[str]]:
    """Return groups of folder names. `owned` maps an addon key to its recorded folders."""
    owned_folders = {f for fs in owned.values() for f in fs if f in folders}
    free = [f for f in folders if f not in owned_folders]
    uf = _UnionFind(free)

    by_id: dict[tuple[str, str], str] = {}
    for name in free:
        for provider, pid in folders[name].provider_ids.items():
            first = by_id.setdefault((provider, pid), name)
            uf.union(first, name)

    lower = {n.lower(): n for n in free}
    for name in free:
        for dep in folders[name].dependencies:
            target = lower.get(dep.lower())
            if target and _related(name, target):
                uf.union(name, target)

    groups = uf.groups()
    for fs in owned.values():
        present = sorted((f for f in fs if f in folders), key=str.lower)
        if present:
            groups.append(present)
    return groups


def main_folder(group: list[str], folders: dict[str, Folder]) -> str:
    members = {g.lower() for g in group}

    def score(name: str):
        f = folders[name]
        inner_deps = sum(1 for d in f.dependencies if d.lower() in members)
        dependents = sum(1 for g in group if name.lower() in (d.lower() for d in folders[g].dependencies))
        # Most depended-on, not load-on-demand, fewest in-group deps, shortest name.
        return (-dependents, f.load_on_demand, inner_deps, len(name), name.lower())

    return min(group, key=score)
