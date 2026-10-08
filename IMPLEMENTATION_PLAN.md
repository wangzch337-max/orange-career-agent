# Orange 约 15 天实施计划 Implementation Plan

本计划以**能力里程碑**而不是机械的“一天一个 Phase”推进。15 天是聚焦范围下的估算；学习检查或质量门未通过时应延长，不以赶日程为理由跨阶段。每个 Phase 都必须遵守 `LEARNING_PLAN.md` 的 Learning Mode。

## 当前里程碑：Online Foundation Pack 1

D.1–D.6 已冻结在 `b319c67`。获批范围仅 Unified Workspace / Storage Contracts：实际调用链审计、显式存储注入、进程内 Ephemeral adapters、既有 SQLite 兼容、共同合同及 D.1–D.6 双适配器回归、九套 offline evaluations、安全检查和必要文档。四 Agent/确认权威/Memory governance/来源验证不变，D.5/D.6 session-only。当前增量不 add/commit/push/deploy/live；不开发认证、Guest UI、PostgreSQL/RLS、无简历画像或 Product Polish，不进入 Pack 2。详见 [Pack 1](docs/ONLINE_FOUNDATION_STORAGE.md)（含 Learning Mode 与停止条件）。

### v1.3D.6 历史实施范围（现已冻结）

D.1–D.5 已冻结为 `d84005a`。本轮仅 Evidence Gap Validation：Candidate A + optional B、ONE UNKNOWN/PARTIAL unresolved user-side scope、九 public synthetic templates、deterministic source pins/lifecycle、主聊天 session-only。Profile/Memory writes=0/new consumer=NO、D.5 mutation=0、无 score/ranking/考试/fit judgment/Learning/Action Plan。本轮先 focused/full pytest，再 Golden/Agent/Universal/D.1–D.6 九 evaluations；不 add/commit/push/deploy/live/private/Product Polish。人工审阅 pending；详见 [D.6](docs/EVIDENCE_GAP_VALIDATION.md)。

D.6 的 handoff 只导航到已有审核入口，不自动转移、确认或启动旧流程。

### v1.3D.5 历史实施范围（现已冻结）

D.1–D.4 已冻结为 `044c8a2`。本轮获批 D.5 Evidence-based Match：A+B、单确认用户/单合法代表性角色、typed user/work projection、确认权威、Fake-only、证据关系和主聊天渐进展示；session-only，包括展示，不写 Profile/Memory、不新增 consumer、无 score/ranking/recommendation/Action Plan。先 focused/full，再 Golden/Agent/Universal/D.1–D.5；本轮未提交，不开始 Product Polish/Action/live/deploy。详见 [D.5](docs/EVIDENCE_BASED_MATCH.md)。

### v1.3D.4 历史实施范围（现已冻结）

D.1–D.3 Integration Checkpoint `dfeb535` 已 commit + 正常 push，冻结基线 3042 passed。D.4 获批实施 Representative Specific Role Understanding：现有9个 archetypes 各有独立公开合成代表性角色，精确 membership / refs / source pin、主聊天渐进问答、QA 共存、父链与 session-only 生命周期。无个人适配、筛选、真实招聘或新 Memory consumer，零 live。先 focused，再 full pytest，再 Golden / Agent / Universal / D.1 / D.2 / D.3 / D.4 七项 Evaluation；人工审阅仍 pending，不暂存/commit/push/deploy，不做 Final Product Polish。详见 [D.4](docs/REPRESENTATIVE_SPECIFIC_ROLE.md)。

D.1 已在 `2316616` 冻结（历史完整基线 2815 passed）。D.2 为已批准的 Chat-first Career Reality Exploration：公开合成资料、精确解析、工作目的/代表情境/有界追问、普通 QA 共存，零 live/Memory/Match/个人胜任判断。实施与离线验证结果以本阶段报告为准，修改保持未提交。根目录 app.py 历史 placeholder 非入口，不在本阶段重构。

v1.3B generation/Stop hardening 与 v1.3C 通用 Resume Intake、canonical ResumeEvidence、个性化 Clarification、逐项 Profile Refinement、跨背景/E2E/隐私验收为当前冻结范围。最新完整离线基线为2519 passed / 0 failed，Golden 27 / 20 PASS / 7 EXPECTED_UNCERTAINTY / 0 FAIL / 0 NEEDS_REVIEW，Agent 58 PASS，Universal 17 PASS / 1691 checks。有限 C.1/C.2/B.2 live 通过，B.3 修复后的 C.3/C.4 完整真实链仍是已记录、非阻塞的验证缺口；不要求更多 live 才能推进开发。详见 [冻结记录](docs/UNIVERSAL_CAREER_VALIDATION.md)。

