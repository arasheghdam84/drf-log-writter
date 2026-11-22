import json

import pytest
from django.core.management import call_command

from drf_log_writer.models import RequestLog

pytestmark = pytest.mark.django_db

CHANGELIST = "/admin/drf_log_writer/requestlog/"
FILE_CHANGELIST = "/admin/drf_log_writer/requestlogfile/"


@pytest.fixture
def admin_session(client, admin_user):
    client.force_login(admin_user)
    return client


def test_changelist_search_and_custom_json_columns(admin_session, login):
    login(username="john")
    login(username="jane")

    response = admin_session.get(CHANGELIST, {"columns": "request.body.username, response.status_code"})
    assert response.status_code == 302

    response = admin_session.get(CHANGELIST, {"q": "request.body.username=jane", "o": "1"})
    assert response.status_code == 200
    content = response.content.decode()
    assert "request.body.username" in content
    assert "jane" in content and "john" not in content


def test_detail_page_shows_pretty_json(admin_session, login):
    login()
    log = RequestLog.objects.get()

    response = admin_session.get(f"{CHANGELIST}{log.pk}/change/")
    assert response.status_code == 200
    assert "&quot;username&quot;: &quot;john&quot;" in response.content.decode()


def test_file_viewer_lists_searches_and_paginates(settings, file_backend, admin_session, login):
    settings.DRF_LOG_WRITER = {**settings.DRF_LOG_WRITER, "ADMIN_PAGE_SIZE": 1}
    login(username="john")
    login(username="jane")

    newest = admin_session.get(FILE_CHANGELIST, {"columns": "request.body.username"}, follow=True)
    assert newest.status_code == 200
    assert newest.context["rows"][0]["cells"] == ["jane"]
    assert newest.context["next_url"]

    searched = admin_session.get(FILE_CHANGELIST, {"q": "request.body.username=john"})
    assert [row["cells"] for row in searched.context["rows"]] == [["john"]]


def test_file_viewer_hidden_when_file_backend_disabled(admin_session):
    assert admin_session.get(FILE_CHANGELIST).status_code == 403


def test_search_command_reads_files(file_backend, login, capsys):
    login(username="john")
    login(username="jane")

    call_command("search_request_logs", "request.body.username=john", source="file")

    lines = capsys.readouterr().out.splitlines()
    assert [json.loads(line)["request"]["body"]["username"] for line in lines] == ["john"]
