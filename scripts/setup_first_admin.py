#!/usr/bin/env python3
"""First-run admin setup script for TidePool.

Interactively creates the initial admin user and generates an API key.
Connects directly to PostgreSQL -- does not require the TidePool server
to be running.

Usage:
    python setup_first_admin.py
    python setup_first_admin.py --non-interactive --username admin --email admin@co.com --password 'S3cure!Pass99'

Environment:
    DATABASE_URL  -- PostgreSQL connection string (or reads from .env file).
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from pathlib import Path

# Ensure backend imports work.
_BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


# ---------------------------------------------------------------------------
# Password complexity (mirrors app.utils.security.validate_password_complexity)
# ---------------------------------------------------------------------------

def validate_password(password: str) -> list[str]:
    """Check password complexity.  Returns a list of failure reasons."""
    errors: list[str] = []
    if len(password) < 12:
        errors.append("Must be at least 12 characters long.")
    if not re.search(r"[A-Z]", password):
        errors.append("Must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        errors.append("Must contain at least one lowercase letter.")
    if not re.search(r"\d", password):
        errors.append("Must contain at least one digit.")
    if not re.search(r"[^A-Za-z0-9]", password):
        errors.append("Must contain at least one special character.")
    return errors


def _load_env_file() -> dict[str, str]:
    """Load key=value pairs from a .env file if present."""
    env_vars: dict[str, str] = {}
    for candidate in [
        Path(__file__).resolve().parent.parent / ".env",
        Path(__file__).resolve().parent.parent / "backend" / ".env",
    ]:
        if candidate.is_file():
            with open(candidate) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, value = line.partition("=")
                        value = value.strip().strip("'\"")
                        env_vars[key.strip()] = value
            break
    return env_vars


def _get_database_url() -> str:
    """Resolve the database URL from environment or .env file.

    Converts asyncpg URLs to psycopg2 for synchronous access.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        env_vars = _load_env_file()
        url = env_vars.get("DATABASE_URL")
    if not url:
        print(
            "ERROR: DATABASE_URL not set.\n"
            "  Set it as an environment variable or in a .env file.\n"
            "  Example: postgresql+asyncpg://tidepool:pass@localhost:5432/tidepool",
            file=sys.stderr,
        )
        sys.exit(1)

    # Convert async driver to sync for this script.
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    url = url.replace("postgresql+psycopg2://", "postgresql://")
    return url


# ---------------------------------------------------------------------------
# Database operations (uses psycopg2 or sqlalchemy sync)
# ---------------------------------------------------------------------------

def _setup_admin(username: str, email: str, password: str) -> tuple[int, str]:
    """Create the admin user and API key.  Returns (user_id, raw_api_key).

    Uses synchronous psycopg2 for simplicity -- this script runs once.
    """
    try:
        import psycopg2
    except ImportError:
        print(
            "ERROR: psycopg2 is required for direct database access.\n"
            "  Install with:  pip install psycopg2-binary",
            file=sys.stderr,
        )
        sys.exit(1)

    # Import hashing utilities.  Try the backend module first; fall back
    # to inline bcrypt if the full app cannot be imported (missing env vars).
    try:
        from app.utils.security import hash_password, generate_api_key
    except Exception:
        # Fallback: use passlib/secrets directly.
        import secrets
        from passlib.context import CryptContext
        _pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

        def hash_password(plain: str) -> str:
            return _pwd.hash(plain)

        def generate_api_key() -> tuple[str, str, str]:
            raw = "tp_" + secrets.token_urlsafe(48)
            return raw, _pwd.hash(raw), raw[:11]

    db_url = _get_database_url()
    hashed = hash_password(password)
    raw_key, key_hash, key_prefix = generate_api_key()

    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = False
        cur = conn.cursor()

        # Check if user already exists.
        cur.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
        existing = cur.fetchone()
        if existing:
            print(
                f"ERROR: A user with username '{username}' or email '{email}' already exists.",
                file=sys.stderr,
            )
            conn.close()
            sys.exit(1)

        # Create admin user.
        cur.execute(
            """
            INSERT INTO users (username, email, hashed_password, is_active, is_admin,
                               failed_login_attempts, created_at, updated_at)
            VALUES (%s, %s, %s, TRUE, TRUE, 0, NOW(), NOW())
            RETURNING id
            """,
            (username, email, hashed),
        )
        user_id = cur.fetchone()[0]

        # Create API key.
        cur.execute(
            """
            INSERT INTO api_keys (key_prefix, key_hash, name, user_id, scopes,
                                  is_active, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, TRUE, NOW(), NOW())
            """,
            (key_prefix, key_hash, "Initial admin key", user_id, '["*"]'),
        )

        conn.commit()
        cur.close()
        conn.close()

    except psycopg2.OperationalError as exc:
        print(f"ERROR: Cannot connect to database.\n  {exc}", file=sys.stderr)
        sys.exit(1)
    except psycopg2.Error as exc:
        print(f"ERROR: Database operation failed.\n  {exc}", file=sys.stderr)
        sys.exit(1)

    return user_id, raw_key


