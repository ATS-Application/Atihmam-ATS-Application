# app/tests/test_candidates.py

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/")

    assert response.status_code == 200


def test_get_candidates():
    response = client.get("/api/candidates")

    # API should respond correctly
    assert response.status_code in [200, 401, 403]


def test_get_jobs():
    response = client.get("/api/jobs")

    assert response.status_code in [200, 401, 403]