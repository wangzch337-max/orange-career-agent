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

数据规范化、taxonomy、来源时效、fixture 设计、角色与单个招聘职位的差别。

### 3. Codex 负责

协助定义最小字段、数据质量检查和去标识化规则；评审约 15–20 个代表角色的平衡性。

### 4. 开发者亲手完成

研究并整理一部分代表角色，标记来源与日期；手工验证至少两条 `actual_work` 是否贴近现实。

### 5. 验收问题

如何避免把某一家公司职位描述当作整个职业的真相？热度为何不能替代职业解释？

### 6. 面试中应该能如何解释

说明规范化流程、来源限制和为何首个 Demo 选择小而精的数据集。

### 7. 完成标准

fixture 脱敏、schema 合法、角色覆盖合理、每条核心说明有来源或明确推断标记。

## Phase 5 — Match & Insight Engine

### 1. 学习目标

组合确定性比较与有限语义推理，生成平衡、可行动的洞察。

### 2. 需要理解的概念

多维评分、缺失数据、权重敏感性、evidence linking、反证、recommendation calibration。

### 3. Codex 负责

设计规则测试、分数免责声明、缺口／行动 schema 与极端案例评审。

### 4. 开发者亲手完成

实现至少一个确定性维度，手算一个案例并与程序结果比较；解释权重变化的影响。

### 5. 验收问题

同一总分为何可能对应完全不同的建议？没有证据应记为“不匹配”还是“不确定”？

### 6. 面试中应该能如何解释

展示规则负责什么、LLM 负责什么，以及结果为何同时包含 fit 与 friction。

### 7. 完成标准

分数可复算，证据引用完整，缺失值策略明确，输出含局限与行动而非单一排名。

## Phase 6 — LangGraph Full Workflow Integration

### 1. 学习目标

把独立能力组装成可暂停、恢复、分支和测试的图工作流。

### 2. 需要理解的概念

node、edge、state、conditional routing、checkpoint、人机协作门、幂等性。

### 3. Codex 负责

提供图设计审查、集成测试骨架和错误路径建议，避免把所有逻辑塞进 node。

### 4. 开发者亲手完成

亲手连接关键节点与画像确认 conditional edge，并画出实际运行 trace。

### 5. 验收问题

哪些步骤可安全重跑？用户编辑画像后从哪里恢复，哪些结果必须失效？

### 6. 面试中应该能如何解释

从 Python 函数骨架迁移到 LangGraph 的实际收益，而不是只说“更适合 Agent”。

### 7. 完成标准

Golden Flow、确认暂停、失败与恢复路径均有集成测试，状态无隐式全局依赖。

## Phase 7 — Memory Layer

### 1. 学习目标

实现不同生命周期和权威级别的记忆，而非把所有内容向量化。

### 2. 需要理解的概念

session state、structured store、vector retrieval、embedding、metadata filter、retention、删除与冲突处理。

### 3. Codex 负责

设计接口、迁移与检索评估；审查最小化存储和隐私边界。

### 4. 开发者亲手完成

实现结构化画像持久化或迁移的一部分，并设计一组检索相关性测试。

### 5. 验收问题

当向量检索片段与用户最新确认画像冲突时，谁优先？如何删除用户长期记忆？

### 6. 面试中应该能如何解释

用实际对象说明三层记忆的职责、生命周期与权威顺序。

### 7. 完成标准

三层接口分离，冲突与删除策略测试通过，向量结果不会覆盖权威画像。

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
