import json
import logging
from logging.handlers import RotatingFileHandler, WatchedFileHandler
from pathlib import Path

from django.utils.module_loading import import_string

from .conf import BACKEND_ALIASES

logger = logging.getLogger(__name__)


class BaseBackend:
    """Custom backends subclass this and are referenced by dotted path in BACKENDS."""

    def __init__(self, config: dict):
        self.config = config

    def write(self, record: dict) -> None:
        raise NotImplementedError


class DatabaseBackend(BaseBackend):
    def write(self, record: dict) -> None:
        from .models import RequestLog

        RequestLog.from_record(record).save()


class FileBackend(BaseBackend):
    """Writes one JSON object per line via stdlib logging, which gives thread-safe writes and rotation."""

    def __init__(self, config: dict):
        super().__init__(config)
        path = Path(config["FILE_PATH"]).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(f"drf_log_writer.file.{path}")
        self.logger.propagate = False
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            if config["FILE_MAX_BYTES"]:
                handler = RotatingFileHandler(
                    path,
                    maxBytes=config["FILE_MAX_BYTES"],
                    backupCount=config["FILE_BACKUP_COUNT"],
                    encoding="utf-8",
                )
            else:
                handler = WatchedFileHandler(path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)

    def write(self, record: dict) -> None:
        self.logger.info(json.dumps(record, ensure_ascii=False, default=str))


_instances: dict[tuple, BaseBackend] = {}


def get_backends(config: dict) -> list[BaseBackend]:
    backends = []
    for name in config["BACKENDS"]:
        dotted_path = BACKEND_ALIASES.get(name, name)
        key = (dotted_path, config["FILE_PATH"], config["FILE_MAX_BYTES"], config["FILE_BACKUP_COUNT"])
        if key not in _instances:
            _instances[key] = import_string(dotted_path)(config)
        backends.append(_instances[key])
    return backends


def write_record(record: dict, config: dict) -> None:
    # One failing backend shouldn't stop the others from receiving the record.
    for backend in get_backends(config):
        try:
            backend.write(record)
        except Exception:
            logger.exception("drf_log_writer backend %s failed", type(backend).__name__)
