import requests

# Assuming DEV-01 is owner or developer? Let's check DB.
from backend.database import SessionLocal
from backend.models import User
from backend.auth_service import create_user_session

db = SessionLocal()
owner = db.query(User).filter(User.role.in_(["OWNER", "ADMIN"])).first()
if not owner:
    print("No owner found")
    exit(1)

print(f"Testing as {owner.employee_id}")
token = create_user_session(db, owner.employee_id)
db.close()

headers = {"X-Session-Token": token}

endpoints = [
    "/api/admin/users",
    "/api/admin/security/stats",
    "/api/admin/system/mode",
    "/api/admin/financial/health"
]

for ep in endpoints:
    url = f"http://localhost:8000{ep}"
    res = requests.get(url, headers=headers)
    print(f"GET {ep} -> {res.status_code}")
    if res.status_code != 200:
        print(res.text)
