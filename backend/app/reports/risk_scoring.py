"""Risk scoring engine for TidePool phishing simulations.

Calculates risk at three levels: recipient, department, and organisation.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Recipient-level risk
# ---------------------------------------------------------------------------

def calculate_recipient_risk(events: list[str]) -> float:
    """Score a single recipient based on their tracking events.

    Weights:
        clicked   = +0.4
        submitted = +0.6
        reported  = -0.2  (reduces score if user reported the phish)

    Args:
        events: List of event type strings (e.g. ``["OPENED", "CLICKED"]``).

    Returns:
        Risk score clamped to [0.0, 1.0].
    """
    score = 0.0
    event_set = {e.upper() for e in events}

    if "CLICKED" in event_set:
        score += 0.4
    if "SUBMITTED" in event_set:
        score += 0.6
    if "REPORTED" in event_set:
        score -= 0.2

    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Department-level risk
# ---------------------------------------------------------------------------

def calculate_department_risk(
    recipient_scores: list[float],
    participation_rate: float,
) -> float:
    """Average recipient scores adjusted by participation rate.

    A department with low participation is penalised (score is inflated)
    because fewer tested employees implies higher uncertainty.

    Args:
        recipient_scores: Individual risk scores for tested recipients.
        participation_rate: Fraction of department members who were tested (0-1).

    Returns:
        Risk score clamped to [0.0, 1.0].
    """
    if not recipient_scores:
        return 0.0

    avg = sum(recipient_scores) / len(recipient_scores)

    # Adjust: low participation inflates risk (uncertainty penalty).
    if participation_rate > 0:
        adjusted = avg / participation_rate
    else:
        adjusted = avg

    return max(0.0, min(1.0, adjusted))


# ---------------------------------------------------------------------------
# Organisation-level risk
# ---------------------------------------------------------------------------

def calculate_org_risk(
    department_scores: list[tuple[str, float, int]],
) -> float:
    """Weighted average of department scores by headcount.

    Args:
        department_scores: List of (department_name, risk_score, headcount).

    Returns:
        Organisation risk score clamped to [0.0, 1.0].
    """
    total_headcount = sum(hc for _, _, hc in department_scores)
    if total_headcount == 0:
        return 0.0

    weighted = sum(score * hc for _, score, hc in department_scores)
    return max(0.0, min(1.0, weighted / total_headcount))


# ---------------------------------------------------------------------------
# Risk level label
# ---------------------------------------------------------------------------

def risk_level(score: float) -> str:
    """Map a numeric risk score to a human-readable severity label.

    Ranges:
        [0.0, 0.2)  -> Low
        [0.2, 0.4)  -> Moderate
        [0.4, 0.6)  -> High
        [0.6, 0.8)  -> Critical
        [0.8, 1.0]  -> Severe
    """
    if score < 0.2:
        return "Low"
    if score < 0.4:
        return "Moderate"
    if score < 0.6:
        return "High"
    if score < 0.8:
        return "Critical"
    return "Severe"
