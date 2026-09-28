"""Provider-independent, evidence-backed Phase 4 Job Intelligence Agent."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from agents.base import BaseAgent, record_agent_event, record_tool_event
from agents.job_intelligence_assembler import JobIntelligenceAssembler
from agents.job_intelligence_evidence import JobEvidenceBuilder
from agents.job_intelligence_models import (
    JobEvidenceBundle,
    JobEvidenceCategory,
    JobExtractionSignal,
    JobIntelligenceExtraction,
)
from data.models import (
    AgentName,
    EventType,
    JobIntelligenceRecord,
    JobRecord,
    JobSignalInferenceType,
    JobUncertainty,
    Severity,
)
from providers.base import LLMProvider
from providers.models import GenerationOptions, StructuredLLMResponse
from providers.prompts import (
    JOB_INTELLIGENCE_PROMPT_NAME,
    JOB_INTELLIGENCE_PROMPT_VERSION,
    build_job_intelligence_messages,
    load_job_intelligence_prompt,
)
from tools.base import JobDataProvider
from workflows.stages import ProfileNotConfirmedError, WorkflowStage
from workflows.state import WorkflowState


def _evidence_for(
    evidence: JobEvidenceBundle,
    category: JobEvidenceCategory,
) -> list:
    return [item for item in evidence.source_evidence if item.category == category]


def _explicit_signals(items: Iterable, *, prefix: str = "") -> List[JobExtractionSignal]:
    return [
        JobExtractionSignal(
            label=f"{prefix}{item.text}",
            description=item.text,
            confidence=1.0,
            evidence_ids=[item.id],
            inference_type=JobSignalInferenceType.EXPLICIT_JOB_FACT,
        )
        for item in items
    ]


def public_offline_job_extraction(
    job: JobRecord,
    evidence: Optional[JobEvidenceBundle] = None,
) -> JobIntelligenceExtraction:
    """Build a canned response from fixture fields before FakeLLMProvider runs.

    This helper deliberately performs no free-text parsing. It exists only to make
    every public Demo role deterministic and network-free.
    """

    bundle = evidence or JobEvidenceBuilder().build(job)
    summary = _evidence_for(bundle, JobEvidenceCategory.SUMMARY)[0]
    responsibilities = _evidence_for(bundle, JobEvidenceCategory.RESPONSIBILITY)
    technologies = _evidence_for(bundle, JobEvidenceCategory.TECHNOLOGY)
    first_responsibility = responsibilities[0]
    first_technology = technologies[0]
    inferred = JobSignalInferenceType.EVIDENCE_SUPPORTED_JOB_INFERENCE
    return JobIntelligenceExtraction(
        actual_work=_explicit_signals(responsibilities),
        required_capabilities=_explicit_signals(
            _evidence_for(bundle, JobEvidenceCategory.REQUIREMENT)
        ),
        preferred_capabilities=_explicit_signals(
            _evidence_for(bundle, JobEvidenceCategory.PREFERRED_QUALIFICATION)
        ),
        technology_signals=_explicit_signals(technologies),
        work_style_signals=[
            JobExtractionSignal(
                label="Evidence-defined delivery work",
                description="The role summary describes a concrete delivery context without implying personality traits.",
                confidence=0.78,
                evidence_ids=[summary.id],
                inference_type=inferred,
            )
        ],
        collaboration_context=[
            JobExtractionSignal(
                label="Collaboration described in the role summary",
                description="Collaboration context is limited to the parties explicitly named in the summary.",
                confidence=0.78,
                evidence_ids=[summary.id],
                inference_type=inferred,
            )
        ],
        growth_exposure=[
            JobExtractionSignal(
                label=f"Exposure to {first_technology.text}",
                description="The stated responsibility and technology may provide hands-on exposure; no career-path prediction is made.",
                confidence=0.76,
                evidence_ids=[first_responsibility.id, first_technology.id],
                inference_type=inferred,
            )
        ],
        potential_friction=[
            JobExtractionSignal(
                label="Sustained responsibility-specific delivery",
                description=f"The role includes recurring focus on: {first_responsibility.text}",
                confidence=0.72,
                evidence_ids=[first_responsibility.id],
                inference_type=inferred,
            )
        ],
        job_uncertainties=[
            JobUncertainty(topic=topic, reason=reason, importance=importance)
            for topic, reason, importance in (
                ("salary", "The Demo Job Record does not provide salary information.", Severity.HIGH),
                ("promotion_path", "The Demo Job Record does not provide a promotion path.", Severity.MEDIUM),
                ("work_life_balance", "The Demo Job Record does not describe workload or work-life balance.", Severity.HIGH),
                ("remote_work_policy", "The Demo Job Record does not state a remote-work policy.", Severity.MEDIUM),
                ("team_size", "The Demo Job Record does not state team size.", Severity.LOW),
                ("exact_technology_stack", "Technology tags do not define the complete implementation stack.", Severity.MEDIUM),
            )
        ],
    )


class JobIntelligenceAgent(BaseAgent):
    """Interpret JobRecord evidence through an injected LLMProvider."""

    name = AgentName.JOB_INTELLIGENCE

    def __init__(
        self,
        job_provider: JobDataProvider,
        llm_provider: LLMProvider,
        *,
        evidence_builder: Optional[JobEvidenceBuilder] = None,
        assembler: Optional[JobIntelligenceAssembler] = None,
        generation_options: Optional[GenerationOptions] = None,
    ) -> None:
        self.job_provider = job_provider
        self.llm_provider = llm_provider
        self.evidence_builder = evidence_builder or JobEvidenceBuilder()
        self.assembler = assembler or JobIntelligenceAssembler()
        self.generation_options = generation_options or GenerationOptions(
            model="fake-job-intelligence-v1",
            max_output_tokens=4096,
            max_retries=0,
        )

    def _analyze(
        self,
        job: JobRecord,
    ) -> tuple[JobIntelligenceRecord, StructuredLLMResponse, JobEvidenceBundle]:
        evidence = self.evidence_builder.build(job)
        response = self.llm_provider.generate_structured(
            build_job_intelligence_messages(
                load_job_intelligence_prompt(),
                evidence.source_evidence,
            ),
            JobIntelligenceExtraction,
            self.generation_options,
            prompt_name=JOB_INTELLIGENCE_PROMPT_NAME,
            prompt_version=JOB_INTELLIGENCE_PROMPT_VERSION,
        )
        response.data.validate_evidence_ids(evidence.source_evidence)
        metadata: Dict[str, object] = response.safe_metadata()
        metadata.update(
            evidence_count=len(evidence.source_evidence),
            signal_counts=response.data.signal_counts(),
        )
        record = self.assembler.assemble(
            job=job,
            extraction=response.data,
            evidence=evidence,
            analysis_metadata=metadata,
        )
        return record, response, evidence

    def analyze(self, job: JobRecord) -> JobIntelligenceRecord:
        """Standalone analysis; intentionally requires no UserProfile."""

        record, _, _ = self._analyze(job)
        return record

    def analyze_with_details(
        self,
        job: JobRecord,
    ) -> tuple[JobIntelligenceRecord, StructuredLLMResponse, JobEvidenceBundle]:
        """Return safe response metadata for the explicit demo/validation command."""

        return self._analyze(job)

    def run(self, state: WorkflowState) -> WorkflowState:
        if state.stage != WorkflowStage.JOB_INTELLIGENCE:
            raise ValueError("Job Intelligence Agent 只能在 job_intelligence 阶段运行")
        if not state.profile_confirmed:
            raise ProfileNotConfirmedError("用户画像未确认，不能执行岗位情报阶段")

        state = record_agent_event(
            state,
            self.name,
            EventType.JOB_INTELLIGENCE_STARTED,
            "开始执行 evidence-backed Job Intelligence。",
        )
        state = record_tool_event(
            state,
            self.job_provider.name,
            EventType.TOOL_CALLED,
            "读取公开的 Fictional Demo Job Records。",
        )
        jobs = self.job_provider.load()
        state = record_tool_event(
            state,
            self.job_provider.name,
            EventType.TOOL_COMPLETED,
            "Demo Job Records 读取完成。",
            {"record_count": len(jobs)},
        )

        records: List[JobIntelligenceRecord] = []
        evidence_count = 0
        signal_totals: Dict[str, int] = {}
        usage_totals = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "latency_ms": 0,
            "retry_count": 0,
        }
        provider = None
        model = None
        for job in jobs:
            record, response, evidence = self._analyze(job)
            records.append(record)
            evidence_count += len(evidence.source_evidence)
            provider = response.provider
            model = response.model
            for name, count in response.data.signal_counts().items():
                signal_totals[name] = signal_totals.get(name, 0) + count
            for name in ("input_tokens", "output_tokens", "total_tokens"):
                value = getattr(response.usage, name)
                if value is not None:
                    usage_totals[name] += value
            usage_totals["latency_ms"] += response.latency_ms
            usage_totals["retry_count"] += response.retry_count

        evidence_ids = [item.id for record in records for item in record.evidence]
        safe = {
            "job_count": len(jobs),
            "evidence_count": evidence_count,
            "signal_counts": signal_totals,
            "provider": provider,
            "model": model,
            "prompt_name": JOB_INTELLIGENCE_PROMPT_NAME,
            "prompt_version": JOB_INTELLIGENCE_PROMPT_VERSION,
            **usage_totals,
        }
        state = record_agent_event(
            state,
            self.name,
            EventType.JOB_EVIDENCE_BUILT,
            "确定性岗位证据已建立。",
            evidence_ids,
            {"job_count": len(jobs), "evidence_count": evidence_count},
        )
        state = record_agent_event(
            state,
            self.name,
            EventType.JOB_LLM_EXTRACTION_COMPLETED,
            "结构化岗位语义抽取完成。",
            safe_metadata=safe,
        )
        state = record_agent_event(
            state,
            self.name,
            EventType.JOB_EVIDENCE_VALIDATION_COMPLETED,
            "所有岗位信号的 evidence ID 已通过确定性校验。",
            safe_metadata={"evidence_count": evidence_count},
        )
        state = state.validated_copy(job_records=jobs, job_intelligence=records)
        state = record_agent_event(
            state,
            self.name,
            EventType.JOB_INTELLIGENCE_ASSEMBLED,
            "确定性 JobIntelligenceAssembler 已生成权威记录。",
            evidence_ids,
            {"record_count": len(records), "signal_counts": signal_totals},
        )
        state = record_agent_event(
            state,
            self.name,
            EventType.JOB_UNCERTAINTIES_IDENTIFIED,
            "缺失岗位信息已保留为未知。",
            safe_metadata={
                "uncertainty_count": signal_totals.get("job_uncertainties", 0)
            },
        )
        return record_agent_event(
            state,
            self.name,
            EventType.JOB_INTELLIGENCE_COMPLETED,
            f"完成 {len(records)} 条岗位情报记录。",
            evidence_ids,
            safe,
        )
