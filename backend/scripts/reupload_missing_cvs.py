# scripts/reupload_missing_cvs.py
from app.db.supabase_client import get_supabase_admin
from app.services.drive_service import download_file_bytes
from app.tasks.drive_sync import upload_cv_to_storage, sanitize_filename
from app.services.drive_service import get_file_metadata

supabase = get_supabase_admin()

rows = (
    supabase.table("candidates")
    .select("id, drive_file_id, cv_file_url")
    .is_("cv_file_url", "null")
    .not_.is_("drive_file_id", "null")
    .execute()
    .data or []
)

print(f"Re-uploading {len(rows)} CVs...")

for row in rows:
    try:
        drive_file_id = row["drive_file_id"]
        metadata = get_file_metadata(drive_file_id)
        file_name = sanitize_filename(metadata.get("name", f"{drive_file_id}.pdf"))
        pdf_bytes = download_file_bytes(drive_file_id)
        cv_url = upload_cv_to_storage(supabase, drive_file_id, file_name, pdf_bytes)
        supabase.table("candidates").update({"cv_file_url": cv_url}).eq("id", row["id"]).execute()
        print(f"✓ {file_name}")
    except Exception as e:
        print(f"✗ {row['drive_file_id']}: {e}")

print("Done.")