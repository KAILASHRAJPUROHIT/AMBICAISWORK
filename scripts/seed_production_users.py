"""Create or update a tenant user without hardcoded identities or passwords.

Example:
    python scripts/seed_production_users.py demo-business OWNER-01 \
        --name "Demo Owner" --email owner@example.com --role OWNER
"""
from argparse import ArgumentParser
from getpass import getpass
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.auth_service import hash_password
from backend.business_registry import load_profile
from backend.database import get_session_factory
from backend.models import User


def parse_args():
    parser = ArgumentParser(description="Create/update one Payment Auditor tenant user")
    parser.add_argument("tenant_slug")
    parser.add_argument("employee_id")
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument(
        "--role",
        choices=["ADMIN", "OWNER", "ACCOUNTANT", "DEVELOPER", "STAFF", "VIEWER"],
        default="OWNER",
    )
    parser.add_argument("--security-email")
    parser.add_argument("--force-reset", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if not load_profile(args.tenant_slug):
        raise SystemExit(f"Unknown tenant slug: {args.tenant_slug}")

    password = getpass("New password (minimum 12 characters): ")
    confirm = getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match")
    if len(password) < 12:
        raise SystemExit("Password must be at least 12 characters")

    db = get_session_factory(args.tenant_slug)()
    try:
        user = db.query(User).filter(User.employee_id == args.employee_id).first()
        if not user:
            user = User(employee_id=args.employee_id, name=args.name, role=args.role)
            db.add(user)
        user.name = args.name
        user.email = args.email
        user.security_email = args.security_email
        user.role = args.role
        user.hashed_password = hash_password(password)
        user.is_active = 1
        user.password_reset_required = args.force_reset
        db.commit()
        print(f"User {args.employee_id} saved for tenant {args.tenant_slug}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
