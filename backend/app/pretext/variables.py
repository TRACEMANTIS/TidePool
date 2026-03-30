"""Variable resolution system for pretext templates.

Handles {{variable}} substitution, extraction, and validation for
phishing simulation email templates.
"""

from __future__ import annotations

import re
from datetime import datetime

# ---------------------------------------------------------------------------
# Standard variable definitions
# ---------------------------------------------------------------------------

STANDARD_VARIABLES: dict[str, str] = {
    "first_name": "Contact's first name",
    "last_name": "Contact's last name",
    "full_name": "Contact's full name (first + last)",
    "email": "Contact's email address",
    "department": "Contact's department or business unit",
    "title": "Contact's job title or position",
    "company": "Target organization name",
    "date": "Current date (formatted as Month Day, Year)",
    "login_url": "Phishing landing page URL",
    "support_email": "Spoofed support/helpdesk email address",
    "from_name": "Display name of the sender",
}

# Regex to match {{variable_name}} patterns
_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def resolve_variables(
    template_str: str,
    contact: dict,
    campaign_config: dict,
) -> str:
    """Substitute all ``{{variable}}`` placeholders with actual values.

    Parameters
    ----------
    template_str:
        The template string containing ``{{variable}}`` placeholders.
    contact:
        Contact data dict with keys like ``first_name``, ``last_name``,
        ``email``, ``department``, ``title``.
    campaign_config:
        Campaign-level configuration dict with keys like ``company``,
        ``login_url``, ``support_email``, ``from_name``.

    Returns
    -------
    str
        The template string with all variables resolved.  Missing
        variables are replaced with an empty string.
    """
    # Build the merged context
    context: dict[str, str] = {}

    # Contact fields
    first = contact.get("first_name", "") or ""
    last = contact.get("last_name", "") or ""
    context["first_name"] = first
    context["last_name"] = last
    context["full_name"] = f"{first} {last}".strip()
    context["email"] = contact.get("email", "") or ""
    context["department"] = contact.get("department", "") or ""
    context["title"] = contact.get("title", "") or ""

    # Campaign-level fields
    context["company"] = campaign_config.get("company", "") or ""
    context["login_url"] = campaign_config.get("login_url", "") or ""
    context["support_email"] = campaign_config.get("support_email", "") or ""
    context["from_name"] = campaign_config.get("from_name", "") or ""
    context["date"] = campaign_config.get("date") or datetime.now().strftime("%B %d, %Y")

    # Merge any custom fields from contact
    custom = contact.get("custom_fields")
    if isinstance(custom, dict):
        for key, value in custom.items():
            context.setdefault(key, str(value) if value is not None else "")

    # Merge any extra campaign config values
    for key, value in campaign_config.items():
        context.setdefault(key, str(value) if value is not None else "")

    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        return context.get(var_name, "")

    return _VAR_PATTERN.sub(_replace, template_str)


def list_variables_in_template(template_str: str) -> list[str]:
    """Extract all ``{{variable_name}}`` patterns from a template string.

    Parameters
    ----------
    template_str:
        The template string to scan.

    Returns
    -------
    list[str]
        Unique variable names in the order they first appear.
    """
    seen: set[str] = set()
    result: list[str] = []

    for match in _VAR_PATTERN.finditer(template_str):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            result.append(name)

    return result


def validate_variables(
    template_str: str,
    available_vars: list[str],
) -> list[str]:
    """Check that all variables used in a template are available.

    Parameters
    ----------
    template_str:
        The template string to validate.
    available_vars:
        List of variable names that will be available at render time.

    Returns
    -------
    list[str]
        List of variable names used in the template that are NOT in
        ``available_vars``.  Empty list means all variables are covered.
    """
    used = list_variables_in_template(template_str)
    available_set = set(available_vars)
    return [var for var in used if var not in available_set]
