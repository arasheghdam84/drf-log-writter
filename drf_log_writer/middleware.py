import logging
import time
import traceback

from django.utils import timezone

from .backends import write_record
from .capture import build_record, is_multipart, read_form_body, read_request_body, should_log
from .conf import get_config

logger = logging.getLogger(__name__)

EXCEPTION_ATTR = "_drf_log_writer_exception"


class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        config = get_config()
        if not should_log(request, config):
            return self.get_response(request)

        started_at = timezone.now()
        start = time.perf_counter()
        multipart = is_multipart(request)
        body = None if multipart else read_request_body(request, config["MAX_BODY_LENGTH"])

        response = self.get_response(request)

        duration_ms = (time.perf_counter() - start) * 1000
        # Logging must never break the request it is observing.
        try:
            files = None
            if multipart:
                body, files = read_form_body(request, config["MAX_BODY_LENGTH"])
            record = build_record(
                request,
                response,
                started_at=started_at,
                duration_ms=duration_ms,
                request_body=body,
                request_files=files,
                exception=getattr(request, EXCEPTION_ATTR, None),
                config=config,
            )
            write_record(record, config)
        except Exception:
            logger.exception("drf_log_writer failed to log %s %s", request.method, request.path)
        return response

    def process_exception(self, request, exception):
        setattr(request, EXCEPTION_ATTR, "".join(traceback.format_exception(exception)))
