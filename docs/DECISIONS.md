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

## ADR-010 — LLM 提取候选信号，确定性代码构造画像

**Context**
Self-Discovery 需要理解课程、项目和明确偏好的语义，但让模型直接拥有权威 `UserProfile` 会混淆事实与推断，也可能引入不存在的证据、弱点或偏好。

**Decision**
确定性 `SourceEvidenceBuilder` 首先建立稳定证据；注入的 `LLMProvider` 只生成 `SelfDiscoveryExtraction` 候选信号；确定性 evidence validator 与 `ProfileAssembler` 拒绝未知引用并映射为 draft `UserProfile`。缺少证据不是弱点，development area 只能由明确有限经验或直接能力缺口证据支持。

**Reason**
混合边界让 LLM 专注语义理解，同时由可测试 Python 保证 provenance、版本、确认状态和安全不变量。用户可以看到 explicit fact 与 evidence-supported inference 的区别，并在任何下游分析前确认或修订画像。

**Tradeoffs**
系统需要维护 extraction 与 domain 两套相邻 schema，并对映射编写更多测试；严格规则可能拒绝可读但证据不足的模型输出。作为回报，失败不会静默污染权威画像，离线 Fake integration 也可完整复现。

**Status**
Accepted — Phase 3

## ADR-011 — Job Intelligence 使用证据受限语义抽取与确定性组装

**Context**
岗位描述需要语义归纳实际工作、能力、工作方式与潜在摩擦，但通用模型知识可能把常见行业信息误写成特定岗位事实，也可能在缺少薪资、晋升或团队信息时自动补全。

**Decision**
确定性 `JobEvidenceBuilder` 先把 `JobRecord` 转为稳定、去重的 `JobSourceEvidence`。注入的 `LLMProvider` 只返回 `JobIntelligenceExtraction` 候选信号；确定性 evidence whitelist 与 `JobIntelligenceAssembler` 再建立权威 `JobIntelligenceRecord`。每个信号保留 confidence、evidence IDs 与 `explicit_job_fact`／`evidence_supported_job_inference` 区分。缺失岗位信息保存为 `JobUncertainty`，不由模型常识填充。

Job Intelligence 不接收 `UserProfile`，不计算 fit、排名、推荐、gap 或用户行动计划。公开 Demo 使用 20 条虚构 role archetypes；自动化测试只使用 `FakeLLMProvider`。

**Reason**
该对称混合架构让模型处理有限语义规范化，同时由可测试 Python 保证 provenance、缺失值与权限边界。岗位理解可独立复用，也不会提前混入 Phase 5 的用户匹配判断。

**Tradeoffs**
系统维护 extraction 与 domain 两套相邻 schema，严格 evidence 校验会拒绝部分看似合理但没有来源的输出；Demo archetype 也不能代表实时招聘市场。作为回报，缺失信息、事实／推断和每条语义结论都保持可审计。

**Status**
Accepted — Phase 4

## ADR-012 — Evidence-first Match、确认门与 issue-linked actions

**Context**
把职业探索压缩成总体匹配分会隐藏能力、兴趣、偏好、经验深度与未知信息之间的差异。更危险的是：模型可能把没有证据误写成能力不足，把未确认画像推断递归放大，或生成与已识别问题无关的流行技能建议。

**Decision**
Phase 5 不计算 overall score、fit percentage、weighted sum 或 role ranking。确定性 `MatchContextBuilder` 只接受 confirmed profile，并最小化用户／岗位 signals 与 evidence。注入的 `LLMProvider` 只提出 `MatchInsightExtraction`；`MatchInsightAssembler` 验证所有双域 ID、引用归属和 relation-specific 规则后构造权威 `MatchResult`。

`EVIDENCE_MISSING` 与 `CONFIRMED_GAP` 永久分离：前者只说明当前画像缺少验证材料；后者必须引用用户确认的 development-area 证据。每个 `ActionItem` 必须引用 validated issue，relation/action 允许表禁止 evidence missing 直接触发 deepen capability，action target 还必须存在于已验证 signal 中。`MatchContextBuilder`、Agent 和 assembler 三层都执行 confirmed-profile gate；私有 profile 只能由开发者本人在默认 N 的本地交互门中确认。