def _verify_setup(base_url: str, api_key: str) -> bool:
    """Optionally verify the setup by calling /health and /auth/me."""
    try:
        import httpx
    except ImportError:
        print("  (httpx not installed -- skipping API verification)")
        return True

    try:
        # Health check (no auth needed).
        resp = httpx.get(f"{base_url}/api/v1/health", timeout=10)
        if resp.status_code == 200:
            print(f"  Health check:  OK ({resp.json()})")
        else:
            print(f"  Health check:  HTTP {resp.status_code} (server may not be running)")
            return False

        # Auth check.
        resp = httpx.get(
            f"{base_url}/api/v1/auth/me",
            headers={"X-API-Key": api_key},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            print(f"  Auth check:    OK (username={data.get('username', 'N/A')})")
            return True
        else:
            print(f"  Auth check:    HTTP {resp.status_code}")
            return False

    except httpx.ConnectError:
        print("  API server not reachable (this is normal if the server is not running yet).")
        return True
    except Exception as exc:
        print(f"  Verification error: {exc}")
        return True  # Non-fatal


# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------

def _prompt_username() -> str:
    while True:
        username = input("  Admin username: ").strip()
        if not username:
            print("    Username cannot be empty.")
            continue
        if len(username) > 64:
            print("    Username must be 64 characters or fewer.")
            continue
        return username


def _prompt_email() -> str:
    while True:
        email = input("  Admin email:    ").strip()
        if not email or "@" not in email:
            print("    Enter a valid email address.")
            continue
        if len(email) > 320:
            print("    Email must be 320 characters or fewer.")
            continue
        return email


def _prompt_password() -> str:
    while True:
        password = getpass.getpass("  Admin password: ")
        errors = validate_password(password)
        if errors:
            print("    Password does not meet requirements:")
            for err in errors:
                print(f"      - {err}")
            continue
        confirm = getpass.getpass("  Confirm password: ")
        if password != confirm:
            print("    Passwords do not match.")
            continue
        return password


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create the initial admin user for a TidePool deployment.",
    )
    parser.add_argument("--non-interactive", action="store_true",
                        help="Run without prompts (requires --username, --email, --password).")
    parser.add_argument("--username", help="Admin username.")
    parser.add_argument("--email", help="Admin email address.")
    parser.add_argument("--password", help="Admin password (will be validated for complexity).")
    parser.add_argument("--verify-url", default="http://localhost:8000",
                        help="TidePool API URL to verify against after setup (default: http://localhost:8000).")
    parser.add_argument("--skip-verify", action="store_true",
                        help="Skip post-setup API verification.")
    args = parser.parse_args()

    print()
    print("TidePool -- First Admin Setup")
    print("=" * 40)
    print()

    if args.non_interactive:
        if not all([args.username, args.email, args.password]):
            print(
                "ERROR: --non-interactive requires --username, --email, and --password.",
                file=sys.stderr,
            )
            return 1
        username = args.username
        email = args.email
        password = args.password
    else:
        username = _prompt_username()
        email = _prompt_email()
        password = _prompt_password()

    # Validate password in all modes.
    errors = validate_password(password)
    if errors:
        print("ERROR: Password does not meet complexity requirements:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print()
    print(f"  Creating admin user '{username}' ...")

    user_id, raw_key = _setup_admin(username, email, password)

    print()
    print("  Admin user created successfully.")
    print()
    print(f"  User ID:   {user_id}")
    print(f"  Username:  {username}")
    print(f"  Email:     {email}")
    print()
    print("  " + "=" * 50)
    print(f"  API Key:   {raw_key}")
    print("  " + "=" * 50)
    print()
    print("  IMPORTANT: Save this API key now.  It cannot be retrieved later.")
    print()

    # Verify setup against the running API.
    if not args.skip_verify:
        print("  Verifying setup ...")
        _verify_setup(args.verify_url, raw_key)
        print()

    print("  Next steps:")
    print("    1. Export the API key:  export TIDEPOOL_API_KEY='<key>'")
    print("    2. Start the server:    docker compose up -d")
    print("    3. Open the dashboard:  http://localhost:3000")
    print("    4. Run the agent CLI:   python scripts/agent_runner.py --help")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
