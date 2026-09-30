# Orange 约 15 天实施计划 Implementation Plan

本计划以**能力里程碑**而不是机械的“一天一个 Phase”推进。15 天是聚焦范围下的估算；学习检查或质量门未通过时应延长，不以赶日程为理由跨阶段。每个 Phase 都必须遵守 `LEARNING_PLAN.md` 的 Learning Mode。

## 总览

| 建议日程 | Phase | 能力里程碑 | 主要产物 |
|---|---|---|---|
| Day 1 | 0 | Foundation & Product Contract | 产品／架构／数据契约、ADR、学习与安全规则 |
| Day 2 | 1 | Domain Models | 核心 Pydantic models、schema tests |
| Day 3 | 1 | Deterministic Workflow Skeleton | 状态枚举、确认门、路由测试 |
| Day 4 | 2 | Provider Abstraction | fake provider、首个结构化调用、错误边界 |
| Day 5 | 3 | Self-Discovery Agent | evidence-first 画像草案与确认流程 |
| Day 6 | 4 | Job Intelligence | 角色规范化、15–20 个脱敏 Demo 角色草案 |
| Day 7 | 5 | Match & Insight Engine | 多维解释、friction、gap、actions |
| Day 8 | 6 | LangGraph Integration | 可暂停／恢复的 Golden Flow |
| Day 9 | 7A | Structured & Persistent Memory | confirmed profile versions、curated records、lexical retrieval、purge |
| Day 9.5 | 7.5 | Interactive Demo Vertical Slice | Streamlit presentation adapter、真实 graph confirmation、三角色 Demo |
| Later | 7B | Semantic/Vector Retrieval | 单独评估 embedding、vector backend 与检索质量；未开始 |
| Day 10 | 8 | Observability | Agent/Tool/workflow events 与脱敏 trace |
| Day 11 | 9 | Streamlit UI | 输入、画像确认、洞察、trace 界面 |
| Day 12 | 10 | Course Data Adapter | mock + sanitized export provider |
| Day 13 | 11 | Reliability & Cost | 测试、错误处理、重试、成本控制 |
| Day 14 | 12 | Demo & Story | Golden/edge cases、README、面试叙事 |
| Day 15 | 13 | Final Polish | release audit、演示视频与 fallback |

## Phase 0 — Foundation & Product Contract

**范围：**建立目录、产品契约、概念架构、数据契约、ADR、安全和学习约束；不实现业务功能。

**Exit criteria：**Phase 0 验证清单全部通过；四个 Agent 命名一致；README 不声称未实现能力；仓库无敏感数据；开发者明确批准 Phase 1。

**用户学习检查：**开发者能回答 `LEARNING_PLAN.md` 的五个 Phase 0 问题，并用自己的图解释确认门、Memory 分层和可观测性。

**主要风险与 fallback：**范围膨胀会把设计误当实现；若契约有争议，保留 ADR 的 Proposed 状态并暂停实现，不通过代码掩盖分歧。

## Phase 1 — Domain Models + Deterministic Workflow Skeleton

**范围：**实现最小 Pydantic domain models、schema version 与不依赖 LLM 的状态转换；画像确认是硬门。

**Exit criteria：**合法／非法 schema、版本和状态转换测试通过；未确认画像无法进入 matching；无外部 API。

**用户学习检查：**开发者亲手完成至少一个核心 model 与一个拒绝非法转换的测试，能区分 schema invariant 和 workflow invariant。

**主要风险与 fallback：**一次建模过多。Fallback 是只保留 `EvidenceItem`、最小 `UserProfile`、`WorkflowState` 和引用类型，其余按使用阶段加入。

## Phase 2 — LLM Provider Abstraction + First Structured LLM Call

**范围：**定义 `LLMProvider` 协议、fake adapter、一个低成本 provider adapter、结构化输出校验、timeout 与有限重试。

**Exit criteria：**业务层不导入供应商 SDK；成功、无效结构、timeout 和限额场景有测试；secret 与原始敏感 prompt 不入日志。

**用户学习检查：**开发者亲手配置本地环境并解释 provider/adapter、schema validation 和重试边界。

**主要风险与 fallback：**API 不可用、模型结构化输出不稳定。Fallback 是使用 deterministic fake provider 推进离线集成，不同时接入多个真实 provider。

## Phase 3 — Self-Discovery Agent

**范围：**从脱敏输入提取候选技能、兴趣、价值观、优势、发展领域和目标，关联证据，输出画像草案。

**Exit criteria：**事实／证据／推断／建议可区分；重要结论含 `evidence_ids` 与 confidence；用户可编辑并确认；无人格诊断。

**可选用户参与：**开发者可修改私有 Golden Case 的一项非敏感职业偏好并重跑本地 Demo；正式学习 quiz 已由用户选择跳过，不作为完成门。

**主要风险与 fallback：**过度推断或证据重复计数。Fallback 是减少推断字段、提高人工确认权重，并只显示明确输入与高质量证据。

