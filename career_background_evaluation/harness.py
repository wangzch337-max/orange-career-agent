"""Real Workspace lifecycle from upload; all provider output deterministically scripted."""

from dataclasses import asdict
import json
from pathlib import Path
from uuid import uuid4

from clarification.policy import TurnIntent
from profile_refinement.context import entry_id
from profile_refinement.models import Resolution, Status
from providers.fake import FakeLLMProvider
from resume_evidence.policy import MAX_CONTEXT_JSON_CHARS
from resume_evidence.session import ResumeAnalysisStatus
from resume_intake.models import ResumeParseStatus
from ui.chat_runtime import Workspace
from career_background_evaluation.scenarios import CONTACTS, RAW_MARKER, upload_bytes


class CheckFailure(AssertionError):
    """Closed check identifier only, never fixture/provider/error content."""


class Checks:
    def __init__(self):
        self.passed = []

    def require(self, code, condition):
        if not condition:
            raise CheckFailure(code)
        self.passed.append(code)


class CapturingFake(FakeLLMProvider):
    def __init__(self, program):
        super().__init__(None)
        self.program, self.payloads, self.options = program, [], []
        self.attempts = 0

    def generate_structured(self, messages, response_model, options, **kwargs):
        self.attempts += 1
        payload = json.loads(messages[1].content)
        self.payloads.append(payload)  # Ephemeral test-only capture, never written.
        self.options.append(options)
        self.predefined_response = self.program(payload)
        return super().generate_structured(messages, response_model, options, **kwargs)


def extraction_program(scenario):
    def extract(payload):
        items = []
        blocks = payload["blocks"]
        for index, fact in enumerate(scenario.facts, 1):
            fields = [fact.label, fact.organization, fact.time_range, fact.responsibility]
            refs = [b for b in blocks if any(field in b["text"] for field in fields)]
            # PDF may split the same evidence over pages; DOCX one paragraph.
            refs = refs[:8]
            item = dict(evidence_id=f"resume_evidence_{index:03d}", category=fact.category,
                normalized_claim=fact.label, source_block_ids=[b["block_id"] for b in refs],
                source_quotes=[dict(block_id=b["block_id"], excerpt=b["text"]) for b in refs],
                confidence="explicit", uncertainty="none", evidence_origin="resume_provided", claim_type="reported_fact")
            if fact.category == "work_experience":
                item.update(role_title=fact.label, organization=fact.organization, time_range=fact.time_range,
                    responsibilities=[fact.responsibility], achievements=[], domain_signals=[], tools=[], business_metrics=[])
            items.append(item)
        return dict(items=items, uncertainties=[])
    return extract


def clarification_program(payload):
    need = payload["eligible_needs"][0]
    return dict(should_ask=True, selected_need_id=need["need_id"], question=need["allowed_questions"][0],
        suggested_replies=need["allowed_replies"][:2], source_refs=need["source_refs"],
        reason_summary="highest_value_supported_need", confidence="grounded")


def delta_program(scenario):
    def propose(payload):
        changes = []
        sources = payload["sources"]
        for source in sources:
            if source["origin"] != "resume_evidence":
                continue
            old = next((s for s in sources if s["origin"] == "confirmed_profile" and
                        s["category"] == source["category"] and s["value"]["label"] == source["value"]["label"]), None)
            if old and old["value"] == source["value"]:
                continue
            changes.append(dict(category=source["category"], target_id=old["target_id"] if old else None,
                change_type="UPDATE" if old else "ADD", proposed_value=source["value"],
                source_refs=[source["ref"], *([old["ref"]] if old else [])],
                reason_summary="new_supported_evidence", uncertainty="none"))
        current = next((s for s in sources if s["origin"] == "explicit_user_input"), None)
        answer = current or next((s for s in sources if s["origin"] == "clarification_answer"), None)
        old = next((s for s in sources if s["origin"] == "confirmed_profile" and s["category"] == "goals"), None)
        if answer and (not old or old["value"]["label"] != scenario.goal_label):
            changes.append(dict(category="goals", target_id=old["target_id"] if old else None,
                change_type="UPDATE" if old else "ADD", proposed_value=dict(label=scenario.goal_label, goal_type="career_goal"),
                source_refs=[answer["ref"], *([old["ref"]] if old else [])],
                reason_summary="clarification_update", uncertainty="explicit_uncertainty" if scenario.uncertain else "none"))
        return dict(outcome="CHANGES" if changes else "NO_MATERIAL_CHANGE", changes=changes)
    return propose


