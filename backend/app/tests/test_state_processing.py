import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
from app.tasks.ai_processing import unlock_stuck_candidates, schedule_quota_retries
from app.tasks.cv_processing import process_cv

def test_unlock_stuck_candidates():
    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.lt.return_value = mock_table
    
    # 1. Setup mock data returned from select query
    mock_table.execute.return_value = MagicMock(data=[
        {"id": "cand-1", "locked_at": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()}
    ])
    
    mock_table.update.return_value = mock_table
    mock_table.in_.return_value = mock_table
    
    unlock_stuck_candidates(mock_supabase, timeout_minutes=10)
    
    # Verify that the update query was called to reset the status
    mock_supabase.table.assert_called_with("candidates")
    mock_table.update.assert_called_with({
        "processing_status": "queued",
        "locked_at": None,
        "processing_error": "Processing timed out (stuck in processing)."
    })
    mock_table.in_.assert_called_with("id", ["cand-1"])


def test_schedule_quota_retries():
    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.lt.return_value = mock_table
    
    # 1. Setup mock data returned from failed_quota check
    mock_table.execute.return_value = MagicMock(data=[
        {"id": "cand-2", "updated_at": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()}
    ])
    
    mock_table.update.return_value = mock_table
    mock_table.in_.return_value = mock_table
    
    schedule_quota_retries(mock_supabase, cooldown_minutes=5)
    
    # Verify that the update query was called to transition to retry_scheduled
    mock_table.update.assert_called_once()
    assert mock_table.update.call_args[0][0]["processing_status"] == "retry_scheduled"
    mock_table.in_.assert_called_with("id", ["cand-2"])


@patch("app.tasks.cv_processing.fetch_candidate")
@patch("app.tasks.cv_processing.update_candidate")
@patch("app.tasks.cv_processing.get_supabase_admin")
@patch("app.tasks.cv_processing.extract_text_safe")
@patch("app.tasks.cv_processing.extract_cv_info")
def test_process_cv_quota_failure(mock_extract_info, mock_extract_text, mock_supabase_admin, mock_update, mock_fetch):
    mock_fetch.return_value = {"id": "cand-3", "processing_status": "queued"}
    
    # Mock download function
    mock_supabase = MagicMock()
    mock_supabase_admin.return_value = mock_supabase
    mock_supabase.storage.from_().download.return_value = b"pdf-bytes"
    mock_extract_text.return_value = "raw cv text"
    
    # Simulate a 429 quota exception
    mock_extract_info.side_effect = Exception("API limit exceeded: 429 Too Many Requests")
    
    result = process_cv("cand-3", "drive/cv.pdf")
    
    assert result["success"] is False
    assert "429" in result["error"]
    
    # The last update should update the candidate to failed_quota status
    mock_update.assert_any_call(mock_supabase, "cand-3", {
        "processing_status": "failed_quota",
        "processing_error": "API limit exceeded: 429 Too Many Requests",
        "locked_at": None,
        "updated_at": mock_update.call_args_list[-1][0][2]["updated_at"] # Match updated_at dynamically
    })
