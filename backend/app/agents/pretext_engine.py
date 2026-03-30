"""AI-powered pretext generation engine.

Generates phishing simulation email content using either the Claude API
(when an Anthropic API key is configured) or a rule-based fallback that
selects and customizes templates from the built-in pretext library.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.pretext.library import PretextLibrary

from app.agents.schemas import (
    AgentCampaignPlan,
    PretextGenerationRequest,
    PretextGenerationResponse,
)

logger = logging.getLogger(__name__)

_pretext_library = PretextLibrary()

# Difficulty-to-characteristic mapping for rule-based evaluation.
_DIFFICULTY_SIGNALS: dict[int, dict[str, Any]] = {
    1: {
        "label": "Easy to detect",
        "expected_red_flags": 4,
        "characteristics": [
            "Obvious spelling/grammar errors",
            "Generic greeting",
            "Mismatched sender domain",
            "Suspicious URL visible in text",
        ],
    },
    2: {
        "label": "Moderate",
        "expected_red_flags": 3,
        "characteristics": [
            "Minor urgency cues",
            "Plausible but external sender",
            "Generic call-to-action",
        ],
    },
    3: {
        "label": "Challenging",
        "expected_red_flags": 2,
        "characteristics": [
            "Well-written with subtle urgency",
            "Plausible internal sender",
            "Context-appropriate language",
        ],
    },
    4: {
        "label": "Advanced",
        "expected_red_flags": 1,
        "characteristics": [
            "Highly targeted content",
            "Mimics real business process",
            "Minimal overt red flags",
        ],
    },
    5: {
        "label": "Expert",
        "expected_red_flags": 0,
        "characteristics": [
            "Indistinguishable from legitimate email",
            "Uses real organizational context",
            "No visible red flags to untrained eye",
        ],
    },
}

# Claude system prompt for pretext generation.
_SYSTEM_PROMPT = """\
You are an authorized security testing content generator for TidePool, a \
phishing simulation platform used by organizations to test and train their \
employees. Your role is to create realistic but identifiable phishing \
simulation emails for AUTHORIZED security awareness testing.

Guidelines:
- Generate emails that mimic real-world phishing techniques at the specified difficulty level.
- Include appropriate red flags that trained users should be able to identify.
- Never generate content that could facilitate actual malicious phishing.
- All content is for authorized security testing within organizations that have opted in.
- Include {{variable}} placeholders for personalization: {{first_name}}, {{last_name}}, \
{{email}}, {{company}}, {{login_url}}, {{date}}, {{from_name}}, {{support_email}}.