class CareerHarness:
    """Uses actual upload/parser/session/store modules, no manually built final Profile."""

    def __init__(self, root, scenario, *, workspace=None, kind="docx", scope=None):
        self.root, self.scenario, self.kind = Path(root), scenario, kind
        self.workspace = workspace or Workspace(scope or str(uuid4()), self.root)
        self.checks = Checks()
        self.raw_bytes = upload_bytes(scenario, kind)
        self.raw_text = self.answer_text = ""
        self.extraction = CapturingFake(extraction_program(scenario))
        self.clarifier = CapturingFake(clarification_program)
        self.refiner = CapturingFake(delta_program(scenario))
        w = self.workspace
        w.resume_analysis.provider_factory = lambda: self.extraction
        w.clarification.provider_factory = lambda: self.clarifier
        w.profile_refinement.provider_factory = lambda: self.refiner

    @property
    def providers(self):
        return self.extraction, self.clarifier, self.refiner

    def upload(self):
        w = self.workspace
        w.resume_intake.select(w.owner_scope_id, w.thread.thread_id, "public-synthetic." + self.kind, self.raw_bytes)
        result = w.resume_intake.parse_pending()
        self.checks.require("local_parse_ready", result.status == ResumeParseStatus.READY)
        self.checks.require("upload_buffer_released", w.resume_intake.pending is None)
        self.raw_text = "\n".join(b.text for b in result.document.blocks)
        return result

    def analyze(self):
        w, c = self.workspace, self.checks
        before = self.extraction.attempts
        w.agent_session.set_consent(granted=True)  # Chat consent is NOT Resume consent.
        c.require("separate_resume_consent", w.resume_analysis.analyze() == ResumeAnalysisStatus.CONSENT_REQUIRED)
        c.require("no_call_before_resume_consent", self.extraction.attempts == before)
        c.require("explicit_test_consent", w.resume_analysis.grant_current())
        c.require("resume_evidence_ready", w.resume_analysis.analyze() == ResumeAnalysisStatus.READY)
        c.require("candidate_not_authority", w.resume_analysis.bundle.authority == "candidate")
        c.require("source_count", len(w.resume_analysis.bundle.items) == len(self.scenario.facts))
        w.resume_analysis.analyze()
        c.require("no_extraction_rerun", self.extraction.attempts == before + 1)

    def clarify(self):
        w, c = self.workspace, self.checks
        decision = w.clarification.run(TurnIntent.RESUME_REVIEW, current_statement=self.scenario.current)
        question = w.clarification.current_question()
        if question:
            payload = self.clarifier.payloads[-1]
            c.require("highest_value_need", decision.selected_need_id in {n["need_id"] for n in payload["eligible_needs"]})
            c.require("no_irrelevant_technical_question", not any(x in question.decision.question.casefold() for x in ("python", "github", "cs专业", "算法项目")))
            self.answer_text = self.scenario.answer
            candidate = w.clarification.answer(question, self.answer_text)
            c.require("explicit_answer_candidate", candidate is not None and candidate.status == "candidate")
            c.require("answer_not_durable_chat", not w.store.list_messages(w.owner_scope_id, w.thread.thread_id))
            c.require("answer_not_extra_call", self.clarifier.attempts == 1)
        else:
            c.require("known_goal_not_reasked", bool(self.scenario.current) and not decision.should_ask and self.clarifier.attempts == 0)
        return question

    def draft(self):
        w, c = self.workspace, self.checks
        old = self.current()
        draft = w.profile_refinement.start(explicit_review=True, current_statement=self.scenario.current)
        c.require("draft_valid", draft is not None)
        c.require("no_silent_profile_overwrite", self.current() == old)
        c.require("no_preconfirmation_memory", not self.memories() or old is not None)
        c.require("source_refs_valid", all(ref in {s.ref for s in w.profile_refinement.context.sources} for change in draft.changes for ref in change.source_refs))
        return draft

    def prepare(self):
        self.upload(); self.analyze(); self.clarify()
        return self.draft()

    def resolve_all(self, *, edit=False, keep_category=None):
        s = self.workspace.profile_refinement
        for change in s.draft.changes:
            value = change.proposed_value
            resolution = Resolution.KEEP_OLD if change.old_value else Resolution.REJECT
            if change.category != keep_category:
                resolution = Resolution.UNCERTAIN if change.uncertainty != "none" else Resolution.CONFIRM
            if edit and change.category == "goals":
                edited = value.model_dump()
                edited["label"] += "（由用户确认保留探索状态）"
                self.checks.require("user_edit", s.resolve(s.token(), change.change_id, Resolution.EDIT, edited_value=edited))
            self.checks.require("field_resolution", s.resolve(s.token(), change.change_id, resolution))

    def confirm(self, *, memory=False):
        s = self.workspace.profile_refinement
        goal = next((ch for ch in s.draft.changes if ch.category == "goals"), None)
        result = s.confirm(s.token(), confirmed_by_user=True, memory_change_id=goal.change_id if goal and memory else None)
        self.checks.require("confirmed_profile", result is not None and result.confirmed)
        self.checks.require("canonical_pointer", self.current() == result)
        return result

    def current(self):
        w = self.workspace
        return w.memory_service.get_current_confirmed_profile(w.subject_id)

    def history(self):
        return self.workspace.memory_service.profile_store.list_profile_history(self.workspace.subject_id)

    def memories(self):
        return self.workspace.memory_service.memory_store.list_active(self.workspace.subject_id)

    def privacy_checks(self, profile):
        c, w = self.checks, self.workspace
        capture = json.dumps([p.payloads for p in self.providers], ensure_ascii=False)
        c.require("bounded_resume_context", len(json.dumps(self.extraction.payloads[0], ensure_ascii=False, separators=(",", ":"))) <= MAX_CONTEXT_JSON_CHARS)
        for index, contact in enumerate(CONTACTS):
            c.require(f"contact_minimized_{index}", contact.split(": ", 1)[1] not in capture)
        c.require("no_local_path_upload_object", not any(x in capture for x in (str(self.root), "UploadedResume", "PK\\u0003", "%PDF", w.owner_scope_id, w.subject_id)))
        events = json.dumps([asdict(e) for session in (w.resume_intake, w.resume_analysis, w.clarification, w.profile_refinement) for e in session.events], default=str)
        for index, value in enumerate((RAW_MARKER, self.answer_text, self.scenario.facts[0].label, *CONTACTS)):
            if value:
                c.require(f"structural_observability_{index}", value not in events)
        c.require("no_prompt_completion_log", not any(x in events.casefold() for x in ("source_quotes", "messages", "api_key", "reasoning", "completion")))
        normalized = profile.model_dump_json()
        c.require("profile_not_raw", RAW_MARKER not in normalized and self.raw_text not in normalized and str(self.root) not in normalized)
        c.require("memory_not_raw", all(m.content != self.answer_text and RAW_MARKER not in m.content and m.memory_type.value in {"goal", "career_preference"} for m in self.memories()))
        # Audit durable bytes in this isolated workspace only, including all DBs.
        for index, path in enumerate(sorted(p for p in self.root.rglob("*") if p.is_file())):
            data = path.read_bytes()
            c.require(f"durable_file_{index}", self.raw_bytes not in data and RAW_MARKER.encode() not in data and self.raw_text.encode() not in data)
            if self.answer_text:
                c.require(f"durable_answer_{index}", self.answer_text.encode() not in data)
            for contact in CONTACTS:
                c.require(f"durable_contact_{index}_{CONTACTS.index(contact)}", contact.split(": ", 1)[1].encode() not in data)
        c.require("no_durable_parser_file", all(p.suffix not in {".pdf", ".docx"} for p in self.root.rglob("*") if p.is_file()))
        c.require("no_provider_retry_or_thinking", all(o.max_retries == 0 and not o.thinking_enabled and o.model == "qwen3.8-flash" for p in self.providers for o in p.options))

    def universal_checks(self, profile):
        c = self.checks
        c.require("projects_optional", not profile.projects)
        c.require("universal_work_history", len(profile.work_experience) == sum(f.category == "work_experience" for f in self.scenario.facts))
        c.require("education_preserved", len(profile.education) == sum(f.category == "education" for f in self.scenario.facts))
        c.require("no_skill_inflation", not profile.skills)
        c.require("major_not_goal", all(goal.label != f.label for goal in profile.goals for f in self.scenario.facts if f.category == "education"))
        c.require("current_direction_respected", len(profile.goals) == 1 and profile.goals[0].label.startswith(self.scenario.goal_label))
        c.require("uncertainty_preserved", all(p.uncertainty == ("explicit_uncertainty" if self.scenario.uncertain else "none") for key, p in profile.field_provenance.items() if key.startswith("goals.")))
        c.require("no_unsupported_conclusion", not profile.development_areas and not profile.career_preferences and not profile.strengths)
        c.require("valid_provenance", all(p.confirmed_by_user and p.source_refs for p in profile.field_provenance.values()) and bool(profile.field_provenance))
        c.require("stable_field_ids", all(entry_id(category, item) for category in ("work_experience", "education", "goals") for item in getattr(profile, category)))
        c.require("no_ranking", not any(key in profile.model_dump() for key in ("score", "ranking", "recommended_roles")))

    def close(self):
        self.workspace.close()


