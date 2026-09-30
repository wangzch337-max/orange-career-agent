# Orange 学习计划 Learning Plan

Orange 采用 **Learning Mode**：交付代码与培养开发者解释、实现和验证系统的能力同等重要。开发者可以明确选择跳过正式问答／检查点；这种选择不阻止阶段完成，但仍保留可选 hands-on task 与关键概念记录。未经明确授权不自动进入下一阶段。

## Phase 0 — Foundation & Product Contract

### 1. 学习目标

建立产品边界、Agent 职责、系统层次、数据 provenance、安全约束与阶段化交付意识。

### 2. 需要理解的概念

Agent／Tool／Workflow 的边界；确定性状态机；结构化数据与向量检索的不同职责；evidence-first；execution trace 与隐藏推理的区别；ADR 的用途。

### 3. Codex 负责

搭建空仓库结构，起草产品、架构、概念数据契约、ADR、路线图与安全规则；验证所有描述只停留在 Phase 0。

### 4. 开发者亲手完成

逐份审阅文档，用自己的话画一张系统图；标出不同意或不理解的取舍；修改至少一项措辞使其符合真实产品意图；检查演示数据脱敏边界。

### 5. 验收问题

1. Agent、Tool、Workflow 有什么区别？
2. 为什么 Orange 未来适合使用 LangGraph，而不是只写一长串 Python 函数？
3. 为什么 `UserProfile` 应该保存为结构化数据，而不是全部丢进向量数据库？
4. 为什么 Orchestrator 不应该完全交给 LLM 自由控制？
5. 为什么 Observability 不等于展示 Chain-of-Thought？

提示：回答时至少联系 Orange 的一个具体状态、失败场景或数据对象；不要只背定义。

### 6. 面试中应该能如何解释

用 2–3 分钟讲清问题、Golden Flow、四个 Agent、画像确认门，以及为何架构优先可控性、证据和可替换性；能够说明一个被刻意推迟的功能及原因。

### 7. 完成标准

开发者认可所有 Phase 0 契约，能独立回答五题，仓库验证通过，并明确授权后才进入 Phase 1。

## Phase 1 — Domain Models + Deterministic Workflow Skeleton

### 1. 学习目标

把概念契约转换为最小、可验证的 Python domain models 和工作流状态骨架。

### 2. 需要理解的概念

Pydantic `BaseModel`、`Enum`、字段／跨字段 validation、JSON 序列化、状态机、确定性路由、interface／abstraction、dependency inversion、fixture-based testing、pytest 基础和 evidence provenance。

### 3. Codex 负责

实现并验证最小模型、provider 接口、Agent stub、状态机、画像确认门、内存事件与离线 Demo；避免加入 LLM 或真实匹配策略。

### 4. 开发者亲手完成

在 Codex 完成 Phase 1 后，只修改 `data/fixtures/sample_user_input.json` 中的脱敏 `career_goal`，随后重跑 pytest 与 Demo，并观察该目标如何通过 evidence 进入 `UserProfile`；不要进入 LLM 集成。

### 5. 验收问题

哪些不变量应由 schema 保证，哪些应由 workflow 保证？如何阻止未确认画像进入 matching？

### 6. 面试中应该能如何解释

展示一个验证错误和一个状态转换，说明类型契约如何降低 Agent 系统的不确定性。

### 7. 完成标准

核心 schema 可序列化、验证测试通过、工作流骨架只含确定性节点；开发者完成上述一项 hands-on 修改并能解释边界后，才可申请进入 Phase 2。

## Phase 2 — LLM Provider Abstraction + First Structured LLM Call

### 1. 学习目标

理解如何在不绑定供应商的前提下安全获得结构化模型输出。

### 2. 需要理解的概念

provider abstraction、dependency inversion、OpenAI-compatible API、环境变量、structured output、JSON Schema、Pydantic parsing、prompt versioning、retry policy、transient vs permanent failure、mock vs live API test、token usage、latency 与 secret management。

### 3. Codex 负责

实现最小 provider 协议、Fake/Qwen adapter、严格 schema、evidence-ID 验证、错误与 retry 测试、安全 usage wrapper 和离线 Demo；真实 live validation 只在本地配置存在时执行一次。

### 4. 开发者亲手完成

只修改 `data/fixtures/sample_profile_signal_input.json` 中的一句脱敏证据文本，然后运行 `python -m providers.demo`，比较为什么 Fake response 保持确定性；不要改 Agent 或加入真实个人资料。

### 5. 验收问题

