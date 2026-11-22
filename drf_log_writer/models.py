import uuid

from django.db import models
from django.utils.dateparse import parse_datetime


class RequestLog(models.Model):
    """The full record lives in ``data``; the other columns are denormalized copies for indexed filtering."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(db_index=True)
    method = models.CharField(max_length=10, db_index=True)
    path = models.CharField(max_length=2048)
    status_code = models.PositiveSmallIntegerField(null=True, db_index=True)
    duration_ms = models.FloatField()
    username = models.CharField(max_length=150, blank=True, db_index=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    data = models.JSONField()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "request log"

    def __str__(self):
        return f"{self.method} {self.path} {self.status_code}"

    @classmethod
    def from_record(cls, record: dict) -> "RequestLog":
        request, response = record["request"], record["response"]
        user = request.get("user") or {}
        return cls(
            id=record["id"],
            created_at=parse_datetime(record["timestamp"]),
            method=request["method"],
            path=request["path"][:2048],
            status_code=response["status_code"],
            duration_ms=record["duration_ms"],
            username=str(user.get("username") or "")[:150],
            ip=request.get("ip"),
            data=record,
        )


class RequestLogFile(models.Model):
    """Table-less model so the file log viewer gets an admin entry and a view permission."""

    class Meta:
        managed = False
        default_permissions = ("view",)
        verbose_name = "request log file"
