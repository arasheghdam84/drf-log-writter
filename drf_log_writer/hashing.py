import hashlib
import hmac
import json
from typing import Any

from django.conf import settings

PREFIX = "hashed$"


def hash_value(value: Any, config: dict) -> str:
    secret = config["HASH_SECRET"] or settings.SECRET_KEY
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, default=str)
    digest = hmac.new(secret.encode(), text.encode(), hashlib.sha256).hexdigest()
    return f"{PREFIX}{digest}"


def hash_sensitive(data: Any, keys: frozenset[str], config: dict) -> Any:
    if isinstance(data, dict):
        return {
            key: (
                hash_value(value, config)
                if str(key).lower() in keys and value is not None
                else hash_sensitive(value, keys, config)
            )
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [hash_sensitive(item, keys, config) for item in data]
    return data
