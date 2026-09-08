from datetime import datetime, timedelta
import pytest
from backend.auth import create_user, authenticate_user, create_session, validate_session, UserAccount, AuthSession, _USER_STORE
from backend.rbac import UserRole
from uuid import UUID


# Clear the in-memory user store before each test
@pytest.fixture(autouse=True)
def clear_user_store():
    _USER_STORE.clear()


def test_create_user():
    user = create_user("testuser", UserRole.ACCOUNTANT)
    assert isinstance(user, UserAccount)
    assert user.username == "testuser"
    assert user.role == UserRole.ACCOUNTANT
    assert user.is_active is True
    assert isinstance(user.user_id, UUID)
    assert _USER_STORE["testuser"] == user


def test_authenticate_active_user():
    create_user("activeuser", UserRole.OWNER, is_active=True)
    user = authenticate_user("activeuser")
    assert user is not None
    assert user.username == "activeuser"


def test_reject_inactive_user():
    create_user("inactiveuser", UserRole.ACCOUNTANT, is_active=False)
    user = authenticate_user("inactiveuser")
    assert user is None


def test_authenticate_non_existent_user():
    user = authenticate_user("nonexistent")
    assert user is None


def test_create_session():
    user = create_user("sessionuser", UserRole.ADMIN)
    session = create_session(user)
    assert isinstance(session, AuthSession)
    assert isinstance(session.session_id, UUID)
    assert session.user_id == user.user_id
    assert session.created_at <= datetime.now()
    assert session.expires_at > datetime.now()


def test_validate_session():
    user = create_user("validuser", UserRole.OWNER)
    session = create_session(user)
    assert validate_session(session)


def test_expired_session_invalid():
    user = create_user("expireduser", UserRole.ACCOUNTANT)
    session = create_session(user)
    
    # Manually expire the session for testing
    session.expires_at = datetime.now() - timedelta(seconds=1)
    
    assert not validate_session(session)

