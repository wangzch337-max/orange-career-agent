# Orange 产品规格 Product Specification

**文档状态：Orange Career v1.3D.6；下方 Golden Flow 保留初始引导产品契约。**

D.6 = uncertainty reduction：单条合法 D.5 UNKNOWN/PARTIAL 的具体未证实范围，临时澄清或 optional public synthetic experiment。九模板 source-bound、明确选择、可跳过/中止；所有结果/摘要 session-only，Profile/Memory writes=0/new consumer=NO、D.5 mutation=0、无 score/ranking、考试、fit judgment、Learning/Action Plan。handoff 只提示已有确认入口，不自动调用旧流程。详见 [D.6](docs/EVIDENCE_GAP_VALIDATION.md)。D.1–D.5 已冻结在 `d84005a`。

D.5 = evidence relationship analysis，A Evidence Relationship Map + B Progressive Conversation：one confirmed user ↔ one valid D.4 role；direct/partial/unknown/evidence-backed tension，not fit score/ranking/recommendation/action plan；no Profile/Memory writes/new consumer，展示也 session-only。适合我吗只展示证据关系，不给 yes/no；新经历走既有确认路径。Fake-only / 无真实 Qwen，详见 [D.5](docs/EVIDENCE_BASED_MATCH.md)。v1.3D.4 work-side responsibility 不变。

D.4 = Representative Specific Role Understanding：D.3 的9个类型各展开一个独立 public synthetic / curated 角色例子，先目的与情境，后单维度协作、交付、决策、节奏与工具。不是 Specific Role Screening、Job Recommendation、Live Job 或 Match；无 Profile write、Memory write，不判断用户能力或适配，不确认职业目标。来源不足安全停止，歧义澄清；主聊天单输入，状态 session-only。详见 [D.4](docs/REPRESENTATIVE_SPECIFIC_ROLE.md)。D.1–D.3 checkpoint 已冻结；Final Product Polish 延期。

D.3 获批 A + C：同一聊天内了解三个公开 Demo 方向里的角色类型与工作差异。方向→角色须由独立合成来源支持，顺序非排名；角色事实不消费个人 Profile/Memory。「哪个更适合我」保留给另行授权 Match，兴趣不确认能力/职业目标。无具体职位筛选、真实招聘、网络或 Product Polish。详见 [D.3](docs/ROLE_LANDSCAPE_EXPLORATION.md)。
**产品副标题：AI Career Discovery Agent**

当前通用简历理解支持学生、经验从业者与转行者，不以学生身份、专业、项目或目标齐全为前提。ResumeEvidence 经来源/材料验证及 canonical 投影仍是候选；澄清不是补全问卷，答案不自动入长期 Memory；画像增量在主聊天审阅并明确确认。curated Memory 是另行 opt-in 的已确认信号。完整离线链已通过，有限 C.1/C.2/B.2 live 已通过，修复后 Clarification/Profile Refinement 完整真实链仍有不阻塞开发的验证缺口；没有生产认证、OCR、完整 DLP 或云端取消保证。D.1 提出宽泛候选；D.2 从有效选择进入公开合成的工作情境理解，不评价个人适合程度。当前范围与验证以 [README](README.md)及[冻结记录](docs/UNIVERSAL_CAREER_VALIDATION.md)为准。

## 1. 产品愿景 Product Vision

Orange 帮助不同职业背景的用户以更有证据、更透明、更可行动的方式理解自己和职业。产品不是“热门岗位推荐器”，而是职业探索的思考伙伴：先建立可被用户修正的自我理解，再解释岗位真实内容，最后提供带来源、限制和下一步行动的判断。

核心理念：**Understand yourself first, understand jobs second, then make a career decision.**

## 2. 问题陈述 Problem Statement

学生在职业探索中面对三类断层：个人经历尚未被整理为可信画像；职位名称与真实日常工作之间存在信息差；推荐结果常缺乏证据、反面因素和行动路径。Orange 已把这些环节连接成本地可审阅工作流，同时避免用单一分数替代人的判断。

## 3. 目标用户 Target Users

