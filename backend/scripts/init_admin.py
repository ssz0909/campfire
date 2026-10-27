"""
Platform admin initialization script.

Usage:
    python -m scripts.init_admin
    or
    cd backend && .venv311/bin/python -m scripts.init_admin

Environment variables (or .env file):
    ADMIN_EMAIL     - admin account email (required)
    ADMIN_PASSWORD  - admin account password (required, min 8 chars)
    ADMIN_NAME      - admin display name (default: "Platform Admin")
    DATABASE_URL    - PostgreSQL connection string

The script is idempotent: running it twice on the same email promotes
an existing user to platform_admin without creating a duplicate.
"""
from __future__ import annotations

import os
import sys
import getpass
from pathlib import Path

# Allow running as `python -m scripts.init_admin` from backend/
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass


def main() -> None:
    email = os.getenv("ADMIN_EMAIL") or input("Admin email: ").strip()
    if not email:
        sys.exit("Error: email is required.")

    password = os.getenv("ADMIN_PASSWORD")
    if not password:
        password = getpass.getpass("Admin password (min 8 chars): ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            sys.exit("Error: passwords do not match.")
    if len(password) < 8:
        sys.exit("Error: password must be at least 8 characters.")

    full_name = os.getenv("ADMIN_NAME", "Platform Admin")

    # Import app modules after path is set up
    from app.database import SessionLocal
    from app.models.user import User
    from app.core.security import get_password_hash

    db = SessionLocal()
    try:
        existing: User | None = (
            db.query(User)
            .filter(User.email == email)
            .first()
        )

        if existing:
            if existing.is_platform_admin:
                print(f"User '{email}' is already a platform admin. Nothing changed.")
                return
            existing.is_platform_admin = True
            existing.is_active = True
            db.commit()
            print(f"Promoted existing user '{email}' to platform admin.")
        else:
            import uuid
            user = User(
                id=uuid.uuid4(),
                email=email,
                hashed_password=get_password_hash(password),
                full_name=full_name,
                is_active=True,
                is_platform_admin=True,
            )
            db.add(user)
            db.commit()
            print(f"Created platform admin account: {email}")

        print("\nLogin at http://localhost:5173/login")
        print("Admin panel: http://localhost:5173/admin")
    finally:
        db.close()


if __name__ == "__main__":
    main()