**Reason**
证据关系比单一分数更能解释为什么某条结论成立、哪里仍未知以及下一步为何合理。多层确定性校验阻止未确认推断、未知 ID、错误 gap 类型和不受支持建议进入权威状态，同时保留 LLM 处理跨表达语义关联的价值。

**Tradeoffs**
输出比一个分数更复杂，调用方需要按 relation type 展示；严格规则会拒绝部分可读但证据结构不完整的响应。Phase 5 也无法替用户选择最佳职业。作为回报，结果可审计、可纠正，并避免虚假精确性与证据缺失造成的伤害性判断。

**Status**
Accepted — Phase 5

## ADR-013 — LangGraph 仅作编排层，使用 interrupt 与本地 workflow checkpoint

**Context**
Phase 3–5 已分别验证 Self-Discovery、Job Intelligence、Match & Insight 与 deterministic ReportBuilder 的领域语义。Phase 6 需要让 Golden Flow 可暂停、人工审阅并跨 runner 恢复，但如果把 evidence、gap、action 或报告判断搬进 graph nodes，会产生第二份业务逻辑；如果把 SQLite checkpoint 称为 memory，也会提前混淆 Phase 7 的长期记忆边界。

**Decision**
LangGraph 只负责显式 `OrangeGraphState`、node sequencing、deterministic edges、execution status、safe failure routing、graph events 和 checkpoint。所有 nodes 调用现有 Agents／ReportBuilder；不使用 LLM router，不增加 graph-level semantic retry，也不实现并行 20-role fan-out。原有 `DeterministicWorkflowEngine` 保留为框架无关的回归基线。

画像确认使用 LangGraph `interrupt` 与同一 opaque thread ID 上的 `Command(resume=...)`。`CONFIRM` 复用 `UserProfile.confirm()`；`REVISE` 复用 `UserProfile.create_revision()`，之后再次 interrupt。自动测试使用 in-memory checkpointer；本地 restart/resume 使用 `data/private/runtime/orange_workflow.sqlite3` 的同步 SQLite checkpointer，并通过 context manager 管理连接。

SQLite 只保存恢复当前 workflow 所需的执行状态。它不是 long-term memory、vector memory、semantic retrieval、conversation history 或 multi-user profile store；Phase 7 仍未开始。

**Reason**
薄编排层使已经 live／offline 验证的语义保持单一权威来源，并让确认门、状态、失败和恢复路径可以独立测试。真实 interrupt/checkpoint 提供进程边界恢复能力；stable opaque identity 避免使用个人标识；保留旧 engine 证明领域代码不依赖 LangGraph。

**Tradeoffs**
项目暂时维护两个 orchestration entry points，但不维护两份 semantic logic。SQLite saver 适合本地同步 Demo，不适合多进程、云服务或 multi-user scale。Graph state 必须显式序列化／重新验证，增加少量 adapter code；换来的是 checkpoint 可移植性、隐私边界和可审计 routing。当前兼容的 SQLite checkpoint package 会安装其上游所需的 transitive packages，但 Orange 不使用任何 vector store 或 LangSmith service。

**Status**
Accepted — Phase 6

## ADR-014 — 分离 checkpoint 与 curated long-term memory，并延后 vector retrieval

**Context**
Phase 6 的 SQLite checkpoint 保存一次 LangGraph execution 的可恢复状态，但不能因此成为跨 workflow 的事实来源。Phase 7A 需要持久化已确认画像和少量长期有用记录，同时避免把整段对话、模型推断或高相关度检索结果升级为用户事实。可恢复节点也可能 replay confirmation side effect，因此写入必须可安全重复。

**Decision**
Workflow checkpoint 与 long-term memory 使用两个独立 SQLite 数据库。`data/private/runtime/orange_workflow.sqlite3` 只负责 graph resume；schema-versioned `data/private/memory/orange_memory.sqlite3` 只负责 confirmed `UserProfile` versions/current pointer 与 curated `MemoryRecord` history。

`StructuredProfileStore` 是完整 confirmed profile 的权威来源，保存不可变版本并拒绝 unconfirmed、version regression 和同 identity 冲突；相同语义版本 replay 幂等。`MemoryRecord` 使用 candidate、confirmed、superseded、archived lifecycle。LLM/model inference 默认只能成为 candidate；confidence 与 retrieval score 都不授予 authority。显式 supersede/archive 保留历史，subject purge 则在 transaction 中 hard-delete 该 subject 的 long-term rows，但不碰 workflow checkpoint。