- 用户：学生、经验专业人士与转行者；工作经历是一等证据，项目/学历/目标不是必填。
- 保留的 Golden Demo：公开虚构的 AI 相关学生 persona；通用跨背景验收另用17个合成场景，均不读取真实用户资料；不是 CityU 官方产品。
- 架构约束：不得假设所有用户来自 CityU；大学、地区、课程来源均应是可替换元数据或 provider。

## 4. 核心用户需求

- 识别有证据支持的技能、兴趣、价值观、优势、发展领域和目标。
- 理解岗位实际上每天做什么，而不仅是职位名称或热度。
- 查看“为什么可能适合”与“为什么可能不适合”。
- 理解能力缺口，并得到具体、可执行的下一步。
- 查看信息来源、推断性质和工作流状态，并能修正系统理解。

## 5. V1 非目标 Non-goals

V1 明确不包括：

- 自动填写简历；
- 自动申请职位或自动化批量投递；
- 心理或人格诊断；
- 不透明的职业决定；
- 保证录用、薪资或职业结果；
- 首个 Demo 中的全国实时职位聚合；
- 取代职业顾问、导师或用户本人的最终判断。

## 6. Golden Flow

1. 用户输入教育、课程、项目、技能、偏好和目标等背景。
2. Orchestrator Agent 初始化并验证工作流状态。
3. Self-Discovery Agent 识别证据与候选画像信号。
4. 系统生成结构化 `UserProfile` 草案。
5. 系统提示：“这是我目前对你的理解，你可以确认、修改或补充。”用户确认后才进入匹配。
6. Job Intelligence Agent 为候选角色生成规范化解释。
7. Match & Insight Agent 进行多维比较，确定性规则优先，语义推理按需使用。
8. Report Builder 汇总适配依据、摩擦点、缺口与行动计划。
9. 用户基于报告追问并检视证据。
10. 显式 Memory policy 为 profile refinement 与 role recall 提供已确认历史；新草案仍需确认。当前浏览器 Demo 使用 session 临时 store，不承诺跨启动保留。

画像未确认、关键输入不完整或校验失败时，Orchestrator 应停留、请求修正或进入明确错误路径，而不是静默继续。

## 7. 四个核心 Agent 的固定职责

### 7.1 Self-Discovery Agent

分析用户输入、课程／项目／技能证据；推断候选技能；识别兴趣、职业价值信号、优势、发展领域和目标；生成带重要证据引用的 `UserProfile`。不得进行无支持的人格诊断。

### 7.2 Job Intelligence Agent

规范化职位与角色信息；解释实际工作内容、能力要求、常见发展路径、优势、潜在缺点和工作方式；明确区分职业理解与市场热度。

### 7.3 Match & Insight Agent

比较 confirmed `UserProfile` 与 `JobIntelligenceRecord`；LLM 提出关系候选，确定性代码验证 schema、signal/evidence ownership、语义最低条件与 action policy。输出八类证据关系，不计算总体分、适配百分比或岗位排名；缺少证据不转 confirmed gap，职业偏好不证明能力。Job Intelligence 与 Match relation generation 不消费 retrieved Memory。

### 7.4 Orchestrator Agent

管理 Shared State、Agent 与 Tool 调用、路由、校验、重试、错误和最终聚合。架构上以确定性工作流编排为主，不设计成可随意决定流程的自治 LLM。

## 8. 用户画像确认 Profile Confirmation

`UserProfile` 是可版本化、可编辑的结构化草案，不是 AI 对用户的终局判断。界面需要展示结论、来源、置信度和可编辑字段；用户的明确修改具有更高权威性。未经确认的画像不得被当作已验证事实，也不得直接触发最终匹配报告。

## 9. 职业角色分析 Role Analysis

Job Intelligence 输出覆盖角色、地区／行业元数据、实际工作、能力、工作方式、协作与成长暴露；未提供的薪资、晋升等事实保持 unknown。公开 dataset 有 20 条虚构角色，交互 Demo 展示 AI Product Intern、AI Application Engineer、Data Analyst 三个方向，固定顺序不代表排名。

代表范围包括：

