"""Code-owned tools over existing read/refinement services, with no arbitrary IO."""

from dataclasses import dataclass

from agents.job_intelligence_evidence import JobEvidenceBuilder
from data.models import EvidenceSourceType
from memory.models import StructuredSessionSignal, MemoryStatus, MemoryType, MemoryChangeChoice
from memory.integration import StructuredSignalPolicyRegistry
from tools.job_data import MockJobDataProvider
from career_runtime.models import (
    ContextItem, Proposal, Reference, Relevance, ToolInput, ToolName, ToolRequest, ToolResult,
)


@dataclass(frozen=True)
class ToolSpec:
    name: ToolName
    description: str
    permission: str
    stage: str


SPECS = (
    ToolSpec(ToolName.PROFILE, "读取当前已确认画像的选定字段，不返回整个画像", "read", "profile"),
    ToolSpec(ToolName.MEMORY, "ROLE_EXPLORATION：相关已确认历史偏好/目标，最多三条", "read", "memory"),
    ToolSpec(ToolName.GOALS, "读取已确认的目标及职业偏好（兴趣不等于能力）", "read", "profile"),
    ToolSpec(ToolName.EVIDENCE, "读取当前画像已有的课程/项目证据，缺失则未知", "read", "evidence"),
    ToolSpec(ToolName.ROLE, "读取公开本地岗位 archetype 的来源证据，不是实时招聘", "read", "role"),
    ToolSpec(ToolName.MATCH, "只读取同一已确认画像版本的既有 validated Match，不生成新结论", "read", "match"),
    ToolSpec(ToolName.PROFILE_DRAFT, "调用既有 refinement 生成 vN+1 待复核草稿，不确认", "candidate", "candidate"),
    ToolSpec(ToolName.MEMORY_CANDIDATE, "提出当前用户原文的 Memory 候选，用户复核后才保存", "candidate", "candidate"),
)


