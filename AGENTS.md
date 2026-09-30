# Orange AI 编码协作规范

本文件约束所有在本仓库工作的 AI 编码 Agent。违反约束时，应停止修改并向开发者报告，而不是自行扩大范围。

## 项目目的与边界

Orange 是面向大学生的 AI 职业探索 Agent，核心顺序是“先理解自己，再理解工作，最后做职业决策”。项目不是香港城市大学官方产品；架构必须保持 university-agnostic。当前阶段以仓库根目录中的 `README.md` 与阶段计划为准。

只修改本仓库。不得读取、复用或修改其他仓库中的凭据、私有配置或实现，尤其不得读取 `cityu-canvas-sync` 的 `.env.local`。发现目标文件与当前阶段冲突、意外数据或不明凭据时，立即停止并报告。

## 语言与代码规范

- README、产品文档、架构说明、未来 UI 文案和演示报告以中文为主，必要时保留英文术语。
- Python 类型、函数、变量、模块等代码标识符使用专业英文，例如 `UserProfile`、`JobRecord`、`run_workflow()`；不得使用中文标识符。
- 代码注释可主要使用中文。公共接口应有清晰、简洁的 docstring。

## 阶段式开发

- 严格按 `IMPLEMENTATION_PLAN.md` 推进，不跨阶段实现。
- 当前 Phase 7.5 只允许 public synthetic Streamlit vertical slice：薄 UI/controller adapter、session-scoped `InMemorySaver`、temporary memory DB、真实 LangGraph profile interrupt/resume、三个固定角色、validated domain output 与安全 developer trace。
- Phase 7.5 不得实现 private mode、live provider、vector／semantic retrieval、embedding、sqlite-vec、transcript dumping、automatic authority、overall Match score、岗位排名、Canvas、职位抓取、认证、部署、Phase 7B 或 Phase 8 新能力。UI 不得拥有或复制 Agent／Match／memory 语义。
- 不得静默改变四个核心 Agent、Golden Flow、数据边界或目录结构。必要变更必须先记录理由、影响和取舍，并取得确认。
- 每个阶段结束时运行与风险相称的测试；测试失败不得伪装为完成。

## 固定核心 Agent 角色

架构必须保持以下且仅以下四个核心概念 Agent 角色，名称不得静默变更：

- `Self-Discovery Agent`
- `Job Intelligence Agent`
- `Match & Insight Agent`
- `Orchestrator Agent`

`Report Builder` 是聚合／格式化组件，不是第五个核心 Agent。普通函数和 Tool 也不得为了包装为“多 Agent”而被错误命名为 Agent。

## 工程与产品原则

- 优先结构化输出和可验证 schema，避免把关键状态隐藏在自由文本中。
- Deterministic before LLM：校验、状态转换、路由、重试、错误处理、规范化和可确定的计分优先使用确定性代码。
- Evidence first：重要结论区分明确事实、观察证据、模型推断和建议，并通过 `evidence_ids` 等方式保留来源。
- 不以总体匹配分数或岗位排名替用户做决定；只展示可验证的多维证据关系，且不保证就业结果。
- 用户画像必须经过用户确认、修改或补充；不得让 AI 单方面定义用户。
- 可观测性展示 execution trace、decision summary、evidence、tool/workflow event，不展示或声称展示隐藏 chain-of-thought。

## 安全与公开仓库要求

- 默认所有已提交内容将公开。不得提交真实学号、私人邮箱、电话、精确地址、账号标识、Canvas token、LLM key 或课程凭据。
- `.env`、`.env.*`、`data/private/` 和本地私有输入必须保持忽略；只有 `.env.example` 可以提交，且仅含空占位符。
- 公共演示数据必须去标识化；真实背景只能留在未提交的私有本地范围。
- 不得把凭据写入代码、测试、日志、文档、截图或示例。

## Learning Mode（强制）

用户已明确选择跳过 Phase 3 的正式 quiz/checkpoint；这不阻止本阶段完成。仍需记录关键概念，并只提供一个可选、非考试性质的 hands-on task。

每个实现阶段都必须明确列出：

1. Codex 负责的工作；
2. 开发者亲手完成的关键任务；
3. 开发者必须理解的概念；
4. 验收／面试问题；
5. 进入下一阶段前的停止条件。

Codex 不得为了更快交付而拿走有意义的学习机会，也不得制造无意义的忙碌。适合开发者亲手完成的任务应能训练 Python 工程、数据建模、Agent/Tool/Workflow 边界、LangGraph、LLM 集成、记忆、检索、可观测性、Streamlit、测试或产品架构能力。

## 停止并报告

遇到以下情况必须停止当前扩展并报告：阶段目标不明确；需要改变核心架构；发现真实敏感数据；需要跨仓库读取私密内容；验证连续失败且原因不明；或下一步需要开发者完成学习检查。报告应包含已完成项、证据、阻塞原因、风险和最小可选方案。
