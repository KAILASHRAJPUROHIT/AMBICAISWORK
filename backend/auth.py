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