上段 v1.3C 数字是历史冻结基线，不是 D.2 最新验收。下方 Phase 0–13 总览及 checkpoint/发布限制均为当时历史，不代表当前 Git 状态或新的调用/部署授权。D.2 不绑定后续岗位筛选、Match、行动、新闻、认证或部署。

## 历史总览

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
| Day 9.6 | 7.6 | Conversation-First Product Redesign | guided discovery、动态画像、role clarification、task UX、exploration map |
| Day 9.7 | 7B | Semantic & Hybrid Memory Retrieval | local embedding、derived sqlite-vec、canonical validation、RRF、bounded context |
| Day 9.8 | 7C | Context-Aware Memory Integration | explicit policies、profile refinement、role recall、human-confirmed changes |
| Day 10 | 8A | Evaluation Framework | contract / semantic Golden / journey、安全报告 |
| Day 10.5 | 8B | Safe Observability & Diagnostics | COMPLETE；checkpoint `5a6a1d1`，无 push |
| Day 10.6 | 8C | Product & Demo Polish | COMPLETE；checkpoint `003c5bc`，无 push |
| 当时 | 8D | Public Portfolio Readiness | 当时 COMPLETE — USER RELEASE DECISIONS PENDING；未提交 |
| 后续（未开始） | 8A.1 | optional live evaluation | 单独授权，不是当前离线质量证明 |
| 后续（未开始） | 9A | Web Deployment Readiness | 需要单独定义与授权 |
| 后续（未开始） | 9B | Public Web Deployment | 需要单独定义与授权 |

Phase 8C 已完成并在通过恢复权限后的 783 tests / Golden gates 后建立本地 checkpoint `003c5bc`：`feat: polish orange demo experience`，无 push。下面初始 Phase 9–13 内容仅保留历史路线，不是当前后续授权；部分 UI／可靠性／story 工作已提前纳入当前 Portfolio v1。

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

**状态：COMPLETE。** Phase 7.5 已通过 390 项回归，并以本地 Git checkpoint 固化；没有 push 或 remote 变更。

## Phase 7.6 — Conversation-First Product Redesign / Demo v0.2

**范围：**把 v0.1 结果页导向改为 conversation-first workspace。`GuidedConversation` 以显式 stage 和固定选项收集职业问题、活动偏好、AI 兴趣、项目贡献、工作方式与职业目标；右侧动态画像区分已有证据、用户刚刚表达、待确认与未知。画像确认继续通过真实 LangGraph interrupt／resume；确认后显示三个无排名探索方向、role clarification、八类 Match Insights、Why／What／Evidence／Status Action tasks、Career Exploration Map 与「Orange 对你的长期理解」。

**Exit criteria：**conversation routing 完全确定且不由 LLM 决定；roles 在确认前不可用；same-thread confirmation 前后 Self-Discovery call count 为 1；role feedback 默认 session-only，明确保存才写入 temporary Demo `USER_FEEDBACK`；deprioritization 不改变 MatchResult；actions 保留 authoritative target／relation／expected evidence；map 无 score/ranking；reset 更换 workflow/subject/storage 并清除所有 v0.2 state；全程 public synthetic + Fake provider，无外部 runtime 网络与 Phase 7B 能力。

**可选用户参与：**从第一个职业问题完成画像确认，保存一条 role clarification 到 Demo Memory，操作一项 Action status，查看 Career Exploration Map 与「Orange 对你的长期理解」，最后 Reset。此任务不是考试或完成门。

**主要风险与 fallback：**guided answers 可能被误读为历史证据或长期事实。Fallback 是对每项显示 authority label，session answer 默认不持久化，Memory 写入必须经过显式「保存」，且 conversation state 不参与 domain routing／Match mutation。

## Phase 7B — Semantic & Hybrid Memory Retrieval

**范围：**通过 `EmbeddingProvider`／`FakeEmbeddingProvider`／`LocalEmbeddingProvider`，为 active confirmed `MemoryRecord` 建立独立、可丢弃、可重建的 sqlite-vec index。`SemanticMemoryRetriever` 在向量命中后必须回查 canonical `MemoryStore`；`HybridMemoryRetriever` 用固定 `k=60` 的一基 rank RRF 融合原有 lexical 与 semantic 结果；`MemoryContextBuilder` 只生成有数量／字符边界的 structured context。

