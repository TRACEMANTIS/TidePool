"""Contact deduplication utilities for address book ingestion."""

from __future__ import annotations


def deduplicate_contacts(
    contacts: list[dict],
    key: str = "email",
) -> tuple[list[dict], int]:
    """Remove duplicate contacts based on a key field.

    Comparison is case-insensitive.  The first occurrence of each unique
    key value is kept; subsequent duplicates are discarded.

    Parameters
    ----------
    contacts:
        List of contact dicts to deduplicate.
    key:
        The dict key to use for deduplication (default ``"email"``).

    Returns
    -------
    tuple[list[dict], int]
        ``(unique_contacts, duplicate_count)``
    """
    seen: set[str] = set()
    unique: list[dict] = []
    duplicate_count = 0

    for contact in contacts:
        value = contact.get(key)
        if value is None:
            # Skip records missing the dedup key entirely
            duplicate_count += 1
            continue

        normalized = value.strip().lower()

        if normalized in seen:
            duplicate_count += 1
        else:
            seen.add(normalized)
            unique.append(contact)

    return unique, duplicate_count
