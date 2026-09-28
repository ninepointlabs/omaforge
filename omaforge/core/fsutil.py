"""Small filesystem helpers shared by the core."""

import json
import os
import tempfile
from pathlib import Path


def atomic_write_bytes(path: Path, data: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, text: str, mode: int = 0o644) -> None:
    atomic_write_bytes(path, text.encode("utf-8"), mode)


def atomic_write_json(path: Path, obj, mode: int = 0o644) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, sort_keys=True) + "\n", mode)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text("utf-8"))
    except FileNotFoundError:
        return default
