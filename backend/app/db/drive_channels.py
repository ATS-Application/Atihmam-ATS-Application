from app.db.supabase_client import get_supabase_admin


def save_channel(channel_id: str, resource_id: str, folder_id: str, expiration_ms: int) -> None:
    supabase = get_supabase_admin()
    supabase.table("drive_webhook_channels").upsert(
        {
            "channel_id": channel_id,
            "resource_id": resource_id,
            "folder_id": folder_id,
            "expiration_ms": expiration_ms,
        },
        on_conflict="channel_id",
    ).execute()


def get_active_channel(folder_id: str) -> dict | None:
    supabase = get_supabase_admin()
    response = (
        supabase.table("drive_webhook_channels")
        .select("*")
        .eq("folder_id", folder_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def delete_channel(channel_id: str) -> None:
    supabase = get_supabase_admin()
    supabase.table("drive_webhook_channels").delete().eq("channel_id", channel_id).execute()