from enum import Enum
from typing import Set


class UserRole(Enum):
    ACCOUNTANT = "accountant"
    OWNER = "owner"
    ADMIN = "admin"


class Permission(Enum):
    VIEW_REVIEWS = "view_reviews"
    RESOLVE_REVIEWS = "resolve_reviews"
    VIEW_ESCALATIONS = "view_escalations"
    RESOLVE_ESCALATIONS = "resolve_escalations"
    VIEW_REPORTS = "view_reports"
    GENERATE_REPORTS = "generate_reports"
    MANAGE_USERS = "manage_users"


_ROLE_PERMISSIONS = {
    UserRole.ACCOUNTANT: {
        Permission.VIEW_REVIEWS,
        Permission.RESOLVE_REVIEWS,
    },
    UserRole.OWNER: {
        Permission.VIEW_ESCALATIONS,
        Permission.RESOLVE_ESCALATIONS,
        Permission.VIEW_REPORTS,
    },
    UserRole.ADMIN: {
        Permission.VIEW_REVIEWS,
        Permission.RESOLVE_REVIEWS,
        Permission.VIEW_ESCALATIONS,
        Permission.RESOLVE_ESCALATIONS,
        Permission.VIEW_REPORTS,
        Permission.GENERATE_REPORTS,
        Permission.MANAGE_USERS,
    },
}


def get_permissions(role: UserRole) -> Set[Permission]:
    """
    Returns the set of permissions for a given user role.
    """
    return _ROLE_PERMISSIONS.get(role, set())


def has_permission(role: UserRole, permission: Permission) -> bool:
    """
    Checks if a given role has a specific permission.
    """
    return permission in get_permissions(role)
