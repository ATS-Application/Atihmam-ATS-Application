from app.services.drive_service import _get_drive_service
svc = _get_drive_service()
resp = svc.files().list(
    q="mimeType='application/pdf' and trashed=false",
    fields="files(id, name, parents)",
    pageSize=10
).execute()
files = resp.get("files", [])
print("Total PDFs visible:", len(files))
for f in files:
    print(" -", f["name"], "| parents:", f.get("parents"))
