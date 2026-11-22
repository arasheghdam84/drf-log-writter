"""One query language for both the database and the JSON-lines files.

Space-separated terms, all of which must match:
    request.method=POST            exact match on a dotted path
    response.status_code!=200      not equal (also matches when the key is missing)
    request.path~orders            case-insensitive contains
    duration_ms>=500               numeric comparison (>, >=, <, <=)
    timeout                        free text anywhere in the record
    request.body.name="John Doe"   quote values containing spaces

Values for keys listed in HASH_KEYS are hashed before comparing, so ``request.body.password=secret`` works.
"""

import json
import operator
import re
import shlex
from dataclasses import dataclass
from functools import reduce
from typing import Any

from django.db.models import Q, QuerySet

from .conf import get_config, hash_keys
from .hashing import hash_value
from .utils import MISSING, get_by_path

CONDITION_RE = re.compile(r"^(?P<path>[\w.\-]+?)(?P<op>>=|<=|!=|=|~|>|<)(?P<raw>.*)$")
COMPARISONS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le}
DB_COMPARISONS = {">": "gt", ">=": "gte", "<": "lt", "<=": "lte"}


@dataclass(frozen=True)
class Condition:
    path: str | None  # None means free-text search over the whole record
    op: str
    value: Any
    # For = and !=: every value that counts as equal, so `status=200` matches both 200 and "200".
    equals: tuple = ()


def parse_query(query: str, config: dict | None = None) -> list[Condition]:
    config = config or get_config()
    keys = hash_keys(config)
    try:
        tokens = shlex.split(query)
    except ValueError:  # unbalanced quotes
        tokens = query.split()

    conditions = []
    for token in tokens:
        match = CONDITION_RE.match(token)
        if not match:
            conditions.append(Condition(None, "~", token))
            continue
        path, op, raw = match["path"], match["op"], match["raw"]
        if op in ("=", "!="):
            if path.rsplit(".", 1)[-1].lower() in keys:
                equals = (hash_value(raw, config),)
            else:
                coerced = _coerce(raw)
                equals = (raw,) if coerced == raw else (coerced, raw)
            conditions.append(Condition(path, op, raw, equals))
        else:
            conditions.append(Condition(path, op, raw if op == "~" else _coerce(raw)))
    return conditions


def matches(record: dict, conditions: list[Condition]) -> bool:
    return all(_matches_one(record, condition) for condition in conditions)


def filter_queryset(queryset: QuerySet, conditions: list[Condition]) -> QuerySet:
    if not conditions:
        return queryset
    return queryset.filter(reduce(operator.and_, (_to_q(condition) for condition in conditions)))


def _matches_one(record: dict, condition: Condition) -> bool:
    if condition.path is None:
        return condition.value.lower() in json.dumps(record, ensure_ascii=False, default=str).lower()

    actual = get_by_path(record, condition.path)
    if condition.op == "=":
        return actual is not MISSING and actual in condition.equals
    if condition.op == "!=":
        return actual is MISSING or actual not in condition.equals
    if actual is MISSING or actual is None:
        return False
    if condition.op == "~":
        text = actual if isinstance(actual, str) else json.dumps(actual, ensure_ascii=False, default=str)
        return condition.value.lower() in text.lower()
    try:
        return COMPARISONS[condition.op](float(actual), float(condition.value))
    except (TypeError, ValueError):
        return COMPARISONS[condition.op](str(actual), str(condition.value))


def _to_q(condition: Condition) -> Q:
    if condition.path is None:
        return Q(path__icontains=condition.value) | Q(data__icontains=condition.value)

    lookup = "data__" + condition.path.replace(".", "__")
    if condition.op in ("=", "!="):
        equal = reduce(operator.or_, (Q(**{lookup: value}) for value in condition.equals))
        if condition.op == "=":
            return equal
        return ~equal | Q(**{f"{lookup}__isnull": True})
    if condition.op == "~":
        return Q(**{f"{lookup}__icontains": condition.value})
    return Q(**{f"{lookup}__{DB_COMPARISONS[condition.op]}": condition.value})


def _coerce(raw: str) -> Any:
    try:
        value = json.loads(raw)
    except ValueError:
        return raw
    return value if isinstance(value, (int, float, bool)) or value is None else raw