若供应商返回合法 JSON 但语义错误，系统哪里处理？为什么业务层不能直接依赖 SDK response？

### 6. 面试中应该能如何解释

用一次成功和一次失败调用说明 adapter、验证、重试与成本控制。

### 7. 完成标准

Fake 与 Qwen adapter 的离线测试通过，secret 未进入仓库，失败不会污染 Shared State；完成上述 hands-on task，且 live config 存在时完成一次 smoke test，才可申请进入 Phase 3。

## Phase 3 — Self-Discovery Agent

### 1. 学习目标

从有限证据生成可修改、可追溯且不过度推断的画像草案。

### 2. 需要理解的概念

semantic extraction、deterministic assembly、provenance、uncertainty、confidence、prompt grounding、dependency injection、hybrid LLM/rule architecture、用户确认，以及事实与推断分离。

### 3. Codex 负责

实现并验证 provider-independent semantic extraction、稳定 SourceEvidence、确定性 ProfileAssembler、安全 observability、公开离线路径和私有 Golden Case 边界；检查人格诊断、无证据结论和 absence-as-weakness。

### 4. 开发者亲手完成

可选任务：只修改私有 Golden Case 中一项非敏感 `career_preferences`，运行本地 Self-Discovery Demo，并比较该明确偏好如何影响候选偏好、不确定性或澄清问题。此任务不是考试或 Phase 完成门。

### 5. 验收问题

怎样识别同一证据被重复计数？用户否定一项推断后，画像版本如何变化？

### 6. 面试中应该能如何解释

展示从 EvidenceItem 到 CandidateSkill，再到用户确认的完整 provenance 链。

### 7. 完成标准

草案字段可追溯，确认门生效，边界案例不过度诊断，离线 fixture 测试通过；开发者已选择跳过正式学习 quiz，因此不以回答问题作为 Phase 完成条件。

## Phase 4 — Job Intelligence Agent + Demo Job Dataset

### 1. 学习目标

把异构职位信息转换为一致、可比较的职业理解。

### 2. 需要理解的概念

taxonomy 设计、结构化岗位数据、语义规范化、evidence-backed inference、不确定性表达、hallucination control，以及岗位理解与用户匹配的分离。

### 3. Codex 负责

实现六类轻量 `RoleFamily`、20 条 Fictional Demo Job Records、`JobEvidenceBuilder`、provider-independent `JobIntelligenceAgent`、严格 extraction schema、evidence whitelist 与确定性 assembler，并保持 Match & Insight 为 stub。

### 4. OPTIONAL DEVELOPER HANDS-ON TASK

可选且不作为 Phase gate：只给一个 Demo role 新增一条虚构 responsibility，运行 `.venv/bin/python -m agents.job_intelligence_demo`，观察稳定 evidence ID 与对应结构化信号如何变化。

### 5. 验收问题

为什么缺失薪资或晋升信息必须保持 unknown？如何区分 `explicit_job_fact` 与 `evidence_supported_job_inference`？

### 6. 面试中应该能如何解释

说明 LLM 只做证据受限的语义解释，而确定性 Python 控制权威记录；说明为什么岗位理解与用户匹配在 Phase 4 独立。

### 7. 完成标准

20-role fixture public-safe、schema 合法、所有信号证据可解析、缺失信息保留 unknown、离线 Demo 全部通过且 live 验证只覆盖三条代表角色。

## Phase 5 — Match & Insight Engine

### 1. 学习目标

用跨领域 evidence links 组合有限语义比较与确定性验证，生成可审计且可行动的关系洞察。

### 2. 需要理解的概念

cross-domain evidence linking、semantic comparison、evidence gap 与 capability gap、experience-depth gap、不确定性、human confirmation、LLM 输出外围的 deterministic validation、explainability，以及为何推迟 scoring／ranking。

### 3. Codex 负责

实现 `MatchContextBuilder`、relation taxonomy、严格 extraction、双域 ID 校验、`MatchInsightAssembler`、action policy、confirmed-profile hard gate、all-20 offline Demo 与安全测试。

### 4. OPTIONAL DEVELOPER HANDS-ON TASK

可选且不作为 Phase gate：修改一个 PUBLIC synthetic confirmed-profile preference，运行 `.venv/bin/python -m agents.match_insight_demo`，观察 preference alignment 或 potential friction 是否变化。

### 5. 验收问题

为什么 evidence missing 不能写成 confirmed gap？为什么 private profile 必须由用户本人确认？为什么 Phase 5 不计算 overall score？

