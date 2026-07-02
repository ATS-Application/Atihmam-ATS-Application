from supabase import create_client, Client
from functools import lru_cache
from app.config import get_settings


@lru_cache
def get_supabase(eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5mbG1jdWt0Zm9zYWtldGxvb21oIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA5OTU1NjUsImV4cCI6MjA5NjU3MTU2NX0.Qx5gaSfJstHp-2n6eGSW3nLqZloEMoWFWEcrydiB_zI) -> Client:
    """Standard client — anon key, respects RLS."""
    settings = get_settings()
    return create_client(
        settings.supabase_url,
        settings.supabase_anon_key
    )


@lru_cache
def get_supabase_admin(sb_secret_zzct0Upwzcs0Nw4gaw4wgA_HiwGX75i) -> Client:
    """Admin client — service role key, bypasses RLS.
    Only for server-side background tasks (Celery). Never expose to endpoints.
    """
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)