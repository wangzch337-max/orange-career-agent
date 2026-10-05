"""B.2 authority tests: synthetic, offline, actual admission and consumers."""

from copy import deepcopy
from dataclasses import replace
import json
from uuid import uuid4

import pytest

from career_background_evaluation.harness import CareerHarness
from career_background_evaluation.scenarios import SCENARIOS
from clarification.context import ClarificationInputs, ClarificationContextBuilder, binding_for
from profile_refinement.context import RefinementInputs, ProfileRefinementContextBuilder, binding_for_refinement
from providers.fake import FakeLLMProvider
from resume_evidence.context import ProviderResumeContextBuilder, content_fingerprint
from resume_evidence.models import ResumeEvidenceExtraction, ResumeEvidenceBundle
from resume_evidence.policy import CATEGORIES
from resume_evidence.service import ResumeEvidenceExtractor
from resume_evidence.validation import validate_extraction, validate_model_claims, ResumeValidationError
from tests.resume_evidence_doubles import document_for, evidence_output
from tests.test_resume_evidence import _grounding_fixture, _multi_block_grounding
from tests.test_chat_product import app, WORKSPACE_KEY

POISON = "Expert executive independently owned global product strategy and improved profit by 97%"


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("B.2 forbids live configuration and provider construction")
    monkeypatch.setattr("providers.models.load_llm_settings", forbidden)
    monkeypatch.setattr("resume_evidence.session._qwen_provider", forbidden)


def admit(document, output):
    return validate_extraction(ResumeEvidenceExtraction.model_validate(output), ProviderResumeContextBuilder().build(document))


def bundle(document, extraction):
    return ResumeEvidenceBundle(**extraction.model_dump(), source_id=document.source_id,
        content_fingerprint=content_fingerprint(document), owner_scope_id="synthetic_owner",
        thread_id="synthetic_thread", context_partial=False)


def contexts(document, extraction):
    b = bundle(document, extraction)
    c = ClarificationInputs("synthetic_owner", "synthetic_thread", "synthetic_subject", b)
    p = RefinementInputs("synthetic_owner", "synthetic_thread", "synthetic_subject", b)
    return ClarificationContextBuilder().build(c), ProfileRefinementContextBuilder().build(p)


@pytest.mark.parametrize("claim", [
    "Audit Associate", "Facilitated assurance documentation for statutory engagements",
    POISON, "Increased revenue by $50M", "Led end-to-end audits independently",
    "Senior strategic expert", "I prefer a Data Analyst career",
    "Contact: discarded-provider@example.invalid",
])
def test_typed_provider_description_is_replaced_not_promoted(claim):
    d = document_for()
    output = evidence_output(d, claim=claim)
    x = admit(d, output)
    item = x.items[0]
    assert item.normalized_claim == item.canonical_label == "Audit Associate"
    assert item.canonical_facts == (item.role_title, item.organization, item.time_range, *item.responsibilities)
    assert item.canonical_text == " · ".join(item.canonical_facts)
    c, p = contexts(d, x)
    assert p.sources[0].value.label == item.canonical_label
    assert c.sources[0].text == item.canonical_text
    if claim != item.canonical_label:
        assert claim not in x.model_dump_json() + c.model_dump_json() + p.model_dump_json()


def test_live_failure_shape_isolated_without_lexical_expansion():
    d = document_for()
    output = evidence_output(d, claim="Facilitated assurance documentation for statutory engagements")
    parsed = ResumeEvidenceExtraction.model_validate(output)  # Strict structured PASS.
    context = ProviderResumeContextBuilder().build(d)
    with pytest.raises(ResumeValidationError, match="EVIDENCE_VALIDATION_FAILED"):
        validate_model_claims(parsed, context)  # Historical lexical diagnostic FAIL.
    provider = FakeLLMProvider(output)
    x, usage = ResumeEvidenceExtractor().extract(provider, context)
    assert x.items[0].canonical_label == "Audit Associate"
    assert provider.call_count == 1 and usage.retries == 0
    assert output["items"][0]["normalized_claim"] not in x.model_dump_json()


