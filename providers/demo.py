"""Isolated Phase 2 structured-extraction Demo.

Default mode is deterministic and offline. Only ``--live`` constructs QwenProvider.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from providers.errors import LLMConfigurationError, LLMError
from providers.fake import FakeLLMProvider
from providers.models import (
    ExtractedGoal,
    ExtractedInterest,
    ExtractedSkill,
    GenerationOptions,
    ProfileSignalExtraction,
    ProfileSignalInput,
    StructuredLLMResponse,
    load_llm_settings,
)
from providers.prompts import (
    PROMPT_NAME,
    PROMPT_VERSION,
    build_profile_signal_messages,
    load_profile_signal_prompt,
)
from providers.qwen import QwenProvider


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INPUT_FIXTURE = REPOSITORY_ROOT / "data" / "fixtures" / "sample_profile_signal_input.json"


def load_demo_input() -> ProfileSignalInput:
    payload = json.loads(INPUT_FIXTURE.read_text(encoding="utf-8"))
    return ProfileSignalInput.model_validate(payload)


def offline_response() -> ProfileSignalExtraction:
    """Deterministic fixture output; it does not infer from edited prose."""

    return ProfileSignalExtraction(
        candidate_skills=[
            ExtractedSkill(
                label="Artificial Intelligence",
                confidence=0.88,
                evidence_ids=["source_001", "source_002"],
            ),
            ExtractedSkill(
                label="AI Prototype Development",
                confidence=0.82,
                evidence_ids=["source_002"],
            ),
        ],
        interest_signals=[
            ExtractedInterest(
                label="AI Product Design",
                confidence=0.91,
                evidence_ids=["source_003"],
            )
        ],
        goal_signals=[
            ExtractedGoal(
                label="Explore AI product careers",
                confidence=0.89,
                evidence_ids=["source_003"],
            )
        ],
    )


def run_offline_demo() -> StructuredLLMResponse[ProfileSignalExtraction]:
    demo_input = load_demo_input()
    prompt = load_profile_signal_prompt()
    provider = FakeLLMProvider(offline_response())
    response = provider.generate_structured(
        build_profile_signal_messages(prompt, demo_input.source_evidence),
        ProfileSignalExtraction,
        GenerationOptions(model="fake-profile-signal-v1", max_retries=0),
        prompt_name=PROMPT_NAME,
        prompt_version=PROMPT_VERSION,
    )
    response.data.validate_evidence_ids(demo_input.source_evidence)
    return response


def run_live_demo() -> StructuredLLMResponse[ProfileSignalExtraction]:
    settings = load_llm_settings(REPOSITORY_ROOT).require_live_qwen()
    demo_input = load_demo_input()
    prompt = load_profile_signal_prompt()
    provider = QwenProvider.from_settings(settings)
    response = provider.generate_structured(
        build_profile_signal_messages(prompt, demo_input.source_evidence),
        ProfileSignalExtraction,
        GenerationOptions(
            model=settings.model,
            temperature=0.1,
            max_output_tokens=800,
            thinking_enabled=False,
            timeout_seconds=30.0,
            max_retries=2,
        ),
        prompt_name=PROMPT_NAME,
        prompt_version=PROMPT_VERSION,
    )
    response.data.validate_evidence_ids(demo_input.source_evidence)
    return response


def print_safe_summary(
    response: StructuredLLMResponse[ProfileSignalExtraction],
    *,
    live: bool,
) -> None:
    usage = response.usage
    print("Orange LLM Provider Demo")
    print(f"\n模式：{'Live' if live else 'Offline'}")
    print(f"Provider：{response.provider}")
    print(f"Model：{response.model}")
    print("Thinking：disabled")
    print(f"Prompt：{response.prompt_name}@{response.prompt_version}")
    print("\n✓ 收到结构化响应")
    print("✓ JSON Schema / Pydantic 验证通过")
    print("✓ Evidence ID 验证通过")
    if not live:
        print("✓ FakeLLMProvider 未进行网络调用")
    print(f"\n候选技能：{len(response.data.candidate_skills)}")
    print(f"兴趣信号：{len(response.data.interest_signals)}")
    print(f"目标信号：{len(response.data.goal_signals)}")
    print("\nUsage：")
    print(f"input tokens：{usage.input_tokens if usage.input_tokens is not None else 'unavailable'}")
    print(f"output tokens：{usage.output_tokens if usage.output_tokens is not None else 'unavailable'}")
    print(f"total tokens：{usage.total_tokens if usage.total_tokens is not None else 'unavailable'}")
    print(f"Latency：{response.latency_ms} ms")
    print("\nNo hidden chain-of-thought stored.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Orange Phase 2 provider Demo")
    parser.add_argument("--live", action="store_true", help="调用本地配置的 Qwen provider")
    args = parser.parse_args(argv)
    try:
        response = run_live_demo() if args.live else run_offline_demo()
    except LLMConfigurationError:
        print("Live Demo 未运行：本地 Qwen 配置不完整。")
        return 2
    except LLMError as exc:
        print(f"Live Demo 失败：{type(exc).__name__}。")
        return 1
    print_safe_summary(response, live=args.live)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