### 6. 面试中应该能如何解释

展示 LLM 如何提出跨域关系，Python 如何验证 signal/evidence IDs、relation rules 与 actions；解释为什么按岗位独立展示而不排名。

### 7. 完成标准

所有关系证据可解析、action 均关联 validated issue、20 roles 离线通过、没有 overall score／ranking；private live validation 必须等待开发者本地明确确认。

## Phase 6 — LangGraph Full Workflow Integration

### 1. 学习目标

把独立能力组装成可暂停、恢复、分支和测试的图工作流，同时保持领域语义不依赖编排框架。

### 2. 需要理解的概念

graph state、node、deterministic edge、interrupt/resume、checkpoint、thread identity、orchestration 与 domain logic 的边界、checkpoint 与 long-term memory 的边界、dependency injection，以及 idempotent/resumable workflow thinking。

### 3. Codex 负责

实现薄 LangGraph orchestration layer、显式 checkpoint-safe state、真实 profile-review interrupt、同 thread resume、内存／SQLite checkpointer、安全失败状态和 graph events；复用现有 Agents 与 ReportBuilder。

### 4. OPTIONAL DEVELOPER HANDS-ON TASK

可选且不作为 Phase gate：运行 public SQLite offline Demo，在 profile interrupt 后退出 runner，再用输出的同一 workflow ID 恢复并确认；观察 Self-Discovery call count 在恢复前后都为 1。

### 5. 验收问题

为什么 `interrupt` 节点恢复时会从节点开头重新执行？哪些 side effect 必须放在 interrupt 之前或之后？为什么 SQLite checkpoint 不是长期记忆？

### 6. 面试中应该能如何解释

说明 LangGraph 只负责状态、边、interrupt/resume 与 checkpoint，Agent／validator 继续拥有语义；解释 stable thread identity 和 idempotent node 设计如何避免重复 LLM 调用。

### 7. 完成标准

Golden Flow、确认／修订 interrupt、失败与恢复路径均有集成测试；SQLite runner 重建后从同一 checkpoint 继续；Self-Discovery 不重跑；state 无 provider、client、credential 或隐式全局依赖。

## Phase 7A — Structured & Persistent Memory

### 1. 学习目标

建立可恢复但不会把推断误当事实的长期记忆：清楚区分 workflow checkpoint、权威 confirmed profile、curated memory record 与 retrieval result。

### 2. 需要理解的概念

persistence vs checkpoint、authoritative profile vs memory record、candidate vs confirmed knowledge、immutable version history、supersession、archival、privacy purge、retrieval relevance vs factual authority、subject isolation、idempotent side effects，以及 lexical vs semantic retrieval。

### 3. Codex 负责

实现 store/retriever/service 抽象、schema v1、SQLite lifecycle、显式 authority rule、最小 graph confirmation boundary、离线测试和隐私审查；不迁移 private profile，不启动 semantic/vector retrieval。

### 4. OPTIONAL DEVELOPER HANDS-ON TASK

可选且不作为 Phase gate：运行 public synthetic memory Demo；创建 confirmed preference，用新的 confirmed preference supersede 它，分别查询 active memory 与 history，并观察 active 只有新记录而 history 同时保留新旧记录。

### 5. 验收问题

为什么 workflow checkpoint 不等于 long-term memory？为什么 retrieval relevance 不能决定某项内容是否为真？为什么 resumable workflow 附近的 profile/memory side effect 必须幂等？

### 6. 面试中应该能如何解释

用实际对象解释两个 SQLite DB 的不同生命周期；说明 confirmed profile、candidate/confirmed/superseded/archived record 的权威顺序，以及 lexical ranking 为什么只影响顺序、不修改真值状态。

### 7. 完成标准

profile immutable history/current pointer、curated lifecycle、subject isolation、transactional purge、deterministic lexical retrieval 与 replay idempotency 均通过；没有 transcript、embedding、vector retrieval 或自动 authority。

## Phase 7.5 — Orange Interactive Demo Vertical Slice

### 1. 学习目标

把已经验证的 domain engine 变成一条可操作 vertical slice，同时保持 UI adapter 与业务权威边界，不因 Streamlit rerun 重复执行昂贵或有副作用的步骤。

### 2. 需要理解的概念

vertical slice、UI adapter vs domain layer、Streamlit rerun model、browser session state、graph state vs UI state、interrupt/resume in UI、presentation models、safe developer trace，以及 synthetic/public Demo design。

### 3. Codex 负责

