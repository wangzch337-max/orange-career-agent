"""Explicit Phase 4 Job Intelligence demo; offline by default."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from agents.job_intelligence import JobIntelligenceAgent, public_offline_job_extraction
from agents.job_intelligence_evidence import JobEvidenceBuilder
from data.models import JobIntelligenceRecord, JobRecord
from providers.errors import LLMConfigurationError, LLMError
from providers.fake import FakeLLMProvider
from providers.models import GenerationOptions, StructuredLLMResponse, load_llm_settings
from providers.qwen import QwenProvider
from tools.job_data import MockJobDataProvider


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LIVE_TITLES = ("AI Product Intern", "AI Application Engineer", "Data Analyst")


def _counts(record: JobIntelligenceRecord) -> dict[str, int]:
    return {
        "actual_work": len(record.actual_work),
        "required_capabilities": len(record.required_capabilities),
        "preferred_capabilities": len(record.preferred_capabilities),
        "technology_signals": len(record.technology_signals),
        "work_style": len(record.work_style),
        "growth_exposure": len(record.growth_exposure),
        "potential_friction": len(record.potential_friction),
        "uncertainties": len(record.uncertainties),
    }


def run_offline_demo() -> list[tuple[JobRecord, JobIntelligenceRecord, StructuredLLMResponse]]:
    provider = MockJobDataProvider()
    jobs = provider.load()
    builder = JobEvidenceBuilder()
    fake = FakeLLMProvider(
        None,
        predefined_responses=[
            public_offline_job_extraction(job, builder.build(job)) for job in jobs
        ],
    )
    agent = JobIntelligenceAgent(provider, fake, evidence_builder=builder)
    return [(job, *agent.analyze_with_details(job)[:2]) for job in jobs]


def run_live_demo() -> list[tuple[JobRecord, JobIntelligenceRecord, StructuredLLMResponse]]:
    settings = load_llm_settings(REPOSITORY_ROOT).require_live_qwen()
    provider = MockJobDataProvider()
    jobs_by_title = {job.title: job for job in provider.load()}
    agent = JobIntelligenceAgent(
        provider,
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
        job = jobs_by_title[title]
        record, response, _ = agent.analyze_with_details(job)
        results.append((job, record, response))
    return results


def print_safe_summary(
    results: list[tuple[JobRecord, JobIntelligenceRecord, StructuredLLMResponse]],
    *,
    live: bool,
) -> None:
    print("Orange Job Intelligence Demo")
    print(f"Mode: {'Live' if live else 'Offline'}")
    print("Prompt: job_intelligence@v1")
    print("Thinking: disabled")
    for job, record, response in results:
        counts = _counts(record)
        print(f"\n{job.title} | {job.role_family.value} | {job.city}, {job.region.value}")
        print("Structured parsing: passed")
        print("Evidence-ID validation: passed")
        print(" | ".join(f"{name}={value}" for name, value in counts.items()))
        if live:
            groups = (
                ("actual_work", record.actual_work),
                ("required_capabilities", record.required_capabilities),
                ("preferred_capabilities", record.preferred_capabilities),
                ("technology_signals", record.technology_signals),
                ("work_style", record.work_style),
                ("growth_exposure", record.growth_exposure),
                ("potential_friction", record.potential_friction),
            )
            for group_name, signals in groups:
                for signal in signals:
                    print(
                        f"- {group_name}: {signal.label} | confidence={signal.confidence:.2f} "
                        f"| inference={signal.inference_type.value} "
                        f"| evidence={','.join(signal.evidence_ids)}"
                    )
            print("- uncertainties: " + ", ".join(item.topic for item in record.uncertainties))
            usage = response.usage
            print(
                "Usage: "
                f"input={usage.input_tokens if usage.input_tokens is not None else 'unavailable'}, "
                f"output={usage.output_tokens if usage.output_tokens is not None else 'unavailable'}, "
                f"total={usage.total_tokens if usage.total_tokens is not None else 'unavailable'}, "
                f"latency_ms={response.latency_ms}, retry_count={response.retry_count}"
            )
    if not live:
        print(f"\nAll {len(results)} Fictional Demo Job Records completed without network access.")
    print("No credentials, raw requests, full prompts, or hidden reasoning displayed.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Orange Phase 4 Job Intelligence Demo")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Call Qwen exactly once for each of the three representative roles.",
    )
    args = parser.parse_args(argv)
    try:
        results = run_live_demo() if args.live else run_offline_demo()
    except LLMConfigurationError:
        print("Live Demo not run: local Qwen configuration is incomplete.")
        return 2
    except LLMError as exc:
        print(f"Live Demo failed: {type(exc).__name__}.")
        return 1
    print_safe_summary(results, live=args.live)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
