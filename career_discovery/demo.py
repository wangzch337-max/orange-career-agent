"""Explicit public offline example, never a normal-runtime failure fallback."""

from copy import deepcopy
import json
from pathlib import Path

from career_discovery.context import BACKGROUND
from career_discovery.models import DiscoveryProposal
from career_discovery.service import PROMPT_NAME, PROMPT_VERSION
from providers.fake import FakeLLMProvider


PUBLIC_DEMO_PATH = Path(__file__).resolve().parents[1] / "data/fixtures/career_discovery/public_demo_proposal.json"
PUBLIC_DEMO_NOTICE = "当前是离线演示模式。这些合成方向用于展示 Orange 的探索流程，不代表真实模型或实时职业市场结论。"


def public_template():
    """Strict proposal schema also applies to the code-owned public fixture."""
    if PUBLIC_DEMO_PATH.stat().st_size > 16000:
        raise ValueError("PUBLIC_DEMO_BUDGET")
    return DiscoveryProposal.model_validate(json.loads(PUBLIC_DEMO_PATH.read_text(encoding="utf-8")))


def proposal_from_payload(payload, *, titles=None):
    """Bind example anchors to this request; no new facts or inferred role fit.

    Optional titles preserve existing offline test variations. The UI provider
    never supplies them and always uses the single public proposal fixture.
    Context reference/semantic validation remains CareerDiscoveryService-owned.
    """
    template = public_template().model_dump(mode="json")
    items = template["directions"]
    if titles is not None:
        items = [{**deepcopy(items[0]), "title": title, "direction_family": title} for title in titles]
    if not items:
        return {"directions": []}
    sources = payload["sources"]
    background = next(s for s in sources if s["origin"] == "confirmed_profile" and s["category"] in BACKGROUND)
    current = [s["ref"] for s in sources if s["origin"] == "current_explicit"]
    historical = [s["ref"] for s in sources if s["origin"] == "confirmed_memory"]
    for item in items:
        item["source_refs"] = [background["ref"], *current, *historical]
        for capability in item["transferable_capabilities"]:
            if background["category"] == "education":
                capability["interpretation"] = "learning_foundation"
            capability["anchors"] = [{"source_ref": background["ref"], "excerpt": background["text"].split(" · ")[0]}]
        for consideration in item["transition_considerations"]:
            consideration["source_refs"] = [background["ref"]]
    return DiscoveryProposal.model_validate({"directions": items}).model_dump(mode="json")


class PublicSyntheticDiscoveryProvider(FakeLLMProvider):
    """Only explicitly demo-configured workspaces install this network-free Fake."""

    def __init__(self):
        super().__init__(None)

    def generate_structured(self, messages, response_model, options, *, prompt_name, prompt_version):
        if (response_model is not DiscoveryProposal or prompt_name != PROMPT_NAME or prompt_version != PROMPT_VERSION or
                options.max_retries != 0 or options.thinking_enabled or options.model != "qwen3.8-flash"):
            raise ValueError("PUBLIC_DEMO_SCOPE")
        self.predefined_response = proposal_from_payload(json.loads(messages[1].content))
        return super().generate_structured(messages, response_model, options,
            prompt_name=prompt_name, prompt_version=prompt_version)
