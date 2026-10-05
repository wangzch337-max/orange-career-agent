"""One bounded structural repair per planning point; no turn/tool replay."""

from pathlib import Path
from pydantic import ValidationError
from career_runtime.context import messages_for
from career_runtime.diagnostics import PlanFailure, RuntimeDiagnostic, structural_failure
from career_runtime.models import Plan, ToolInput, TOOL_ARGUMENTS, PROFILE_TOOLS, MEMORY_TOOLS, ROLE_TOOLS
from providers.errors import LLMError, LLMStructuredOutputError
from providers.models import GenerationOptions

PROMPTS = Path(__file__).parent / "prompts"


def public_contract():
    schema = Plan.model_json_schema()
    return {
        "required_plan_fields": list(Plan.model_fields),
        "enum_values": {name: field.get("enum", schema.get("$defs", {}).get(field.get("$ref", "").split("/")[-1], {}).get("enum", []))
                        for name, field in schema["properties"].items() if "enum" in field or "$ref" in field},
        "source_flag_tools": {"needs_profile": sorted(item.value for item in PROFILE_TOOLS),
            "needs_memory": sorted(item.value for item in MEMORY_TOOLS), "needs_role": sorted(item.value for item in ROLE_TOOLS)},
        "tool_arguments": {name: {"used_fields": list(used),
            "unused_defaults": {key: [] if key == "sections" else "" for key in ToolInput.model_fields if key not in used}}
            for name, used in TOOL_ARGUMENTS.items()},
    }


def generate_plan(provider, payload, registry, options, *, round_index, record, usage, counts, cancellation=None):
    """Repair input contains public structure + already-permitted context, NOT bad output."""
    for repair in range(2):
        if cancellation is not None:
            cancellation.checkpoint()
        counts["repair_invocation_count" if repair else "planner_invocation_count"] += 1
        prompt_name = "orange_planner_repair" if repair else "orange_planner"
        prompt = (PROMPTS / ("planner_repair_v1.md" if repair else "planner_v1.md")).read_text()
        current = {**payload, "plan_contract": public_contract()}
        if repair:
            current["structural_issues"] = previous.diagnostic.model_dump(mode="json")
        try:
            response = provider.generate_structured(messages_for(prompt, current), Plan,
                options.model_copy(update={"max_retries": 0}) if repair else options,
                prompt_name=prompt_name, prompt_version="v1")
            usage.append(response.safe_metadata())
            plan = Plan.model_validate(response.data.model_dump())
        except (ValidationError, LLMStructuredOutputError) as exc:
            if cancellation is not None:
                cancellation.checkpoint()
            failure = structural_failure(exc, plan_attempt=round_index+1, repair_attempt=repair)
            record(failure.diagnostic)
            if repair or not failure.repairable:
                raise failure from None
            previous = failure
            continue
        except LLMError:
            if cancellation is not None:
                cancellation.checkpoint()
            failure = PlanFailure(RuntimeDiagnostic(stage="planner_provider_transport", status="failed",
                error_category="provider_failure", schema_model="Plan", plan_attempt=round_index+1,
                repair_attempt=repair, repair_result="failure" if repair else "not_attempted"), repairable=False)
            record(failure.diagnostic)
            raise failure from None
        if cancellation is not None:
            cancellation.checkpoint()
        record(RuntimeDiagnostic(stage="planner_semantic_validation", status="succeeded", error_category="none",
            schema_model="Plan", plan_attempt=round_index+1, repair_attempt=repair,
            repair_result="success" if repair else "not_attempted", tool_request_count=len(plan.tools)))
        # Validate ALL candidate permissions/sources before any tool executes.
        for request in plan.tools:
            if registry.specs[request.name].permission == "candidate" and (
                not registry.permitted(request, plan.relevance) or request.arguments.user_quote != registry.user_text):
                failure = PlanFailure(RuntimeDiagnostic(stage="tool_permission_validation", status="failed",
                    error_category="security_violation", schema_model="ToolRequest", plan_attempt=round_index+1,
                    repair_attempt=repair, tool_request_count=len(plan.tools), tool_name_category="registered_candidate"), repairable=False)
                record(failure.diagnostic)
                raise failure from None
        return plan
    raise AssertionError("Unreachable repair bound.")