@pytest.mark.parametrize("field,value", [
    ("role_title", "Senior Audit Associate"), ("organization", "Invented Company"),
    ("time_range", "2000 - 2026"), ("responsibilities", ["Led end-to-end audit"]),
    ("achievements", ["Increased conversion by 37%"]), ("tools", ["Advanced Excel expert"]),
    ("domain_signals", ["Strong analytical capability"]), ("business_metrics", ["$50M profit"]),
])
def test_harmless_description_cannot_hide_bad_typed_field(field, value):
    d = document_for()
    output = evidence_output(d)  # Harmless exact provider description.
    output["items"][0][field] = value
    with pytest.raises(ResumeValidationError, match="EVIDENCE_VALIDATION_FAILED"):
        admit(d, output)


@pytest.mark.parametrize("source,bad", [
    ("Increased conversion by 18%", "Increased conversion by 18"),
    ("Managed a budget of $50K", "Managed a budget of 50K"),
    ("Reviewed invoices totaling HK$20,000", "Reviewed invoices totaling $20,000"),
    ("Achieved a 3x increase", "Achieved a 3 increase"),
    ("Worked for 10 years", "Worked for 10"),
    ("Coordinated 5 people", "Coordinated 5"),
    ("Recorded change of -18%", "Recorded change of 18%"),
    ("Reached >=18%", "Reached 18%"),
    ("Project ownership: none", "Project ownership"),
    ("No leadership responsibility", "Leadership responsibility"),
    ("Did not lead the project", "Lead the project"),
    ("Participated in implementation", "Led implementation"),
    ("Supported implementation", "Owned implementation"),
    ("Co-led implementation", "Led implementation"),
    ("Implemented under supervision", "Implemented"),
    ("Proficiency: basic", "Proficiency"),
    ("Used Python3", "Python"),
    ("没有主导项目", "主导项目"),
    ("熟练度: 基础", "熟练度"),
])
def test_canonical_typed_material_boundary_stays_fail_closed(source, bad):
    d, output = _grounding_fixture(source, source, category="work_experience", typed={"responsibilities": [bad]})
    with pytest.raises(ResumeValidationError, match="EVIDENCE_VALIDATION_FAILED"):
        admit(d, output)


@pytest.mark.parametrize("source", [
    "Increased conversion by 18%", "Managed a budget of $50K", "Project ownership: none",
    "No leadership responsibility", "Did not lead the project", "Supported implementation",
    "Participated in implementation", "Implemented under supervision", "Proficiency: basic", "项目所有权: 无",
])
def test_canonical_material_facts_keep_exact_units_scope_and_uncertainty(source):
    d, output = _grounding_fixture(source, POISON, category="work_experience", typed={"responsibilities": [source]})
    output["items"][0].update(confidence="uncertain", uncertainty="unclear_ownership")
    item = admit(d, output).items[0]
    assert item.canonical_label == item.canonical_text == source
    assert item.uncertainty == "unclear_ownership" and item.confidence == "uncertain"
    assert POISON not in item.model_dump_json()


@pytest.mark.parametrize("mutation", ["nonexistent", "cross_resume", "fake_excerpt", "missing_block", "unrelated_excerpt", "hidden_block"])
def test_canonical_source_provenance_negative_matrix(mutation):
    d, output = _multi_block_grounding()
    output["items"][0]["normalized_claim"] = POISON
    item = output["items"][0]
    context = ProviderResumeContextBuilder().build(d)
    if mutation in {"nonexistent", "cross_resume"}:
        bad = "fabricated" if mutation == "nonexistent" else "other_resume:block:1"
        item["source_block_ids"][0] = item["source_quotes"][0]["block_id"] = bad
    elif mutation in {"fake_excerpt", "unrelated_excerpt"}:
        item["source_quotes"][1]["excerpt"] = "Unrelated invented fact" if mutation == "fake_excerpt" else "Audit Associate"
    elif mutation == "missing_block":
        item["source_block_ids"].pop(); item["source_quotes"].pop()
    else:
        context = replace(context, blocks=context.blocks[:-1], partial=True)
    with pytest.raises(ResumeValidationError):
        validate_extraction(ResumeEvidenceExtraction.model_validate(output), context)


