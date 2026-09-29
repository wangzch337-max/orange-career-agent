# Versioned prompts

本目录只保存可审阅、可版本化的 Prompt。文件名包含版本；正常 observability 仅记录 `prompt_name` 和 `prompt_version`，不记录完整 Prompt 或用户输入。

Phase 2 Prompt：`profile_signal_extraction@v1`。它继续保留为隔离的 provider Demo 历史契约。

Phase 3 当前 Prompt：`self_discovery@v2`。它要求使用证据支持的最窄专业标签，区分 career／project／learning goals；权威画像由确定性 `ProfileAssembler` 构造。`self_discovery@v1` 保留为不可变历史。

Phase 4 Prompt：`job_intelligence@v1`。它只根据 `JobSourceEvidence` 抽取候选岗位信号；权威岗位记录由确定性 `JobIntelligenceAssembler` 构造。缺失信息必须保持 unknown，且禁止用户匹配、排名或推荐。

Phase 5 当前 Prompt：`match_insight@v5`。request-scoped provider schema 将 profile/job signal ID 限制为当前 `MatchContext` 的枚举，同时保留 bilateral、evidence-missing 与 unknown 三个 relation-aware 结构家族。权威 evidence links 由 `MatchEvidenceResolver` 根据 signal 所有权构造，权威 `MatchResult` 与用户可见 action 文案由确定性 `MatchInsightAssembler`／`ActionRenderer` 构造。缺失证据不等于能力缺口，且禁止总体分与岗位排名。`match_insight@v1`至 `match_insight@v4` 保留为不可变历史。
