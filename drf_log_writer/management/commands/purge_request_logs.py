from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from drf_log_writer.models import RequestLog


class Command(BaseCommand):
    help = "Delete database request logs older than N days. File logs are bounded by rotation instead."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, required=True)

    def handle(self, *args, days, **options):
        cutoff = timezone.now() - timedelta(days=days)
        deleted, _ = RequestLog.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(f"Deleted {deleted} request logs older than {days} days.")
