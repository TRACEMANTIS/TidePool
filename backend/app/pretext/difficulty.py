"""Difficulty rating system for phishing pretext templates.

Provides both static difficulty level descriptions and a heuristic
assessment function that scores a pretext template based on its
characteristics.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Difficulty level definitions
# ---------------------------------------------------------------------------

DIFFICULTY_LEVELS: dict[int, str] = {
    1: "Obvious - Clear red flags, generic content, possible spelling errors. "
       "Most security-aware users should identify this as phishing.",
    2: "Basic - Somewhat generic, minor red flags visible upon inspection. "
       "Users with basic security training should catch this.",
    3: "Moderate - Plausible content and formatting, requires attention to "
       "detail to spot indicators of compromise.",
    4: "Advanced - Well-crafted pretext with few obvious red flags. "
       "Only users with strong security awareness are likely to identify it.",
    5: "Expert - Highly targeted, personalized content with minimal "
       "indicators of compromise. Difficult even for trained users to detect.",
}


def get_difficulty_description(level: int) -> str:
    """Return the human-readable description for a difficulty level.

    Parameters
    ----------
    level:
        Integer from 1 to 5.

    Returns
    -------
    str
        Description string, or a fallback message for out-of-range values.
    """
    return DIFFICULTY_LEVELS.get(level, f"Unknown difficulty level: {level}")


# ---------------------------------------------------------------------------
# Heuristic difficulty assessment
# ---------------------------------------------------------------------------

# Indicators that increase perceived sophistication
_PERSONALIZATION_VARS = {"first_name", "last_name", "full_name", "title", "department"}
_URGENCY_KEYWORDS = [
    "urgent", "immediately", "expires", "deadline", "action required",
    "within 24 hours", "within 48 hours", "asap", "time-sensitive",
    "must be completed",
]
_AUTHORITY_KEYWORDS = [
    "ceo", "cfo", "cto", "ciso", "president", "vice president",
    "director", "board", "executive", "chief", "management",
    "compliance", "legal",
]


def assess_difficulty(pretext: dict) -> int:
    """Heuristically score a pretext template's difficulty level.

    The function examines personalization depth, urgency indicators,
    authority impersonation, and technical sophistication to produce
    an integer score from 1 to 5.

    Parameters
    ----------
    pretext:
        A pretext template dict containing at minimum ``subject``,
        ``body_html`` or ``body_text``, and ``variables_used``.

    Returns
    -------
    int
        Difficulty score from 1 (Obvious) to 5 (Expert).
    """
    score = 0.0

    # --- Personalization depth ---
    variables_used = set(pretext.get("variables_used", []))
    personalization_count = len(variables_used & _PERSONALIZATION_VARS)
    if personalization_count >= 4:
        score += 2.0
    elif personalization_count >= 2:
        score += 1.0
    elif personalization_count >= 1:
        score += 0.5

    # --- Content analysis ---
    text = " ".join([
        pretext.get("subject", ""),
        pretext.get("body_text", "") or "",
        pretext.get("body_html", "") or "",
    ]).lower()

    # Urgency indicators (moderate use suggests sophistication; overuse is a red flag)
    urgency_count = sum(1 for kw in _URGENCY_KEYWORDS if kw in text)
    if 1 <= urgency_count <= 2:
        score += 1.0
    elif urgency_count > 2:
        score += 0.5  # Over-urgency is actually a red flag, so less sophisticated

    # Authority impersonation
    authority_count = sum(1 for kw in _AUTHORITY_KEYWORDS if kw in text)
    if authority_count >= 2:
        score += 1.5
    elif authority_count >= 1:
        score += 0.75

    # --- HTML sophistication ---
    html = pretext.get("body_html", "") or ""
    has_table_layout = "<table" in html.lower()
    has_styling = "style=" in html.lower()
    has_images = "<img" in html.lower() or "{{" in html  # logo variables count
    has_footer = "unsubscribe" in html.lower() or "privacy" in html.lower()

    sophistication_signals = sum([
        has_table_layout, has_styling, has_images, has_footer,
    ])
    score += sophistication_signals * 0.25

    # --- Red flags (reduce difficulty if many are present) ---
    red_flags = pretext.get("red_flags", [])
    if len(red_flags) >= 5:
        score -= 0.5
    elif len(red_flags) <= 1:
        score += 0.5

    # Clamp to 1-5 range
    level = max(1, min(5, round(score)))
    return level
