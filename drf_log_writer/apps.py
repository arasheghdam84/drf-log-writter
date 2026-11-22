from django.apps import AppConfig


class DrfLogWriterConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "drf_log_writer"
    verbose_name = "Request logs"
