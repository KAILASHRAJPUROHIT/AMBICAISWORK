"""Small database-independent routes.

Tenant financial routes live in review_api.py where they can use the
request-scoped get_db dependency. This router intentionally contains no mock
review, escalation, or report data.
"""
from fastapi import APIRouter, HTTPException

from backend.rbac import UserRole, get_permissions


router = APIRouter()


@router.get("/health")
def health():
    return {"status": "healthy"}


@router.get("/permissions/{role}")
def get_role_permissions(role: str):
    try:
        user_role = UserRole[role.upper()]
    except KeyError:
        raise HTTPException(status_code=404, detail="Role not found")

    permissions = get_permissions(user_role)
    return {"role": user_role.value, "permissions": [p.value for p in permissions]}
