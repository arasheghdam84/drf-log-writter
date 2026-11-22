from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

DEFAULTS = {
    "ENABLED": True,
    # "database", "file", or a dotted path to a custom backend class. Any combination.
    "BACKENDS": ["database"],
    "FILE_PATH": "logs/requests.log",
    # 0 switches to WatchedFileHandler, for when an external tool (logrotate) rotates the file.
    "FILE_MAX_BYTES": 10 * 1024 * 1024,
    "FILE_BACKUP_COUNT": 5,
    # Regexes matched against request.path.
    "SKIP_PATHS": [r"^/admin/", r"^/static/", r"^/media/", r"^/favicon\.ico$"],
    # None logs every method.
    "METHODS": None,
    # Bodies above this size are replaced by a marker; None means unlimited, 0 disables body logging.
    "MAX_BODY_LENGTH": 64 * 1024,
    # Values under these keys (case-insensitive, at any depth) are replaced by an HMAC-SHA256 digest.
    "HASH_KEYS": [
        "password",
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "token",
        "access",
        "refresh",
        "secret",
    ],
    # Defaults to settings.SECRET_KEY; set explicitly so hashes survive a SECRET_KEY rotation.
    "HASH_SECRET": None,
    # Dotted paths into the JSON record, shown as columns in the admin.
    "ADMIN_COLUMNS": [
        "timestamp",
        "request.method",
        "request.path",
        "response.status_code",
        "duration_ms",
        "request.user.username",
        "request.ip",
    ],
    "ADMIN_PAGE_SIZE": 50,
}

BACKEND_ALIASES = {
    "database": "drf_log_writer.backends.DatabaseBackend",
    "file": "drf_log_writer.backends.FileBackend",
}


def get_config() -> dict:
    user_config = getattr(settings, "DRF_LOG_WRITER", {})
    unknown = set(user_config) - set(DEFAULTS)
    if unknown:
        raise ImproperlyConfigured(f"Unknown DRF_LOG_WRITER keys: {', '.join(sorted(unknown))}")
    return {**DEFAULTS, **user_config}


def hash_keys(config: dict) -> frozenset[str]:
    return frozenset(key.lower() for key in config["HASH_KEYS"])
