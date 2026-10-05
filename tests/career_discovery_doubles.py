"""Public synthetic inputs reused from the frozen universal-career harness."""

from career_background_evaluation.harness import CareerHarness
from career_background_evaluation.scenarios import SCENARIOS
from career_discovery.context import BACKGROUND


def prepared(root, scenario=SCENARIOS[3]):
    harness = CareerHarness(root, scenario)
    harness.prepare()
    harness.resolve_all()
    harness.confirm(memory=True)
    return harness


def proposal_from_payload(payload, *, titles=("Business Analysis", "Process Improvement", "Knowledge Operations")):
    sources = payload["sources"]
    background = next(s for s in sources if s["origin"] == "confirmed_profile" and s["category"] in BACKGROUND)
    current = [s["ref"] for s in sources if s["origin"] == "current_explicit"]
    historical = [s["ref"] for s in sources if s["origin"] == "confirmed_memory"]
    directions = []
    for title in titles:
        directions.append(dict(title=title, direction_family=title, source_refs=[background["ref"], *current, *historical],
            transferable_capabilities=[dict(interpretation="learning_foundation" if background["category"] == "education" else "structured_documentation",
                anchors=[dict(source_ref=background["ref"], excerpt=background["text"].split(" · ")[0])],
                relevance_to_direction="potential_transfer", uncertainty="requires_validation")],
            transition_considerations=[dict(kind="domain_transfer", source_refs=[background["ref"]],
                topic="相关工作情境", state="unknown")], uncertainties=["尚未选定最终方向"],
            evidence_gaps=["方向相关的实际职责情境"], goal_relation="EXPLORATORY", confidence="TENTATIVE"))
    return dict(directions=directions)
