from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestDriveWebhook:

    def test_sync_ping_acknowledged(self):
        response = client.post(
            "/api/v1/ingestion/drive/webhook",
            headers={
                "x-goog-channel-id": "test-channel",
                "x-goog-resource-state": "sync",
                "x-goog-resource-id": "resource-id",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "acknowledged"

    def test_irrelevant_state_ignored(self):
        response = client.post(
            "/api/v1/ingestion/drive/webhook",
            headers={
                "x-goog-channel-id": "test-channel",
                "x-goog-resource-state": "remove",
                "x-goog-resource-id": "resource-id",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"

    @patch("app.api.v1.ingestion.sync_drive_folder")
    def test_add_event_queues_sync(self, mock_sync):
        mock_sync.delay = MagicMock()
        response = client.post(
            "/api/v1/ingestion/drive/webhook",
            headers={
                "x-goog-channel-id": "test-channel",
                "x-goog-resource-state": "add",
                "x-goog-resource-id": "file-resource-id",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "queued"
        mock_sync.delay.assert_called_once()

    def test_missing_resource_id_ignored(self):
        response = client.post(
            "/api/v1/ingestion/drive/webhook",
            headers={
                "x-goog-channel-id": "test-channel",
                "x-goog-resource-state": "add",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"