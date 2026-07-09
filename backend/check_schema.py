import os
import sys
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

client = create_client(url, key)

try:
    cand_resp = client.table("candidates").select("id, job_id, domain, processing_status").execute()
    data = cand_resp.data or []
    print(f"Total candidates: {len(data)}")
    null_job = [c for c in data if c.get("job_id") is None]
    not_null_job = [c for c in data if c.get("job_id") is not None]
    print(f"Candidates with null job_id: {len(null_job)}")
    print(f"Candidates with non-null job_id: {len(not_null_job)}")
    
    domains = {}
    for c in data:
        dom = c.get("domain")
        domains[dom] = domains.get(dom, 0) + 1
    print("Candidates by domain:", domains)
except Exception as e:
    print("Error:", e)
