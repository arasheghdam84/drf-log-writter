import json

import pytest


@pytest.fixture
def file_backend(settings, tmp_path):
    path = tmp_path / "requests.log"
    settings.DRF_LOG_WRITER = {"BACKENDS": ["file"], "FILE_PATH": str(path)}
    return path


@pytest.fixture
def read_file_records():
    def read(path):
        return [json.loads(line) for line in path.read_text().splitlines()]

    return read


@pytest.fixture
def login(client):
    def post(username="john", password="hunter2"):
        return client.post(
            "/api/login/?next=/home",
            data={"username": username, "password": password},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer abc",
        )

    return post
