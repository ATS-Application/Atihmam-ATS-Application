# run: python insert_profile.py
import httpx

SUPABASE_URL = "https://nflmcuktfosaketloomh.supabase.co"
SERVICE_ROLE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5mbG1jdWt0Zm9zYWtldGxvb21oIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MDk5NTU2NSwiZXhwIjoyMDk2NTcxNTY1fQ.ypTVwT8sS08PgkOYuDe5shkzWMzUJzzV3iABbtC5sSg"

r = httpx.post(
    f"{SUPABASE_URL}/rest/v1/profiles",
    headers={
        "apikey": SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    },
    json={
        "id": "33bd623b-4714-4ace-970e-fe1fbd71560b",
        "email": "contact@atihmam.com",
        "full_name": "Contact Atihmam",
        "role": "admin",
    },
)
print(r.status_code, r.text)