## Phase 4 — Job Intelligence Agent + Demo Job Dataset

**范围：**创建约 15–20 个代表角色的脱敏、可追溯 fixture，生成一致的实际工作、能力、路径、优缺点与工作方式。

**Exit criteria：**角色覆盖 Product/Business、Data、Engineering/AI、Research/Technical 与 Cross-functional；来源和时间可追溯；职业理解与热度分离。

**用户学习检查：**开发者亲手研究若干角色并说明如何避免由单个招聘广告过度概括。

**主要风险与 fallback：**研究时间和来源质量不足。Fallback 是缩至 8–10 个高质量代表角色；不使用未经审阅的大规模抓取数据。

## Phase 5 — Match & Insight Engine

**范围：**以 confirmed profile 与 Job Intelligence 的双向证据关系实现 alignment、evidence gap、confirmed gap、depth gap、friction、unknown 和 issue-linked actions；不计算总体分或岗位排名。

**Exit criteria：**所有双域 ID 与 action policy 可确定性验证、缺失证据不被当作能力弱、20 roles 离线通过、报告含局限且没有总体分或排名。

**可选用户参与：**开发者可修改一个公开合成偏好并观察 preference alignment／friction 的变化；正式 quiz 不作为完成门。

**主要风险与 fallback：**语义关系越界、把 evidence gap 当作 capability gap。Fallback 是拒绝无效关系／行动，并只展示通过确定性 evidence validation 的分类、证据与不确定性。

## Phase 6 — LangGraph Full Workflow Integration

**范围：**用 LangGraph 表达完整状态图、确定性条件路由、画像确认 interrupt/resume，以及内存与本地 SQLite workflow checkpoint；provider 重试所有权保持在既有 provider policy。

**Exit criteria：**Golden Flow 端到端通过；确认前暂停；修订后增加 profile version 并再次暂停；SQLite runner 重建后从同一 thread 恢复且 Self-Discovery 不重跑；安全失败路径有测试；旧 deterministic engine 保持回归通过。

**可选用户参与：**运行 public SQLite offline Demo，在 profile interrupt 后退出，再用相同 workflow ID 恢复并确认，观察 Self-Discovery call count 前后仍为 1。此任务不是考试或 Phase 完成门。

**主要风险与 fallback：**框架复杂度超出 Demo 价值。Fallback 是只把高价值状态与确认门放入 LangGraph，纯函数继续保留为独立 service。

## Phase 7A — Structured & Persistent Memory

**范围：**把 workflow checkpoint 与 long-term memory 分开；实现 confirmed `StructuredProfileStore`、curated `MemoryRecord` lifecycle、subject isolation、不可变版本历史、current pointer、idempotent replay、supersede/archive、transactional hard purge 和 deterministic lexical retrieval。

**Exit criteria：**只有 confirmed profile 能进入权威 store；重复写入幂等而冲突写入失败；active retrieval 默认只含 confirmed records；history、purge、subject isolation、graph confirmation replay 和 separate SQLite boundaries 都有离线测试；没有 transcript dump、embedding 或 vector retrieval。

**可选用户参与：**运行 public synthetic memory Demo，观察 preference 被新 confirmed record supersede 后，active query 只有新记录而 history 保留两条。此任务不是考试或 Phase 完成门。

**主要风险与 fallback：**把 relevant 当 true、把 checkpoint 当 memory 或在 resume 时重复写入。Fallback 是把 authority 固定在显式 confirmation/lifecycle、保持两个 DB，并让确认 side effect 使用 immutable identity 幂等。

**状态：COMPLETE。** Phase 7A 已通过 370 项回归并建立本地 checkpoint；Phase 7.5 不修改其 authority semantics。

## Phase 7.5 — Orange Interactive Demo Vertical Slice

**范围：**用 Streamlit 把现有 public offline engine 组成一条可见 vertical slice：Welcome → synthetic About You → real LangGraph Self-Discovery interrupt → same-thread profile confirm/resume → 三个固定角色 → validated Job Intelligence／Match／Actions → confirmed Profile Memory summary。

**Exit criteria：**每个 browser session 使用独立 `InMemorySaver` 与 temporary memory DB；Self-Discovery 在确认前后 call count 均为 1；UI 只使用 Fake provider 和 public fixture；三个角色保持固定顺序；没有总体分、排名、private mode、external data、vector retrieval；Streamlit AppTest、controller tests、全部旧回归和本地手动 vertical slice 通过。

**可选用户参与：**从 Welcome 手动走到 Profile Confirmation，打开三个角色的 Match 页面和 Memory Summary，再 Reset Demo；重点观察 profile confirmation 没有重新运行 Self-Discovery。此任务不是考试或完成门。

**主要风险与 fallback：**Streamlit rerun 可能意外重建 runtime 或触发重复 side effect。Fallback 是 controller/checkpointer 保存在 browser session state、start 保持幂等、domain status 决定可导航页面，并由真实 graph state 而非 UI boolean 掌握进度。

