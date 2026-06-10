# run: python check_token.py
import httpx
from jose import jwt

SERVICE_ROLE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5mbG1jdWt0Zm9zYWtldGxvb21oIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MDk5NTU2NSwiZXhwIjoyMDk2NTcxNTY1fQ.ypTVwT8sS08PgkOYuDe5shkzWMzUJzzV3iABbtC5sSg"
SUPABASE_URL = "https://nflmcuktfosaketloomh.supabase.co"
API_URL = "https://atihmam-ats-application.onrender.com"

# 1. Login via ton backend
r = httpx.post(f"{API_URL}/api/v1/auth/login", json={
    "email": "contact@atihmam.com",
    "password": "TON_MOT_DE_PASSE",  # <-- remplace
})
print("Login status:", r.status_code)
token = r.json().get("access_token")
print("Token preview:", token[:40] if token else "NO TOKEN")

# 2. Decode sans vérifier la signature — voir les claims
if token:
    payload = jwt.decode(token, options={"verify_signature": False})
    print("Token payload:", payload)

# 3. Test GET /candidates avec ce token
r2 = httpx.get(f"{API_URL}/api/v1/candidates", headers={
    "Authorization": f"Bearer {token}"
})
print("Candidates status:", r2.status_code, r2.text[:200])