"""Turns a Django request/response pair into a JSON-native log record."""

import json
import re
import uuid
from datetime import datetime
from typing import Any

from django.core.exceptions import RequestDataTooBig
from django.http import QueryDict
from django.http.request import RawPostDataException

from .conf import hash_keys
from .hashing import hash_sensitive
from .utils import MISSING


def should_log(request, config: dict) -> bool:
    if not config["ENABLED"]:
        return False
    if config["METHODS"] and request.method not in config["METHODS"]:
        return False
    return not any(re.search(pattern, request.path) for pattern in config["SKIP_PATHS"])


def is_multipart(request) -> bool:
    return request.content_type.startswith("multipart/")


def read_request_body(request, max_length: int | None) -> Any:
    """Must run before the view: once the view consumes the stream, request.body is unavailable."""
    if max_length == 0:
        return None
    try:
        raw = request.body
    except RequestDataTooBig:
        return "<too large>"
    except RawPostDataException:
        return None
    return decode_body(raw, request.content_type, max_length)


def read_form_body(request, max_length: int | None) -> tuple[Any, Any]:
    """Multipart bodies are read after the view so uploads aren't buffered twice."""
    if max_length == 0:
        return None, None
    files = {name: _single([_file_info(f) for f in request.FILES.getlist(name)]) for name in request.FILES}
    return _multi_dict(request.POST), files or None


def decode_body(raw: bytes, content_type: str, max_length: int | None) -> Any:
    if not raw:
        return None
    if max_length and len(raw) > max_length:
        # Never store a partial body: truncated JSON can't be parsed, so hashed keys would leak.
        return f"<truncated: {len(raw)} bytes>"
    if "json" in content_type:
        try:
            return json.loads(raw)
        except ValueError:
            pass
    if content_type == "application/x-www-form-urlencoded":
        return _multi_dict(QueryDict(raw))
    try:
        return raw.decode()
    except UnicodeDecodeError:
        return f"<binary: {len(raw)} bytes>"


def build_record(
    request,
    response,
    *,
    started_at: datetime,
    duration_ms: float,
    request_body: Any,
    request_files: Any,
    exception: str | None,
    config: dict,
) -> dict:
    match = getattr(request, "resolver_match", None)
    keys = hash_keys(config)
    request_data = {
        "method": request.method,
        "path": request.path,
        "query_params": _multi_dict(request.GET),
        "headers": dict(request.headers),
        "content_type": request.content_type,
        "body": request_body,
        "files": request_files,
        "ip": request.META.get("REMOTE_ADDR"),
        "user": _user(request),
    }
    response_data = {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": _response_body(response, config["MAX_BODY_LENGTH"]),
    }
    return {
        "id": str(uuid.uuid4()),
        "timestamp": started_at.isoformat(),
        "duration_ms": round(duration_ms, 2),
        "view": match.view_name if match else None,
        "request": hash_sensitive(request_data, keys, config),
        "response": hash_sensitive(response_data, keys, config),
        "exception": exception,
    }


def _response_body(response, max_length: int | None) -> Any:
    if max_length == 0:
        return None
    if getattr(response, "streaming", False):
        return "<streaming>"
    data = getattr(response, "data", MISSING)  # DRF Response keeps the unrendered data
    if data is MISSING:
        return decode_body(response.content, response.get("Content-Type", ""), max_length)
    dumped = json.dumps(data, ensure_ascii=False, default=str)
    if max_length and len(dumped.encode()) > max_length:
        return f"<truncated: {len(dumped.encode())} bytes>"
    return json.loads(dumped)


def _user(request) -> dict | None:
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    pk = user.pk if isinstance(user.pk, int) else str(user.pk)
    return {"id": pk, "username": user.get_username()}


def _multi_dict(query_dict) -> dict:
    return {key: _single(values) for key, values in query_dict.lists()}


def _single(values: list) -> Any:
    return values[0] if len(values) == 1 else values


def _file_info(uploaded) -> dict:
    return {"name": uploaded.name, "size": uploaded.size, "content_type": uploaded.content_type}
