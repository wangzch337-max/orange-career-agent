"""Explicit Phase 3 Self-Discovery demo; offline by default, live only with --live."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from agents.self_discovery import SelfDiscoveryAgent, public_offline_extraction
from agents.self_discovery_models import SelfDiscoveryExtraction, SelfDiscoveryResult
from data.models import CourseRecord
from providers.errors import LLMConfigurationError, LLMError
from providers.fake import FakeLLMProvider
from providers.models import GenerationOptions, load_llm_settings
from providers.qwen import QwenProvider
from tools.course_data import MockCourseDataProvider


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_INPUT = REPOSITORY_ROOT / "data" / "fixtures" / "sample_user_input.json"
PRIVATE_INPUT = REPOSITORY_ROOT / "data" / "private" / "golden_case" / "profile_input.json"


def load_fixture(kind: str) -> Tuple[Dict[str, object], List[CourseRecord]]:
    if kind == "public":
        payload = json.loads(PUBLIC_INPUT.read_text(encoding="utf-8"))
        return payload, MockCourseDataProvider().load()
    payload = json.loads(PRIVATE_INPUT.read_text(encoding="utf-8"))
    courses = [
        CourseRecord(
            course_id=str(item["course_id"]),
            title=str(item["title"]),
            summary="课程名称由用户明确提供；未包含成绩或作业数据。",
            source="private_golden_case",
        )
        for item in payload.get("courses", [])
    ]
    return payload, courses


def run_demo(*, live: bool, fixture: str) -> SelfDiscoveryResult:
    user_input, courses = load_fixture(fixture)
    if live:
        settings = load_llm_settings(REPOSITORY_ROOT).require_live_qwen()
        provider = QwenProvider.from_settings(settings)
        options = GenerationOptions(
            model=settings.model,
            temperature=0.1,
            max_output_tokens=3000,
            thinking_enabled=False,
            timeout_seconds=60.0,
            max_retries=2,
        )
    else:
        response = public_offline_extraction() if fixture == "public" else SelfDiscoveryExtraction()
        provider = FakeLLMProvider(response)
        options = GenerationOptions(model="fake-self-discovery-v1", max_retries=0)
    agent = SelfDiscoveryAgent(
        MockCourseDataProvider(),
        provider,
        generation_options=options,
    )
    return agent.discover(user_input, courses)


def print_safe_summary(result: SelfDiscoveryResult, *, live: bool, fixture: str) -> None:
    profile = result.user_profile
    metadata = result.extraction_metadata
    print("Orange Self-Discovery Demo")
    print(f"模式：{'Live' if live else 'Offline'}")
    print(f"Fixture：{fixture}")
    print(f"Provider：{metadata.get('provider')}")
    print(f"Model：{metadata.get('model')}")
    print("Thinking：disabled")
    print("Prompt：self_discovery@v1")
    print(f"Evidence count：{metadata.get('evidence_count')}")
    print("✓ Strict structured parsing / Pydantic validation passed")
    print("✓ Evidence-ID validation passed")
    print("✓ Deterministic ProfileAssembler completed")
    print(f"Skills：{len(profile.skills)}")
    print(f"Interests：{len(profile.interests)}")
    print(f"Values：{len(profile.values)}")
    print(f"Goals：{len(profile.goals)}")
    print(f"Strengths：{len(profile.strengths)}")
    print(f"Development areas：{len(profile.development_areas)}")
    print(f"Career preferences：{len(profile.career_preferences)}")
    print(f"Uncertainties：{len(result.uncertainties)}")
    print(f"Clarification questions：{len(result.clarification_questions)}")
    print(f"Profile：v{profile.version} / {'confirmed' if profile.confirmed else 'draft'}")
    print(f"Input tokens：{result.usage.input_tokens if result.usage.input_tokens is not None else 'unavailable'}")
    print(f"Output tokens：{result.usage.output_tokens if result.usage.output_tokens is not None else 'unavailable'}")
    print(f"Total tokens：{result.usage.total_tokens if result.usage.total_tokens is not None else 'unavailable'}")
    print(f"Latency：{metadata.get('latency_ms')} ms")
    print(f"Retry count：{metadata.get('retry_count')}")
    if fixture == "private":
        print("\nSafe local signal review:")
        groups = (
            ("skills", profile.skills),
            ("interests", profile.interests),
            ("values", profile.values),
            ("goals", profile.goals),
            ("strengths", profile.strengths),
            ("development_areas", profile.development_areas),
            ("career_preferences", profile.career_preferences),
        )
        for group_name, items in groups:
            for item in items:
                label = getattr(item, "label", getattr(item, "text", "signal"))
                print(
                    f"- {group_name}: {label} | confidence={item.confidence:.2f} "
                    f"| inference={item.inference_type.value} | evidence={','.join(item.evidence_ids)}"
                )
        for uncertainty in result.uncertainties:
            print(
                f"- uncertainty: {uncertainty.topic} "
                f"| evidence={','.join(uncertainty.evidence_ids) or 'none'}"
            )
        for question in result.clarification_questions:
            print(
                f"- clarification: {question.question} "
                f"| evidence={','.join(question.related_evidence_ids) or 'none'}"
            )
    print("No raw prompt, private source text, credentials, or hidden reasoning stored.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Orange Phase 3 Self-Discovery Demo")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--fixture", choices=("public", "private"), default="public")
    args = parser.parse_args(argv)
    try:
        result = run_demo(live=args.live, fixture=args.fixture)
    except FileNotFoundError:
        print("Self-Discovery Demo 未运行：所选本地 fixture 不存在。")
        return 2
    except LLMConfigurationError:
        print("Self-Discovery Demo 未运行：本地 Qwen 配置不完整。")
        return 2
    except LLMError as exc:
        print(f"Self-Discovery Demo 失败：{type(exc).__name__}。")
        return 1
    print_safe_summary(result, live=args.live, fixture=args.fixture)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
