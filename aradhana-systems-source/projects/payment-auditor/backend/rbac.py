from enum import Enum
from typing import Set


class UserRole(Enum):
    ADMIN = "admin"
    OWNER = "owner"
    ACCOUNTANT = "accountant"
    DEVELOPER = "developer"
    STAFF = "staff"
    VIEWER = "viewer"


class Permission(Enum):
    VIEW_REVIEWS = "view_reviews"
    RESOLVE_REVIEWS = "resolve_reviews"
    VIEW_ESCALATIONS = "view_escalations"
    RESOLVE_ESCALATIONS = "resolve_escalations"
    VIEW_REPORTS = "view_reports"
    GENERATE_REPORTS = "generate_reports"
    MANAGE_USERS = "manage_users"
    VIEW_SECURITY_STATS = "view_security_stats"
    EMERGENCY_CONTROLS = "emergency_controls"
    ACCESS_MASTER_CONSOLE = "access_master_console"
    VIEW_AUDIT_LOGS = "view_audit_logs"
    SYSTEM_DIAGNOSTICS = "system_diagnostics"
    MAINTENANCE_MODE = "maintenance_mode"
    DEBUG_ACCESS = "debug_access"


_ROLE_PERMISSIONS = {
    UserRole.DEVELOPER: {
        Permission.VIEW_AUDIT_LOGS,
        Permission.SYSTEM_DIAGNOSTICS,
        Permission.MAINTENANCE_MODE,
        Permission.DEBUG_ACCESS,
        Permission.EMERGENCY_CONTROLS, # Service restart, force sync
    },
    UserRole.ACCOUNTANT: {
        Permission.VIEW_REVIEWS,
        Permission.RESOLVE_REVIEWS,
        Permission.VIEW_REPORTS,
        Permission.VIEW_AUDIT_LOGS,
    },
    UserRole.OWNER: {
        Permission.VIEW_REVIEWS,
        Permission.RESOLVE_REVIEWS,
        Permission.VIEW_ESCALATIONS,
        Permission.RESOLVE_ESCALATIONS,
        Permission.VIEW_REPORTS,
        Permission.GENERATE_REPORTS,
        Permission.MANAGE_USERS,
        Permission.VIEW_SECURITY_STATS,
        Permission.EMERGENCY_CONTROLS,
        Permission.ACCESS_MASTER_CONSOLE,
        Permission.VIEW_AUDIT_LOGS,
    },
    UserRole.ADMIN: {
        Permission.VIEW_REVIEWS,
        Permission.RESOLVE_REVIEWS,
        Permission.VIEW_ESCALATIONS,
        Permission.RESOLVE_ESCALATIONS,
        Permission.VIEW_REPORTS,
        Permission.GENERATE_REPORTS,
        Permission.MANAGE_USERS,
        Permission.VIEW_SECURITY_STATS,
        Permission.EMERGENCY_CONTROLS,
        Permission.ACCESS_MASTER_CONSOLE,
        Permission.VIEW_AUDIT_LOGS,
    },
}


def get_permissions(role: "str | UserRole") -> Set[Permission]:
    """
    Returns the set of permissions for a given user role.

    Accepts either a ``UserRole`` enum member or a role string (case-insensitive).
    Returns an empty set for unknown roles.
    """
    try:
        if isinstance(role, UserRole):
            resolved = role
        else:
            resolved = UserRole(str(role).lower())
        return _ROLE_PERMISSIONS.get(resolved, set())
    except (ValueError, AttributeError):
        return set()


def has_permission(role: "str | UserRole", permission: Permission) -> bool:
    """
    Checks if a given role (enum or string) has a specific permission.
    """
    return permission in get_permissions(role)
