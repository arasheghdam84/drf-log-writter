import json

import django
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models.fields.json import KeyTransform
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.utils.html import format_html

from .conf import get_config
from .files import log_file_paths, search_records
from .models import RequestLog, RequestLogFile
from .search import filter_queryset, parse_query
from .utils import format_cell, get_by_path, parse_columns

COLUMNS_SESSION_KEY = "drf_log_writer_columns"
COLUMN_PREFIX = "json__"

# Columns backed by a real model field use it directly, so they sort on an indexed column.
FIELD_COLUMNS = {
    "timestamp": "created_at",
    "request.method": "method",
    "request.path": "path",
    "response.status_code": "status_code",
    "duration_ms": "duration_ms",
    "request.user.username": "username",
    "request.ip": "ip",
}

SEARCH_HELP = (
    "Search: request.method=POST · response.status_code>=500 · request.path~orders · "
    "request.body.password=secret (hashed automatically) · free text"
)


class JsonColumnsMixin:
    """Lets admins pick which JSON paths are shown as columns; the choice is kept in the session."""

    def get_log_columns(self, request) -> list[str]:
        return request.session.get(COLUMNS_SESSION_KEY) or get_config()["ADMIN_COLUMNS"]

    def update_columns_from_query(self, request):
        """Stores ?columns=... and redirects without it (the changelist rejects unknown GET params)."""
        if "columns" not in request.GET:
            return None
        columns = parse_columns(request.GET["columns"])
        if columns:
            request.session[COLUMNS_SESSION_KEY] = columns
        else:
            request.session.pop(COLUMNS_SESSION_KEY, None)
        params = request.GET.copy()
        del params["columns"]
        return HttpResponseRedirect(f"{request.path}?{params.urlencode()}" if params else request.path)

    def columns_context(self, request) -> dict:
        return {
            "log_columns": ", ".join(self.get_log_columns(request)),
            "preserved_params": [
                (key, value) for key, values in request.GET.lists() if key != "columns" for value in values
            ],
            "search_help": SEARCH_HELP,
        }


@admin.register(RequestLog)
class RequestLogAdmin(JsonColumnsMixin, admin.ModelAdmin):
    change_list_template = "admin/drf_log_writer/requestlog/change_list.html"
    list_filter = ("method", "status_code", "created_at")
    date_hierarchy = "created_at"
    search_fields = ("path",)  # enables the search box; matching is done by get_search_results
    fields = ("created_at", "method", "path", "status_code", "duration_ms", "username", "ip", "pretty_data")
    readonly_fields = fields
    show_full_result_count = False

    def __getattr__(self, name):
        # Resolves list_display entries like "json__request__body__email" into a column callable.
        if not name.startswith(COLUMN_PREFIX):
            raise AttributeError(name)
        path = name[len(COLUMN_PREFIX) :].replace("__", ".")

        def column(obj):
            return format_cell(get_by_path(obj.data, path))

        return admin.display(description=path, ordering=_json_ordering(path))(column)

    def get_list_display(self, request):
        return [
            FIELD_COLUMNS.get(path) or COLUMN_PREFIX + path.replace(".", "__")
            for path in self.get_log_columns(request)
        ]

    def changelist_view(self, request, extra_context=None):
        redirect = self.update_columns_from_query(request)
        if redirect:
            return redirect
        return super().changelist_view(request, {**self.columns_context(request), **(extra_context or {})})

    def get_search_results(self, request, queryset, search_term):
        return filter_queryset(queryset, parse_query(search_term)), False

    @admin.display(description="data")
    def pretty_data(self, obj):
        return format_html(
            '<pre style="white-space: pre-wrap; overflow-wrap: anywhere">{}</pre>',
            json.dumps(obj.data, indent=2, ensure_ascii=False),
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(RequestLogFile)
class RequestLogFileAdmin(JsonColumnsMixin, admin.ModelAdmin):
    def has_view_permission(self, request, obj=None):
        return "file" in get_config()["BACKENDS"] and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        from django.urls import path

        view = self.admin_site.admin_view(self.changelist_view)
        return [path("", view, name=f"{self.opts.app_label}_{self.opts.model_name}_changelist")]

    def changelist_view(self, request, extra_context=None):
        if not self.has_view_permission(request):
            raise PermissionDenied
        redirect = self.update_columns_from_query(request)
        if redirect:
            return redirect

        config = get_config()
        files = log_file_paths(config)
        selected = request.GET.get("file", "")
        # Only offer files we discovered ourselves; never open a path taken from the query string.
        paths = [f for f in files if f.name == selected] or files
        query = request.GET.get("q", "")
        page_size = config["ADMIN_PAGE_SIZE"]
        page = _positive_int(request.GET.get("p"), 1)
        conditions = parse_query(query, config)
        records, has_next = search_records(paths, conditions, (page - 1) * page_size, page_size)

        columns = self.get_log_columns(request)
        params = request.GET.copy()
        context = {
            **self.admin_site.each_context(request),
            **self.columns_context(request),
            "title": "Request log files",
            "opts": self.opts,
            # Django 6 switched breadcrumbs from <div> to <ol>, and the admin CSS targets only one of them.
            "ol_breadcrumbs": django.VERSION >= (6, 0),
            "files": [f.name for f in files],
            "selected_file": selected,
            "query": query,
            "columns": columns,
            "rows": [
                {
                    "cells": [format_cell(get_by_path(record, c)) for c in columns],
                    "json": json.dumps(record, indent=2, ensure_ascii=False),
                }
                for record in records
            ],
            "page": page,
            "previous_url": _page_url(params, page - 1) if page > 1 else None,
            "next_url": _page_url(params, page + 1) if has_next else None,
            **(extra_context or {}),
        }
        return TemplateResponse(request, "admin/drf_log_writer/requestlogfile/change_list.html", context)


def _json_ordering(path: str):
    expression = "data"
    for key in path.split("."):
        expression = KeyTransform(key, expression)
    return expression


def _positive_int(value, default: int) -> int:
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return default


def _page_url(params, page: int) -> str:
    params = params.copy()
    params["p"] = page
    return f"?{params.urlencode()}"