def evaluate_scenario(scenario, root, *, kind="docx"):
    h = CareerHarness(root, scenario, kind=kind)
    try:
        h.prepare()
        h.resolve_all(edit=True)
        profile = h.confirm(memory=True)
        h.universal_checks(profile)
        h.privacy_checks(profile)
        scope = h.workspace.owner_scope_id
        h.workspace.create_new_thread()
        h.checks.require("new_chat_clears_candidate", h.workspace.resume_intake.result is None and h.workspace.resume_analysis.bundle is None and not h.workspace.resume_analysis.has_consent and not h.workspace.clarification.state.answer_candidates and h.workspace.profile_refinement.draft is None)
        h.checks.require("new_chat_canonical_profile", h.workspace.thread.profile_id_ref == profile.profile_id)
        memories = h.memories()
        h.close()
        with Workspace(scope, root) as restored:
            h.checks.require("restart_profile", restored.memory_service.get_current_confirmed_profile(restored.subject_id) == profile)
            h.checks.require("restart_history", restored.memory_service.profile_store.list_profile_history(restored.subject_id) == [profile])
            h.checks.require("restart_memory", restored.memory_service.memory_store.list_active(restored.subject_id) == memories)
            h.checks.require("restart_ephemeral_clear", restored.resume_intake.result is None and restored.resume_analysis.bundle is None and restored.profile_refinement.draft is None)
        return len(h.checks.passed)
    finally:
        h.close()
