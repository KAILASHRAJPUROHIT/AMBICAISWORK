import pytest
from enum import Enum
from backend.rbac import UserRole, Permission, get_permissions, has_permission


def test_accountant_permissions():
    # Current model: accountant can review and view reports/audit logs,
    # but cannot touch escalations, generate reports, or manage users.
    permissions = get_permissions(UserRole.ACCOUNTANT)
    assert Permission.VIEW_REVIEWS in permissions
    assert Permission.RESOLVE_REVIEWS in permissions
    assert Permission.VIEW_REPORTS in permissions
    assert Permission.VIEW_ESCALATIONS not in permissions
    assert Permission.RESOLVE_ESCALATIONS not in permissions
    assert Permission.GENERATE_REPORTS not in permissions
    assert Permission.MANAGE_USERS not in permissions


def test_owner_permissions():
    # Current model: owner is the shop proprietor / superuser and holds the
    # full operational permission set (reviews, escalations, reports, user mgmt).
    permissions = get_permissions(UserRole.OWNER)
    assert Permission.VIEW_REVIEWS in permissions
    assert Permission.RESOLVE_REVIEWS in permissions
    assert Permission.VIEW_ESCALATIONS in permissions
    assert Permission.RESOLVE_ESCALATIONS in permissions
    assert Permission.VIEW_REPORTS in permissions
    assert Permission.GENERATE_REPORTS in permissions
    assert Permission.MANAGE_USERS in permissions


def test_admin_permissions():
    permissions = get_permissions(UserRole.ADMIN)
    assert Permission.VIEW_REVIEWS in permissions
    assert Permission.RESOLVE_REVIEWS in permissions
    assert Permission.VIEW_ESCALATIONS in permissions
    assert Permission.RESOLVE_ESCALATIONS in permissions
    assert Permission.VIEW_REPORTS in permissions
    assert Permission.GENERATE_REPORTS in permissions
    assert Permission.MANAGE_USERS in permissions


def test_has_permission():
    # Accountant
    assert has_permission(UserRole.ACCOUNTANT, Permission.VIEW_REVIEWS)
    assert not has_permission(UserRole.ACCOUNTANT, Permission.VIEW_ESCALATIONS)

    # Owner (superuser — holds escalation and user-management permissions)
    assert has_permission(UserRole.OWNER, Permission.VIEW_ESCALATIONS)
    assert has_permission(UserRole.OWNER, Permission.MANAGE_USERS)

    # Admin
    assert has_permission(UserRole.ADMIN, Permission.GENERATE_REPORTS)
    assert has_permission(UserRole.ADMIN, Permission.MANAGE_USERS)


def test_invalid_role_handling():
    class InvalidRole(Enum):
        UNKNOWN = "unknown"

    permissions = get_permissions(InvalidRole.UNKNOWN)
    assert len(permissions) == 0
    assert not has_permission(InvalidRole.UNKNOWN, Permission.VIEW_REVIEWS)
