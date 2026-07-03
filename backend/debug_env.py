import os
from app.config import get_settings

print(f"Current Working Directory: {os.getcwd()}")
print(f".env File exists: {os.path.exists('.env')}")

try:
    get_settings.cache_clear()
    settings = get_settings()
    print(f"[OK] Supabase URL:       {'LOADED' if settings.supabase_url else 'EMPTY'}")
    print(f"[OK] Supabase Anon Key:  {'LOADED' if settings.supabase_anon_key else 'EMPTY'}")
    print(f"[OK] Service Role Key:   {'LOADED' if settings.supabase_service_role_key else 'EMPTY'}")
    print(f"[OK] Gemini API Key:     {'LOADED' if settings.gemini_api_key else 'EMPTY'}")
    print(f"[OK] DeepSeek Key:       {'LOADED' if settings.deepseek_api_key else 'EMPTY'}")
    print(f"[OK] Mistral Key:        {'LOADED' if settings.mistral_api_key else 'EMPTY'}")
    print(f"[OK] Drive Folder ID:    {settings.drive_folder_id or '(non defini)'}")
    print(f"[OK] Secret Key:         {'LOADED' if settings.secret_key != 'change-me' else 'DEFAULT (OK en dev)'}")
    print("\n[SUCCESS] Toutes les configurations ont ete chargees depuis .env")
except Exception as e:
    print(f"[ERROR] Chargement des parametres: {e}")