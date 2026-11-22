# drf-log-writer

Log every Django / Django REST Framework request and response as a single JSON record — to files, the
database, or both — with key-based value hashing, a search language, and an admin viewer whose columns are
picked from keys in the JSON.

## Install

```bash
pip install drf-log-writer          # or: uv add drf-log-writer
```

```python
INSTALLED_APPS = [
    ...,
    "drf_log_writer",
]

MIDDLEWARE = [
    "drf_log_writer.middleware.RequestLogMiddleware",  # near the top: measures the full request
    ...,
]
```

```bash
python manage.py migrate
```

That's it — requests are now logged to the database. Everything else is optional.

## Configuration

All settings live in one dict; every key is optional.

```python
DRF_LOG_WRITER = {
    "BACKENDS": ["database", "file"],  # "database", "file", or a dotted path to a custom backend
    "FILE_PATH": BASE_DIR / "logs" / "requests.log",
    "FILE_MAX_BYTES": 10 * 1024 * 1024,  # rotate at this size; 0 = WatchedFileHandler (use logrotate)
    "FILE_BACKUP_COUNT": 5,
    "HASH_KEYS": ["password", "authorization", "cookie", "token", "card_number"],
    "HASH_SECRET": env("LOG_HASH_SECRET"),  # defaults to SECRET_KEY
    "SKIP_PATHS": [r"^/admin/", r"^/static/", r"^/health/"],
    "METHODS": None,  # e.g. ["POST", "PUT", "PATCH", "DELETE"]
    "MAX_BODY_LENGTH": 64 * 1024,  # bigger bodies become "<truncated: N bytes>"; 0 = no bodies
    "ADMIN_COLUMNS": ["timestamp", "request.method", "request.path", "response.status_code", "duration_ms"],
    "ADMIN_PAGE_SIZE": 50,
    "ENABLED": True,
}
```

| Key | Default | Notes |
| --- | --- | --- |
| `BACKENDS` | `["database"]` | Any combination. |
| `FILE_PATH` | `logs/requests.log` | Relative paths resolve against the working directory — prefer absolute. |
| `FILE_MAX_BYTES` / `FILE_BACKUP_COUNT` | 10 MB / 5 | Size-based rotation. With several worker processes, set `FILE_MAX_BYTES = 0` and rotate with logrotate. |
| `HASH_KEYS` | password, authorization, cookie, set-cookie, x-api-key, token, access, refresh, secret | Case-insensitive, matched at any depth in headers, query params, and bodies. |
| `HASH_SECRET` | `SECRET_KEY` | HMAC key. Set it explicitly so hashes stay stable across `SECRET_KEY` rotations. |
| `SKIP_PATHS` | admin, static, media, favicon | Regexes matched against `request.path`. |
| `METHODS` | `None` (all) | |
| `MAX_BODY_LENGTH` | 64 KB | Applies to request and response bodies. |
| `ADMIN_COLUMNS` | see above | Dotted paths into the record. |

## The record

Every request produces one JSON object, identical in the file and the database:

```json
{
  "id": "6f1c…",
  "timestamp": "2026-11-22T10:15:02.120Z",
  "duration_ms": 42.7,
  "view": "orders-list",
  "request": {
    "method": "POST",
    "path": "/api/login/",
    "query_params": {"next": "/home"},
    "headers": {"Content-Type": "application/json", "Authorization": "hashed$9b1e…"},
    "content_type": "application/json",
    "body": {"username": "john", "password": "hashed$4a7d…"},
    "files": null,
    "ip": "10.0.0.4",
    "user": {"id": 7, "username": "john"}
  },
  "response": {
    "status_code": 200,
    "headers": {"Content-Type": "application/json"},
    "body": {"token": "hashed$c0f2…"}
  },
  "exception": null
}
```

- JSON and form bodies are stored parsed; other text is stored as a string; binary is `"<binary: N bytes>"`.
- DRF responses are logged from `response.data`; plain Django responses from their content.
- Multipart uploads log form fields plus file metadata (`name`, `size`, `content_type`) — never file contents.
- `exception` holds the traceback when the view raised.

### Hashing

Values under a key listed in `HASH_KEYS` are replaced by `hashed$<hmac-sha256>`. The same input always gives
the same hash, so you can still search for a value without storing it. Only keyed data (JSON, form, headers,
query params) can be hashed — raw text bodies are stored as-is, and bodies over `MAX_BODY_LENGTH` are dropped
entirely rather than truncated, so a sensitive key can never leak through a partial body.

## Searching

One syntax works in the admin search box (database and files) and in the management command. Terms are
space-separated and all must match:

| Query | Meaning |
| --- | --- |
| `request.method=POST` | exact match on a dotted path |
| `response.status_code!=200` | not equal (also matches when the key is missing) |
| `request.path~orders` | case-insensitive contains |
| `duration_ms>=500` | `>`, `>=`, `<`, `<=` |
| `request.body.items.0.sku=A1` | list indexes work too |
| `request.body.name="John Doe"` | quote values with spaces |
| `request.body.password=hunter2` | hashed keys are hashed before comparing |
| `timeout` | free text anywhere in the record |

```bash
python manage.py search_request_logs "response.status_code>=500 request.path~checkout" --limit 10
python manage.py search_request_logs "request.user.username=john" --source file
python manage.py purge_request_logs --days 30
```

## Admin

- **Request logs** (database): a filterable, searchable, read-only list. Columns are taken from
  `ADMIN_COLUMNS`, and you can change them in the "Columns" box above the list (for example
  `timestamp, request.method, request.body.email, response.body.id`). Your choice is kept in your session.
  Columns that map to an indexed field (method, path, status, duration, user, IP, timestamp) sort on that
  field; any other JSON column sorts on the JSON value.
- **Request log files**: shown when the `file` backend is enabled. It reads the JSON-lines file and its
  rotated backups, newest first, with the same search, column picker, and an expandable JSON view per row.
  Access requires the `drf_log_writer.view_requestlogfile` permission.

## Custom backends

```python
from drf_log_writer.backends import BaseBackend


class StdoutBackend(BaseBackend):
    def write(self, record: dict) -> None:
        print(record["request"]["path"])


DRF_LOG_WRITER = {"BACKENDS": ["database", "myproject.logging.StdoutBackend"]}
```

## Notes

- Logging failures are caught and reported through the `drf_log_writer` logger; they never break the request.
- Database writes happen synchronously, inside the request. For very high traffic, prefer the `file`
  backend and ship the file with your usual log pipeline.
- `SKIP_PATHS` excludes `/admin/` by default; adjust it if your admin is mounted somewhere else.

## Development

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format .
```

## License

MIT — see [LICENSE](LICENSE).