**Exit criteria：**canonical DB 继续使用 stdlib sqlite3；vector DB 只使用 pysqlite3 + sqlite-vec 且保持 separate/private；candidate、superseded、archived 和 stale rows 不可进入结果；subject isolation、lifecycle sync、rebuild、purge、RRF provenance 与 public multilingual local-model acceptance 全部通过；normal pytest 只用 Fake 且零网络；没有自动 Agent/LangGraph injection。

**可选用户参与：**运行 public semantic-memory Demo，对比 lexical、semantic 与 hybrid rank，然后 supersede top Memory 并观察旧记录从 active retrieval 消失。

**主要风险与 fallback：**两个 DB 无法共享一个 SQLite transaction，canonical 写入始终优先；derived sync 失败记录安全 diagnostic，并通过 rebuild 恢复。vector DB 丢失时 canonical operations 不受影响，hybrid 可显式 surfaced lexical-only fallback。

**状态：COMPLETE（以最终自动化、离线 real-model acceptance 与安全扫描为准）。** 下一阶段的 Agent-aware memory context integration 仍明确 deferred。

## Phase 7C — Context-Aware Memory Integration

**范围：**只开放 `PROFILE_REFINEMENT` 与 `ROLE_EXPLORATION`。确定性 policy 决定类型、检索、top-k、预算和 consumer；query 构造不使用 LLM。Profile refinement 只生成 draft 并保留 `memory_refs`；Role recall 独立展示，不改 role facts／MatchResult。结构化同维度变化建立 session-only candidate，只有用户确认才经 canonical service supersede。

**Exit criteria：**retrieval 零 canonical write；current session／confirmed profile／historical Memory 三层 authority 分离；free text／semantic similarity 不触发 conflict；Job Intelligence 与 Match relation generation 零 Memory retrieval；update／defer／uncertain／compatible keep-both lifecycle 通过；profile v2 必须独立 review；Fake-only／public synthetic／zero-network regressions通过。

**可选用户参与：**运行 public Demo，在 AI Product Intern 中先 defer 一次结构化偏好变化，再显式更新长期理解，最后单独确认画像 revision。

**主要风险与 fallback：**retrieval context 可能被误当权威或静默污染 Match。Fallback 是 closed policy、read/write path 分离、每条个性化 statement 强制 `memory_refs`，并把 profile confirmation 置于未来 Match 之前。

**状态：COMPLETE。** 493 baseline tests 通过；本地 checkpoint `1c64e7a`：`feat: integrate context-aware career memory`，无 push。

## Phase 8A — Evaluation Framework

**范围：**独立 `evaluation/` observer；三层评估、27 个公开合成场景、closed status/taxonomy、required/forbidden/uncertainty/provenance/relation/lifecycle/workflow checks、registry、isolated deterministic runner 与 JSON/Markdown CLI reports。仅 FakeLLMProvider／FakeEmbeddingProvider，不改生产 engine，不引入模型 judge／分数／排名／private input。

**Exit criteria：**Phase 7C checkpoint、493 原回归保留、新测试与 complete Golden suite 通过；不隐藏 FAIL/review；任意 authority/subject/private/gate/lifecycle/network BLOCKING failure 必须 NEEDS REVIEW。报告保存在 ignored artifacts，Phase 8A 不自动 commit/push。

**状态：COMPLETE。** 当时 668 tests、27 scenarios（20 PASS / 7 EXPECTED_UNCERTAINTY / 0 FAIL / 0 NEEDS_REVIEW）；本地 checkpoint `e707063`，无 push。后续 8B / 8C 已完成，当前 8D 只整理公开入口；8A.1 live 仍未开始。

## Phase 8B — Safe Observability & Diagnostics

**范围：**独立 `observability/` contracts/redaction/context/events/adapters/collector/diagnostics；生产高价值路径薄 instrumentation；只升级折叠 Developer Trace；Golden报告安全关联 run/event IDs。默认本地与离线，无 trace DB/exporter、新增依赖、live request、Prompt/domain/authority 改动或 UI redesign。

**Exit criteria：**保留 668 原回归；strict metadata、录制故障、scope/reset/isolation、HITL resume、Memory/vector/Match counts 和 synthetic failure links 验证；Golden statuses 不变；public synthetic 实际 Streamlit 手动验收；secret-safe、无私有内容、无网络／推理泄露。最终证据以 Phase 8B 报告为准。

**状态：COMPLETE。** 743 tests、27 scenarios（20 PASS / 7 EXPECTED_UNCERTAINTY / 0 FAIL / 0 NEEDS_REVIEW）。用户明确批准建立唯一 local checkpoint `5a6a1d1`：`feat: add safe observability diagnostics`，无 push／remote／runtime artifacts。

