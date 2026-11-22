import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from drf_log_writer.models import RequestLog

pytestmark = pytest.mark.django_db


def test_drf_request_is_logged_to_database_with_hashed_keys(login):
    login()

    log = RequestLog.objects.get()
    request, response = log.data["request"], log.data["response"]
    assert (log.method, log.path, log.status_code) == ("POST", "/api/login/", 200)
    assert request["body"]["username"] == "john"
    assert request["query_params"] == {"next": "/home"}
    assert request["body"]["password"].startswith("hashed$")
    assert request["headers"]["Authorization"].startswith("hashed$")
    assert response["body"]["token"].startswith("hashed$")
    assert "hunter2" not in str(log.data) and "issued-token" not in str(log.data)


def test_file_backend_writes_json_lines_only(file_backend, read_file_records, login):
    login()
    login(username="jane")

    records = read_file_records(file_backend)
    assert [r["request"]["body"]["username"] for r in records] == ["john", "jane"]
    assert not RequestLog.objects.exists()


def test_both_backends_receive_the_same_record(settings, file_backend, read_file_records, login):
    settings.DRF_LOG_WRITER = {**settings.DRF_LOG_WRITER, "BACKENDS": ["database", "file"]}
    login()

    assert RequestLog.objects.get().data == read_file_records(file_backend)[0]


def test_skipped_paths_and_methods_are_not_logged(settings, client, login):
    client.get("/admin/login/")
    settings.DRF_LOG_WRITER = {"METHODS": ["GET"]}
    login()

    assert not RequestLog.objects.exists()


def test_exception_traceback_is_recorded(client):
    client.raise_request_exception = False
    client.get("/boom/")

    log = RequestLog.objects.get()
    assert log.status_code == 500
    assert "ValueError: boom" in log.data["exception"]


def test_multipart_logs_file_metadata_not_contents(client):
    upload = SimpleUploadedFile("cv.pdf", b"%PDF secret contents", content_type="application/pdf")
    response = client.post("/api/upload/", {"name": "john", "password": "x", "cv": upload})

    assert response.status_code == 201
    request = RequestLog.objects.get().data["request"]
    assert request["body"]["name"] == "john"
    assert request["body"]["password"].startswith("hashed$")
    assert request["files"] == {"cv": {"name": "cv.pdf", "size": 20, "content_type": "application/pdf"}}


def test_oversized_body_is_dropped_not_truncated(settings, login):
    settings.DRF_LOG_WRITER = {"MAX_BODY_LENGTH": 10}
    login()

    assert RequestLog.objects.get().data["request"]["body"].startswith("<truncated:")