实现 session-scoped controller、Streamlit pages、real graph profile confirmation、presentation mappings、safe error/trace、temporary memory、telemetry configuration 与 AppTest/controller regressions；不添加 private mode、live provider 或新的业务语义。

### 4. OPTIONAL DEVELOPER HANDS-ON TASK

可选且不作为 Phase gate：从 Welcome 手动运行到 Profile Confirmation，依次打开三个角色的 Match 页面与 Memory Summary，再 Reset Demo；确认 profile confirm 前后 Self-Discovery call count 都是 1。

### 5. 验收问题

为什么 UI session state 不能成为第二个业务状态机？为什么 runtime/checkpointer 可以保存在 browser session 中但不能进入 graph state？真实 interrupt/resume 如何避免确认按钮绕过领域门？

### 6. 面试中应该能如何解释

展示 Streamlit click/rerun 如何通过薄 controller 驱动同一 LangGraph thread；说明 presentation mapping 只改变显示、不改变 domain enums／evidence；解释 synthetic fixture、Fake provider、temporary memory 与 safe trace 如何形成可公开演示边界。

### 7. 完成标准

完整 UI vertical slice、same-thread confirm、rerun idempotency、三角色展示、actions/memory/trace、reset/session isolation 均有自动化与本地验证；没有 score、ranking、private data、live provider、external data 或 Phase 7B 能力。

## Phase 7.6 — Conversation-First Product Redesign / Demo v0.2

### 1. 学习目标

把“先填表、再看结果”改造成可解释的 guided career conversation，并用 progressive disclosure 让用户先理解自己，再逐步进入岗位、证据和行动。

### 2. 需要理解的概念

guided conversation design、progressive disclosure、information hierarchy、session state vs domain state、product feedback → confirmed Memory、presentation transformation、task-oriented action UX，以及 career exploration vs ranking。

### 3. Codex 负责

实现显式 `ConversationStage`、controller-owned session interaction、动态画像 authority labels、profile calibration、role clarification、临时 confirmed feedback、Match group presentation、Action task views、Career Exploration Map、long-term understanding view、reset isolation 与离线测试；不改变 Agent／Match／Memory authority semantics。

### 4. OPTIONAL DEVELOPER HANDS-ON TASK

运行 Orange v0.2：从第一个引导职业问题走到画像确认；保存一条岗位澄清到 Demo Memory；完成一次 Action Plan 交互；查看 Career Exploration Map 与「Orange 对你的长期理解」；最后 Reset。

### 5. 验收问题

为什么 guided conversation state 不能决定 LangGraph domain routing？为什么“用户刚刚表达”不等于“已有证据”？为什么 role deprioritization 不能转成 confirmed gap？

### 6. 面试中应该能如何解释

用一次完整交互说明 progressive disclosure 如何降低认知负担；展示 view model 如何把 authoritative domain output 变得可读，却不改写 evidence、relation 或 action；解释显式保存如何把 session feedback 安全升级为 confirmed Memory。

### 7. 完成标准

Conversation、dynamic profile、role clarification、Match、Action、exploration map、Memory 与 reset 都有自动化及手动验证；界面无 profile completeness、score/ranking 或自由 LLM routing；公开合成／Fake-only／temporary-storage 边界保持成立。

## Phase 7B — Semantic/Vector Retrieval（未开始）

未来单独学习 embedding、semantic similarity、vector metadata filter、retrieval evaluation 与隐私/retention tradeoff。开始前必须先证明 lexical retrieval 不足，并重新确认：semantic relevance 仍不能覆盖 explicit confirmation。

## Phase 8 — Observability

### 1. 学习目标

建立可调试、可演示且保护隐私的事件系统。

### 2. 需要理解的概念

structured logging、correlation id、latency、error taxonomy、redaction、token usage、decision summary。

### 3. Codex 负责

提供事件 schema、脱敏测试和 trace 视图建议；检查是否泄露 prompt、secret 或隐藏推理。

### 4. 开发者亲手完成

埋点一个完整流程，定位一次注入的失败，并写出用户可读的错误摘要。

### 5. 验收问题

哪些字段适合日志，哪些只能存在 session？如何从事件判断重试是否有效？

### 6. 面试中应该能如何解释

展示 execution trace 如何帮助调试与建立用户信任，同时不等于 chain-of-thought。

### 7. 完成标准

关键节点／工具事件完整、可关联、脱敏，失败与延迟可定位，安全测试通过。

## Phase 9 — Streamlit UI