class ToolRegistry:
    def __init__(self, workspace, user_text: str, *, proposal_permission: bool):
        self.workspace = workspace
        self.user_text = user_text
        self.proposal_permission = proposal_permission
        self.specs = {item.name: item for item in SPECS}
        self.proposals: list[Proposal] = []
        self.profile_drafts = []
        self.memory_changes = {}
        self.context_profile_stamp = None
        self.roles = {job.job_id: job for job in MockJobDataProvider().load()
                      if job.job_id in {"job_001", "job_007", "job_013"}}

    def catalog(self):
        return [{"name": item.name.value, "description": item.description,
                 "permission": item.permission} for item in SPECS]

    def profile(self):
        return self.workspace.memory_service.get_current_confirmed_profile(self.workspace.subject_id)

    def authority_summary(self):
        current = self.profile()
        self.context_profile_stamp = {"profile_id": current.profile_id, "version": current.version} if current else None
        return {"confirmed_profile_available": current is not None,
                "profile_version": current.version if current else None,
                "proposal_permission": self.proposal_permission,
                "known_roles": [{"role_id": key, "title": job.title} for key, job in self.roles.items()]}

    def conversation_citations(self, messages, plan):
        """Reuse ONLY already-cited profile evidence still owned by exact version.

        Dialogue is not canonical knowledge. No Memory retrieval/promotion or
        new tool execution occurs here; changed profiles require fresh tools.
        """
        from career_runtime.continuity import message_status
        from career_runtime.models import TurnStatus
        if plan.dialogue_act == "new_topic" or plan.relevance in {Relevance.GENERAL_QA, Relevance.LEARNING_OR_TECHNICAL}:
            return set()
        current = self.profile()
        if current is None:
            return set()
        owned = {item.id for item in current.evidence}
        refs = set()
        for message in messages[-12:]:
            if message.role != "assistant" or message_status(message) != TurnStatus.COMPLETED:
                continue
            stamp = message.metadata.get("agent_profile_stamp", {})
            if stamp == {"profile_id": current.profile_id, "version": current.version}:
                refs.update(set(message.metadata.get("evidence_refs", [])) & owned)
        return refs

    def execute(self, request: ToolRequest, relevance: Relevance) -> ToolResult:
        request = ToolRequest.model_validate(request.model_dump())
        spec = self.specs[request.name]
        if not self.permitted(request, relevance):
            return ToolResult(name=request.name, status="denied", items=[], summary="not_permitted")
        try:
            items = self._execute(request)
            return ToolResult(name=request.name, status="succeeded" if items else "unavailable",
                              items=items, summary="candidate_pending_review" if spec.permission == "candidate" and items
                              else "read_completed" if items else "no_confirmed_source")
        except Exception:
            # Never return exception text, source payloads or secret values.
            return ToolResult(name=request.name, status="failed", items=[], summary="tool_failure")

    def permitted(self, request, relevance):
        return relevance not in {Relevance.GENERAL_QA, Relevance.LEARNING_OR_TECHNICAL} and (
            self.specs[request.name].permission == "read" or self.proposal_permission)

    def _execute(self, request):
        name, args = request.name, request.arguments
        if self.specs[name].permission == "read" and (args.dimension or args.value or args.user_quote):
            raise ValueError("Read tools cannot carry mutation arguments.")
        current = self.profile()
        if name in {ToolName.PROFILE, ToolName.GOALS}:
            if current is None:
                return []
            sections = args.sections if name == ToolName.PROFILE else ["goals", "career_preferences"]
            evidence = {item.id: item for item in current.evidence}
            return [ContextItem(label=(signal.text if section in {"strengths", "development_areas"} else signal.label)[:600], category=section + (":" + signal.goal_type.value if section == "goals" else ""),
                    status="confirmed", confidence=signal.confidence, inference_type=signal.inference_type.value, refs=[Reference(ref=ref, kind="profile_evidence",
                    source_type=evidence[ref].source_type.value, authority="confirmed_profile")
                    for ref in signal.evidence_ids[:8]])
                    for section in sections for signal in getattr(current, section)[:4]]
        if name == ToolName.EVIDENCE:
            if current is None:
                return []
            return [ContextItem(label=item.statement[:600], category=item.source_type.value, status="confirmed",
                    refs=[Reference(ref=item.id, kind="profile_evidence", source_type=item.source_type.value,
                                    authority="confirmed_profile")]) for item in current.evidence
                    if item.source_type in {EvidenceSourceType.COURSE, EvidenceSourceType.PROJECT}][:6]
        if name == ToolName.MEMORY:
            job = self.roles.get(args.role_id)
            context, _ = self.workspace.controller.role_memory_service.recall(
                subject_id=self.workspace.subject_id, role_title=job.title if job else "职业方向探索",
                role_summary=job.description[:400] if job else "当前职业偏好和目标",
                clarification_topic=self.user_text[:500])
            items = []
            for item in context.items:
                record = self.workspace.memory_service.memory_store.get(self.workspace.subject_id, item.memory_id)
                if record is None or record.status != MemoryStatus.CONFIRMED:
                    continue
                items.append(ContextItem(label=record.content[:600], category=record.memory_type.value, status="confirmed", confidence=record.confidence,
                    refs=[Reference(ref=record.memory_id, kind="memory", source_type=record.source_type.value,
                                    authority="confirmed_historical_memory")]))
            return items[:3]
        if name == ToolName.ROLE:
            job = self.roles.get(args.role_id)
            if job is None:
                return []
            bundle = JobEvidenceBuilder().build(job)
            return [ContextItem(label=item.text[:600], category=item.category.value, status="public_fixture",
                    refs=[Reference(ref=item.id, kind="job_evidence", source_type=item.source_type.value,
                                    authority="public_role_archetype")]) for item in bundle.source_evidence[:12]]
        if name == ToolName.MATCH:
            state = self.workspace.controller.state
            if current is None or not state or not state.get("profile"):
                return []
            profile = self.workspace.controller.confirmed_profile()
            if (profile.profile_id, profile.version) != (current.profile_id, current.version):
                return []
            result = self.workspace.controller.match_for(args.role_id)
            profile_evidence = {item.id: item for item in current.evidence}
            job_evidence = {item.id: item for item in self.workspace.controller.intelligence_for(args.role_id).evidence}
            items = []
            for insight in result.insights()[:8]:
                refs = [Reference(ref=ref, kind="profile_evidence", source_type=profile_evidence[ref].source_type.value,
                                  authority="confirmed_profile") for ref in insight.evidence_link.profile_evidence_ids]
                refs += [Reference(ref=ref, kind="job_evidence", source_type=job_evidence[ref].source_type.value,
                                   authority="public_role_archetype") for ref in insight.evidence_link.job_evidence_ids]
                items.append(ContextItem(label=insight.description[:600], category=insight.relation_type.value,
                                         status="confirmed", refs=refs[:8]))
            return items
        # Candidate preparation is transient. Confirmation is NOT in the registry.
        if args.user_quote != self.user_text or not args.dimension or not args.value:
            raise ValueError("Candidate must quote this user's current complete statement.")
        dimensions = {"career_direction_priority": "career_direction.priority", "work_style_primary_focus": "work_style.primary_focus"}
        values = {"hands_on": "hands_on_implementation", "product_and_requirements": "product_and_requirement_work"}
        canonical_dimension = dimensions[args.dimension]
        canonical_value = values.get(args.value, args.value)
        if canonical_value not in StructuredSignalPolicyRegistry().get(canonical_dimension).allowed_values:
            raise ValueError("Unsupported same-dimension value.")
        proposal = Proposal(kind="profile" if name == ToolName.PROFILE_DRAFT else "memory",
                            dimension=args.dimension, value=args.value, user_quote=args.user_quote)
        if proposal in self.proposals:
            raise ValueError("Duplicate proposal.")
        if name == ToolName.PROFILE_DRAFT:
            if current is None:
                return []
            signal = StructuredSessionSignal(signal_id="session_runtime_preference", dimension=canonical_dimension,
                value=canonical_value, display_label=args.user_quote, source="explicit_user_input", session_order=1)
            draft = self.workspace.controller.profile_refinement_service.refine(
                subject_id=self.workspace.subject_id, current_input=signal)
            self.profile_drafts.append((proposal, current.profile_id, current.version, draft))
        else:
            signal = StructuredSessionSignal(signal_id="session_runtime_preference", dimension=canonical_dimension,
                value=canonical_value, display_label=args.user_quote, source="explicit_user_input", session_order=1)
            self.memory_changes[proposal.model_dump_json()] = self.workspace.controller.memory_change_detector.detect(
                self.workspace.subject_id, signal)
        self.proposals.append(proposal)
        return [ContextItem(label=args.user_quote, category="pending_candidate", status="unknown", refs=[])]

    def confirm_proposal(self, proposal: Proposal, *, confirmed_by_user: bool, memory_choice: MemoryChangeChoice | None = None):
        """UI-only explicit command; no LLM/tool authority can call this method."""
        if not confirmed_by_user or proposal not in self.proposals:
            raise PermissionError("Explicit candidate review is required.")
        if proposal.kind == "profile":
            pending, profile_id, version, draft = next(item for item in self.profile_drafts if item[0] == proposal)
            current = self.profile()
            if current is None or (current.profile_id, current.version) != (profile_id, version):
                raise ValueError("Profile changed; review a fresh draft.")
            result = self.workspace.controller.profile_refinement_service.confirm(
                self.workspace.subject_id, draft, confirmed_by_user=True)
        else:
            change = self.memory_changes.get(proposal.model_dump_json())
            if change is not None:
                if not isinstance(memory_choice, MemoryChangeChoice):
                    raise ValueError("Same-dimension change requires an explicit review choice.")
                _, result = self.workspace.controller.memory_change_service.resolve(change, memory_choice)
                self.proposals.remove(proposal)
                return result
            record = self.workspace.memory_service.create_candidate(
                subject_id=self.workspace.subject_id, memory_type=MemoryType.CAREER_PREFERENCE,
                content=proposal.user_quote, source_type=EvidenceSourceType.EXPLICIT_USER_INPUT,
                metadata={"signal_dimension": {"career_direction_priority": "career_direction.priority", "work_style_primary_focus": "work_style.primary_focus"}[proposal.dimension],
                          "signal_value": {"hands_on": "hands_on_implementation", "product_and_requirements": "product_and_requirement_work"}.get(proposal.value, proposal.value)})
            result = self.workspace.memory_service.confirm_candidate(
                self.workspace.subject_id, record.memory_id, confirmed_by_user=True)
        self.proposals.remove(proposal)
        return result
