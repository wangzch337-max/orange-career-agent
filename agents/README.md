# agents

这里实现三个推理 Agent 与产品层 Orchestrator Agent。`SelfDiscoveryAgent`、`JobIntelligenceAgent` 与 `MatchInsightAgent` 均通过显式 `LLMProvider` 注入；每个 LLM extraction 后都有 evidence whitelist 与确定性 assembler。Match 不计算总体分或岗位排名。
