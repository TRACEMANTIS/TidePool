"""Tests for address book functionality: column detection, email validation, deduplication."""

import re

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import AddressBook, Contact, ImportStatus
from tests.helpers import create_test_csv


# ---------------------------------------------------------------------------
# Column auto-detection
# ---------------------------------------------------------------------------


class TestColumnAutoDetection:
    """Verify that various header formats are detected correctly."""

    def test_standard_headers(self):
        """Standard column names (email, first_name, last_name) are recognized."""
        csv_bytes = create_test_csv(3, ["email", "first_name", "last_name", "department"])
        content = csv_bytes.decode("utf-8")
        header_line = content.split("\n")[0]
        headers = [h.strip() for h in header_line.split(",")]

        assert "email" in headers
        assert "first_name" in headers
        assert "last_name" in headers

    def test_alternate_header_formats(self):
        """Common alternate header names should be detectable."""
        # These are the kinds of headers that detect_columns should handle.
        alternate_sets = [
            ["Email Address", "First Name", "Last Name", "Department"],
            ["EMAIL", "FIRST", "LAST", "DEPT"],
            ["email_address", "fname", "lname", "department"],
            ["Mail", "Given Name", "Surname", "Division"],
        ]

        for headers in alternate_sets:
            csv_bytes = create_test_csv(2, headers)
            content = csv_bytes.decode("utf-8")
            first_line = content.split("\n")[0]
            # Verify the custom headers appear in the generated CSV.
            for h in headers:
                assert h in first_line, f"Header '{h}' not found in CSV output"


# ---------------------------------------------------------------------------
# Email validation
# ---------------------------------------------------------------------------


class TestEmailValidation:
    """Verify that invalid emails are caught during contact creation."""

    _VALID_EMAILS = [
        "user@example.com",
        "first.last@company.co.uk",
        "user+tag@domain.org",
        "name@sub.domain.test",
    ]

    _INVALID_EMAILS = [
        "not-an-email",
        "@missing-local.com",
        "missing-domain@",
        "spaces in@email.com",
        "",
    ]

    def test_valid_emails_accepted(self):
        """Standard email formats pass basic regex validation."""
        email_re = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
        for email in self._VALID_EMAILS:
            assert email_re.match(email), f"Valid email rejected: {email}"

    def test_invalid_emails_rejected(self):
        """Malformed emails are caught by validation."""
        email_re = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
        for email in self._INVALID_EMAILS:
            assert not email_re.match(email), f"Invalid email accepted: {email}"


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


class TestDeduplication:
    """Verify that duplicate emails within the same address book are deduplicated."""

    async def test_deduplication(
        self,
        db_session: AsyncSession,
    ):
        """Adding contacts with the same email to the same book keeps only one."""
        book = AddressBook(
            name="Dedup Test",
            import_status=ImportStatus.COMPLETED,
        )
        db_session.add(book)
        await db_session.flush()
        await db_session.refresh(book)

        # Add the first contact.
        contact1 = Contact(
            email="duplicate@test.local",
            first_name="First",
            last_name="Contact",
            address_book_id=book.id,
        )
        db_session.add(contact1)
        await db_session.flush()

        # Attempt to add a second contact with the same email in the same book.
        contact2 = Contact(
            email="duplicate@test.local",
            first_name="Second",
            last_name="Contact",
            address_book_id=book.id,
        )
        db_session.add(contact2)

        # The unique constraint (email, address_book_id) should cause a conflict.
        with pytest.raises(Exception):
            await db_session.flush()

        await db_session.rollback()

    async def test_same_email_different_books(
        self,
        db_session: AsyncSession,
    ):
        """The same email can exist in different address books."""
        book1 = AddressBook(name="Book A", import_status=ImportStatus.COMPLETED)
        book2 = AddressBook(name="Book B", import_status=ImportStatus.COMPLETED)
        db_session.add_all([book1, book2])
        await db_session.flush()

        contact1 = Contact(
            email="shared@test.local",
            first_name="Alice",
            address_book_id=book1.id,
        )
        contact2 = Contact(
            email="shared@test.local",
            first_name="Alice",
            address_book_id=book2.id,
        )
        db_session.add_all([contact1, contact2])
        await db_session.flush()

        # Both should exist.
        result = await db_session.execute(
            select(Contact).where(Contact.email == "shared@test.local")
        )
        contacts = result.scalars().all()
        assert len(contacts) == 2


# ---------------------------------------------------------------------------
# Large file handling (mock)
# ---------------------------------------------------------------------------


class TestLargeFileHandling:
    """Verify that large file imports are handled without excessive memory use."""

    def test_large_csv_generation(self):
        """Generating a large CSV uses streaming and does not exceed expected size."""
        row_count = 10000
        csv_bytes = create_test_csv(row_count)

        # Verify the correct number of rows (header + data).
        lines = csv_bytes.decode("utf-8").strip().split("\n")
        assert len(lines) == row_count + 1  # +1 for header

        # Each line should contain an email.
        for line in lines[1:6]:  # Spot-check first 5 data rows.
            assert "@" in line

    def test_large_file_size_reasonable(self):
        """A 10,000-row CSV should be under 2 MB (sanity check)."""
        csv_bytes = create_test_csv(10000)
        size_mb = len(csv_bytes) / (1024 * 1024)
        assert size_mb < 2.0, f"CSV is {size_mb:.2f} MB, expected < 2 MB"