- Product / Business：AI Product Manager、AI Product Intern、Product Manager、Technical Product Manager、AI Solutions Consultant、Business Analyst、Strategy / Innovation Analyst；
- Data / Analytics：Data Analyst、BI Analyst、Data Scientist、Decision Scientist；
- Engineering / AI：AI Engineer、Machine Learning Engineer、LLM Application Engineer、AI Agent Engineer、AI Application Engineer、Automation / AI Workflow Specialist；
- Research / Technical：Research Assistant、Applied AI Research Intern、AI Solutions Engineer；
- Cross-functional：AI Builder。

## 10. 匹配与洞察输出契约

每个角色洞察至少应表达以下概念：

- `why_it_may_fit`：可能适配的原因；
- `actual_work`：岗位实际工作；
- `evidence_of_fit`：支持判断的证据；
- `potential_friction`：价值观、工作方式或偏好上的摩擦；
- `capability_gaps`：可验证的能力缺口；
- `suggested_actions`：具体下一步。

可用 skills、interests、values、experience、growth 等维度帮助解释，但不生成总体匹配分。输出同时展示支持因素、待验证摩擦与不确定性。当前 `MatchResult` 的正式字段以 [数据契约](DATA_CONTRACTS.md)和 Pydantic models 为准；本节概念名称不是额外 schema。

## 11. Evidence-first 原则

重要陈述须尽可能关联 `EvidenceItem`，并区分：

1. **明确用户事实**：用户直接陈述；
2. **观察证据**：课程、项目或职位描述中可定位的内容；
3. **模型推断**：根据证据形成、带置信度且可被纠正的推论；
4. **建议**：面向目标与缺口的行动选项。

系统不得把推断改写成事实，也不得在没有证据时生成确定性人格标签。

## 12. 地理与数据范围

角色模型有中国大陆、香港、澳门和台湾地理元数据；这不是实时市场覆盖承诺。当前只用虚构 fixtures，不采集职位 API；签证／工作资格等未提供信息保持未知。课程数据通过 provider abstraction 输入，不依赖 Canvas 在线服务。

## 13. 保留的 Golden Demo 范围

Public Synthetic Demo 使用 `FakeLLMProvider`、`FakeEmbeddingProvider`、公开合成数据、内存 checkpoint 和临时 Memory DB；不读 `.env.local`、私有 Golden Case 或真实确认画像。Guided conversation 与动态画像 → Profile Review → 三个方向 → role clarification／Match／Action Plan／Exploration Map → 显式 Demo Memory；不是自由聊天、正式职业评估或生产级多用户 UI。正常聊天入口的本地持久化、独立同意与通用简历流程见 [README](README.md)，不与临时 Demo 混同。

## 14. V1 成功标准

- 用户能查看、修改并确认结构化画像；
- 至少一个端到端 Golden Case 稳定复现；
- 职业解释包含真实工作、优点、缺点与工作方式，而非仅排名；
- 关键结论可追溯到证据并标记推断／建议；
- 工作流错误和重试可见，且不暴露隐藏 chain-of-thought；
- provider、课程来源和大学身份可替换；
- 演示数据公开安全，核心流程测试通过；
- 开发者能够解释主要架构取舍。

## 15. 未来扩展

长期结构化 Memory、hybrid retrieval 与三个显式 consumer（PROFILE_REFINEMENT、ROLE_EXPLORATION、CAREER_DIRECTION_DISCOVERY）已实现。D.2 不新增 consumer，不读取/写入 Memory。更多大学 adapter、真实职位、认证／云部署、导师协作等未实现；Phase 9A / 9B 尚未开始，需单独授权。任何扩展都必须遵守用户确认、来源可追溯、最小数据收集和非自动决策原则。

## 16. 伦理与 Responsible AI

- 保持用户自主权，避免权威式职业定论；
- 对不确定性、数据时效与模型限制进行显式说明；
- 避免因学校、地区、性别或其他敏感属性造成刻板推断；
- 允许用户更正、删除或不提供非必要信息；
- 不把模型输出当作心理测评、雇佣保证或专业咨询；
- 记录可公开的 execution trace 与 evidence，不保存或展示隐藏推理过程；
- 对公开 Demo 采用数据最小化与去标识化。
