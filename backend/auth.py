from fastapi import Header, HTTPException, status, Depends
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel
from backend.rbac import UserRole # Assuming UserRole is defined here


class UserAccount(BaseModel):
    user_id: UUID
    username: str
    role: UserRole
    is_active: bool


class AuthSession(BaseModel):
    session_id: UUID
    user_id: UUID
    created_at: datetime
    expires_at: datetime


# Simplified in-memory "user store" for deterministic behavior without a DB
_USER_STORE: dict[str, UserAccount] = {}


def create_user(username: str, role: UserRole, is_active: bool = True) -> UserAccount:
    """
    Creates a new UserAccount object.
    """
    user_id = uuid4()
    user = UserAccount(user_id=user_id, username=username, role=role, is_active=is_active)
    _USER_STORE[username] = user  # Add to simplified store
    return user


def authenticate_user(username: str) -> Optional[UserAccount]:
    """
    Authenticates a user based on username.
    Returns the user if active and found, otherwise None.
    """
    user = _USER_STORE.get(username)
    if user and user.is_active:
        return user
    return None


def create_session(user: UserAccount) -> AuthSession:
    """
    Creates a deterministic session object for a given user.
    Session expires after a fixed duration (e.g., 1 hour).
    """
    session_id = uuid4()
    created_at = datetime.now()
    expires_at = created_at + timedelta(hours=1)
    return AuthSession(
        session_id=session_id,
        user_id=user.user_id,
        created_at=created_at,
        expires_at=expires_at,
    )


def validate_session(session: AuthSession) -> bool:
    """
    Validates if a session is still active and not expired.
    """
    return datetime.now() < session.expires_at


def get_current_role(x_user_role: Optional[str] = Header(None)) -> UserRole:
    """
    Dependency to get the current role from X-User-Role header.
    Defaults to ACCOUNTANT if no header is provided for backwards compatibility if needed, 
    but for hardening we should probably require it or handle it.
    The prompt says "Return 403 when role lacks permission."
    """
    if not x_user_role:
        # If no role is provided, we can't authorize mutation.
        # However, we might want a default or just fail.
        # Let's fail for mutations.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="X-User-Role header missing"
        )
    
    try:
        return UserRole[x_user_role.upper()]
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid role"
        )


def require_admin(role: UserRole = Depends(get_current_role)) -> UserRole:
    if role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return role


def require_admin_or_owner(role: UserRole = Depends(get_current_role)) -> UserRole:
    if role not in [UserRole.ADMIN, UserRole.OWNER]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or Owner access required")
    return role


def require_admin_or_accountant(role: UserRole = Depends(get_current_role)) -> UserRole:
    if role not in [UserRole.ADMIN, UserRole.ACCOUNTANT]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or Accountant access required")
    return role
