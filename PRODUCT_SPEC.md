# Orange 产品规格 Product Specification

**文档状态：Phase 0 产品契约**
**产品副标题：AI Career Discovery Agent for University Students**

## 1. 产品愿景 Product Vision

Orange 帮助大学生以更有证据、更透明、更可行动的方式理解自己和职业。产品不是“热门岗位推荐器”，而是职业探索的思考伙伴：先建立可被用户修正的自我理解，再解释岗位真实内容，最后提供带来源、限制和下一步行动的判断。

核心理念：**Understand yourself first, understand jobs second, then make a career decision.**

## 2. 问题陈述 Problem Statement

学生在职业探索中面对三类断层：个人经历尚未被整理为可信画像；职位名称与真实日常工作之间存在信息差；推荐结果常缺乏证据、反面因素和行动路径。Orange 计划把这些环节连接成可审阅的工作流，同时避免用单一分数替代人的判断。

## 3. 目标用户 Target Users

- 长期用户：不同大学、学科和年级的学生。
- 初始 Demo：以 AI 或相关方向为背景的 CityU 硕士生，但仅使用去标识化 fixture。
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
10. 经授权的长期结构化画像影响后续会话。

画像未确认、关键输入不完整或校验失败时，Orchestrator 应停留、请求修正或进入明确错误路径，而不是静默继续。

## 7. 四个核心 Agent 的固定职责

### 7.1 Self-Discovery Agent

分析用户输入、课程／项目／技能证据；推断候选技能；识别兴趣、职业价值信号、优势、发展领域和目标；生成带重要证据引用的 `UserProfile`。不得进行无支持的人格诊断。

### 7.2 Job Intelligence Agent

规范化职位与角色信息；解释实际工作内容、能力要求、常见发展路径、优势、潜在缺点和工作方式；明确区分职业理解与市场热度。

### 7.3 Match & Insight Agent

比较 `UserProfile` 与 `JobIntelligenceRecord`；可确定的校验和计分使用规则，语义解释才使用 LLM；生成有证据的适配原因、能力缺口、潜在摩擦和行动建议。匹配分数不得表述为客观真理。

### 7.4 Orchestrator Agent

管理 Shared State、Agent 与 Tool 调用、路由、校验、重试、错误和最终聚合。架构上以确定性工作流编排为主，不设计成可随意决定流程的自治 LLM。

## 8. 用户画像确认 Profile Confirmation

`UserProfile` 是可版本化、可编辑的结构化草案，不是 AI 对用户的终局判断。界面需要展示结论、来源、置信度和可编辑字段；用户的明确修改具有更高权威性。未经确认的画像不得被当作已验证事实，也不得直接触发最终匹配报告。

## 9. 职业角色分析 Role Analysis

Job Intelligence 输出应覆盖：标准角色名称、地区／行业元数据、实际工作、核心能力、典型发展路径、优势、潜在缺点与工作方式。首个 Demo 使用约 15–20 个代表性角色，而不是数百个职位；Phase 0 不创建数据集。

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

可用 skills、interests、values、experience、growth fit 等维度帮助解释，但不得把总分当成客观真理。输出应同时展示支持与反对因素，并明确不确定性。

## 11. Evidence-first 原则

重要陈述须尽可能关联 `EvidenceItem`，并区分：

1. **明确用户事实**：用户直接陈述；
2. **观察证据**：课程、项目或职位描述中可定位的内容；
3. **模型推断**：根据证据形成、带置信度且可被纠正的推论；
4. **建议**：面向目标与缺口的行动选项。

系统不得把推断改写成事实，也不得在没有证据时生成确定性人格标签。

## 12. 地理与数据范围

长期职位市场覆盖中国大陆、香港、澳门和台湾。职位数据模型应允许地区、语言、签证／工作资格、数据时间等元数据，但 Phase 0 不采集实时职位。课程数据通过 provider abstraction 输入，不直接依赖 CityU Canvas 在线服务。

## 13. Demo 范围

首个 Golden Case 使用去标识化的代表性学术／项目资料和约 15–20 个职业角色。Demo 聚焦“输入 → 画像确认 → 职业理解 → 匹配洞察 → 行动计划 → 追问”的完整性。Phase 0 只定义契约，不创建实际个人画像、职位数据或 AI 输出。

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

在核心 Demo 验证后，可扩展更多大学数据适配器、职位来源、地区规则、长期记忆、导师协作、对比报告和反馈闭环。任何扩展都必须继续遵守用户确认、来源可追溯、最小数据收集和非自动决策原则。

## 16. 伦理与 Responsible AI

- 保持用户自主权，避免权威式职业定论；
- 对不确定性、数据时效与模型限制进行显式说明；
- 避免因学校、地区、性别或其他敏感属性造成刻板推断；
- 允许用户更正、删除或不提供非必要信息；
- 不把模型输出当作心理测评、雇佣保证或专业咨询；
- 记录可公开的 execution trace 与 evidence，不保存或展示隐藏推理过程；
- 对公开 Demo 采用数据最小化与去标识化。
