"""Deterministic, context-grounded rendering for authoritative Match actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from data.models import ActionType, MatchInsight


@dataclass(frozen=True)
class RenderedActionText:
    """User-visible action text produced without provider-authored prose."""

    description: str
    expected_evidence: str
    rationale: str


class ActionRenderer:
    """Render safe action wording from validated semantic action intent."""

    _RATIONALES = {
        ActionType.VERIFY_EXISTING_CAPABILITY: (
            "The related evidence-missing insight requires verification before any "
            "capability-gap inference."
        ),
        ActionType.BUILD_PORTFOLIO_EVIDENCE: (
            "The related insight supports creating verifiable portfolio evidence "
            "without selecting a tool or framework."
        ),
        ActionType.DEEPEN_CAPABILITY: (
            "The related confirmed or experience-depth gap supports a focused "
            "capability-deepening step."
        ),
        ActionType.GAIN_PRACTICAL_EXPERIENCE: (
            "The related confirmed or experience-depth gap supports gaining "
            "verifiable practical experience."
        ),
        ActionType.CLARIFY_PREFERENCE: (
            "The related preference uncertainty requires user confirmation rather "
            "than an inferred preference."
        ),
        ActionType.INVESTIGATE_JOB_UNKNOWN: (
            "The related job unknown requires reliable role information rather than "
            "an invented answer."
        ),
    }

    def render(
        self,
        *,
        action_type: ActionType,
        target_label: str,
        related_insights: Sequence[MatchInsight],
    ) -> RenderedActionText:
        """Return generic wording containing only the exact validated target label."""

        if not related_insights:
            raise ValueError("Action rendering requires at least one validated insight")

        demonstrable_target = self._with_experience_suffix(target_label)
        descriptions = {
            ActionType.VERIFY_EXISTING_CAPABILITY: (
                "Review existing course and project evidence to determine whether "
                f"you already have demonstrable {demonstrable_target}."
            ),
            ActionType.BUILD_PORTFOLIO_EVIDENCE: (
                f"Create a small portfolio artifact demonstrating {target_label}."
            ),
            ActionType.DEEPEN_CAPABILITY: (
                f"Complete a focused exercise or project to deepen {target_label}."
            ),
            ActionType.GAIN_PRACTICAL_EXPERIENCE: (
                f"Gain hands-on experience applying {target_label} in a realistic task."
            ),
            ActionType.CLARIFY_PREFERENCE: (
                f"Clarify your current preference regarding {target_label}."
            ),
            ActionType.INVESTIGATE_JOB_UNKNOWN: (
                f"Investigate the role information related to {target_label}."
            ),
        }
        expected_evidence = {
            ActionType.VERIFY_EXISTING_CAPABILITY: (
                f"One or more verifiable examples of {target_label} use, or an explicit "
                "confirmation that no such experience currently exists."
            ),
            ActionType.BUILD_PORTFOLIO_EVIDENCE: (
                f"A verifiable artifact demonstrating {target_label}."
            ),
            ActionType.DEEPEN_CAPABILITY: (
                f"A verifiable exercise or project demonstrating deeper {target_label}."
            ),
            ActionType.GAIN_PRACTICAL_EXPERIENCE: (
                f"A verifiable record of applying {target_label} in a realistic task."
            ),
            ActionType.CLARIFY_PREFERENCE: (
                f"A user-confirmed preference statement regarding {target_label}."
            ),
            ActionType.INVESTIGATE_JOB_UNKNOWN: (
                f"A reliable source clarifying {target_label}."
            ),
        }
        return RenderedActionText(
            description=descriptions[action_type],
            expected_evidence=expected_evidence[action_type],
            rationale=self._RATIONALES[action_type],
        )

    @staticmethod
    def _with_experience_suffix(target_label: str) -> str:
        """Add `experience` only when the exact target does not already contain it."""

        target = target_label.strip()
        if "experience" in target.casefold().split():
            if target.casefold().startswith("experience "):
                return "experience " + target[len("experience ") :]
            return target
        return f"{target} experience"