Phase 7A retrieval 仅使用 subject/type/status/metadata filtering 与 deterministic lexical ranking。默认只返回 active confirmed records，并保留 status/provenance/relevance metadata。不开启 transcript storage、embedding、sqlite-vec、Chroma、vector similarity 或 LLM memory extraction；semantic/vector retrieval 留给 Phase 7B 的独立需求与隐私评估。

**Reason**
分离 execution recovery 与 durable knowledge，能让 retention、purge、authority 和 replay 语义各自清晰。Curated records 减少隐私与过时信息污染；显式 confirmation 避免模型 confidence 或相似度被误解为事实。不可变 identity 与 current pointer 使审计、history 和 resumable graph side effect 可确定性测试。Lexical retrieval 已足够验证 Phase 7A 的接口与 authority boundary，不需要提前引入 vector 依赖。

**Tradeoffs**
两个数据库与 profile/record 两套 store 增加少量 wiring，lexical overlap 也无法覆盖所有同义表达。Hard purge 不等于产品级“删除一切”，调用方未来若要同时删除 checkpoint 必须显式协调两个系统。Curated lifecycle 需要 caller 明确确认与 supersede，自动化程度较低；作为回报，历史、隐私、来源和事实权威保持可审计。

**Status**
Accepted — Phase 7A

## ADR-015 — Streamlit 作为 portfolio vertical slice 的 presentation adapter

**Context**
Phase 0–7A 已验证 Self-Discovery、Job Intelligence、Match、LangGraph interrupt/resume 和 persistent memory，但主要能力仍通过代码与 CLI 可见。作品集需要一个可操作的端到端 Demo，同时不能让 UI 重写业务规则、绕过 profile confirmation、读取私有数据或因 rerun 重复执行 Agent side effects。

**Decision**
Phase 7.5 使用 Streamlit 构建 Orange Interactive Demo v0.1，但只把它视为 presentation layer，不承诺最终 production frontend 架构。薄 `DemoController` 在每个 browser session 内组装现有 public offline dependencies、`InMemorySaver` 与 temporary SQLite `MemoryService`，并通过现有 `OrangeGraphRunner` 启动真实 interrupt、用 `ProfileReviewDecision(CONFIRM)` 恢复同一 thread。

默认且唯一暴露的模式是 public synthetic fixture + `FakeLLMProvider`，固定显示 AI Product Intern、AI Application Engineer 和 Data Analyst。UI 只渲染 validated profile review payload、`JobIntelligenceRecord`、`MatchResult`、`ActionItem`、confirmed profile memory 和 allowlisted graph trace；不读取 private databases／credentials，不提供 live provider，不生成 score/ranking/action prose，也不实现 vector retrieval。Streamlit usage telemetry 关闭并默认绑定 localhost。

**Reason**
Streamlit 能以最少前端基础设施展示真实 Python／LangGraph engine，并提供官方 testing API 验证 click/rerun 行为。Session-scoped runtime 避免跨 browser sharing，真实 resume 证明 human-in-the-loop 不是 UI boolean；presentation mapping 让中文可读性提升而不改变 domain enums 或 evidence authority。

**Tradeoffs**
Streamlit rerun 与 server-side session object 不等于 production web architecture，也不提供 durable multi-user session、认证、移动体验或独立 frontend/backend deployment。Controller 暂时持有进程内 checkpointer 和 temporary DB，server restart 后 Demo 会重置。作为回报，v0.1 保持离线、可测试、截图友好，并让已验证 engine 在不扩大语义范围的情况下可见。

**Status**
Accepted — Phase 7.5

## ADR-016 — Conversation-first guided UX，而不是自由聊天机器人

**Context**
Phase 7.5 已证明 Streamlit 能以真实 LangGraph interrupt/resume 展示完整 vertical slice，但页面主要以资料与结果为中心，职业画像层级较弱、actions 偏模板化，空 Memory 也不容易解释。产品需要通过对话帮助学生逐步澄清方向，同时不能让自由文本 LLM 决定 workflow、把即时回答伪装成历史证据，或绕过现有画像、Match 和 Memory authority。

