"""Readers for Blizzard's pipe-separated `.build.info` / `.flavor.info` files.

Both use the same format: a header line of `Name!TYPE:size` columns separated
by `|`, then one row per entry.
"""

from pathlib import Path


def parse_table(text: str) -> list[dict[str, str]]:
    lines = [ln.strip("\r") for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    header = [col.split("!", 1)[0].strip() for col in lines[0].split("|")]
    rows = []
    for line in lines[1:]:
        cells = line.split("|")
        rows.append({name: (cells[i] if i < len(cells) else "") for i, name in enumerate(header)})
    return rows


def read_table(path: Path) -> list[dict[str, str]]:
    try:
        return parse_table(path.read_text("utf-8", errors="replace"))
    except (FileNotFoundError, NotADirectoryError):
        return []


def read_flavor(client_dir: Path) -> str | None:
    """The product id of a client folder, e.g. `wow` or `wow_classic_beta`."""
    rows = read_table(client_dir / ".flavor.info")
    if rows:
        return rows[0].get("Product Flavor") or next(iter(rows[0].values()), None) or None
    return None


def read_builds(root: Path) -> dict[str, dict[str, str]]:
    """Product id -> {version, build_key, active, branch} from the root's .build.info."""
    out = {}
    for row in read_table(root / ".build.info"):
        product = row.get("Product")
        if not product:
            continue
        # Several regions can list the same product; prefer the active row.
        if product in out and row.get("Active") != "1":
            continue
        out[product] = {
            "version": row.get("Version", ""),
            "build_key": row.get("Build Key", ""),
            "active": row.get("Active", ""),
            "branch": row.get("Branch", ""),
        }
    return out
