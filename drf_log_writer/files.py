"""Reading JSON-lines log files newest-first, so a page of results never needs a full-file scan."""

import json
import os
from collections.abc import Iterator
from itertools import islice
from pathlib import Path

from .search import Condition, matches

CHUNK_SIZE = 64 * 1024


def log_file_paths(config: dict) -> list[Path]:
    """The active file followed by rotated backups (.1 is the most recent backup)."""
    base = Path(config["FILE_PATH"]).resolve()
    candidates = [base] + [
        base.with_name(f"{base.name}.{i}") for i in range(1, config["FILE_BACKUP_COUNT"] + 1)
    ]
    return [path for path in candidates if path.exists()]


def read_lines_reversed(path: Path) -> Iterator[str]:
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        position = f.tell()
        remainder = b""
        while position > 0:
            size = min(CHUNK_SIZE, position)
            position -= size
            f.seek(position)
            lines = (f.read(size) + remainder).split(b"\n")
            remainder = lines.pop(0)  # may be the tail of a line that continues in the previous chunk
            for line in reversed(lines):
                if line.strip():
                    yield line.decode("utf-8", errors="replace")
        if remainder.strip():
            yield remainder.decode("utf-8", errors="replace")


def iter_records(paths: list[Path]) -> Iterator[dict]:
    for path in paths:
        for line in read_lines_reversed(path):
            try:
                yield json.loads(line)
            except ValueError:
                continue


def search_records(
    paths: list[Path], conditions: list[Condition], offset: int = 0, limit: int = 50
) -> tuple[list[dict], bool]:
    """Returns one page of matching records and whether another page exists."""
    found = (record for record in iter_records(paths) if matches(record, conditions))
    page = list(islice(found, offset, offset + limit + 1))
    return page[:limit], len(page) > limit
