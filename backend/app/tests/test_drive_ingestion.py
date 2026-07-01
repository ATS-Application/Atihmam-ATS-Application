from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.tasks.drive_sync import sync_drive_folder, sync_drive_webhook

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

    @patch("app.tasks.drive_sync.list_pdf_files")
    @patch("app.tasks.drive_sync.get_supabase_admin")
    @patch("app.tasks.drive_sync.get_settings")
    def test_sync_drive_folder_uses_drive_root_when_not_configured(
        self,
        mock_get_settings,
        mock_supabase_admin,
        mock_list_pdf_files,
    ):
        mock_get_settings.return_value = MagicMock(drive_folder_id="")
        mock_list_pdf_files.return_value = []

        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])
        mock_supabase_admin.return_value = mock_supabase

        result = sync_drive_folder()

        assert result["status"] == "done"
        mock_list_pdf_files.assert_called_once_with("root")

    @patch("app.tasks.drive_sync.sync_drive_folder")
    @patch("app.tasks.drive_sync.get_start_page_token")
    @patch("app.tasks.drive_sync.get_settings")
    @patch("app.tasks.drive_sync.get_supabase_admin")
    def test_sync_webhook_runs_initial_full_sync_and_stores_page_token(
        self,
        mock_supabase_admin,
        mock_get_settings,
        mock_get_start_page_token,
        mock_sync_drive_folder,
    ):
        mock_get_settings.return_value = MagicMock(drive_folder_id="folder-123")
        mock_get_start_page_token.return_value = "page-token-1"
        mock_sync_drive_folder.return_value = {
            "status": "done",
            "total_files": 3,
            "queued": 3,
            "errors": 0,
        }

        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=None)
        mock_table.upsert.return_value = mock_table
        mock_supabase_admin.return_value = mock_supabase

        result = sync_drive_webhook()

        assert result["status"] == "initialized"
        assert result["reason"] == "initial_full_sync_completed"
        mock_sync_drive_folder.assert_called_once_with(None)
        mock_get_start_page_token.assert_called_once()
        mock_table.upsert.assert_called_once_with(
            {"key": "drive_page_token", "value": "page-token-1"}
        )