"""Shared pytest fixtures for TidePool backend tests.

Provides:
- An isolated async SQLite in-memory database per test.
- A FastAPI test app with dependency overrides.
- Pre-authenticated headers for admin and API key access.
- Sample data factories for campaigns, address books, and SMTP profiles.
"""

import os
import uuid
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# ---------------------------------------------------------------------------
# Set test environment variables BEFORE importing app modules.
# This avoids validation errors in Settings.__init__.
# ---------------------------------------------------------------------------
_TEST_SECRET_KEY = "test-secret-key-at-least-32-characters-long!"
_TEST_ENCRYPTION_KEY = Fernet.generate_key().decode()

os.environ.setdefault("SECRET_KEY", _TEST_SECRET_KEY)
os.environ.setdefault("ENCRYPTION_KEY", _TEST_ENCRYPTION_KEY)
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.smtp_profile import SmtpProfile, BackendType  # noqa: E402
from app.models.email_template import EmailTemplate, TemplateCategory  # noqa: E402
from app.models.contact import AddressBook, Contact, ImportStatus  # noqa: E402
from app.models.campaign import Campaign, CampaignStatus  # noqa: E402
from app.utils.security import (  # noqa: E402
    create_access_token,
    hash_password,
    generate_api_key,
)
from app.models.api_key import ApiKey  # noqa: E402


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session():
    """Yield an async SQLAlchemy session backed by an in-memory SQLite database.

    Each test gets a completely fresh database with all tables created.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    await engine.dispose()


# ---------------------------------------------------------------------------
# Application fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def app(db_session: AsyncSession):
    """Create a FastAPI test application with the database dependency overridden."""

    async def _override_get_db():
        yield db_session

    application = create_app()
    application.dependency_overrides[get_db] = _override_get_db
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def client(app):
    """Provide an httpx.AsyncClient wired to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Auth fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """Create and persist a test admin user in the database."""
    user = User(
        username="testadmin",
        email="testadmin@tidepool.test",
        hashed_password=hash_password("Adm!nP@ss2026w0rd"),
        is_active=True,
        is_admin=True,
        full_name="Test Admin",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def auth_headers(admin_user: User) -> dict[str, str]:
    """Return HTTP headers containing a valid JWT for the test admin user."""
    token = create_access_token(
        data={
            "sub": admin_user.username,
            "user_id": admin_user.id,
            "is_admin": admin_user.is_admin,
        }
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def regular_user(db_session: AsyncSession) -> User:
    """Create and persist a regular (non-admin) test user."""
    user = User(
        username="testuser",
        email="testuser@tidepool.test",
        hashed_password=hash_password("Us3rP@ss2026w0rd!"),
        is_active=True,
        is_admin=False,
        full_name="Test User",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def user_headers(regular_user: User) -> dict[str, str]:
    """Return HTTP headers with a valid JWT for the regular test user."""
    token = create_access_token(
        data={
            "sub": regular_user.username,
            "user_id": regular_user.id,
            "is_admin": regular_user.is_admin,
        }
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def api_key_headers(db_session: AsyncSession, admin_user: User) -> dict[str, str]:
    """Create an API key for the admin user and return X-API-Key headers."""
    raw_key, key_hash, key_prefix = generate_api_key()
    api_key = ApiKey(
        key_prefix=key_prefix,
        key_hash=key_hash,
        name="test-api-key",
        user_id=admin_user.id,
        scopes=["*"],
        is_active=True,
    )
    db_session.add(api_key)
    await db_session.flush()
    return {"X-API-Key": raw_key}


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def sample_smtp_profile(db_session: AsyncSession, admin_user: User) -> SmtpProfile:
    """Create a test SMTP profile."""
    profile = SmtpProfile(
        name="Test SMTP",
        backend_type=BackendType.SMTP,
        host="smtp.test.local",
        port=587,
        username="smtp_user",
        password="smtp_password_secret",
        use_tls=True,
        use_ssl=False,
        from_address="noreply@test.local",
        from_name="Test Sender",
        created_by=admin_user.id,
    )
    db_session.add(profile)
    await db_session.flush()
    await db_session.refresh(profile)
    return profile


@pytest.fixture
async def sample_template(db_session: AsyncSession, admin_user: User) -> EmailTemplate:
    """Create a test email template."""
    template = EmailTemplate(
        name="Test Template",
        category=TemplateCategory.IT,
        difficulty=2,
        subject="Important: Verify your account",
        body_html="<p>Hello {{first_name}}, please verify your account.</p>",
        body_text="Hello {{first_name}}, please verify your account.",
        variables=["first_name", "last_name"],
        created_by=admin_user.id,
    )
    db_session.add(template)
    await db_session.flush()
    await db_session.refresh(template)
    return template


@pytest.fixture
async def sample_addressbook(db_session: AsyncSession) -> AddressBook:
    """Create an address book with 100 test contacts."""
    book = AddressBook(
        name="Test Address Book",
        source_filename="test_contacts.csv",
        import_status=ImportStatus.COMPLETED,
        row_count=100,
        column_mapping={
            "email": "email",
            "first_name": "first_name",
            "last_name": "last_name",
            "department": "department",
        },
    )
    db_session.add(book)
    await db_session.flush()
    await db_session.refresh(book)

    departments = ["Engineering", "Sales", "HR", "Finance", "Marketing"]
    contacts = []
    for i in range(100):
        contact = Contact(
            email=f"user{i}@company.test",
            first_name=f"First{i}",
            last_name=f"Last{i}",
            department=departments[i % len(departments)],
            address_book_id=book.id,
        )
        contacts.append(contact)
    db_session.add_all(contacts)
    await db_session.flush()

    return book


@pytest.fixture
async def sample_campaign(
    db_session: AsyncSession,
    admin_user: User,
    sample_smtp_profile: SmtpProfile,
    sample_template: EmailTemplate,
    sample_addressbook: AddressBook,
) -> Campaign:
    """Create a complete test campaign with all dependencies."""
    campaign = Campaign(
        name="Test Campaign",
        description="Automated test campaign with full dependency chain",
        status=CampaignStatus.DRAFT,
        smtp_profile_id=sample_smtp_profile.id,
        email_template_id=sample_template.id,
        landing_page_id=None,
        training_redirect_url="https://training.test.local/module/1",
        training_redirect_delay_seconds=5,
        created_by=admin_user.id,
    )
    db_session.add(campaign)
    await db_session.flush()
    await db_session.refresh(campaign)
    return campaign