**风险／取舍：**bounded local collector 不是无限历史或生产 telemetry；粗粒度 spans 不代表每个内部验证分步时长；旧 source timestamps 与当前 span 可能交错，由 timestamp/sequence/ID 稳定排序；Fake/stub 验证不证明 live 模型行为。

## Phase 8C — Product & Demo Polish

**范围：**现有 Streamlit 的集中有限 visual system、typography／spacing／card／badge／CTA、一致中文文案、conversation continuity／named journey、动态画像、Profile Review、三方向、role／Match／Action／map／Memory／安全诊断的表现层。无新依赖、截图生成、业务功能或 backend semantic changes。

**验收：**先验证 743-test／27-Golden 基线再创建上述 checkpoint；全部原测试不修改，新增 meaningful UI product contracts，Golden statuses 不变。十个目标视图、50 个手动步骤、窄屏／长文案、错误／空状态按 `docs/PRODUCT_UX_ACCEPTANCE.md` 验收；不制造 numeric UX score。具体最终状态以执行报告为准。

**状态：COMPLETE（本地工程／产品验收）。** 783 passed / 0 failed；Golden 27 / 20 PASS / 7 EXPECTED_UNCERTAINTY / 0 FAIL / 0 NEEDS_REVIEW。全部十个视图及 50 步按本地结构／交互／布局验收 PASS；无截图生成，最终 live 审美复核保留为唯一可选开发者任务。

**Checkpoint：**已获明确批准，在全部 pre-8D gates 通过后建立唯一本地 `003c5bc`；没有 push／remote。8D 文档整理不会重新修改表现层或 core semantics。

## Phase 8D — Public Portfolio Readiness

**范围：**产品优先中文 README、Product / Agent / Memory Mermaid 图、人工截图计划与 asset 策略、文档导航／当前状态、tracked／untracked／ignore／全 Git 历史审查、LICENSE 与作者元数据记录、公开与 portfolio checklist、meaningful offline tests。无新生产能力／依赖／artifact 路径／语义。

**验收：**保留全部 783 tests；full pytest、27 Golden（20 PASS / 7 EXPECTED_UNCERTAINTY / 0 FAIL / 0 NEEDS_REVIEW）、internal link／Markdown／diff check、public Demo 与安全审查。当前结果见 [公开审查记录](docs/PUBLIC_READINESS_AUDIT.md)与[验收](docs/PORTFOLIO_ACCEPTANCE.md)。

**状态：PHASE 8D COMPLETE — USER RELEASE DECISIONS PENDING。** 818 passed / 0 failed（原 783 不变 + 35 readiness tests）；Golden 前后不变；当前与全 13 commits 安全审查、本地 browser Demo、文档导航通过。无 LICENSE、图片、remote 或部署；剩余用户决定不等于技术 blocker。

**边界：**Phase 8D 修改留在 working tree，等待用户决策；不选择 LICENSE、不自动截图、不创建 remote／push／release、不改写历史、不云部署、不开始 9A / 9B。历史发现真实凭据／私有资料必须停止。技术完成不代表已发布，许可／作者元数据／截图／仓库地址与 visibility 仍由用户决定。

## Phase 8 — Observability（历史初始路线）

**范围：**实现 `AgentEvent`、`ToolEvent`、routing、error、retry、latency 与可用时的 model usage。

**Exit criteria：**一次 workflow 可用 id 串联；敏感字段脱敏；UI 能显示安全摘要；不记录／展示隐藏 chain-of-thought。

**用户学习检查：**开发者用 trace 定位一次故障并解释为什么日志足以诊断。

**主要风险与 fallback：**过量日志泄露数据或干扰 UI。Fallback 是只保留生命周期、引用、计数、错误码和延迟等最小事件。

## Phase 9 — Streamlit UI（历史路线，非当前 Phase 9A）

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

1. 历史上的 vector extension 预算（当前 local hybrid 已实现；Chroma 没有引入）；
2. 实时职位搜索、网页抓取和大规模数据集；
3. 多个真实 LLM provider（保留接口、fake 与一个 adapter）；
4. Canvas 在线连接（保留 mock／脱敏导出 adapter）；
5. 高级 UI 动画、复杂图表、导出格式和主题；
6. 大量 follow-up 能力与非核心角色。

不可删减的核心是：用户画像确认、四个 Agent 的清晰边界、deterministic-first Orchestrator、结构化契约、evidence-first 双面洞察、公开安全数据、关键错误路径和一个可复现 Golden Case。
