"""Phase 5 Match demo: public offline by default, private live only after consent."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Callable, Optional, Sequence

from agents.job_intelligence import JobIntelligenceAgent, public_offline_job_extraction
from agents.job_intelligence_evidence import JobEvidenceBuilder
from agents.match_context import MatchContextBuilder
from agents.match_insight import MatchInsightAgent, public_offline_match_extraction
from agents.self_discovery_demo import print_safe_summary as print_profile_summary
from agents.self_discovery_demo import run_demo as run_self_discovery_demo
from data.models import JobIntelligenceRecord, MatchResult, UserProfile
from providers.errors import LLMConfigurationError, LLMError, LLMStructuredOutputError
from providers.fake import FakeLLMProvider
from providers.models import GenerationOptions, StructuredLLMResponse, load_llm_settings
from providers.qwen import QwenProvider
from tools.job_data import MockJobDataProvider


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_PROFILE = REPOSITORY_ROOT / "data" / "fixtures" / "public_confirmed_profile.json"
PRIVATE_CONFIRMED_PROFILE = (
    REPOSITORY_ROOT / "data" / "private" / "golden_case" / "confirmed_profile.json"
)
LIVE_TITLES = ("AI Product Intern", "AI Application Engineer", "Data Analyst")


def load_public_profile() -> UserProfile:
    return UserProfile.model_validate_json(PUBLIC_PROFILE.read_text(encoding="utf-8"))


def build_offline_job_intelligence() -> list[JobIntelligenceRecord]:
    provider = MockJobDataProvider()
    jobs = provider.load()
    builder = JobEvidenceBuilder()
    agent = JobIntelligenceAgent(
        provider,
        FakeLLMProvider(
            None,
            predefined_responses=[
                public_offline_job_extraction(job, builder.build(job)) for job in jobs
            ],
        ),
        evidence_builder=builder,
    )
    return [agent.analyze(job) for job in jobs]


def run_offline_demo() -> list[tuple[JobIntelligenceRecord, MatchResult, StructuredLLMResponse]]:
    profile = load_public_profile()
    intelligence = build_offline_job_intelligence()
    builder = MatchContextBuilder()
    responses = [
        public_offline_match_extraction(builder.build(profile, item))
        for item in intelligence
    ]
    agent = MatchInsightAgent(
        FakeLLMProvider(None, predefined_responses=responses),
        context_builder=builder,
    )
    return [
        (item, *agent.analyze_with_details(profile, item)[:2])
        for item in intelligence
    ]


def _safe_profile_for_storage(profile: UserProfile) -> None:
    serialized = profile.model_dump_json()
    patterns = (
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        r"\b(?:student[_ -]?id|phone|address)\b",
        r"\b[569]\d{7}\b",
        r"DASHSCOPE_API_KEY",
        r"Authorization",
    )
    if any(re.search(pattern, serialized, re.IGNORECASE) for pattern in patterns):
        raise ValueError("Private profile contains a prohibited identifier category.")


def confirm_and_store_profile(
    draft: UserProfile,
    output_path: Path,
    *,
    input_fn: Callable[[str], str] = input,
) -> bool:
    """Require literal interactive `y`; every other response safely declines."""

    print("\nSafe private profile review")
    groups = (
        ("skills", draft.skills, "skill_id", "label"),
        ("interests", draft.interests, "interest_id", "label"),
        ("values", draft.values, "value_id", "label"),
        ("goals", draft.goals, "goal_id", "label"),
        ("strengths", draft.strengths, "statement_id", "text"),
        ("development areas", draft.development_areas, "statement_id", "text"),
        ("career preferences", draft.career_preferences, "preference_id", "label"),
    )
    for group_name, items, id_field, label_field in groups:
        for item in items:
            print(
                f"- {group_name}: {getattr(item, label_field)} "
                f"| signal={getattr(item, id_field)} "
                f"| evidence={','.join(item.evidence_ids)}"
            )
    answer = input_fn("\n是否确认这个 UserProfile 用于岗位匹配？ [y/N] ")
    if answer.strip().lower() != "y":
        print("Profile not confirmed; no file was written.")
        return False
    confirmed = draft.confirm()
    _safe_profile_for_storage(confirmed)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(confirmed.model_dump_json(indent=2), encoding="utf-8")
    print("Confirmed profile saved to the Git-ignored private path.")
    return True


def prepare_private_profile() -> int:
    if PRIVATE_CONFIRMED_PROFILE.exists():
        print("A confirmed private profile already exists at the Git-ignored local path.")
        return 0
    result = run_self_discovery_demo(live=True, fixture="private")
    print_profile_summary(result, live=True, fixture="private")
    confirm_and_store_profile(result.user_profile, PRIVATE_CONFIRMED_PROFILE)
    return 0


def run_private_live_demo() -> list[tuple[JobIntelligenceRecord, MatchResult, StructuredLLMResponse]]:
    if not PRIVATE_CONFIRMED_PROFILE.exists():
        raise FileNotFoundError("Confirmed private profile is absent.")
    profile = UserProfile.model_validate_json(
        PRIVATE_CONFIRMED_PROFILE.read_text(encoding="utf-8")
    )
    if not profile.confirmed:
        raise ValueError("Stored private profile is not confirmed.")
    settings = load_llm_settings(REPOSITORY_ROOT).require_live_qwen()
    intelligence_by_title = {
        item.role_title: item for item in build_offline_job_intelligence()
    }
    agent = MatchInsightAgent(
        QwenProvider.from_settings(settings),
        generation_options=GenerationOptions(
            model=settings.model,
            temperature=0.1,
            max_output_tokens=4096,
            thinking_enabled=False,
            timeout_seconds=60.0,
            max_retries=2,
        ),
    )
    results = []
    for title in LIVE_TITLES:
        intelligence = intelligence_by_title[title]
        result, response, _ = agent.analyze_with_details(profile, intelligence)
        results.append((intelligence, result, response))
    return results


def result_counts(result: MatchResult) -> dict[str, int]:
    return {
        "strong_alignment": len(result.alignments),
        "partial_alignment": len(result.partial_alignments),
        "evidence_missing": len(result.evidence_gaps),
        "confirmed_gap": len(result.confirmed_gaps),
        "experience_depth_gap": len(result.experience_depth_gaps),
        "preference_alignment": len(result.preference_alignments),
        "potential_friction": len(result.potential_frictions),
        "unknown": len(result.unknowns),
        "actions": len(result.action_items),
    }


def print_safe_results(
    results: list[tuple[JobIntelligenceRecord, MatchResult, StructuredLLMResponse]],
    *,
    live: bool,
) -> None:
    print("Orange Evidence-Based Match & Insight Demo")
    print(f"Mode: {'Private live' if live else 'Public offline'}")
    print("Ordering: Demo dataset order; no ranking")
    print("Evidence relationships only; no scoring")
    for intelligence, result, response in results:
        print(f"\n{intelligence.role_title}")
        print(" | ".join(f"{name}={value}" for name, value in result_counts(result).items()))
        if live:
            for insight in result.insights():
                link = insight.evidence_link
                safe_ids = [
                    *link.profile_evidence_ids,
                    *link.job_evidence_ids,
                ]
                print(
                    f"- {insight.title} | relation={insight.relation_type.value} "
                    f"| confidence={insight.confidence:.2f} "
                    f"| evidence={','.join(safe_ids) or 'signal-reference-only'}"
                )
            usage = response.usage
            print(
                "Usage: "
                f"input={usage.input_tokens if usage.input_tokens is not None else 'unavailable'}, "
                f"output={usage.output_tokens if usage.output_tokens is not None else 'unavailable'}, "
                f"total={usage.total_tokens if usage.total_tokens is not None else 'unavailable'}, "
                f"latency_ms={response.latency_ms}, retry_count={response.retry_count}"
            )
    if not live:
        print(f"\nAll {len(results)} roles completed offline with FakeLLMProvider.")
    print("No ranking, credentials, raw private evidence, prompts, or hidden reasoning displayed.")


def print_safe_validation_diagnostics(error: LLMStructuredOutputError) -> None:
    """Print structural failure metadata without raw model or private values."""

    print("Live Match failed: LLMStructuredOutputError.")
    for diagnostic in error.safe_diagnostics():
        print("Validation diagnostic:")
        for field in ("stage", "error_code", "loc", "type", "identifier", "message"):
            if field in diagnostic:
                print(f"- {field}: {diagnostic[field]}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Orange Phase 5 Match & Insight Demo")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--prepare-private-profile", action="store_true")
    group.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.prepare_private_profile:
            return prepare_private_profile()
        results = run_private_live_demo() if args.live else run_offline_demo()
        print_safe_results(results, live=args.live)
        return 0
    except FileNotFoundError:
        print("Private live Match not run: confirmed private profile is absent.")
        return 2
    except (LLMConfigurationError, ValueError):
        print("Private profile preparation or live Match did not pass a safe local gate.")
        return 2
    except LLMStructuredOutputError as exc:
        print_safe_validation_diagnostics(exc)
        return 1
    except LLMError as exc:
        print(f"Live Match failed: {type(exc).__name__}.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
