# Orange 架构决策记录 Architecture Decision Records

本文记录影响多个阶段、需要长期保持一致的决策。Phase 0 的记录为 **Accepted**；后续如需改变，必须新增替代 ADR，而不是静默重写历史。

## ADR-001 — 中文优先文档，英文代码标识符

**Context**
开发者与首要演示受众使用中文，但代码需要便于工程协作、库集成和公开作品集阅读。

**Decision**
README、产品／架构文档、未来 UI 和演示报告以中文为主，必要时保留 English terms；Python 类、函数、变量和模块等标识符统一使用专业英文。

**Why**
中文降低产品与学习沟通成本；英文标识符与 Python 生态、API 和招聘场景保持一致，也避免混合命名造成维护困难。

**Tradeoffs**
文档可能比单语略长，贡献者需要维护术语一致性；部分概念需中英并列。

**Status**
Accepted — Phase 0

## ADR-002 — Deterministic-first Orchestrator

**Context**
Golden Flow 包含校验、画像确认、路由、重试、错误处理和成本控制。若全部由 LLM 自由决定，行为难复现，也可能跳过关键人工确认。

**Decision**
Orchestrator Agent 以显式状态和确定性路由为主；仅在语义判断有价值时调用 LLM。未来优先用 LangGraph 表达状态转换和 human-in-the-loop 门。

**Why**
提高可测试性、可审计性、安全性和成本可控性，保证未确认画像不能进入最终匹配。

**Tradeoffs**
需要提前设计状态与边，灵活性低于完全自治 Agent；新增路径要更新 schema 和测试。

**Status**
Accepted — Phase 0

## ADR-003 — Structured Profile 与 Vector Memory 分离

**Context**
用户画像需要精确字段、版本、确认状态与可编辑性；历史对话和长文本更适合语义检索。

**Decision**
将 Session Memory、Structured Profile Store 和 Vector Memory 作为不同层。确认后的结构化画像是权威来源；向量检索只提供候选上下文和证据。

**Why**
向量相似度无法保证完整、最新或精确更新，不能承担权威用户状态。分层可支持冲突解决、删除、版本化和可靠测试。

**Tradeoffs**
需要同步引用与清晰权威顺序，系统接口更多；部分内容可能在结构化记录与检索索引中以不同形式出现。

**Status**
Accepted — Phase 0

## ADR-004 — Provider-agnostic LLM Layer

**Context**
未来可能评估其他 provider，但成本、可用性、模型能力和 SDK 都会变化。

**Decision**
业务层依赖 `LLMProvider` 契约；具体 provider 作为 adapter。配置通过环境变量注入；Phase 0 不选模型、不实现 provider。

**Why**
避免业务规则绑定供应商格式，支持 fake 测试、替换、成本比较与故障降级。

**Tradeoffs**
统一接口只能覆盖共同能力；供应商特有功能可能需要可选扩展，adapter 也增加维护量。

**Status**
Accepted — Phase 0

## ADR-005 — Canvas 通过脱敏适配器隔离

**Context**
独立项目 `cityu-canvas-sync` 已负责安全只读同步；Orange 是公开项目，不应持有 Canvas 凭据或依赖在线服务完成 Demo。

**Decision**
数据流为 Canvas → 独立同步项目 → sanitized normalized export → Orange `CourseDataProvider`／`CourseDataTool`。Orange V1 不读取另一个仓库的 `.env.local`，不共享 token，也不直接调用 Canvas API。

**Why**
缩小凭据和隐私风险，保持 Demo 离线可复现，并允许 mock 与其他大学 adapter 使用同一契约。

**Tradeoffs**
导出格式需要版本管理，数据不是实时的；跨项目变更需要协调。

**Status**
Accepted — Phase 0

## ADR-006 — Execution Observability，不暴露隐藏 Chain-of-Thought

**Context**
用户与开发者需要理解流程状态、证据、工具、路由、错误和成本，但隐藏推理并非可靠或适合展示的产品数据。

**Decision**
记录并展示 `AgentEvent`、`ToolEvent`、workflow event、安全参数摘要、公开规则、evidence id、结构化 decision summary、错误、重试、延迟及可用时的模型用量；不记录或声称展示 raw/hidden chain-of-thought。

**Why**
可审计事实和结构化摘要足以支持调试与信任，同时降低隐私、误导和信息泄露风险。

**Tradeoffs**
某些模型错误仍需通过输入／输出与复现实验诊断；事件 schema 和脱敏规则需要维护。

**Status**
Accepted — Phase 0

## ADR-007 — Public-repository-safe Demo Data

**Context**
首个 Golden Case 受开发者真实背景启发，但仓库计划公开，真实学号、联系方式、账户、课程凭据和 token 不可进入历史。

**Decision**
公开 fixture 必须去标识化、最小化并人工审阅；真实本地输入放入被忽略的 `data/private/`，Phase 0 不创建任何真实或虚构的个人画像内容。

**Why**
保护个人和学校系统安全，避免 Git 历史永久泄露，同时让 Demo 可共享、可复现。

**Tradeoffs**
脱敏数据可能降低部分真实性，需要额外审阅并维护 public/private 边界。

**Status**
Accepted — Phase 0

## ADR-008 — Learning Mode 是核心开发约束

**Context**
项目目标不仅是交付 Demo，也包括让开发者学习 Python 工程、Agent 架构、LangGraph、数据建模、LLM、记忆、检索、可观测性、UI 和测试。

**Decision**
每个阶段明确 Codex 负责、开发者亲手完成、必懂概念、验收／面试问题和停止条件。未经学习检查和明确确认不自动进入下一阶段。

**Why**
开发者应能独立解释和维护系统；关键实现经验不能为追求交付速度而全部外包。

**Tradeoffs**
进度可能慢于全自动生成；需要安排审阅和亲手任务，但这些任务必须有真实学习价值，不能成为人为忙碌。

**Status**
Accepted — Phase 0

## ADR-009 — Provider-independent structured LLM boundary

**Context**
Phase 2 需要验证真实模型的严格结构化输出，但未来 Agent 不应依赖 Alibaba base URL、workspace ID、API key 名称、OpenAI-compatible request 细节或某一 SDK response。

**Decision**
领域与未来 Agent 依赖通用 `LLMProvider.generate_structured()` 契约。`FakeLLMProvider` 负责离线测试；`QwenProvider` 是 Phase 2 唯一 live adapter，使用 Pydantic JSON Schema parsing、non-thinking mode、单层有限重试和 credential-safe response wrapper。

**Reason**
Dependency inversion 允许测试不联网、供应商替换不改变 Agent 领域逻辑，并在模型输出进入领域层前统一执行 schema、evidence-ID 和错误验证。

**Tradeoffs**
通用契约只暴露当前真正需要的共同能力，供应商特有参数必须留在 adapter；严格 schema 可能拒绝部分可读但不合约的响应。额外边界也增加少量类型与测试代码。

`qwen3.8-flash` 是当前 Phase 2 Demo 模型，不是永久硬编码的产品依赖。Phase 2 的 live guard 会拒绝其他模型；未来阶段若更换模型，应通过受控配置与 adapter 变更完成。

**Status**
Accepted — Phase 2