@pytest.mark.parametrize("category", [c for c in CATEGORIES if c not in {"work_experience", "projects"}])
def test_all_minimally_typed_categories_require_verified_extractive_basis(category):
    source = "Documented public synthetic activity"
    d, output = _grounding_fixture(source, "Experience documenting public synthetic activity", category=category)
    item = admit(d, output).items[0]
    assert item.canonical_text == source
    assert item.canonical_label != output["items"][0]["normalized_claim"]
    output["items"][0]["normalized_claim"] = "Expert strategic leadership"
    with pytest.raises(ResumeValidationError):
        admit(d, output)


@pytest.mark.parametrize("category", ["work_experience", "projects"])
def test_empty_typed_items_do_not_offer_generic_escape_hatch(category):
    d, output = _grounding_fixture("Used Excel", "Expert spreadsheet strategist", category=category)
    with pytest.raises(ResumeValidationError):
        admit(d, output)
    output["items"][0]["normalized_claim"] = "Experience with Excel"
    assert admit(d, output).items[0].canonical_text == "Used Excel"


def test_project_materials_are_canonical_and_bad_fields_still_reject():
    d, output = _grounding_fixture("Public Synthetic Event\nParticipated in welcome event", POISON,
        category="projects", typed={"project_name": "Public Synthetic Event", "responsibilities": ["Participated in welcome event"]})
    item = admit(d, output).items[0]
    assert item.canonical_label == "Public Synthetic Event"
    assert item.canonical_text.endswith("Participated in welcome event")
    output["items"][0]["responsibilities"] = ["Led welcome event"]
    with pytest.raises(ResumeValidationError):
        admit(d, output)


def test_generic_readable_representation_and_identity_keep_source_order():
    source = "Reviewed tolerances\nCoordinated preventive maintenance"
    d, first = _grounding_fixture(source, "Experience coordinating preventive maintenance; reviewing tolerances")
    second = deepcopy(first)
    second["items"][0]["normalized_claim"] = "Experience reviewing tolerances; coordinating preventive maintenance"
    a, b = admit(d, first), admit(d, second)
    assert a == b and a.canonical_json() == b.canonical_json()
    assert a.items[0].canonical_text == "Reviewed tolerances · Coordinated preventive maintenance"


def test_generic_cannot_crop_original_qualifiers_or_keep_contacts():
    for source, cropped in (("No Python experience", "Python experience"), ("Project ownership: none", "Project ownership")):
        d, output = _grounding_fixture(source, cropped)
        output["items"][0]["source_quotes"][0]["excerpt"] = cropped
        with pytest.raises(ResumeValidationError):
            admit(d, output)
    d, output = _grounding_fixture("Skill: Excel\nEmail: synthetic@example.invalid", "Email: synthetic@example.invalid")
    with pytest.raises(ResumeValidationError):
        admit(d, output)


def test_typed_dedup_binding_and_fingerprints_ignore_model_wording():
    d = document_for()
    a = admit(d, evidence_output(d))
    b = admit(d, evidence_output(d, claim=POISON))
    assert a == b and a.canonical_json() == b.canonical_json()
    output = evidence_output(d)
    duplicate = deepcopy(output["items"][0]); duplicate.update(evidence_id="resume_evidence_002", normalized_claim=POISON)
    output["items"].append(duplicate)
    assert len(admit(d, output).items) == 1
    ba, bb = bundle(d, a), bundle(d, b)
    ca = ClarificationInputs("synthetic_owner", "synthetic_thread", "synthetic_subject", ba)
    cb = replace(ca, resume=bb)
    pa = RefinementInputs("synthetic_owner", "synthetic_thread", "synthetic_subject", ba)
    pb = replace(pa, resume=bb)
    assert binding_for(ca, 0) == binding_for(cb, 0)
    assert binding_for_refinement(pa) == binding_for_refinement(pb)
    changed = ba.items[0].model_copy(update={"responsibilities": ()})
    assert binding_for(replace(ca, resume=ba.model_copy(update={"items": (changed,)})), 0) != binding_for(ca, 0)