## Phase 7B — Semantic/Vector Retrieval（未开始）

**范围：**另行评估 semantic retrieval 的实际需求、embedding 模型、local vector backend、privacy/retention、版本兼容和 retrieval evaluation；Phase 7A 不预选 Chroma、sqlite-vec 或其他 vector store。

**Exit criteria：**尚未定义为已实现。必须在新的明确授权与设计审查后确定，且 semantic relevance 不得获得事实权威。

**主要风险与 fallback：**vector similarity 可能召回语义相近但过时或非权威记录，并增加依赖与隐私面。Fallback 是保留已验证的 metadata + deterministic lexical retrieval。

## Phase 8 — Observability

**范围：**实现 `AgentEvent`、`ToolEvent`、routing、error、retry、latency 与可用时的 model usage。

**Exit criteria：**一次 workflow 可用 id 串联；敏感字段脱敏；UI 能显示安全摘要；不记录／展示隐藏 chain-of-thought。

**用户学习检查：**开发者用 trace 定位一次故障并解释为什么日志足以诊断。

**主要风险与 fallback：**过量日志泄露数据或干扰 UI。Fallback 是只保留生命周期、引用、计数、错误码和延迟等最小事件。

## Phase 9 — Streamlit UI

**范围：**中文优先界面，包括背景输入、画像编辑／确认、角色洞察、证据、行动计划、follow-up 与 execution trace。

**Exit criteria：**完整 Golden Flow 可由非开发者操作；rerun 不重复副作用；错误／等待／空状态明确；不把分数做成权威排名。

**用户学习检查：**开发者亲手实现画像确认交互并完成一次观察式可用性测试。

**主要风险与 fallback：**UI polish 挤压核心可靠性。Fallback 是使用少量清晰页面，不做动画、复杂主题和高级图表。

## Phase 10 — Course Data Adapter / Sanitized Canvas Export

**范围：**定义并实现 `CourseDataProvider`，支持 mock fixture 与来自独立同步项目的脱敏规范化导出。

**Exit criteria：**Orange 无 Canvas token 或 API 调用；Demo 完全离线；字段最小化与去标识化人工审阅通过；其他大学 adapter 可替换。

**用户学习检查：**开发者亲手完成字段映射与公开安全审查。

**主要风险与 fallback：**跨仓库格式漂移或意外敏感字段。Fallback 是固定版本的手工脱敏 fixture，并拒绝未知字段。

## Phase 11 — Testing + Error Handling + Cost Controls

**范围：**补齐 unit/contract/integration/E2E、fault injection、error taxonomy、有限重试、缓存与预算观察。

**Exit criteria：**核心测试矩阵通过；重试幂等且有上限；模型不可用时可解释降级；单次 Demo 的成本／延迟有预算。

**用户学习检查：**开发者编写一个 E2E 和一个故障测试，解释重试为何不会污染状态。

**主要风险与 fallback：**追求覆盖率数字而忽略关键路径。Fallback 是优先确认门、schema、provenance、provider failure 和 Golden Flow。

## Phase 12 — Demo Cases + README + Interview Story

**范围：**准备一个 Golden Case、一个边界案例、准确 README、架构讲解和面试故事。

**Exit criteria：**案例可重复；README 明确已实现／计划中；claim 有运行证据；开发者能独立讲解决策和亲手工作。

**用户学习检查：**开发者做一次无稿演示并回答追问。

**主要风险与 fallback：**演示脚本只覆盖 happy path。Fallback 是至少保留一个输入不足或模型失败的可见恢复案例。

## Phase 13 — Final Polish + Demo Video

**范围：**视觉与文案一致性、干净环境复现、安全扫描、release checklist、视频和离线 fallback。

**Exit criteria：**安装／运行可复现；测试与 secret scan 通过；视频不含隐私；已知限制公开；fallback 可演示。

**用户学习检查：**开发者亲自录制和讲解，能区分已完成、主动删减和未来计划。

**主要风险与 fallback：**视频录制时网络／provider 失败。Fallback 是使用事先验证的脱敏 fixture 与离线 deterministic replay，清楚标记其性质。

## 不损害核心 Demo 的可删减项

进度受限时，按以下顺序优先删减，而不是牺牲画像确认、证据或安全：

1. Vector Memory／Chroma（保留 session + structured profile）；
2. 实时职位搜索、网页抓取和大规模数据集；
3. 多个真实 LLM provider（保留接口、fake 与一个 adapter）；
4. Canvas 在线连接（保留 mock／脱敏导出 adapter）；
5. 高级 UI 动画、复杂图表、导出格式和主题；
6. 大量 follow-up 能力与非核心角色。

不可删减的核心是：用户画像确认、四个 Agent 的清晰边界、deterministic-first Orchestrator、结构化契约、evidence-first 双面洞察、公开安全数据、关键错误路径和一个可复现 Golden Case。