**Decision**
Phase 7.6 采用 conversation-first split workspace：左侧是小型、显式、确定性的 `ConversationStage` 引导流程，右侧是随回答更新的动态职业画像。主要输入是固定单选／多选、可选短文本和确认／修订控件；conversation routing 由 Python stage contract 决定，不调用 LLM。Guided session 完成后仍由现有 LangGraph 执行 Self-Discovery、profile interrupt、same-thread confirm/revise、Job Intelligence、Match 与 Report。

角色只在画像确认后作为无排名的探索方向出现。Role clarification 默认是 session-only；用户明确选择「保存」时，才通过现有 `MemoryService` 创建 confirmed `USER_FEEDBACK`，且只写当前 Demo temporary DB。Deprioritization、action status 与 exploration map 保持 session presentation state，不改变 MatchResult 或 profile authority。Action UI 使用 authoritative ActionItem 的 rationale／description／target／expected evidence，并只增加确定性的 task scaffolding。

**Reason**
结构化对话能实现 progressive disclosure、让动态画像与未知项逐步可见，并保持可预测、可测试的产品路径。它比永久自由聊天更容易说明证据、表达与确认的区别，也防止模型控制 workflow。明确的 Memory 选择保留用户控制权，并让“长期理解”只包含 confirmed information。

**Tradeoffs**
固定问题无法覆盖所有个性化追问，role Q&A 也只能使用预定义菜单；conversation state 与 graph state 需要清晰的 adapter 边界。Temporary Demo feedback 会在 reset 或 server restart 后消失，且 v0.2 不提供任意 profile field 编辑。作为回报，交互完全离线、可回归、无 provider 成本，并避免新的 LLM、private-data 和 retrieval 风险。

**Status**
Accepted — Phase 7.6

## ADR-017 — Derived local vector index、confirmed-only authority 与 RRF

**Context**
Phase 7A lexical retrieval 无法稳定覆盖中英文改写，但 semantic similarity 也可能召回过时、candidate 或错误 subject 的内容。当前 stdlib sqlite3 不支持 loadable extensions，而 canonical store 已有稳定 authority／lifecycle 语义，不能为了 vector backend 被全局替换。

**Decision**
Canonical `orange_memory.sqlite3` 和 `memory/sqlite_store.py` 继续只使用 stdlib sqlite3。Derived `orange_vectors.sqlite3` 单独使用 `pysqlite3 0.6.0 + sqlite-vec 0.1.9`，不 monkey-patch `sys.modules`；index 可删除、可重建，不成为 source of truth。

Private long-term Memory 的 embedding 默认使用 local provider。Normal tests 注入 stable SHA-256 `FakeEmbeddingProvider`；显式 real validation 使用 FastEmbed CPU 与 Apache-2.0 `paraphrase-multilingual-MiniLM-L12-v2`。只有 active confirmed `MemoryRecord` 默认入索引，StructuredProfileStore、transcript、JobRecord、MatchResult 和 ActionItem 不自动 vectorize。

每个 semantic hit 必须用 subject + memory ID 回查 canonical store，并重新验证 confirmed status、active lifecycle、type 与 content hash。Lexical path 保留；hybrid 用固定 one-based RRF `k=60`，不相加 raw lexical/cosine score。`MemoryContextBuilder` 只构造 bounded structured context；自动 Agent/LangGraph injection deferred。

**Reason**
物理和 binding 分离保护已验证的 canonical semantics；local embeddings 避免 private Memory 离开设备；confirmed-only + lookup defense 阻止 stale vectors 复活非权威内容。RRF 能融合异质 rank，而不伪装成统一 truth scale。

**Tradeoffs**
两个 DB 无法共享 atomic transaction，index sync failure 必须 diagnostic + rebuild；ONNX model 增加约 0.22 GB local cache 与首次加载成本；semantic quality 只能通过有限 acceptance cases 观察，不能据此声称普遍准确。删除 vector DB 会暂时触发 surfaced lexical fallback，但不会损坏 canonical Memory。

**Status**
Accepted — Phase 7B

## ADR-018 — Explicit memory-use policies and human-confirmed change handling

