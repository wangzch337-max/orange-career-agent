"""Public synthetic shapes and scripted semantic choices; never network clients."""

from dataclasses import replace
import json
from uuid import uuid4

from clarification.context import ClarificationInputs
from data.models import Goal, GoalType, UserProfile
from providers.fake import FakeLLMProvider
from resume_evidence.context import content_fingerprint
from resume_evidence.models import ResumeEvidenceBundle
from tests.resume_evidence_doubles import document_for, evidence_output


def profile_for(goal=None):
    return UserProfile(profile_id="synthetic_profile", goals=[] if not goal else [
        Goal(goal_id="goal_001", goal_type=GoalType.CAREER_GOAL, label=goal)]).confirm()


def bundle_for(background="audit", *, owner="synthetic_owner", thread="synthetic_thread", ambiguity="none", category=None):
    document = document_for(background)
    category = category or ("education" if background == "student" else "work_experience")
    output = evidence_output(document, category=category)
    output["items"][0]["uncertainty"] = ambiguity
    if ambiguity != "none":
        output["items"][0]["confidence"] = "uncertain"
    return ResumeEvidenceBundle(**output, source_id=document.source_id, content_fingerprint=content_fingerprint(document),
        owner_scope_id=owner, thread_id=thread, context_partial=False)


def inputs_for(background="audit", *, goal=None, current="", ambiguity="none", category=None):
    return ClarificationInputs("synthetic_owner", "synthetic_thread", "synthetic_subject",
        bundle_for(background, ambiguity=ambiguity, category=category), profile_for(goal), current_statement=current)


class InputSource:
    def __init__(self, inputs):
        self.value = inputs
        self.calls = 0

    def __call__(self, *, current_statement=""):
        self.calls += 1
        return replace(self.value, current_statement=current_statement or self.value.current_statement)


class SelectingFake(FakeLLMProvider):
    def __init__(self, *, ask=True, transform=None):
        super().__init__(None)
        self.ask = ask
        self.transform = transform
        self.payloads = []
        self.options = []
        self.schemas = []

    def generate_structured(self, messages, response_model, options, **kwargs):
        payload = json.loads(messages[1].content)
        self.payloads.append(payload)
        self.options.append(options)
        self.schemas.append(response_model.model_json_schema())
        need = payload["eligible_needs"][0]
        output = {"should_ask": self.ask, "selected_need_id": need["need_id"] if self.ask else None,
            "question": need["allowed_questions"][0] if self.ask else None,
            "suggested_replies": need["allowed_replies"][:2] if self.ask else [],
            "source_refs": need["source_refs"] if self.ask else [],
            "reason_summary": "highest_value_supported_need" if self.ask else "no_useful_question_now",
            "confidence": "grounded"}
        self.predefined_response = self.transform(output) if self.transform else output
        return super().generate_structured(messages, response_model, options, **kwargs)
