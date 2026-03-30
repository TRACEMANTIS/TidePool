"""Celery task for Excel/CSV address book ingestion.

Handles .xlsx (openpyxl), .xls (xlrd), and .csv files with memory-efficient
streaming, batch inserts, email validation, and progress tracking via Redis.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
from typing import Any

import chardet
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session, sessionmaker

from app.celery_app import celery
from app.config import settings
from app.addressbook.dedup import deduplicate_contacts

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BATCH_SIZE = 1000

# Simple but robust email regex (RFC 5321 local-part @ domain)
_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)

# ---------------------------------------------------------------------------
# Sync database helpers (Celery workers cannot use asyncpg)
# ---------------------------------------------------------------------------

_sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2").replace(
    "postgresql+asyncpg", "postgresql+psycopg2"
)
_sync_engine = create_engine(_sync_url, pool_pre_ping=True, pool_size=5)
_SyncSession = sessionmaker(bind=_sync_engine)


def _get_redis():
    """Return a Redis client instance."""
    import redis
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def _update_progress(
    addressbook_id: int,
    processed: int,
    total: int,
    errors: int,
) -> None:
    """Push progress data into Redis for real-time polling."""
    try:
        r = _get_redis()
        key = f"addressbook:{addressbook_id}:progress"
        r.set(
            key,
            json.dumps({"processed": processed, "total": total, "errors": errors}),
            ex=3600,  # expire after 1 hour
        )
    except Exception:
        logger.debug("Failed to update Redis progress for addressbook %s", addressbook_id)


def _set_status(session: Session, addressbook_id: int, status: str, row_count: int | None = None) -> None:
    """Update AddressBook status (and optionally row_count) in the database."""
    from app.models.contact import AddressBook, ImportStatus

    values: dict[str, Any] = {"import_status": ImportStatus(status)}
    if row_count is not None:
        values["row_count"] = row_count

    session.execute(
        update(AddressBook).where(AddressBook.id == addressbook_id).values(**values)
    )
    session.commit()


# ---------------------------------------------------------------------------
# File readers (streaming, memory-efficient)
# ---------------------------------------------------------------------------

def _detect_encoding(file_path: str) -> str:
    """Detect the character encoding of a file using chardet."""
    sample_size = 64 * 1024  # 64 KB sample
    with open(file_path, "rb") as f:
        raw = f.read(sample_size)
    result = chardet.detect(raw)
    encoding = result.get("encoding") or "utf-8"
    logger.debug("Detected encoding %s (confidence %.2f) for %s",
                 encoding, result.get("confidence", 0), file_path)
    return encoding


def _iter_csv_rows(file_path: str) -> tuple[list[str], Any]:
    """Open a CSV file and return (headers, row_iterator).

    Each row from the iterator is a list of strings.
    """
    encoding = _detect_encoding(file_path)
    fh = open(file_path, "r", encoding=encoding, errors="replace", newline="")
    reader = csv.reader(fh)
    headers = next(reader)
    return headers, reader, fh


def _iter_xlsx_rows(file_path: str) -> tuple[list[str], Any]:
    """Open an xlsx file in read-only mode and return (headers, row_iterator)."""
    import openpyxl

    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    ws = wb.active
    row_iter = ws.iter_rows(values_only=True)
    header_row = next(row_iter)
    headers = [str(cell) if cell is not None else "" for cell in header_row]
    return headers, row_iter, wb


def _iter_xls_rows(file_path: str) -> tuple[list[str], Any]:
    """Open an xls file and return (headers, row_generator)."""
    import xlrd

    wb = xlrd.open_workbook(file_path)
    ws = wb.sheet_by_index(0)

    headers = [str(ws.cell_value(0, col)) for col in range(ws.ncols)]

    def _row_gen():
        for row_idx in range(1, ws.nrows):
            yield [ws.cell_value(row_idx, col) for col in range(ws.ncols)]

    return headers, _row_gen(), None


# ---------------------------------------------------------------------------
# Row processing
# ---------------------------------------------------------------------------

_KNOWN_FIELDS = {"email", "first_name", "last_name", "department", "title"}


def _map_row(
    row: list | tuple,
    headers: list[str],
    column_mapping: dict[str, str],
) -> dict[str, Any] | None:
    """Map a raw row to a contact dict using the column mapping.

    Returns None if the row has no valid email.
    """
    contact: dict[str, Any] = {}
    custom: dict[str, str] = {}

    for idx, header in enumerate(headers):
        if idx >= len(row):
            break

        canonical = column_mapping.get(header)
        if canonical is None:
            continue

        value = row[idx]
        if value is None:
            value = ""
        value = str(value).strip()

        if canonical.startswith("custom_fields."):
            sub_key = canonical[len("custom_fields."):]
            if value:
                custom[sub_key] = value
        elif canonical in _KNOWN_FIELDS:
            contact[canonical] = value

    # Validate email
    email = contact.get("email", "").strip()
    if not email or not _EMAIL_RE.match(email):
        return None

    contact["email"] = email.lower()

    if custom:
        contact["custom_fields"] = custom

    return contact


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery.task(name="app.addressbook.ingest_addressbook", bind=True, max_retries=0)
def ingest_addressbook(
    self,
    addressbook_id: int,
    file_path: str,
    column_mapping: dict[str, str],
) -> dict[str, Any]:
    """Ingest a CSV/XLSX/XLS file into the contacts table.

    Parameters
    ----------
    addressbook_id:
        Primary key of the AddressBook row to populate.
    file_path:
        Absolute path to the uploaded file on disk.
    column_mapping:
        Dict mapping original column headers to canonical field names
        (e.g. ``{"Email Address": "email", "First Name": "first_name"}``).

    Returns
    -------
    dict
        Summary with keys ``total_processed``, ``imported``, ``duplicates``,
        ``invalid_emails``, ``status``.
    """
    session = _SyncSession()
    resource_handle = None
    total_processed = 0
    total_errors = 0
    total_imported = 0
    total_duplicates = 0

    try:
        # Mark as processing
        _set_status(session, addressbook_id, "PROCESSING")

        # Determine file type and open the appropriate reader
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".csv":
            headers, row_iter, resource_handle = _iter_csv_rows(file_path)
        elif ext == ".xlsx":
            headers, row_iter, resource_handle = _iter_xlsx_rows(file_path)
        elif ext == ".xls":
            headers, row_iter, resource_handle = _iter_xls_rows(file_path)
        else:
            raise ValueError(f"Unsupported file extension: {ext}")

        # Stream rows and batch insert
        batch: list[dict] = []
        seen_emails: set[str] = set()

        for row in row_iter:
            total_processed += 1

            contact = _map_row(
                list(row) if not isinstance(row, list) else row,
                headers,
                column_mapping,
            )

            if contact is None:
                total_errors += 1
                continue

            # In-flight dedup by email within this address book
            email_lower = contact["email"]
            if email_lower in seen_emails:
                total_duplicates += 1
                continue
            seen_emails.add(email_lower)

            contact["address_book_id"] = addressbook_id
            batch.append(contact)

            if len(batch) >= BATCH_SIZE:
                _flush_batch(session, batch)
                total_imported += len(batch)
                batch = []
                _update_progress(addressbook_id, total_processed, 0, total_errors)

        # Flush remaining
        if batch:
            _flush_batch(session, batch)
            total_imported += len(batch)

        # Final status update
        _set_status(session, addressbook_id, "COMPLETED", row_count=total_imported)
        _update_progress(addressbook_id, total_processed, total_processed, total_errors)

        logger.info(
            "Address book %s ingestion complete: %d imported, %d duplicates, %d invalid",
            addressbook_id, total_imported, total_duplicates, total_errors,
        )

        return {
            "total_processed": total_processed,
            "imported": total_imported,
            "duplicates": total_duplicates,
            "invalid_emails": total_errors,
            "status": "COMPLETED",
        }

    except Exception as exc:
        logger.exception("Address book %s ingestion failed", addressbook_id)
        try:
            _set_status(session, addressbook_id, "FAILED")
            _update_progress(addressbook_id, total_processed, total_processed, total_errors)
        except Exception:
            logger.exception("Failed to update status after error")
        raise

    finally:
        session.close()
        if resource_handle is not None:
            try:
                resource_handle.close()
            except Exception:
                pass


def _flush_batch(session: Session, batch: list[dict]) -> None:
    """Bulk insert a batch of contact dicts via SQLAlchemy."""
    from app.models.contact import Contact

    session.bulk_insert_mappings(Contact, batch)
    session.commit()
