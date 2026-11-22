import pytest

from drf_log_writer.models import RequestLog
from drf_log_writer.search import filter_queryset, matches, parse_query

pytestmark = pytest.mark.django_db


@pytest.fixture
def logs(client, login):
    client.raise_request_exception = False
    login(username="john")
    login(username="jane", password="other")
    client.get("/plain/?page=2")
    client.get("/boom/")
    return list(RequestLog.objects.order_by("created_at"))


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("request.method=POST", [0, 1]),
        ("request.body.username=jane", [1]),
        ("request.body.password=hunter2", [0]),  # hashed before comparing
        ("response.status_code>=500", [3]),
        ("response.status_code=200 request.path~plain", [2]),
        ("response.status_code!=200", [3]),
        ("request.query_params.page=2", [2]),
        ("request.body.username!=john", [1, 2, 3]),
        ("ValueError", [3]),
        ('request.body.username="jane"', [1]),
    ],
)
def test_database_and_file_search_agree(logs, query, expected):
    conditions = parse_query(query)
    in_db = set(filter_queryset(RequestLog.objects.all(), conditions).values_list("id", flat=True))
    in_python = {log.id for log in logs if matches(log.data, conditions)}

    assert in_db == in_python == {logs[i].id for i in expected}