**Context**
Phase 7B 能找到相关 active confirmed Memory，但 relevance 不能决定何时使用、谁可使用或是否意味着用户已改变偏好。若把 retrieval 做成全局 middleware，Job Intelligence、Match relation 或当前 session 表达可能被历史内容静默污染。

**Decision**
Phase 7C 只开放 `PROFILE_REFINEMENT` 与 `ROLE_EXPLORATION`。Code-owned `MemoryContextPolicy` 固定类型、hybrid retrieval、top-k、预算和唯一 consumer；retrieval 是只读路径。当前 explicit input 是本 session 最新表达，confirmed Profile 是画像权威，active confirmed Memory 是历史权威，三者不折叠。

只有已注册 structured signal 的 same-dimension value difference 可建立 session-only `MemoryChangeCandidate`。Semantic similarity 永远不自动判断 contradiction。用户明确 update 后，write command 才通过现有 `MemoryService.supersede()` 保存 history 并同步 vector lifecycle；profile 仍须独立 review／confirmation。Memory-aware statement 必须保留并重新验证 `memory_refs`。Job Intelligence 接收零 user Memory；Memory 不能直接 patch `MatchResult`。

**Reason**
Explicit policy 防止 consumer 扩权；read/write 分离防止 retrieval 自我强化；structured comparison 提供可解释的有限 change detection；human confirmation 保留用户对长期理解与画像版本的最终控制。

**Tradeoffs**
只覆盖少量 structured dimensions，free-text 变化需要人工澄清；profile 和 Memory confirmation 是两个步骤；role recall context 与 authoritative Match 必须在 UI 中分区，增加 presentation complexity。

**Status**
Accepted — Phase 7C

## ADR-019 — Golden evaluation 是离线外部 observer，不是总体评分或模型 judge

**Context**
Phase 7C 已完成。单元／回归测试能保护实现，但作品集还需要说明在职业探索情境中如何保持 uncertainty、evidence ownership、authority、lifecycle 和 human confirmation。总体分数会掩盖不同类型的失败，LLM judge 又增加不可复现、成本与隐私风险。

**Decision**
新增独立 `evaluation/`，保留 deterministic contract、semantic Golden、end-to-end journey 三层。27 个公开合成案例只用 FakeLLMProvider/FakeEmbeddingProvider 与隔离 temporary stores，观察既有生产 pipeline，不 repair、不重写 Match、不改变 UI。Closed statuses/taxonomy 产生可追溯 checks/findings；unknown 正确保留可为 EXPECTED_UNCERTAINTY，security/authority/subject/gate/lifecycle/network 必须 FAIL/BLOCKING。NEEDS_REVIEW 只用于明确 non-contract presentation ambiguity。

**Reason**
显式 required/forbidden/provenance 等规则使评价可重复、可定位、可手工解释；隔离状态与 latched offline guards 防止 private/network fallback。JSON 和 failures-first Markdown 同时服务脚本与人工审阅，不引入无依据的聚合质量分。

**Tradeoffs**
Fake suite 不能证明 live LLM 或真实 embedding 质量；label normalization 与窄 claim checks 不是通用 semantic entailment。Guard 是单线程 Python accident defense，不是恶意 native code sandbox。后续 8A.1 live 需要显式授权，8B diagnostics、8C polish、8D public readiness 均 deferred。Phase 8A 代码保留未提交，等待开发者明确批准。

**Status**
Accepted — Phase 8A

## ADR-020 — 本地最小内容诊断与 evaluation correlation 分离

**Context**
Phase 8A Golden suite 已建立 checkpoint。跨 workflow/HITL/Memory/vector/Match 的诊断仍分散在原事件列表；直接输出原始状态或自由 summary 可能泄露 profile、Memory、Prompt 或凭据。

**Decision**
新增独立 strict `orange.observability.v1`。保留原事件，显式 adapter 投影；高价值操作用 scoped coarse spans，不重写业务逻辑。每个 session/scenario 独立 bounded in-memory collector，ContextVar 只传播显式 context，并 finally reset。run 穿过确认门，parent 必须同 run；Reset 清空旧 collector。UI 只升级默认折叠 Developer Trace，所有展示重新验证；report 只引用 run/event IDs，不存 full trace。