### 1. 学习目标

把架构契约转化为清晰的人机协作体验。

### 2. 需要理解的概念

session state、form、rerun、loading/error state、可访问性、信息层级、确认交互。

### 3. Codex 负责

搭建最小页面骨架、状态映射和 UI 测试建议；保持中文优先与非权威表达。

### 4. 开发者亲手完成

设计并实现画像编辑／确认体验的一部分，邀请一位测试者完成 Golden Flow。

### 5. 验收问题

UI rerun 如何避免重复调用模型？用户如何分辨事实、推断和建议？

### 6. 面试中应该能如何解释

从用户控制权出发说明确认门、trace 和双面洞察的界面设计。

### 7. 完成标准

Golden Flow 可操作，错误／等待状态清晰，刷新不重复副作用，用户测试反馈已处理。

## Phase 10 — Course Data Adapter / Sanitized Canvas Export

### 1. 学习目标

通过受控 adapter 使用外部课程数据，同时维持跨大学复用和凭据隔离。

### 2. 需要理解的概念

adapter、schema mapping、数据最小化、sanitization、fixture、跨仓库 trust boundary。

### 3. Codex 负责

定义导入契约、校验器和 mock；不读取另一仓库凭据或替开发者决定敏感字段。

### 4. 开发者亲手完成

审阅并执行一次脱敏映射，逐字段确认公开 fixture 不含身份信息。

### 5. 验收问题

为何 Orange 不直接调用 Canvas？换成另一所大学时哪些组件需要变化？

### 6. 面试中应该能如何解释

画出 Canvas → sync → sanitized export → Orange 的边界和故障隔离。

### 7. 完成标准

mock 与脱敏导出使用同一接口，离线 Demo 可运行，secret scan 与人工审阅通过。

## Phase 11 — Testing + Error Handling + Cost Controls

### 1. 学习目标

让核心流程在模型不稳定、输入缺失和外部失败下仍可预测。

### 2. 需要理解的概念

test pyramid、contract test、fault injection、retry/backoff、timeout、budget、caching、graceful degradation。

### 3. Codex 负责

协助建立覆盖矩阵、故障 fixture 和 CI 建议，识别高风险未测路径。

### 4. 开发者亲手完成

编写一个端到端测试和一个故障注入测试；定义可接受的单次 Demo 成本／延迟预算。

### 5. 验收问题

哪些错误可重试、哪些必须立即停止？怎样防止重试造成重复成本或状态污染？

### 6. 面试中应该能如何解释

用测试失败修复案例说明可靠性、成本与用户体验的权衡。

### 7. 完成标准

核心覆盖矩阵通过，重试有上限，预算可观测，关键失败有用户可理解的降级路径。

## Phase 12 — Demo Cases + README + Interview Story

### 1. 学习目标

用可信演示和技术叙事呈现产品价值与工程取舍。

### 2. 需要理解的概念

Golden Case、edge case、reproducibility、portfolio narrative、claim/evidence alignment。

### 3. Codex 负责

审阅演示脚本、文档准确性和技术叙事；查找夸大或与实现不符的 claim。

### 4. 开发者亲手完成

独立演示并录制一次讲解草稿；回答架构追问；根据反馈改写 README 的关键段落。

### 5. 验收问题

如果只能展示三分钟，哪些证据最能证明 Orange 不是普通聊天机器人？

### 6. 面试中应该能如何解释

以问题—约束—取舍—验证—反思结构讲述项目，并明确自己亲手完成的部分。

### 7. 完成标准

至少一个 Golden Case 与一个边界案例可复现，README claim 与实际一致，开发者可无稿讲解。

## Phase 13 — Final Polish + Demo Video

### 1. 学习目标

完成发布前质量收敛，并对已知限制做诚实说明。

### 2. 需要理解的概念

release checklist、版本标记、文档一致性、可复现环境、演示恢复方案。

### 3. Codex 负责

协助最终审计、缺陷分级、文案一致性与安全扫描；不替代开发者的最终讲解。

### 4. 开发者亲手完成

完成 demo video、从干净环境复现安装、整理已知限制与下一步反思。

### 5. 验收问题

哪些限制必须在公开演示中主动说明？如果外部模型不可用，Demo 如何降级？

### 6. 面试中应该能如何解释

清楚区分已实现、计划中和主动删减的能力，并说明下一轮最优先验证的假设。

### 7. 完成标准

发布清单、安全与测试通过，演示可复现且有 fallback，视频和仓库不包含隐私或虚假 claim。
