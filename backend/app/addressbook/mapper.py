"""Column mapping intelligence for address book imports.

Provides heuristic detection of common column header variations and maps
them to TidePool's canonical contact fields.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Canonical field definitions and their known header variations
# ---------------------------------------------------------------------------

_FIELD_PATTERNS: dict[str, list[str]] = {
    "email": [
        "email", "e-mail", "email address", "email_addr", "emailaddress",
        "e-mail address", "mail", "email_address", "work email",
        "primary email", "contact email",
    ],
    "first_name": [
        "first name", "firstname", "first", "given name", "givenname",
        "first_name", "fname", "forename",
    ],
    "last_name": [
        "last name", "lastname", "last", "surname", "family name",
        "familyname", "last_name", "lname",
    ],
    "department": [
        "department", "dept", "dept.", "division", "business unit",
        "team", "group", "org unit",
    ],
    "title": [
        "title", "job title", "jobtitle", "position", "role",
        "job_title", "designation", "job role",
    ],
}

# Pre-compile: lowered, stripped variations -> canonical field name
_LOOKUP: dict[str, str] = {}
for _field, _variations in _FIELD_PATTERNS.items():
    for _var in _variations:
        _LOOKUP[_var.lower().strip()] = _field


def _normalize(header: str) -> str:
    """Normalize a header string for fuzzy matching."""
    # Strip whitespace, lower-case, collapse multiple spaces
    s = re.sub(r"\s+", " ", header.strip().lower())
    return s


def auto_detect_mapping(headers: list[str]) -> dict[str, str]:
    """Heuristically map spreadsheet column headers to TidePool contact fields.

    Parameters
    ----------
    headers:
        List of raw column header strings from the uploaded file.

    Returns
    -------
    dict[str, str]
        Mapping of ``{original_header: canonical_field}``.  Unmapped
        columns are assigned to ``"custom_fields"`` with a sub-key
        derived from the header name.
    """
    mapping: dict[str, str] = {}
    assigned_fields: set[str] = set()

    for header in headers:
        if not header or not header.strip():
            continue

        normalized = _normalize(header)
        canonical = _LOOKUP.get(normalized)

        if canonical and canonical not in assigned_fields:
            mapping[header] = canonical
            assigned_fields.add(canonical)
        else:
            # Store unmapped columns under custom_fields namespace
            safe_key = re.sub(r"[^a-z0-9_]", "_", normalized)
            safe_key = re.sub(r"_+", "_", safe_key).strip("_")
            mapping[header] = f"custom_fields.{safe_key}"

    return mapping


def validate_mapping(
    mapping: dict[str, str],
    required: list[str] | None = None,
) -> list[str]:
    """Validate that a column mapping covers all required fields.

    Parameters
    ----------
    mapping:
        The column mapping dict (``{header: canonical_field}``).
    required:
        List of canonical field names that must be present.
        Defaults to ``["email"]``.

    Returns
    -------
    list[str]
        Validation error messages.  Empty list means the mapping is valid.
    """
    if required is None:
        required = ["email"]

    mapped_fields = set(mapping.values())
    errors: list[str] = []

    for field in required:
        if field not in mapped_fields:
            errors.append(f"Required field '{field}' is not mapped")

    return errors
