import json
from typing import Any

from .hashing import PREFIX as HASH_PREFIX

MISSING = object()


def get_by_path(data: Any, path: str) -> Any:
    """Resolve a dotted path like ``request.body.items.0.id``; returns MISSING if any segment is absent."""
    for key in path.split("."):
        if isinstance(data, dict) and key in data:
            data = data[key]
        elif isinstance(data, list) and key.isdigit() and int(key) < len(data):
            data = data[int(key)]
        else:
            return MISSING
    return data


def format_cell(value: Any, max_length: int = 120) -> str:
    if value is MISSING or value is None:
        return "-"
    if isinstance(value, str) and value.startswith(HASH_PREFIX):
        # A prefix is enough to tell hashes apart in a table; the detail view shows the full digest.
        return f"{value[: len(HASH_PREFIX) + 10]}…"
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= max_length else f"{text[: max_length - 1]}…"


def parse_columns(text: str) -> list[str]:
    return [column.strip() for column in text.split(",") if column.strip()]