**Reason**
Closed keys/values 比 denylist/free-form summary 更能防止新字段泄露；内容最小化使安全与诊断可以同时成立。Observer failures 显式计数而不接管产品异常／权威。Evaluation check event 定位失败，但不把评价 taxonomy 注入生产组件，也不把 unknown 当 warning。

**Tradeoffs**
无持久化／exporter，Reset 后不能恢复历史 trace；4000-event cap 可截断诊断且会显式计数。Coarse spans 不提供每个内部 validation stage 的独立时长；旧事件顺序按 timestamp/sequence/ID 稳定排序。动态 IDs 只在 report transport 加入，不污染 deterministic scenario comparisons。Fake/stub 与合成 Demo 不等于 live/private quality validation。

**Status**
Accepted — Phase 8B 已获明确批准建立本地 checkpoint `5a6a1d1`；后续 8C 只改变表现层，8D 未开始。

## ADR-021 — Polish existing Streamlit product before public portfolio packaging

### Context

核心 workflow、证据关系、确认门、长期理解及安全诊断已通过 743 tests 和 27 Golden scenarios。产品体验需要更清晰的层级和一致性，而不是新业务能力。用户授权唯一 Phase 8B 本地 checkpoint，Phase 8C 仅 Product & Demo Polish；8D 需要另行批准。

### Decision

保留 Streamlit 和全部 backend semantics。集中轻量 tokens、native card、escaped badge/panel、固定 journey copy，优先对话 workspace／动态职业画像，再打磨 direction、role、Match、Action、Memory 和折叠诊断。采用渐进披露，岗位事实／用户情况／Memory 分离；十个产品视图达到本地展示准备状态，不自动生成截图。无 frontend rewrite，无评分／排名可视化，无新依赖。

### Reason

在已验证产品链上改进信息层级，成本小、风险可测，用户能更快理解当前证据状态和下一步。视觉 prominence 不能把兴趣变能力、未知变缺点、session input 变长期 Memory，或把 diagnostic observation 变权威。

### Tradeoffs

使用稳定原生结构和少量 CSS，不能达到专用前端的任意布局能力；CSS 依赖已固定版本 Streamlit 的结构，应在升级时重新验收。保留英文 evidence 原文而不翻译／改写冻结语义；中文 product framing 负责解释。AppTest 不做脆弱像素快照，窄布局采用真实浏览器 DOM/几何 smoke，最终审美仍由开发者在 live UI 中复核。

### Status

Accepted — Phase 8C，表现层修改不自动 commit/push；Phase 8D 未开始。

## ADR-022 — Product-first portfolio packaging without runtime changes

### Context

Phase 8C 在恢复 repository、Git metadata、evaluation output 写权限后再次通过 783 tests 与 27 Golden scenarios。用户明确授权唯一 checkpoint `003c5bc`：`feat: polish orange demo experience`，随后仅允许 Phase 8D public readiness。

### Decision

README 先解释产品、确认门、证据关系和行动，再展示 Product Flow / Agent Architecture / Memory Architecture。深层模块说明和旧 ADR 保留历史上下文，根目录当前说明与索引负责消除过时能力表述。只新增 documentation／readiness contracts，不修改任何现有生产代码、prompt、fixture、依赖、原 783 tests 或 artifact location。

完整历史与当前公开文件都审查；发现真实私有资料必须停止而非自动 rewrite。LICENSE、作者元数据、截图、未来 repository URL 与 visibility 由用户决定。截图先准备安全计划，无截图／外部 asset／云部署／push。

### Reason and tradeoffs

产品入口降低理解成本，同时以已执行的 Golden 与安全边界支持工程故事；不制造 live benchmark 或 production-ready 声明。Text-native Mermaid 可维护、不引入 asset license，但这里只做结构 syntax smoke，未宣称跨 renderer 的像素验证。模式扫描加人工 public-fixture review 降低泄露风险，不等于完备法律／隐私保证。为保持全部回归与阶段记录，冻结模块 README 中历史状态保留，并由当前根入口解释。

### Status

Accepted — Phase 8D；修改未提交。技术 gates 和 public-readiness review 结果见 [审查记录](PUBLIC_READINESS_AUDIT.md)。Phase 9A / 9B 未开始；本 ADR 不授权发布或改写历史。
