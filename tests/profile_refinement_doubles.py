"""C.4 scripted semantic deltas over the existing public C.2/C.3 shapes."""

from dataclasses import replace
import json
from uuid import uuid4

from clarification.context import ClarificationInputs, binding_for
from clarification.models import ClarificationAnswerCandidate
from data.models import utc_now
from memory.service import build_sqlite_memory_service
from profile_refinement.context import RefinementInputs
from profile_refinement.models import Resolution
from profile_refinement.session import ProfileRefinementSession
from providers.fake import FakeLLMProvider
from tests.clarification_doubles import bundle_for, profile_for


def proposal(source, *, category=None, target=None, value=None, refs=None, change_type="ADD", uncertainty="none"):
    return dict(category=category or source["category"], target_id=target, change_type=change_type,
        proposed_value=value or source.get("value"), source_refs=refs or [source["ref"]],
        reason_summary="new_supported_evidence", uncertainty=uncertainty)


def work_plan(payload):
    source = next(s for s in payload["sources"] if s["origin"] == "resume_evidence")
    return {"outcome": "CHANGES", "changes": [proposal(source)]}


def goal_plan(payload):
    old = next((s for s in payload["sources"] if s["category"] == "goals" and s["origin"] == "confirmed_profile"), None)
    source = next(s for s in payload["sources"] if s["origin"] in {"explicit_user_input", "clarification_answer"})
    return {"outcome": "CHANGES", "changes": [proposal(source, category="goals",
        target=old["target_id"] if old else None, value={"label": "正在探索数据分析", "goal_type": "career_goal"},
        refs=[source["ref"], *([old["ref"]] if old else [])], change_type="UPDATE" if old else "ADD")]}


class DeltaFake(FakeLLMProvider):
    def __init__(self, plan=work_plan):
        super().__init__(None)
        self.plan, self.payloads, self.options, self.schemas = plan, [], [], []

    def generate_structured(self, messages, response_model, options, **kwargs):
        payload = json.loads(messages[1].content)
        self.payloads.append(payload)
        self.options.append(options)
        self.schemas.append(response_model.model_json_schema())
        self.predefined_response = self.plan(payload)
        return super().generate_structured(messages, response_model, options, **kwargs)


class Harness:
    def __init__(self, root, *, profile=None, background="audit", plan=work_plan, current=""):
        self.service = build_sqlite_memory_service(root / "memory.sqlite3")
        self.inputs = RefinementInputs("synthetic_owner", "synthetic_thread", "synthetic_subject",
            bundle_for(background), profile, current_statement=current)
        if profile:
            self.service.save_confirmed_profile(self.inputs.subject_id, profile)
        self.fake = DeltaFake(plan)
        self.session = ProfileRefinementSession(self.inputs.owner_scope_id, self.factory, self.service,
                                               provider_factory=lambda: self.fake)

    def factory(self, *, current_statement="", include_memory=False):
        del include_memory
        return replace(self.inputs, current_statement=current_statement,
            profile=self.service.get_current_confirmed_profile(self.inputs.subject_id))

    def start(self):
        return self.session.start(explicit_review=True, current_statement=self.inputs.current_statement)

    def review(self, resolution=Resolution.CONFIRM):
        for c in self.session.draft.changes:
            assert self.session.resolve(self.session.token(), c.change_id, resolution)

    def confirm(self, **kwargs):
        return self.session.confirm(self.session.token(), confirmed_by_user=True, **kwargs)

    def history(self):
        return self.service.profile_store.list_profile_history(self.inputs.subject_id)

    def memories(self):
        return self.service.memory_store.list_active(self.inputs.subject_id)

    def answer(self, text="我在探索数据分析，目前还不确定", topic="career_direction"):
        profile = self.service.get_current_confirmed_profile(self.inputs.subject_id)
        b = binding_for(ClarificationInputs(self.inputs.owner_scope_id, self.inputs.conversation_id,
            self.inputs.subject_id, self.inputs.resume, profile), 0)
        candidate = ClarificationAnswerCandidate(candidate_id="clarification_answer_" + uuid4().hex,
            question_id="question_" + uuid4().hex, need_id="need_" + "1" * 20, topic=topic, user_answer=text,
            uncertainty="explicit_uncertainty" if "不确定" in text else "none", created_at=utc_now(),
            binding=b, resolved_sources=())
        self.inputs = replace(self.inputs, answers=(candidate,), clarification_version=1)
        return candidate
