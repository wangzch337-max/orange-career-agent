"""Versioned, strict evaluation contracts and explicit expectation families."""

from enum import Enum
from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator, field_serializer

from data.models import DomainModel, MatchRelationType
from evaluation.taxonomy import FailureTaxonomy, EvaluationSeverity, severity_for


class EvaluationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    EXPECTED_UNCERTAINTY = "EXPECTED_UNCERTAINTY"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class EvaluationLayer(str, Enum):
    CONTRACT = "deterministic_contract"
    SEMANTIC = "semantic_golden"
    JOURNEY = "end_to_end_journey"


class Capability(str, Enum):
    SELF_DISCOVERY = "self_discovery"
    JOB_INTELLIGENCE = "job_intelligence"
    MATCH = "match"
    MEMORY = "memory"
    CONVERSATION = "conversation"
    ACTION = "action"
    END_TO_END = "end_to_end"


class ExpectationBase(DomainModel):
    check_id: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    summary: str = Field(min_length=1)
    taxonomy: FailureTaxonomy
    source_component: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    memory_refs: list[str] = Field(default_factory=list)


class RequiredExpectation(ExpectationBase):
    kind: Literal["required"] = "required"
    path: str
    operation: Literal["equals", "contains", "subset", "nonempty", "empty", "gte"] = "equals"
    expected: JsonValue = True


class ForbiddenExpectation(ExpectationBase):
    kind: Literal["forbidden"] = "forbidden"
    path: str
    forbidden: list[JsonValue] = Field(min_length=1)
    mode: Literal["values", "keys", "claim_fragments"] = "values"


class UncertaintyExpectation(ExpectationBase):
    kind: Literal["uncertainty"] = "uncertainty"
    path: str
    topics: list[str] = Field(min_length=1)


class ProvenanceExpectation(ExpectationBase):
    kind: Literal["provenance"] = "provenance"
    path: str
    scope: Literal["evidence", "memory", "actions"]


class RelationExpectation(ExpectationBase):
    kind: Literal["relation"] = "relation"
    path: str = "relations"
    relation: MatchRelationType
    job_label: str | None = None
    forbidden_substitutions: list[MatchRelationType] = Field(default_factory=list)


class LifecycleExpectation(RequiredExpectation):
    kind: Literal["lifecycle"] = "lifecycle"


class WorkflowExpectation(RequiredExpectation):
    kind: Literal["workflow"] = "workflow"


class ReviewExpectation(ExpectationBase):
    """Only an explicit non-contract presentation ambiguity can request review."""

    kind: Literal["review"] = "review"
    taxonomy: Literal[FailureTaxonomy.PRESENTATION_AMBIGUITY] = FailureTaxonomy.PRESENTATION_AMBIGUITY
    path: str


Expectation = Annotated[
    RequiredExpectation | ForbiddenExpectation | UncertaintyExpectation |
    ProvenanceExpectation | RelationExpectation | LifecycleExpectation |
    WorkflowExpectation | ReviewExpectation,
    Field(discriminator="kind"),
]


class GoldenScenario(DomainModel):
    scenario_id: str = Field(pattern=r"^(SD|JI|MI|MEM|CONV|ACT|E2E)_[0-9]{3}$")
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    layer: EvaluationLayer
    capability: Capability
    input_fixture_refs: list[str] = Field(min_length=1)
    expected_status: EvaluationStatus
    tags: list[str] = Field(min_length=1)
    checks: list[Expectation] = Field(min_length=1)
    expected_failures_allowed: list[FailureTaxonomy] = Field(default_factory=list)
    notes: str = ""
    journey_steps: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_contract(self):
        ids = [item.check_id for item in self.checks]
        if len(ids) != len(set(ids)):
            raise ValueError("Check IDs must be unique within a scenario")
        if set(ids).intersection({"zero_network", "zero_private_access", "execution_completed"}):
            raise ValueError("Runner boundary check IDs are reserved")
        if self.expected_failures_allowed:
            raise ValueError("v1 never waives contract failures; list must be empty")
        if self.expected_status == EvaluationStatus.EXPECTED_UNCERTAINTY and not any(
            isinstance(item, UncertaintyExpectation) for item in self.checks
        ):
            raise ValueError("Expected uncertainty requires an explicit uncertainty check")
        if self.layer == EvaluationLayer.JOURNEY and not self.journey_steps:
            raise ValueError("Journey scenarios require ordered steps")
        return self


DiagnosticEventRef = Annotated[str, Field(pattern=r"^evt_[0-9a-f]{32}$")]


class EvaluationFailure(DomainModel):
    related_event_ids: list[DiagnosticEventRef] = Field(default_factory=list, max_length=8, exclude=True)
    failure_id: str
    taxonomy: FailureTaxonomy
    scenario_id: str
    check_id: str
    summary: str
    expected: JsonValue
    observed: JsonValue
    source_component: str
    evidence_refs: list[str] = Field(default_factory=list)
    memory_refs: list[str] = Field(default_factory=list)
    severity: EvaluationSeverity

    @model_validator(mode="after")
    def fixed_severity(self):
        if self.severity != severity_for(self.taxonomy):
            raise ValueError("Severity may not downgrade a taxonomy category")
        return self


class CheckResult(DomainModel):
    related_event_ids: list[DiagnosticEventRef] = Field(default_factory=list, max_length=8, exclude=True)
    check_id: str
    kind: str
    summary: str
    passed: bool
    review_triggered: bool = False
    failure: EvaluationFailure | None = None


class ScenarioResult(DomainModel):
    diagnostic_run_id: str | None = Field(default=None, exclude=True, pattern=r"^diag_[0-9a-f]{32}$")
    scenario_id: str
    title: str
    layer: EvaluationLayer
    capability: Capability
    expected_status: EvaluationStatus
    status: EvaluationStatus
    checks: list[CheckResult]
    findings: list[EvaluationFailure]


class RunMetadata(DomainModel):
    run_id: str
    timestamp: str
    git_commit: str | None
    python_version: str
    selected_scenario_count: int
    executed_scenario_count: int
    selected_tags: list[str]
    llm_provider: Literal["FakeLLMProvider"] = "FakeLLMProvider"
    embedding_provider: Literal["FakeEmbeddingProvider"] = "FakeEmbeddingProvider"
    mode: Literal["offline_synthetic"] = "offline_synthetic"
    network_attempt_count: int = 0
    private_access_attempt_count: int = 0


class EvaluationSummary(DomainModel):
    total: int
    pass_count: int = Field(serialization_alias="pass", validation_alias="pass")
    fail: int
    expected_uncertainty: int
    needs_review: int

    model_config = {**DomainModel.model_config, "populate_by_name": True, "serialize_by_alias": True}


class EvaluationReport(DomainModel):
    schema_version: Literal["orange.evaluation.v1"] = "orange.evaluation.v1"
    run: RunMetadata
    summary: EvaluationSummary
    scenarios: list[ScenarioResult]

    @field_serializer("scenarios")
    def correlated_scenarios(self, values):
        # Dynamic correlation belongs to report transport, not deterministic scenario snapshots.
        rows = []
        for scenario in values:
            row = scenario.model_dump(mode="json")
            row["diagnostic_run_id"] = scenario.diagnostic_run_id
            for data, check in zip(row["checks"], scenario.checks):
                data["related_event_ids"] = check.related_event_ids
                if check.failure is not None:
                    data["failure"]["related_event_ids"] = check.failure.related_event_ids
            for data, finding in zip(row["findings"], scenario.findings):
                data["related_event_ids"] = finding.related_event_ids
            rows.append(row)
        return rows
