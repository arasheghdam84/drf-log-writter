import json

from django.core.management.base import BaseCommand

from drf_log_writer.conf import get_config
from drf_log_writer.files import log_file_paths, search_records
from drf_log_writer.models import RequestLog
from drf_log_writer.search import filter_queryset, parse_query


class Command(BaseCommand):
    help = (
        "Print matching request logs as JSON lines, newest first. "
        "Query example: 'request.method=POST response.status_code>=500 request.path~orders'"
    )

    def add_arguments(self, parser):
        parser.add_argument("query", nargs="?", default="")
        parser.add_argument("--source", choices=["database", "file"])
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, query, source, limit, **options):
        config = get_config()
        source = source or ("database" if "database" in config["BACKENDS"] else "file")
        conditions = parse_query(query, config)
        if source == "database":
            records = (log.data for log in filter_queryset(RequestLog.objects.all(), conditions)[:limit])
        else:
            records, _ = search_records(log_file_paths(config), conditions, limit=limit)
        for record in records:
            self.stdout.write(json.dumps(record, ensure_ascii=False, default=str))
