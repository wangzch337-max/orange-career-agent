# agents

这里实现三个推理 Agent 与产品层 Orchestrator Agent。`SelfDiscoveryAgent` 与 `JobIntelligenceAgent` 均通过显式 `LLMProvider` 注入实现 evidence-backed semantic extraction；Match & Insight 仍是 Phase 1 exact-overlap stub。