Output format (JSON):
{
  "subject": "...",
  "body_html": "...",
  "body_text": "...",
  "variables_used": ["first_name", "company", ...],
  "estimated_difficulty": 1-5,
  "red_flags": ["flag1", "flag2", ...],
  "reasoning": "Why this pretext was designed this way..."
}
"""


class PretextEngine:
    """Generate and evaluate phishing simulation pretexts.

    Works in two modes:
    - AI mode: Uses the Anthropic Claude API for custom generation.
    - Fallback mode: Selects and customizes from the built-in library.
    """

    def __init__(self, anthropic_api_key: str | None = None) -> None:
        self.api_key = anthropic_api_key
        self._client = None

        if self.api_key:
            try:
                import anthropic
                self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
            except ImportError:
                logger.warning(
                    "anthropic package not installed. Falling back to template-based generation."
                )
                self._client = None

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------

    async def generate_pretext(
        self,
        request: PretextGenerationRequest,
    ) -> PretextGenerationResponse:
        """Generate a phishing simulation pretext.

        Uses Claude API if available, otherwise falls back to selecting
        and customizing a template from the built-in library.
        """
        if self._client is not None:
            return await self._generate_with_ai(request)
        return self._generate_from_library(request)

    async def generate_campaign_pretexts(
        self,
        plan: AgentCampaignPlan,
        count: int = 3,
    ) -> list[PretextGenerationResponse]:
        """Generate multiple pretext variants for A/B testing.

        Varies difficulty, category, and approach across variants.
        """
        variants: list[PretextGenerationResponse] = []
        categories = ["IT", "HR", "FINANCE", "EXECUTIVE", "VENDOR"]
        tones = ["professional", "urgent", "casual", "formal"]
        urgency_levels = ["low", "medium", "high"]

        for i in range(count):
            # Rotate category and tone for diversity.
            cat = categories[i % len(categories)]
            tone = tones[i % len(tones)]
            urgency = urgency_levels[i % len(urgency_levels)]

            # Vary difficulty around the target (+/- 1).
            difficulty = plan.difficulty_target + (i % 3 - 1)
            difficulty = max(1, min(5, difficulty))

            request = PretextGenerationRequest(
                target_audience=plan.target_audience,
                company_context=plan.objective,
                difficulty=difficulty,
                category=cat,
                tone=tone,
                urgency_level=urgency,
            )

            variant = await self.generate_pretext(request)
            variants.append(variant)

        return variants

    # ------------------------------------------------------------------
    # Evaluate
    # ------------------------------------------------------------------

    async def evaluate_pretext(
        self,
        subject: str,
        body: str,
    ) -> dict[str, Any]:
        """Score and analyze an existing pretext.

        Returns difficulty rating, red flag analysis, and improvement
        suggestions. Uses AI if available, rule-based fallback otherwise.
        """
        if self._client is not None:
            return await self._evaluate_with_ai(subject, body)
        return self._evaluate_rule_based(subject, body)

    # ------------------------------------------------------------------
    # AI-powered generation (Claude API)
    # ------------------------------------------------------------------

    async def _generate_with_ai(
        self,
        request: PretextGenerationRequest,
    ) -> PretextGenerationResponse:
        """Call Claude API to generate a custom pretext."""
        import json as json_module

        user_prompt = (
            f"Generate a phishing simulation email for authorized security testing.\n\n"
            f"Target audience: {request.target_audience}\n"
            f"Company context: {request.company_context}\n"
            f"Difficulty level: {request.difficulty}/5\n"
            f"Category: {request.category}\n"
            f"Tone: {request.tone}\n"
            f"Urgency level: {request.urgency_level}\n\n"
            f"Return the result as a JSON object with the specified fields."
        )

        try:
            response = await self._client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )

            # Parse the response content.
            content = response.content[0].text

            # Extract JSON from the response (may be wrapped in markdown code fences).
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                data = json_module.loads(json_match.group())
            else:
                raise ValueError("No JSON object found in API response.")

            return PretextGenerationResponse(
                subject=data.get("subject", ""),
                body_html=data.get("body_html", ""),
                body_text=data.get("body_text", ""),
                variables_used=data.get("variables_used", []),
                estimated_difficulty=data.get("estimated_difficulty", request.difficulty),
                red_flags=data.get("red_flags", []),
                reasoning=data.get("reasoning", "Generated via Claude API."),
            )

        except Exception as exc:
            logger.error("AI pretext generation failed: %s. Falling back to library.", exc)
            return self._generate_from_library(request)

    async def _evaluate_with_ai(self, subject: str, body: str) -> dict[str, Any]:
        """Use Claude API to evaluate an existing pretext."""
        import json as json_module

        eval_prompt = (
            f"Evaluate this phishing simulation email for authorized security testing.\n\n"
            f"Subject: {subject}\n\n"
            f"Body:\n{body}\n\n"
            f"Analyze and return JSON with:\n"
            f'- "difficulty_score": 1-5 rating\n'
            f'- "red_flags": list of identifiable phishing indicators\n'
            f'- "strengths": what makes this pretext effective\n'
            f'- "weaknesses": what could be improved\n'
            f'- "suggestions": specific improvement recommendations\n'
            f'- "overall_assessment": brief summary'
        )

        try:
            response = await self._client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                system="You are a phishing simulation quality analyst for authorized security testing.",
                messages=[{"role": "user", "content": eval_prompt}],
            )

            content = response.content[0].text
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                return json_module.loads(json_match.group())

            return {"error": "Failed to parse evaluation response", "raw": content}

        except Exception as exc:
            logger.error("AI pretext evaluation failed: %s. Using rule-based fallback.", exc)
            return self._evaluate_rule_based(subject, body)

    # ------------------------------------------------------------------
    # Library-based fallback
    # ------------------------------------------------------------------

    def _generate_from_library(
        self,
        request: PretextGenerationRequest,
    ) -> PretextGenerationResponse:
        """Select and customize a pretext from the built-in library."""
        # Search for matching pretexts.
        pretexts = _pretext_library.list_pretexts(
            category=request.category,
            difficulty=request.difficulty,
        )

        # Broaden search if no exact match.
        if not pretexts:
            pretexts = _pretext_library.list_pretexts(category=request.category)
        if not pretexts:
            pretexts = _pretext_library.list_pretexts(difficulty=request.difficulty)
        if not pretexts:
            pretexts = _pretext_library.list_pretexts()

        if not pretexts:
            return PretextGenerationResponse(
                subject="Security Notification",
                body_html="<p>Please review your account security settings.</p>",
                body_text="Please review your account security settings.",
                variables_used=[],
                estimated_difficulty=request.difficulty,
                red_flags=["Generic content -- no library templates available"],
                reasoning="No matching templates found in the pretext library.",
            )

        # Select the best match (closest difficulty).
        pretexts.sort(key=lambda p: abs(p["difficulty"] - request.difficulty))
        selected = pretexts[0]

        # Retrieve full template.
        full_pretext = _pretext_library.get_pretext(selected["id"])
        if full_pretext is None:
            # Should not happen, but handle gracefully.
            full_pretext = selected

        return PretextGenerationResponse(
            subject=full_pretext.get("subject", ""),
            body_html=full_pretext.get("body_html", ""),
            body_text=full_pretext.get("body_text", ""),
            variables_used=full_pretext.get("variables_used", []),
            estimated_difficulty=full_pretext.get("difficulty", request.difficulty),
            red_flags=full_pretext.get("red_flags", []),
            reasoning=(
                f"Selected '{full_pretext.get('name', 'unknown')}' from built-in library. "
                f"Category: {full_pretext.get('category', 'unknown')}, "
                f"Difficulty: {full_pretext.get('difficulty', '?')}. "
                f"Matched against request for {request.category} at difficulty {request.difficulty}. "
                f"No AI API key configured -- using template-based generation."
            ),
        )

    def _evaluate_rule_based(self, subject: str, body: str) -> dict[str, Any]:
        """Rule-based pretext evaluation without AI."""
        combined = f"{subject} {body}".lower()
        red_flags: list[str] = []
        strengths: list[str] = []
        weaknesses: list[str] = []
        suggestions: list[str] = []

        # Check for urgency indicators.
        urgency_words = ["urgent", "immediately", "expire", "deadline", "required", "action required"]
        urgency_count = sum(1 for w in urgency_words if w in combined)
        if urgency_count > 0:
            red_flags.append(f"Contains {urgency_count} urgency indicator(s): creates pressure to act quickly")
        if urgency_count > 2:
            weaknesses.append("Excessive urgency may make the email obviously suspicious")

        # Check for personalization variables.
        variables = re.findall(r"\{\{(\w+)\}\}", f"{subject} {body}")
        if "first_name" in variables:
            strengths.append("Uses recipient's first name for personalization")
        if "company" in variables:
            strengths.append("References company name for authenticity")
        if not variables:
            weaknesses.append("No personalization variables -- generic emails are easier to detect")
            suggestions.append("Add {{first_name}} and {{company}} variables for personalization")

        # Check for link/URL presence.
        if "{{login_url}}" in body or "href=" in body.lower():
            red_flags.append("Contains clickable link or URL -- primary phishing vector")
        else:
            weaknesses.append("No link present -- campaign tracking requires a clickable element")
            suggestions.append("Add a {{login_url}} call-to-action for click tracking")

        # Check for credential-related language.
        cred_words = ["password", "credential", "verify", "confirm", "login", "sign in", "account"]
        cred_count = sum(1 for w in cred_words if w in combined)
        if cred_count > 0:
            red_flags.append(f"References credentials/authentication ({cred_count} indicators)")

        # Check for threat language.
        threat_words = ["suspended", "terminated", "locked", "disabled", "penalty", "failure"]
        threat_count = sum(1 for w in threat_words if w in combined)
        if threat_count > 0:
            red_flags.append(f"Uses threatening language ({threat_count} indicators)")

        # Difficulty scoring.
        total_flags = len(red_flags)
        if total_flags >= 4:
            difficulty = 1
        elif total_flags >= 3:
            difficulty = 2
        elif total_flags >= 2:
            difficulty = 3
        elif total_flags >= 1:
            difficulty = 4
        else:
            difficulty = 5

        # Length analysis.
        body_length = len(body)
        if body_length < 100:
            weaknesses.append("Body is very short -- may appear suspicious")
            suggestions.append("Expand the email body with contextual details")
        elif body_length > 5000:
            weaknesses.append("Body is very long -- most phishing emails are concise")
            suggestions.append("Consider condensing the content for realism")
        else:
            strengths.append("Email length is appropriate for the format")

        if not weaknesses:
            strengths.append("Well-constructed pretext with no obvious deficiencies")

        return {
            "difficulty_score": difficulty,
            "red_flags": red_flags,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "suggestions": suggestions,
            "overall_assessment": (
                f"Difficulty {difficulty}/5 ({_DIFFICULTY_SIGNALS.get(difficulty, {}).get('label', 'Unknown')}). "
                f"Identified {len(red_flags)} red flag(s), {len(strengths)} strength(s), "
                f"and {len(weaknesses)} area(s) for improvement."
            ),
        }
