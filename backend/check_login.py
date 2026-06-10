# run: python check_login.py
from supabase import create_client

SUPABASE_URL = "https://nflmcuktfosaketloomh.supabase.co"
SERVICE_ROLE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5mbG1jdWt0Zm9zYWtldGxvb21oIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MDk5NTU2NSwiZXhwIjoyMDk2NTcxNTY1fQ.ypTVwT8sS08PgkOYuDe5shkzWMzUJzzV3iABbtC5sSg"

supabase = create_client(SUPABASE_URL, SERVICE_ROLE_KEY)

try:
    r = supabase.auth.sign_in_with_password({
        "email": "contact@atihmam.com",
        "password": "Password123",  # <-- remplace
    })
    print("✅ Login OK:", r.user.email)
except Exception as e:
    print("❌ Login failed:", e)