def test_student_clarification_and_refinement_receive_extractive_activity():
    d = document_for("student")
    output = evidence_output(d, category="education", claim="Experience coordinating a student welcome event")
    x = admit(d, output)
    c, p = contexts(d, x)
    assert c.sources[0].text == p.sources[0].value.label == "Coordinated a student welcome event"
    assert "Experience" not in c.sources[0].text
    assert not c.sources[0].explicit_goal and not p.sources[0].explicit_goal


def test_over_budget_projection_omits_whole_facts_without_material_cut():
    long = "Recorded " + "synthetic " * 30 + "change of 18% under supervision"
    d, output = _grounding_fixture("Audit Associate\n" + long, POISON, category="work_experience",
        typed={"role_title": "Audit Associate", "responsibilities": [long]})
    x = admit(d, output)
    assert x.items[0].canonical_text.endswith("18% under supervision")
    text, partial = x.items[0].canonical_projection(160)
    assert partial and text == "Audit Associate"
    _, p = contexts(d, x)
    assert p.partial and p.sources[0].value.details == ()


BACKGROUND_IDS = ("student_new_graduate", "experienced_professional", "career_switcher", "accounting_audit",
                 "mechanical_manufacturing", "marketing_ecommerce", "ux_design", "work_heavy_zero_projects")


@pytest.mark.parametrize("scenario_id", BACKGROUND_IDS)
def test_canonical_public_backgrounds_real_profile_memory_and_privacy(tmp_path, scenario_id, caplog):
    scenario = next(s for s in SCENARIOS if s.scenario_id == scenario_id)
    h = CareerHarness(tmp_path, scenario)
    native = h.extraction.program
    def poison_typed(payload):
        output = native(payload)
        for item in output["items"]:
            if item["category"] == "work_experience":
                item["normalized_claim"] = POISON
        return output
    h.extraction.program = poison_typed
    try:
        h.prepare()
        assert not h.current() and not h.memories()
        capture = json.dumps(h.clarifier.payloads + h.refiner.payloads)
        assert POISON not in capture
        h.resolve_all(); profile = h.confirm(memory=True)
        assert POISON not in profile.model_dump_json() and all(POISON not in m.content for m in h.memories())
        assert len(h.memories()) == 1
        assert [p.attempts for p in h.providers] == [1, 1, 1]
        h.universal_checks(profile); h.privacy_checks(profile)
        assert POISON not in caplog.text
        assert all(POISON.encode() not in path.read_bytes() for path in tmp_path.rglob("*") if path.is_file())
    finally:
        h.close()


@pytest.mark.parametrize("theme", ["浅色模式", "深色模式"])
def test_actual_profile_review_ui_shows_only_canonical_source(tmp_path, theme):
    value = app(tmp_path, str(uuid4()))
    w = value.session_state[WORKSPACE_KEY]
    h = CareerHarness(tmp_path, SCENARIOS[3], workspace=w)
    native = h.extraction.program
    def poisoned(payload):
        output = native(payload); output["items"][0]["normalized_claim"] = POISON
        return output
    h.extraction.program = poisoned
    try:
        h.prepare()
        value.radio(key="orange_appearance").set_value(theme).run()
        assert not value.exception
        text = "\n".join(e.value for e in value.text)
        assert "新候选：Audit Associate" in text and POISON not in text
        assert all(POISON not in e.value for e in value.text_input)
        assert not h.current() and not h.memories()
        assert [p.attempts for p in h.providers] == [1, 1, 1]
    finally:
        h.close()
